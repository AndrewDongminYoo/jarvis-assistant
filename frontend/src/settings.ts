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

  // Form fields
  const fields: {
    label: string;
    id: string;
    key: string;
    placeholder: string;
  }[] = [
    {
      label: "ElevenLabs Voice ID",
      id: "s-voice-id",
      key: "jarvis_voice_id",
      placeholder: "Leave blank for default (George)",
    },
    {
      label: "Your Name",
      id: "s-user-name",
      key: "jarvis_user_name",
      placeholder: "sir",
    },
    {
      label: "Backend URL",
      id: "s-backend-url",
      key: "jarvis_backend_url",
      placeholder: "https://localhost:8340",
    },
  ];

  const formWrap = document.createElement("div");
  formWrap.style.cssText =
    "display:flex;flex-direction:column;gap:12px;width:100%;max-width:400px;";

  fields.forEach(({ label, id, key, placeholder }) => {
    const group = document.createElement("div");
    group.className = "settings-group";

    const lbl = document.createElement("label");
    lbl.className = "settings-label";
    lbl.htmlFor = id;
    lbl.textContent = label;

    const inp = document.createElement("input");
    inp.type = "text";
    inp.id = id;
    inp.className = "settings-input";
    inp.placeholder = placeholder;

    const saved = localStorage.getItem(key);
    if (saved) inp.value = saved;
    inp.addEventListener("change", () => localStorage.setItem(key, inp.value));

    group.appendChild(lbl);
    group.appendChild(inp);
    formWrap.appendChild(group);
  });
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
