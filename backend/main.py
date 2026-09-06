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
import fitz  # <--- NEW: Add PyMuPDF here

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

# ----------------- MEMORY MANAGEMENT -----------------
def flush_ollama_memory(model_name: str = "llama3.2:3b"):
    """Safely drops the model from memory AFTER processing is fully complete."""
    try:
        requests.post(
            "http://localhost:11434/api/generate",
            json={"model": model_name, "keep_alive": 0},
            timeout=5
        )
        print(f"[*] Memory flushed for {model_name}.")
    except Exception:
        pass

# ----------------- HYBRID AUDITING CORE -----------------
def run_regex_pii_audit(text_content: str) -> List[dict]:
    """Layer 1: Deterministic Regex catching for rigid formats."""
    patterns = {
        "CONTACT_LOCATION": [
            r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", 
            r"(?:\+?\d{1,3}[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}" 
        ],
        "NETWORK_DEVICE": [
            r"\b(?:\d{1,3}\.){3}\d{1,3}\b", 
            r"(?:[0-9A-Fa-f]{2}[:-]){5}(?:[0-9A-Fa-f]{2})" 
        ],
        "SECURITY_SECRET": [
            r"ghp_[a-zA-Z0-9]{36}", 
            r"AKIA[0-9A-Z]{16}" 
        ],
        "GOVERNMENT_LEGAL": [
            r"\b[A-Z]{5}[0-9]{4}[A-Z]{1}\b", 
            r"\b\d{4}[\s\-]?\d{4}[\s\-]?\d{4}\b" 
        ]
    }
    
    flagged = []
    for category, regex_list in patterns.items():
        for pattern in regex_list:
            for match in re.finditer(pattern, text_content):
                flagged.append({"text": match.group(), "type": category})
    return flagged

def run_ollama_pii_audit(text_content: str) -> dict:
    """Layer 2: Probabilistic LLM catching (WITH CHUNKING)."""
    
    system_prompt = (
    "You are an elite, zero-tolerance Data Privacy & PII Auditor. "
    "Your objective is the EXHAUSTIVE extraction of every piece of Personally Identifiable Information (PII), "
    "sensitive personal data, and confidential credentials from the provided text.\n\n"
    "You MUST detect and categorize every instance into one of these 8 categories:\n"
    "1. PERSONAL_IDENTIFIER: Individual names, maiden names, family members, spouses, managers, educators.\n"
    "2. DEMOGRAPHIC_VITAL: Date of birth, age, place/city of birth, citizenship, blood group, demographic traits.\n"
    "3. CONTACT_LOCATION: Personal and backup emails, phone numbers, postal addresses, apartment/room numbers.\n"
    "4. GOVERNMENT_LEGAL: Passports, National IDs, Driver's Licenses, Voter IDs, Tax numbers, Student roll numbers.\n"
    "5. FINANCIAL_EMPLOYMENT: Bank names, card providers, credit/debit card numbers, CVVs, account numbers, routing/IFSC codes, salary/income, employer names.\n"
    "6. HEALTH_MEDICAL: Illnesses, allergies, prescriptions/medications, primary doctors, clinic addresses, medical test IDs, health app tokens.\n"
    "7. NETWORK_DEVICE: Wi-Fi SSIDs, router passwords, IP addresses (IPv4/IPv6), MAC addresses.\n"
    "8. SECURITY_SECRET: API keys, access tokens, SSH keys, crypto wallet addresses, hashes, password hints, 2FA codes.\n\n"
    "STRICT EXTRACTION RULES:\n"
    "- ANTI-NORMALIZATION: You MUST extract the EXACT raw string. DO NOT change capitalization. DO NOT fix spelling. DO NOT remove extra spaces. If the text says 'aMit  sHarma', you must extract 'aMit  sHarma' this is the most important rule to follow.\n"
    "- OBFUSCATION & CORRUPTION BYPASS: PII may be corrupted by PDF extraction or typed with Leet Speak (e.g., 'j0hn', '@lice', 'P@ssw0rd', 'A.m.i.t', 'S H A R M A'). You MUST identify and extract these obfuscated values exactly as written.\n"
    "- CONTEXTUAL PII: Extract unconventional formats, such as spelled-out dates ('Fourth of December') or conversational addresses ('42nd and Broadway, apt 3B').\n"
    "- Extract the exact literal VALUE only (e.g., extract 'Apex National Bank', not 'Primary Bank Name: Apex National Bank').\n"
    "- NEVER skip consecutive items (if there are two emails or two phone numbers, extract BOTH).\n"
    "- Include bank and insurance provider names, not just their numbers.\n"
    "- Include dates of birth and geographic birthplaces.\n"
    "- Extract ALL values even if the list is long. Do not summarize or abbreviate."
    )
    # 1. Split text into manageable chunks (~3000 chars)
    # chunk_size = 2000
    # chunks = [text_content[i:i + chunk_size] for i in range(0, len(text_content), chunk_size)]
    # 1. Split text into manageable chunks WITH OVERLAP
    chunk_size = 2000
    overlap = 50  # 50 characters overlap ensures no word/name is chopped in half
    chunks = []
    
    start = 0
    while start < len(text_content):
        end = start + chunk_size
        chunks.append(text_content[start:end])
        start += (chunk_size - overlap) # Move forward, but step back 100 chars
    
    all_flagged_items = []

    # 2. Process each chunk
    for index, chunk in enumerate(chunks):
        print(f"[*] Processing Ollama Chunk {index + 1} of {len(chunks)}...")
        
        
        messages = [
    {"role": "system", "content": system_prompt},
    {
        "role": "user",
        "content": (
            "Text to audit:\n"
            "Profile Summary:\n"
            "Born: 12   may 1995 in boSton, MA. Emails: test1@mail.com, test2@backup.org. "
            "Bank: Chase Bank, Acc: 987654321, Salary: $90,000. Doctor: Dr. Smith, Allergy: Sulfa.\n\n"
            "1. Personal Records\n"
            "- Full Legal Name: jOhn rje doE\n"
            "- Mother Name: aMit  sHa rma\n"
            "- Date of Birth: Fourth of December Two Thousand Three\n"
            "- Place of Birth: Seattle, Washington\n"
            "2. Financial Info\n"
            "- Bank Account Number: 00981020003456\n"
            "3. Corrupted / Obfuscated Data\n"
            "- Alt Email: @lice.sm1th@domain.com\n"
            "- Weird Name: S.u.n.i.t.a\n"
            "- Password Hint: mY  d0g's  n@m3\n"
            "- Drop off package at 42nd and broadway, apt 3B"
        )
    },
    {
        "role": "assistant",
        "content": json.dumps({
            "has_pii": True,
            "flagged_items": [
                {"text": "12   may 1995", "type": "DEMOGRAPHIC_VITAL"},
                {"text": "boSton, MA", "type": "DEMOGRAPHIC_VITAL"},
                {"text": "test1@mail.com", "type": "CONTACT_LOCATION"},
                {"text": "test2@backup.org", "type": "CONTACT_LOCATION"},
                {"text": "Chase Bank", "type": "FINANCIAL_EMPLOYMENT"},
                {"text": "987654321", "type": "FINANCIAL_EMPLOYMENT"},
                {"text": "$90,000", "type": "FINANCIAL_EMPLOYMENT"},
                {"text": "Dr. Smith", "type": "HEALTH_MEDICAL"},
                {"text": "Sulfa", "type": "HEALTH_MEDICAL"},
                {"text": "jOhn rje doE", "type": "PERSONAL_IDENTIFIER"},
                {"text": "aMit  sHa rma", "type": "PERSONAL_IDENTIFIER"},
                {"text": "Fourth of December Two Thousand Three", "type": "DEMOGRAPHIC_VITAL"},
                {"text": "Seattle, Washington", "type": "DEMOGRAPHIC_VITAL"},
                {"text": "00981020003456", "type": "FINANCIAL_EMPLOYMENT"},
                {"text": "@lice.sm1th@domain.com", "type": "CONTACT_LOCATION"},
                {"text": "S.u.n.i.t.a", "type": "PERSONAL_IDENTIFIER"},
                {"text": "mY  d0g's  n@m3", "type": "SECURITY_SECRET"},
                {"text": "42nd and broadway, apt 3B", "type": "CONTACT_LOCATION"}
            ]
        })
    },
    {"role": "user", "content": f"Text to audit:\n{chunk}"}
    ]

        ollama_payload = {
            "model": "llama3.2:3b",
            "messages": messages,
            "format": PIIScanResult.model_json_schema(),
            "stream": False,
            "keep_alive": "5m", # Keep in RAM during the chunking loop
            "options": {
                "temperature": 0.0,
                "num_ctx": 4096
            }
        }

        try:
            res = requests.post("http://localhost:11434/api/chat", json=ollama_payload, timeout=120)
            res.raise_for_status()
            
            raw_result = res.json()["message"]["content"]
            parsed_result = json.loads(raw_result)
            
            if parsed_result.get("has_pii") and parsed_result.get("flagged_items"):
                all_flagged_items.extend(parsed_result["flagged_items"])
                
        except Exception as e:
            print(f"Extraction error on chunk {index + 1}: {e}")

    return {
        "has_pii": len(all_flagged_items) > 0,
        "flagged_items": all_flagged_items
    }

def run_hybrid_pii_audit(text_content: str) -> dict:
    """Layer 3: The Merger. Combines Regex and LLM results."""
    if not text_content.strip():
        return {"has_pii": False, "flagged_items": []}

    # 1. Run Regex Parser
    regex_items = run_regex_pii_audit(text_content)

    # 2. Run LLM Parser (Now handles chunks)
    ollama_result = run_ollama_pii_audit(text_content)
    ollama_items = ollama_result.get("flagged_items", [])

    # 3. Merge and Deduplicate (Fixed logic)
    all_items = regex_items + ollama_items
    
    unique_items = {}
    for item in all_items:
        # Use BOTH text and type to prevent overwriting different entities with the same text
        key = f"{item['text'].strip()}_{item['type']}"
        if key not in unique_items:
            unique_items[key] = item

    final_list = list(unique_items.values())

    # 4. Cleanup Memory AFTER everything is done
    flush_ollama_memory("llama3.2:3b")

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
        # SKELETON: PDF coordinate-based redaction will go here
        # ---> NEW: Extract PDF text page by page
        doc = fitz.open(file_path)
        for page in doc:
            extracted_text.append(page.get_text())
        doc.close()
        

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
        doc = fitz.open(source_path)
        
        for page in doc:
            for rule in replacements:
                # Find the exact X/Y rectangles where the sensitive word appears
                rectangles = page.search_for(rule.original)
                
                for rect in rectangles:
                    # Create a redaction annotation with replacement text
                    page.add_redact_annot(
                        rect, 
                        text=rule.replace_with,  # e.g., "[NAME_1]"
                        fill=(1, 1, 1),          # White background
                        text_color=(0, 0, 0),    # Black text
                        fontsize=10,             # Approximate font size
                        align=1                  # Center align the placeholder
                    )
                    
            # CRITICAL: Surgically removes original text from the file data
            page.apply_redactions()
        doc.save(target_path)
        doc.close()

# ----------------- API ENDPOINTS -----------------
@app.post("/scan")
def scan_text(request: TextScanRequest):
    return run_hybrid_pii_audit(request.text) 

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
    scan_result = run_hybrid_pii_audit(extracted_text) 

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