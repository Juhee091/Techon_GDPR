import pandas as pd
from presidio_analyzer import AnalyzerEngine
from presidio_analyzer.nlp_engine import NlpEngineProvider
from sklearn.metrics import classification_report
import warnings
warnings.filterwarnings("ignore")


# ── 1. Load sample data ───────────────────────────────────────────────────────

df = pd.read_excel(
    r"classification\sample_data.xlsx",
    parse_dates=["file_created_date", "last_modified_date"]
)

# ── 2. Build Presidio engine with English + German support ───────────────────

nlp_config = {
    "nlp_engine_name": "spacy",
    "models": [
        {"lang_code": "en", "model_name": "en_core_web_lg"},
        {"lang_code": "de", "model_name": "de_core_news_sm"},
    ],
}

provider = NlpEngineProvider(nlp_configuration=nlp_config)
nlp_engine = provider.create_engine()

engine = AnalyzerEngine(
    nlp_engine=nlp_engine,
    supported_languages=["en", "de"],
)


# ── 3. Retention flag logic ───────────────────────────────────────────────────

RETENTION_YEARS = 3
TODAY = pd.Timestamp.today().normalize()

def is_retention_exceeded(creation_date) -> bool:
    if pd.isnull(creation_date):
        return False
    return (TODAY - creation_date).days > RETENTION_YEARS * 365


# ── 4. Risk scoring ───────────────────────────────────────────────────────────

HIGH_RISK_TYPES = {
    "PASSPORT",
    "NRP",
    "CREDIT_CARD",
    "IBAN_CODE",
    "MEDICAL_LICENSE",
    "US_SSN",
}

def compute_risk(categories: list[str]) -> str:
    if not categories:
        return "None"
    if any(c in HIGH_RISK_TYPES for c in categories):
        return "High"
    if len(categories) >= 3:
        return "High"
    if len(categories) >= 1:
        return "Medium"
    return "Low"


# ── 5. Core scan function ─────────────────────────────────────────────────────

# Maps Presidio entity types to the ground truth column names in the CSV
ENTITY_TO_COLUMN = {
    "PERSON":           "PERSON_yes_no",
    "EMAIL_ADDRESS":    "EMAIL_ADDRESS_yes_no",
    "PHONE_NUMBER":     "PHONE_NUMBER_yes_no",
    "LOCATION":         "LOCATION_yes_no",
    "IBAN_CODE":        "IBAN_CODE_yes_no",
    "CREDIT_CARD":      "CREDIT_CARD_yes_no",
    "PASSPORT":         "PASSPORT_yes_no",
    "NRP":              "NRP_yes_no",
    "DATE_TIME":        "DATE_TIME_yes_no",
    "IP_ADDRESS":       "IP_ADDRESS_yes_no",
    "URL":              "URL_yes_no",
    "MEDICAL_LICENSE":  "MEDICAL_LICENSE_yes_no",
}

def scan_text(text: str, language: str = "en") -> dict:
    if not isinstance(text, str) or text.strip() == "":
        return {
            "detected_pii":              False,
            "detected_categories":       [],
            "detected_PERSON":           False,
            "detected_EMAIL_ADDRESS":    False,
            "detected_PHONE_NUMBER":     False,
            "detected_LOCATION":         False,
            "detected_IBAN_CODE":        False,
            "detected_CREDIT_CARD":      False,
            "detected_PASSPORT":         False,
            "detected_NRP":              False,
            "detected_DATE_TIME":        False,
            "detected_IP_ADDRESS":       False,
            "detected_URL":              False,
            "detected_MEDICAL_LICENSE":  False,
            "detected_category_count":   0,
            "risk_level":                "None",
            "entities":                  [],
        }

    results = engine.analyze(
        text=text,
        language=language,
        score_threshold=0.5,
    )

    categories = list(set(r.entity_type for r in results))

    entities = [
        {
            "type":  r.entity_type,
            "value": text[r.start:r.end],
            "score": round(r.score, 3),
        }
        for r in results
    ]

    return {
        "detected_pii":             len(results) > 0,
        "detected_categories":      categories,
        "detected_PERSON":          "PERSON" in categories,
        "detected_EMAIL_ADDRESS":   "EMAIL_ADDRESS" in categories,
        "detected_PHONE_NUMBER":    "PHONE_NUMBER" in categories,
        "detected_LOCATION":        "LOCATION" in categories,
        "detected_IBAN_CODE":       "IBAN_CODE" in categories,
        "detected_CREDIT_CARD":     "CREDIT_CARD" in categories,
        "detected_PASSPORT":        "PASSPORT" in categories,
        "detected_NRP":             "NRP" in categories,
        "detected_DATE_TIME":       "DATE_TIME" in categories,
        "detected_IP_ADDRESS":      "IP_ADDRESS" in categories,
        "detected_URL":             "URL" in categories,
        "detected_MEDICAL_LICENSE": "MEDICAL_LICENSE" in categories,
        "detected_category_count":  len(categories),
        "risk_level":               compute_risk(categories),
        "entities":                 entities,
    }


# ── 6. Run the scan over the full DataFrame ───────────────────────────────────

has_language_col = "language" in df.columns

scan_results = df.apply(
    lambda row: pd.Series(
        scan_text(
            text=row["full_text"],
            language=row["language"] if has_language_col else "en",
        )
    ),
    axis=1,
)

df = pd.concat([df, scan_results], axis=1)

# Retention flag — use file_created_date as the relevant date per spec
df["detected_retention_exceeded"] = df["file_created_date"].apply(is_retention_exceeded)


# ── 7. Evaluation — ground truth vs detections ───────────────────────────────

# Top-level PII flag
EVAL_PAIRS = [
    ("contains_personal_data", "detected_pii"),
    ("PERSON_YES",             "detected_PERSON"),
    ("EMAIL_ADDRESS_YES",      "detected_EMAIL_ADDRESS"),
    ("PHONE_NUMBER_YES",       "detected_PHONE_NUMBER"),
    ("LOCATION_YES",           "detected_LOCATION"),
    ("IBAN_CODE_YES",          "detected_IBAN_CODE"),
    ("CREDIT_CARD_YES",        "detected_CREDIT_CARD"),
    ("PASSPORT_YES",           "detected_PASSPORT"),
    ("NRP_YES",                "detected_NRP"),
    ("DATE_TIME_YES",          "detected_DATE_TIME"),
    ("IP_ADDRESS_YES",         "detected_IP_ADDRESS"),
    ("URL_YES",                "detected_URL"),
    ("MEDICAL_LICENSE_YES",    "detected_MEDICAL_LICENSE"),
    ("retention_period_exceeded", "detected_retention_exceeded"),
]

print("=" * 60)
print("EVALUATION REPORT")
print("=" * 60)

for truth_col, pred_col in EVAL_PAIRS:
    if truth_col not in df.columns or pred_col not in df.columns:
        continue

    # Normalise ground truth — CSV booleans may come in as strings
    truth = df[truth_col].map(
        lambda v: str(v).strip().lower() in {"true", "yes", "1"}
    )
    pred = df[pred_col].astype(bool)

    print(f"\n── {truth_col} ──")
    print(
        classification_report(
            truth, pred,
            target_names=["No", "Yes"],
            zero_division=0,
        )
    )


# ── 8. Results preview ────────────────────────────────────────────────────────

preview_cols = [
    "file_name", "document_type", "source_system", "responsible_owner",
    "file_created_date", "detected_pii", "detected_categories",
    "detected_category_count", "risk_level", "detected_retention_exceeded",
]

print("=" * 60)
print("SCAN RESULTS PREVIEW")
print("=" * 60)
print(df[[c for c in preview_cols if c in df.columns]].to_string(index=False))


# ── 9. Export ─────────────────────────────────────────────────────────────────

output_cols = [c for c in df.columns if c != "entities"]
df[output_cols].to_csv("scan_results.csv", index=False)

# Flat entity breakdown — one row per detected entity
entities_rows = []
for _, row in df.iterrows():
    for ent in row.get("entities", []):
        entities_rows.append({
            "file_name":         row.get("file_name", ""),
            "document_type":     row.get("document_type", ""),
            "responsible_owner": row.get("responsible_owner", ""),
            **ent,
        })

pd.DataFrame(entities_rows).to_csv("entity_details.csv", index=False)

print("\nOutputs written to scan_results.csv and entity_details.csv")
