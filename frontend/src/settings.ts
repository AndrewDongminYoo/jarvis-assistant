// settings.ts — Settings panel built with safe DOM methods (no innerHTML)
export function initSettings(): void {
  const panel = document.getElementById("settings-panel")!;
  const btn = document.getElementById("settings-btn")!;

  // Heading
  const h2 = document.createElement("h2");
  h2.style.cssText =
    "font-size:1rem;letter-spacing:.2em;text-transform:uppercase;color:#888;";
  h2.textContent = "Settings";
  panel.appendChild(h2);

  const formWrap = document.createElement("div");
  formWrap.style.cssText =
    "display:flex;flex-direction:column;gap:12px;width:100%;max-width:400px;";

  const languageGroup = document.createElement("div");
  languageGroup.className = "settings-group";

  const languageLabel = document.createElement("label");
  languageLabel.className = "settings-label";
  languageLabel.htmlFor = "s-recognition-lang";
  languageLabel.textContent = "Speech Recognition Language";

  const languageSelect = document.createElement("select");
  languageSelect.id = "s-recognition-lang";
  languageSelect.className = "settings-input";

  const languageOptions = [
    { value: "ko-KR", label: "Korean (ko-KR)" },
    { value: "en-US", label: "English (en-US)" },
    { value: "ja-JP", label: "Japanese (ja-JP)" },
    { value: "zh-CN", label: "Chinese (zh-CN)" },
  ];

  languageOptions.forEach(({ value, label }) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = label;
    languageSelect.appendChild(option);
  });

  const savedLang = localStorage.getItem("jarvis_recognition_lang");
  languageSelect.value = savedLang ?? "ko-KR";
  languageSelect.addEventListener("change", () =>
    localStorage.setItem("jarvis_recognition_lang", languageSelect.value),
  );

  languageGroup.appendChild(languageLabel);
  languageGroup.appendChild(languageSelect);
  formWrap.appendChild(languageGroup);

  panel.appendChild(formWrap);

  const closeBtn = document.createElement("button");
  closeBtn.id = "settings-close";
  closeBtn.textContent = "Close";
  panel.appendChild(closeBtn);

  btn.addEventListener("click", () => panel.classList.remove("hidden"));
  closeBtn.addEventListener("click", () => panel.classList.add("hidden"));
  panel.addEventListener("click", (e) => {
    if (e.target === panel) panel.classList.add("hidden");
  });
}
