import os
import uuid
import json
import requests
from typing import List
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
import docx
import pptx
import re

app = FastAPI(title="AI Privacy Guard Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads_temp")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# ----------------- PYDANTIC SCHEMAS -----------------
class FlaggedItem(BaseModel):
    text: str
    type: str

class PIIScanResult(BaseModel):
    has_pii: bool
    flagged_items: List[FlaggedItem]

class TextScanRequest(BaseModel):
    text: str

class ReplacementRule(BaseModel):
    original: str
    replace_with: str

# ----------------- HYBRID AUDITING CORE -----------------

def run_regex_pii_audit(text_content: str) -> List[dict]:
    """Layer 1: Deterministic Regex catching for rigid formats."""
    # Dictionary of Regex patterns mapped to our 8 PII categories
    patterns = {
        "CONTACT_LOCATION": [
            r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+",  # Standard Emails
            r"(?:\+?\d{1,3}[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}" # Phone numbers
        ],
        "NETWORK_DEVICE": [
            r"\b(?:\d{1,3}\.){3}\d{1,3}\b",  # IPv4 Addresses
            r"(?:[0-9A-Fa-f]{2}[:-]){5}(?:[0-9A-Fa-f]{2})"  # MAC Addresses
        ],
        "SECURITY_SECRET": [
            r"ghp_[a-zA-Z0-9]{36}",  # GitHub Personal Access Tokens
            r"AKIA[0-9A-Z]{16}"      # AWS Access Key IDs
        ],
        "GOVERNMENT_LEGAL": [
            r"\b[A-Z]{5}[0-9]{4}[A-Z]{1}\b",  # Indian PAN Card format
            r"\b\d{4}[\s\-]?\d{4}[\s\-]?\d{4}\b" # Aadhaar / 12-digit ID formats
        ]
    }
    
    flagged = []
    for category, regex_list in patterns.items():
        for pattern in regex_list:
            # finditer gets the exact text match without destroying context
            for match in re.finditer(pattern, text_content):
                flagged.append({"text": match.group(), "type": category})
                
    return flagged


def flush_ollama_memory(model_name: str = "llama3.2:3b"):
    """Forces Ollama to drop the model from GPU/RAM memory."""
    print(f"[*] Flushing {model_name} from GPU/RAM memory...")
    try:
        # Sending an empty generate request with keep_alive=0 clears the VRAM
        requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": model_name,
                "keep_alive": 0
            },
            timeout=5
        )
        print("[*] Memory cleared successfully.")
    except Exception as e:
        print(f"[*] Memory flush skipped (Ollama offline).")

def run_ollama_pii_audit(text_content: str) -> dict:
    """Layer 2: Probabilistic LLM catching for contextual data."""
    system_prompt = (
        "You are an elite Data Privacy Auditor. Extract ALL Personally Identifiable Information (PII).\n\n"
        "Categories:\n"
        "1. PERSONAL_IDENTIFIER: Names, family members, managers.\n"
        "2. DEMOGRAPHIC_VITAL: Date of birth, place of birth, blood group.\n"
        "3. CONTACT_LOCATION: Addresses, room numbers.\n"
        "4. GOVERNMENT_LEGAL: Passports, Voter IDs, Student roll numbers.\n"
        "5. FINANCIAL_EMPLOYMENT: Bank names, card providers, credit/debit card numbers, CVVs, account numbers, routing/IFSC codes, salary.\n"
        "6. HEALTH_MEDICAL: Illnesses, allergies, prescriptions, doctors, clinics.\n"
        "7. NETWORK_DEVICE: Wi-Fi SSIDs, router passwords.\n"
        "8. SECURITY_SECRET: Crypto wallet addresses, hashes, password hints, 2FA codes, Secret Access Keys.\n\n"
        "RULES:\n"
        "- Extract EXACT literal values only.\n"
        "- NEVER skip consecutive items.\n"
        "- Extract all values even if the list is long."
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": (
                "Text to audit:\n"
                "Profile:\n"
                "Born: 12 May 1995 in Boston, MA. Emails: test1@mail.com. "
                "Bank: Chase Bank, Acc: 987654321, Salary: $90,000. Doctor: Dr. Smith, Allergy: Sulfa.\n\n"
                "1. Records\n"
                "- Full Legal Name: John Doe\n"
                "- Date of Birth: 22 October 1990\n"
            )
        },
        {
            "role": "assistant",
            "content": json.dumps({
                "has_pii": True,
                "flagged_items": [
                    {"text": "12 May 1995", "type": "DEMOGRAPHIC_VITAL"},
                    {"text": "Boston, MA", "type": "DEMOGRAPHIC_VITAL"},
                    {"text": "test1@mail.com", "type": "CONTACT_LOCATION"},
                    {"text": "Chase Bank", "type": "FINANCIAL_EMPLOYMENT"},
                    {"text": "987654321", "type": "FINANCIAL_EMPLOYMENT"},
                    {"text": "$90,000", "type": "FINANCIAL_EMPLOYMENT"},
                    {"text": "Dr. Smith", "type": "HEALTH_MEDICAL"},
                    {"text": "Sulfa", "type": "HEALTH_MEDICAL"},
                    {"text": "John Doe", "type": "PERSONAL_IDENTIFIER"},
                    {"text": "22 October 1990", "type": "DEMOGRAPHIC_VITAL"}
                ]
            })
        },
        {"role": "user", "content": f"Text to audit:\n{text_content[:4000]}"}
    ]

    ollama_payload = {
        "model": "llama3.2:3b",
        "messages": messages,
        "format": PIIScanResult.model_json_schema(),
        "stream": False,
        "keep_alive": 0,
        "options": {
            "temperature": 0.0,
            "num_ctx": 4096
        }
    }

    try:
        res = requests.post("http://localhost:11434/api/chat", json=ollama_payload, timeout=300)
        res.raise_for_status()
        raw_result = res.json()["message"]["content"]
        return json.loads(raw_result)
    except Exception as e:
        print(f"Extraction error: {e}")
        return {"has_pii": False, "flagged_items": []}

def run_hybrid_pii_audit(text_content: str) -> dict:
    """Layer 3: The Merger. Combines Regex and LLM results."""
    if not text_content.strip():
        return {"has_pii": False, "flagged_items": []}

    flush_ollama_memory("llama3.2:3b")

    # 1. Run Regex Parser
    regex_items = run_regex_pii_audit(text_content)

    # 2. Run LLM Parser
    ollama_result = run_ollama_pii_audit(text_content)
    ollama_items = ollama_result.get("flagged_items", [])

    # 3. Merge and Deduplicate
    all_items = regex_items + ollama_items
    
    unique_items = {}
    for item in all_items:
        text_key = item["text"].strip()
        # We use a dictionary to automatically overwrite duplicates.
        # If both Regex and Ollama find "alice@gmail.com", it only shows up once.
        if text_key not in unique_items:
            unique_items[text_key] = item

    final_list = list(unique_items.values())

    return {
        "has_pii": len(final_list) > 0,
        "flagged_items": final_list
    }

# ----------------- DOCUMENT TEXT EXTRACTION -----------------
def extract_text_from_file(file_path: str, ext: str) -> str:
    extracted_text = []

    if ext == ".docx":
        doc = docx.Document(file_path)
        for p in doc.paragraphs:
            if p.text:
                extracted_text.append(p.text)
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    if cell.text:
                        extracted_text.append(cell.text)

    elif ext == ".pptx":
        prs = pptx.Presentation(file_path)
        for slide in prs.slides:
            for shape in slide.shapes:
                if shape.has_text_frame:
                    for paragraph in shape.text_frame.paragraphs:
                        if paragraph.text:
                            extracted_text.append(paragraph.text)
                if shape.has_table:
                    for row in shape.table.rows:
                        for cell in row.cells:
                            if cell.text:
                                extracted_text.append(cell.text)

    elif ext == ".pdf":
        # SKELETON: We will connect PyMuPDF here in the next step
        pass

    return "\n".join(extracted_text)

# ----------------- DOCUMENT MASKING / REPLACEMENT -----------------
def apply_masks_to_file(source_path: str, target_path: str, ext: str, replacements: List[ReplacementRule]):
    if ext == ".docx":
        doc = docx.Document(source_path)
        for rule in replacements:
            for p in doc.paragraphs:
                if rule.original in p.text:
                    p.text = p.text.replace(rule.original, rule.replace_with)
            for table in doc.tables:
                for row in table.rows:
                    for cell in row.cells:
                        if rule.original in cell.text:
                            cell.text = cell.text.replace(rule.original, rule.replace_with)
        doc.save(target_path)

    elif ext == ".pptx":
        prs = pptx.Presentation(source_path)
        for rule in replacements:
            for slide in prs.slides:
                for shape in slide.shapes:
                    if shape.has_text_frame:
                        for p in shape.text_frame.paragraphs:
                            if rule.original in p.text:
                                p.text = p.text.replace(rule.original, rule.replace_with)
                    if shape.has_table:
                        for row in shape.table.rows:
                            for cell in row.cells:
                                if rule.original in cell.text:
                                    cell.text = cell.text.replace(rule.original, rule.replace_with)
        prs.save(target_path)

    elif ext == ".pdf":
        # SKELETON: PDF coordinate-based redaction will go here
        pass

# ----------------- API ENDPOINTS -----------------
# @app.post("/scan")
# def scan_text(request: TextScanRequest):
#     return run_ollama_pii_audit(request.text)

# @app.post("/scan-file")
# async def scan_file(file: UploadFile = File(...)):
#     filename = file.filename
#     ext = os.path.splitext(filename)[1].lower()

#     if ext not in [".docx", ".pptx", ".pdf"]:
#         raise HTTPException(status_code=400, detail="Only .docx, .pptx, and .pdf are supported.")

#     file_id = str(uuid.uuid4())
#     saved_path = os.path.join(UPLOAD_DIR, f"{file_id}{ext}")

#     with open(saved_path, "wb") as f:
#         f.write(await file.read())

#     extracted_text = extract_text_from_file(saved_path, ext)
#     scan_result = run_ollama_pii_audit(extracted_text)

#     return {
#         "file_id": file_id,
#         "filename": filename,
#         "extension": ext,
#         "has_pii": scan_result.get("has_pii", False),
#         "flagged_items": scan_result.get("flagged_items", []),
#         "preview_text": extracted_text[:500]
#     }

# ----------------- API ENDPOINTS -----------------
@app.post("/scan")
def scan_text(request: TextScanRequest):
    return run_hybrid_pii_audit(request.text) # <--- UPDATED HERE

@app.post("/scan-file")
async def scan_file(file: UploadFile = File(...)):
    filename = file.filename
    ext = os.path.splitext(filename)[1].lower()

    if ext not in [".docx", ".pptx", ".pdf"]:
        raise HTTPException(status_code=400, detail="Only .docx, .pptx, and .pdf are supported.")

    file_id = str(uuid.uuid4())
    saved_path = os.path.join(UPLOAD_DIR, f"{file_id}{ext}")

    with open(saved_path, "wb") as f:
        f.write(await file.read())

    # extracted_text = extract_text_from_file(saved_path, ext)
    # scan_result = run_hybrid_pii_audit(extracted_text) # <--- UPDATED HERE
    # --- ADD THESE PRINT STATEMENTS ---
    print(f"\n--- NEW FILE UPLOAD: {filename} ---")
    print("1. Extracting text from document...")
    extracted_text = extract_text_from_file(saved_path, ext)
    print(f"   -> Found {len(extracted_text)} characters.")
    
    print("2. Running Regex Layer (Instant)...")
    # Note: We let the hybrid function handle the actual regex call, 
    # we just print this here for terminal tracking.
    
    print(f"3. Running Ollama 3B LLM Layer (This will take a moment)...")
    scan_result = run_hybrid_pii_audit(extracted_text)
    
    print("4. Scan complete! Sending data back to Chrome.")
    print("-----------------------------------\n")
    # ----------------------------------

    return {
        "file_id": file_id,
        "filename": filename,
        "extension": ext,
        "has_pii": scan_result.get("has_pii", False),
        "flagged_items": scan_result.get("flagged_items", []),
        "preview_text": extracted_text[:500]
    }

@app.post("/mask-file")
async def mask_file(file_id: str = Form(...), rules_json: str = Form(...)):
    rules_data = json.loads(rules_json)
    replacements = [ReplacementRule(**r) for r in rules_data]

    # Find the matching original file in uploads_temp
    matching_files = [f for f in os.listdir(UPLOAD_DIR) if f.startswith(file_id)]
    if not matching_files:
        raise HTTPException(status_code=404, detail="File session expired or missing.")

    original_filename = matching_files[0]
    ext = os.path.splitext(original_filename)[1].lower()
    source_path = os.path.join(UPLOAD_DIR, original_filename)
    masked_path = os.path.join(UPLOAD_DIR, f"safe_{file_id}{ext}")

    apply_masks_to_file(source_path, masked_path, ext, replacements)

    return FileResponse(
        path=masked_path,
        filename=f"safe_{original_filename[37:]}" if len(original_filename) > 37 else f"safe_masked{ext}",
        media_type="application/octet-stream"
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)