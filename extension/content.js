let isBypassed = false;
let interceptedFileInput = null;
let currentPendingFile = null;

// 1. INTERCEPT PROMPT TYPING (ENTER KEY)
document.addEventListener(
  "keydown",
  function (event) {
    if (event.key === "Enter" && !event.shiftKey) {
      if (isBypassed) {
        isBypassed = false;
        return;
      }

      const activeEl = document.activeElement;
      if (
        activeEl &&
        (activeEl.tagName === "TEXTAREA" || activeEl.isContentEditable)
      ) {
        const text = activeEl.value || activeEl.innerText;
        if (!text || text.trim() === "") return;

        event.preventDefault();
        event.stopPropagation();
        showPreScanModal(activeEl, text);
      }
    }
  },
  true,
);

// 2. INTERCEPT FILE UPLOADS (INPUT CHANGE)
document.addEventListener(
  "change",
  function (event) {
    const target = event.target;
    if (target && target.tagName === "INPUT" && target.type === "file") {
      if (isBypassed) {
        isBypassed = false;
        return;
      }

      if (target.files && target.files.length > 0) {
        const file = target.files[0];
        const validExts = [".docx", ".pptx", ".pdf"];
        const hasValidExt = validExts.some((ext) =>
          file.name.toLowerCase().endsWith(ext),
        );

        if (hasValidExt) {
          event.preventDefault();
          event.stopImmediatePropagation();
          interceptedFileInput = target;
          currentPendingFile = file;
          showFilePreScanModal(file);
        }
      }
    }
  },
  true,
);

// ----------------- MODALS FOR TEXT -----------------
function showPreScanModal(targetInput, originalText) {
  removeExistingModal();
  const modal = createBaseModal(`
    <h3>🛡️ Privacy Check (Prompt)</h3>
    <p style="font-size: 13px; margin: 5px 0;">Scan this text for personal data using your local model?</p>
    <div class="btn-group">
      <button class="btn-ignore" id="pg-skip">Skip & Send Directly</button>
      <button class="btn-mask" id="pg-scan">Scan Prompt</button>
    </div>
  `);

  document.getElementById("pg-skip").onclick = () => {
    modal.remove();
    isBypassed = true;
    targetInput.dispatchEvent(
      new KeyboardEvent("keydown", { key: "Enter", bubbles: true }),
    );
  };

  document.getElementById("pg-scan").onclick = async () => {
    modal.innerHTML = `<h3 style="color: #0084ff;">Scanning with Local AI...</h3>`;
    try {
      const res = await fetch("http://127.0.0.1:8000/scan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: originalText }),
      });
      const data = await res.json();

      if (data.has_pii && data.flagged_items && data.flagged_items.length > 0) {
        showResultsModal(targetInput, originalText, data.flagged_items);
      } else {
        modal.remove();
        isBypassed = true;
        targetInput.dispatchEvent(
          new KeyboardEvent("keydown", { key: "Enter", bubbles: true }),
        );
      }
    } catch (err) {
      alert("Local AI Server is offline! Run 'python main.py'.");
      modal.remove();
    }
  };
}

function showResultsModal(targetInput, originalText, flaggedItems) {
  const modal = document.getElementById("privacy-guard-modal");
  modal.innerHTML = `
    <h3>⚠️ Private Data Detected!</h3>
    <p style="font-size: 13px; margin: 5px 0;">Found ${flaggedItems.length} sensitive items in your prompt.</p>
    <div class="btn-group">
      <button class="btn-ignore" id="pg-proceed">Process Anyway</button>
      <button class="btn-mask" id="pg-playground">Open in Playground</button>
    </div>
  `;

  document.getElementById("pg-proceed").onclick = () => {
    modal.remove();
    isBypassed = true;
    targetInput.dispatchEvent(
      new KeyboardEvent("keydown", { key: "Enter", bubbles: true }),
    );
  };

  document.getElementById("pg-playground").onclick = () => {
    chrome.storage.local.set(
      {
        privacyPlaygroundData: {
          mode: "text",
          text: originalText,
          items: flaggedItems,
        },
      },
      () => {
        modal.remove();
        window.open(chrome.runtime.getURL("playground.html"), "_blank");
      },
    );
  };
}

// ----------------- MODALS FOR FILES -----------------
function showFilePreScanModal(file) {
  removeExistingModal();
  const modal = createBaseModal(`
    <h3>🛡️ Privacy Check (File)</h3>
    <p style="font-size: 13px; margin: 5px 0;">Detected upload: <strong>${file.name}</strong></p>
    <p style="font-size: 12px; color: #bbb;">Scan document contents with your local model before uploading?</p>
    <div class="btn-group">
      <button class="btn-ignore" id="pg-file-skip">Upload As-Is</button>
      <button class="btn-mask" id="pg-file-scan">Scan File</button>
    </div>
  `);

  document.getElementById("pg-file-skip").onclick = () => {
    modal.remove();
    isBypassed = true;
    // Dispatch original file
    if (interceptedFileInput) {
      interceptedFileInput.dispatchEvent(
        new Event("change", { bubbles: true }),
      );
    }
  };

  document.getElementById("pg-file-scan").onclick = async () => {
    modal.innerHTML = `<h3 style="color: #0084ff;">Extracting & Scanning Document...</h3>`;
    const formData = new FormData();
    formData.append("file", file);

    try {
      const res = await fetch("http://127.0.0.1:8000/scan-file", {
        method: "POST",
        body: formData,
      });
      const data = await res.json();

      if (data.has_pii && data.flagged_items && data.flagged_items.length > 0) {
        showFileResultsModal(data);
      } else {
        alert("No PII found in this document. Safe to upload!");
        modal.remove();
        isBypassed = true;
        if (interceptedFileInput) {
          interceptedFileInput.dispatchEvent(
            new Event("change", { bubbles: true }),
          );
        }
      }
    } catch (err) {
      alert("Error scanning document. Ensure local Python server is running.");
      modal.remove();
    }
  };
}

function showFileResultsModal(scanData) {
  const modal = document.getElementById("privacy-guard-modal");
  modal.innerHTML = `
    <h3>⚠️ Sensitive Data in File!</h3>
    <p style="font-size: 13px; margin: 5px 0;">Found ${scanData.flagged_items.length} sensitive items in <strong>${scanData.filename}</strong>.</p>
    <div class="btn-group">
      <button class="btn-ignore" id="pg-file-proceed">Upload Anyway</button>
      <button class="btn-mask" id="pg-file-playground">Open in Playground</button>
    </div>
  `;

  document.getElementById("pg-file-proceed").onclick = () => {
    modal.remove();
    isBypassed = true;
    if (interceptedFileInput) {
      interceptedFileInput.dispatchEvent(
        new Event("change", { bubbles: true }),
      );
    }
  };

  document.getElementById("pg-file-playground").onclick = () => {
    chrome.storage.local.set(
      {
        privacyPlaygroundData: {
          mode: "file",
          file_id: scanData.file_id,
          filename: scanData.filename,
          extension: scanData.extension,
          preview_text: scanData.preview_text,
          items: scanData.flagged_items,
        },
      },
      () => {
        modal.remove();
        window.open(chrome.runtime.getURL("playground.html"), "_blank");
      },
    );
  };
}

// ----------------- HELPERS -----------------
function removeExistingModal() {
  const existing = document.getElementById("privacy-guard-modal");
  if (existing) existing.remove();
}

function createBaseModal(innerContent) {
  const modal = document.createElement("div");
  modal.id = "privacy-guard-modal";
  modal.innerHTML = innerContent;
  document.body.appendChild(modal);
  return modal;
}
