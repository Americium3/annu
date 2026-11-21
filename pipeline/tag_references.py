"""Curated cross-references from service/condition tags to standard vocabularies.

  mesh   NLM Medical Subject Headings, given by exact descriptor preferred label.
         ``crosswalk_taxonomies.py`` resolves each label to its descriptor ID and tree
         numbers through the NLM MeSH API and fails loudly on any label it cannot find.
  icd10  WHO ICD-10 (2019) codes: categories ("N18"), subcategories ("Z94.0"), blocks
         ("A15-A19") or chapters ("XII"). Conditions get diagnosis codes; some services
         get the matching "care involving ..." Z code. Validated against the WHO 2019
         code set (``simple-icd-10`` package).
"""

REFERENCES: dict[str, dict[str, list[str]]] = {
    # Kidney & urinary
    "kidney-dialysis": {"mesh": ["Renal Dialysis"], "icd10": ["Z49"]},
    "kidney-failure": {"mesh": ["Renal Insufficiency, Chronic", "Kidney Failure, Chronic"], "icd10": ["N18", "N19"]},
    "kidney-transplant": {"mesh": ["Kidney Transplantation"], "icd10": ["Z94.0"]},
    "kidney-stones": {"mesh": ["Kidney Calculi", "Urolithiasis", "Lithotripsy"], "icd10": ["N20"]},
    "prostate": {"mesh": ["Prostatic Hyperplasia", "Prostatic Diseases"], "icd10": ["N40", "N42"]},
    # Heart & vessels
    "heart-disease": {"mesh": ["Heart Diseases", "Coronary Artery Disease"], "icd10": ["I20", "I21", "I25", "I50"]},
    "angiography": {"mesh": ["Coronary Angiography", "Cardiac Catheterization"], "icd10": []},
    "angioplasty": {"mesh": ["Percutaneous Coronary Intervention", "Angioplasty", "Stents"], "icd10": []},
    "cardiac-surgery": {"mesh": ["Cardiac Surgical Procedures", "Coronary Artery Bypass", "Heart Valve Prosthesis Implantation"], "icd10": []},
    "pacemaker": {"mesh": ["Pacemaker, Artificial", "Cardiac Pacing, Artificial"], "icd10": ["Z95.0"]},
    "echocardiography": {"mesh": ["Echocardiography"], "icd10": []},
    "ecg": {"mesh": ["Electrocardiography"], "icd10": []},
    "stress-test": {"mesh": ["Exercise Test"], "icd10": []},
    "hypertension": {"mesh": ["Hypertension"], "icd10": ["I10"]},
    "varicose-veins": {"mesh": ["Varicose Veins"], "icd10": ["I83"]},
    # Imaging & diagnostics
    "mri": {"mesh": ["Magnetic Resonance Imaging"], "icd10": []},
    "ct-scan": {"mesh": ["Tomography, X-Ray Computed"], "icd10": []},
    "x-ray": {"mesh": ["Radiography"], "icd10": []},
    "ultrasound": {"mesh": ["Ultrasonography", "Ultrasonography, Doppler"], "icd10": []},
    "mammography": {"mesh": ["Mammography"], "icd10": []},
    "pet-ct": {"mesh": ["Positron Emission Tomography Computed Tomography"], "icd10": []},
    "bone-density": {"mesh": ["Absorptiometry, Photon", "Bone Density"], "icd10": []},
    "pathology-lab": {"mesh": ["Clinical Laboratory Services", "Clinical Laboratory Techniques"], "icd10": []},
    "health-checkup": {"mesh": ["Physical Examination", "Mass Screening"], "icd10": ["Z00.0"]},
    # Cancer
    "cancer": {"mesh": ["Neoplasms"], "icd10": ["II"]},
    "chemotherapy": {"mesh": ["Antineoplastic Agents", "Chemotherapy, Adjuvant"], "icd10": ["Z51.1"]},
    "radiotherapy": {"mesh": ["Radiotherapy"], "icd10": ["Z51.0"]},
    "bone-marrow-transplant": {"mesh": ["Bone Marrow Transplantation", "Hematopoietic Stem Cell Transplantation"], "icd10": []},
    # Women's health & fertility
    "pregnancy-delivery": {"mesh": ["Delivery, Obstetric", "Prenatal Care"], "icd10": ["O80", "Z34"]},
    "c-section": {"mesh": ["Cesarean Section"], "icd10": ["O82"]},
    "high-risk-pregnancy": {"mesh": ["Pregnancy, High-Risk"], "icd10": ["Z35"]},
    "infertility": {"mesh": ["Infertility", "Infertility, Female", "Infertility, Male"], "icd10": ["N97", "N46"]},
    "ivf": {"mesh": ["Fertilization in Vitro", "Sperm Injections, Intracytoplasmic", "Embryo Transfer"], "icd10": []},
    "iui": {"mesh": ["Insemination, Artificial"], "icd10": []},
    "pcos": {"mesh": ["Polycystic Ovary Syndrome"], "icd10": ["E28.2"]},
    "hysterectomy": {"mesh": ["Hysterectomy"], "icd10": []},
    "pregnancy-termination": {"mesh": ["Abortion, Induced"], "icd10": ["O04"]},
    "family-planning": {"mesh": ["Family Planning Services", "Contraception", "Sterilization, Reproductive"], "icd10": ["Z30"]},
    # Children & newborns
    "nicu": {"mesh": ["Intensive Care Units, Neonatal"], "icd10": []},
    "picu": {"mesh": ["Intensive Care Units, Pediatric"], "icd10": []},
    "vaccination": {"mesh": ["Vaccination", "Immunization"], "icd10": ["Z23", "Z27"]},
    "child-development": {"mesh": ["Autism Spectrum Disorder", "Developmental Disabilities", "Cerebral Palsy",
                                   "Attention Deficit Disorder with Hyperactivity"], "icd10": ["F84", "F90", "G80"]},
    # Eyes
    "cataract": {"mesh": ["Cataract", "Cataract Extraction", "Phacoemulsification"], "icd10": ["H25", "H26"]},
    "glaucoma": {"mesh": ["Glaucoma"], "icd10": ["H40"]},
    "retina": {"mesh": ["Retinal Diseases", "Diabetic Retinopathy", "Vitreoretinal Surgery"], "icd10": ["H33", "H35", "H36"]},
    "refractive-surgery": {"mesh": ["Refractive Surgical Procedures", "Keratomileusis, Laser In Situ"], "icd10": ["H52"]},
    "squint": {"mesh": ["Strabismus"], "icd10": ["H49", "H50"]},
    "cornea": {"mesh": ["Corneal Diseases", "Keratoplasty, Penetrating", "Keratoconus"], "icd10": ["H16", "H17", "H18"]},
    # Bones, joints & spine
    "joint-replacement": {"mesh": ["Arthroplasty, Replacement, Knee", "Arthroplasty, Replacement, Hip"], "icd10": ["Z96.6"]},
    "arthroscopy": {"mesh": ["Arthroscopy"], "icd10": []},
    "spine-surgery": {"mesh": ["Spinal Fusion", "Diskectomy", "Laminectomy"], "icd10": ["M51"]},
    "fracture-trauma": {"mesh": ["Fractures, Bone", "Wounds and Injuries", "Trauma Centers"], "icd10": ["XIX"]},
    "arthritis": {"mesh": ["Arthritis", "Osteoarthritis", "Arthritis, Rheumatoid", "Gout"], "icd10": ["M05", "M06", "M10", "M15-M19"]},
    "back-pain": {"mesh": ["Back Pain", "Neck Pain", "Sciatica", "Spondylosis"], "icd10": ["M54", "M47"]},
    "physiotherapy": {"mesh": ["Physical Therapy Modalities", "Rehabilitation"], "icd10": []},
    # Brain & nerves
    "stroke": {"mesh": ["Stroke", "Thrombolytic Therapy", "Paralysis"], "icd10": ["I63", "I64", "G81"]},
    "epilepsy": {"mesh": ["Epilepsy", "Seizures"], "icd10": ["G40", "G41"]},
    "neurosurgery": {"mesh": ["Neurosurgical Procedures", "Craniotomy", "Brain Neoplasms"], "icd10": []},
    "eeg-emg": {"mesh": ["Electroencephalography", "Electromyography", "Neural Conduction"], "icd10": []},
    "headache-migraine": {"mesh": ["Migraine Disorders", "Headache"], "icd10": ["G43", "G44"]},
    "parkinsons-dementia": {"mesh": ["Parkinson Disease", "Dementia", "Alzheimer Disease", "Movement Disorders"], "icd10": ["G20", "G30", "F03"]},
    # Digestive & liver
    "endoscopy": {"mesh": ["Endoscopy, Gastrointestinal", "Colonoscopy", "Cholangiopancreatography, Endoscopic Retrograde"], "icd10": []},
    "gallstones": {"mesh": ["Gallstones", "Cholecystectomy"], "icd10": ["K80"]},
    "hernia": {"mesh": ["Hernia", "Herniorrhaphy"], "icd10": ["K40-K46"]},
    "piles-fistula": {"mesh": ["Hemorrhoids", "Rectal Fistula", "Fissure in Ano", "Pilonidal Sinus"], "icd10": ["K64", "K60", "L05"]},
    "appendicitis": {"mesh": ["Appendicitis", "Appendectomy"], "icd10": ["K35", "K36", "K37"]},
    "liver-disease": {"mesh": ["Liver Diseases", "Liver Cirrhosis", "Hepatitis", "Fatty Liver"], "icd10": ["K70-K77", "B15-B19"]},
    "liver-transplant": {"mesh": ["Liver Transplantation"], "icd10": ["Z94.4"]},
    "bariatric-surgery": {"mesh": ["Bariatric Surgery"], "icd10": []},
    # Ear, nose & throat
    "ent": {"mesh": ["Otorhinolaryngologic Diseases", "Otolaryngology"], "icd10": ["VIII"]},
    "sinus": {"mesh": ["Sinusitis", "Nasal Polyps"], "icd10": ["J01", "J32", "J33"]},
    "hearing": {"mesh": ["Hearing Loss", "Hearing Aids", "Cochlear Implants", "Audiometry"], "icd10": ["H90", "H91"]},
    "tonsils": {"mesh": ["Tonsillitis", "Tonsillectomy", "Adenoids"], "icd10": ["J03", "J35"]},
    # Lungs & breathing
    "asthma-copd": {"mesh": ["Asthma", "Pulmonary Disease, Chronic Obstructive", "Bronchitis"], "icd10": ["J44", "J45", "J40"]},
    "tuberculosis": {"mesh": ["Tuberculosis"], "icd10": ["A15-A19"]},
    "pulmonary-function": {"mesh": ["Respiratory Function Tests", "Spirometry", "Bronchoscopy"], "icd10": []},
    "sleep-apnea": {"mesh": ["Sleep Apnea Syndromes", "Polysomnography", "Snoring"], "icd10": ["G47.3"]},
    # Hormones & metabolism
    "diabetes": {"mesh": ["Diabetes Mellitus"], "icd10": ["E10-E14"]},
    "thyroid": {"mesh": ["Thyroid Diseases", "Goiter"], "icd10": ["E00-E07"]},
    "obesity": {"mesh": ["Obesity", "Weight Reduction Programs"], "icd10": ["E66"]},
    # Infections
    "fever-infections": {"mesh": ["Fever", "Dengue", "Malaria", "Typhoid Fever", "Chikungunya Fever"],
                         "icd10": ["R50", "A97", "B50", "B51", "B52", "B53", "B54", "A01.0", "A92.0"]},
    "hiv": {"mesh": ["HIV Infections", "Acquired Immunodeficiency Syndrome"], "icd10": ["B20-B24"]},
    "snakebite-rabies": {"mesh": ["Snake Bites", "Rabies", "Antivenins", "Rabies Vaccines"], "icd10": ["T63.0", "A82"]},
    # Skin, hair & cosmetic
    "skin-disease": {"mesh": ["Skin Diseases", "Psoriasis", "Eczema", "Acne Vulgaris", "Vitiligo"], "icd10": ["XII"]},
    "hair-loss": {"mesh": ["Alopecia"], "icd10": ["L63", "L64", "L65"]},
    "cosmetic-surgery": {"mesh": ["Surgery, Plastic", "Cosmetic Techniques", "Lipectomy", "Rhinoplasty"], "icd10": []},
    "burns": {"mesh": ["Burns", "Burn Units"], "icd10": ["T20-T32"]},
    # Dental
    "root-canal": {"mesh": ["Root Canal Therapy", "Endodontics"], "icd10": ["K04"]},
    "dental-implants": {"mesh": ["Dental Implants", "Dental Implantation"], "icd10": []},
    "orthodontics": {"mesh": ["Orthodontics", "Orthodontic Appliances"], "icd10": ["K07"]},
    "dentures": {"mesh": ["Dentures"], "icd10": []},
    "tooth-extraction": {"mesh": ["Tooth Extraction"], "icd10": []},
    "gum-disease": {"mesh": ["Periodontal Diseases", "Gingivitis"], "icd10": ["K05"]},
    # Mental health
    "mental-health": {"mesh": ["Mental Disorders", "Depression", "Anxiety Disorders", "Psychiatry"], "icd10": ["V"]},
    "addiction": {"mesh": ["Substance-Related Disorders", "Alcoholism"], "icd10": ["F10-F19"]},
    # Emergency & critical care
    "emergency-24x7": {"mesh": ["Emergency Service, Hospital", "Emergency Medical Services"], "icd10": []},
    "icu": {"mesh": ["Intensive Care Units", "Critical Care", "Ventilators, Mechanical"], "icd10": []},
    "ambulance": {"mesh": ["Ambulances"], "icd10": []},
    "blood-bank": {"mesh": ["Blood Banks", "Blood Transfusion"], "icd10": []},
    "palliative-care": {"mesh": ["Palliative Care", "Hospice Care"], "icd10": ["Z51.5"]},
}
