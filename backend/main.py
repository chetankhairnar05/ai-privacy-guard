from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
import requests

app = FastAPI(title="AI Privacy Guard Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ScanRequest(BaseModel):
    text: str

# 1. DEFINE THE STRICT JSON SCHEMA USING PYDANTIC
class FlaggedItem(BaseModel):
    text: str
    type: str

class PIIScanResult(BaseModel):
    has_pii: bool
    flagged_items: List[FlaggedItem]

@app.post("/scan")
def scan_text(request: ScanRequest):
    user_text = request.text.strip()
    if not user_text:
        return {"has_pii": False, "flagged_items": []}

    # 2. THE 3B-OPTIMIZED PROMPT
    # Notice we give explicit rules on extracting hashes, keys, and values-only.
    system_prompt = (
        "You are an expert data privacy auditor. Your task is the exhaustive extraction of ALL Personally Identifiable Information (PII).\n"
        "You must carefully scan the text line-by-line and extract the exact values for the following categories:\n"
        "1. PERSON_NAME (Real names, mother/father/sibling names, principal/teacher names)\n"
        "2. CONTACT (Emails, phone numbers, physical addresses, social media handles)\n"
        "3. FINANCIAL (Credit card numbers, CVV/CVC, bank routing/checking numbers)\n"
        "4. GOVERNMENT_ID (SSN, Passport numbers, Driver's License)\n"
        "5. SECURITY_BIOMETRIC (Passwords, Date of Birth, birth cities, hashes, cryptographic keys, wallet addresses)\n"
        "6. INSTITUTIONAL (School names, university IDs, employer names)\n\n"
        "CRITICAL RULES:\n"
        "- Extract the VALUE ONLY (e.g., extract '000-12-3456', not 'SSN: 000-12-3456').\n"
        "- Do not omit any cryptographic hashes, keys, CVVs, or alphanumeric IDs.\n"
        "- Do not omit family member names or locations.\n"
        "- If a category appears multiple times, extract every single instance."
    )

    # 3. FEW-SHOT EXAMPLES TO CALIBRATE THE MODEL
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "My name is John. Born in Chicago. My CVV is 382. Hash: SHA256:7f83b1a9c2e4"},
        {"role": "assistant", "content": '{"has_pii": true, "flagged_items": [{"text": "John", "type": "PERSON_NAME"}, {"text": "Chicago", "type": "SECURITY_BIOMETRIC"}, {"text": "382", "type": "FINANCIAL"}, {"text": "SHA256:7f83b1a9c2e4", "type": "SECURITY_BIOMETRIC"}]}'},
        {"role": "user", "content": f"Text to audit: {user_text}"}
    ]

    ollama_payload = {
        "model": "llama3.2:3b",
        "messages": messages,
        # 4. ENFORCE THE SCHEMA: This completely prevents JSON parsing errors
        "format": PIIScanResult.model_json_schema(),
        "stream": False,
        "options": {
            "temperature": 0.0 # Strict determinism
        }
    }

    try:
        response = requests.post("http://localhost:11434/api/chat", json=ollama_payload, timeout=60)
        response.raise_for_status()
        
        # Because we used "format", Ollama guarantees the output is a valid JSON string
        # matching our Pydantic model. No markdown stripping required!
        raw_result = response.json()["message"]["content"]
        
        # Convert string back to Python dict to send to browser extension
        import json
        parsed_result = json.loads(raw_result)
        return parsed_result
        
    except Exception as e:
        print(f"Server Error: {str(e)}")
        return {"error": "Failed to connect to local Ollama. Is it running?", "has_pii": False, "flagged_items": []}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)