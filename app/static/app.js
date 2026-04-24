const THEME_STORAGE_KEY = "projstatus-theme";

document.addEventListener("DOMContentLoaded", () => {
  applyTheme(resolveTheme());
  bindThemeToggle();
  bindSystemThemeSync();
  initializeMermaid();
  initializeBoard();
  initializeMermaidEditor();
});

document.body.addEventListener("htmx:afterSwap", () => {
  initializeMermaid();
  initializeMermaidEditor();
});

function bindThemeToggle() {
  const toggle = document.querySelector("[data-theme-toggle]");
  if (!toggle) {
    return;
  }

  updateThemeLabel(resolveTheme());
  toggle.addEventListener("click", async () => {
    const current = resolveTheme();
    const next = current === "dark" ? "light" : "dark";
    setStoredTheme(next);
    applyTheme(next);
    await initializeMermaid();
  });
}

function bindSystemThemeSync() {
  const mediaQuery = window.matchMedia("(prefers-color-scheme: dark)");
  const handleChange = async () => {
    if (getStoredTheme()) {
      return;
    }
    applyTheme(resolveTheme());
    await initializeMermaid();
  };

  if (typeof mediaQuery.addEventListener === "function") {
    mediaQuery.addEventListener("change", handleChange);
  } else if (typeof mediaQuery.addListener === "function") {
    mediaQuery.addListener(handleChange);
  }
}

function getStoredTheme() {
  try {
    const value = window.localStorage.getItem(THEME_STORAGE_KEY);
    return value === "light" || value === "dark" ? value : "";
  } catch (error) {
    return "";
  }
}

function setStoredTheme(theme) {
  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, theme);
  } catch (error) {
    console.warn("Unable to persist theme preference", error);
  }
}

function resolveTheme() {
  const storedTheme = getStoredTheme();
  if (storedTheme) {
    return storedTheme;
  }
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  updateThemeLabel(theme);
}

function updateThemeLabel(theme) {
  const label = document.querySelector("[data-theme-label]");
  if (!label) {
    return;
  }
  label.textContent = theme === "dark" ? "Light mode" : "Dark mode";
}

function getMermaidConfig(theme) {
  const dark = theme === "dark";
  return {
    startOnLoad: false,
    securityLevel: "loose",
    theme: "base",
    fontFamily: "Segoe UI Variable Text, Aptos, Segoe UI, sans-serif",
    themeVariables: {
      fontFamily: "Segoe UI Variable Text, Aptos, Segoe UI, sans-serif",
      primaryColor: dark ? "#112540" : "#E6F2FF",
      primaryTextColor: dark ? "#E8F1FF" : "#0F172A",
      primaryBorderColor: dark ? "#3794FF" : "#007ACC",
      lineColor: dark ? "#5C7FA8" : "#8AA8C7",
      textColor: dark ? "#E8F1FF" : "#0F172A",
      taskTextColor: dark ? "#E8F1FF" : "#0F172A",
      taskTextLightColor: dark ? "#E8F1FF" : "#0F172A",
      taskBkgColor: dark ? "#18375A" : "#D9EAFF",
      taskBorderColor: dark ? "#5B88B7" : "#7CA9D8",
      activeTaskBkgColor: dark ? "#3794FF" : "#3794FF",
      activeTaskBorderColor: dark ? "#6CB6FF" : "#007ACC",
      doneTaskBkgColor: dark ? "#1F6F6B" : "#8FD3C8",
      doneTaskBorderColor: dark ? "#36C3B4" : "#2AA198",
      critTaskBkgColor: dark ? "#4A2230" : "#FFCCD1",
      critTaskBorderColor: dark ? "#FF6B7A" : "#D64550",
      gridColor: dark ? "#294665" : "#D5E2F0",
      sectionBkgColor: dark ? "#0F1D33" : "#F8FBFF",
      sectionBkgColor2: dark ? "#12253F" : "#EEF5FF",
      sectionColor: dark ? "#E8F1FF" : "#0F172A",
      todayLineColor: dark ? "#6CB6FF" : "#007ACC",
    },
    gantt: {
      barHeight: 28,
      barGap: 10,
      topPadding: 50,
      leftPadding: 110,
      rightPadding: 32,
    },
  };
}

async function initializeMermaid() {
  if (typeof mermaid === "undefined") {
    return;
  }
  mermaid.initialize(getMermaidConfig(resolveTheme()));
  await renderMermaidNodes(Array.from(document.querySelectorAll(".mermaid")));
}

async function renderMermaidNodes(nodes) {
  if (typeof mermaid === "undefined" || !nodes.length) {
    return;
  }

  for (const node of nodes) {
    const definition = node.dataset.graphDefinition || node.textContent;
    node.dataset.graphDefinition = definition;
    node.textContent = definition;
    node.removeAttribute("data-processed");
  }

  try {
    await mermaid.run({ nodes });
  } catch (error) {
    console.warn("Mermaid render failed", error);
  }
}

function initializeBoard() {
  if (typeof Sortable === "undefined") {
    return;
  }

  document.querySelectorAll(".task-lane").forEach((lane) => {
    if (lane.dataset.sortableReady === "true") {
      return;
    }
    lane.dataset.sortableReady = "true";
    new Sortable(lane, {
      group: "projstatus-board",
      animation: 180,
      onEnd: async (event) => {
        const taskId = event.item.dataset.taskId;
        const column = event.to.dataset.column;
        const columnWrapper = event.to.closest(".board-column");
        const template = columnWrapper.dataset.moveUrlBase;
        const endpoint = template.replace("TASK_ID_PLACEHOLDER", taskId);
        try {
          const response = await fetch(endpoint, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ column }),
          });
          if (!response.ok) {
            throw new Error("Move failed");
          }
          window.location.reload();
        } catch (error) {
          window.location.reload();
        }
      },
    });
  });
}

function initializeMermaidEditor() {
  const editor = document.querySelector("#timeline-editor");
  const preview = document.querySelector("#timeline-preview");
  if (!editor || !preview || typeof mermaid === "undefined") {
    return;
  }

  if (editor.dataset.previewBound === "true") {
    return;
  }
  editor.dataset.previewBound = "true";

  const renderPreview = async () => {
    preview.dataset.graphDefinition = editor.value;
    preview.textContent = editor.value;
    await renderMermaidNodes([preview]);
  };

  editor.addEventListener("input", renderPreview);
  renderPreview();
}
