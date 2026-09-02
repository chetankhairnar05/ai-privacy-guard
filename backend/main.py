from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import requests
import json

app = FastAPI(title="AI Privacy Guard Backend")

# Enable CORS so your browser extension can communicate with localhost:8000
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ScanRequest(BaseModel):
    text: str

@app.post("/scan")
def scan_text(request: ScanRequest):
    user_text = request.text.strip()
    if not user_text:
        return {"has_pii": False, "flagged_items": []}

    system_prompt = (
        "You are an expert privacy auditor. Analyze the following text strictly for sensitive Personally Identifiable Information (PII), "
        "such as real names, mother/father names, school/college names, personal phone numbers, addresses, and personal emails.\n"
        "Return ONLY a JSON object with this exact schema:\n"
        "{\n"
        '  "has_pii": true,\n'
        '  "flagged_items": [\n'
        '    {"text": "identified word or phrase", "type": "NAME|SCHOOL|EMAIL|PHONE|FAMILY_MEMBER"}\n'
        "  ]\n"
        "}\n"
        "If no sensitive personal information is present, set has_pii to false and flagged_items to []."
    )

    ollama_payload = {
        "model": "llama3.2:3b",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Text to audit: {user_text}"}
        ],
        "format": "json",
        "stream": False
    }

    try:
        response = requests.post("http://localhost:11434/api/chat", json=ollama_payload, timeout=60)
        response.raise_for_status()
        raw_result = response.json()["message"]["content"].strip()
        
        # FIX: Clean up the model output if it hallucinated markdown tags
        if raw_result.startswith("```json"):
            raw_result = raw_result[7:]
        if raw_result.startswith("```"):
            raw_result = raw_result[3:]
        if raw_result.endswith("```"):
            raw_result = raw_result[:-3]
            
        raw_result = raw_result.strip()
        
        parsed_result = json.loads(raw_result)
        return parsed_result
        
    except json.JSONDecodeError as e:
        print(f"JSON ERROR! Raw model output was: {raw_result}")
        return {"error": "LLM returned invalid JSON. Check backend terminal.", "has_pii": False, "flagged_items": []}
    except Exception as e:
        return {"error": f"Failed to connect: {str(e)}", "has_pii": False, "flagged_items": []}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)