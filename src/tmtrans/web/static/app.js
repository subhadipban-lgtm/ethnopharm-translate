/* tmtrans workbench UI */
const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];
const api = async (path, opts) => {
  const r = await fetch(path, opts);
  if (!r.ok) throw new Error((await r.json()).error || r.statusText);
  return r.json();
};
const esc = (s) => (s || "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
function toast(msg) { const t = $("#toast"); t.textContent = msg; t.style.display = "block";
  setTimeout(() => t.style.display = "none", 2600); }

$$("nav button").forEach(b => b.onclick = () => {
  $$("nav button").forEach(x => x.classList.remove("active"));
  b.classList.add("active");
  $$(".view").forEach(v => v.classList.remove("active"));
  $("#view-" + b.dataset.view).classList.add("active");
  if (b.dataset.view === "documents") loadDocuments();
  if (b.dataset.view === "review") loadReviewDocs();
  if (b.dataset.view === "candidates") loadCandidates();
  if (b.dataset.view === "glossary") loadGlossaryStats();
});

async function loadHealth() {
  try {
    const h = await api("/api/health");
    const b = h.backend, o = h.ocr || {};
    const state = b.kind === "mock" ? "mock (offline test)" :
      (b.endpoint && b.endpoint.ok ? "connected" : "unreachable — check your vLLM/Ollama server");
    const ostate = !o.kind || o.kind === "mock" ? "mock" :
      (o.endpoint && o.endpoint.ok ? "connected" : "unreachable");
    $("#backend-meta").textContent =
      `${b.model} · ${state} | OCR: ${o.model || "n/a"} · ${ostate} | glossary: ${h.glossary.entries} entries`;
  } catch (e) { $("#backend-meta").textContent = "server error"; }
}

async function loadDocuments() {
  const docs = await api("/api/documents");
  const tb = $("#doc-table tbody");
  tb.innerHTML = "";
  for (const d of docs) {
    const tr = document.createElement("tr");
    tr.className = "clickable";
    tr.innerHTML = `<td>${esc(d.title)}</td><td>${d.source_lang}</td>
      <td><span class="badge b-${d.status}">${d.status}</span></td>
      <td>${d.done_segments}/${d.total_segments}</td>
      <td>${d.auto_pass || 0}</td><td>${d.needs_review || 0}</td>
      <td>${d.approved || 0}</td><td>${d.failed || 0}</td>
      <td>${["jsonl","csv","xlsx","txt"].map(f =>
        `<a href="/api/documents/${d.id}/export/${f}" style="color:var(--accent)">${f}</a>`).join(" ")}</td>`;
    tr.onclick = () => showDocument(d.id);
    tb.appendChild(tr);
  }
}

async function showDocument(docId) {
  const segs = await api(`/api/documents/${docId}/segments`);
  $("#doc-detail").innerHTML = "<h3>Segments</h3>" + segs.map(renderSegment).join("");
  bindSegmentActions();
}

function renderSegment(s) {
  const gates = (s.report.results || []).filter(r => !r.passed && r.severity !== "info")
    .map(r => `<span class="gate-fail">✗ ${r.gate}: ${esc(r.detail)}</span>`).join(" · ");
  const terms = (s.terms || []).map(t =>
    `<span class="pill" title="${t.status}">${esc(t.source)} → ${esc(t.english)}</span>`).join("");
  return `<div class="seg" data-id="${s.id}">
    <div class="seg-head"><b>#${s.idx}</b><span class="badge b-${s.status}">${s.status}</span>
      ${s.modern_text ? '<span class="pill">classical→modern</span>' : ''}</div>
    <div class="seg-body">
      <div class="seg-src">${esc(s.source_text)}
        ${s.modern_text ? `<div class="small muted" style="margin-top:8px">modern: ${esc(s.modern_text)}</div>` : ''}</div>
      <div class="seg-tgt"><textarea data-role="translation">${esc(s.translation)}</textarea></div>
    </div>
    <div class="gates">${gates || '<span style="color:var(--green)">all gates passed</span>'}<br>${terms}</div>
    <div class="seg-actions">
      <button class="approve" data-act="approve">Approve</button>
      <button data-act="reject">Send back</button>
      <button data-act="retranslate">Retranslate</button>
      ${s.reviewed_by ? `<span class="muted small">reviewed by ${esc(s.reviewed_by)}</span>` : ''}
    </div></div>`;
}

function bindSegmentActions() {
  $$(".seg-actions button").forEach(btn => btn.onclick = async () => {
    const seg = btn.closest(".seg");
    const id = seg.dataset.id;
    const translation = seg.querySelector('[data-role="translation"]').value;
    if (btn.dataset.act === "retranslate") {
      await api(`/api/segments/${id}/retranslate`, {method: "POST"});
      toast("Retranslated");
    } else {
      await api(`/api/segments/${id}/review`, {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({translation, reviewer: "local", action: btn.dataset.act}),
      });
      toast(btn.dataset.act === "approve" ? "Approved — added to translation memory" : "Sent back to review");
    }
    const docSel = $("#rq-doc").value;
    if ($("#view-review").classList.contains("active") && docSel) loadReviewList();
  });
}

async function loadReviewDocs() {
  const docs = await api("/api/documents");
  $("#rq-doc").innerHTML = docs.map(d => `<option value="${d.id}">${esc(d.title)}</option>`).join("");
  if (docs.length) loadReviewList();
}
async function loadReviewList() {
  const doc = $("#rq-doc").value, status = $("#rq-status").value;
  const segs = await api(`/api/documents/${doc}/segments${status ? "?status=" + status : ""}`);
  $("#rq-list").innerHTML = segs.length ? segs.map(renderSegment).join("") : '<p class="muted">No segments in this state.</p>';
  bindSegmentActions();
}
$("#rq-load").onclick = loadReviewList;

$("#nt-submit").onclick = async () => {
  const body = {title: $("#nt-title").value || "untitled", text: $("#nt-text").value,
    source_lang: $("#nt-lang").value, variant: $("#nt-variant").value || null,
    tradition: $("#nt-tradition").value || null};
  if (!body.text.trim()) return toast("Paste some source text first");
  await api("/api/documents/text", {method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify(body)});
  toast("Translation started");
  $$("nav button")[0].click();
};

$("#nf-submit").onclick = async () => {
  const f = $("#nf-file").files[0];
  if (!f) return toast("Choose a file first");
  const fd = new FormData();
  fd.append("file", f); fd.append("source_lang", $("#nf-lang").value);
  if ($("#nf-variant").value) fd.append("variant", $("#nf-variant").value);
  await api("/api/documents/file", {method: "POST", body: fd});
  toast("Upload accepted — translation started");
  $$("nav button")[0].click();
};

async function loadGlossaryStats() {
  const h = await api("/api/health");
  $("#gl-stats").textContent = JSON.stringify(h.glossary.by_language) + " · " + JSON.stringify(h.glossary.by_category);
}
$("#gl-search").onclick = async () => {
  const res = await api("/api/glossary/search?q=" + encodeURIComponent($("#gl-q").value));
  $("#gl-results").innerHTML = res.length ? res.map(e =>
    `<div class="card"><b>${esc(e.source_form)}</b> → ${esc(e.english)}
     ${e.binomial ? `<i>${esc(e.binomial)}</i>` : ""}
     <div class="small muted">${e.entry_id} · ${e.category} · ${e.tradition || ""} ${e.pharmacopoeia || ""}
     ${e.variants && e.variants.length ? " · variants: " + esc(e.variants.join(", ")) : ""}</div></div>`).join("")
    : '<p class="muted">No match.</p>';
};

$("#ocr-submit").onclick = async () => {
  const folder = $("#ocr-folder").value.trim();
  if (!folder) return toast("Enter the scans folder path on the server");
  const body = {
    folder,
    title: $("#ocr-title").value || null,
    source_lang: $("#ocr-lang").value,
    variant: $("#ocr-variant").value || null,
    reading_order: $("#ocr-order").value,
    iast: $("#ocr-iast").checked,
    line_segmentation: $("#ocr-lineseg").value,
  };
  try {
    const r = await api("/api/ocr", {method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify(body)});
    toast(`OCR job started (doc ${r.document_id}) — watch progress in Documents`);
    $$("nav button")[0].click();
  } catch (e) { toast("OCR failed: " + e.message); }
};

async function loadCandidates() {
  const rows = await api("/api/term-candidates");
  $("#tc-table tbody").innerHTML = rows.map(r =>
    `<tr><td>${esc(r.source_form)}</td><td>${r.source_lang}</td><td>${r.occurrences}</td></tr>`).join("");
}

loadHealth();
loadDocuments();
setInterval(() => { if ($("#view-documents").classList.contains("active")) loadDocuments(); }, 5000);
