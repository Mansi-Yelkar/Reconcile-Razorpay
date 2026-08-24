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

async function loadPipeline() {
  decisionsBody.innerHTML = `<tr><td colspan="6" class="empty-row">running reconciliation…</td></tr>`;
  const res = await fetch("/api/run");
  const data = await res.json();
  renderStats(data.summary);
  renderTable(data.decisions);
}

async function injectDemo() {
  injectBtn.disabled = true;
  injectBtn.textContent = "agent deciding…";
  const res = await fetch("/api/inject", { method: "POST" });
  const decision = await res.json();
  currentDecisions = [decision, ...currentDecisions];
  renderTable(currentDecisions);
  selectRow(0);
  injectBtn.disabled = false;
  injectBtn.textContent = "Inject a dropped webhook →";
}

injectBtn.addEventListener("click", injectDemo);
loadPipeline();
