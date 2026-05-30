import os, hashlib
import pandas as pd
import msal
import httpx
from dotenv import load_dotenv
load_dotenv()

GRAPH_URL = "https://graph.microsoft.com/v1.0"

def get_token():
    app = msal.ConfidentialClientApplication(
        client_id=os.getenv("AZURE_CLIENT_ID"),
        client_credential=os.getenv("AZURE_CLIENT_SECRET"),
        authority=f"https://login.microsoftonline.com/{os.getenv('AZURE_TENANT_ID')}"
    )
    result = app.acquire_token_for_client(
        scopes=["https://graph.microsoft.com/.default"]
    )
    if "access_token" not in result:
        raise Exception(f"Token error: {result.get('error_description')}")
    return result["access_token"]

def collect_files(source: str) -> list:
    if source == "onedrive":
        return collect_onedrive_files()
    elif source == "excel":
        return collect_from_excel()
    return collect_local_files()

def collect_onedrive_files() -> list:
    token = get_token()
    headers = {"Authorization": f"Bearer {token}"}
    resp = httpx.get(f"{GRAPH_URL}/drives", headers=headers)
    drives = resp.json().get("value", [])
    files = []
    for drive in drives:
        drive_id = drive["id"]
        resp2 = httpx.get(f"{GRAPH_URL}/drives/{drive_id}/root/children", headers=headers)
        items = resp2.json().get("value", [])
        for item in items:
            if "file" not in item:
                continue
            if not item["name"].endswith(".pdf"):
                continue
            files.append({
                "file_name":     item["name"],
                "file_path":     item.get("@microsoft.graph.downloadUrl", ""),
                "owner_email":   item.get("createdBy", {}).get("user", {}).get("email", "unknown"),
                "last_modified": item.get("lastModifiedDateTime"),
                "file_hash":     item.get("file", {}).get("hashes", {}).get("sha256Hash", ""),
            })
    return files

def collect_local_files(folder: str = "./sample_files") -> list:
    files = []
    if not os.path.exists(folder):
        return files
    for fname in os.listdir(folder):
        if not fname.endswith(".pdf"):
            continue
        fpath = os.path.join(folder, fname)
        with open(fpath, "rb") as f:
            content = f.read()
        files.append({
            "file_name":     fname,
            "file_path":     fpath,
            "owner_email":   "demo@example.com",
            "last_modified": None,
            "file_hash":     hashlib.sha256(content).hexdigest(),
        })
    return files

def collect_from_excel(path: str = "./gdpr_training_dataset.xlsx") -> list:
    df = pd.read_excel(path)
    files = []
    for _, row in df.iterrows():
        files.append({
            "file_name":     row["file_name"],
            "file_path":     row["file_name"],
            "owner_email":   row["owner_email"],
            "last_modified": str(row["last_modified_date"]),
            "file_hash":     hashlib.sha256(str(row["full_text"]).encode()).hexdigest(),
            "full_text":     str(row["full_text"]),
            "ground_truth":  {
                "contains_personal_data": row["contains_personal_data"],
                "PERSON":          row["PERSON_yes_no"],
                "EMAIL_ADDRESS":   row["EMAIL_ADDRESS_yes_no"],
                "PHONE_NUMBER":    row["PHONE_NUMBER_yes_no"],
                "LOCATION":        row["LOCATION_yes_no"],
                "IBAN_CODE":       row["IBAN_CODE_yes_no"],
                "CREDIT_CARD":     row["CREDIT_CARD_yes_no"],
                "PASSPORT":        row["PASSPORT_yes_no"],
                "NRP":             row["NRP_yes_no"],
                "DATE_TIME":       row["DATE_TIME_yes_no"],
                "IP_ADDRESS":      row["IP_ADDRESS_yes_no"],
                "URL":             row["URL_yes_no"],
                "MEDICAL_LICENSE": row["MEDICAL_LICENSE_yes_no"],
            }
        })
    return files