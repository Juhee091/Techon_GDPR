from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database import get_db
from models import Finding, AuditLog
from datetime import datetime

router = APIRouter()

@router.get("/")
def list_findings(risk_level: str = None, db: Session = Depends(get_db)):
    query = db.query(Finding)
    if risk_level:
        query = query.filter(Finding.risk_level == risk_level)
    results = []
    for f in query.all():
        results.append({
            "id":              f.id,
            "file_name":       f.file.file_name,
            "owner_email":     f.file.owner_email,
            "risk_level":      f.risk_level,
            "category":        f.category,
            "pii_types":       f.pii_types,
            "regex_hits":      f.regex_hits,
            "reason":          f.reason,
            "reviewer_action": f.reviewer_action,
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
    