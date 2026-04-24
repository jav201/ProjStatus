const MERMAID_CONFIG = {
  startOnLoad: false,
  securityLevel: "loose",
  theme: "base",
  fontFamily: "Aptos, Segoe UI Variable Text, Segoe UI, sans-serif",
  themeVariables: {
    fontFamily: "Aptos, Segoe UI Variable Text, Segoe UI, sans-serif",
    primaryColor: "#E6F2FF",
    primaryTextColor: "#0F172A",
    primaryBorderColor: "#007ACC",
    lineColor: "#8AA8C7",
    textColor: "#0F172A",
    taskTextColor: "#0F172A",
    taskTextLightColor: "#0F172A",
    taskBkgColor: "#D9EAFF",
    taskBorderColor: "#7CA9D8",
    activeTaskBkgColor: "#3794FF",
    activeTaskBorderColor: "#007ACC",
    doneTaskBkgColor: "#8FD3C8",
    doneTaskBorderColor: "#2AA198",
    critTaskBkgColor: "#FFCCD1",
    critTaskBorderColor: "#D64550",
    gridColor: "#D5E2F0",
    sectionBkgColor: "#F8FBFF",
    sectionBkgColor2: "#EEF5FF",
    sectionColor: "#0F172A",
    todayLineColor: "#007ACC",
  },
  gantt: {
    barHeight: 28,
    barGap: 10,
    topPadding: 50,
    leftPadding: 110,
    rightPadding: 32,
  },
};

document.addEventListener("DOMContentLoaded", () => {
  initializeMermaid();
  initializeBoard();
  initializeMermaidEditor();
});

document.body.addEventListener("htmx:afterSwap", () => {
  initializeMermaid();
  initializeMermaidEditor();
});

function initializeMermaid() {
  if (typeof mermaid === "undefined") {
    return;
  }
  mermaid.initialize(MERMAID_CONFIG);
  renderMermaidNodes(Array.from(document.querySelectorAll(".mermaid")));
}

async function renderMermaidNodes(nodes) {
  if (typeof mermaid === "undefined" || !nodes.length) {
    return;
  }

  for (const node of nodes) {
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
    preview.textContent = editor.value;
    await renderMermaidNodes([preview]);
  };

  editor.addEventListener("input", renderPreview);
  renderPreview();
}
