from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database import get_db
from models import Finding, AuditLog
from datetime import datetime
import json

router = APIRouter()

@router.get("/")
def list_findings(risk_level: str = None, db: Session = Depends(get_db)):
    query = db.query(Finding)
    if risk_level:
        query = query.filter(Finding.risk_level == risk_level)
    results = []
    for f in query.all():
        pii_types = json.loads(f.pii_types) if f.pii_types else []
        results.append({
            "document_id":       f.id,
            "file_name":         f.file.file_name,
            "document_type":     "Unknown",
            "source_system":     f.file.owner_email.split("@")[-1] if f.file.owner_email else "Unknown",
            "responsible_owner": f.file.owner_email or "Unknown",
            "owner_email":       f.file.owner_email or "Unknown",
            "file_created_date": f.file.last_modified or "Unknown",
            "last_modified_date": f.file.last_modified or "Unknown",
            "contains_personal_data": "yes" if pii_types else "no",
            "full_text":         f.reason or "",
            "retention_period_exceeded_3y": "yes" if f.file.last_modified and (datetime.utcnow() - datetime.strptime(f.file.last_modified[:10], "%Y-%m-%d")).days > 3*365 else "no",
            "PERSON_yes_no":          "yes" if "PERSON" in pii_types else "no",
            "EMAIL_ADDRESS_yes_no":   "yes" if "EMAIL_ADDRESS" in pii_types else "no",
            "PHONE_NUMBER_yes_no":    "yes" if "PHONE_NUMBER" in pii_types else "no",
            "LOCATION_yes_no":        "yes" if "LOCATION" in pii_types else "no",
            "IBAN_CODE_yes_no":       "yes" if "IBAN_CODE" in pii_types else "no",
            "CREDIT_CARD_yes_no":     "yes" if "CREDIT_CARD" in pii_types else "no",
            "PASSPORT_yes_no":        "yes" if "PASSPORT" in pii_types else "no",
            "NRP_yes_no":             "yes" if "NRP" in pii_types else "no",
            "DATE_TIME_yes_no":       "yes" if "DATE_TIME" in pii_types else "no",
            "IP_ADDRESS_yes_no":      "yes" if "IP_ADDRESS" in pii_types else "no",
            "URL_yes_no":             "yes" if "URL" in pii_types else "no",
            "MEDICAL_LICENSE_yes_no": "yes" if "MEDICAL_LICENSE" in pii_types else "no",
            "reviewer_action":        f.reviewer_action,
        })
    return results
@router.patch("/{finding_id}/review")
def review_finding(finding_id: str, action: str, reviewed_by: str, db: Session = Depends(get_db)):
    finding = db.query(Finding).filter(Finding.id == finding_id).first()
    finding.reviewer_action = action
    finding.reviewed_by     = reviewed_by
    finding.reviewed_at     = datetime.utcnow()
    db.commit()

    db.add(AuditLog(
        file_id = finding.file_id,
        action  = action,
        actor   = reviewed_by,
        detail  = f"Reviewer decision: {action}"
    ))
    db.commit()
    return {"status": "updated", "action": action}
    
