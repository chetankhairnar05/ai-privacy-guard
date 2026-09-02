let isBypassed = false;

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

        // Step 1: Ask the user if they want to scan BEFORE doing anything
        showPreScanModal(activeEl, text);
      }
    }
  },
  true,
);

function showPreScanModal(targetInput, originalText) {
  const existing = document.getElementById("privacy-guard-modal");
  if (existing) existing.remove();

  const modal = document.createElement("div");
  modal.id = "privacy-guard-modal";
  modal.innerHTML = `
    <h3>🛡️ Privacy Check</h3>
    <p style="font-size: 13px; margin: 5px 0;">Do you want to scan this prompt for private information locally before sending?</p>
    <div class="btn-group">
      <button class="btn-ignore" id="pg-skip">Skip & Send Directly</button>
      <button class="btn-mask" id="pg-scan">Scan Prompt</button>
    </div>
  `;
  document.body.appendChild(modal);

  // If they skip, bypass and send immediately
  document.getElementById("pg-skip").onclick = () => {
    modal.remove();
    isBypassed = true;
    targetInput.dispatchEvent(
      new KeyboardEvent("keydown", { key: "Enter", bubbles: true }),
    );
  };

  // If they scan, hit the Python backend
  document.getElementById("pg-scan").onclick = async () => {
    modal.innerHTML = `<h3 style="color: #0084ff;">Scanning with Local AI...</h3>`;
    try {
      const res = await fetch("http://127.0.0.1:8000/scan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: originalText }),
      });
      const data = await res.json();

      // FIX: Check if the backend reported an error first
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
          isBypassed = true;
          targetInput.dispatchEvent(
            new KeyboardEvent("keydown", { key: "Enter", bubbles: true }),
          );
        };
        return; // Stop here
      }

      // Normal flow if no error
      if (data.has_pii && data.flagged_items && data.flagged_items.length > 0) {
        showResultsModal(targetInput, originalText, data.flagged_items);
      } else {
        // No PII found, auto-send
        modal.remove();
        isBypassed = true;
        targetInput.dispatchEvent(
          new KeyboardEvent("keydown", { key: "Enter", bubbles: true }),
        );
      }
    } catch (err) {
      alert("Local AI Server is offline! Start your Python backend.");
      modal.remove();
    }
  };
}

function showResultsModal(targetInput, originalText, flaggedItems) {
  const modal = document.getElementById("privacy-guard-modal");
  modal.innerHTML = `
    <h3>⚠️ Private Data Detected!</h3>
    <p style="font-size: 13px; margin: 5px 0;">We found ${flaggedItems.length} sensitive items.</p>
    <div class="btn-group">
      <button class="btn-ignore" id="pg-proceed">Process Anyway</button>
      <button class="btn-mask" id="pg-playground">Open in Playground</button>
    </div>
  `;

  // Process Anyway: Ignores warnings, sends original text
  document.getElementById("pg-proceed").onclick = () => {
    modal.remove();
    isBypassed = true;
    targetInput.dispatchEvent(
      new KeyboardEvent("keydown", { key: "Enter", bubbles: true }),
    );
  };

  // Open Playground: Save data to storage and open new tab
  document.getElementById("pg-playground").onclick = () => {
    chrome.storage.local.set(
      {
        privacyPlaygroundData: { text: originalText, items: flaggedItems },
      },
      () => {
        modal.remove();
        // Open the playground page in a new Chrome tab
        window.open(chrome.runtime.getURL("playground.html"), "_blank");
      },
    );
  };
}
