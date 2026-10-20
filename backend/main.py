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
import csv
import openpyxl
import uvicorn



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
        "CONTACT": [
            r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", 
            r"(?:\+?\d{1,3}[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}" 
        ],
        "NETWORK": [
            r"\b(?:\d{1,3}\.){3}\d{1,3}\b", 
            r"(?:[0-9A-Fa-f]{2}[:-]){5}(?:[0-9A-Fa-f]{2})" 
        ],
        "SECURITY": [
            r"ghp_[a-zA-Z0-9]{36}", 
            r"AKIA[0-9A-Z]{16}" 
        ],
        "GOVERNMENT": [
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
    "1. PERSONAL: Individual names, maiden names, family members, spouses, managers, educators.\n"
    "2. DEMOGRAPHIC: Date of birth, age, place/city of birth, citizenship, blood group, demographic traits.\n"
    "3. CONTACT: Personal and backup emails, phone numbers, postal addresses, apartment/room numbers.\n"
    "4. GOVERNMENT: Passports, National IDs, Driver's Licenses, Voter IDs, Tax numbers, Student roll numbers.\n"
    "5. FINANCIAL: Bank names, card providers, credit/debit card numbers, CVVs, account numbers, routing/IFSC codes, salary/income, employer names.\n"
    "6. HEALTH: Illnesses, allergies, prescriptions/medications, primary doctors, clinic addresses, medical test IDs, health app tokens.\n"
    "7. NETWORK: Wi-Fi SSIDs, router passwords, IP addresses (IPv4/IPv6), MAC addresses.\n"
    "8. SECURITY: API keys, access tokens, SSH keys, crypto wallet addresses, hashes, password hints, 2FA codes.\n\n"
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
    chunk_size = 1300
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
                {"text": "12   may 1995", "type": "DEMOGRAPHIC"},
                {"text": "boSton, MA", "type": "DEMOGRAPHIC"},
                {"text": "test1@mail.com", "type": "CONTACT"},
                {"text": "test2@backup.org", "type": "CONTACT"},
                {"text": "Chase Bank", "type": "FINANCIAL"},
                {"text": "987654321", "type": "FINANCIAL"},
                {"text": "$90,000", "type": "FINANCIAL"},
                {"text": "Dr. Smith", "type": "HEALTH"},
                {"text": "Sulfa", "type": "HEALTH"},
                {"text": "jOhn rje doE", "type": "PERSONAL"},
                {"text": "aMit  sHa rma", "type": "PERSONAL"},
                {"text": "Fourth of December Two Thousand Three", "type": "DEMOGRAPHIC"},
                {"text": "Seattle, Washington", "type": "DEMOGRAPHIC"},
                {"text": "00981020003456", "type": "FINANCIAL"},
                {"text": "@lice.sm1th@domain.com", "type": "CONTACT"},
                {"text": "S.u.n.i.t.a", "type": "PERSONAL"},
                {"text": "mY  d0g's  n@m3", "type": "SECURITY"},
                {"text": "42nd and broadway, apt 3B", "type": "CONTACT"}
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
                "num_predict": 2500,
                "num_ctx": 4096
            }
        }

        

        try:
            res = requests.post("http://localhost:11434/api/chat", json=ollama_payload, timeout=120)
            res.raise_for_status()
            
            raw_result = res.json()["message"]["content"].strip()

            # Safety Check: Remove markdown formatting
            if "```json" in raw_result:
                raw_result = raw_result.split("```json")[1].split("```")[0].strip()
            elif "```" in raw_result:
                raw_result = raw_result.split("```")[1].strip()
            
            # Attempt to parse JSON normally
            try:
                parsed_result = json.loads(raw_result)
            except json.JSONDecodeError:
                # LLM JSON Rescue: If the LLM forgets a quote or bracket, use Regex to force extract it
                print(f"[*] JSON Error on chunk {index + 1}. Utilizing Regex Rescue...")
                
                matches = re.findall(r'"text":\s*"([^"]+)",\s*"type":\s*"([^"]+)"', raw_result)
                parsed_result = {
                    "has_pii": len(matches) > 0,
                    "flagged_items": [{"text": m[0].replace("\\", ""), "type": m[1]} for m in matches]
                }
            
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
    # CRITICAL FIX: Sort by length descending (longest strings first)
    # This ensures "John Doe" is masked before "John", preventing broken partial masks.
    final_list.sort(key=lambda x: len(x['text']), reverse=True)

    # 4. Cleanup Memory AFTER everything is done
    # flush_ollama_memory("llama3.2:3b")

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

    # ---------- NEW CODE TO PASTE HERE ----------
    elif ext == ".txt":
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            extracted_text.append(f.read())
            
    elif ext == ".csv":
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            reader = csv.reader(f)
            for row in reader:
                # extracted_text.extend([str(cell) for cell in row if cell])
                # CRITICAL FIX: Join cells with commas so the LLM reads it naturally
                row_text = ", ".join([str(cell).strip() for cell in row if str(cell).strip()])
                if row_text:
                    extracted_text.append(row_text)
                
    elif ext == ".xlsx":
        wb = openpyxl.load_workbook(file_path, data_only=True)
        for sheet in wb.worksheets:
            for row in sheet.iter_rows(values_only=True):
                for cell in row:
                    if cell is not None:
                        extracted_text.append(str(cell))
    # --------------------------------------------

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

    # ---------- NEW CODE TO PASTE HERE ----------
    elif ext == ".txt":
        with open(source_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        for rule in replacements:
            content = content.replace(rule.original, rule.replace_with)
        with open(target_path, "w", encoding="utf-8") as f:
            f.write(content)

    elif ext == ".csv":
        with open(source_path, "r", encoding="utf-8", errors="ignore") as f_in, \
             open(target_path, "w", encoding="utf-8", newline="") as f_out:
            reader = csv.reader(f_in)
            writer = csv.writer(f_out)
            for row in reader:
                new_row = []
                for cell in row:
                    cell_str = str(cell)
                    for rule in replacements:
                        cell_str = cell_str.replace(rule.original, rule.replace_with)
                    new_row.append(cell_str)
                writer.writerow(new_row)

    elif ext == ".xlsx":
        wb = openpyxl.load_workbook(source_path)
        for sheet in wb.worksheets:
            for row in sheet.iter_rows():
                for cell in row:
                    if cell.value and isinstance(cell.value, str):
                        for rule in replacements:
                            if rule.original in cell.value:
                                cell.value = cell.value.replace(rule.original, rule.replace_with)
        wb.save(target_path)
    # --------------------------------------------

# ----------------- API ENDPOINTS -----------------
@app.post("/scan")
def scan_text(request: TextScanRequest):
    return run_hybrid_pii_audit(request.text) 

@app.post("/scan-file")
async def scan_file(file: UploadFile = File(...)):
    filename = file.filename
    ext = os.path.splitext(filename)[1].lower()

    # --- REPLACE THIS LINE ---
    if ext not in [".docx", ".pptx", ".pdf", ".txt", ".csv", ".xlsx"]:
        raise HTTPException(status_code=400, detail="Only .docx, .pptx, .pdf, .txt, .csv, .xlsx are supported.")

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
    
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)