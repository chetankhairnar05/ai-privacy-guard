let isBypassed = false;
let interceptedFileInput = null;
let pendingSendAction = null;

// ----------------- DOM HELPERS FOR CROSS-PLATFORM -----------------

function getPromptElement() {
  return (
    document.querySelector("#prompt-textarea") || // ChatGPT
    document.querySelector("rich-textarea") || // Gemini (Shadow Host)
    document.querySelector('div[contenteditable="true"].ProseMirror') || // Claude
    document.querySelector('div[contenteditable="true"]') || // Fallback
    document.querySelector("textarea")
  ); // Fallback
}

function getActiveText(element) {
  if (!element) return "";
  if (element.tagName === "TEXTAREA" || element.tagName === "INPUT") {
    return element.value;
  }
  return element.innerText || element.textContent || "";
}

function isSendButton(target) {
  const path = target.composedPath ? target.composedPath() : [target];
  for (let el of path) {
    if (el && el.tagName === "BUTTON") {
      const aria = (el.getAttribute("aria-label") || "").toLowerCase();
      const testid = (el.getAttribute("data-testid") || "").toLowerCase();

      if (
        (testid.includes("send") ||
          aria.includes("send") ||
          aria.includes("message")) &&
        !aria.includes("attach") &&
        !aria.includes("upload") &&
        !aria.includes("voice") &&
        !aria.includes("mic")
      ) {
        return el;
      }
    }
  }
  return null;
}

// ----------------- 1. INTERCEPT PROMPT TYPING (ENTER KEY) -----------------
document.addEventListener(
  "keydown",
  function (event) {
    if (event.key === "Enter" && !event.shiftKey) {
      if (isBypassed) {
        isBypassed = false;
        return;
      }

      const activeEl = event.composedPath()[0];
      const text = getActiveText(activeEl);

      if (text.trim().length > 0) {
        event.preventDefault();
        event.stopImmediatePropagation();

        pendingSendAction = () => {
          isBypassed = true;
          activeEl.dispatchEvent(
            new KeyboardEvent("keydown", {
              key: "Enter",
              code: "Enter",
              bubbles: true,
              composed: true,
            }),
          );
        };

        showPreScanModal(activeEl, text.trim());
      }
    }
  },
  true,
);

// ----------------- 2. INTERCEPT SEND BUTTON CLICKS -----------------
document.addEventListener(
  "click",
  function (event) {
    if (isBypassed) {
      isBypassed = false;
      return;
    }

    const sendBtn = isSendButton(event.target);
    if (sendBtn) {
      const activeEl = getPromptElement();
      const text = getActiveText(activeEl);

      if (text.trim().length > 0) {
        event.preventDefault();
        event.stopImmediatePropagation();

        pendingSendAction = () => {
          isBypassed = true;
          sendBtn.click();
        };

        showPreScanModal(activeEl, text.trim());
      }
    }
  },
  true,
);

// ----------------- 3. INTERCEPT FILE UPLOADS (BUTTON / INPUT) -----------------
document.addEventListener(
  "change",
  function (event) {
    // CRITICAL FIX: Use composedPath()[0] to pierce Gemini's Shadow DOM
    const target = event.composedPath ? event.composedPath()[0] : event.target;

    if (target && target.tagName === "INPUT" && target.type === "file") {
      if (isBypassed) {
        isBypassed = false;
        return;
      }

      if (target.files && target.files.length > 0) {
        const file = target.files[0];
        const validExts = [".docx", ".pptx", ".pdf", ".txt", ".csv", ".xlsx"];

        if (validExts.some((ext) => file.name.toLowerCase().endsWith(ext))) {
          event.preventDefault();
          event.stopImmediatePropagation();

          interceptedFileInput = target;
          showFilePreScanModal(file);
        }
      }
    }
  },
  true,
);

// ----------------- 4. INTERCEPT CLIPBOARD PASTING (CTRL+V FILES) -----------------
document.addEventListener(
  "paste",
  function (event) {
    if (isBypassed) {
      isBypassed = false;
      return;
    }

    if (
      event.clipboardData &&
      event.clipboardData.files &&
      event.clipboardData.files.length > 0
    ) {
      const file = event.clipboardData.files[0];
      const validExts = [".docx", ".pptx", ".pdf", ".txt", ".csv", ".xlsx"];

      if (validExts.some((ext) => file.name.toLowerCase().endsWith(ext))) {
        event.preventDefault();
        event.stopImmediatePropagation();

        interceptedFileInput = null; // It's a paste, so there is no hidden input
        showFilePreScanModal(file);
      }
    }
  },
  true,
);

// ----------------- MODALS -----------------
// (Prompt Modals)
function showPreScanModal(targetInput, originalText) {
  removeExistingModal();
  const modal = createBaseModal(`
    <h3>🛡️ Privacy Check (Prompt)</h3>
    <p style="font-size: 13px; margin: 5px 0;">Scan this prompt for personal data locally before sending?</p>
    <div class="btn-group">
      <button class="btn-ignore" id="pg-skip">Skip & Send</button>
      <button class="btn-mask" id="pg-scan">Scan Prompt</button>
    </div>
  `);

  document.getElementById("pg-skip").onclick = () => {
    modal.remove();
    if (pendingSendAction) pendingSendAction();
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
        if (pendingSendAction) pendingSendAction();
      }
    } catch (err) {
      alert(
        "Local AI Server is offline! Make sure 'python main.py' is running.",
      );
      modal.remove();
    }
  };
}

function showResultsModal(targetInput, originalText, flaggedItems) {
  const modal = document.getElementById("privacy-guard-modal");
  modal.innerHTML = `
    <h3>⚠️ Private Data Detected!</h3>
    <p style="font-size: 13px; margin: 5px 0;">Found ${flaggedItems.length} sensitive items.</p>
    <div class="btn-group">
      <button class="btn-ignore" id="pg-proceed">Send Anyway</button>
      <button class="btn-mask" id="pg-playground">Open in Playground</button>
    </div>
  `;

  document.getElementById("pg-proceed").onclick = () => {
    modal.remove();
    if (pendingSendAction) pendingSendAction();
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

// (File Modals)
function showFilePreScanModal(file) {
  removeExistingModal();
  const modal = createBaseModal(`
    <h3>🛡️ Privacy Check (File)</h3>
    <p style="font-size: 13px; margin: 5px 0;">Detected upload: <strong>${file.name}</strong></p>
    <div class="btn-group">
      <button class="btn-ignore" id="pg-file-skip">Upload As-Is</button>
      <button class="btn-mask" id="pg-file-scan">Scan File</button>
    </div>
  `);

  document.getElementById("pg-file-skip").onclick = () => {
    modal.remove();
    resumeFileUpload(file);
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
        showFileResultsModal(data, file);
      } else {
        alert("No PII found in this document. Safe to upload!");
        modal.remove();
        resumeFileUpload(file);
      }
    } catch (err) {
      alert("Error scanning document. Ensure local Python server is running.");
      modal.remove();
    }
  };
}

function showFileResultsModal(scanData, originalFile) {
  const modal = document.getElementById("privacy-guard-modal");

  modal.innerHTML = `
    <h3>⚠️ Sensitive Data in File!</h3>
    <p style="font-size: 13px; margin: 5px 0;">Found ${scanData.flagged_items.length} items in <strong>${scanData.filename}</strong>.</p>
    <div class="btn-group">
      <button class="btn-ignore" id="pg-file-proceed">Upload Anyway</button>
      <button class="btn-mask" id="pg-file-playground">Open in Playground</button>
    </div>
  `;

  document.getElementById("pg-file-proceed").onclick = () => {
    modal.remove();
    resumeFileUpload(originalFile);
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

// ----------------- THE ULTIMATE FILE UPLOAD RESUMER -----------------
function resumeFileUpload(file) {
  isBypassed = true;

  const dataTransfer = new DataTransfer();
  dataTransfer.items.add(file);

  // Strategy 1: Inject into the exact input element we caught earlier
  // We check if it is still connected to the DOM (hasn't been destroyed by React/Lit)
  if (interceptedFileInput && interceptedFileInput.isConnected) {
    interceptedFileInput.files = dataTransfer.files;

    // composed: true ensures the event escapes Gemini's Shadow DOM
    interceptedFileInput.dispatchEvent(
      new Event("input", { bubbles: true, composed: true }),
    );
    interceptedFileInput.dispatchEvent(
      new Event("change", { bubbles: true, composed: true }),
    );
    return;
  }

  // Strategy 2: The Synthetic Paste Fallback (Crucial for Gemini & Paste events)
  // If the input was destroyed, or if the user used Ctrl+V, we simulate a Paste Event
  const pasteEvent = new ClipboardEvent("paste", {
    clipboardData: dataTransfer,
    bubbles: true,
    composed: true,
    cancelable: true,
  });

  // Target the prompt text box to paste the file into
  const targetEl = getPromptElement() || document.body;
  targetEl.dispatchEvent(pasteEvent);
}

// ----------------- UTILS -----------------
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
