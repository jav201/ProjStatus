const THEME_STORAGE_KEY = "projstatus-theme";

document.addEventListener("DOMContentLoaded", () => {
  applyTheme(resolveTheme());
  bindThemeToggle();
  bindSystemThemeSync();
  initializeMermaid();
  initializeBoard();
  initializeMermaidEditor();
  initializeTaskSidePanel();
  bindOutsideClickClose();
  bindSidebarToggle();
});

function bindSidebarToggle() {
  const toggle = document.querySelector("[data-sidebar-toggle]");
  const sidebar = document.querySelector("[data-sidebar]");
  if (!toggle || !sidebar) return;
  toggle.addEventListener("click", () => sidebar.classList.toggle("is-open"));
  document.addEventListener("click", (event) => {
    if (window.innerWidth > 1024) return;
    if (toggle.contains(event.target) || sidebar.contains(event.target)) return;
    sidebar.classList.remove("is-open");
  });
}

function bindOutsideClickClose() {
  // Close any open <details class="menu" | "health-chip"> when clicking outside.
  document.addEventListener("click", (event) => {
    document.querySelectorAll("details.menu[open], details.health-chip[open]").forEach((d) => {
      if (!d.contains(event.target)) d.removeAttribute("open");
    });
  });
}

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
  // Default to light to match the design mockup; system-dark is opt-in via toggle.
  return "light";
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
          updateColumnCounts();
        } catch (error) {
          // revert on failure
          showToast("Couldn't save move — refreshing.", "error");
          setTimeout(() => window.location.reload(), 800);
        }
      },
    });
  });
}

function updateColumnCounts() {
  document.querySelectorAll(".board-column").forEach((column) => {
    const lane = column.querySelector(".task-lane");
    const counter = column.querySelector("header span");
    if (lane && counter) {
      counter.textContent = lane.querySelectorAll(".task-card").length;
    }
  });
}

function showToast(message, level) {
  let toast = document.querySelector(".toast");
  if (!toast) {
    toast = document.createElement("div");
    toast.className = "toast";
    document.body.appendChild(toast);
  }
  toast.dataset.level = level || "info";
  toast.textContent = message;
  toast.classList.add("is-visible");
  clearTimeout(toast.dataset.timeoutId);
  toast.dataset.timeoutId = setTimeout(() => toast.classList.remove("is-visible"), 3500);
}

function initializeTaskSidePanel() {
  const editPanel = document.querySelector("[data-task-panel]");
  const addPanel = document.querySelector("[data-add-task-panel]");
  const backdrop = document.querySelector("[data-task-panel-backdrop]");
  if (!backdrop || (!editPanel && !addPanel)) {
    return;
  }

  const setOpen = (panel, isOpen) => {
    if (!panel) return;
    panel.classList.toggle("is-open", isOpen);
    panel.setAttribute("aria-hidden", isOpen ? "false" : "true");
  };
  const openPanel = (panel) => {
    if (!panel) return;
    // Only one drawer at a time.
    if (panel === editPanel) setOpen(addPanel, false);
    if (panel === addPanel) setOpen(editPanel, false);
    setOpen(panel, true);
    backdrop.classList.add("is-open");
  };
  const closeAll = () => {
    setOpen(editPanel, false);
    setOpen(addPanel, false);
    backdrop.classList.remove("is-open");
  };

  // Edit panel: card-click populates the form, Close button + Delete button.
  if (editPanel) {
    const form = editPanel.querySelector("[data-task-form]");
    const closeBtn = editPanel.querySelector("[data-task-panel-close]");
    const deleteBtn = editPanel.querySelector("[data-task-delete]");
    if (closeBtn) closeBtn.addEventListener("click", closeAll);

    if (form) {
      document.querySelectorAll(".task-card").forEach((card) => {
        card.addEventListener("click", (event) => {
          // ignore clicks that bubble up from drag operations
          if (event.target.closest(".sortable-fallback") || card.classList.contains("sortable-chosen")) return;
          const dataNode = card.querySelector(".task-data");
          if (!dataNode) return;
          const data = JSON.parse(dataNode.textContent || "{}");
          form.action = card.dataset.editUrl;
          form.elements.title.value = data.title || "";
          form.elements.description.value = data.description || "";
          form.elements.column.value = data.column || "";
          form.elements.priority.value = data.priority || "medium";
          form.elements.start_date.value = data.start_date || "";
          form.elements.due_date.value = data.due_date || "";
          form.elements.milestone_id.value = data.milestone_id || "";
          form.elements.notes.value = data.notes || "";
          form.elements.change_note.value = "";
          const assignees = new Set(data.assignee_ids || []);
          const checkboxes = form.querySelectorAll('input[type="checkbox"][name="assignee_ids"]');
          checkboxes.forEach((box) => {
            box.checked = assignees.has(box.value);
          });
          if (deleteBtn) deleteBtn.dataset.url = card.dataset.deleteUrl;
          openPanel(editPanel);
        });
      });
    }

    if (deleteBtn) {
      deleteBtn.addEventListener("click", () => {
        if (!deleteBtn.dataset.url) return;
        if (!confirm("Delete this task?")) return;
        const deleteForm = document.createElement("form");
        deleteForm.method = "POST";
        deleteForm.action = deleteBtn.dataset.url;
        const note = document.createElement("input");
        note.name = "change_note";
        note.value = "Deleted from side panel";
        deleteForm.appendChild(note);
        document.body.appendChild(deleteForm);
        deleteForm.submit();
      });
    }
  }

  // Add panel: trigger button opens, Close button closes.
  if (addPanel) {
    const closeBtn = addPanel.querySelector("[data-add-task-panel-close]");
    if (closeBtn) closeBtn.addEventListener("click", closeAll);
    document.querySelectorAll("[data-add-task-open]").forEach((btn) => {
      btn.addEventListener("click", () => openPanel(addPanel));
    });
  }

  // Shared dismissal: backdrop click and Escape key.
  backdrop.addEventListener("click", closeAll);
  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    const anyOpen =
      (editPanel && editPanel.classList.contains("is-open")) ||
      (addPanel && addPanel.classList.contains("is-open"));
    if (anyOpen) closeAll();
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
