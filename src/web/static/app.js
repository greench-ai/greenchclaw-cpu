/**
 * GreenClaw CPU — All-in-One Web UI JavaScript Client
 *
 * Handles:
 * - WebSocket streaming chat
 * - Knowledge base management (upload, search, list)
 * - Tool and model discovery
 * - Multi-panel navigation
 * - File drag & drop
 * - Image analysis
 * - Auto-reconnection
 *
 * MIT License — GreenClaw Team
 */

(function () {
  "use strict";

  // ═══════════════════════════════════════════════════════════════
  // State
  // ═══════════════════════════════════════════════════════════════
  let ws = null;
  let connected = false;
  let busy = false;
  let reconnectDelay = 1000;
  let reconnectTmo = null;
  let modelName = "—";
  let providerName = "ollama";
  let streamingMsg = null;

  const pendingFiles = [];

  // ═══════════════════════════════════════════════════════════════
  // DOM refs
  // ═══════════════════════════════════════════════════════════════
  const $  = (s) => document.querySelector(s);
  const $$ = (s) => document.querySelectorAll(s);

  const elMessages     = $("#messages");
  const elWelcome      = $("#welcome-screen");
  const elWelcomeHint  = $("#welcome-hint");
  const elInput       = $("#message-input");
  const elSendBtn     = $("#send-btn");
  const elStatusDot   = $("#status-indicator .dot");
  const elStatusText  = $("#status-text");
  const elTyping      = $("#typing-indicator");
  const elInputHint   = $("#input-hint");
  const elModelName   = $("#model-name");
  const elToolsGrid   = $("#tools-grid");
  const elKBResults   = $("#kb-results");
  const elKBDocs      = $("#kb-docs");
  const elAttachMenu  = $("#attach-menu");
  const elFileDrop    = $("#file-drop-zone");
  const elFileList    = $("#file-list");
  const elUploadBtn   = $("#kb-upload-btn");

  // ═══════════════════════════════════════════════════════════════
  // Status helpers
  // ═══════════════════════════════════════════════════════════════
  const Status = { IDLE: "idle", THINKING: "thinking", STREAMING: "streaming", TOOL: "tool" };

  function setStatus(status, detail) {
    const dotClass = {
      [Status.IDLE]:      "dot-idle",
      [Status.THINKING]:  "dot-thinking",
      [Status.STREAMING]: "dot-streaming",
      [Status.TOOL]:      "dot-tool",
    }[status] || "dot-idle";

    elStatusDot.className = `dot ${dotClass}`;
    elStatusText.textContent = detail || {
      [Status.IDLE]:      "Idle",
      [Status.THINKING]:  "Thinking…",
      [Status.STREAMING]: "Streaming…",
      [Status.TOOL]:      "Using tool…",
    }[status] || status;

    elSendBtn.disabled = !connected || busy;
  }

  function showToast(msg, type = "") {
    const t = document.createElement("div");
    t.className = `toast ${type}`;
    t.textContent = msg;
    document.body.appendChild(t);
    setTimeout(() => t.remove(), 3500);
  }

  // ═══════════════════════════════════════════════════════════════
  // WebSocket
  // ═══════════════════════════════════════════════════════════════
  function getWsUrl() {
    const p = location.protocol === "https:" ? "wss:" : "ws:";
    return `${p}//${location.host}/ws/chat`;
  }

  function connect() {
    if (ws && ws.readyState <= 1) return;

    setStatus(Status.THINKING, "Connecting…");
    elWelcomeHint.innerHTML = '<span class="hint-spinner"></span> Connecting…';

    try {
      ws = new WebSocket(getWsUrl());
    } catch (e) {
      scheduleReconnect();
      return;
    }

    ws.addEventListener("open", () => {
      connected = true;
      reconnectDelay = 1000;
      clearTimeout(reconnectTmo);
      elStatusDot.className = "dot dot-connected";
      elStatusText.textContent = "Connected";
      elWelcomeHint.textContent = "Connected — start chatting below!";
      elSendBtn.disabled = busy;
      loadTools();
      loadKB();
    });

    ws.addEventListener("message", (e) => {
      let data;
      try { data = JSON.parse(e.data); } catch { return; }
      handleMessage(data);
    });

    ws.addEventListener("close", (e) => {
      connected = false;
      ws = null;
      elStatusDot.className = "dot dot-idle";
      elStatusText.textContent = "Disconnected";
      elSendBtn.disabled = true;
      if (!e.wasClean) scheduleReconnect();
    });

    ws.addEventListener("error", () => {
      connected = false;
      setStatus(Status.IDLE, "Connection error");
    });
  }

  function scheduleReconnect() {
    clearTimeout(reconnectTmo);
    reconnectTmo = setTimeout(() => {
      reconnectDelay = Math.min(reconnectDelay * 2, 16000);
      connect();
    }, reconnectDelay);
  }

  // ═══════════════════════════════════════════════════════════════
  // Message handling
  // ═══════════════════════════════════════════════════════════════
  function handleMessage(data) {
    switch (data.type) {

      case "status":
        if (data.status) setStatus(data.status, data.detail);
        if (data.model) {
          modelName = data.model;
          elModelName.textContent = data.model;
        }
        break;

      case "token":
        if (!streamingMsg) {
          streamingMsg = {
            el: createMsgEl("assistant", ""),
            content: "",
          };
          elTyping.style.display = "none";
        }
        streamingMsg.content += data.content || "";
        updateMsgContent(streamingMsg.el, streamingMsg.content, true);
        scrollToBottom();
        break;

      case "tool_start":
        // Tool being executed — show in status
        setStatus(Status.TOOL, `Using ${data.tool}…`);
        break;

      case "tool_result":
        if (streamingMsg) {
          // Append tool result preview
          const preview = document.createElement("div");
          preview.className = "tool-result-preview";
          const resultText = data.truncated
            ? data.result + "\n\n… [truncated]"
            : data.result;
          preview.textContent = resultText;
          streamingMsg.el.closest(".message-body").appendChild(preview);
        }
        break;

      case "done":
        if (streamingMsg) {
          updateMsgContent(streamingMsg.el, streamingMsg.content, false);
          addToHistory("user", streamingMsg._userMsg || "");
          addToHistory("assistant", streamingMsg.content);
          streamingMsg = null;
        }
        setStatus(Status.IDLE);
        busy = false;
        elSendBtn.disabled = !connected;
        elInput.focus();
        break;

      case "error":
        if (streamingMsg) {
          updateMsgContent(
            streamingMsg.el,
            streamingMsg.content + "\n\n⚠️ Error: " + (data.message || "Unknown"),
            false
          );
          streamingMsg.el.closest(".message").classList.add("error");
          streamingMsg = null;
        } else {
          const el = createMsgEl("assistant", "⚠️ " + (data.message || "An error occurred"));
          el.closest(".message").classList.add("error");
        }
        setStatus(Status.IDLE);
        busy = false;
        showToast(data.message || "Error", "error");
        break;

      case "pong":
        break;
    }
  }

  // ═══════════════════════════════════════════════════════════════
  // Message DOM helpers
  // ═══════════════════════════════════════════════════════════════
  const conversation = [];

  function addToHistory(role, content) {
    conversation.push({ role, content });
  }

  function createMsgEl(role, content) {
    if (elWelcome && !elWelcome.classList.contains("hidden")) {
      elWelcome.classList.add("hidden");
    }

    const avatar = role === "user" ? "👤" : "🦎";
    const label  = role === "user" ? "You" : "GreenClaw";
    const extraClass = role === "tool" ? "tool" : "";

    const wrap = document.createElement("div");
    wrap.className = `message ${role} ${extraClass}`.trim();
    wrap.innerHTML = `
      <div class="message-avatar">${avatar}</div>
      <div class="message-body">
        <div class="role-name">${label}</div>
        <div class="message-content"></div>
      </div>`;

    elMessages.appendChild(wrap);
    scrollToBottom();
    const contentEl = wrap.querySelector(".message-content");
    if (content) updateMsgContent(contentEl, content, false);
    return contentEl;
  }

  function updateMsgContent(el, content, streaming) {
    if (!el) return;
    let html = escapeHtml(content);

    // Inline code
    html = html.replace(/`([^`]+)`/g, "<code>$1</code>");
    // Bold
    html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    // Italic
    html = html.replace(/\*([^*]+)\*/g, "<em>$1</em>");
    // Code fences
    html = html.replace(/```([\s\S]*?)```/g, "<pre><code>$1</code></pre>");
    // Numbered/bullet lists
    html = html.replace(/^(\d+)\. (.+)$/gm, "<li>$1. $2</li>");
    html = html.replace(/^[-*] (.+)$/gm, "<li>$1</li>");

    el.innerHTML = html;
    el.classList.toggle("streaming-cursor", streaming);
  }

  function escapeHtml(text) {
    const d = document.createElement("div");
    d.textContent = text;
    return d.innerHTML;
  }

  function scrollToBottom() {
    const main = $("#chat-main");
    main.scrollTop = main.scrollHeight;
  }

  // ═══════════════════════════════════════════════════════════════
  // Send message
  // ═══════════════════════════════════════════════════════════════
  function sendMessage() {
    const content = elInput.value.trim();
    if (!content || !connected || busy) return;

    // Add user message to UI
    createMsgEl("user", content);
    elInput.value = "";
    elInput.style.height = "auto";

    busy = true;
    setStatus(Status.THINKING, "Analyzing…");
    elSendBtn.disabled = true;

    // Show typing indicator after short delay
    let typingTmo = setTimeout(() => {
      if (busy) {
        elTyping.style.display = "flex";
        scrollToBottom();
      }
    }, 600);

    // Track the user message for history
    if (streamingMsg) streamingMsg._userMsg = content;

    ws.send(JSON.stringify({ type: "message", content }));
    elInput.focus();
  }

  // ═══════════════════════════════════════════════════════════════
  // Input handling
  // ═══════════════════════════════════════════════════════════════
  elInput.addEventListener("input", () => {
    elInput.style.height = "auto";
    elInput.style.height = Math.min(elInput.scrollHeight, 150) + "px";
  });

  elInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });

  elSendBtn.addEventListener("click", sendMessage);

  // Attach menu
  $("#attach-btn").addEventListener("click", (e) => {
    e.stopPropagation();
    const shown = elAttachMenu.style.display === "flex";
    elAttachMenu.style.display = shown ? "none" : "flex";
  });

  document.addEventListener("click", () => {
    elAttachMenu.style.display = "none";
  });

  $("#attach-image").addEventListener("click", async () => {
    elAttachMenu.style.display = "none";
    const input = document.createElement("input");
    input.type = "file";
    input.accept = "image/*";
    input.onchange = async () => {
      const file = input.files[0];
      if (!file) return;
      showToast("Analyzing image…");
      try {
        const fd = new FormData();
        fd.append("file", file);
        fd.append("prompt", "Describe this image in detail.");
        const res = await fetch("/api/analyze/image", { method: "POST", body: fd });
        const data = await res.json();
        if (data.success) {
          createMsgEl("assistant", data.content);
        } else {
          createMsgEl("assistant", "⚠️ Image analysis failed: " + (data.error || "Unknown error"));
        }
      } catch (e) {
        createMsgEl("assistant", "⚠️ Image analysis error: " + e.message);
      }
    };
    input.click();
  });

  $("#attach-to-kb").addEventListener("click", () => {
    elAttachMenu.style.display = "none";
    switchPanel("kb");
    $("#header-nav [data-panel='kb']").click();
  });

  // ═══════════════════════════════════════════════════════════════
  // Panel navigation
  // ═══════════════════════════════════════════════════════════════
  function switchPanel(name) {
    $$(".nav-btn").forEach(b => b.classList.toggle("active", b.dataset.panel === name));
    $$(".panel").forEach(p => p.classList.toggle("active", p.id === `panel-${name}`));
  }

  $$(".nav-btn").forEach(btn => {
    btn.addEventListener("click", () => switchPanel(btn.dataset.panel));
  });

  // ═══════════════════════════════════════════════════════════════
  // Tools panel
  // ═══════════════════════════════════════════════════════════════
  async function loadTools() {
    try {
      const res = await fetch("/api/tools");
      if (!res.ok) return;
      const data = await res.json();
      renderTools(data.tools || []);
    } catch (e) {
      elToolsGrid.innerHTML = '<div class="kb-empty">Could not load tools.</div>';
    }
  }

  const toolIcons = {
    file: "📁", web: "🌐", code: "⚡", media: "🖼️",
    knowledge: "🧠", agent: "🤖", system: "⚙️",
  };

  function renderTools(tools) {
    elToolsGrid.innerHTML = tools.map(t => `
      <div class="tool-card" data-category="${t.category || "system"}">
        <div class="tool-card-header">
          <span class="tool-card-icon">${toolIcons[t.category] || "🔧"}</span>
          <span class="tool-card-name">${escapeHtml(t.name)}</span>
          <span class="tool-card-category">${t.category || "system"}</span>
        </div>
        <p class="tool-card-desc">${escapeHtml(t.description || "")}</p>
      </div>
    `).join("");
  }

  // ═══════════════════════════════════════════════════════════════
  // Knowledge Base
  // ═══════════════════════════════════════════════════════════════

  // KB tabs
  $$(".kb-tab").forEach(tab => {
    tab.addEventListener("click", () => {
      $$(".kb-tab").forEach(t => t.classList.remove("active"));
      $$(".kb-tab-content").forEach(c => c.classList.remove("active"));
      tab.classList.add("active");
      $(`#kb-tab-${tab.dataset.kbTab}`).classList.add("active");
    });
  });

  // File drop zone
  elFileDrop.addEventListener("dragover", (e) => {
    e.preventDefault();
    elFileDrop.classList.add("drag-over");
  });

  elFileDrop.addEventListener("dragleave", () => {
    elFileDrop.classList.remove("drag-over");
  });

  elFileDrop.addEventListener("drop", (e) => {
    e.preventDefault();
    elFileDrop.classList.remove("drag-over");
    handleFileSelect(Array.from(e.dataTransfer.files));
  });

  $("#kb-file-input").addEventListener("change", (e) => {
    handleFileSelect(Array.from(e.target.files));
    e.target.value = "";
  });

  function handleFileSelect(files) {
    for (const f of files) {
      if (!pendingFiles.find(p => p.name === f.name)) {
        pendingFiles.push(f);
      }
    }
    renderFileList();
    elUploadBtn.disabled = pendingFiles.length === 0;
  }

  function renderFileList() {
    elFileList.innerHTML = pendingFiles.map((f, i) => `
      <div class="file-item">
        <span class="file-item-name">${escapeHtml(f.name)}</span>
        <span class="file-item-size">${formatSize(f.size)}</span>
        <span class="file-item-remove" data-index="${i}">✕</span>
      </div>
    `).join("");

    $$(".file-item-remove").forEach(btn => {
      btn.addEventListener("click", () => {
        pendingFiles.splice(parseInt(btn.dataset.index), 1);
        renderFileList();
        elUploadBtn.disabled = pendingFiles.length === 0;
      });
    });
  }

  function formatSize(bytes) {
    for (const unit of ["B", "KB", "MB", "GB"]) {
      if (bytes < 1024) return `${bytes.toFixed(0)} ${unit}`;
      bytes /= 1024;
    }
    return `${bytes.toFixed(1)} TB`;
  }

  // Upload files
  elUploadBtn.addEventListener("click", async () => {
    if (!pendingFiles.length) return;
    elUploadBtn.disabled = true;
    elUploadBtn.textContent = "Uploading…";

    for (const file of pendingFiles) {
      try {
        const fd = new FormData();
        fd.append("file", file);
        fd.append("kb_name", "default");
        fd.append("name", file.name);

        const res = await fetch("/api/kb/add/file", { method: "POST", body: fd });
        const data = await res.json();

        if (data.status === "ok") {
          showToast(`Added: ${file.name}`, "success");
        } else {
          showToast(`Failed: ${file.name}`, "error");
        }
      } catch (e) {
        showToast(`Error: ${e.message}`, "error");
      }
    }

    pendingFiles.length = 0;
    renderFileList();
    elUploadBtn.disabled = true;
    elUploadBtn.textContent = "Upload to Knowledge Base";
    loadKB();
  });

  // Add URL
  $("#kb-add-url-btn").addEventListener("click", async () => {
    const url = $("#kb-url-input").value.trim();
    const name = $("#kb-url-name").value.trim();
    if (!url) return;

    $("#kb-add-url-btn").disabled = true;
    $("#kb-add-url-btn").textContent = "Adding…";

    try {
      const res = await fetch("/api/kb/add/url", {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: new URLSearchParams({ url, name, kb_name: "default" }),
      });
      const data = await res.json();
      if (data.status === "ok") {
        showToast("URL added to knowledge base!", "success");
        $("#kb-url-input").value = "";
        $("#kb-url-name").value = "";
        loadKB();
      } else {
        showToast(data.error || "Failed to add URL", "error");
      }
    } catch (e) {
      showToast(e.message, "error");
    }

    $("#kb-add-url-btn").disabled = false;
    $("#kb-add-url-btn").textContent = "Add URL";
  });

  // Add text
  $("#kb-add-text-btn").addEventListener("click", async () => {
    const content = $("#kb-text-input").value.trim();
    const name = $("#kb-text-name").value.trim();
    if (!content) return;

    $("#kb-add-text-btn").disabled = true;
    $("#kb-add-text-btn").textContent = "Adding…";

    try {
      const res = await fetch("/api/kb/add/text", {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: new URLSearchParams({ content, name: name || "Note", kb_name: "default" }),
      });
      const data = await res.json();
      if (data.status === "ok") {
        showToast("Text added to knowledge base!", "success");
        $("#kb-text-input").value = "";
        $("#kb-text-name").value = "";
        loadKB();
      } else {
        showToast(data.error || "Failed to add text", "error");
      }
    } catch (e) {
      showToast(e.message, "error");
    }

    $("#kb-add-text-btn").disabled = false;
    $("#kb-add-text-btn").textContent = "Add Text";
  });

  // Search KB
  $("#kb-search-btn").addEventListener("click", searchKB);
  $("#kb-search-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter") searchKB();
  });

  async function searchKB() {
    const query = $("#kb-search-input").value.trim();
    if (!query) return;

    $("#kb-search-btn").disabled = true;
    $("#kb-search-btn").textContent = "Searching…";
    elKBResults.innerHTML = '<div class="kb-loading"><span class="hint-spinner"></span> Searching…</div>';

    try {
      const res = await fetch("/api/kb/search", {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: new URLSearchParams({ query, kb_name: "default", top_k: "5" }),
      });
      const data = await res.json();
      renderKBResults(data.results || []);
    } catch (e) {
      elKBResults.innerHTML = `<div class="kb-empty">Search error: ${escapeHtml(e.message)}</div>`;
    }

    $("#kb-search-btn").disabled = false;
    $("#kb-search-btn").textContent = "Search";
  }

  function renderKBResults(results) {
    if (!results.length) {
      elKBResults.innerHTML = '<div class="kb-empty">No results found. Try different keywords.</div>';
      return;
    }

    elKBResults.innerHTML = results.map(r => `
      <div class="kb-result-item">
        <div class="kb-result-meta">
          📄 ${escapeHtml(r.doc_name || "Document")}
          <span class="kb-result-score">★ ${(r.similarity * 100).toFixed(0)}%</span>
        </div>
        <div class="kb-result-text">${escapeHtml(r.text || "").substring(0, 400)}${(r.text || "").length > 400 ? "…" : ""}</div>
      </div>
    `).join("");
  }

  // Load KB list
  async function loadKB() {
    try {
      const res = await fetch("/api/kb/list?kb_name=default");
      if (!res.ok) return;
      const data = await res.json();
      renderKBDocs(data.documents || [], data.stats || {});
    } catch (e) {
      elKBDocs.innerHTML = '<div class="kb-empty">Could not load documents.</div>';
    }
  }

  function renderKBDocs(docs, stats) {
    if (!docs.length) {
      elKBDocs.innerHTML = `
        <div class="kb-empty">
          <p>📭 No documents yet.</p>
          <p style="margin-top:6px;font-size:12px;color:var(--text-3)">
            Upload files, add URLs, or paste text above to build your knowledge base.
          </p>
        </div>`;
      return;
    }

    elKBDocs.innerHTML = docs.map(d => `
      <div class="kb-doc-item">
        <span class="kb-doc-icon">${getFileIcon(d.source_path || d.name)}</span>
        <div>
          <div class="kb-doc-name">${escapeHtml(d.name)}</div>
          <div class="kb-doc-meta">${d.chunks} chunks · ${d.source}</div>
        </div>
        <span class="kb-doc-delete" data-doc-id="${d.id}" title="Delete">✕</span>
      </div>
    `).join("");

    $$(".kb-doc-delete").forEach(btn => {
      btn.addEventListener("click", async () => {
        if (!confirm("Delete this document?")) return;
        try {
          await fetch(`/api/kb/document/${btn.dataset.docId}?kb_name=default`, { method: "DELETE" });
          showToast("Document deleted", "success");
          loadKB();
        } catch (e) {
          showToast(e.message, "error");
        }
      });
    });
  }

  function getFileIcon(name) {
    const ext = name.split(".").pop().toLowerCase();
    const icons = {
      pdf: "📕", docx: "📘", doc: "📘", txt: "📄", md: "📝",
      py: "🐍", js: "📜", ts: "📜", json: "📋", yaml: "⚙️",
      yml: "⚙️", csv: "📊", html: "🌐", css: "🎨",
      png: "🖼️", jpg: "🖼️", jpeg: "🖼️", gif: "🖼️", webp: "🖼️",
      url: "🔗",
    };
    return icons[ext] || "📄";
  }

  // ═══════════════════════════════════════════════════════════════
  // Models panel
  // ═══════════════════════════════════════════════════════════════
  async function loadModels() {
    try {
      const res = await fetch("/api/models");
      if (!res.ok) return;
      const data = await res.json();

      const listEl = $("#model-list");
      if (!data.models || !data.models.length) {
        listEl.innerHTML = '<div class="kb-empty">No models detected. Is Ollama running?</div>';
        return;
      }

      listEl.innerHTML = data.models.map(m => `
        <div class="model-item">
          <span>🤖</span>
          <span class="model-item-name">${escapeHtml(m.name)}</span>
          <span style="color:var(--text-3);font-size:11px">${m.size ? formatSize(m.size) : ""}</span>
        </div>
      `).join("");

      // Populate model dropdown
      const select = $("#cfg-model");
      select.innerHTML = '<option value="">— Select model —</option>' +
        data.models.map(m => `<option value="${m.name}">${m.name}</option>`).join("");
    } catch (e) {
      $("#model-list").innerHTML = '<div class="kb-empty">Could not load models.</div>';
    }
  }

  // Load config
  async function loadConfig() {
    try {
      const res = await fetch("/api/config");
      if (!res.ok) return;
      const data = await res.json();
      if (data.model) {
        providerName = data.model.provider || "ollama";
        modelName = data.model.name || "—";
        elModelName.textContent = modelName;
        $("#cfg-provider").value = providerName;
      }
    } catch (e) {}
    loadModels();
  }

  $("#cfg-provider").addEventListener("change", () => {
    showToast("Provider change requires server restart.", "info");
  });

  // ═══════════════════════════════════════════════════════════════
  // Keep-alive
  // ═══════════════════════════════════════════════════════════════
  setInterval(() => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "ping" }));
    }
  }, 30000);

  // ═══════════════════════════════════════════════════════════════
  // Init
  // ═══════════════════════════════════════════════════════════════
  connect();
  loadConfig();

  // Monkey-patch typing indicator off when status goes idle
  const origSetStatus = setStatus;
  setStatus = function (status, detail) {
    origSetStatus(status, detail);
    if (status === Status.IDLE || status === Status.TOOL) {
      elTyping.style.display = "none";
    }
  };

  // Expose for debugging
  window._greenchlaw = {
    getConversation: () => conversation,
    reconnect: () => { if (ws) ws.close(); connect(); },
    loadKB,
    loadTools,
    loadModels,
    ws: () => ws,
  };

})();
