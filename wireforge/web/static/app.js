"use strict";

// Everything that reaches the page from a run (URLs, site responses, model text) is untrusted:
// it only ever goes through esc() or textContent, never straight into innerHTML.
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const api = async (path, opts) => {
  const r = await fetch(path, opts);
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(body.detail || `HTTP ${r.status}`);
  return body;
};
const host = (u) => { try { return new URL(u).host.replace(/^www\./, ""); } catch { return u || ""; } };
const OUTCOME = { verified: "verified", rejected_by_verifier: "rejected", no_working_action: "no action", error: "error", running: "running", interrupted: "interrupted", done: "done" };

let meta = {};
let current = null; // { id, source }

// ------------------------------------------------------------------ router
const ROUTES = ["home", "board", "actions", "results", "safety"];
function route() {
  const h = location.hash.slice(1);
  const name = ROUTES.includes(h) ? h : "home";
  ROUTES.forEach((r) => ($(`#view-${r}`).hidden = r !== name));
  $$(".tabs a").forEach((a) => a.classList.toggle("on", a.dataset.route === name));
  if (!ROUTES.includes(h) && h) document.getElementById(h)?.scrollIntoView();
  else window.scrollTo(0, 0);
  if (name === "board") loadBoard();
  if (name === "actions") loadActions();
  if (name === "results") loadResults();
}
window.addEventListener("hashchange", route);

// ------------------------------------------------------------------ tally (only from bench/results.csv)
async function loadTally() {
  const t = await api("/api/tally").catch(() => null);
  if (!t) return;
  $$("[data-t]").forEach((el) => {
    const v = t[el.dataset.t];
    el.textContent = v === null || v === undefined || (t.runs === 0 && el.dataset.t !== "runs") ? "—" : `${v}${el.dataset.unit || ""}`;
  });
  $("#home-tally-empty").hidden = t.runs > 0;
  const rows = Object.entries(t.models);
  renderModelChart(rows);
  $("#home-models tbody").innerHTML = rows.length
    ? rows.map(([m, v]) => `<tr><td class="mono">${esc(m)}</td><td>${v.runs}</td><td>${v.verified}</td><td>${v.median_min ?? "—"}</td><td>${v.avg_repairs ?? "—"}</td></tr>`).join("")
    : `<tr><td colspan="5" class="empty">No comparison runs yet.</td></tr>`;
}

function renderModelChart(rows) {
  // Bars come straight from /api/tally (which reads only bench/results.csv); no chart without data.
  const box = $("#model-chart");
  if (!box) return;
  const withTime = rows.filter(([, v]) => v.median_min != null);
  box.hidden = withTime.length < 1;
  if (box.hidden) return;
  const max = Math.max(...withTime.map(([, v]) => v.median_min));
  $("#model-bars").innerHTML = withTime.map(([m, v]) => `
    <div class="bar-row">
      <span class="bar-label mono">${esc(m)}</span>
      <div class="bar-track"><div class="bar-fill" style="width:${Math.max(6, (v.median_min / max) * 100)}%"></div></div>
      <span class="bar-value">${esc(v.median_min)} min · ${v.verified}/${v.runs} verified</span>
    </div>`).join("");
}

async function loadMeta() {
  meta = await api("/api/meta").catch(() => ({}));
  $$('[data-meta="version"]').forEach((el) => (el.textContent = `v${meta.version || "?"}`));
  $$('[data-meta="browser"]').forEach((el) => (el.textContent = meta.browser || "—"));
  const sel = $("#model-select");
  sel.innerHTML = [meta.model, meta.baseline_model].filter(Boolean)
    .map((m, i) => `<option value="${esc(m)}">${esc(m)}${i ? " (baseline)" : ""}</option>`).join("");
}

setInterval(() => ($("#clock").textContent = new Date().toLocaleTimeString()), 1000);

// ------------------------------------------------------------------ home: steps + faq
function initSteps() {
  const items = $$("#step-list li"), arts = $$(".step-body article");
  const on = (i) => items.forEach((li) => li.classList.toggle("on", +li.dataset.step === i));
  items.forEach((li) => li.addEventListener("click", () => arts[+li.dataset.step].scrollIntoView({ behavior: "smooth", block: "center" })));
  const io = new IntersectionObserver((es) => es.forEach((e) => e.isIntersecting && on(+e.target.dataset.step)), { rootMargin: "-45% 0px -45% 0px" });
  arts.forEach((a) => io.observe(a));
}

const FAQ = [
  ["Is it safe to point at a real shop?", "Write actions stop at the cart. Checkout, payment and order paths are refused by the probe tool and by the harness that runs every action, and no passwords are used anywhere."],
  ["What does it actually produce?", "A Wire-shaped spec (action_id, type, parameters), a Python function that calls the site's backend with no browser, a strict return schema, test parameters that worked at build time, and an auto-generated test."],
  ["How do you know the output is right?", "A second agent with a fresh browser runs the action at least twice, once with its own inputs, and compares concrete values against the rendered page. For add-to-cart it opens the cart with the action's own session cookies."],
  ["What if the verifier says no?", "Its report goes back to the forge, which investigates and re-emits. After two repair rounds without a pass, the run is recorded as rejected, not quietly shipped."],
  ["Which parts are the model, and which are code?", "The model explores the site, reads traffic and writes the action. Running it, schema checks, the checkout guard, the two-run rule and the verdict rules are plain code."],
  ["How is the model comparison fair?", "Same sites, same goals, same tools, same limits, and the same verifier model judges both runs. Every run is a row in bench/results.csv."],
  ["Does it need Anakin's Browser API?", "With an Anakin key it drives Anakin's hosted browser over CDP. Without one it falls back to a local headless Chromium, so the whole thing runs on a laptop."],
];
function initFaq() {
  const q = $("#faq-q"), a = $("#faq-a");
  const show = (i) => {
    $$("li", q).forEach((li, j) => li.classList.toggle("on", i === j));
    a.innerHTML = `<h3>${esc(FAQ[i][0])}</h3><p>${esc(FAQ[i][1])}</p>`;
  };
  q.innerHTML = FAQ.map(([t]) => `<li tabindex="0">${esc(t)}</li>`).join("");
  $$("li", q).forEach((li, i) => {
    li.addEventListener("click", () => show(i));
    li.addEventListener("keydown", (e) => e.key === "Enter" && show(i));
  });
  show(0);
}

// ------------------------------------------------------------------ board
const PRESETS = [
  ["L1 · BMTC", "https://nammabmtcapp.karnataka.gov.in/", "list bus routes between two stops with timings"],
  ["L1 · VTU results", "https://results.vtu.ac.in/", "look up a student's semester results by USN"],
  ["L2 · RedBus", "https://www.redbus.in/", "search buses between two cities on a date, with fares and seats left"],
  ["L3 · Myntra", "https://www.myntra.com/", "search products by keyword with brand and price filters, paginated"],
  ["L4 · Snitch cart", "https://www.snitch.com/", "add a shirt in a given size and quantity to the cart"],
  ["Air quality · aqicn", "https://aqicn.org/city/delhi/", "live AQI and main pollutants for a given Indian city"],
  ["L5 · CPCB AQI", "https://airquality.cpcb.gov.in/ccr/", "live AQI and pollutant readings for a given city or station"],
];
function initBoard() {
  $("#presets").innerHTML = PRESETS.map(([l], i) => `<button type="button" data-i="${i}">${esc(l)}</button>`).join("");
  $$("#presets button").forEach((b) => b.addEventListener("click", () => {
    const [, url, goal] = PRESETS[+b.dataset.i];
    $("#run-form").url.value = url;
    $("#run-form").goal.value = goal;
  }));
  $("#run-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const f = e.target, msg = $("#form-msg"), btn = $("#run-btn");
    msg.className = "form-msg";
    msg.textContent = "Starting…";
    btn.disabled = true;
    try {
      const { id } = await api("/api/runs", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: f.url.value.trim(), goal: f.goal.value.trim(), model: f.model.value, passcode: f.passcode.value }),
      });
      msg.textContent = "Running. Watch it on the right.";
      await loadRuns();
      watch(id);
    } catch (err) {
      msg.className = "form-msg err";
      msg.textContent = err.message;
    } finally {
      btn.disabled = false;
    }
  });
}

async function loadBoard() {
  await Promise.all([loadTally(), loadRuns()]);
}

async function loadRuns() {
  const runs = await api("/api/runs").catch(() => []);
  const ul = $("#run-list");
  if (!runs.length) { ul.innerHTML = `<li class="empty">No runs yet.</li>`; return runs; }
  ul.innerHTML = runs.map((r) => {
    const st = r.status === "done" ? r.outcome : r.status;
    return `<li data-id="${esc(r.id)}" class="${current?.id === r.id ? "on" : ""}">
      <div class="t"><span>${esc(host(r.url))}</span><span class="status ${esc(st)}">${esc(OUTCOME[st] || st)}</span></div>
      <div class="g">${esc(r.goal)}</div><div class="g mono">${esc(r.model)}</div></li>`;
  }).join("");
  $$("li[data-id]", ul).forEach((li) => li.addEventListener("click", () => watch(li.dataset.id)));
  if (!current && runs[0]) watch(runs.find((r) => r.status === "running")?.id || runs[0].id);
  return runs;
}

function setStage(name, cls) {
  const order = ["trace", "endpoint", "emit", "verify", "done"];
  const idx = order.indexOf(name);
  $$("#live-stages li").forEach((li, i) => {
    li.className = i < idx ? "ok" : i === idx ? cls : "";
  });
}

function watch(id) {
  if (current?.source) current.source.close();
  current = { id, source: null };
  $$("#run-list li").forEach((li) => li.classList.toggle("on", li.dataset.id === id));
  $("#feed").innerHTML = "";
  $("#spec-card").innerHTML = `<p class="panel-title">Action</p><p class="empty">Appears when the forge emits.</p>`;
  $("#verdict-card").innerHTML = `<p class="panel-title">Verifier</p><p class="empty">Appears when the verifier decides.</p>`;
  setStage("trace", "");
  api(`/api/runs/${encodeURIComponent(id)}`).then((d) => {
    const req = d.request || {};
    $("#live-title").textContent = `${host(req.url)} · ${req.goal || ""}`;
    $("#live-sub").textContent = `${req.model || ""} · verifier ${req.verifier_model || ""} · ${id}`;
    setStatus(d.status === "done" ? d.summary?.outcome : d.status);
  }).catch(() => {});
  const es = new EventSource(`/api/runs/${encodeURIComponent(id)}/events`);
  current.source = es;
  es.onmessage = (m) => { try { onEvent(id, JSON.parse(m.data)); } catch { /* partial line */ } };
  es.addEventListener("end", () => { es.close(); refreshDetail(id); loadRuns(); loadTally(); });
}

function setStatus(st) {
  const el = $("#live-status");
  el.className = `status ${st || ""}`;
  el.textContent = OUTCOME[st] || st || "";
}

function onEvent(id, ev) {
  if (current?.id !== id) return;
  const d = ev.data || {};
  const feed = $("#feed");
  const stick = feed.scrollHeight - feed.scrollTop - feed.clientHeight < 60;
  const div = document.createElement("div");
  div.className = `ev ${esc(ev.agent)}`;
  const who = `<span class="who">${esc(ev.agent)}</span>`;

  if (ev.kind === "stage") {
    div.classList.add("stage");
    if (d.stage === "error") div.classList.add("error");
    div.innerHTML = `${who}${esc(stageText(d))}`;
    if (d.stage === "trace" || d.stage === "start") setStage("trace", "on");
    if (d.stage === "verify") setStage("verify", "on");
    if (d.stage === "repair") setStage("emit", "on");
    if (d.stage === "done") { setStage("done", d.outcome === "verified" ? "ok" : "bad"); setStatus(d.outcome); }
    if (d.stage === "error") { setStatus("error"); $$("#live-stages li.on").forEach((li) => (li.className = "bad")); }
  } else if (ev.kind === "tool") {
    const args = JSON.stringify(d.input || {});
    div.innerHTML = `${who}<details><summary>${esc(d.name)}(${esc(args.length > 110 ? args.slice(0, 110) + "…" : args)})${d.error ? " · error" : ""}</summary><pre>${esc(d.result)}</pre></details>`;
    if (d.error) div.classList.add("error");
    if (ev.agent === "forge" && (d.name === "network_detail" || d.name === "http_request")) setStage("endpoint", "on");
    if (d.name === "emit_action") {
      const ok = String(d.result).startsWith("Action PASSED");
      setStage(ok ? "verify" : "emit", ok ? "" : "on");
      refreshDetail(id);
    }
    if (d.name === "submit_verdict") refreshDetail(id);
  } else if (ev.kind === "thinking") {
    div.classList.add("thinking");
    div.innerHTML = `${who}${esc(String(d).slice(0, 600))}`;
  } else if (ev.kind === "text") {
    div.innerHTML = `${who}${esc(d)}`;
  } else if (ev.kind === "stats") {
    div.innerHTML = `${who}<span class="mono small">${esc(`${d.turns} turns · ${d.tool_calls} tool calls · ${d.output_tokens} output tokens · ${d.wall_s}s · stop: ${d.stop}`)}</span>`;
  } else if (ev.kind === "task") {
    div.innerHTML = `${who}<details><summary>task</summary><pre>${esc(d)}</pre></details>`;
  } else {
    return;
  }
  feed.appendChild(div);
  if (stick) feed.scrollTop = feed.scrollHeight;
}

function stageText(d) {
  switch (d.stage) {
    case "start": return `Start · ${d.url} · ${d.model}`;
    case "trace": return `Tracing the site in ${d.browser}`;
    case "verify": return `Verifying ${d.action_id} in a fresh browser`;
    case "repair": return `Verifier rejected it · repair round ${d.round}`;
    case "done": return `Done · ${OUTCOME[d.outcome] || d.outcome}`;
    case "error": return `Run failed · ${d.error}`;
    default: return d.stage;
  }
}

async function refreshDetail(id) {
  const d = await api(`/api/runs/${encodeURIComponent(id)}`).catch(() => null);
  if (!d || current?.id !== id) return;
  if (d.spec) $("#spec-card").innerHTML = `<p class="panel-title">Action</p>${specHtml(d.spec, d.test_params)}`;
  if (d.verdict) $("#verdict-card").innerHTML = `<p class="panel-title">Verifier</p>${verdictHtml(d.verdict)}`;
}

function specHtml(s, tp) {
  const params = (s.parameters || []).map((p) => `<tr><td class="mono">${esc(p.name)}</td><td>${esc(p.type)}${p.required ? " *" : ""}</td><td>${esc(p.description)}</td></tr>`).join("");
  return `<h4>${esc(s.action_id)}</h4>
    <p class="kv">${esc(s.name)} · <b>${esc(s.type)}</b></p>
    <p class="kv">${esc(s.description)}</p>
    <table class="params">${params}</table>
    ${(s.endpoints || []).length ? `<pre>${esc(s.endpoints.join("\n"))}</pre>` : ""}
    ${tp ? `<details><summary class="small mono">test_params</summary><pre>${esc(JSON.stringify(tp, null, 1))}</pre></details>` : ""}`;
}

function verdictHtml(v) {
  const checks = (v.checks || []).map((c) => `<div class="check"><span class="m ${c.match ? "y" : "n"}">${c.match ? "✓" : "✗"}</span>
    <div>${esc(c.what)}<small>action: ${esc(c.action_value)} · page: ${esc(c.page_value)}${c.note ? ` · ${esc(c.note)}` : ""}</small></div></div>`).join("");
  return `<p class="kv"><span class="status ${v.passed ? "verified" : "error"}">${v.passed ? "passed" : "rejected"}</span></p>
    <p class="kv">${esc(v.summary)}</p>${checks}`;
}

// ------------------------------------------------------------------ actions
async function loadActions() {
  const runs = (await api("/api/runs").catch(() => [])).filter((r) => r.action_id);
  const grid = $("#actions-grid");
  grid.innerHTML = runs.length ? runs.map((r) => {
    const st = r.status === "done" ? r.outcome : r.status;
    return `<div class="a-card" data-id="${esc(r.id)}" tabindex="0"><span class="status ${esc(st)}">${esc(OUTCOME[st] || st)}</span>
      <h4>${esc(r.action_id)}</h4><p>${esc(host(r.url))} · ${esc(r.type)} · ${esc(r.model)}</p></div>`;
  }).join("") : `<p class="empty">No actions yet. Start one on the Forge Board.</p>`;
  $$(".a-card", grid).forEach((c) => c.addEventListener("click", () => showAction(c.dataset.id)));
}

async function showAction(id) {
  $$(".a-card").forEach((c) => c.classList.toggle("on", c.dataset.id === id));
  const d = await api(`/api/runs/${encodeURIComponent(id)}`);
  const box = $("#action-detail");
  box.hidden = false;
  box.innerHTML = `<div class="detail-grid">
    <div>${d.spec ? specHtml(d.spec, d.test_params) : ""}
      ${d.spec ? `<details><summary class="small mono">return_schema</summary><pre>${esc(JSON.stringify(d.spec.return_schema, null, 1))}</pre></details>` : ""}
      <div class="side-card" style="margin-top:14px"><p class="panel-title">Verifier</p>${d.verdict ? verdictHtml(d.verdict) : `<p class="empty">Not verified.</p>`}</div></div>
    <div><p class="panel-title">action.py</p><pre style="max-height:640px">${esc(d.code || "")}</pre></div></div>`;
  box.scrollIntoView({ behavior: "smooth" });
}

// ------------------------------------------------------------------ results
async function loadResults() {
  const rows = await api("/api/results").catch(() => []);
  $("#results-table tbody").innerHTML = rows.length ? rows.map((r) => `<tr>
    <td class="mono">${esc(r.timestamp)}</td><td>${esc(host(r.site))}</td><td class="mono">${esc(r.model)}</td>
    <td><span class="status ${esc(r.outcome)}">${esc(OUTCOME[r.outcome] || r.outcome)}</span></td><td class="mono">${esc(r.action_id)}</td>
    <td>${esc(r.emits)}</td><td>${esc(r.repair_rounds)}</td><td>${esc(r.forge_turns)}</td>
    <td>${esc(r.verifier_matched)}/${esc(r.verifier_checks)}</td><td>${(Number(r.wall_s) / 60).toFixed(1)}</td></tr>`).join("")
    : `<tr><td colspan="10" class="empty">No runs recorded yet.</td></tr>`;
}

// ------------------------------------------------------------------ live chip (only a real running run)
async function loadLiveChip() {
  const runs = await api("/api/runs").catch(() => []);
  const r = runs.find((x) => x.status === "running");
  const chip = $("#live-chip");
  chip.hidden = !r;
  if (r) $("span", chip).textContent = `forging ${host(r.url)} now`;
}

// ------------------------------------------------------------------ boot
initSteps();
initFaq();
initBoard();
loadMeta();
loadTally();
route();
loadLiveChip();
setInterval(() => { if (location.hash === "#board") loadRuns(); loadTally(); loadLiveChip(); }, 15000);
