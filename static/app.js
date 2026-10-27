/* app.js - poora frontend (plain JavaScript, koi framework nahi).
   Flow: login -> token sessionStorage mein -> har API call mein "Authorization: Bearer <token>".
   Pages: hash routing (#/dashboard, #/complaints, ...). Server hi permissions enforce karta hai. */

const $ = (sel, root = document) => root.querySelector(sel);
// esc(): user/DB text ko HTML mein safe banata hai (XSS se bachne ke liye).
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (ch) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));

let TOKEN = sessionStorage.getItem("token");
let ME = JSON.parse(sessionStorage.getItem("me") || "null");
let META = null;

async function api(path, opts = {}) {
  const headers = { "Content-Type": "application/json" };
  if (TOKEN) headers.Authorization = "Bearer " + TOKEN;
  const res = await fetch(path, { ...opts, headers, body: opts.body ? JSON.stringify(opts.body) : undefined });
  if (res.status === 401 && path !== "/api/login") { logout(true); throw new Error("Please log in."); }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || "Something went wrong.");
  return data;
}

function toast(msg, bad = false) {
  const t = $("#toast");
  t.textContent = msg;
  t.className = "show" + (bad ? " bad" : "");
  setTimeout(() => (t.className = ""), 3200);
}

/* ---------- small UI helpers ---------- */
const STATUS_CLASS = { "Pending": "pending", "Under Process": "process", "Transferred": "transferred",
  "Escalated": "escalated", "Disposed": "disposed", "Potential": "potential", "Confirmed": "confirmed",
  "Dismissed": "dismissed" };
const badge = (s) => `<span class="badge ${STATUS_CLASS[s] || ""}">${esc(s)}</span>`;
const overdueBadge = (c) => (c.overdue ? ` <span class="badge overdue">Overdue ${Math.abs(c.days_left)}d</span>` : "");
const caseLink = (id) => `<a href="#/complaints/${encodeURIComponent(id)}">${esc(id)}</a>`;
const instLink = (id, name) => `<a href="#/institutions/${encodeURIComponent(id)}">${esc(name || id)}</a>`;
const fmtTs = (t) => esc((t || "").slice(0, 16));

function bars(items, key = "total") {
  const max = Math.max(1, ...items.map((i) => i[key]));
  return items.map((i) => `<div class="bar-row"><span>${esc(i.label)}</span>
    <div class="bar"><i style="width:${(100 * i[key]) / max}%"></i></div><b>${i[key]}</b></div>`).join("")
    || `<div class="empty">No data</div>`;
}

function table(cols, rows, rowHref) {
  if (!rows.length) return `<div class="empty">Nothing to show.</div>`;
  return `<div class="table-wrap"><table><thead><tr>${cols.map((c) => `<th>${esc(c.label)}</th>`).join("")}</tr></thead>
    <tbody>${rows.map((r) => `<tr class="${rowHref ? "clickable" : ""}">${cols.map((c) => `<td>${c.render(r)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
}

const complaintCols = [
  { label: "Complaint", render: (c) => caseLink(c.complaint_id) },
  { label: "Institution", render: (c) => instLink(c.institution_id, c.institution_name) },
  { label: "Category", render: (c) => esc(c.category) + `<div class="muted">${esc(c.subcategory)}</div>` },
  { label: "Bureau/Cell", render: (c) => esc(c.bureau) },
  { label: "Officer", render: (c) => esc(c.assigned_officer || "Unassigned") },
  { label: "Status", render: (c) => badge(c.status) + overdueBadge(c) + (c.overlap_count ? ' <span class="badge potential">Overlap</span>' : "") },
  { label: "Received", render: (c) => esc(c.date_received) },
  { label: "Due", render: (c) => esc(c.expected_disposal_date) },
];

/* ---------- auth ---------- */
const DEMO_USERS = [["head.office", "Supervisor"], ["a.sharma", "PGRC officer"]];

function showLogin() {
  $("#app").hidden = true;
  $("#login").hidden = false;
  $("#demo-buttons").innerHTML = DEMO_USERS.map(([u, l]) => `<button type="button" data-u="${u}">${l}</button>`).join("");
  $("#demo-buttons").onclick = (e) => {
    if (e.target.dataset.u) { $("#lu").value = e.target.dataset.u; $("#lp").value = "demo123"; }
  };
}

$("#login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  $("#login-error").textContent = "";
  try {
    const r = await api("/api/login", { method: "POST", body: { username: $("#lu").value, password: $("#lp").value } });
    TOKEN = r.token; ME = r.user;
    sessionStorage.setItem("token", TOKEN);
    sessionStorage.setItem("me", JSON.stringify(ME));
    await start();
  } catch (err) { $("#login-error").textContent = err.message; }
});

function logout(silent) {
  if (TOKEN && !silent) fetch("/api/logout", { method: "POST", headers: { Authorization: "Bearer " + TOKEN } });
  TOKEN = null; ME = null;
  sessionStorage.clear();
  showLogin();
}
$("#logout").onclick = () => logout(false);

/* ---------- app shell ---------- */
const PAGES = [["dashboard", "Dashboard"], ["complaints", "All complaints"], ["institutions", "Institutions"],
  ["overlaps", "Overlap detection"], ["coordination", "Coordination centre"], ["alerts", "Alerts"],
  ["reports", "Reports"], ["users", "Users and settings"]];

async function start() {
  META = await api("/api/meta");
  $("#login").hidden = true;
  $("#app").hidden = false;
  $("#nav").innerHTML = PAGES.map(([id, label]) => `<a href="#/${id}" data-page="${id}">${label}</a>`).join("");
  $("#me-name").textContent = ME.full_name;
  $("#me-role").textContent = ME.role + (ME.bureau ? " - " + ME.bureau : "");
  $("#banner").textContent = META.data_label + ". Last recorded action: " + (META.last_updated || "n/a");
  if (!location.hash) location.hash = "#/dashboard";
  route();
}

window.addEventListener("hashchange", () => TOKEN && route());

async function route() {
  const parts = location.hash.replace(/^#\//, "").split("?")[0].split("/").map(decodeURIComponent);
  const page = parts[0] || "dashboard";
  document.querySelectorAll("#nav a").forEach((a) => a.classList.toggle("active", a.dataset.page === page));
  const view = $("#view");
  view.innerHTML = `<div class="empty">Loading...</div>`;
  try {
    const fn = { dashboard, complaints, institutions, overlaps, coordination, alerts, reports, users }[page];
    if (!fn) { view.innerHTML = `<div class="empty">Page not found.</div>`; return; }
    await fn(view, parts[1]);
    view.focus({ preventScroll: true });
  } catch (err) {
    view.innerHTML = `<div class="panel error">${esc(err.message)}</div>`;
  }
}

/* ---------- 1. Dashboard ---------- */
async function dashboard(view) {
  const d = await api("/api/dashboard");
  const c = d.cards;
  const card = (n, label, href, cls = "") => `<a class="stat ${cls}" href="${href}"><div class="n">${n}</div><div class="muted">${label}</div></a>`;
  view.innerHTML = `
    <div class="page-head"><h1>Dashboard</h1><span class="muted">Counts recalculated on every load</span></div>
    <div class="cards">
      ${card(c.total, "Total received", "#/complaints")}
      ${card(c.pending, "Pending", "#/complaints?status=Pending")}
      ${card(c.under_process, "Under process", "#/complaints?status=Under Process")}
      ${card(c.disposed, "Disposed", "#/complaints?status=Disposed")}
      ${card(c.transferred, "Transferred", "#/complaints?status=Transferred")}
      ${card(c.escalated, "Escalated", "#/complaints?status=Escalated")}
      ${card(c.overdue, "Overdue", "#/complaints?overdue=1", "danger")}
      ${card(c.potential_overlaps, "Potential overlaps", "#/overlaps", "overlap")}
    </div>
    <div class="grid g2">
      <div class="panel"><h2>By Bureau/Cell</h2>${bars(d.by_bureau)}</div>
      <div class="panel"><h2>By status</h2>${bars(d.by_status)}</div>
      <div class="panel"><h2>By region</h2>${bars(d.by_region)}</div>
      <div class="panel"><h2>Institutions with most open cases</h2>
        ${table([{ label: "Institution", render: (r) => instLink(r.permanent_id, r.name) },
                 { label: "Open", render: (r) => r.open_cases }], d.top_institutions)}</div>
    </div>
    <p class="muted">Definitions: Overdue = not disposed and past its expected disposal date. Deadlines come from the configurable SLA table (demo placeholders).</p>`;
}

/* ---------- 2. Complaints list ---------- */
async function complaints(view, id) {
  if (id) return complaintDetail(view, id);
  const hashQuery = new URLSearchParams(location.hash.split("?")[1] || "");
  const f = Object.fromEntries(hashQuery.entries());
  const opts = (arr, sel) => `<option value="">All</option>` + arr.map((o) => `<option ${o === sel ? "selected" : ""}>${esc(o)}</option>`).join("");
  view.innerHTML = `
    <div class="page-head"><h1>All complaints</h1><span id="count" class="muted"></span></div>
    <div class="panel">
      <div class="filters">
        <label>Search<input id="f-q" placeholder="ID, institution, Permanent ID" value="${esc(f.q || "")}"></label>
        <label>Bureau/Cell<select id="f-bureau">${opts(META.bureaus.map((b) => b.code), f.bureau)}</select></label>
        <label>Category<select id="f-category">${opts(Object.keys(META.categories), f.category)}</select></label>
        <label>Status<select id="f-status">${opts(META.statuses, f.status)}</select></label>
        <label>Region<select id="f-region">${opts(META.regions, f.region)}</select></label>
        <label>Received from<input id="f-from" type="date"></label>
        <label>Received to<input id="f-to" type="date"></label>
        <label>Overdue only<select id="f-overdue"><option value="">No</option><option value="1" ${f.overdue ? "selected" : ""}>Yes</option></select></label>
      </div>
      <div id="list"></div>
    </div>`;
  let timer;
  const load = async () => {
    const p = new URLSearchParams();
    [["q", "f-q"], ["bureau", "f-bureau"], ["category", "f-category"], ["status", "f-status"], ["region", "f-region"],
     ["date_from", "f-from"], ["date_to", "f-to"], ["overdue", "f-overdue"]].forEach(([k, el]) => { const v = $("#" + el).value; if (v) p.set(k, v); });
    const data = await api("/api/complaints?" + p.toString());
    $("#count").textContent = data.count + " shown";
    $("#list").innerHTML = table(complaintCols, data.items, true);
  };
  view.querySelectorAll(".filters input, .filters select").forEach((el) =>
    el.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(() => load().catch((e) => toast(e.message, true)), 250); }));
  await load();
}

/* ---------- 3. Case details ---------- */
async function complaintDetail(view, id) {
  const d = await api("/api/complaints/" + encodeURIComponent(id));
  const c = d.complaint;
  const fact = (k, v) => `<dt>${k}</dt><dd>${v}</dd>`;
  const bureauOpts = META.bureaus.filter((b) => b.code !== c.bureau).map((b) => `<option value="${b.code}">${esc(b.name)}</option>`).join("");
  const statusOpts = META.statuses.filter((s) => s !== "Transferred" && s !== c.status).map((s) => `<option>${esc(s)}</option>`).join("");
  const isSenior = ME.role === "admin" || ME.role === "supervisor";
  view.innerHTML = `
    <div class="page-head"><div><a href="#/complaints">&larr; All complaints</a>
      <h1>${esc(c.complaint_id)} ${badge(c.status)}${overdueBadge(c)}</h1></div></div>
    <div class="grid g2">
      <div class="panel"><h2>Case details</h2><dl class="facts">
        ${fact("Institution", instLink(d.institution.permanent_id, d.institution.name) + `<div class="muted">${esc(d.institution.permanent_id)} - ${esc(d.institution.city)}, ${esc(d.institution.region)}</div>`)}
        ${fact("Category", esc(c.category) + " / " + esc(c.subcategory))}
        ${fact("Description", esc(c.description))}
        ${fact("Responsible", esc(c.bureau) + " - " + esc(c.assigned_officer || "Unassigned"))}
        ${fact("Received", esc(c.date_received) + " via " + esc(c.source_channel))}
        ${fact("Original ID", esc(c.source_ref) + `<div class="muted">${esc(c.source_system)}</div>`)}
        ${c.external_ref ? fact("External ref", esc(c.external_ref)) : ""}
        ${fact("Last action", esc(c.last_action) + `<div class="muted">${esc(c.last_action_date)}</div>`)}
        ${fact("Next action", esc(c.next_action))}
        ${fact("Expected disposal", esc(c.expected_disposal_date) + `<div class="muted">SLA ${esc(c.sla_days)} days (demo placeholder)</div>`)}
        ${fact("Procedure", esc(c.applicable_procedure))}
        ${fact("Complainant", esc(c.complainant_name) + " / " + esc(c.complainant_contact))}
      </dl></div>
      <div>
        <div class="panel"><h2>Related cases</h2>
          ${d.overlaps.length ? d.overlaps.map((o) => `<p><a href="#/overlaps/${o.id}">Alert #${o.id}</a>: ${caseLink(o.complaint_a)} + ${caseLink(o.complaint_b)} ${badge(o.status)} <span class="muted">score ${o.score}, coordination: ${esc(o.coordination_status)}</span></p>`).join("") : `<div class="muted">No overlap alerts for this case.</div>`}
        </div>
        <div class="panel actions"><h2>Take action</h2>
          ${d.can_act ? `
          <form data-act="update_status"><div class="row"><label>New status<select name="to_status">${statusOpts}</select></label>
            <label>Next action<input name="next_action"></label></div>
            <label>Remarks (required to dispose)<textarea name="remarks"></textarea></label><button class="primary">Update status</button></form>
          <form data-act="transfer"><div class="row"><label>Transfer to<select name="to_bureau">${bureauOpts}</select></label></div>
            <label>Reason for transfer<textarea name="remarks"></textarea></label><button>Transfer case</button></form>
          <form data-act="escalate"><label>Reason to escalate<textarea name="remarks"></textarea></label><button>Escalate</button></form>
          <form data-act="remark"><label>Add a remark<textarea name="remarks"></textarea></label><button>Save remark</button></form>
          ${isSenior ? `<form data-act="correct"><div class="row"><label>Category<select name="category">${Object.keys(META.categories).map((k) => `<option ${k === c.category ? "selected" : ""}>${esc(k)}</option>`).join("")}</select></label>
            <label>Bureau/Cell<select name="bureau">${META.bureaus.map((b) => `<option value="${b.code}" ${b.code === c.bureau ? "selected" : ""}>${b.code}</option>`).join("")}</select></label></div>
            <label>Reason for correction<textarea name="remarks"></textarea></label><button>Correct record</button></form>` : ""}`
          : `<div class="muted">Your role/bureau cannot change this case. You can view it.</div>`}
        </div>
      </div>
    </div>
    <div class="panel"><h2>Action history</h2><ol class="timeline">
      ${d.history.map((h) => `<li><div><b>${esc(h.action)}</b> ${h.from_status && h.to_status && h.from_status !== h.to_status ? `<span class="muted">${esc(h.from_status)} to ${esc(h.to_status)}</span>` : ""}
        ${h.from_bureau && h.to_bureau ? `<span class="muted">${esc(h.from_bureau)} to ${esc(h.to_bureau)}</span>` : ""}</div>
        <div class="when">${fmtTs(h.ts)} - ${esc(h.actor)} (${esc(h.actor_bureau || "")})</div>
        ${h.remarks ? `<div>${esc(h.remarks)}</div>` : ""}</li>`).join("")}</ol></div>`;
  view.querySelectorAll("form[data-act]").forEach((form) => form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const body = Object.fromEntries(new FormData(form).entries());
    body.action = form.dataset.act;
    try { await api(`/api/complaints/${encodeURIComponent(id)}/action`, { method: "POST", body }); toast("Saved."); await complaintDetail(view, id); }
    catch (err) { toast(err.message, true); }
  }));
}

/* ---------- 4. Institutions ---------- */
async function institutions(view, id) {
  if (id) return institutionDetail(view, id);
  view.innerHTML = `<div class="page-head"><h1>Institutions</h1></div><div class="panel">
    <label>Search by name or AICTE Permanent ID<input id="iq" placeholder="e.g. College A or SYN-00001"></label><div id="ilist"></div></div>`;
  const cols = [
    { label: "Institution", render: (i) => instLink(i.permanent_id, i.name) + `<div class="muted">${esc(i.permanent_id)}</div>` },
    { label: "Region", render: (i) => esc(i.region) }, { label: "Total", render: (i) => i.total },
    { label: "Open", render: (i) => i.open_cases || 0 },
    { label: "Overdue", render: (i) => (i.overdue ? `<span class="badge overdue">${i.overdue}</span>` : "0") },
    { label: "Potential overlaps", render: (i) => (i.potential_overlaps ? `<span class="badge potential">${i.potential_overlaps}</span>` : "0") }];
  let timer;
  const load = async () => { const d = await api("/api/institutions?q=" + encodeURIComponent($("#iq").value)); $("#ilist").innerHTML = table(cols, d.items, true); };
  $("#iq").addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(load, 250); });
  await load();
}

async function institutionDetail(view, id) {
  const d = await api("/api/institutions/" + encodeURIComponent(id));
  const i = d.institution;
  const open = Object.entries(d.open_by_bureau).map(([b, n]) => `<span class="badge process">${esc(b)}: ${n} open</span>`).join(" ") || "No open cases";
  const potential = d.overlaps.filter((o) => o.status === "Potential");
  view.innerHTML = `
    <div class="page-head"><div><a href="#/institutions">&larr; Institutions</a><h1>${esc(i.name)}</h1>
      <div class="muted">${esc(i.permanent_id)} - ${esc(i.address)}, ${esc(i.state)} - ${esc(i.region)} region - ${esc(i.institution_type)}</div></div></div>
    <div class="panel"><h2>At a glance</h2><p>${open}</p>
      <p>${d.overdue ? `<span class="badge overdue">${d.overdue} overdue</span>` : ""} ${potential.length ? `<span class="badge potential">${potential.length} potential overlap(s) - coordination may be required</span>` : ""}</p>
      ${d.overlaps.map((o) => `<p><a href="#/overlaps/${o.id}">Alert #${o.id}</a>: ${caseLink(o.complaint_a)} + ${caseLink(o.complaint_b)} ${badge(o.status)}</p>`).join("")}</div>
    <div class="panel"><h2>All complaints (${d.complaints.length})</h2>${table(complaintCols.filter((c) => c.label !== "Institution"), d.complaints, true)}</div>
    <div class="panel"><h2>Complete complaint history (latest 100 actions)</h2><ol class="timeline">
      ${d.history.map((h) => `<li><b>${esc(h.action)}</b> - ${caseLink(h.complaint_id)}<div class="when">${fmtTs(h.ts)} - ${esc(h.actor)} (${esc(h.actor_bureau || "")})</div>${h.remarks ? `<div>${esc(h.remarks)}</div>` : ""}</li>`).join("")}</ol></div>`;
}

/* ---------- 5. Overlap detection ---------- */
async function overlaps(view, id) {
  if (id) return overlapDetail(view, id);
  const d = await api("/api/overlaps");
  const canRun = ME.role !== "viewer";
  const cols = [
    { label: "Alert", render: (o) => `<a href="#/overlaps/${o.id}">#${o.id}</a>` },
    { label: "Institution", render: (o) => instLink(o.institution_id, o.institution_name) },
    { label: "Case A", render: (o) => caseLink(o.complaint_a) + `<div class="muted">${esc(o.bureau_a)} - ${esc(o.status_a)}</div>` },
    { label: "Case B", render: (o) => caseLink(o.complaint_b) + `<div class="muted">${esc(o.bureau_b)} - ${esc(o.status_b)}</div>` },
    { label: "Score", render: (o) => o.score },
    { label: "Review", render: (o) => badge(o.status) }, { label: "Coordination", render: (o) => esc(o.coordination_status) }];
  view.innerHTML = `<div class="page-head"><div><h1>Overlap detection</h1>
    <div class="muted">System flags possible overlaps for review. It never merges, closes or decides duplicates.</div></div>
    ${canRun ? `<button id="run" class="primary">Re-run detection</button>` : ""}</div>
    <div class="panel">${table(cols, d.items, true)}</div>`;
  const run = $("#run");
  if (run) run.onclick = async () => { try { const r = await api("/api/overlaps/detect", { method: "POST" }); toast(`New: ${r.created}, potential total: ${r.potential_total}`); route(); } catch (e) { toast(e.message, true); } };
}

async function overlapDetail(view, id) {
  const d = await api("/api/overlaps/" + id);
  const { a, b, alert } = d;
  const row = (label, va, vb, match) => `<div class="f ${match ? "match" : ""}"><span>${label}</span><span>${va}</span></div>`;
  const same = (k) => a[k] && a[k] === b[k];
  const col = (c, other) => `<div class="col"><h3>${caseLink(c.complaint_id)} ${badge(c.status)}</h3>
    ${row("Bureau/Cell", esc(c.bureau), "", c.bureau === other.bureau)}${row("Officer", esc(c.assigned_officer || "Unassigned"))}
    ${row("Category", esc(c.category), "", same("category"))}${row("Subcategory", esc(c.subcategory), "", same("subcategory"))}
    ${row("Issue", esc(c.description))}${row("Received", esc(c.date_received))}
    ${row("Last action", esc(c.last_action) + " (" + esc(c.last_action_date) + ")")}${row("Next action", esc(c.next_action))}
    ${row("Due", esc(c.expected_disposal_date) + (c.overdue ? " (overdue)" : ""))}${c.external_ref ? row("External ref", esc(c.external_ref), "", same("external_ref")) : ""}</div>`;
  const reviewed = alert.status !== "Potential";
  view.innerHTML = `
    <div class="page-head"><div><a href="#/overlaps">&larr; Overlap detection</a><h1>Alert #${alert.id} ${badge(alert.status)}</h1>
      <div class="muted">${instLink(d.institution.permanent_id, d.institution.name)} (${esc(d.institution.permanent_id)})</div></div>
      <div class="score">Match score ${alert.score}/100</div></div>
    <div class="panel"><h2>Why this was flagged</h2><ul class="reasons">${alert.reasons.map((r) => `<li>${esc(r)}</li>`).join("")}</ul>
      <p class="muted">A high score means "worth a human look". It does not mean the complaints are duplicates.</p></div>
    <div class="legend"><i></i>Highlighted rows match on both sides</div>
    <div class="compare">${col(a, b)}${col(b, a)}</div>
    <div class="grid g2" style="margin-top:1rem">
      <div class="panel"><h2>Official review</h2>
        ${reviewed ? `<p>${badge(alert.status)} by ${esc(alert.reviewed_by)} on ${fmtTs(alert.reviewed_at)}</p><div class="note">${esc(alert.review_remarks)}</div>`
        : d.can_review ? `<form id="review"><label>Remarks (required)<textarea name="remarks"></textarea></label>
          <div class="row"><button class="primary" data-d="confirm">Confirm and link cases</button><button class="danger" data-d="dismiss">Dismiss alert</button></div></form>`
        : `<div class="muted">Only officers of the involved Bureaus/Cells or a supervisor can review.</div>`}
        ${d.links.length ? `<p class="muted">Linked on ${fmtTs(d.links[0].linked_at)} by ${esc(d.links[0].linked_by)}. Both records remain separate.</p>` : ""}</div>
      <div class="panel"><h2>Coordination record</h2>
        <p>Status: <b>${esc(alert.coordination_status)}</b></p>
        ${d.notes.length ? d.notes.map((n) => `<div class="note"><b>${esc(n.username)}</b> (${esc(n.bureau)}) <span class="muted">${fmtTs(n.ts)}</span><br>${esc(n.remark)}${n.decision ? `<br><span class="badge confirmed">Decision: ${esc(n.decision)}</span>` : ""}</div>`).join("") : `<div class="muted">No remarks yet.</div>`}
        ${d.can_review && alert.status !== "Dismissed" ? `<form id="coord"><label>Coordination remark<textarea name="remark"></textarea></label>
          <label>Decision (optional)<select name="decision"><option value="">No decision yet</option>${d.decisions.map((x) => `<option>${esc(x)}</option>`).join("")}</select></label>
          <button class="primary">Save coordination remark</button></form>` : ""}</div></div>`;
  const rf = $("#review");
  if (rf) rf.addEventListener("submit", async (e) => {
    e.preventDefault();
    const decision = e.submitter && e.submitter.dataset.d;
    try { await api(`/api/overlaps/${id}/review`, { method: "POST", body: { decision, remarks: rf.remarks.value } }); toast("Review recorded."); overlapDetail(view, id); }
    catch (err) { toast(err.message, true); }
  });
  const cf = $("#coord");
  if (cf) cf.addEventListener("submit", async (e) => {
    e.preventDefault();
    try { await api(`/api/overlaps/${id}/coordination`, { method: "POST", body: { remark: cf.remark.value, decision: cf.decision.value } }); toast("Coordination remark saved."); overlapDetail(view, id); }
    catch (err) { toast(err.message, true); }
  });
}

/* ---------- 6. Coordination centre ---------- */
async function coordination(view) {
  const d = await api("/api/alerts");
  const cols = [
    { label: "Alert", render: (o) => `<a href="#/overlaps/${o.id}">#${o.id}</a>` },
    { label: "Institution", render: (o) => instLink(o.institution_id, o.institution_name) },
    { label: "Cases", render: (o) => caseLink(o.complaint_a) + " + " + caseLink(o.complaint_b) },
    { label: "Review", render: (o) => badge(o.status) }, { label: "Coordination", render: (o) => esc(o.coordination_status) }];
  view.innerHTML = `<div class="page-head"><div><h1>Coordination centre</h1>
    <div class="muted">Alerts where Bureaus/Cells still need to record a coordination decision</div></div></div>
    <div class="panel">${table(cols, d.coordination_required, true)}</div>`;
}

/* ---------- 7. Alerts ---------- */
async function alerts(view) {
  const d = await api("/api/alerts");
  const cols = [{ label: "Complaint", render: (c) => caseLink(c.complaint_id) },
    { label: "Institution", render: (c) => instLink(c.institution_id, c.institution_name) },
    { label: "Bureau/Cell", render: (c) => esc(c.bureau) }, { label: "Status", render: (c) => badge(c.status) },
    { label: "Due", render: (c) => esc(c.expected_disposal_date) + ` <span class="muted">(${c.days_left}d)</span>` },
    { label: "Last action", render: (c) => esc(c.last_action_date) + ` <span class="muted">(${c.days_since_action}d ago)</span>` }];
  const sec = (title, note, html) => `<div class="panel"><h2>${title}</h2><div class="muted" style="margin-bottom:.5rem">${note}</div>${html}</div>`;
  view.innerHTML = `<div class="page-head"><h1>Alerts and pending cases</h1></div>
    ${sec(`Overdue (${d.overdue.length})`, "Past the expected disposal date", table(cols, d.overdue.slice(0, 50)))}
    ${sec(`Approaching deadline (${d.approaching.length})`, `Due within ${d.settings.approaching_days} days`, table(cols, d.approaching))}
    ${sec(`No recent action (${d.no_recent_action.length})`, `No action for more than ${d.settings.stale_days} days`, table(cols, d.no_recent_action.slice(0, 50)))}
    ${sec(`Potential overlaps (${d.potential_overlaps.length})`, "Awaiting official review", table([
      { label: "Alert", render: (o) => `<a href="#/overlaps/${o.id}">#${o.id}</a>` },
      { label: "Institution", render: (o) => instLink(o.institution_id, o.institution_name) },
      { label: "Cases", render: (o) => caseLink(o.complaint_a) + " + " + caseLink(o.complaint_b) },
      { label: "Score", render: (o) => o.score }], d.potential_overlaps.slice(0, 50)))}`;
}

/* ---------- 8. Reports ---------- */
const REPORT_LABELS = { bureau: "Bureau/Cell-wise", region: "Region-wise", status: "Status-wise", overdue: "Overdue cases",
  institution: "Institution-wise history", overlaps: "Potential overlaps", ageing: "Ageing and disposal", monthly: "Monthly received vs disposed" };

async function reports(view, kind) {
  kind = kind || "bureau";
  const d = await api("/api/reports/" + kind);
  const canExport = ME.role === "admin" || ME.role === "supervisor";
  view.innerHTML = `<div class="page-head"><h1>Reports and analytics</h1>
    <div class="row" style="flex:0 0 auto"><select id="rk" aria-label="Report type">${d.kinds.map((k) => `<option value="${k}" ${k === kind ? "selected" : ""}>${REPORT_LABELS[k]}</option>`).join("")}</select>
    ${canExport ? `<button id="csv">Export CSV</button>` : ""}</div></div>
    <div class="panel"><h2>${esc(d.title)}</h2><div class="muted">Generated ${esc(d.generated_at)} - ${esc(d.data_label)}</div>
    ${table(d.columns.map((c) => ({ label: c.replace(/_/g, " "), render: (r) => esc(r[c]) })), d.rows)}</div>`;
  $("#rk").onchange = (e) => (location.hash = "#/reports/" + e.target.value);
  const csv = $("#csv");
  if (csv) csv.onclick = async () => {
    const res = await fetch(`/api/reports/${kind}?format=csv`, { headers: { Authorization: "Bearer " + TOKEN } });
    if (!res.ok) return toast((await res.json()).error, true);
    const url = URL.createObjectURL(await res.blob());
    const a = document.createElement("a"); a.href = url; a.download = `report_${kind}.csv`; a.click(); URL.revokeObjectURL(url);
    toast("Exported (logged in the audit trail).");
  };
}

/* ---------- 9. Users and settings ---------- */
async function users(view) {
  const s = await api("/api/settings");
  const sla = table([{ label: "Category", render: (r) => esc(r.category) }, { label: "Days", render: (r) => r.days }, { label: "Note", render: (r) => esc(r.note) }], s.sla_rules);
  let adminHtml = `<div class="panel"><div class="muted">User list and audit log are visible to administrators only.</div></div>`;
  if (ME.role === "admin") {
    const [u, a] = await Promise.all([api("/api/users"), api("/api/audit")]);
    adminHtml = `<div class="panel"><h2>Users</h2>${table([{ label: "Username", render: (r) => esc(r.username) }, { label: "Name", render: (r) => esc(r.full_name) },
      { label: "Role", render: (r) => esc(r.role) }, { label: "Bureau/Cell", render: (r) => esc(r.bureau || "-") }], u.items)}</div>
      <div class="panel"><h2>Audit log (latest 100)</h2>${table([{ label: "When", render: (r) => fmtTs(r.ts) }, { label: "User", render: (r) => esc(r.username) },
      { label: "Action", render: (r) => esc(r.action) }, { label: "Item", render: (r) => esc(r.entity + " " + r.entity_id) }], a.items)}</div>`;
  }
  view.innerHTML = `<div class="page-head"><h1>Users and settings</h1></div>${adminHtml}
    <div class="panel"><h2>Deadlines (SLA) by category</h2><div class="muted">Placeholders until AICTE's prescribed timelines are configured.</div>${sla}
    <p class="muted">Alert thresholds: approaching ${esc(s.settings.approaching_days)} days, no-action ${esc(s.settings.stale_days)} days, overlap score ${esc(s.settings.overlap_threshold)}.</p></div>
    <div class="panel"><h2>Status definitions</h2><dl class="facts">${Object.entries(META.definitions).map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join("")}</dl></div>`;
}

/* ---------- boot ---------- */
if (TOKEN && ME) start().catch(() => logout(true)); else showLogin();
