let isBypassed = false;
let interceptedFileInput = null;
let pendingActiveEl = null;
let pendingOriginalSendBtn = null;

// ----------------- DOM HELPERS FOR CROSS-PLATFORM -----------------

function getPromptElement() {
  // 1. Common specific selectors
  let el =
    document.querySelector("#prompt-textarea") ||
    document.querySelector("rich-textarea") ||
    document.querySelector('div[contenteditable="true"].ProseMirror') ||
    document.querySelector('textarea[data-testid="chat-input"]') ||
    document.querySelector("textarea") ||
    document.querySelector('div[contenteditable="true"]');

  if (el) return el;

  // 2. Deep Shadow DOM Piercer (Crucial for Microsoft Copilot)
  function searchShadowRoots(node) {
    if (node.shadowRoot) {
      const ta =
        node.shadowRoot.querySelector("textarea") ||
        node.shadowRoot.querySelector('div[contenteditable="true"]');
      if (ta) return ta;
      for (const child of node.shadowRoot.querySelectorAll("*")) {
        const found = searchShadowRoots(child);
        if (found) return found;
      }
    }
    return null;
  }

  for (const node of document.querySelectorAll("*")) {
    const found = searchShadowRoots(node);
    if (found) return found;
  }

  // 3. Absolute fallback
  return document.querySelector("input[type='text']");
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
    if (
      el &&
      (el.tagName === "BUTTON" ||
        el.tagName === "DIV" ||
        el.tagName === "SPAN" ||
        el.tagName === "SVG")
    ) {
      const aria = (el.getAttribute("aria-label") || "").toLowerCase();
      const testid = (el.getAttribute("data-testid") || "").toLowerCase();
      const title = (el.getAttribute("title") || "").toLowerCase();

      const isSendIntent =
        testid.includes("send") ||
        aria.includes("send") ||
        aria.includes("message") ||
        aria.includes("submit") ||
        title.includes("send") ||
        title.includes("submit") ||
        el.type === "submit";

      const isNotMediaIntent =
        !aria.includes("attach") &&
        !aria.includes("upload") &&
        !aria.includes("voice") &&
        !aria.includes("mic");

      if (isSendIntent && isNotMediaIntent) {
        return el.tagName === "BUTTON" ? el : el.closest("button") || el;
      }
    }
  }
  return null;
}

function getSendButtonFromDOM() {
  const possibleButtons = document.querySelectorAll(
    "button, div[role='button'], svg, span",
  );
  for (let el of possibleButtons) {
    const aria = (el.getAttribute("aria-label") || "").toLowerCase();
    const testid = (el.getAttribute("data-testid") || "").toLowerCase();
    const title = (el.getAttribute("title") || "").toLowerCase();

    const isSendIntent =
      testid.includes("send") ||
      aria.includes("send") ||
      aria.includes("message") ||
      aria.includes("submit") ||
      title.includes("send") ||
      title.includes("submit");
    const isNotMediaIntent =
      !aria.includes("attach") &&
      !aria.includes("upload") &&
      !aria.includes("voice") &&
      !aria.includes("mic");

    if (isSendIntent && isNotMediaIntent) {
      return el.tagName === "BUTTON" ? el : el.closest("button") || el;
    }
  }
  return null;
}

// ----------------- 1. INTERCEPT PROMPT TYPING (ENTER KEY) -----------------
document.addEventListener(
  "keydown",
  function (event) {
    if (isBypassed) {
      isBypassed = false;
      return;
    }

    if (event.key === "Enter" && !event.shiftKey) {
      const activeEl = event.composedPath()[0];

      // CRITICAL FIX: Ignore if the user is typing/interacting inside our own modal
      if (
        activeEl &&
        activeEl.closest &&
        activeEl.closest("#privacy-guard-modal")
      ) {
        return;
      }

      const text = getActiveText(activeEl);

      if (text.trim().length > 0) {
        event.preventDefault();
        event.stopPropagation();
        event.stopImmediatePropagation();

        pendingActiveEl = activeEl;
        pendingOriginalSendBtn = null;

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

    const target = event.composedPath ? event.composedPath()[0] : event.target;

    // CRITICAL FIX: Ignore clicks inside our own modal so buttons aren't dead
    if (target && target.closest && target.closest("#privacy-guard-modal")) {
      return;
    }

    const sendBtn = isSendButton(target);
    if (sendBtn) {
      const activeEl = getPromptElement();
      const text = getActiveText(activeEl);

      if (text.trim().length > 0) {
        event.preventDefault();
        event.stopPropagation();
        event.stopImmediatePropagation();

        pendingActiveEl = activeEl;
        pendingOriginalSendBtn = sendBtn;

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

    // Allow pasting text normally
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

        interceptedFileInput = null; // Paste means no input element
        showFilePreScanModal(file);
      }
    }
  },
  true,
);

// ----------------- THE ULTIMATE PROMPT RESUMER -----------------
function resumePromptSubmission(activeEl, originalSendBtn) {
  isBypassed = true;

  if (activeEl) {
    if (typeof activeEl.focus === "function") activeEl.focus();

    // Wake up React/NextJS
    activeEl.dispatchEvent(
      new Event("input", { bubbles: true, composed: true }),
    );
    activeEl.dispatchEvent(
      new Event("change", { bubbles: true, composed: true }),
    );
  }

  setTimeout(() => {
    // 1. Try original button
    if (
      originalSendBtn &&
      !originalSendBtn.disabled &&
      typeof originalSendBtn.click === "function"
    ) {
      originalSendBtn.click();
      return;
    }

    // 2. Try dynamic button
    const dynamicSendBtn = getSendButtonFromDOM();
    if (
      dynamicSendBtn &&
      !dynamicSendBtn.disabled &&
      typeof dynamicSendBtn.click === "function"
    ) {
      dynamicSendBtn.click();
      return;
    }

    // 3. Fallback to synthetic Enter
    if (activeEl) {
      activeEl.dispatchEvent(
        new KeyboardEvent("keydown", {
          key: "Enter",
          code: "Enter",
          keyCode: 13,
          which: 13,
          bubbles: true,
          cancelable: true,
          composed: true,
        }),
      );
    }
  }, 20);
}

// ----------------- THE ULTIMATE FILE UPLOAD RESUMER -----------------
function resumeFileUpload(file) {
  isBypassed = true;

  const dataTransfer = new DataTransfer();
  dataTransfer.items.add(file);

  if (interceptedFileInput && interceptedFileInput.isConnected) {
    interceptedFileInput.files = dataTransfer.files;
    interceptedFileInput.dispatchEvent(
      new Event("input", { bubbles: true, composed: true }),
    );
    interceptedFileInput.dispatchEvent(
      new Event("change", { bubbles: true, composed: true }),
    );
    return;
  }

  const pasteEvent = new ClipboardEvent("paste", {
    clipboardData: dataTransfer,
    bubbles: true,
    composed: true,
    cancelable: true,
  });

  const targetEl = getPromptElement() || document.body;
  targetEl.dispatchEvent(pasteEvent);
}

// ----------------- MODALS -----------------
function removeExistingModal() {
  const existing = document.getElementById("privacy-guard-modal");
  if (existing) existing.remove();
}

function createBaseModal(innerContent) {
  removeExistingModal();
  const modal = document.createElement("div");
  modal.id = "privacy-guard-modal";
  modal.innerHTML = innerContent;
  document.body.appendChild(modal);
  return modal;
}

// (Prompt Modals)
function showPreScanModal(targetInput, originalText) {
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
    resumePromptSubmission(pendingActiveEl, pendingOriginalSendBtn);
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

      if (data.error) {
        modal.innerHTML = `
          <h3 style="color: #ff4d4d;">⚠️ Scanner Error</h3>
          <p style="font-size: 13px;">${data.error}</p>
          <div class="btn-group">
            <button class="btn-ignore" id="pg-error-skip">Send Anyway</button>
            <button class="btn-mask" onclick="document.getElementById('privacy-guard-modal').remove()">Cancel</button>
          </div>
        `;
        document.getElementById("pg-error-skip").onclick = () => {
          modal.remove();
          resumePromptSubmission(pendingActiveEl, pendingOriginalSendBtn);
        };
        return;
      }

      if (data.has_pii && data.flagged_items && data.flagged_items.length > 0) {
        showResultsModal(targetInput, originalText, data.flagged_items);
      } else {
        modal.remove();
        resumePromptSubmission(pendingActiveEl, pendingOriginalSendBtn);
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
  const modal = createBaseModal(`
    <h3>⚠️ Private Data Detected!</h3>
    <p style="font-size: 13px; margin: 5px 0;">Found ${flaggedItems.length} sensitive items.</p>
    <div class="btn-group">
      <button class="btn-ignore" id="pg-proceed">Send Anyway</button>
      <button class="btn-mask" id="pg-playground">Open in Playground</button>
    </div>
  `);

  document.getElementById("pg-proceed").onclick = () => {
    modal.remove();
    resumePromptSubmission(pendingActiveEl, pendingOriginalSendBtn);
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
  const modal = createBaseModal(`
    <h3>⚠️ Sensitive Data in File!</h3>
    <p style="font-size: 13px; margin: 5px 0;">Found ${scanData.flagged_items.length} items in <strong>${scanData.filename}</strong>.</p>
    <div class="btn-group">
      <button class="btn-ignore" id="pg-file-proceed">Upload Anyway</button>
      <button class="btn-mask" id="pg-file-playground">Open in Playground</button>
    </div>
  `);

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
