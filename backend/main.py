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

# ----------------- LLM AUDITING CORE -----------------
def run_ollama_pii_audit(text_content: str) -> dict:
    if not text_content.strip():
        return {"has_pii": False, "flagged_items": []}

    system_prompt = (
        "You are an expert data privacy auditor. Your task is the exhaustive extraction of ALL Personally Identifiable Information (PII).\n"
        "Carefully scan line-by-line and extract exact values for:\n"
        "1. PERSON_NAME (Real names, family members, officials)\n"
        "2. CONTACT (Emails, phone numbers, addresses, handles)\n"
        "3. FINANCIAL (Card numbers, CVV, bank account numbers)\n"
        "4. GOVERNMENT_ID (SSN, Passports, Driver's License)\n"
        "5. SECURITY_BIOMETRIC (Passwords, Birth dates/cities, cryptographic keys, hashes)\n"
        "6. INSTITUTIONAL (School, company, university IDs)\n\n"
        "CRITICAL: Extract the sensitive VALUE ONLY. Do not omit any ID or hash."
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "Text to audit: My name is Alice, email is alice@test.com, born in Chicago."},
        {"role": "assistant", "content": '{"has_pii": true, "flagged_items": [{"text": "Alice", "type": "PERSON_NAME"}, {"text": "alice@test.com", "type": "CONTACT"}, {"text": "Chicago", "type": "SECURITY_BIOMETRIC"}]}'},
        {"role": "user", "content": f"Text to audit: {text_content[:4000]}"} # Scan first 4k chars to stay fast
    ]

    ollama_payload = {
        "model": "llama3.2:3b",
        "messages": messages,
        "format": PIIScanResult.model_json_schema(),
        "stream": False,
        "options": {"temperature": 0.0}
    }

    try:
        res = requests.post("http://localhost:11434/api/chat", json=ollama_payload, timeout=90)
        res.raise_for_status()
        raw_result = res.json()["message"]["content"]
        return json.loads(raw_result)
    except Exception as e:
        print(f"Ollama Error: {e}")
        return {"has_pii": False, "flagged_items": []}

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
@app.post("/scan")
def scan_text(request: TextScanRequest):
    return run_ollama_pii_audit(request.text)

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

    extracted_text = extract_text_from_file(saved_path, ext)
    scan_result = run_ollama_pii_audit(extracted_text)

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