import re
from presidio_analyzer import AnalyzerEngine

analyzer = AnalyzerEngine()

REGEX_PATTERNS = {
    "email pattern": r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+",
    "IBAN pattern":  r"\b[A-Z]{2}\d{2}[A-Z0-9]{4}\d{7}([A-Z0-9]?){0,16}\b",
    "phone pattern": r"(\+49|0)[0-9\s\-]{9,}",
}

CATEGORY_MAP = {
    "PERSON":          "identity",
    "EMAIL_ADDRESS":   "contact",
    "PHONE_NUMBER":    "contact",
    "LOCATION":        "identity",
    "IBAN_CODE":       "financial",
    "CREDIT_CARD":     "financial",
    "PASSPORT":        "identity",
    "NRP":             "identity",
    "DATE_TIME":       "identity",
    "IP_ADDRESS":      "contact",
    "URL":             "contact",
    "MEDICAL_LICENSE": "health",
}

HIGH_ENTITIES   = {"IBAN_CODE", "CREDIT_CARD", "PASSPORT", "NRP", "MEDICAL_LICENSE"}
MEDIUM_ENTITIES = {"PERSON", "LOCATION", "DATE_TIME", "PHONE_NUMBER"}

def classify(text: str) -> dict:
    results = analyzer.analyze(text=text, language="en")
    detected_entities = list(set(r.entity_type for r in results))

    regex_hits = [name for name, pattern in REGEX_PATTERNS.items() if re.search(pattern, text)]

    if any(e in HIGH_ENTITIES for e in detected_entities):
        risk_level = "HIGH"
    elif any(e in MEDIUM_ENTITIES for e in detected_entities):
        risk_level = "MEDIUM"
    elif detected_entities:
        risk_level = "LOW"
    else:
        risk_level = "LOW"

    categories = list(set(CATEGORY_MAP.get(e, "none") for e in detected_entities))
    if "financial" in categories:
        category = "financial"
    elif "health" in categories:
        category = "health"
    elif "identity" in categories:
        category = "identity"
    elif "contact" in categories:
        category = "contact"
    else:
        category = "none"

    if detected_entities:
        reason = f"Detected: {', '.join(detected_entities)}."
    else:
        reason = "No personal data detected."

    return {
        "risk_level": risk_level,
        "category":   category,
        "pii_types":  detected_entities,
        "regex_hits": regex_hits,
        "reason":     reason,
    }