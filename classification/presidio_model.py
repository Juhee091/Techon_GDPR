import pandas as pd
from datetime import date
from presidio_analyzer import AnalyzerEngine
from presidio_analyzer.nlp_engine import NlpEngineProvider
from sklearn.metrics import classification_report
import warnings
warnings.filterwarnings("ignore")


# ── 1. Load sample data ───────────────────────────────────────────────────────

df = pd.read_csv("sample_data.csv", parse_dates=["creation_date"])


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

def is_retention_exceeded(creation_date):
    """Returns True if the file is older than the retention period."""
    if pd.isnull(creation_date):
        return False
    return (TODAY - creation_date).days > RETENTION_YEARS * 365


# ── 4. Risk scoring ───────────────────────────────────────────────────────────

# Higher-sensitivity entity types drive the risk level up
HIGH_RISK_TYPES = {
    "PASSPORT",
    "NRP",           # national ID / driver's license
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

CATEGORY_TO_COLUMN = {
    "PERSON":         "has_name",
    "EMAIL_ADDRESS":  "has_email",
    "PHONE_NUMBER":   "has_phone",
    "LOCATION":       "has_address",
    "PASSPORT":       "has_id_number",
    "NRP":            "has_id_number",
    "MEDICAL_LICENSE":"has_health",
}

def scan_text(text: str, language: str = "en") -> dict:
    """
    Run Presidio on a single piece of text.
    Returns detected PII metadata.
    """
    if not isinstance(text, str) or text.strip() == "":
        return {
            "detected_pii":        False,
            "detected_categories": [],
            "detected_has_name":   False,
            "detected_has_email":  False,
            "detected_has_phone":  False,
            "detected_has_address":False,
            "detected_has_id_number": False,
            "detected_has_health": False,
            "risk_level":          "None",
            "entities":            [],
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
        "detected_pii":            len(results) > 0,
        "detected_categories":     categories,
        "detected_has_name":       "PERSON" in categories,
        "detected_has_email":      "EMAIL_ADDRESS" in categories,
        "detected_has_phone":      "PHONE_NUMBER" in categories,
        "detected_has_address":    "LOCATION" in categories,
        "detected_has_id_number":  any(c in categories for c in ["PASSPORT", "NRP"]),
        "detected_has_health":     "MEDICAL_LICENSE" in categories,
        "risk_level":              compute_risk(categories),
        "entities":                entities,
    }


# ── 6. Run the scan over the full DataFrame ───────────────────────────────────

# Detect language column — fall back to "en" if not present
has_language_col = "language" in df.columns

scan_results = df.apply(
    lambda row: pd.Series(
        scan_text(
            text=row["text"],
            language=row["language"] if has_language_col else "en",
        )
    ),
    axis=1,
)

df = pd.concat([df, scan_results], axis=1)

# Retention flag
df["retention_flag"] = df["creation_date"].apply(is_retention_exceeded)


# ── 7. Evaluation — compare ground truth vs detections ───────────────────────

EVAL_PAIRS = [
    ("contains_pii",    "detected_pii"),
    ("has_name",        "detected_has_name"),
    ("has_email",       "detected_has_email"),
    ("has_phone",       "detected_has_phone"),
    ("has_address",     "detected_has_address"),
    ("has_id_number",   "detected_has_id_number"),
    ("has_health",      "detected_has_health"),
]

print("=" * 60)
print("EVALUATION REPORT")
print("=" * 60)

for truth_col, pred_col in EVAL_PAIRS:
    if truth_col not in df.columns or pred_col not in df.columns:
        continue
    print(f"\n── {truth_col} ──")
    print(
        classification_report(
            df[truth_col],
            df[pred_col],
            target_names=["No PII", "PII Found"],
            zero_division=0,
        )
    )


# ── 8. Results preview ────────────────────────────────────────────────────────

preview_cols = [
    "file_id", "filename", "creation_date",
    "detected_pii", "detected_categories",
    "risk_level", "retention_flag",
]

print("=" * 60)
print("SCAN RESULTS PREVIEW")
print("=" * 60)
print(df[[c for c in preview_cols if c in df.columns]].to_string(index=False))


# ── 9. Export results ─────────────────────────────────────────────────────────

output_cols = [c for c in df.columns if c != "entities"]  # entities is a list; awkward in CSV
df[output_cols].to_csv("scan_results.csv", index=False)

# Save the detailed entity breakdown separately
entities_rows = []
for _, row in df.iterrows():
    for ent in row["entities"]:
        entities_rows.append({
            "file_id":  row.get("file_id", ""),
            "filename": row.get("filename", ""),
            **ent,
        })

pd.DataFrame(entities_rows).to_csv("entity_details.csv", index=False)

print("\nOutputs written to scan_results.csv and entity_details.csv")
