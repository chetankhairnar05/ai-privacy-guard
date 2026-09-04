document.addEventListener("DOMContentLoaded", () => {
  chrome.storage.local.get("privacyPlaygroundData", (stored) => {
    const data = stored.privacyPlaygroundData;
    if (!data) {
      document.getElementById("items-list").innerHTML = "<p>No data found.</p>";
      return;
    }

    const items = data.items || [];
    const listContainer = document.getElementById("items-list");
    listContainer.innerHTML = "";

    // Track mask configurations for each item
    let maskSettings = items.map((item, index) => ({
      original: item.text,
      type: item.type,
      replaceWith: `[${item.type}_${index + 1}]`,
      shouldMask: true,
    }));

    // Render configuration rows
    maskSettings.forEach((setting, index) => {
      const row = document.createElement("div");
      row.className = "item-row";
      row.innerHTML = `
        <div>
          <input type="checkbox" id="mask-${index}" checked>
          <label for="mask-${index}">
            <span class="badge">${setting.type}</span>
            <strong>${setting.original}</strong>
          </label>
        </div>
        <div>
          Replace with: 
          <input type="text" id="replace-${index}" value="${setting.replaceWith}">
        </div>
      `;
      listContainer.appendChild(row);

      document
        .getElementById(`mask-${index}`)
        .addEventListener("change", (e) => {
          setting.shouldMask = e.target.checked;
          if (data.mode === "text") updateTextOutput();
        });

      document
        .getElementById(`replace-${index}`)
        .addEventListener("input", (e) => {
          setting.replaceWith = e.target.value;
          if (data.mode === "text") updateTextOutput();
        });
    });

    // ----------------- MODE: TEXT PROMPT -----------------
    if (data.mode === "text") {
      document.getElementById("text-mode-container").style.display = "block";
      const outputBox = document.getElementById("output-box");

      function updateTextOutput() {
        let text = data.text;
        maskSettings.forEach((setting) => {
          if (setting.shouldMask) {
            text = text.split(setting.original).join(setting.replaceWith);
          }
        });
        outputBox.value = text;
      }

      updateTextOutput();

      document.getElementById("copy-btn").onclick = () => {
        navigator.clipboard.writeText(outputBox.value).then(() => {
          alert("Sanitized prompt copied to clipboard! Paste it into ChatGPT.");
        });
      };
    }

    // ----------------- MODE: FILE (.DOCX / .PPTX) -----------------
    else if (data.mode === "file") {
      document.getElementById("file-mode-container").style.display = "block";
      document.getElementById("file-info").innerText =
        `File: ${data.filename} (${data.extension}). Checked items above will be replaced inside the document structure.`;

      document.getElementById("download-masked-btn").onclick = async () => {
        const btn = document.getElementById("download-masked-btn");
        btn.innerText = "Processing Document on Local Server...";
        btn.disabled = true;

        // Filter only checked replacements
        const activeRules = maskSettings
          .filter((s) => s.shouldMask)
          .map((s) => ({ original: s.original, replace_with: s.replaceWith }));

        const formData = new FormData();
        formData.append("file_id", data.file_id);
        formData.append("rules_json", JSON.stringify(activeRules));

        try {
          const res = await fetch("http://127.0.0.1:8000/mask-file", {
            method: "POST",
            body: formData,
          });

          if (!res.ok) throw new Error("Masking failed on server");

          // Convert the stream to a downloadable blob
          const blob = await res.blob();
          const downloadUrl = window.URL.createObjectURL(blob);
          const a = document.createElement("a");
          a.href = downloadUrl;
          a.download = `safe_${data.filename}`;
          document.body.appendChild(a);
          a.click();
          a.remove();

          btn.innerText = "✅ Downloaded Safe File!";
          btn.disabled = false;
        } catch (err) {
          alert("Failed to mask file: " + err.message);
          btn.innerText = "Apply Masks & Download Safe Document";
          btn.disabled = false;
        }
      };
    }
  });
});
