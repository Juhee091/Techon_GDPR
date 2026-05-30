from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy.orm import Session
from database import get_db, SessionLocal
from models import ScanJob, ScannedFile, Finding, AuditLog
from services.graph_client import collect_files
from services.classifier import classify
import pdfplumber, json, hashlib
from datetime import datetime

router = APIRouter()

@router.post("/")
def start_scan(source: str, scan_type: str = "full", background_tasks: BackgroundTasks = None, db: Session = Depends(get_db)):
    job = ScanJob(source=source, scan_type=scan_type)
    db.add(job)
    db.commit()
    db.refresh(job)
    background_tasks.add_task(run_scan, job.id, source, scan_type)
    return {"job_id": job.id, "status": "started"}

@router.get("/{job_id}")
def get_scan(job_id: str, db: Session = Depends(get_db)):
    job   = db.query(ScanJob).filter(ScanJob.id == job_id).first()
    files = db.query(ScannedFile).filter(ScannedFile.job_id == job_id).all()
    return {
        "job_id":      job.id,
        "status":      job.status,
        "total_files": len(files),
        "classified":  sum(1 for f in files if f.status == "classified"),
        "errors":      sum(1 for f in files if f.status == "error"),
    }

def run_scan(job_id: str, source: str, scan_type: str):
    db = SessionLocal()
    try:
        job = db.query(ScanJob).filter(ScanJob.id == job_id).first()
        job.status = "running"
        db.commit()

        files = collect_files(source)

        for f in files:
            if scan_type == "delta":
                existing = db.query(ScannedFile).filter(
                    ScannedFile.file_path == f["file_path"],
                    ScannedFile.file_hash == f["file_hash"]
                ).first()
                if existing:
                    continue

            full_text = f.pop("full_text", None)
            f.pop("ground_truth", None)
            scanned = ScannedFile(job_id=job_id, **f)
            db.add(scanned)
            db.commit()
            db.refresh(scanned)

            db.add(AuditLog(file_id=scanned.id, action="scanned", actor="system"))
            db.commit()

            try:
                if full_text:
                    text = full_text[:3000]
                else:
                    with pdfplumber.open(scanned.file_path) as pdf:
                        text = "\n".join(p.extract_text() or "" for p in pdf.pages)
                    text = text[:3000] 

                result = classify(text[:3000])

                finding = Finding(
                    file_id    = scanned.id,
                    risk_level = result["risk_level"],
                    category   = result["category"],
                    pii_types  = json.dumps(result["pii_types"]),
                    regex_hits = json.dumps(result["regex_hits"]),
                    reason     = result["reason"],
                )
                db.add(finding)
                scanned.status = "classified"
                db.add(AuditLog(file_id=scanned.id, action="classified", actor="system",
                                detail=f"risk={result['risk_level']}"))
                db.commit()

            except Exception as e:
                print(f"FILE ERROR: {e}")
                import traceback
                traceback.print_exc()
                scanned.status = "error"
                db.commit()

        job.status = "done"
        job.completed_at = datetime.utcnow()
        db.commit()

    except Exception as e:
        print(f"SCAN ERROR: {e}")
        import traceback
        traceback.print_exc()
        job.status = "failed"
        db.commit()
