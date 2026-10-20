import json
import os
import fitz  # PyMuPDF

FOLDER_NAME = "xyxyxy"


def mask_pdf_from_results():
    folder_path = os.path.join(os.path.dirname(__file__), FOLDER_NAME)

    if not os.path.exists(folder_path):
        print(f"[!] Folder '{FOLDER_NAME}' does not exist.")
        return

    result_path = os.path.join(folder_path, "result.txt")
    if not os.path.exists(result_path):
        print(f"[!] 'result.txt' not found inside '{FOLDER_NAME}'.")
        return

    # 1. Load the Groq scan results
    with open(result_path, "r", encoding="utf-8") as f:
        scan_data = json.load(f)

    flagged_items = scan_data.get("flagged_items", [])
    if not flagged_items:
        print("[*] No PII items flagged in result.txt. Nothing to redact.")
        return

    print(
        f"[*] Loaded {len(flagged_items)} flagged PII item(s) from result.txt."
    )

    # 2. Find the PDF file in xyxyxy (skip any existing 'safe_' files)
    pdf_files = [
        f
        for f in os.listdir(folder_path)
        if f.lower().endswith(".pdf") and not f.startswith("safe_")
    ]

    if not pdf_files:
        print(f"[!] No original PDF file found inside '{FOLDER_NAME}'.")
        return

    target_pdf = pdf_files[0]
    input_pdf_path = os.path.join(folder_path, target_pdf)
    output_pdf_path = os.path.join(folder_path, f"safe_{target_pdf}")

    print(f"[*] Redacting '{target_pdf}'...")

    # Sort items by length descending so larger entities are masked before substrings
    flagged_items.sort(key=lambda x: len(x.get("text", "")), reverse=True)

    # 3. Apply PyMuPDF coordinate redactions
    doc = fitz.open(input_pdf_path)

    total_redactions = 0
    for page_idx, page in enumerate(doc):
        for item in flagged_items:
            sensitive_text = item.get("text", "").strip()
            item_type = item.get("type", "PII")

            if not sensitive_text:
                continue

            rectangles = page.search_for(sensitive_text)
            for rect in rectangles:
                page.add_redact_annot(
                    rect,
                    text=f"[{item_type}]",
                    fill=(1, 1, 1),  # White background fill
                    text_color=(0, 0, 0),  # Black text label
                    fontsize=9,
                    align=1,  # Center text
                )
                total_redactions += 1

        page.apply_redactions()

    doc.save(output_pdf_path)
    doc.close()

    print(f"[+] Complete! Applied {total_redactions} redaction(s).")
    print(f"[+] Output PDF saved at: {output_pdf_path}")


if __name__ == "__main__":
    mask_pdf_from_results()