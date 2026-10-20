import os
import time
import requests
import json
import re

# Configuration
PROMPT_FILE = os.path.join("my_notes", "prompt.txt")
API_URL = "http://127.0.0.1:8000/scan"  # The text scanning endpoint of your backend
WAIT_TIME = 20  # Seconds to wait between API calls

def process_prompts():
    # 1. Check if the prompt file exists
    if not os.path.exists(PROMPT_FILE):
        print(f"[!] Error: Could not find '{PROMPT_FILE}'. Please ensure the 'my_notes' folder exists and contains 'prompt.txt'.")
        return

    # 2. Read the file
    print(f"[*] Reading prompts from {PROMPT_FILE}...")
    with open(PROMPT_FILE, "r", encoding="utf-8") as f:
        content = f.read()

    # 3. Split the text into separate prompts
    # This splits the text wherever there is a blank line (two or more newlines)
    raw_prompts = re.split(r'\n\s*\n', content)
    
    # Clean up whitespace and remove any empty results
    prompts = [p.strip() for p in raw_prompts if p.strip()]

    print(f"[*] Found {len(prompts)} distinct prompt(s). Starting processing...\n")

    # 4. Process each prompt sequentially
    for index, prompt_text in enumerate(prompts, start=1):
        output_filename = f"p{index}.txt"
        print(f"--- Processing Prompt {index} of {len(prompts)} ---")
        
        # Prepare the payload for your FastAPI backend
        payload = {"text": prompt_text}
        
        try:
            # Send the request to main3.py
            response = requests.post(API_URL, json=payload, timeout=120)
            
            # Check if the request was successful
            response.raise_for_status()
            
            # Parse the JSON response
            result_data = response.json()
            
            # IMMEDIATELY save the result to the output file
            with open(output_filename, "w", encoding="utf-8") as out_file:
                json.dump(result_data, out_file, indent=2, ensure_ascii=False)
            
            print(f"[+] Success! Results saved to {output_filename}")
            
        except requests.exceptions.ConnectionError:
            print("[!] Connection Error: Is main3.py running on port 8000?")
            break
        except requests.exceptions.RequestException as e:
            print(f"[!] API Error on prompt {index}: {e}")

        # 5. Wait for 20 seconds (skip waiting if it's the very last prompt)
        if index < len(prompts):
            print(f"[*] Sleeping for {WAIT_TIME} seconds to respect API rate limits...\n")
            time.sleep(WAIT_TIME)
            
    print("\n[+] All prompts processed successfully!")

if __name__ == "__main__":
    process_prompts()