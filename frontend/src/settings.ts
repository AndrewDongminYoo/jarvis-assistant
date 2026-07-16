// settings.ts — Settings panel built with safe DOM methods (no innerHTML)
type ProviderPreferenceSaveResult =
  | { readonly ok: true; readonly preferred: string }
  | { readonly ok: false; readonly preferred: string };

export async function saveProviderPreference(
  requested: string,
  confirmed: string,
  request: typeof fetch = fetch,
): Promise<ProviderPreferenceSaveResult> {
  try {
    const response = await request("/api/providers", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ preferred: requested || null }),
    });
    return response.ok
      ? { ok: true, preferred: requested }
      : { ok: false, preferred: confirmed };
  } catch {
    return { ok: false, preferred: confirmed };
  }
}

export function initSettings(): void {
  const panel = document.getElementById("settings-panel")!;
  const btn = document.getElementById("settings-btn")!;
  panel.setAttribute("role", "dialog");
  panel.setAttribute("aria-modal", "true");
  panel.setAttribute("aria-labelledby", "settings-title");
  btn.setAttribute("aria-haspopup", "dialog");
  btn.setAttribute("aria-controls", "settings-panel");
  btn.setAttribute("aria-expanded", "false");

  // Heading
  const h2 = document.createElement("h2");
  h2.id = "settings-title";
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
  let confirmedProvider = "";

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
      confirmedProvider = providerSelect.value;
      providerSelect.disabled = false;
    } catch {
      // settings are a convenience; ignore fetch failures
    }
  }

  providerSelect.addEventListener("change", () => {
    const requested = providerSelect.value;
    providerSelect.disabled = true;
    void saveProviderPreference(requested, confirmedProvider).then((result) => {
      confirmedProvider = result.preferred;
      providerSelect.value = result.preferred;
      providerSelect.disabled = false;
      if (!result.ok) {
        console.warn("Failed to save preferred LLM provider.");
      }
    });
  });

  panel.appendChild(formWrap);

  const closeBtn = document.createElement("button");
  closeBtn.id = "settings-close";
  closeBtn.textContent = "Close";
  panel.appendChild(closeBtn);

  let restoreFocusTo: HTMLElement | null = null;

  function closePanel(): void {
    panel.classList.add("hidden");
    btn.setAttribute("aria-expanded", "false");
    const focusTarget = restoreFocusTo ?? btn;
    restoreFocusTo = null;
    focusTarget.focus();
  }

  function openPanel(): void {
    restoreFocusTo =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : btn;
    panel.classList.remove("hidden");
    btn.setAttribute("aria-expanded", "true");
    void loadProviders();
    languageSelect.focus();
  }

  btn.addEventListener("click", openPanel);
  closeBtn.addEventListener("click", closePanel);
  panel.addEventListener("click", (e) => {
    if (e.target === panel) closePanel();
  });
  panel.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      e.preventDefault();
      closePanel();
      return;
    }
    if (e.key !== "Tab") return;

    const focusable = Array.from(
      panel.querySelectorAll<HTMLElement>(
        "button:not([disabled]), select:not([disabled])",
      ),
    );
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last?.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first?.focus();
    }
  });
}
