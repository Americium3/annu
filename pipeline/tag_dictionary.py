"""Curated service / condition tags matched against facility evidence sentences.

Each tag is grounded in phrases that actually occur in the procedure, capability
and equipment sentence lists of ``workspace.cardinal_virtues.model_evidence_items``
(see ``pipeline/README.md`` for how the vocabulary was mined).

Fields:
  id        stable machine code (kebab-case)
  label     user-facing name
  kind      "condition" (a disease/problem a user might type) or
            "service" (a procedure, test or facility capability)
  group     body system / area, for grouping tags in the UI
  patterns  case-insensitive regexes; a facility gets the tag when any
            non-negated evidence sentence matches any pattern
  synonyms  extra user-facing terms for the search box (not used for matching)
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Tag:
    id: str
    label: str
    kind: str
    group: str
    patterns: tuple[str, ...]
    synonyms: tuple[str, ...] = field(default_factory=tuple)


def T(id, label, kind, group, patterns, synonyms=()):
    return Tag(id, label, kind, group, tuple(patterns), tuple(synonyms))


TAGS: list[Tag] = [
    # ── Kidney & urinary ────────────────────────────────────────────────
    T("kidney-dialysis", "Dialysis", "service", "Kidney & urinary",
      [r"\b(h(a)?emo)?dialy(sis|ses|ser)\b", r"\bcapd\b"],
      ["hemodialysis", "renal dialysis", "peritoneal dialysis"]),
    T("kidney-failure", "Kidney failure / chronic kidney disease", "condition", "Kidney & urinary",
      [r"\b(kidney|renal) (failure|disease|insufficiency)\b", r"\bckd\b", r"\besrd\b", r"\bend[- ]stage renal\b"],
      ["CKD", "renal failure"]),
    T("kidney-transplant", "Kidney transplant", "service", "Kidney & urinary",
      [r"\b(kidney|renal) transplant"], ["renal transplant"]),
    T("kidney-stones", "Kidney stones", "condition", "Kidney & urinary",
      [r"\b(kidney|renal|urinary|ureteric|bladder) stones?\b", r"\b(renal |urinary )?calculi\b", r"\burolithiasis\b",
       r"\bstones? (treatment|removal|clinic|surgery)", r"\blithotripsy\b", r"\beswl\b", r"\brirs\b", r"\bpcnl\b"],
      ["renal calculi", "lithotripsy"]),
    T("prostate", "Prostate problems", "condition", "Kidney & urinary",
      [r"\bprostat", r"\bturp\b", r"\bbph\b"], ["enlarged prostate", "BPH", "TURP"]),

    # ── Heart & blood vessels ──────────────────────────────────────────
    T("heart-disease", "Heart disease", "condition", "Heart & vessels",
      [r"\b(heart|cardiac|coronary) (disease|attack|failure|condition|problem)s?\b", r"\bmyocardial infarction\b",
       r"\bcoronary artery disease\b", r"\barrhythmia", r"\bangina\b"],
      ["heart attack", "cardiac disease", "CAD"]),
    T("angiography", "Coronary angiography", "service", "Heart & vessels",
      [r"\bangiogra(m|phy)", r"\bcath(eteri[sz]ation)? ?lab", r"\b(cardiac|heart|coronary) catheteri[sz]ation\b"], ["cath lab"]),
    T("angioplasty", "Angioplasty / stenting", "service", "Heart & vessels",
      [r"\bangioplast", r"\bptca\b", r"\bcoronary stent"], ["stent", "PTCA"]),
    T("cardiac-surgery", "Heart surgery (bypass / valve)", "service", "Heart & vessels",
      [r"\bcabg\b", r"\b(coronary artery )?bypass (graft|surgery)", r"\bvalve (replacement|repair|surgery)",
       r"\bopen[- ]heart\b", r"\bcardiac surger", r"\bcardiothoracic surger"],
      ["CABG", "bypass surgery", "valve replacement"]),
    T("pacemaker", "Pacemaker implantation", "service", "Heart & vessels", [r"\bpace ?makers?\b"]),
    T("echocardiography", "Echocardiography", "service", "Heart & vessels",
      [r"\bechocardiogra", r"\b2d[- ]echo\b", r"\becho\b"], ["2D echo"]),
    T("ecg", "ECG", "service", "Heart & vessels", [r"\becg\b", r"\bekg\b", r"\belectrocardiogra"]),
    T("stress-test", "Treadmill / stress test (TMT)", "service", "Heart & vessels",
      [r"\btreadmill\b", r"\btmt\b", r"\bstress test"]),
    T("hypertension", "High blood pressure", "condition", "Heart & vessels",
      [r"\bhypertension\b", r"\bhigh blood pressure\b"], ["hypertension", "BP"]),
    T("varicose-veins", "Varicose veins", "condition", "Heart & vessels", [r"\bvaricose\b"]),

    # ── Imaging & diagnostics ──────────────────────────────────────────
    T("mri", "MRI scan", "service", "Imaging & diagnostics",
      [r"\bmri\b", r"\bmagnetic resonance (imaging|scan|angiography)", r"\bmr (imaging|angiography|scan)"], ["magnetic resonance imaging"]),
    T("ct-scan", "CT scan", "service", "Imaging & diagnostics",
      [r"\bct\b(?![- ]?(vs|ts)\b)", r"\bcomputed tomography\b", r"\bcat scan\b"], ["computed tomography"]),
    T("x-ray", "X-ray", "service", "Imaging & diagnostics", [r"\bx[- ]?rays?\b", r"\bradiograph"]),
    T("ultrasound", "Ultrasound / sonography", "service", "Imaging & diagnostics",
      [r"\bultra ?sound\b", r"\bsonograph", r"\busg\b", r"\bdoppler\b"], ["sonography", "USG", "Doppler"]),
    T("mammography", "Mammography", "service", "Imaging & diagnostics", [r"\bmammogra"]),
    T("pet-ct", "PET-CT scan", "service", "Imaging & diagnostics", [r"\bpet ?[-/]? ?(ct|scan)", r"\bgamma camera\b", r"\bspect\b"]),
    T("bone-density", "Bone density (DEXA)", "service", "Imaging & diagnostics",
      [r"\bdexa\b", r"\bbone (mineral )?densit"], ["DEXA scan", "osteoporosis test"]),
    T("pathology-lab", "Pathology / blood tests", "service", "Imaging & diagnostics",
      [r"\bpatholog(y|ical) lab", r"\bblood tests?\b", r"\bdiagnostic lab", r"\b(clinical|medical|on-site|in-house) lab(oratory)?\b",
       r"\blipid profile\b", r"\bliver function test", r"\bsample collection\b",
       r"\blab(oratory)? (services|testing|tests|diagnostics?)\b", r"\b(pathology|diagnostic) (and|&) laborator"],
      ["lab tests", "blood test"]),
    T("health-checkup", "Health check-up", "service", "Imaging & diagnostics",
      [r"\bhealth check", r"\bhealth packages?\b", r"\bcheck[- ]?ups\b", r"\bfull body check", r"\bmaster health check", r"\bexecutive health check"]),

    # ── Cancer ─────────────────────────────────────────────────────────
    T("cancer", "Cancer", "condition", "Cancer",
      [r"\bcancers?\b", r"\boncolog", r"\btumou?rs?\b", r"\bmalignan", r"\bcarcinoma", r"\bleuk(a)?emia", r"\blymphoma"],
      ["oncology", "tumour", "malignancy"]),
    T("chemotherapy", "Chemotherapy", "service", "Cancer", [r"\bchemo(therapy)?\b"]),
    T("radiotherapy", "Radiation therapy", "service", "Cancer",
      [r"\bradiotherapy\b", r"\bradiation (therapy|oncology|treatment)", r"\blinac\b", r"\blinear accelerator",
       r"\bbrachytherapy\b", r"\btomotherapy\b", r"\bcyberknife\b", r"\bgamma knife\b"]),
    T("bone-marrow-transplant", "Bone marrow transplant", "service", "Cancer",
      [r"\bbone marrow transplant", r"\bbmt\b", r"\bstem cell transplant"]),

    # ── Pregnancy, fertility & women's health ──────────────────────────
    T("pregnancy-delivery", "Pregnancy & childbirth", "service", "Women's health & fertility",
      [r"\bnormal deliver", r"\bvaginal deliver", r"\bchild ?birth\b", r"\blabou?r room\b", r"\bmaternity\b",
       r"\bantenatal\b", r"\bprenatal\b", r"\bdeliver(y|ies)\b"],
      ["maternity", "antenatal care", "delivery"]),
    T("c-section", "Caesarean section", "service", "Women's health & fertility",
      [r"\bc(a)?esarean\b", r"\bc[- ]section\b", r"\blscs\b"], ["C-section", "LSCS"]),
    T("high-risk-pregnancy", "High-risk pregnancy", "condition", "Women's health & fertility",
      [r"\bhigh[- ]risk pregnanc", r"\bfetal medicine\b", r"\bfoetal medicine\b", r"\bmaternal[- ]fetal\b"]),
    T("infertility", "Infertility", "condition", "Women's health & fertility",
      [r"\binfertil", r"\bfertility\b"], ["fertility treatment"]),
    T("ivf", "IVF", "service", "Women's health & fertility",
      [r"\bivf\b", r"\bin[- ]?vitro fertili[sz]ation\b", r"\bicsi\b", r"\bembryo transfer\b"],
      ["in vitro fertilisation", "test tube baby", "ICSI"]),
    T("iui", "IUI", "service", "Women's health & fertility", [r"\biui\b", r"\bintra[- ]?uterine insemination\b"]),
    T("pcos", "PCOS / PCOD", "condition", "Women's health & fertility",
      [r"\bpco[sd]\b", r"\bpolycystic ovar"], ["polycystic ovary"]),
    T("hysterectomy", "Hysterectomy", "service", "Women's health & fertility", [r"\bhysterectom"]),
    T("pregnancy-termination", "Medical termination of pregnancy", "service", "Women's health & fertility",
      [r"\bmtp\b", r"\btermination of pregnanc", r"\babortion\b"], ["MTP", "abortion"]),
    T("family-planning", "Family planning / contraception", "service", "Women's health & fertility",
      [r"\bfamily planning\b", r"\bcontracept", r"\btubectom", r"\bvasectom", r"\bsterili[sz]ation\b"]),

    # ── Children & newborns ────────────────────────────────────────────
    T("nicu", "Newborn intensive care (NICU)", "service", "Children & newborns",
      [r"\bnicu\b", r"\bneonatal intensive\b", r"\bneonatal icu\b", r"\bsncu\b"], ["NICU", "SNCU"]),
    T("picu", "Pediatric intensive care (PICU)", "service", "Children & newborns",
      [r"\bpicu\b", r"\bp(a)?ediatric intensive\b", r"\bp(a)?ediatric icu\b"]),
    T("vaccination", "Vaccination", "service", "Children & newborns",
      [r"\bvaccin", r"\bimmuni[sz]ation\b"], ["immunisation"]),
    T("child-development", "Autism & child development", "condition", "Children & newborns",
      [r"\bautis", r"\badhd\b", r"\bdevelopmental delay", r"\bcerebral palsy\b", r"\bchild development\b"]),

    # ── Eyes ───────────────────────────────────────────────────────────
    T("cataract", "Cataract", "condition", "Eyes", [r"\bcataract", r"\bphaco", r"\bintraocular lens\b", r"\biol\b"]),
    T("glaucoma", "Glaucoma", "condition", "Eyes", [r"\bglaucoma"]),
    T("retina", "Retina problems / diabetic retinopathy", "condition", "Eyes",
      [r"\bretina", r"\bvitreo", r"\bretinopathy\b", r"\bmacular\b"], ["diabetic retinopathy", "vitreoretinal"]),
    T("refractive-surgery", "LASIK / vision correction", "service", "Eyes",
      [r"\blasik\b", r"\brefractive (surgery|correction|procedure)", r"\bsmile (eye|laser|surgery|procedure)\b", r"\bprk\b"],
      ["LASIK", "laser eye surgery"]),
    T("squint", "Squint / strabismus", "condition", "Eyes", [r"\bsquint", r"\bstrabismus\b"]),
    T("cornea", "Cornea problems / transplant", "condition", "Eyes",
      [r"\bcornea", r"\bkeratoplast", r"\bkeratoconus\b"]),

    # ── Bones, joints & spine ──────────────────────────────────────────
    T("joint-replacement", "Knee / hip replacement", "service", "Bones, joints & spine",
      [r"\b(knee|hip|joint|shoulder) replacement", r"\barthroplast"], ["knee replacement", "hip replacement"]),
    T("arthroscopy", "Arthroscopy", "service", "Bones, joints & spine", [r"\barthroscop", r"\bacl reconstruction\b"]),
    T("spine-surgery", "Spine surgery", "service", "Bones, joints & spine",
      [r"\bspin(e|al) surger", r"\bdiscectom", r"\blaminectom", r"\bspinal fusion\b", r"\bslip(ped)? disc\b"]),
    T("fracture-trauma", "Fractures & trauma", "condition", "Bones, joints & spine",
      [r"\bfractures?\b", r"\btrauma (care|centre|center|surgery|unit)", r"\bpolytrauma\b"], ["broken bone"]),
    T("arthritis", "Arthritis", "condition", "Bones, joints & spine",
      [r"\barthritis\b", r"\bosteoarthrit", r"\bgout\b"], ["rheumatoid arthritis", "osteoarthritis"]),
    T("back-pain", "Back & neck pain", "condition", "Bones, joints & spine",
      [r"\b(back|neck|spine|spinal|low back) pain\b", r"\bsciatica\b", r"\bspondyl"]),
    T("physiotherapy", "Physiotherapy & rehabilitation", "service", "Bones, joints & spine",
      [r"\bphysiotherap", r"\bphysical therap", r"\brehabilitation\b"]),

    # ── Brain & nerves ─────────────────────────────────────────────────
    T("stroke", "Stroke", "condition", "Brain & nerves",
      [r"\bstrokes?\b(?! ?(volume|count))", r"\bthromboly", r"\bparalysis\b"]),
    T("epilepsy", "Epilepsy / seizures", "condition", "Brain & nerves", [r"\bepilep", r"\bseizure"]),
    T("neurosurgery", "Brain surgery", "service", "Brain & nerves",
      [r"\bbrain (surgery|tumou?r)", r"\bneurosurg", r"\bcraniotom"]),
    T("eeg-emg", "EEG / EMG / nerve conduction", "service", "Brain & nerves",
      [r"\beeg\b", r"\bemg\b", r"\bncv\b", r"\bnerve conduction\b", r"\belectroencephalogra"]),
    T("headache-migraine", "Headache & migraine", "condition", "Brain & nerves", [r"\bmigraine", r"\bheadache"]),
    T("parkinsons-dementia", "Parkinson's & dementia", "condition", "Brain & nerves",
      [r"\bparkinson", r"\bdementia\b", r"\balzheimer", r"\bmovement disorder"]),

    # ── Digestive system & liver ───────────────────────────────────────
    T("endoscopy", "Endoscopy / colonoscopy", "service", "Digestive & liver",
      [r"\b(gi |gastrointestinal |upper |lower |diagnostic |therapeutic )?endoscopy\b", r"\bgastroscop", r"\bcolonoscop", r"\bsigmoidoscop", r"\bercp\b"],
      ["colonoscopy", "gastroscopy", "ERCP"]),
    T("gallstones", "Gallstones", "condition", "Digestive & liver",
      [r"\bgall ?(bladder|stones?)\b", r"\bcholecystectom"], ["gall bladder removal", "cholecystectomy"]),
    T("hernia", "Hernia", "condition", "Digestive & liver", [r"\bhernia"]),
    T("piles-fistula", "Piles, fissure & fistula", "condition", "Digestive & liver",
      [r"\bpiles\b", r"\bh(a)?emorrhoid", r"\bfistula", r"\bfissure", r"\bpilonidal\b", r"\bproctolog"],
      ["haemorrhoids", "anal fistula"]),
    T("appendicitis", "Appendicitis", "condition", "Digestive & liver", [r"\bappendic", r"\bappendectom"]),
    T("liver-disease", "Liver disease", "condition", "Digestive & liver",
      [r"\bliver (disease|cirrhosis|failure)", r"\bcirrhosis\b", r"\bhepatitis\b", r"\bfatty liver\b", r"\bhepatolog"],
      ["hepatitis", "cirrhosis"]),
    T("liver-transplant", "Liver transplant", "service", "Digestive & liver", [r"\bliver transplant"]),
    T("bariatric-surgery", "Weight-loss (bariatric) surgery", "service", "Digestive & liver",
      [r"\bbariatric\b", r"\bobesity surger", r"\bweight[- ]loss surger", r"\bsleeve gastrectom", r"\bgastric bypass\b"]),

    # ── Ear, nose & throat ─────────────────────────────────────────────
    T("ent", "Ear, nose & throat (ENT)", "service", "Ear, nose & throat",
      [r"\bent\b", r"\bear,? nose", r"\botolaryngolog", r"\botorhinolaryngolog"], ["ENT"]),
    T("sinus", "Sinus problems", "condition", "Ear, nose & throat",
      [r"\bsinus(itis)?\b(?! (rhythm|lift))", r"\bfess\b", r"\bnasal polyp"], ["sinusitis", "FESS"]),
    T("hearing", "Hearing loss / hearing aids", "condition", "Ear, nose & throat",
      [r"\bhearing (loss|aid|test|impair)", r"\baudiometr", r"\bcochlear implant", r"\baudiolog"]),
    T("tonsils", "Tonsils & adenoids", "condition", "Ear, nose & throat", [r"\btonsil", r"\badenoid"]),

    # ── Lungs & breathing ──────────────────────────────────────────────
    T("asthma-copd", "Asthma / COPD", "condition", "Lungs & breathing",
      [r"\basthma", r"\bcopd\b", r"\bbronchit", r"\bchronic obstructive pulmonary"]),
    T("tuberculosis", "Tuberculosis (TB)", "condition", "Lungs & breathing", [r"\btuberculosis\b", r"\btb\b", r"\bdots\b"]),
    T("pulmonary-function", "Lung function test (PFT)", "service", "Lungs & breathing",
      [r"\bpulmonary function", r"\bpft\b", r"\bspirometr", r"\bbronchoscop"]),
    T("sleep-apnea", "Sleep apnea / sleep study", "condition", "Lungs & breathing",
      [r"\bsleep apn(o)?ea\b", r"\bsleep stud", r"\bpolysomnograph", r"\bsnoring\b"]),

    # ── Hormones & metabolism ──────────────────────────────────────────
    T("diabetes", "Diabetes", "condition", "Hormones & metabolism", [r"\bdiabet(es|ic|ology)\b"], ["sugar", "diabetic care"]),
    T("thyroid", "Thyroid disorders", "condition", "Hormones & metabolism", [r"\bthyroid", r"\bgoitre\b", r"\bgoiter\b"]),
    T("obesity", "Obesity & weight management", "condition", "Hormones & metabolism",
      [r"\bobesity\b", r"\bweight (loss|management)\b"]),

    # ── Infections & fevers ────────────────────────────────────────────
    T("fever-infections", "Fever, dengue, malaria & typhoid", "condition", "Infections",
      [r"\b(viral )?fever\b", r"\bdengue\b", r"\bmalaria\b", r"\btyphoid\b", r"\bchikungunya\b"]),
    T("hiv", "HIV / AIDS", "condition", "Infections", [r"\bhiv\b", r"\bplhiv\b", r"\bart cent(re|er)\b", r"\bantiretroviral\b"]),
    T("snakebite-rabies", "Snakebite & rabies", "condition", "Infections",
      [r"\bsnake ?bite", r"\banti[- ]?(snake )?venom", r"\brabies\b", r"\bdog bite"]),

    # ── Skin, hair & cosmetic ──────────────────────────────────────────
    T("skin-disease", "Skin conditions", "condition", "Skin, hair & cosmetic",
      [r"\b(eczema|psoriasis|vitiligo|acne|dermatitis|fungal infection|skin (disease|disorder|infection|condition)s?)\b"],
      ["psoriasis", "eczema", "acne"]),
    T("hair-loss", "Hair loss / hair transplant", "condition", "Skin, hair & cosmetic",
      [r"\bhair (loss|fall|transplant|restoration)", r"\balopecia\b"]),
    T("cosmetic-surgery", "Cosmetic / plastic surgery", "service", "Skin, hair & cosmetic",
      [r"\bcosmetic surger", r"\bplastic surger", r"\bliposuction\b", r"\brhinoplast", r"\bbreast (augmentation|reduction|implant)",
       r"\btummy tuck\b", r"\babdominoplast", r"\bblepharoplast"]),
    T("burns", "Burns", "condition", "Skin, hair & cosmetic", [r"\bburns?\b(?! (out|fat|calories))", r"\bburn (unit|ward|care|centre)"]),

    # ── Dental ─────────────────────────────────────────────────────────
    T("root-canal", "Root canal treatment", "service", "Dental", [r"\broot canal", r"\brct\b", r"\bendodont"]),
    T("dental-implants", "Dental implants", "service", "Dental", [r"\bdental implant", r"\bimplantolog", r"\btooth implant"]),
    T("orthodontics", "Braces & aligners", "service", "Dental",
      [r"\bbraces\b", r"\baligners?\b", r"\borthodont", r"\binvisalign\b"]),
    T("dentures", "Dentures", "service", "Dental", [r"\bdentures?\b"]),
    T("tooth-extraction", "Tooth extraction", "service", "Dental",
      [r"\b(tooth|teeth|wisdom tooth|wisdom teeth) (extraction|removal)", r"\bextraction of (tooth|teeth)"]),
    T("gum-disease", "Gum disease", "condition", "Dental",
      [r"\bgum (disease|treatment|surgery|infection)", r"\bperiodont", r"\bgingiv"]),

    # ── Mental health ──────────────────────────────────────────────────
    T("mental-health", "Mental health (depression, anxiety)", "condition", "Mental health",
      [r"\bdepression\b", r"\banxiety\b", r"\bmental (health|illness|disorder)", r"\bpsychiatr", r"\bschizophren",
       r"\bbipolar\b", r"\bpsycholog"]),
    T("addiction", "De-addiction", "condition", "Mental health",
      [r"\bde-?addiction\b", r"\baddiction\b", r"\balcohol(ism)? (dependence|rehab|de-?addiction)", r"\bsubstance (abuse|use)"]),

    # ── Emergency & critical care ──────────────────────────────────────
    T("emergency-24x7", "24/7 emergency", "service", "Emergency & critical care",
      [r"\bemergency\b", r"\bcasualty\b", r"\baccident (and|&) emergency\b"]),
    T("icu", "Intensive care (ICU)", "service", "Emergency & critical care",
      [r"\bicu\b", r"\bintensive care\b", r"\biccu\b", r"\bccu\b", r"\bcritical care\b", r"\bventilators?\b"]),
    T("ambulance", "Ambulance", "service", "Emergency & critical care", [r"\bambulances?\b"]),
    T("blood-bank", "Blood bank", "service", "Emergency & critical care",
      [r"\bblood (bank|storage|centre|center)", r"\bblood transfusion"]),
    T("palliative-care", "Palliative care", "service", "Emergency & critical care",
      [r"\bpalliative\b", r"\bhospice\b", r"\bend[- ]of[- ]life care\b"]),
]


# A match is discarded when one of these appears shortly before it in the same sentence:
# negations ("No dialysis facility", "does not offer MRI") and services that are only
# planned ("Future liver transplantation program", "Plans to start palliative care").
NEGATION_PATTERN = (
    r"\b(no|not|without|lacks?|lacking|unavailable|absence of|absent|neither|nor|never"
    r"|future|plans?(ned)? to|planned|proposed|upcoming|will (be|start|soon))\b|n't\b"
    r"|\bnon[- ]?$"  # "non-ICU beds": only when "non-" directly precedes the match
)
NEGATION_WINDOW_CHARS = 40
