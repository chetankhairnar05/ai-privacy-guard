document.addEventListener("DOMContentLoaded", () => {
  // Read the saved prompt and flagged items from Chrome storage
  chrome.storage.local.get("privacyPlaygroundData", (data) => {
    if (!data.privacyPlaygroundData) {
      document.getElementById("items-list").innerHTML = "<p>No data found.</p>";
      return;
    }

    const originalText = data.privacyPlaygroundData.text;
    const items = data.privacyPlaygroundData.items;

    const listContainer = document.getElementById("items-list");
    const outputBox = document.getElementById("output-box");

    // Array to track user choices
    let maskSettings = items.map((item, index) => ({
      original: item.text,
      type: item.type,
      replaceWith: `[${item.type}_${index + 1}]`, // Default generic tag
      shouldMask: true,
    }));

    // Function to render the live output
    function updateOutput() {
      let currentText = originalText;
      maskSettings.forEach((setting) => {
        if (setting.shouldMask) {
          // Replace all instances of the original word
          currentText = currentText
            .split(setting.original)
            .join(setting.replaceWith);
        }
      });
      outputBox.value = currentText;
    }

    // Generate the UI rows for each item
    maskSettings.forEach((setting, index) => {
      const row = document.createElement("div");
      row.className = "item-row";

      row.innerHTML = `
        <div>
          <input type="checkbox" id="mask-${index}" checked>
          <label for="mask-${index}"><strong>${setting.type}:</strong> ${setting.original}</label>
        </div>
        <div>
          Change to: <input type="text" id="replace-${index}" value="${setting.replaceWith}">
        </div>
      `;

      listContainer.appendChild(row);

      // Listen for checkbox toggles
      document
        .getElementById(`mask-${index}`)
        .addEventListener("change", (e) => {
          setting.shouldMask = e.target.checked;
          updateOutput();
        });

      // Listen for custom mask typing (e.g. typing xyz@gmail.com)
      document
        .getElementById(`replace-${index}`)
        .addEventListener("input", (e) => {
          setting.replaceWith = e.target.value;
          updateOutput();
        });
    });

    // Initial render
    updateOutput();
  });

  // Copy to clipboard logic
  document.getElementById("copy-btn").addEventListener("click", () => {
    const outputText = document.getElementById("output-box").value;
    navigator.clipboard.writeText(outputText).then(() => {
      alert(
        "Sanitized prompt copied! You can now close this tab and paste it into ChatGPT.",
      );
    });
  });
});
