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

## Prudence: TF-IDF classification (`tfidf_classify.py`)

**Prudence** is the name of the service-tag classifier: the curated regex tags graded by TF-IDF.

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

## Medical vocabulary and search aliases (`medical_vocabulary.py`)

Searching the app with a synonym ("piles", "sugar", "slip disc") used to find nothing: the
demo knew six services and silently fell back to the first one. This step builds the vocabulary
for real search from a medical encyclopedia:

- **NLM MeSH 2026** Diseases (C) and Mental Disorders (F03) trees: 5,194 diseases and
  syndromes with 59,532 official synonyms.
- **MedlinePlus** health topics: plain-language names ("Piles" → Hemorrhoids, "HBP" →
  Hypertension). These are used only when MeSH lacks the term.
- **A small curated list of colloquial English and Hindi terms** common in Indian searches
  ("high bp", "slip disc", "white patches", "bawaseer", "motiyabind", "madhumeh", "pcod").
  Each one maps to a MeSH descriptor by name, and the script fails if a name is wrong.

Every name is searched in all 433k evidence sentences. Matching is longest-match-first on word
boundaries, negated or planned mentions are skipped, and generic words or non-medical senses are
blocked. For example, "joint" and "grass" are MeSH synonyms of *Marijuana Abuse*.

- **1,347 MeSH conditions appear in the data. 770 found at ≥3 facilities become condition tags**
  (`mesh:<UI>`). On a random sample of 80 facility–condition pairs, precision was **98.8%**
  (95% CI 93.3–99.8%).
- Each condition links to the curated tags whose MeSH descriptor is the same or an ancestor in the
  MeSH tree. For example, *Hernia, Inguinal* → `hernia`, and *Acute Kidney Injury* →
  `kidney-failure`.
- Each condition also has fallback specialties, taken from the curated tag's body-system group or
  from the MeSH organ branch. Generic "signs and symptoms" branches are used only when nothing
  more specific exists.
- `alias_table.csv` holds 32,683 search names, each resolved to one MeSH descriptor, plus the
  curated tag names.

**Medical corrections from checking the tags against MeSH:**

| Change | Why |
|---|---|
| Stroke no longer matches "paralysis" (−48 facilities), and ICD-10 G81 (hemiplegia) was removed | Paralysis can result from stroke but isn't stroke: Bell's palsy, cerebral palsy, spinal injury |
| Hernia references *Hernia, Abdominal*; slipped disc maps to Spine surgery | MeSH files disc herniation under Hernia, but the Hernia tag means abdominal hernia repair |
| Cancer excludes benign branches: cysts, fibroids/leiomyoma, lipoma, nevus, adenoma and others | MeSH *Neoplasms* includes benign growths |
| Skin conditions excludes breast diseases; Mental health excludes psychological sexual dysfunction | MeSH also files these under several parents; clinically they belong to oncology/surgery and urology |
| Kidney failure includes the general *Renal Insufficiency* | "kidney failure" resolved to it but missed the tag |
| Women's conditions fall back to gynaecology via MeSH 2026 branches C12.050 and C12.100.250 | MeSH 2026 has no C13 |

## Search resolver and fallback (`search_resolver.py`, `sql/facility_comprehensiveness.sql`)

The resolver first turns the user's text into a vocabulary entry. It tries, in order:

1. An exact alias.
2. The alias with filler words removed ("piles treatment near me").
3. The longest alias contained in the text.
4. A close spelling ("diabetis", "asthama").

It then answers in this order:

1. **Does any facility in the dataset have evidence?** It checks curated service tags graded
   strong or mention by Prudence, then MeSH condition mentions. (`exists_anywhere`.) The
   "suggested" grade never counts.
2. **If yes:** it returns the nearest facilities with that evidence, widening the radius from 50
   to 200 km. If the only evidence is further away, the nearest facility is still returned
   (`far: true`), together with the most comprehensive hospital nearby.
3. **If no:** it returns facilities with a relevant specialty, labelled `match_level: specialty`,
   not as a match.
4. **If nothing matches, or the text isn't understood:** it falls back to the most comprehensive
   hospitals nearby, clearly marked as a fallback.

**Comprehensiveness** is a percentile score among hospitals. It combines specialties (35%),
documented procedures, capabilities and equipment (25%), beds (20%) and doctors (20%). Missing or
implausible bed and doctor counts are left out and the weights re-normalised, and tertiary
centres (medical colleges, AIIMS) get +0.15.

The region is distance from the user, not the district field. The district field is unreliable:
Malkangiri District HQ Hospital is filed under Kendujhar. Around Bhubaneswar the top five are
AIIMS Bhubaneswar, SCB Medical College (Cuttack), Hi-Tech Medical College, Utkal Hospital and SUM
Ultimate Medicare.

```bash
python3 pipeline/search_resolver.py "bawaseer"          # resolution + exists_anywhere
python3 -m unittest discover -s pipeline/tests          # 7 tests, synthetic data
```

## Publishing to Databricks (`publish_to_databricks.py`)

Writes the catalog into the workspace next to the cleaned tables. It uploads the generated
files to the volume `workspace.cardinal_virtues.tag_files`, then (re)creates:

- `workspace.cardinal_virtues.tag_catalog`: one row per tag (service, condition or
  specialty), with facility counts, TF-IDF class counts and MeSH / ICD-10 / NUCC references.
- `workspace.cardinal_virtues.facility_tags`: one row per (facility, tag), with
  `evidence_class` (strong / mention / suggested / specialty), `tfidf_probability` and
  `evidence_refs` into `model_evidence_items`.

```bash
python3 pipeline/publish_to_databricks.py
```

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
| `condition_tags.json` | MeSH conditions found at ≥3 facilities: counts, matched terms, linked curated tags, fallback specialties |
| `alias_table.csv` | Search name → MeSH descriptor → curated tags, condition tag, fallback specialties |
| `facility_condition_tags.csv` | *(gitignored)* facility × MeSH condition with evidence refs |

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
