const decisionsBody = document.getElementById("decisions-body");
const reasoningBody = document.getElementById("reasoning-body");
const injectBtn = document.getElementById("inject-btn");

let currentDecisions = [];

function fmtMoney(n) {
  return "₹" + Number(n).toLocaleString("en-IN", { maximumFractionDigits: 0 });
}

function fmtGap(seconds) {
  if (seconds < 60) return `${Math.round(seconds)}s`;
  if (seconds < 3600) return `${(seconds / 60).toFixed(1)}m`;
  return `${(seconds / 3600).toFixed(1)}h`;
}

function renderStats(summary) {
  document.getElementById("stat-total").textContent = summary.total_transactions;
  document.getElementById("stat-found").textContent = fmtMoney(summary.ghost_revenue_found);
  document.getElementById("stat-recovered").textContent = fmtMoney(summary.auto_recovered);
  document.getElementById("stat-review").textContent = fmtMoney(summary.pending_review);
  document.getElementById("stat-escalated").textContent = fmtMoney(summary.escalated);
}

// ---- count-up animation for the hero number ----
function animateCountUp(el, target, durationMs = 900) {
  const start = performance.now();
  function tick(now) {
    const t = Math.min(1, (now - start) / durationMs);
    const eased = 1 - Math.pow(1 - t, 3);
    el.textContent = fmtMoney(Math.round(target * eased));
    if (t < 1) requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);
}

// ---- segmented recovery bar ----
function renderSegmentedBar(summary) {
  const total = summary.ghost_revenue_found || 1;
  const bar = document.getElementById("segmented-bar");
  const pct = v => `${Math.max((v / total) * 100, v > 0 ? 1.5 : 0)}%`;
  bar.innerHTML = `
    <div class="seg found" style="width:${pct(summary.auto_recovered)}" title="auto-recovered"></div>
    <div class="seg review" style="width:${pct(summary.pending_review)}" title="pending review"></div>
    <div class="seg escalated" style="width:${pct(summary.escalated)}" title="escalated"></div>
  `;
}

// ---- donut chart: ghost revenue by rail ----
const RAIL_COLORS = { UPI: "#45d8b0", CARD: "#6ea8fe", NETBANKING: "#f0a84e" };

function renderDonut(decisions) {
  const totals = {};
  decisions.forEach(d => { totals[d.rail] = (totals[d.rail] || 0) + d.amount; });
  const sum = Object.values(totals).reduce((a, b) => a + b, 0) || 1;

  const r = 50, cx = 60, cy = 60, circumference = 2 * Math.PI * r;
  let offset = 0;
  const svg = document.getElementById("donut-svg");
  const rails = Object.keys(totals);

  const circles = rails.map(rail => {
    const frac = totals[rail] / sum;
    const dash = frac * circumference;
    const circle = `<circle cx="${cx}" cy="${cy}" r="${r}" fill="none"
      stroke="${RAIL_COLORS[rail] || '#8a93a6'}" stroke-width="14"
      stroke-dasharray="${dash} ${circumference - dash}"
      stroke-dashoffset="${-offset}" transform="rotate(-90 ${cx} ${cy})" />`;
    offset += dash;
    return circle;
  }).join("");

  svg.innerHTML = `<circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="#232a35" stroke-width="14" />${circles}`;

  const legend = document.getElementById("donut-legend");
  legend.innerHTML = rails.map(rail => `
    <div class="donut-legend-item">
      <i style="background:${RAIL_COLORS[rail] || '#8a93a6'}"></i>
      ${rail} <b>${fmtMoney(totals[rail])}</b>
    </div>
  `).join("");
}

// ---- horizontal bars: decision count by confidence tier ----
function renderTierBars(decisions) {
  const counts = { high: 0, medium: 0, low: 0 };
  decisions.forEach(d => { counts[d.tier] = (counts[d.tier] || 0) + 1; });
  const max = Math.max(...Object.values(counts), 1);
  const labels = { high: "auto-reconciled", medium: "drafted for review", low: "escalated" };

  const wrap = document.getElementById("tier-bars");
  wrap.innerHTML = Object.keys(labels).map(tier => `
    <div class="tier-bar-row">
      <div class="tier-bar-label"><span>${labels[tier]}</span><span>${counts[tier]}</span></div>
      <div class="tier-bar-track">
        <div class="tier-bar-fill ${tier}" style="width:${(counts[tier] / max) * 100}%"></div>
      </div>
    </div>
  `).join("");
}

function renderImpact(summary, decisions) {
  const heroEl = document.getElementById("hero-number");
  animateCountUp(heroEl, summary.ghost_revenue_found);
  renderSegmentedBar(summary);
  renderDonut(decisions);
  renderTierBars(decisions);
}

function renderTable(decisions) {
  currentDecisions = decisions;
  if (!decisions.length) {
    decisionsBody.innerHTML = `<tr><td colspan="6" class="empty-row">no mismatches — every ledger row agrees</td></tr>`;
    return;
  }
  decisionsBody.innerHTML = decisions.map((d, i) => `
    <tr data-idx="${i}">
      <td class="ref-cell">${d.ref_id}</td>
      <td>${fmtMoney(d.amount)}</td>
      <td>${d.rail}</td>
      <td>${fmtGap(d.time_gap_seconds)}</td>
      <td>${d.confidence.toFixed(2)}</td>
      <td><span class="action-pill ${d.tier}">${d.action.replace(/_/g, " ")}</span></td>
    </tr>
  `).join("");

  decisionsBody.querySelectorAll("tr[data-idx]").forEach(row => {
    row.addEventListener("click", () => selectRow(Number(row.dataset.idx)));
  });
}

function selectRow(idx) {
  decisionsBody.querySelectorAll("tr").forEach(r => r.classList.remove("selected"));
  const row = decisionsBody.querySelector(`tr[data-idx="${idx}"]`);
  if (row) row.classList.add("selected");
  showReasoning(currentDecisions[idx]);
}

function showReasoning(d) {
  reasoningBody.innerHTML = `
    <div class="reasoning-meta">
      <span>${d.ref_id}</span>
      <span>${fmtMoney(d.amount)}</span>
      <span>${d.rail}</span>
      <span>tier: ${d.tier}</span>
      <span>${new Date(d.decided_at).toLocaleString("en-IN")}</span>
    </div>
    <div class="reasoning-text">${d.reasoning}</div>
  `;
}

let lastSummary = null;

async function loadPipeline() {
  decisionsBody.innerHTML = `<tr><td colspan="6" class="empty-row">running reconciliation…</td></tr>`;
  const res = await fetch("/api/run");
  const data = await res.json();
  lastSummary = data.summary;
  renderStats(data.summary);
  renderTable(data.decisions);
  renderImpact(data.summary, data.decisions);
}

async function injectDemo() {
  injectBtn.disabled = true;
  injectBtn.textContent = "agent deciding…";
  const res = await fetch("/api/inject", { method: "POST" });
  const decision = await res.json();
  currentDecisions = [decision, ...currentDecisions];
  renderTable(currentDecisions);
  selectRow(0);

  // flash the new row and nudge the charts to reflect the live decision
  const newRow = decisionsBody.querySelector('tr[data-idx="0"]');
  if (newRow) { newRow.classList.add("flash"); setTimeout(() => newRow.classList.remove("flash"), 1400); }

  if (lastSummary) {
    lastSummary = { ...lastSummary, ghost_revenue_found: lastSummary.ghost_revenue_found + decision.amount };
    if (decision.action === "AUTO_RECONCILE") lastSummary.auto_recovered += decision.amount;
    else if (decision.action === "DRAFT_FOR_REVIEW") lastSummary.pending_review += decision.amount;
    else lastSummary.escalated += decision.amount;
    renderStats(lastSummary);
    renderImpact(lastSummary, currentDecisions);
  }

  injectBtn.disabled = false;
  injectBtn.textContent = "Inject a dropped webhook →";
}

injectBtn.addEventListener("click", injectDemo);
loadPipeline();
