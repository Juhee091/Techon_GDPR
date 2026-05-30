from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import engine, Base
from routers import scan, findings

Base.metadata.create_all(bind=engine)

app = FastAPI(title="GDPR Scanner")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(scan.router,     prefix="/scan",     tags=["scan"])
app.include_router(findings.router, prefix="/findings", tags=["findings"])

@app.get("/health")
def health():
    return {"status": "ok"}