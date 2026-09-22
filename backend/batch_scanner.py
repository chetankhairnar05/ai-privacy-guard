import os
import requests
import json
import time

INPUT_FILE = "prompts.txt"
OUTPUT_FILE = "results_prompt.txt"
API_URL = "http://127.0.0.1:8000/scan"

def run_batch_scan():
    # 1. Check if the file exists
    if not os.path.exists(INPUT_FILE):
        print(f"❌ Error: '{INPUT_FILE}' not found in the current directory.")
        return

    # 2. Read and split the prompts
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        content = f.read()

    # Split by double newline and remove empty whitespace blocks
    prompts = [p.strip() for p in content.split("\n\n") if p.strip()]
    
    total_prompts = len(prompts)
    print(f"🚀 Found {total_prompts} prompts in '{INPUT_FILE}'. Starting batch scan...")

    # 3. Process each prompt and write to the output file
    with open(OUTPUT_FILE, "w", encoding="utf-8") as out_file:
        for idx, prompt in enumerate(prompts, start=1):
            print(f"[*] Processing Prompt {idx}/{total_prompts}...", end=" ")
            
            # Write the header and original text to the results file
            out_file.write(f"==================== PROMPT {idx} ====================\n")
            out_file.write(f"TEXT:\n{prompt}\n\n")
            
            try:
                # Hit your FastAPI backend
                res = requests.post(API_URL, json={"text": prompt}, timeout=45)
                res.raise_for_status()
                data = res.json()
                
                # Write the AI's JSON result beautifully formatted
                out_file.write("EXTRACTION RESULT:\n")
                out_file.write(json.dumps(data, indent=4) + "\n\n")
                print("[SUCCESS]")
                
                # Standard 1.5s hardware cooldown
                time.sleep(1.5)
                
            except requests.exceptions.Timeout:
                print("[TIMEOUT] Prompt hung. Clearing Ollama queue...")
                out_file.write("EXTRACTION RESULT:\n[TIMEOUT] The AI took too long to respond.\n\n")
                
                # Force-cancel Ollama's running task to recover
                try:
                    requests.post("http://localhost:11434/api/generate", json={"model": "llama3.2:3b", "keep_alive": 0}, timeout=5)
                except Exception:
                    pass
                time.sleep(4.0)  # Extended recovery sleep
                
            except Exception as e:
                print(f"[ERROR] {e}")
                out_file.write(f"EXTRACTION RESULT:\n[ERROR] {str(e)}\n\n")
                time.sleep(1.5)

    print(f"\n✅ Batch processing complete! Open '{OUTPUT_FILE}' to review what the AI caught.")

if __name__ == "__main__":
    run_batch_scan()