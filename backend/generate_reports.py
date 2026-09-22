import json
import csv
import re
from fpdf import FPDF
from datetime import datetime

TARGET_JSON_FILE = "target_prompts.json"
RESULTS_TXT_FILE = "results_prompt.txt"

def parse_results_file(filepath):
    """Parses the raw results_prompt.txt file and extracts the JSON outputs in order."""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Split the file by the "==================== PROMPT X ====================" header
    blocks = re.split(r'==================== PROMPT \d+ ====================', content)
    
    extracted_counts = []
    
    for block in blocks:
        if not block.strip():
            continue
            
        # Try to find the JSON block under "EXTRACTION RESULT:"
        if "EXTRACTION RESULT:" in block:
            try:
                json_part = block.split("EXTRACTION RESULT:")[1].strip()
                # If there was a timeout or error, this will safely fail the JSON parse
                parsed_json = json.loads(json_part)
                
                flagged = parsed_json.get("flagged_items", [])
                extracted_counts.append(len(flagged))
            except json.JSONDecodeError:
                # Happens if the AI timed out or threw an error message instead of JSON
                extracted_counts.append(0)
        else:
            extracted_counts.append(0)
            
    return extracted_counts

def generate_evaluation():
    print(f"🚀 Loading Ground Truth from '{TARGET_JSON_FILE}'...")
    with open(TARGET_JSON_FILE, 'r', encoding='utf-8') as f:
        targets = json.load(f)
        
    print(f"🚀 Loading Extracted Results from '{RESULTS_TXT_FILE}'...")
    extracted_counts = parse_results_file(RESULTS_TXT_FILE)
    
    if len(targets) != len(extracted_counts):
        print(f"⚠️ WARNING: The number of prompts in JSON ({len(targets)}) does not match the TXT results ({len(extracted_counts)}).")
        print("Proceeding anyway, but aligning up to the shortest list length.")

    results = []
    
    for i in range(min(len(targets), len(extracted_counts))):
        target = targets[i]
        expected_count = target.get("number_of_p2", 0)
        caught_count = extracted_counts[i]
        
        # Calculate Accuracy logic based on your exact formula
        if expected_count == 0:
            accuracy = 100.0  # Prevent divide-by-zero
        else:
            accuracy = (caught_count / expected_count) * 100.0
            
        # Cap at 100% (so if it caught 12 but expected 10, it doesn't say 120%)
        if accuracy > 100.0:
            accuracy = 100.0
            
        if accuracy == 100.0:
            status = "PASS"
        elif accuracy > 0.0:
            status = "PARTIAL"
        else:
            status = "FAIL"
            
        # Create a small snippet of the prompt text for the report
        # prompt_snippet = target["prompt"][:60].replace('\n', ' ') + "..."
        # Create a small snippet of the prompt text for the report
        prompt_snippet = target["prompt"][:60].replace('\n', ' ') + "..."
        
        # FIX: FPDF Unicode crash. Replace smart quotes and strip unsupported characters
        prompt_snippet = prompt_snippet.replace('’', "'").replace('‘', "'").replace('“', '"').replace('”', '"')
        prompt_snippet = prompt_snippet.replace('₹', 'Rs.')
        prompt_snippet = prompt_snippet.encode('latin-1', 'ignore').decode('latin-1')
        
        results.append({
            "Test_ID": f"TC_{i+1:03d}",
            "Prompt_Snippet": prompt_snippet,
            "Expected": expected_count,
            "Caught": caught_count,
            "Accuracy": accuracy,
            "Status": status
        })
        
    return results

def generate_reports(results):
    print("\n📊 Generating Final Reports (PDF & CSV)...")
    
    total_tests = len(results)
    full_passes = sum(1 for r in results if r["Status"] == "PASS")
    partials = sum(1 for r in results if r["Status"] == "PARTIAL")
    fails = sum(1 for r in results if r["Status"] == "FAIL")
    
    avg_score = sum(r["Accuracy"] for r in results) / total_tests if total_tests > 0 else 0

    # ----- 1. GENERATE CSV REPORT -----
    csv_report_path = "Project_Test_Results.csv"
    with open(csv_report_path, mode='w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=["Test_ID", "Prompt_Snippet", "Expected", "Caught", "Accuracy", "Status"])
        writer.writeheader()
        writer.writerows(results)

    # ----- 2. GENERATE PDF REPORT -----
    pdf = FPDF(orientation='L', unit='mm', format='A4')
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    
    pdf.cell(0, 10, txt="AI Privacy Guard - Model Extraction Evaluation Matrix", ln=True, align='C')
    pdf.set_font("Arial", size=10)
    pdf.cell(0, 10, txt=f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", ln=True, align='C')
    pdf.ln(5)
    
    # Summary Stats
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 8, txt=f"Total Tests: {total_tests} | Full Pass: {full_passes} | Partial: {partials} | Fail: {fails}", ln=True)
    
    if avg_score >= 85:
        pdf.set_text_color(0, 128, 0) # Green
    elif avg_score >= 60:
        pdf.set_text_color(204, 102, 0) # Orange
    else:
        pdf.set_text_color(200, 0, 0) # Red
        
    pdf.cell(0, 10, txt=f"Overall Extraction Accuracy: {avg_score:.1f}%", ln=True)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(5)
    
    # Table Header
    pdf.set_font("Arial", 'B', 10)
    col_widths = [25, 150, 25, 25, 25, 25]
    headers = ["Test ID", "Prompt Snippet", "Expected", "Caught", "Accuracy", "Status"]
    
    for i, header in enumerate(headers):
        pdf.cell(col_widths[i], 10, header, border=1, align='C')
    pdf.ln()
    
    # Table Rows
    pdf.set_font("Arial", size=9)
    for res in results:
        pdf.cell(col_widths[0], 10, res["Test_ID"], border=1, align='C')
        pdf.cell(col_widths[1], 10, res["Prompt_Snippet"], border=1)
        pdf.cell(col_widths[2], 10, str(res["Expected"]), border=1, align='C')
        pdf.cell(col_widths[3], 10, str(res["Caught"]), border=1, align='C')
        pdf.cell(col_widths[4], 10, f"{res['Accuracy']:.0f}%", border=1, align='C')
        
        # Color code status
        if res["Status"] == "PASS":
            pdf.set_text_color(0, 128, 0)
        elif res["Status"] == "PARTIAL":
            pdf.set_text_color(204, 102, 0)
        else:
            pdf.set_text_color(200, 0, 0)
            
        pdf.cell(col_widths[5], 10, res["Status"], border=1, align='C')
        pdf.set_text_color(0, 0, 0)
        pdf.ln()
        
    pdf_report_path = "Project_Test_Matrix_Report.pdf"
    pdf.output(pdf_report_path)
    print(f"✅ Success! Reports saved as:\n - {pdf_report_path}\n - {csv_report_path}")

if __name__ == "__main__":
    evaluation_results = generate_evaluation()
    generate_reports(evaluation_results)