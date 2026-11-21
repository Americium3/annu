# Data pipeline: service & condition tags

The first step of the search flow is "does **any** facility in the dataset treat what the
user typed?". To answer that, we need a fixed vocabulary of things facilities provide.
`build_tags.py` builds that vocabulary from the cleaned Databricks tables.

## Why two tag layers

The dataset has no disease column. Service information lives in sentence lists:

| Field (in `model_evidence_items`) | Content | Example |
|---|---|---|
| `procedure` | free-text sentences | "Hemodialysis is performed in three units as a regular service" |
| `capability` | free-text sentences | "24-hour dialysis facility" |
| `equipment` | free-text sentences | "Dialysis equipment" |
| `specialty` (`model_facilities.specialties_std`) | camelCase codes, inconsistently spelled | `nephrology`, `Paediatrics`, `ENT` |

So we produce:

1. **Service / condition tags**: 100 curated tags (`tag_dictionary.py`), such as Dialysis,
   MRI, IVF, Cataract, Kidney stones, Diabetes, Cancer and Snakebite & rabies. A facility
   gets a tag when one of its procedure, capability or equipment sentences matches the
   tag's patterns. Mentions that are negated or only planned are skipped: "No dialysis
   facility", "Future liver transplantation program". Each tag has a `kind`: `condition`
   (what a user would type as a disease) or `service` (procedure, test or capability).
2. **Specialty tags**: `specialties_std` with British spellings, case and alias variants
   merged (`ENT` / `otorhinolaryngology` → `otolaryngology`, `obGy` →
   `gynecologyAndObstetrics`, ...). Codes found at fewer than 5 facilities go to
   `specialty_unmapped.csv` for review instead of becoming tags.

The vocabulary was mined from the data. An n-gram frequency pass over all 433k
procedure, capability and equipment sentences, counted by distinct facility, surfaced the
common services and conditions. Each tag's patterns were then spot-checked against random
matched sentences.

## TF-IDF classification (`tfidf_classify.py`)

Regex tags are binary. "Dialysis unit of 20 beds" and a 40-item specialty list that
happens to include "dialysis" each count as one hit. `tfidf_classify.py` grades them:

1. Vectorize every procedure, capability and equipment sentence with TF-IDF (word 1–2
   grams, sublinear TF).
2. For each tag, train a logistic-regression classifier using the regex hits as weak
   labels.
3. Score every sentence out-of-fold: 5 folds, grouped by facility, so a facility's own
   sentences never train the model that scores them.
4. Classify each (facility, tag) pair:

| Class | Rule | Meaning |
|---|---|---|
| `strong` | regex match, probability ≥ 0.5 | the sentence is about this service |
| `mention` | regex match, probability < 0.5 | named in passing, e.g. inside a long specialty list |
| `suggested` | no regex match, probability ≥ 0.8, no negation/"planned" wording | likely dictionary miss; review before trusting |

TF-IDF is used to grade and extend the regex tags, not to replace them. Two loops feed back:

- `suggested` sentences are reviewed and turned into new patterns. "PET/CT scanner",
  "Renal (Kidney) Stones Treatment" and "Heart catheterization" were added this way.
- Low-scoring regex hits point to dictionary false positives. "non-ICU beds" and
  "Quantum Magnetic Resonance Therapy" led to the `non-` negation rule and a tighter MRI
  pattern.

`tfidf_tag_report.json` lists, per tag: facility counts by class, how well the classifier
agrees with the regex labels, the top-weighted TF-IDF terms, and example sentences for
each class.

```bash
pip install -r pipeline/requirements.txt
python3 pipeline/build_tags.py      # weak labels → data/tags/facility_tags.csv
python3 pipeline/tfidf_classify.py  # → tfidf_tag_report.json, facility_tag_scores.csv
```

## Taxonomy crosswalk (`crosswalk_taxonomies.py`)

Every tag is cross-referenced with a standard vocabulary, so labels can be traced to an
authoritative definition and joined with other datasets:

| Tag layer | Reference | Source | Coverage |
|---|---|---|---|
| Service/condition | **MeSH** descriptors (ID, preferred label, tree numbers, top-level category) | U.S. National Library of Medicine, live API | 100/100 tags, 213 descriptors |
| Service/condition | **ICD-10** codes (category, block or chapter) | WHO ICD-10 2019 (`simple-icd-10`) | 65/100 tags (the rest are procedures or facility capabilities, which ICD-10 doesn't classify) |
| Specialty | **NUCC Health Care Provider Taxonomy** codes | NUCC v26.1 CSV | 98.1% of facility-specialty links (90.7% equivalent, 7.5% broader) |

- The service/condition references are curated in `tag_references.py`. MeSH terms are given by
  exact preferred label. The script resolves every label to its descriptor ID through the NLM
  API and validates every ICD-10 code against the WHO 2019 code set. It fails on anything it
  can't verify. The MeSH tree categories also give an independent check on our `group`
  assignment: for example, Eyes → C11 Eye Diseases and Dental → E06 Dentistry.
- Specialties map to NUCC in three ways. Exact name matches are trusted only within physician,
  dental and eye-care groupings. Naming differences go through the curated `SPECIALTY_TO_NUCC`
  table. Fuzzy matches with similarity ≥ 0.88 become `candidate` for review. Each mapping
  records a relation:
  - `equivalent`: the same concept.
  - `broader`: NUCC has no code this specific, so the nearest parent is used.
    "Cataract & anterior segment surgery" → Ophthalmology.
- The 163 unmapped specialties are niche concepts that NUCC doesn't classify, such as maternal
  & child health, laser dentistry and neurosciences. Together they cover 1.9% of
  facility-specialty links.
- NUCC is US-centric, and India's NMC/MCI specialty list has no machine-readable release.
  NUCC is used as the closest widely adopted standard.

```bash
python3 pipeline/crosswalk_taxonomies.py --nucc-csv /tmp/nucc_taxonomy_261.csv
```

It needs network access to `id.nlm.nih.gov` and `www.nucc.org`.

## Outputs (`data/tags/`)

| File | Contents |
|---|---|
| `service_tags.json` | Service/condition tags: id, label, kind, group, synonyms, facility count, sentence counts by field, example evidence |
| `specialty_tags.json` | Normalized specialty tags: code, label, facility count, raw variants merged into it |
| `tags.csv` | Flat list of both layers, for eyeballing |
| `specialty_unmapped.csv` | Rare specialty values (< `--min-facilities`) left out |
| `facility_tags.csv` | *(gitignored, ~15 MB)* one row per (facility, tag) with evidence refs `field:item_idx` into `model_evidence_items` |
| `tfidf_tag_report.json` | TF-IDF grading summary per tag (see above) |
| `facility_tag_scores.csv` | *(gitignored)* one row per (facility, service tag): class, best probability, best evidence ref |
| `taxonomy_crosswalk.json` | Each tag with its MeSH / ICD-10 / NUCC references and source metadata |
| `taxonomy_crosswalk.csv` | One row per (tag, reference), for review |

## Running

```bash
export DATABRICKS_HOST=https://<workspace>.cloud.databricks.com
export DATABRICKS_WAREHOUSE_ID=<sql-warehouse-id>
export DATABRICKS_TOKEN=<token>
python3 pipeline/build_tags.py
```

`build_tags.py` has no third-party dependencies: it calls the Databricks SQL Statement Execution
API directly. To iterate on `tag_dictionary.py` without re-querying, cache the inputs:

```bash
python3 pipeline/build_tags.py --evidence-cache /tmp/evidence.tsv --specialty-cache /tmp/specialties.tsv
```

On the first run it writes the caches, and on later runs it reads them (about 1.5 minutes
locally).

## Known limitations

- Matching is regex-based, graded by TF-IDF. Neither can reliably tell "treats X" apart
  from "a doctor here trained in X". Show the evidence sentence to the user, and treat a
  match as "evidence found", not as proof.
- A low TF-IDF score doesn't always mean a weak mention. Rare phrasings with little
  training data ("Lumbar Discectomy – Open/MIS") also score low.
- Negation and "planned" detection only looks 40 characters before the match.
- Counts are by `unique_id`. Rows flagged `flag_duplicate_record` in `model_facilities`
  are not collapsed.
