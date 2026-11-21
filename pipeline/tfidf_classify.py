"""Grade and extend the regex service/condition tags with a TF-IDF classifier.

The regex tags from ``build_tags.py`` are high-precision but binary: "Dialysis unit with
10 machines" and a 40-item specialty list that happens to contain "dialysis" both count
as one hit. This step trains, for every tag, a TF-IDF + logistic-regression classifier on
the evidence sentences, using the regex hits as weak labels. Each sentence then gets a
probability per tag, computed out-of-fold (5-fold, grouped by facility, so a facility's
own sentences never train the model that scores them).

Each (facility, tag) pair is then classified as:

  strong     regex match and TF-IDF probability >= --strong-threshold: the sentence is
             about this service ("Dialysis unit of 20 beds")
  mention    regex match but low probability: the service is only named in passing,
             usually inside a long list of specialties; weaker evidence
  suggested  no regex match but probability >= --suggest-threshold and no negation or
             "planned" wording: a likely miss of the dictionary, to review

Run ``build_tags.py`` first: its ``facility_tags.csv`` provides the weak labels.

Outputs (``data/tags/``):
  tfidf_tag_report.json    per tag: agreement with regex labels, top TF-IDF terms,
                           facility counts by class, example sentences
  facility_tag_scores.csv  (gitignored) one row per (facility, tag) with class, best
                           probability and best evidence reference

Requires: scikit-learn, numpy, scipy.
"""
from __future__ import annotations

import argparse
import collections
import csv
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from joblib import Parallel, delayed
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_tags import REPO_ROOT, SCHEMA, load_evidence  # noqa: E402
from tag_dictionary import NEGATION_PATTERN, TAGS  # noqa: E402

csv.field_size_limit(sys.maxsize)

VECTORIZER_PARAMS = dict(
    ngram_range=(1, 2),
    min_df=3,
    max_df=0.2,
    sublinear_tf=True,
    stop_words="english",
    token_pattern=r"(?u)\b[a-zA-Z][a-zA-Z0-9\-]+\b",  # keeps short codes such as ct, tb, iui, x-ray
)
CLASS_RANK = {"strong": 3, "mention": 2, "suggested": 1}


def log(msg: str, t0: float) -> None:
    print(f"[{time.time() - t0:6.0f}s] {msg}", file=sys.stderr)


def load_weak_labels(path: Path, index: dict[tuple[str, str, int], int], tag_col: dict[str, int], n_rows: int):
    """Rebuild the sentence × tag regex label matrix from facility_tags.csv evidence refs."""
    Y = np.zeros((n_rows, len(tag_col)), dtype=np.int8)
    with open(path) as f:
        r = csv.reader(f)
        next(r)
        for uid, tag_id, _kind, refs in r:
            if tag_id not in tag_col or not refs:
                continue
            for ref in refs.split(";"):
                field, idx = ref.split(":")
                row = index.get((uid, field, int(idx)))
                if row is not None:
                    Y[row, tag_col[tag_id]] = 1
    return Y


def fit_predict(X_train, y_train, X_test, C):
    if y_train.sum() == 0:
        return np.zeros(X_test.shape[0], dtype=np.float32)
    clf = LogisticRegression(C=C, solver="liblinear", max_iter=200)
    clf.fit(X_train, y_train)
    return clf.predict_proba(X_test)[:, 1].astype(np.float32)


def fit_coef(X, y, C):
    if y.sum() == 0:
        return np.zeros(X.shape[1], dtype=np.float32)
    clf = LogisticRegression(C=C, solver="liblinear", max_iter=200)
    clf.fit(X, y)
    return clf.coef_[0].astype(np.float32)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out-dir", default=str(REPO_ROOT / "data" / "tags"))
    ap.add_argument("--evidence-cache", help="TSV cache of evidence sentences (read if present, else written)")
    ap.add_argument("--strong-threshold", type=float, default=0.5)
    ap.add_argument("--suggest-threshold", type=float, default=0.8)
    ap.add_argument("--folds", type=int, default=5)
    ap.add_argument("--C", type=float, default=8.0, help="inverse L2 regularization strength")
    ap.add_argument("--jobs", type=int, default=-1)
    args = ap.parse_args()
    t0 = time.time()
    out = Path(args.out_dir)

    evidence = [row for row in load_evidence(args) if row[3]]
    texts = [row[3] for row in evidence]
    groups = [row[0] for row in evidence]
    index = {(uid, field, idx): i for i, (uid, field, idx, _) in enumerate(evidence)}
    tag_ids = [t.id for t in TAGS]
    tag_col = {tid: j for j, tid in enumerate(tag_ids)}
    Y = load_weak_labels(out / "facility_tags.csv", index, tag_col, len(texts))
    log(f"{len(texts)} sentences, {int(Y.sum())} regex (sentence, tag) labels", t0)

    vectorizer = TfidfVectorizer(dtype=np.float32, **VECTORIZER_PARAMS)
    X = vectorizer.fit_transform(texts).tocsr()
    X.sum_duplicates()
    vocab = np.array(vectorizer.get_feature_names_out())
    log(f"TF-IDF matrix {X.shape[0]} × {X.shape[1]}", t0)

    # Out-of-fold probabilities: every sentence is scored by a model that never saw its facility.
    P = np.zeros(Y.shape, dtype=np.float32)
    for fold, (tr, te) in enumerate(GroupKFold(n_splits=args.folds).split(X, groups=groups)):
        X_tr, X_te = X[tr], X[te]
        X_tr.sum_duplicates()  # canonicalize once; otherwise threads mutate the shared matrix in fit()
        cols = Parallel(n_jobs=args.jobs, prefer="threads")(
            delayed(fit_predict)(X_tr, Y[tr, j], X_te, args.C) for j in range(len(tag_ids)))
        P[te] = np.column_stack(cols)
        log(f"fold {fold + 1}/{args.folds} done", t0)

    coefs = Parallel(n_jobs=args.jobs, prefer="threads")(
        delayed(fit_coef)(X, Y[:, j], args.C) for j in range(len(tag_ids)))
    log("full-data models fitted for term weights", t0)

    negation = re.compile(NEGATION_PATTERN, re.I)
    # (uid, tag) -> [class, best_prob, best_ref, n_regex_sentences]
    pairs: dict[tuple[str, str], list] = {}
    examples = collections.defaultdict(lambda: {"strong": [], "mention": [], "suggested": []})

    def update(uid, tag_id, cls, prob, ref, text):
        cur = pairs.get((uid, tag_id))
        if cls != "suggested":
            n = (cur[3] if cur else 0) + 1
        else:
            n = cur[3] if cur else 0
        if cur is None or (CLASS_RANK[cls], prob) > (CLASS_RANK[cur[0]], cur[1]):
            pairs[(uid, tag_id)] = [cls, prob, ref, n]
        else:
            cur[3] = n
        ex = examples[tag_id][cls]
        if len(ex) < 5 and len(text) < 200 and text not in (e["text"] for e in ex):
            ex.append({"text": text, "probability": round(float(prob), 3)})

    rows_r, cols_r = np.nonzero(Y)
    for i, j in zip(rows_r, cols_r):
        uid, field, idx, text = evidence[i]
        cls = "strong" if P[i, j] >= args.strong_threshold else "mention"
        update(uid, tag_ids[j], cls, float(P[i, j]), f"{field}:{idx}", text)

    rows_s, cols_s = np.nonzero((P >= args.suggest_threshold) & (Y == 0))
    for i, j in zip(rows_s, cols_s):
        uid, field, idx, text = evidence[i]
        if negation.search(text):
            continue
        update(uid, tag_ids[j], "suggested", float(P[i, j]), f"{field}:{idx}", text)

    counts = collections.defaultdict(collections.Counter)
    for (uid, tag_id), (cls, *_rest) in pairs.items():
        counts[tag_id][cls] += 1

    report_tags = []
    for j, tag in enumerate(TAGS):
        y, p = Y[:, j], P[:, j] >= args.strong_threshold
        tp = int((p & (y == 1)).sum())
        top = np.argsort(coefs[j])[::-1][:12]
        c = counts[tag.id]
        report_tags.append({
            "id": tag.id,
            "label": tag.label,
            "kind": tag.kind,
            "group": tag.group,
            "facilities": {
                "strong": c["strong"],
                "mention": c["mention"],
                "suggested": c["suggested"],
                "regexTotal": c["strong"] + c["mention"],
            },
            "agreementWithRegex": {
                "regexSentences": int(y.sum()),
                "precision": round(tp / max(int(p.sum()), 1), 4),
                "recall": round(tp / max(int(y.sum()), 1), 4),
            },
            "topTerms": [str(vocab[k]) for k in top if coefs[j][k] > 0],
            "examples": examples[tag.id],
        })

    total = collections.Counter(cls for cls, *_ in pairs.values())
    y_all, p_all = Y == 1, P >= args.strong_threshold
    tp_all = int((p_all & y_all).sum())
    report = {
        "meta": {
            "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "source": f"{SCHEMA}.model_evidence_items (procedure, capability, equipment)",
            "sentences": len(texts),
            "vocabularySize": int(X.shape[1]),
            "vectorizer": {k: (list(v) if isinstance(v, tuple) else v) for k, v in VECTORIZER_PARAMS.items()},
            "classifier": f"one-vs-rest LogisticRegression(C={args.C}, liblinear), {args.folds}-fold out-of-fold, grouped by facility",
            "thresholds": {"strong": args.strong_threshold, "suggested": args.suggest_threshold},
            "facilityTagPairs": dict(total),
            "overallAgreementWithRegex": {
                "precision": round(tp_all / max(int(p_all.sum()), 1), 4),
                "recall": round(tp_all / max(int(y_all.sum()), 1), 4),
            },
        },
        "tags": report_tags,
    }
    (out / "tfidf_tag_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")

    with open(out / "facility_tag_scores.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["unique_id", "tag_id", "class", "best_probability", "best_evidence_ref", "regex_sentence_count"])
        for (uid, tag_id), (cls, prob, ref, n) in sorted(pairs.items()):
            w.writerow([uid, tag_id, cls, f"{prob:.4f}", ref, n])

    log(f"facility-tag pairs: {dict(total)}", t0)
    log(f"overall agreement with regex: {report['meta']['overallAgreementWithRegex']}", t0)
    log(f"wrote {out / 'tfidf_tag_report.json'} and facility_tag_scores.csv", t0)


if __name__ == "__main__":
    main()
