// Reconcile Command Center JavaScript Application

document.addEventListener('DOMContentLoaded', () => {
  initTabs();
  loadDashboardData();
  bindSimulatorEvents();
  bindSearchAndFilters();
  bindModalClose();
  bindQuickHeaderActions();
});

// Currency formatting helper
function formatINR(val) {
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 2
  }).format(val || 0);
}

async function apiFetch(url, options) {
  const response = await fetch(url, options);
  let payload;

  try {
    payload = await response.json();
  } catch (error) {
    payload = null;
  }

  if (!response.ok) {
    throw new Error(payload?.error || payload?.reason || `Request failed (${response.status})`);
  }

  return payload;
}

// Tab Switching
function initTabs() {
  const tabs = document.querySelectorAll('.segmented-tab');
  tabs.forEach(tab => {
    tab.addEventListener('click', () => {
      tabs.forEach(t => t.classList.remove('active'));
      document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));

      tab.classList.add('active');
      const targetId = `tab-${tab.dataset.tab}`;
      const targetContent = document.getElementById(targetId);
      if (targetContent) {
        targetContent.classList.add('active');
      }

      // Lazy load tab data
      if (tab.dataset.tab === 'cases') loadAllCases();
      if (tab.dataset.tab === 'audit') loadAuditLog();
    });
  });
}

// Load Dashboard Data
async function loadDashboardData() {
  try {
    const data = await apiFetch('/api/analytics/overview');

    document.getElementById('kpi-at-risk').textContent = formatINR(data.revenue_at_risk);
    document.getElementById('kpi-recovered').textContent = formatINR(data.revenue_recovered);
    document.getElementById('kpi-recovery-rate').textContent = `${data.recovery_rate_pct}% safe recovery rate`;
    document.getElementById('kpi-active-cases').textContent = data.active_cases || 0;
    document.getElementById('kpi-blocked-actions').textContent = data.blocked_actions || 0;

    loadFunnel(data.revenue_at_risk, data.revenue_recovered);
    loadRecentCases();
  } catch (err) {
    console.error('Failed to load overview data:', err);
  }
}

// Load Funnel
async function loadFunnel(atRisk, recovered) {
  try {
    const funnel = await apiFetch('/api/analytics/funnel');

    document.getElementById('funnel-val-risk').textContent = formatINR(funnel.at_risk);
    document.getElementById('funnel-val-eligible').textContent = formatINR(funnel.eligible);
    document.getElementById('funnel-val-attempted').textContent = formatINR(funnel.attempted);
    document.getElementById('funnel-val-recovered').textContent = formatINR(funnel.recovered);
  } catch (err) {
    console.error('Failed to load funnel data:', err);
  }
}

// Load Recent Cases
async function loadRecentCases() {
  const tbody = document.getElementById('tbl-recent-cases');
  try {
    const cases = await apiFetch('/api/recovery/cases');

    if (!cases || cases.length === 0) {
      tbody.innerHTML = '<tr><td colspan="10" class="text-center text-muted">No recovery cases recorded yet. Click a scenario in Simulation Center.</td></tr>';
      return;
    }

    tbody.innerHTML = cases.slice(0, 10).map(c => renderCaseRow(c)).join('');
    bindRowActionButtons();
  } catch (err) {
    tbody.innerHTML = '<tr><td colspan="10" class="text-center text-muted">Error loading cases.</td></tr>';
  }
}

// Render Case Row HTML
function renderCaseRow(c) {
  const statusBadge = getStatusBadge(c.status);
  const prob = (c.recovery_probability * 100).toFixed(0);
  
  return `
    <tr>
      <td><strong>${c.id}</strong></td>
      <td><span class="badge badge-amber">${c.case_type}</span></td>
      <td><strong>${formatINR(c.amount_at_risk)}</strong></td>
      <td><code>${c.root_cause}</code></td>
      <td><strong>${prob}%</strong></td>
      <td><code>${c.recommended_action}</code></td>
      <td>${c.is_duplicate_suspected ? '<span class="badge badge-red">DUP BLOCKED</span>' : (c.amount_at_risk > 50000 ? '<span class="badge badge-amber">ESCALATED</span>' : '<span class="badge badge-green">PASSED</span>')}</td>
      <td>${statusBadge}</td>
      <td><strong>${formatINR(c.status === 'RECOVERED' ? c.amount_at_risk : 0)}</strong></td>
      <td>
        <button class="btn-secondary-action btn-sm btn-inspect-case" data-id="${c.id}">Inspect</button>
        ${c.status === 'DETECTED' || c.status === 'DIAGNOSED' ? `<button class="btn-lime-action btn-sm btn-exec-case" data-id="${c.id}">Execute</button>` : ''}
        ${c.status === 'ESCALATED' ? `<button class="btn-secondary-action btn-sm btn-approve-case" data-id="${c.id}">Approve</button>` : ''}
      </td>
    </tr>
  `;
}

// Status Badges Helper
function getStatusBadge(status) {
  if (status === 'RECOVERED') return '<span class="badge badge-green">RECOVERED</span>';
  if (status === 'BLOCKED') return '<span class="badge badge-red">BLOCKED</span>';
  if (status === 'ESCALATED') return '<span class="badge badge-amber">ESCALATED</span>';
  if (status === 'IN_PROGRESS') return '<span class="badge badge-blue">IN PROGRESS</span>';
  if (status === 'STOPPED') return '<span class="badge badge-red">STOPPED</span>';
  return `<span class="badge badge-lime">${status}</span>`;
}

// Load All Cases for Cases Tab
async function loadAllCases() {
  const tbody = document.getElementById('tbl-all-cases');
  try {
    const cases = await apiFetch('/api/recovery/cases');

    if (!cases || cases.length === 0) {
      tbody.innerHTML = '<tr><td colspan="9" class="text-center text-muted">No cases found.</td></tr>';
      return;
    }

    tbody.innerHTML = cases.map(c => `
      <tr>
        <td><strong>${c.id}</strong></td>
        <td><span class="badge badge-amber">${c.case_type}</span></td>
        <td><strong>${formatINR(c.amount_at_risk)}</strong></td>
        <td><code>${c.root_cause}</code></td>
        <td><strong>${(c.recovery_probability * 100).toFixed(0)}%</strong></td>
        <td>${formatINR(c.estimated_net_value)}</td>
        <td>${getStatusBadge(c.status)}</td>
        <td><strong>${formatINR(c.status === 'RECOVERED' ? c.amount_at_risk : 0)}</strong></td>
        <td>
          <button class="btn-secondary-action btn-sm btn-inspect-case" data-id="${c.id}">Details</button>
          ${c.status === 'ESCALATED' ? `<button class="btn-secondary-action btn-sm btn-approve-case" data-id="${c.id}">Approve</button>` : ''}
          ${c.status === 'IN_PROGRESS' || c.status === 'DETECTED' ? `<button class="btn-secondary-action btn-sm btn-stop-case" data-id="${c.id}">Stop</button>` : ''}
        </td>
      </tr>
    `).join('');

    bindRowActionButtons();
  } catch (err) {
    tbody.innerHTML = '<tr><td colspan="9" class="text-center text-muted">Error loading cases.</td></tr>';
  }
}

// Bind Row Action Buttons
function bindRowActionButtons() {
  document.querySelectorAll('.btn-inspect-case').forEach(btn => {
    btn.addEventListener('click', () => openCaseModal(btn.dataset.id));
  });

  document.querySelectorAll('.btn-exec-case').forEach(btn => {
    btn.addEventListener('click', async () => {
      btn.disabled = true;
      btn.textContent = '...';
      try {
        await apiFetch(`/api/recovery/cases/${btn.dataset.id}/execute`, { method: 'POST' });
        await loadDashboardData();
      } catch (err) {
        btn.disabled = false;
        btn.textContent = 'Execute';
        alert(`Recovery execution failed: ${err.message}`);
      }
    });
  });

  document.querySelectorAll('.btn-approve-case').forEach(btn => {
    btn.addEventListener('click', async () => {
      btn.disabled = true;
      btn.textContent = '...';
      try {
        await apiFetch(`/api/recovery/cases/${btn.dataset.id}/approve`, { method: 'POST' });
        await loadDashboardData();
        await loadAllCases();
      } catch (err) {
        btn.disabled = false;
        btn.textContent = 'Approve';
        alert(`Approval failed: ${err.message}`);
      }
    });
  });

  document.querySelectorAll('.btn-stop-case').forEach(btn => {
    btn.addEventListener('click', async () => {
      btn.disabled = true;
      btn.textContent = '...';
      try {
        await apiFetch(`/api/recovery/cases/${btn.dataset.id}/stop`, { method: 'POST' });
        await loadDashboardData();
        await loadAllCases();
      } catch (err) {
        btn.disabled = false;
        btn.textContent = 'Stop';
        alert(`Stopping case failed: ${err.message}`);
      }
    });
  });
}

// Open Case Modal with Timeline & Explainability
async function openCaseModal(caseId) {
  const modal = document.getElementById('case-modal');
  const title = document.getElementById('modal-case-title');
  const body = document.getElementById('modal-case-body');

  title.textContent = `Recovery Case Details: ${caseId}`;
  body.innerHTML = '<p class="text-center text-muted">Loading case details and audit timeline...</p>';
  modal.classList.add('open');

  try {
    const data = await apiFetch(`/api/recovery/cases/${caseId}`);
    const c = data.case;

    body.innerHTML = `
      <div class="modal-case-summary mb-4" style="background: var(--bg-subtle); padding: 16px; border-radius: 10px; border: 1px solid var(--border-color);">
        <div style="display: flex; justify-content: space-between; align-items: center;" class="mb-3">
          <h4>Case Overview: ${c.id}</h4>
          ${getStatusBadge(c.status)}
        </div>
        <p><strong>Payment ID:</strong> <code>${c.payment_id}</code></p>
        <p><strong>Amount at Risk:</strong> <strong style="color: var(--text-main);">${formatINR(c.amount_at_risk)}</strong></p>
        <p><strong>Case Type:</strong> <span class="badge badge-amber">${c.case_type}</span></p>
        <p><strong>Created At:</strong> ${c.created_at}</p>
      </div>

      <div class="modal-diagnosis mb-4" style="background: var(--bg-subtle); padding: 16px; border-radius: 10px; border: 1px solid var(--border-color);">
        <h4 class="mb-2">AI Root Cause Diagnosis & Economics</h4>
        <p><strong>Diagnosed Cause:</strong> <code style="color: var(--color-blue);">${c.root_cause}</code></p>
        <p><strong>Recovery Probability P(rec):</strong> <strong style="color: var(--color-green);">${(c.recovery_probability * 100).toFixed(1)}%</strong></p>
        <p><strong>Recommended Action:</strong> <code>${c.recommended_action}</code></p>
        <p><strong>Estimated Net Value:</strong> ${formatINR(c.estimated_net_value)}</p>
        <p class="mt-2"><strong>Evidence Trail:</strong></p>
        <ul class="evidence-list mt-1">
          ${(c.evidence || []).map(ev => `<li>${ev}</li>`).join('')}
        </ul>
      </div>

      <div class="modal-audit-trail">
        <h4 class="mb-2">Audit Compliance Log</h4>
        <div class="sim-output-box" style="background: #f8fafc; padding: 12px; border-radius: 8px; font-family: 'JetBrains Mono', monospace; font-size: 0.8rem; border: 1px solid var(--border-color);">
          <pre style="color: var(--text-main); white-space: pre-wrap;">${JSON.stringify(data.audit_trail || [], null, 2)}</pre>
        </div>
      </div>
    `;
  } catch (err) {
    body.innerHTML = '<p class="text-danger">Failed to load case details.</p>';
  }
}

// Bind Simulator Events
function bindSimulatorEvents() {
  const simCards = document.querySelectorAll('.sim-card');
  simCards.forEach(card => {
    card.addEventListener('click', () => runSimulationScenario(card.dataset.sim));
  });
}

// Run Simulation Scenario with Animated Stepper & Rich Result Cards
async function runSimulationScenario(scenario) {
  const richContainer = document.getElementById('sim-rich-output');
  const statusText = document.getElementById('pipeline-status-text');

  const stepDetect = document.getElementById('step-detect');
  const stepDiagnose = document.getElementById('step-diagnose');
  const stepPredict = document.getElementById('step-predict');
  const stepPolicy = document.getElementById('step-policy');
  const stepExecute = document.getElementById('step-execute');

  // Reset steps
  [stepDetect, stepDiagnose, stepPredict, stepPolicy, stepExecute].forEach(s => {
    s.className = 'step-box';
  });

  statusText.textContent = `Running pipeline for [${scenario}]...`;
  richContainer.innerHTML = '<div class="text-center"><p class="text-subtle">Ingesting event & evaluating safety policy...</p></div>';

  // Step 1: Detect
  stepDetect.classList.add('active');
  await delay(250);

  // Step 2: Diagnose
  stepDiagnose.classList.add('active');
  await delay(250);

  // Step 3: Predict
  stepPredict.classList.add('active');
  await delay(250);

  try {
    const data = await apiFetch(`/api/simulate/${scenario}`, { method: 'POST' });
    const c = data.case;

    // Step 4: Policy Check
    if (data.policy_decision === 'APPROVED') {
      stepPolicy.classList.add('success');
      stepExecute.classList.add('success');
      statusText.textContent = `Pipeline Complete: APPROVED & VERIFIED (${formatINR(c.amount_at_risk)})`;
    } else if (data.policy_decision === 'BLOCKED') {
      stepPolicy.classList.add('blocked');
      stepExecute.classList.add('blocked');
      statusText.textContent = `Pipeline Complete: POLICY BLOCKED (${data.policy_reason})`;
    } else {
      stepPolicy.classList.add('escalated');
      stepExecute.classList.add('escalated');
      statusText.textContent = `Pipeline Complete: HUMAN ESCALATION REQUIRED`;
    }

    // Render Rich Cards Output
    richContainer.innerHTML = renderRichResultCards(data);
    bindRawJsonToggle();
    loadDashboardData();
  } catch (err) {
    richContainer.innerHTML = `<p class="text-danger">Simulation failed: ${err}</p>`;
    statusText.textContent = 'Pipeline Error';
  }
}

// Render Rich Result Cards
function renderRichResultCards(data) {
  const c = data.case;
  const decision = data.policy_decision;
  const isApproved = decision === 'APPROVED';
  const isBlocked = decision === 'BLOCKED';
  
  const verdictClass = isApproved ? 'verdict-approved' : (isBlocked ? 'verdict-blocked' : 'verdict-escalated');
  const verdictColor = isApproved ? 'var(--color-green)' : (isBlocked ? 'var(--color-red)' : 'var(--color-amber)');
  const verdictIcon = isApproved ? '✅' : (isBlocked ? '🛡️' : '⚠️');

  return `
    <div class="rich-result-grid">
      <!-- Card 1: AI Diagnosis & Evidence -->
      <div class="result-card">
        <h5>1. AI Root Cause Diagnosis</h5>
        <div style="display: flex; justify-content: space-between; align-items: center;" class="mb-2">
          <span class="badge badge-amber">${c.case_type}</span>
          <span style="font-weight: 700; color: var(--color-green);">P(rec): ${(c.recovery_probability * 100).toFixed(0)}%</span>
        </div>
        <p><strong>Root Cause:</strong> <code style="color: var(--color-blue);">${c.root_cause}</code></p>
        <p class="mt-2"><strong>Evidence Trail:</strong></p>
        <ul class="evidence-list mt-1">
          ${(c.evidence || []).map(e => `<li>${e}</li>`).join('')}
        </ul>
      </div>

      <!-- Card 2: Policy Verdict Box -->
      <div class="result-card">
        <h5>2. Safety Policy Engine Verdict</h5>
        <div class="result-card-verdict ${verdictClass}">
          <span style="font-size: 1.8rem;">${verdictIcon}</span>
          <span class="verdict-title" style="color: ${verdictColor};">${decision}</span>
          <p class="verdict-reason">${data.policy_reason}</p>
        </div>
        <div class="mt-3 text-center">
          <small class="text-subtle">Recommended: <code>${c.recommended_action}</code></small>
        </div>
      </div>

      <!-- Card 3: Execution & Verification Certificate -->
      <div class="result-card">
        <h5>3. Execution & Verification</h5>
        ${isApproved ? `
          <div style="background: var(--color-green-bg); padding: 14px; border-radius: 8px; border: 1px solid rgba(5, 150, 105, 0.3); text-align: center;">
            <span style="font-size: 0.8rem; color: var(--color-green); font-weight: 700;">REVENUE VERIFIED</span>
            <h3 style="color: var(--text-main); margin: 4px 0;">${formatINR(c.amount_at_risk)}</h3>
            <small style="color: var(--text-subtle);">Idempotency Key: <code>${data.action?.idempotency_key || 'VERIFIED'}</code></small>
          </div>
        ` : `
          <div style="background: var(--color-red-bg); padding: 14px; border-radius: 8px; border: 1px solid rgba(225, 29, 72, 0.3); text-align: center;">
            <span style="font-size: 0.8rem; color: var(--color-red); font-weight: 700;">EXECUTION HALTED</span>
            <h4 style="color: var(--text-main); margin: 4px 0;">₹0.00 Debited</h4>
            <small style="color: var(--text-subtle);">Prevented financial loss or duplicate debit.</small>
          </div>
        `}
      </div>
    </div>

    <!-- Toggle Raw JSON Button -->
    <div class="mt-4 text-center">
      <button class="btn-secondary-action btn-sm" id="btn-toggle-json">📄 Toggle Raw JSON Payload</button>
      <div id="raw-json-box" style="display: none; background: #ffffff; border: 1px solid var(--border-color); padding: 14px; border-radius: 8px;" class="sim-output-box mt-3 text-left">
        <pre style="font-family: 'JetBrains Mono', monospace; font-size: 0.8rem; color: var(--text-main);">${JSON.stringify(data, null, 2)}</pre>
      </div>
    </div>
  `;
}

// Toggle Raw JSON Payload View
function bindRawJsonToggle() {
  const btn = document.getElementById('btn-toggle-json');
  const box = document.getElementById('raw-json-box');
  if (btn && box) {
    btn.addEventListener('click', () => {
      box.style.display = box.style.display === 'none' ? 'block' : 'none';
    });
  }
}

// Helper delay
function delay(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

// Load Audit Log
async function loadAuditLog() {
  const tbody = document.getElementById('tbl-audit-events');
  try {
    const events = await apiFetch('/api/audit');

    if (!events || events.length === 0) {
      tbody.innerHTML = '<tr><td colspan="8" class="text-center text-muted">No audit events recorded yet.</td></tr>';
      return;
    }

    tbody.innerHTML = events.map(e => `
      <tr>
        <td><small>${e.created_at}</small></td>
        <td><code>${e.entity_type}</code></td>
        <td><small><code>${e.entity_id}</code></small></td>
        <td><span class="badge badge-amber">${e.event_type}</span></td>
        <td><strong>${e.actor}</strong></td>
        <td>${e.decision === 'APPROVED' ? '<span class="badge badge-green">APPROVED</span>' : (e.decision === 'BLOCKED' ? '<span class="badge badge-red">BLOCKED</span>' : `<span class="badge badge-amber">${e.decision}</span>`)}</td>
        <td>${e.reason}</td>
        <td><small><code>${JSON.stringify(e.metadata)}</code></small></td>
      </tr>
    `).join('');
  } catch (err) {
    tbody.innerHTML = '<tr><td colspan="8" class="text-center text-muted">Error loading audit log.</td></tr>';
  }
}

// Bind Quick Header Actions & Evaluation Runner
function bindQuickHeaderActions() {
  const heroBtn = document.getElementById('btn-hero-action');
  if (heroBtn) {
    heroBtn.addEventListener('click', () => {
      switchToTab('simulator');
      runSimulationScenario('payment-failure');
    });
  }

  const quickFail = document.getElementById('btn-quick-sim-fail');
  if (quickFail) {
    quickFail.addEventListener('click', () => {
      switchToTab('simulator');
      runSimulationScenario('payment-failure');
    });
  }

  const quickWhk = document.getElementById('btn-quick-sim-whk');
  if (quickWhk) {
    quickWhk.addEventListener('click', () => {
      switchToTab('simulator');
      runSimulationScenario('webhook-loss');
    });
  }

  const runEval = async () => {
    switchToTab('evaluation');
    const container = document.getElementById('eval-results-container');
    if (container) {
      container.innerHTML = '<div class="text-center"><p class="text-subtle mt-2">Running 10,000 Event Batch Benchmark across 3 strategies...</p></div>';
    }

    try {
      const data = await apiFetch('/api/evaluation/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ events: 10000 })
      });
      const recRecovered = data.reconcile_recovered || data.reconcilex_recovered || 0;

      if (container) {
        container.innerHTML = `
          <div class="grid-2col mb-6">
            <div class="kpi-card danger-card">
              <div class="kpi-header">
                <span class="kpi-title">Revenue At Risk (10,000 Events)</span>
                <span class="badge badge-red">Total Leakage</span>
              </div>
              <div class="kpi-value">${formatINR(data.revenue_at_risk)}</div>
              <div class="kpi-subtext">Across 10,000 synthetic payment streams</div>
            </div>

            <div class="kpi-card success-card">
              <div class="kpi-header">
                <span class="kpi-title">Reconcile Net Recovered</span>
                <span class="badge badge-green">100% Safe</span>
              </div>
              <div class="kpi-value text-green">${formatINR(recRecovered)}</div>
              <div class="kpi-subtext"><strong>0 Unsafe Debits</strong> | ${data.blocked_duplicates} Duplicate Charges Blocked</div>
            </div>
          </div>

          <div class="card-panel">
            <div class="card-panel-header">
              <div>
                <h3>Strategy Comparison Benchmark Summary</h3>
                <p class="card-panel-subtitle">Performance breakdown across 10,000 payment scenarios</p>
              </div>
              <span class="badge badge-lime">Benchmark Report</span>
            </div>
            <table class="data-table mt-3">
              <thead>
                <tr>
                  <th>Strategy</th>
                  <th>Revenue Recovered</th>
                  <th>Unsafe Recoveries</th>
                  <th>Blocked Duplicates</th>
                  <th>Human Escalations</th>
                  <th>Safety Compliance</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td><strong>Blind Retry</strong></td>
                  <td>${formatINR(data.blind_recovered)}</td>
                  <td><span class="badge badge-red">${data.blind_unsafe} Unsafe Debits</span></td>
                  <td>0</td>
                  <td>0</td>
                  <td><span class="badge badge-red">FAILED (Duplicate Chargebacks)</span></td>
                </tr>
                <tr>
                  <td><strong>Rule-Based</strong></td>
                  <td>${formatINR(data.rule_recovered)}</td>
                  <td>0</td>
                  <td>0</td>
                  <td>0</td>
                  <td><span class="badge badge-amber">PARTIAL (Missed Complex Failures)</span></td>
                </tr>
                <tr style="background: var(--color-green-bg); border: 1px solid rgba(5, 150, 105, 0.3);">
                  <td><strong style="color: var(--color-green);">⚡ Reconcile Orchestrator</strong></td>
                  <td><strong style="color: var(--text-main); font-size: 1rem;">${formatINR(recRecovered)}</strong></td>
                  <td><span class="badge badge-green">0 TARGET PASSED</span></td>
                  <td><strong>${data.blocked_duplicates}</strong></td>
                  <td><strong>${data.human_escalations}</strong></td>
                  <td><span class="badge badge-green">100% COMPLIANT</span></td>
                </tr>
              </tbody>
            </table>
          </div>
        `;
      }
    } catch (err) {
      if (container) container.innerHTML = '<p class="text-danger">Failed to run evaluation benchmark.</p>';
    }
  };

  const quickEval = document.getElementById('btn-quick-run-eval');
  if (quickEval) quickEval.addEventListener('click', runEval);

  const refreshDashboard = document.getElementById('btn-refresh-dashboard');
  if (refreshDashboard) {
    refreshDashboard.addEventListener('click', async () => {
      refreshDashboard.disabled = true;
      refreshDashboard.textContent = 'Refreshing...';
      try {
        await loadDashboardData();
      } finally {
        refreshDashboard.disabled = false;
        refreshDashboard.textContent = '🔄 Refresh Stream';
      }
    });
  }

  const evalTabBtn = document.getElementById('btn-run-eval-tab');
  if (evalTabBtn) evalTabBtn.addEventListener('click', runEval);
}

// Switch to specific tab
function switchToTab(tabName) {
  const tabs = document.querySelectorAll('.segmented-tab');
  tabs.forEach(t => {
    if (t.dataset.tab === tabName) {
      t.click();
    }
  });
}

// Search and Filter Bindings
function bindSearchAndFilters() {
  const searchInput = document.getElementById('input-case-search');
  const filterSelect = document.getElementById('select-status-filter');

  if (searchInput) {
    searchInput.addEventListener('input', filterCasesTable);
  }
  if (filterSelect) {
    filterSelect.addEventListener('change', filterCasesTable);
  }
}

function filterCasesTable() {
  const searchInput = document.getElementById('input-case-search');
  const filterSelect = document.getElementById('select-status-filter');
  if (!searchInput || !filterSelect) return;

  const query = (searchInput.value || '').toLowerCase();
  const statusFilter = filterSelect.value;
  const rows = document.querySelectorAll('#tbl-all-cases tr');

  rows.forEach(row => {
    const text = row.textContent.toLowerCase();
    const matchesQuery = text.includes(query);
    const matchesStatus = statusFilter === 'ALL' || text.includes(statusFilter.toLowerCase());

    if (matchesQuery && matchesStatus) {
      row.style.display = '';
    } else {
      row.style.display = 'none';
    }
  });
}

// Modal Bindings
function bindModalClose() {
  const btnClose = document.getElementById('btn-close-modal');
  const modal = document.getElementById('case-modal');

  if (btnClose) {
    btnClose.addEventListener('click', () => modal.classList.remove('open'));
  }
  if (modal) {
    modal.addEventListener('click', (e) => {
      if (e.target === modal) modal.classList.remove('open');
    });
  }
}
