"""Stage-2 rerankers for the golden-set grid: the same candidate pool, only the ranking changes.

A ranker replaces backend/recommender.rank_candidates(ok, tag, text_match=None). It scores each candidate's own
evidence sentences (max over its first `max_evidence` usable sentences) with one text model and combines:

    evidence = w_text * T + (1 - w_text) * proof          (proof = backend.proof_strength: tier, equipment, location)
    score    = evidence * closeness(km, travel_km(tag) * travel_mult)
    order    = solid proof first (as live), then score

Text models (T in [0, 1]):
    none        T = 0 (pure rules; w_text ignored)
    bm25        BM25 over the pool's sentences, squashed s / (s + 5)
    bi          bge-small-en-v1.5 cosine (bi-encoder)
    ce_msmarco  cross-encoder/ms-marco-MiniLM-L6-v2, sigmoid (the live default model)
    ce_bge      BAAI/bge-reranker-base, sigmoid
    ce_bge_l    BAAI/bge-reranker-large, sigmoid
    nli         cross-encoder/nli-deberta-v3-small: P(entailment) of "This facility provides <service>." given the sentence
    llm_qwen05  Qwen2.5-0.5B-Instruct, zero-shot: P("yes") to "Does this sentence say the facility itself currently
                provides <service>?" (a small instruction LLM used as an evidence verifier, not a generator)
    llm_qwen15  same with Qwen2.5-1.5B-Instruct
    ensemble    mean of ce_msmarco, ce_bge and nli
"""
from __future__ import annotations

import math
import re
from functools import lru_cache

import numpy as np
import pandas as pd

LLMS = {"llm_qwen05": "Qwen/Qwen2.5-0.5B-Instruct", "llm_qwen15": "Qwen/Qwen2.5-1.5B-Instruct"}
MODELS = {"ce_msmarco": "cross-encoder/ms-marco-MiniLM-L6-v2", "ce_bge": "BAAI/bge-reranker-base",
          "ce_bge_l": "BAAI/bge-reranker-large", "nli": "cross-encoder/nli-deberta-v3-small", "bi": "BAAI/bge-small-en-v1.5"}
_CACHE: dict = {}


@lru_cache(maxsize=None)
def _llm(kind):
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    tok = AutoTokenizer.from_pretrained(LLMS[kind], padding_side="left")
    model = AutoModelForCausalLM.from_pretrained(LLMS[kind], torch_dtype=torch.float32).eval()
    yes = [tok.encode(w, add_special_tokens=False)[0] for w in ("yes", "Yes", " yes", " Yes")]
    no = [tok.encode(w, add_special_tokens=False)[0] for w in ("no", "No", " no", " No")]
    return tok, model, yes, no


def _llm_scores(kind, service, texts, batch=16):
    import torch
    tok, model, yes, no = _llm(kind)
    prompts = [tok.apply_chat_template([
        {"role": "system", "content": "You check hospital records. Answer only yes or no."},
        {"role": "user", "content": f"Record sentence: \"{t}\"\nDoes this sentence say that this facility itself currently "
                                    f"provides {service}? Planned, referred, outsourced, negated or only related services count as no."}],
        tokenize=False, add_generation_prompt=True) for t in texts]
    out = []
    with torch.no_grad():
        for i in range(0, len(prompts), batch):
            enc = tok(prompts[i:i + batch], return_tensors="pt", padding=True)
            logits = model(**enc).logits[:, -1, :]
            ly = torch.logsumexp(logits[:, yes], dim=1); ln = torch.logsumexp(logits[:, no], dim=1)
            out += torch.sigmoid(ly - ln).tolist()
    return np.array(out)


@lru_cache(maxsize=None)
def _model(kind):
    from sentence_transformers import CrossEncoder, SentenceTransformer
    return SentenceTransformer(MODELS[kind]) if kind == "bi" else CrossEncoder(MODELS[kind])


def _sigmoid(x):
    x = np.asarray(x, dtype=float)
    return 1 / (1 + np.exp(-x))


def query_text(label: str, synonyms, style: str) -> str:
    if style == "keywords":          # the live backend's query: label + synonyms
        return " ".join(dict.fromkeys([label, *synonyms]))
    return f"a hospital that provides {label.lower()}"


def text_scores(kind: str, query: str, passages: list[str]) -> np.ndarray:
    """Cached scores in [0, 1] for (query, passage) pairs."""
    if kind == "none" or not passages:
        return np.zeros(len(passages))
    if kind == "bm25":
        return _bm25(query, passages)
    if kind == "ensemble":
        return np.mean([text_scores(k, query, passages) for k in ("ce_msmarco", "ce_bge", "nli")], axis=0)
    keys = [(kind, query, p) for p in passages]
    missing = list(dict.fromkeys(k for k in keys if k not in _CACHE))
    if missing:
        texts = [k[2] for k in missing]
        if kind in LLMS:
            vals = _llm_scores(kind, query.replace("a hospital that provides ", ""), texts)
        elif kind == "bi":
            m = _model("bi")
            q = m.encode(["Represent this sentence for searching relevant passages: " + query], normalize_embeddings=True)[0]
            v = m.encode(texts, normalize_embeddings=True, batch_size=64, show_progress_bar=False) @ q
            vals = np.clip(v, 0, 1)
        elif kind == "nli":
            hyp = f"This facility provides {query.replace('a hospital that provides ', '')}."
            logits = np.asarray(_model("nli").predict([(t, hyp) for t in texts], batch_size=32, show_progress_bar=False))
            e = np.exp(logits - logits.max(axis=1, keepdims=True)); p = e / e.sum(axis=1, keepdims=True)
            label2id = {v.lower(): k for k, v in _model("nli").model.config.id2label.items()}
            vals = p[:, label2id.get("entailment", 1)]
        else:
            vals = _sigmoid(np.asarray(_model(kind).predict([(query, t) for t in texts], batch_size=32, show_progress_bar=False)).reshape(-1))
        _CACHE.update(zip(missing, map(float, vals)))
    return np.array([_CACHE[k] for k in keys])


def _bm25(query, passages, k1=1.5, b=0.75):
    tok = lambda s: re.findall(r"[a-z0-9]+", s.lower())
    docs = [tok(p) for p in passages]; q = set(tok(query))
    N = len(docs); avg = max(1.0, sum(map(len, docs)) / max(N, 1))
    df = {w: sum(w in set(d) for d in docs) for w in q}
    out = []
    for d in docs:
        s = 0.0
        for w in q:
            tf = d.count(w)
            if tf:
                idf = math.log((N - df[w] + .5) / (df[w] + .5) + 1)
                s += idf * tf * (k1 + 1) / (tf + k1 * (1 - b + b * len(d) / avg))
        out.append(s / (s + 5.0))
    return np.array(out)


def make_ranker(rec, kind="none", w_text=0.0, travel_mult=1.0, style="natural", max_evidence=5, solid_gate=True):
    """Return a replacement for recommender.rank_candidates bound to a Recommender instance (for labels/synonyms)."""
    import config
    import recommender as R

    def rank(ok: pd.DataFrame, tag: str, text_match=None):
        out = ok.copy()
        out["proof"] = R.proof_strength(out)
        out["closeness"] = R.closeness(out["distance_km"].to_numpy(), R.travel_km(tag) * travel_mult)
        if kind != "none" and len(out) and w_text > 0:
            label = rec.tags.loc[tag, "label"]
            q = query_text(label, list(rec.tags.loc[tag, "synonyms"]) + config.SERVICE_INPUT_SYNONYMS.get(tag, []), style)
            per_row, texts = [], []
            for ev in out["evidence"]:
                usable = [e["text"] for e in ev if e.get("evidence_status") == "usable" and isinstance(e.get("text"), str)
                          and e["text"].strip()][:max_evidence]
                per_row.append((len(texts), len(usable))); texts += usable
            sc = text_scores(kind, q, texts)
            out["text_match"] = [float(sc[s:s + n].max()) if n else 0.0 for s, n in per_row]
            out["evidence_strength"] = w_text * out["text_match"] + (1 - w_text) * out["proof"]
        else:
            out["text_match"] = 0.0
            out["evidence_strength"] = out["proof"]
        out["rank_score"] = out["evidence_strength"] * out["closeness"]
        out["solid_proof"] = R.solid_proof(out) if solid_gate else True
        return out.sort_values(["solid_proof", "rank_score", "distance_km", "n_explicit_usable", "unique_id"],
                               ascending=[False, False, True, False, True])
    return rank
