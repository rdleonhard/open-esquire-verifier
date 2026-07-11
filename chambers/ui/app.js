/* Open Esquire Chambers — bench logic. Vanilla JS against /api/*. */

let S = null;            // last /api/state
let selected = null;     // selected matter id
let pendingDecision = null;

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g,
  (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const oed = (wei) => (Number(wei) / 1e18).toLocaleString(undefined,
  {maximumFractionDigits: 2}) + " OED";
const when = (ts) => ts ? new Date(ts * 1000).toLocaleString([],
  {month: "short", day: "numeric", hour: "2-digit", minute: "2-digit"}) : "";

async function api(path, body) {
  const r = await fetch(path, body === undefined ? {} : {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify(body)});
  const d = await r.json();
  if (!r.ok) throw new Error(d.error || r.status);
  return d;
}

function matterById(id) {
  return (S?.matters || []).find((m) => m.id === id) || null;
}

/* ---- render ---- */

function render() {
  renderChip();
  renderSession();
  renderDocket();
  renderMatter();
  renderRep();
  renderHistory();
  $("terms").textContent = S.disclaimer;
}

/* minutes left before the watchdog refunds a pending matter; null = off */
function refundIn(m) {
  const mins = Number(S.settings?.auto_deny_minutes || 0);
  if (!mins || m.ruling !== "pending") return null;
  return (m.filedAt + mins * 60) - Date.now() / 1000;
}

function clockTag(m) {
  const left = refundIn(m);
  if (left === null) return "";
  const label = left <= 0 ? "REFUND IMMINENT"
    : "AUTO-REFUND IN " + Math.ceil(left / 60) + " MIN";
  return `<span class="tag tag-clock ${left < 600 ? "urgent" : ""}">${label}</span>`;
}

function renderSession() {
  const mins = Number(S.settings?.auto_deny_minutes || 0);
  const pol = mins
    ? `UNANSWERED MATTERS AUTO-REFUND AFTER ${mins} MIN`
    : "AUTO-REFUND DISABLED";
  $("session").innerHTML = S.in_session
    ? `<span class="on">&#9670; IN SESSION — COUNSEL IS AT THE BENCH</span>
       &nbsp; <span class="pol">${esc(S.hours_text)} &middot; ${pol}</span>`
    : `<span class="off">&#9671; OUT OF SESSION</span>
       &nbsp; <span class="pol">HOURS: ${esc(S.hours_text)} &middot; ${pol}</span>`;
  $("hours-view").innerHTML =
    `<span class="${S.in_session ? "on" : "off"}">
       ${S.in_session ? "◆ IN SESSION" : "◇ OUT OF SESSION"}</span><br>
     ${esc(S.hours_text)}<br>
     <span style="color:#6a6658">${pol.toLowerCase()}</span>`;
}

function renderChip() {
  const c = S.chain;
  const short = (a) => a ? a.slice(0, 6) + "…" + a.slice(-4) : "?";
  let html = `BASE MAINNET ◆ DOCKET <a target="_blank"
    href="https://base.blockscout.com/address/${c.docket}">${short(c.docket)}</a><br>
    ${oed(c.price)} = 1 YES/NO ANSWER`;
  if (c.error) html += `<br><span class="err">CHAIN: ${esc(c.error.slice(0, 60))}</span>`;
  $("chainchip").innerHTML = html;
}

function renderDocket() {
  const box = $("docket");
  const ms = S.matters || [];
  if (!ms.length) { box.innerHTML = '<div class="empty">THE DOCKET IS CLEAR</div>'; return; }
  box.innerHTML = ms.map((m) => `
    <div class="docket-item ${m.id === selected ? "sel" : ""}" onclick="select('${esc(m.id)}')">
      <div class="d-head">
        <span class="d-id">${esc(m.id)}</span>
        <span class="tag tag-cite">CITATION</span>
        <span class="tag ${m.chain ? "tag-chain" : "tag-practice"}">
          ${m.chain ? "BASE" : "PRACTICE"}</span>
        ${clockTag(m)}
        <span class="d-when">${when(m.filedAt)}</span>
      </div>
      <div class="d-text">${esc(m.text)}</div>
    </div>`).join("");
}

let renderedMatter = null;   // don't wipe lookup results / a rewrite draft
                             // when the periodic poll re-renders the SAME matter

function renderMeta(m) {
  $("m-meta").innerHTML = `
    <span class="tag tag-cite">IN RE: IS THIS CITATION ON COURTLISTENER?</span>
    <span class="tag ${m.chain ? "tag-chain" : "tag-practice"}">${m.chain ? "BASE MAINNET" : "PRACTICE"}</span>
    ${m.chain ? `<span class="tag tag-fee">ESCROW ${oed(m.paid)}</span>
      <span>ASKER ${esc(m.asker.slice(0, 10))}…</span>` : ""}
    <span>FILED ${when(m.filedAt)}</span>
    ${clockTag(m)}`;
}

function renderMatter() {
  const m = matterById(selected);
  $("m-empty").classList.toggle("hidden", !!m);
  $("m-body").classList.toggle("hidden", !m);
  if (!m) {
    $("m-title").textContent = "MATTER FOR REVIEW";
    renderedMatter = null;
    return;
  }
  renderMeta(m);
  if (renderedMatter === m.id) return;   // same matter: keep working state
  renderedMatter = m.id;
  $("m-title").textContent = "MATTER FOR REVIEW ◆ " + m.id;
  $("m-text").textContent = m.text;
  $("cl-results").innerHTML = "";
  $("cl-note").textContent = "";
  lookup();          // the whole question IS the lookup — run it right away
}

function renderRep() {
  const r = S.reputation, c = S.chain;
  const days = r.since ? Math.max(1, Math.round((Date.now() / 1000 - r.since) / 86400)) : 0;
  const turn = r.median_turnaround_s
    ? (r.median_turnaround_s < 3600
        ? Math.round(r.median_turnaround_s / 60) + " min"
        : (r.median_turnaround_s / 3600).toFixed(1) + " h") : "—";
  $("reputation").innerHTML = `
    <div><div class="k">MATTERS RULED</div><div class="v">${r.ruled}</div></div>
    <div><div class="k">MEDIAN TURNAROUND</div><div class="v">${turn}</div></div>
    <div><div class="k">VERIFIED / WRONG / DENIED</div>
      <div class="v">${r.verified} / ${r.wrong} / ${r.denied}</div></div>
    <div><div class="k">TOKENS BURNED</div><div class="v">${oed(r.burned)}</div></div>
    <div style="grid-column:1/-1"><div class="k">VERIFIER OF RECORD</div>
      <div class="v"><a target="_blank"
        href="https://base.blockscout.com/address/${r.attorney}">${esc(r.attorney)}</a>
        ${days ? " · serving " + days + " d" : ""}</div></div>`;
}

function renderHistory() {
  const h = S.history || [];
  const box = $("history");
  if (!h.length) { box.innerHTML = '<div class="empty">NO RULINGS YET</div>'; return; }
  const hlabel = {verified: "YES — ON CL", wrong: "NO — NOT ON CL",
                  denied: "DENIED"};
  box.innerHTML = h.slice(0, 12).map((r) => `
    <div class="h-item">
      <span class="h-verdict hv-${esc(r.decision)}">${hlabel[r.decision] || esc(r.decision).toUpperCase()}</span>
      <span class="h-id">${esc(r.id)}</span>
      <span style="color:#6a6658;font-size:11px">${esc(r.date)} ${esc(r.ruled)}</span>
      ${r.tx ? `<span class="h-tx"><a target="_blank"
        href="https://base.blockscout.com/tx/${esc(r.tx)}">tx ↗</a></span>` : ""}
      ${r.via === "auto" ? '<span class="tag tag-auto">AUTO — LAPSED, REFUNDED</span>' : ""}
      ${r.response ? '<span class="tag tag-char">REWRITE RETURNED</span>' : ""}
      <span class="h-text">${esc(r.text)}</span>
    </div>`).join("");
}

/* ---- actions ---- */

function select(id) { selected = id; render(); }

async function refresh() {
  $("refreshbtn").textContent = "…";
  try { S = await api("/api/refresh", {}); } finally { $("refreshbtn").textContent = "REFRESH"; }
  if (selected && !matterById(selected)) selected = null;
  render();
}

async function load() {
  S = await api("/api/state");
  if (!selected && S.matters.length) selected = S.matters[0].id;
  render();
  // first paint may precede the chain refresh; poll once more shortly
  if (!S.chain.refreshed) setTimeout(load, 2500);
}

async function lookup() {
  const m = matterById(selected);
  if (!m) return;
  const btn = $("lookupbtn");
  btn.disabled = true; btn.textContent = "PULLING AUTHORITY…";
  try {
    const d = await api("/api/lookup", {text: m.text});
    $("cl-note").textContent = d.note || (d.mode === "token" ? "citation-lookup (authenticated)" : "");
    const CHECK_WORDS = {name: "NAME", year: "YEAR", court: "COURT"};
    $("cl-results").innerHTML = (d.citations || []).map((c) => `
      <div class="cl-cite">
        <span class="cite">${esc(c.cite)}</span>
        <span class="${c.on_notice ? "cl-amb" :
                       {found: "cl-found", not_found: "cl-notfound",
                        ambiguous: "cl-amb"}[c.status] || "cl-amb"}">
          ${c.on_notice ? "⚠ RESOLVES — BUT PARTS MISMATCH" :
            {found: "✓ REPORTED", not_found: "✗ NOT FOUND — LIKELY FABRICATED",
             ambiguous: "⚠ AMBIGUOUS"}[c.status] || "⚠ " + esc(c.detail || "ERROR")}</span>
        ${c.on_notice ? `<div class="cl-notice">⚠ ON NOTICE — THE CITATION RESOLVES,
          BUT PARTS DO NOT MATCH THE REPORTED CASE. As presented, this citation
          does not match a case on CourtListener.</div>` : ""}
        ${(c.checks || []).map((ch) => `<div class="cl-check ${
            ch.ok === true ? "ck-ok" : ch.ok === false ? "ck-bad" : "ck-na"}">
          ${ch.ok === true ? "✓" : ch.ok === false ? "✗" : "⚠"}
          ${CHECK_WORDS[ch.field] || esc(ch.field)}
          ${ch.ok === true ? "MATCHES" : ch.ok === false ? "DOES NOT MATCH" : "NOT VERIFIED"}
          — cited ${esc(ch.claimed)}; reporter shows ${esc(ch.actual)}</div>`).join("")}
        ${(c.cases || []).map((k) => `<div class="cl-case">${esc(k.name)}
          — ${esc(k.court)}${k.date ? ", " + esc(k.date) : ""}
          ${k.url ? ` <a target="_blank" href="${esc(k.url)}">read ↗</a>` : ""}</div>`).join("")}
        ${c.status === "not_found" && c.detail ? `<div class="cl-case">${esc(c.detail)}</div>` : ""}
      </div>`).join("") || "";
  } catch (e) {
    $("cl-note").textContent = "lookup failed: " + e.message;
  } finally {
    btn.disabled = false; btn.textContent = "PULL CITED AUTHORITY — COURTLISTENER";
  }
}

async function filePractice() {
  const text = $("p-text").value.trim();
  if (!text) return;
  const m = await api("/api/practice", {text});
  $("p-text").value = "";
  S = await api("/api/state");
  selected = m.id;
  render();
}

const VERDICTS = {
  verified: {label: "YES — ON COURTLISTENER", color: "var(--green)"},
  denied: {label: "DENIED — NO ANSWER", color: "var(--silver)"},
  wrong: {label: "NO — NOT ON COURTLISTENER", color: "var(--oxblood)"},
};

function openRule(decision) {
  const m = matterById(selected);
  if (!m) return;
  pendingDecision = decision;
  $("modal-verdict").textContent = VERDICTS[decision].label;
  $("modal-verdict").style.color = VERDICTS[decision].color;
  $("modal-consequence").textContent = !m.chain
    ? "Practice matter — recorded locally, nothing on-chain."
    : (decision === "denied"
        ? `The asker is refunded ${oed(m.paid)}.`
        : `The answer is given: ${oed(m.paid)} in escrow is burned; the ruling and receipt URL are posted on Base mainnet.`);
  $("attest").checked = false;
  $("modal-err").textContent = "";
  $("modal").classList.remove("hidden");
}

function closeModal() { $("modal").classList.add("hidden"); pendingDecision = null; }

async function confirmRule() {
  if (!$("attest").checked) {
    $("modal-err").textContent = "The personal-capacity attestation is required.";
    return;
  }
  const m = matterById(selected);
  const btn = $("soorder");
  btn.disabled = true; btn.textContent = "ENTERING…";
  try {
    await api("/api/rule", {id: m.id, decision: pendingDecision, attest: true});
    closeModal();
    selected = null;
    S = await api("/api/state");
    render();
  } catch (e) {
    $("modal-err").textContent = e.message;
  } finally {
    btn.disabled = false; btn.textContent = "SO ORDER IT";
  }
}

async function publish() {
  $("publishbtn").disabled = true;
  $("publishmsg").textContent = "syncing…";
  try {
    const d = await api("/api/publish", {});
    $("publishmsg").textContent = d.ok ? `synced (${d.merged} merged)` : "publish.sh failed";
  } catch (e) {
    $("publishmsg").textContent = "failed: " + e.message;
  } finally {
    $("publishbtn").disabled = false;
  }
}

function toggleTerms() { $("terms").classList.toggle("hidden"); }

/* ---- session hours editor ---- */

const DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];

function toggleHours() {
  const ed = $("hours-edit");
  if (ed.classList.contains("hidden")) {
    const days = S.settings.days || {};
    $("hours-days").innerHTML = DAYS.map((d) => {
      const w = days[d];
      return `<div class="day-row">
        <input type="checkbox" id="d-on-${d}" ${w ? "checked" : ""}>
        <span class="dname">${d.toUpperCase()}</span>
        <input type="time" id="d-a-${d}" value="${w ? w[0] : "09:00"}">
        &ndash;
        <input type="time" id="d-b-${d}" value="${w ? w[1] : "17:00"}">
      </div>`;
    }).join("");
    $("s-deadline").value = S.settings.auto_deny_minutes;
    $("hours-msg").textContent = "";
    ed.classList.remove("hidden");
    $("hoursbtn").textContent = "CLOSE";
  } else {
    ed.classList.add("hidden");
    $("hoursbtn").textContent = "EDIT";
  }
}

async function saveSettings() {
  const days = {};
  for (const d of DAYS) {
    days[d] = $(`d-on-${d}`).checked
      ? [$(`d-a-${d}`).value, $(`d-b-${d}`).value] : null;
  }
  try {
    S = await api("/api/settings", {
      days, auto_deny_minutes: Number($("s-deadline").value)});
    $("hours-msg").textContent = "adopted";
    render();
  } catch (e) {
    $("hours-msg").textContent = e.message;
  }
}

load();
setInterval(() => { if (document.visibilityState === "visible") load(); }, 60000);
// countdown chips tick between polls; meta-only, never touches working state
setInterval(() => {
  if (!S || document.visibilityState !== "visible") return;
  renderDocket();
  const m = matterById(selected);
  if (m) renderMeta(m);
}, 15000);
