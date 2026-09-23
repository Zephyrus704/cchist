// SPDX-License-Identifier: MIT
const $ = (s) => document.querySelector(s);
const state = { q: "", fulltext: false, sort: "time", reverse: true, trash: false, active: null, favoritesOnly: false };
let L = {};  // 语言文案,启动时从 /api/lang 载入

function toast(msg) {
  const t = $("#toast");
  t.textContent = msg;
  t.classList.add("show");
  clearTimeout(t._timer);
  t._timer = setTimeout(() => t.classList.remove("show"), 2200);
}

async function api(url, opts) {
  const r = await fetch(url, opts);
  if (!r.ok) { toast("Error: " + r.status); throw new Error(r.status); }
  return r.json();
}

function applyStaticLabels() {
  $("#search").placeholder = L.search;
  $("#tagline").textContent = L.tagline;
  $("#statsBtn").textContent = L.stats;
  $("#cleanupBtn").textContent = L.cleanup;
  $("#shutdownBtn").textContent = L.shutdown;
  $("#trashBtn").innerHTML = `${L.trash} <span id="trashCount" class="badge">0</span>`;
  $("#fulltextLabel").childNodes[1].textContent = " " + L.fulltext;
  $("#sortTime").textContent = L.sort_time;
  $("#sortProject").textContent = L.sort_project;
  $("#sortTurns").textContent = L.sort_turns;
  $("#sortSize").textContent = L.sort_size;
  $("#detailPlaceholder").textContent = L.select_hint;
  $("#statsModalTitle").textContent = L.stats_title;
  $("#favsBtn").textContent = L.favorites_only;
  $("#ignoredBtn").textContent = L.manage_ignored;
  $("#ignoredModalTitle").textContent = L.ignored_title;
}

async function loadStats() {
  const s = await api("/api/stats");
  $("#stats").innerHTML = `
    <div class="stat"><div class="num">${s.total}</div><div class="lbl">${L.total}</div></div>
    <div class="stat"><div class="num">${s.projects.length}</div><div class="lbl">${L.projects}</div></div>
    <div class="stat"><div class="num">${fmtSize(s.total_size)}</div><div class="lbl">${L.used}</div></div>
  `;
  $("#trashCount").textContent = s.trash;
}

function fmtSize(b) {
  const u = ["B","K","M","G"]; let i = 0;
  while (b >= 1024 && i < u.length-1) { b /= 1024; i++; }
  return (i === 0 ? b.toFixed(0) : b.toFixed(1)) + u[i];
}

async function loadList() {
  const p = new URLSearchParams({
    q: state.q, fulltext: state.fulltext, sort: state.sort,
    reverse: state.reverse, trash: state.trash,
    favorites_only: state.favoritesOnly,
  });
  const data = await api("/api/sessions?" + p);
  const list = $("#list");
  if (!data.sessions.length) {
    list.innerHTML = emptyStateHTML();
    return;
  }
  list.innerHTML = data.sessions.map(cardHTML).join("");
  data.sessions.forEach((s) => {
    $(`#card-${s.session_id}`).addEventListener("click", () => showDetail(s.session_id));
  });
}

function emptyStateHTML() {
  if (state.q) {
    return `<div class="empty-state"><div class="big">${L.no_match}</div>${L.empty_hint}</div>`;
  }
  if (state.trash) {
    return `<div class="empty-state"><div class="big">${L.trash_empty}</div></div>`;
  }
  return `<div class="empty-state">
    <div class="big">${L.no_sessions}</div>
    <code>CLAUDE_CONFIG_DIR</code> / <code>CODEX_HOME</code>
  </div>`;
}

function cardHTML(s) {
  const tags = [];
  if (s.favorite) tags.push(`<span class="tag fav">★</span>`);
  if (s.is_trivial) tags.push(`<span class="tag empty">·</span>`);
  if (s.is_orphan) tags.push(`<span class="tag orphan">⚠</span>`);
  const tail = (s.last_user_msg && s.last_user_msg !== s.first_msg) ? s.last_user_msg : "";
  const title = tail ? `${esc(s.first_msg)}　→　${esc(tail)}` : esc(s.first_msg);
  const provTag = `<span class="tag prov prov-${s.provider}">${esc(s.provider_label)}</span>`;
  return `
  <div class="card ${s.is_trivial ? "trivial" : ""} ${state.active===s.session_id?"active":""}" id="card-${s.session_id}">
    <div class="card-top">
      ${provTag}
      <span class="card-proj">${esc(s.project_label)}</span>
      ${tags.join("")}
      <span class="card-meta">
        <span class="turns">${s.user_turns}/${s.assistant_turns}</span>
        <span>${s.size_str}</span>
        <span>${s.mtime_str}</span>
      </span>
    </div>
    <div class="card-title">${title}</div>
    <div class="card-path ${s.is_orphan?"orphan":""}">${esc(s.short_path)}</div>
  </div>`;
}

async function showDetail(id) {
  state.active = id;
  document.querySelectorAll(".card").forEach(c => c.classList.remove("active"));
  $(`#card-${id}`)?.classList.add("active");
  const d = await api(`/api/session/${id}`);
  const det = $("#detail");
  det.classList.remove("empty");
  const favLabel = d.favorite ? L.faved : L.fav;
  const trashBtns = state.trash
    ? `<button class="btn-primary" onclick="restoreS('${id}')">${L.restore}</button>
       <button onclick="deleteS('${id}')">${L.delete_perm}</button>`
    : `<button onclick="toggleFav('${id}')">${favLabel}</button>
       <button onclick="exportS('${id}')">${L.export}</button>
       <button onclick="trashS('${id}')">${L.to_trash}</button>`;
  det.innerHTML = `
    <h2>${esc(d.first_msg)}</h2>
    <div class="detail-sub">${esc(d.provider_label)} · ${esc(d.short_path)} · ${d.session_id}</div>
    <div class="detail-actions">${trashBtns}</div>
    <div class="resume-box">
      <code>${esc(d.resume_cmd)}</code>
      <button onclick="copyCmd(this,'${esc(d.resume_cmd)}')">${L.copy}</button>
    </div>
    <div class="messages">
      ${d.messages.map(m => `
        <div class="msg ${m.role}">
          <div class="role">${m.role==="user"?L.me:"Assistant"}</div>
          <div class="body">${esc(m.text)}</div>
        </div>`).join("")}
    </div>`;
}

async function toggleFav(id) { const r = await api(`/api/session/${id}/favorite`, {method:"POST"}); toast(r.favorite?L.faved:L.fav); showDetail(id); loadList(); }
async function trashS(id) { if(!confirm(L.confirm_trash)) return; await api(`/api/session/${id}/trash`, {method:"POST"}); toast(L.to_trash); state.active=null; $("#detail").className="detail empty"; $("#detail").innerHTML=`<div class="detail-placeholder">${L.select_hint}</div>`; loadList(); loadStats(); }
async function restoreS(id) { await api(`/api/session/${id}/restore`, {method:"POST"}); toast(L.restore); loadList(); loadStats(); }
async function deleteS(id) { if(!confirm(L.confirm_delete)) return; await api(`/api/session/${id}`, {method:"DELETE"}); toast("OK"); loadList(); loadStats(); }
function copyCmd(btn, cmd) { navigator.clipboard.writeText(cmd).then(()=>{ btn.textContent=L.copied; setTimeout(()=>btn.textContent=L.copy,1500); }); }

function exportS(id) { window.location.href = `/api/session/${id}/export`; }

async function cleanup() {
  if (!confirm(L.confirm_cleanup)) return;
  const r = await api("/api/cleanup", {method:"POST"});
  toast(`${r.cleaned}${r.errors?` (${r.errors} failed)`:""}`);
  loadList(); loadStats();
}

async function showIgnored() {
  const data = await api("/api/ignored");
  const body = $("#ignoredBody");
  if (!data.dirs.length) {
    body.innerHTML = `<p style="color:var(--muted)">${L.ignored_empty}</p>`;
  } else {
    body.innerHTML = `<ul class="ignored-list">${
      data.dirs.map(d => `
        <li class="ignored-item">
          <span class="ignored-path">${esc(d)}</span>
          <button class="btn-sm danger" onclick="unignore(this,'${esc(d)}')">${L.ignored_removed}</button>
        </li>`).join("")
    }</ul>`;
  }
  $("#ignoredModal").classList.remove("hidden");
}

async function unignore(btn, path) {
  await api(`/api/ignored/${encodeURIComponent(path)}`, {method:"DELETE"});
  toast(L.ignored_removed + ": " + path);
  showIgnored();
  loadList();
}

async function shutdown() {
  if (!confirm(L.confirm_shutdown)) return;
  try { await fetch("/api/shutdown", {method:"POST"}); } catch(e) {}
  document.body.innerHTML = `<div style="display:flex;align-items:center;justify-content:center;height:100vh;color:#8b949e;font-size:18px;flex-direction:column;gap:10px">
    <div>${L.stopped}</div><div style="font-size:13px">${L.can_close}</div></div>`;
}

async function showStats() {
  const [s, d] = await Promise.all([api("/api/stats"), api("/api/daily")]);
  const maxDay = Math.max(1, ...d.daily.map(x=>x.count));
  const spark = d.daily.map(x => {
    const h = Math.round(x.count/maxDay*100);
    return `<div class="spark-bar" style="height:${h}%"><span class="tip">${x.date}: ${x.count}</span></div>`;
  }).join("");
  const firstDay = d.daily[0]?.date || "", lastDay = d.daily[d.daily.length-1]?.date || "";
  const maxProj = Math.max(1, ...s.projects.map(p=>p.count));
  const bars = s.projects.slice(0,12).map(p => {
    const w = Math.round(p.count/maxProj*100);
    return `<div class="bar-row"><span class="bar-label">${esc(p.name)}</span>
      <span class="bar-track"><span class="bar-fill" style="width:${w}%">${p.count}</span></span></div>`;
  }).join("");
  $("#statsBody").innerHTML = `
    <div class="chart-section">
      <h3>${L.daily_title}</h3>
      <div class="spark">${spark}</div>
      <div class="spark-axis"><span>${firstDay}</span><span>${lastDay}</span></div>
    </div>
    <div class="chart-section">
      <h3>${L.proj_title}</h3>
      ${bars}
    </div>
    <div class="chart-section">
      <h3>${L.overview}</h3>
      <div class="bar-row"><span class="bar-label">${L.total}</span><b style="color:var(--accent)">${s.total}</b></div>
      <div class="bar-row"><span class="bar-label">${L.empty_count}</span><b>${s.trivial}</b></div>
      <div class="bar-row"><span class="bar-label">${L.orphan_count}</span><b>${s.orphan}</b></div>
      <div class="bar-row"><span class="bar-label">${L.trash}</span><b>${s.trash}</b></div>
    </div>`;
  $("#statsModal").classList.remove("hidden");
}

function esc(s) { return (s||"").replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }

// 事件绑定
let searchTimer;
$("#search").addEventListener("input", (e) => { clearTimeout(searchTimer); searchTimer = setTimeout(()=>{ state.q = e.target.value; loadList(); }, 250); });
$("#fulltext").addEventListener("change", (e) => { state.fulltext = e.target.checked; loadList(); });
$("#sort").addEventListener("change", (e) => { state.sort = e.target.value; loadList(); });
$("#reverse").addEventListener("click", (e) => { state.reverse = !state.reverse; e.target.textContent = state.reverse ? "↓" : "↑"; loadList(); });
$("#trashBtn").addEventListener("click", () => {
  state.trash = !state.trash;
  $("#trashBtn").classList.toggle("btn-primary", state.trash);
  $("#trashBtn").firstChild.textContent = (state.trash ? L.back : L.trash) + " ";
  loadList();
});

$("#statsBtn").addEventListener("click", showStats);
$("#cleanupBtn").addEventListener("click", cleanup);
$("#shutdownBtn").addEventListener("click", shutdown);
$("#statsClose").addEventListener("click", () => $("#statsModal").classList.add("hidden"));
$("#statsModal").addEventListener("click", (e) => { if (e.target.id === "statsModal") $("#statsModal").classList.add("hidden"); });

$("#favsBtn").addEventListener("click", () => {
  state.favoritesOnly = !state.favoritesOnly;
  $("#favsBtn").classList.toggle("btn-primary", state.favoritesOnly);
  loadList();
});

$("#ignoredBtn").addEventListener("click", showIgnored);
$("#ignoredClose").addEventListener("click", () => $("#ignoredModal").classList.add("hidden"));
$("#ignoredModal").addEventListener("click", (e) => { if (e.target.id === "ignoredModal") $("#ignoredModal").classList.add("hidden"); });

// 初始化:先载入语言,再渲染
(async function init() {
  const lang = await api("/api/lang");
  L = lang.strings;
  document.documentElement.lang = lang.lang;
  applyStaticLabels();
  loadStats();
  loadList();
})();
