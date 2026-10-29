# AI Privacy Guard: Local LLM-Powered PII Redaction Engine

AI Privacy Guard is a locally hosted, zero-trust privacy shield designed to intercept, audit, and sanitize sensitive Personal Identifiable Information (PII) before it is transmitted to public Generative AI platforms like ChatGPT, Claude, and Gemini.

It utilizes a Hybrid Auditing Engine (Deterministic Regex + Probabilistic Llama-3.2 LLM) to sanitize raw text and surgically redact complex documents (PDF, DOCX, PPTX) at the byte level.

## 🚀 Features

- **Universal Browser Interception:** Pierces Shadow DOMs and intercepts standard keystrokes, Send buttons, and clipboard events.
- **Hybrid Auditing Engine:** Merges strict Regex patterns with a local 3B parameter LLM for contextual and obfuscated PII extraction.
- **Multi-Format Redaction:** Lossless string replacement for DOCX/PPTX, and surgical byte-level coordinate redaction for PDFs.
- **100% Local Processing:** Ensures zero data leakage by running all inferences locally on your hardware.
- **Automated CI/CD Testing Suite:** Evaluates extraction recall accuracy using adversarial test payloads.

## 🛠️ Tech Stack

- **Frontend:** JavaScript (Manifest V3), HTML, CSS
- **Backend:** Python, FastAPI, Uvicorn
- **AI/LLM Engine:** Ollama, Llama-3.2 (3B parameters)
- **Document Processing:** PyMuPDF (`fitz`), `python-docx`, `python-pptx`
- **Testing:** Custom Python evaluation scripts, `fpdf`, `requests`

---

## ⚙️ Prerequisites

Before running the project, ensure you have the following installed:

1. **Python 3.8+**
2. **Ollama:** [Download and install Ollama](https://ollama.com/)
3. **Llama-3.2 (3B):** Open your terminal and run:
   ```bash
   ollama run llama3.2:3b
   ```
   _(Ensure the model downloads successfully and can run locally before proceeding)._

---

## 💻 Installation & Setup

### 1. Backend Setup (FastAPI & AI Engine)

1. Clone the repository and navigate to the backend folder:
   ```bash
   cd ai-privacy-guard/backend
   ```
2. Create a virtual environment (recommended):
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows use: venv\Scripts\activate
   ```
3. Install the required Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Start the FastAPI server:
   ```bash
   python main.py
   ```
   _The server will start on `http://127.0.0.1:8000`._

### 2. Browser Extension Setup (Chrome / Brave / Edge)

1. Open your browser and navigate to the extensions page:
   - Chrome/Brave: `chrome://extensions/`
   - Edge: `edge://extensions/`
2. Enable **"Developer mode"** in the top-right or bottom-left corner.
3. Click **"Load unpacked"**.
4. Select the `extension` folder from this project directory.
5. The extension is now active. Refresh any open tabs of ChatGPT, Claude, or Gemini to initialize the content scripts.

### 2.1 Firefox Setup (Optional)

1. Navigate to `about:debugging#/runtime/this-firefox`.
2. Click **"Load Temporary Add-on"**.
3. Navigate inside the extension folder and select the `manifest.json` file.

---

## 🧪 Running the Automated Test Suite

The project includes an adversarial testing pipeline to benchmark the Hybrid Engine's recall accuracy. Ensure the backend server (`main.py`) is running before executing tests.

### 1. Batch Scanning

To run bulk inferences on raw prompts and measure hardware thermal stability:

1. Place your test prompts inside `prompts.txt` (separated by double newlines).
2. Run the scanner:
   ```bash
   python batch_scanner.py
   ```
   _Results will be logged to `results_prompt.txt`._

### 2. Generating Evaluation Reports

To evaluate the AI's extraction accuracy against a ground-truth JSON and generate a formal PDF Test Matrix:

1. Ensure `target_prompts.json` and `results_prompt.txt` are in the backend directory.
2. Run the report generator:
   ```bash
   python generate_reports.py
   ```
   _The script will output `Project_Test_Results.csv` and `Project_Test_Matrix_Report.pdf`._

---

## 📂 Project Structure

```text
ai-privacy-guard/
│
├── backend/
│   ├── main.py                  # FastAPI server & Hybrid Engine logic
│   ├── batch_scanner.py         # Automated API injection script
│   ├── generate_reports.py      # PDF & CSV Test Matrix generator
│   ├── prompts.txt              # Raw test payloads
│   ├── target_prompts.json      # Ground truth for test evaluation
│   └── uploads_temp/            # Temporary directory for file redaction
│
└── extension/
    ├── manifest.json            # Manifest V3 configuration
    ├── content.js               # Shadow DOM piercing & prompt interception
    ├── style.css                # Extension UI styling
    └── playground.html          # Local dashboard for PII review
```
