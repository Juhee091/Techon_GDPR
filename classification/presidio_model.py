import re
import warnings
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from sklearn.metrics import (
    classification_report,
    confusion_matrix,
    ConfusionMatrixDisplay,
)
from presidio_analyzer import AnalyzerEngine
from presidio_analyzer.nlp_engine import NlpEngineProvider

warnings.filterwarnings("ignore")

# ─────────────────────────────────────────────────────────────────────────────
# 1. Load Data
# ─────────────────────────────────────────────────────────────────────────────

df = pd.read_excel(
    r"classification\sample_data.xlsx",
    parse_dates=["file_created_date", "last_modified_date"],
)

# ─────────────────────────────────────────────────────────────────────────────
# 2. Presidio Engine
# ─────────────────────────────────────────────────────────────────────────────

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

# ─────────────────────────────────────────────────────────────────────────────
# 3. Retention Logic
# ─────────────────────────────────────────────────────────────────────────────

RETENTION_YEARS = 3
TODAY = pd.Timestamp.today().normalize()

def is_retention_exceeded(creation_date):
    if pd.isnull(creation_date):
        return False
    return (TODAY - creation_date).days > RETENTION_YEARS * 365

# ─────────────────────────────────────────────────────────────────────────────
# 4. Risk Weights + Category Roles
# ─────────────────────────────────────────────────────────────────────────────

# Strong PII: used for accuracy and "high confidence" classification
STRONG_PII = {
    "PHONE_NUMBER",
    "CREDIT_CARD",
    "IBAN_CODE",
    "MEDICAL_LICENSE",
}

# Potential PII: shown in UI as "potential personal data", excluded from accuracy
POTENTIAL_PII = {
    "PERSON",
    "EMAIL_ADDRESS",
}

MEANINGFUL_PII = STRONG_PII | POTENTIAL_PII

ENTITY_WEIGHTS = {
    "PERSON":          0.3,
    "EMAIL_ADDRESS":   0.5,
    "PHONE_NUMBER":    1.0,
    "CREDIT_CARD":     1.0,
    "IBAN_CODE":       1.0,
    "MEDICAL_LICENSE": 0.8,
}

REGEX_BOOST = 0.3
REGEX_BASE_CONFIDENCE = 0.9

def risk_level_from_score(score):
    if score <= 0:
        return "None"
    if score < 1.0:
        return "Low"
    if score < 3.0:
        return "Medium"
    return "High"

# ─────────────────────────────────────────────────────────────────────────────
# 5. Regex Detectors (for kept features)
# ─────────────────────────────────────────────────────────────────────────────

_RE_EMAIL = re.compile(
    r"\b[a-zA-Z0-9._%+\-äöüÄÖÜß]+@[a-zA-Z0-9\-]+\.[a-zA-Z]{2,}\b",
    re.IGNORECASE,
)

_RE_IBAN = re.compile(
    r"\b[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]{4}){2,7}\b"
)

_RE_CREDIT_CARD = re.compile(
    r"\b(?:\d[ -]*?){13,16}\b"
)

_RE_MEDICAL = re.compile(
    r"\b(?:Approbation(?:snummer)?|Arztnummer|Heilpraktiker|Medical\s+ID|Medizinische\s+Lizenz)\b",
    re.IGNORECASE,
)

def custom_detect(text):
    if not isinstance(text, str) or not text.strip():
        return {k: False for k in [
            "custom_EMAIL_ADDRESS",
            "custom_IBAN_CODE",
            "custom_CREDIT_CARD",
            "custom_MEDICAL_LICENSE",
        ]}
    return {
        "custom_EMAIL_ADDRESS":   bool(_RE_EMAIL.search(text)),
        "custom_IBAN_CODE":       bool(_RE_IBAN.search(text)),
        "custom_CREDIT_CARD":     bool(_RE_CREDIT_CARD.search(text)),
        "custom_MEDICAL_LICENSE": bool(_RE_MEDICAL.search(text)),
    }

# ─────────────────────────────────────────────────────────────────────────────
# 6. Fusion Layer (Presidio + Regex)
# ─────────────────────────────────────────────────────────────────────────────

def fuse_entities(text, language="en"):
    if not isinstance(text, str) or not text.strip():
        return {
            "entities": [],
            "per_type_conf": {},
            "risk_score": 0.0,
            "risk_level": "None",
        }

    raw = engine.analyze(text=text, language=language, score_threshold=0.5)

    entities = []
    per_type_scores = {}

    for r in raw:
        etype = r.entity_type.upper()
        value = text[r.start:r.end]
        conf = float(r.score)

        if etype not in MEANINGFUL_PII:
            continue

        entities.append({
            "type": etype,
            "value": value,
            "confidence": round(conf, 3),
            "source": "presidio",
        })

        per_type_scores.setdefault(etype, []).append(conf)

    custom = custom_detect(text)
    regex_map = {
        "EMAIL_ADDRESS": custom["custom_EMAIL_ADDRESS"],
        "IBAN_CODE": custom["custom_IBAN_CODE"],
        "CREDIT_CARD": custom["custom_CREDIT_CARD"],
        "MEDICAL_LICENSE": custom["custom_MEDICAL_LICENSE"],
    }

    for etype, detected in regex_map.items():
        if not detected:
            continue

        if etype in per_type_scores:
            boosted = [min(1.0, s + REGEX_BOOST) for s in per_type_scores[etype]]
            per_type_scores[etype] = boosted
        else:
            per_type_scores.setdefault(etype, []).append(REGEX_BASE_CONFIDENCE)
            entities.append({
                "type": etype,
                "value": "",
                "confidence": REGEX_BASE_CONFIDENCE,
                "source": "custom_regex",
            })

    per_type_conf = {etype: max(scores) for etype, scores in per_type_scores.items()}

    risk_score = sum(
        ENTITY_WEIGHTS.get(etype, 0.0) * conf
        for etype, conf in per_type_conf.items()
    )

    return {
        "entities": entities,
        "per_type_conf": per_type_conf,
        "risk_score": round(risk_score, 3),
        "risk_level": risk_level_from_score(risk_score),
    }

# ─────────────────────────────────────────────────────────────────────────────
# 7. scan_text (Unified, with strong vs potential PII)
# ─────────────────────────────────────────────────────────────────────────────

def scan_text(text, language="en"):
    base = {
        "detected_categories": [],
        "strong_pii_categories": [],
        "potential_pii_categories": [],
        "detected_any_pii": False,   # strong OR potential (for UI)
        "detected_pii": False,       # strong only (for accuracy)
        "risk_score": 0.0,
        "risk_level": "None",
        "entities": [],
        "per_type_conf": {},
    }

    for etype in MEANINGFUL_PII:
        base[f"detected_{etype}"] = False

    if not isinstance(text, str) or not text.strip():
        base["detected_category_count"] = 0
        return base

    fusion = fuse_entities(text, language)

    per_type_conf = fusion["per_type_conf"]
    entities = fusion["entities"]
    risk_score = fusion["risk_score"]
    risk_level = fusion["risk_level"]

    categories = sorted(per_type_conf.keys())

    strong_hit = False
    potential_hit = False
    strong_cats = []
    potential_cats = []

    for etype, conf in per_type_conf.items():
        flag = f"detected_{etype}"
        if flag in base:
            base[flag] = conf > 0

        if etype in STRONG_PII and conf > 0:
            strong_hit = True
            strong_cats.append(etype)
        if etype in POTENTIAL_PII and conf > 0:
            potential_hit = True
            potential_cats.append(etype)

    base.update({
        "detected_any_pii": strong_hit or potential_hit,
        "detected_pii": strong_hit,  # used for accuracy
        "detected_categories": categories,
        "detected_category_count": len(categories),
        "strong_pii_categories": sorted(set(strong_cats)),
        "potential_pii_categories": sorted(set(potential_cats)),
        "risk_score": risk_score,
        "risk_level": risk_level,
        "entities": entities,
        "per_type_conf": per_type_conf,
    })

    return base

# ─────────────────────────────────────────────────────────────────────────────
# 8. Run Scan
# ─────────────────────────────────────────────────────────────────────────────

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
df["detected_retention_exceeded"] = df["file_created_date"].apply(is_retention_exceeded)

# ─────────────────────────────────────────────────────────────────────────────
# 9. Document-level Ground Truth (excluding PERSON + EMAIL)
# ─────────────────────────────────────────────────────────────────────────────

pii_truth_cols = [
    col for col in df.columns
    if col.endswith("_yes_no")
    and col not in {"person_yes_no", "email_address_yes_no"}
]

df["truth_document_pii"] = df[pii_truth_cols].apply(
    lambda row: any(str(v).lower() in {"yes", "true", "1"} for v in row),
    axis=1
)

df["correct_document_prediction"] = df["truth_document_pii"] == df["detected_pii"]

document_accuracy = df["correct_document_prediction"].mean()
print("\n── Document-Level Accuracy (strong PII only) ──")
print("Accuracy:", round(document_accuracy, 3))

from sklearn.metrics import confusion_matrix, ConfusionMatrixDisplay

cm_doc = confusion_matrix(df["truth_document_pii"], df["detected_pii"])
disp = ConfusionMatrixDisplay(cm_doc, display_labels=["No PII", "PII"])
disp.plot(cmap="Blues")
plt.title("Document-Level Confusion Matrix (Strong PII)")
plt.show()

# ─────────────────────────────────────────────────────────────────────────────
# 10. Feature-level Evaluation (excluding PERSON + EMAIL)
# ─────────────────────────────────────────────────────────────────────────────

def build_eval_pairs(df):
    pairs = []
    for col in df.columns:
        if col.endswith("_yes_no"):
            if col in {"person_yes_no", "email_address_yes_no"}:
                continue  # exclude from accuracy metrics
            base = col[:-7]
            candidates = [
                f"detected_{base.upper()}",
                f"detected_{base}",
            ]
            for pred in candidates:
                if pred in df.columns:
                    pairs.append((col, pred))
                    break
    return pairs

EVAL_PAIRS = build_eval_pairs(df)

def normalise_truth(series):
    return series.map(lambda v: str(v).strip().lower() in {"true", "yes", "1"})

eval_results = []
metrics_rows = []

for truth_col, pred_col in EVAL_PAIRS:
    truth = normalise_truth(df[truth_col])
    pred = df[pred_col].astype(bool)

    report = classification_report(
        truth, pred,
        target_names=["No", "Yes"],
        output_dict=True,
        zero_division=0,
    )

    label = truth_col.replace("_yes_no", "").replace("_", " ").title()

    metrics_rows.append({
        "Label": label,
        "Precision": round(report["Yes"]["precision"], 3),
        "Recall": round(report["Yes"]["recall"], 3),
        "F1": round(report["Yes"]["f1-score"], 3),
        "Support": int(report["Yes"]["support"]),
    })

    eval_results.append((label, truth, pred))

metrics_df = pd.DataFrame(metrics_rows)
print("\n── Evaluation Metrics (Strong PII only) ──")
print(metrics_df.to_string(index=False))
metrics_df.to_csv("evaluation_metrics_strong_pii.csv", index=False)

# ─────────────────────────────────────────────────────────────────────────────
# 10a. Bar Chart
# ─────────────────────────────────────────────────────────────────────────────

labels = metrics_df["Label"].tolist()
x = np.arange(len(labels))
width = 0.25

fig, ax = plt.subplots(figsize=(15, 5))
ax.bar(x - width, metrics_df["Precision"], width, label="Precision")
ax.bar(x, metrics_df["Recall"], width, label="Recall")
ax.bar(x + width, metrics_df["F1"], width, label="F1")

ax.set_xticks(x)
ax.set_xticklabels(labels, rotation=35, ha="right")
ax.set_ylim(0, 1.1)
ax.set_ylabel("Score")
ax.set_title("PII Detection Performance (Strong PII)")
ax.legend()
plt.tight_layout()
plt.savefig("fig1_performance_bars_strong_pii.png", dpi=150)
plt.show()

# ─────────────────────────────────────────────────────────────────────────────
# 10b. Heatmap
# ─────────────────────────────────────────────────────────────────────────────

heatmap_data = metrics_df[["Precision", "Recall", "F1"]].values

fig, ax = plt.subplots(figsize=(5, max(4, len(labels) * 0.45)))
im = ax.imshow(heatmap_data, aspect="auto", cmap="RdYlGn", vmin=0, vmax=1)

ax.set_xticks([0, 1, 2])
ax.set_xticklabels(["Precision", "Recall", "F1"])
ax.set_yticks(range(len(labels)))
ax.set_yticklabels(labels)
ax.set_title("Metrics Heatmap (Strong PII)")

for i in range(len(labels)):
    for j, val in enumerate(heatmap_data[i]):
        color = "black" if 0.35 < val < 0.85 else "white"
        ax.text(j, i, f"{val:.2f}", ha="center", va="center", color=color)

plt.colorbar(im, ax=ax, fraction=0.03)
plt.tight_layout()
plt.savefig("fig2_metrics_heatmap_strong_pii.png", dpi=150)
plt.show()

# ─────────────────────────────────────────────────────────────────────────────
# 10c. Confusion Matrices (Strong PII labels)
# ─────────────────────────────────────────────────────────────────────────────

ncols = 4
nrows = int(np.ceil(len(eval_results) / ncols))

fig, axes = plt.subplots(nrows, ncols, figsize=(ncols * 3.5, nrows * 3.2))
axes = axes.flatten()

for i, (label, truth, pred) in enumerate(eval_results):
    cm = confusion_matrix(truth, pred)
    disp = ConfusionMatrixDisplay(cm, display_labels=["No", "Yes"])
    disp.plot(ax=axes[i], colorbar=False, cmap="Blues")
    axes[i].set_title(label)
    axes[i].set_xlabel("")
    axes[i].set_ylabel("")

for j in range(i + 1, len(axes)):
    axes[j].set_visible(False)

plt.tight_layout()
plt.savefig("fig3_confusion_matrices_strong_pii.png", dpi=150)
plt.show()

# ─────────────────────────────────────────────────────────────────────────────
# 11. Export Results (Backend → Frontend)
# ─────────────────────────────────────────────────────────────────────────────

# Main scan results (without exploding entities)
df[[c for c in df.columns if c != "entities"]].to_csv("scan_results.csv", index=False)

# Entity-level details for frontend (strong + potential)
entities_rows = []
for _, row in df.iterrows():
    for ent in row.get("entities", []):
        entities_rows.append({
            "file_name": row.get("file_name", ""),
            "document_type": row.get("document_type", ""),
            "responsible_owner": row.get("responsible_owner", ""),
            "type": ent.get("type", ""),
            "value": ent.get("value", ""),
            "confidence": ent.get("confidence", ""),
            "source": ent.get("source", ""),
        })

pd.DataFrame(entities_rows).to_csv("entity_details.csv", index=False)

print("\nSaved: scan_results.csv, entity_details.csv")
print("Saved: fig1_performance_bars_strong_pii.png, fig2_metrics_heatmap_strong_pii.png, fig3_confusion_matrices_strong_pii.png")
print("Saved: evaluation_metrics_strong_pii.csv")
