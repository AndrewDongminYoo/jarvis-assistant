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

  // Preferred LLM provider
  const providerGroup = document.createElement("div");
  providerGroup.className = "settings-group";

  const providerLabel = document.createElement("label");
  providerLabel.className = "settings-label";
  providerLabel.htmlFor = "s-llm-provider";
  providerLabel.textContent = "Preferred LLM";

  const providerSelect = document.createElement("select");
  providerSelect.id = "s-llm-provider";
  providerSelect.className = "settings-input";
  providerSelect.disabled = true; // enabled after availability loads

  const providerLabels: Record<string, string> = {
    anthropic: "Claude (Anthropic)",
    openai: "GPT (OpenAI)",
    gemini: "Gemini (Google)",
  };

  const autoOption = document.createElement("option");
  autoOption.value = "";
  autoOption.textContent = "Auto (default order)";
  providerSelect.appendChild(autoOption);

  Object.entries(providerLabels).forEach(([value, label]) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = label;
    option.disabled = true; // enabled per availability in loadProviders()
    providerSelect.appendChild(option);
  });

  providerGroup.appendChild(providerLabel);
  providerGroup.appendChild(providerSelect);
  formWrap.appendChild(providerGroup);

  async function loadProviders(): Promise<void> {
    try {
      const res = await fetch("/api/providers");
      if (!res.ok) return;
      const data = (await res.json()) as {
        available: string[];
        preferred: string | null;
      };
      Array.from(providerSelect.options).forEach((opt) => {
        opt.disabled = opt.value !== "" && !data.available.includes(opt.value);
      });
      providerSelect.value = data.preferred ?? "";
      providerSelect.disabled = false;
    } catch {
      // settings are a convenience; ignore fetch failures
    }
  }

  providerSelect.addEventListener("change", () => {
    void fetch("/api/providers", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ preferred: providerSelect.value || null }),
    }).catch(() => {
      /* ignore — non-critical */
    });
  });

  panel.appendChild(formWrap);

  const closeBtn = document.createElement("button");
  closeBtn.id = "settings-close";
  closeBtn.textContent = "Close";
  panel.appendChild(closeBtn);

  btn.addEventListener("click", () => {
    panel.classList.remove("hidden");
    void loadProviders();
  });
  closeBtn.addEventListener("click", () => panel.classList.add("hidden"));
  panel.addEventListener("click", (e) => {
    if (e.target === panel) panel.classList.add("hidden");
  });
}
