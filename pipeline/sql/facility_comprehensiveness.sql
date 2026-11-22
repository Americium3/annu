-- Comprehensiveness score per hospital, used as the search fallback: when no facility near the
-- user has evidence for the condition or service, recommend the most comprehensive hospitals
-- within reach instead of returning nothing.
--
-- Score (0-1, plus 0.15 for tertiary centres):
--   35%  distinct specialties             percentile among all hospitals
--   25%  procedures + capabilities + equipment items documented
--   20%  beds      (ignored when missing or flagged implausible; weights re-normalised)
--   20%  doctors   (ignored when missing or flagged implausible; weights re-normalised)
--   +0.15 tertiary centre (medical college / AIIMS / institute of medical sciences)
--
-- The region is decided at query time by distance from the user (see search_resolver.py):
-- the cleaned district field is unreliable (e.g. Malkangiri DHH is filed under Kendujhar).

CREATE OR REPLACE VIEW workspace.cardinal_virtues.facility_comprehensiveness
COMMENT 'Comprehensiveness score per hospital (search fallback). See pipeline/sql/facility_comprehensiveness.sql.'
AS
WITH h AS (
  SELECT
    unique_id, name, district, state, best_lat, best_lon, location_confidence,
    n_specialties_std,
    coalesce(n_procedures, 0) + coalesce(n_capabilities, 0) + coalesce(n_equipment, 0) AS n_services,
    CASE WHEN flag_impossible_beds OR flag_implausible_scale THEN NULL ELSE n_beds END AS beds,
    CASE WHEN flag_impossible_doctors OR flag_suspect_doctor_count OR flag_implausible_scale THEN NULL ELSE n_doctors END AS doctors,
    name RLIKE '(?i)medical college|AIIMS|all india institute|institute of medical sciences' AS tertiary
  FROM workspace.cardinal_virtues.model_facilities
  WHERE facility_category = 'hospital'
    AND NOT coalesce(flag_duplicate_record, false)
    AND best_lat IS NOT NULL
),
p AS (
  SELECT *,
    percent_rank() OVER (ORDER BY n_specialties_std) AS p_specialties,
    percent_rank() OVER (ORDER BY n_services) AS p_services,
    CASE WHEN beds IS NULL THEN NULL ELSE percent_rank() OVER (PARTITION BY beds IS NULL ORDER BY beds) END AS p_beds,
    CASE WHEN doctors IS NULL THEN NULL ELSE percent_rank() OVER (PARTITION BY doctors IS NULL ORDER BY doctors) END AS p_doctors
  FROM h
)
SELECT
  unique_id, name, district, state, best_lat, best_lon, location_confidence, tertiary,
  n_specialties_std, n_services, beds, doctors,
  (0.35 * p_specialties + 0.25 * p_services + 0.20 * coalesce(p_beds, 0) + 0.20 * coalesce(p_doctors, 0))
    / (0.60 + CASE WHEN p_beds IS NULL THEN 0 ELSE 0.20 END + CASE WHEN p_doctors IS NULL THEN 0 ELSE 0.20 END)
    + CASE WHEN tertiary THEN 0.15 ELSE 0 END AS comprehensiveness
FROM p;
