/**
 * Feedback Intelligence — Frontend Controller
 * Manages multi-dimensional feedback streams, real-time client filtering,
 * Chart.js analytics, triage drawer actions, and batch data ingestion.
 */

const COLORS = {
  positive: '#2dd9a8',
  negative: '#fb5b72',
  neutral: '#fbbf24',
  brand: '#8b5cf6',
  brand2: '#22d3ee',
  p0: '#fb5b72',
  p1: '#f97316',
  p2: '#38bdf8',
  p3: '#2dd9a8',
  gridline: 'rgba(255,255,255,0.06)',
  text: '#8a90ab',
};

// Global application state
let rawFeedback = [];
let summaryData = {};
const activeFilters = {
  search: '',
  channel: '',
  intent: '',
  sentiment: '',
  urgency: '',
};

// Chart instances
let trendChart, sentimentChart, channelChart;

// ---------------------------------------------------------------------------
// Bootstrap & Data Ingestion
// ---------------------------------------------------------------------------
async function loadAll() {
  let feedbackRes, summaryRes;
  try {
    [feedbackRes, summaryRes] = await Promise.all([
      fetch('/api/feedback').then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      }),
      fetch('/api/summary').then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      }),
    ]);
  } catch (err) {
    console.error('Network error reaching backend:', err);
    const tbody = document.querySelector('#feedback-table tbody');
    if (tbody) {
      tbody.innerHTML =
        '<tr><td colspan="7" style="text-align:center; padding: 24px; color: var(--negative);">Failed to communicate with API server. Please ensure backend is running.</td></tr>';
    }
    return;
  }

  rawFeedback = feedbackRes || [];
  summaryData = summaryRes || {};

  const renderSteps = [
    () => applyFilters(),
    () => renderExecutiveBrief(summaryData.executive_digest),
    () => renderKpis(summaryData),
    () => renderClusters(summaryData.clusters),
    () => renderPainPoints(summaryData.top_pain_points),
    () => renderTrendChart(summaryData.trend),
    () => renderSentimentChart(summaryData.sentiment_counts),
    () => renderChannelChart(summaryData.channel_breakdown),
    () => initTilt(),
  ];

  for (const step of renderSteps) {
    try {
      step();
    } catch (renderErr) {
      console.warn('Dashboard render step warning:', renderErr);
    }
  }
}

// ---------------------------------------------------------------------------
// Executive Briefing Banner
// ---------------------------------------------------------------------------
function renderExecutiveBrief(digest) {
  if (!digest) return;

  const headlineEl = document.getElementById('brief-headline');
  const healthEl = document.getElementById('health-index-val');
  const insightsEl = document.getElementById('brief-insights');

  headlineEl.textContent = digest.takeaway;
  healthEl.textContent = `${digest.health_score > 0 ? '+' : ''}${digest.health_score} NPS (${digest.sentiment_ratio})`;

  const chips = [];

  if (digest.p0_critical_count > 0) {
    chips.push(`
      <div class="insight-chip fire">
        <span>🔥</span> <strong>${digest.p0_critical_count} P0 Critical Blockers</strong> requiring immediate dev review
      </div>
    `);
  }

  if (digest.billing_risk_count > 0) {
    chips.push(`
      <div class="insight-chip risk">
        <span>💸</span> <strong>${digest.billing_risk_count} Financial/Billing Grievances</strong> flagged
      </div>
    `);
  }

  if (digest.top_opportunity) {
    chips.push(`
      <div class="insight-chip opp">
        <span>💡</span> <strong>Roadmap Signal:</strong> ${digest.top_opportunity.title} (${digest.top_opportunity.count} requests)
      </div>
    `);
  }

  insightsEl.innerHTML = chips.join('');
}

// ---------------------------------------------------------------------------
// KPI Cards
// ---------------------------------------------------------------------------
function renderKpis(summary) {
  const pct = summary.sentiment_pct || {};
  const p0Count = (summary.urgency_counts && summary.urgency_counts.P0) || 0;
  const p1Count = (summary.urgency_counts && summary.urgency_counts.P1) || 0;
  const topSubsystem = Object.entries(summary.topic_counts || {}).sort((a, b) => b[1] - a[1])[0];

  const cards = [
    { value: summary.total_feedback, label: 'Total Ingested Entries', percent: false },
    { value: pct.positive || 0, label: 'Positive Sentiment Share', percent: true },
    { value: p0Count + p1Count, label: 'P0/P1 Urgent Action Items', percent: false },
    { value: topSubsystem ? topSubsystem[0] : '—', label: 'Primary Affected Subsystem', percent: false },
  ];

  document.getElementById('kpis').innerHTML = cards.map((c, i) => `
    <div class="kpi">
      <div class="kpi-value" id="kpi-value-${i}">0</div>
      <div class="kpi-label">${c.label}</div>
    </div>
  `).join('');

  cards.forEach((c, i) => {
    const el = document.getElementById(`kpi-value-${i}`);
    if (typeof c.value === 'string' && Number.isNaN(parseFloat(c.value))) {
      el.textContent = c.value;
    } else {
      animateValue(el, c.value, c.percent);
    }
  });
}

function animateValue(el, endValue, isPercent) {
  const numericEnd = parseFloat(endValue);
  if (Number.isNaN(numericEnd)) {
    el.textContent = endValue;
    return;
  }
  const duration = 600;
  const start = performance.now();

  function tick(now) {
    const progress = Math.min((now - start) / duration, 1);
    const eased = 1 - Math.pow(1 - progress, 3);
    const current = numericEnd * eased;
    el.textContent = isPercent ? `${current.toFixed(1)}%` : Math.round(current).toString();
    if (progress < 1) requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);
}

// ---------------------------------------------------------------------------
// Master Problem Clusters
// ---------------------------------------------------------------------------
function renderClusters(clusters) {
  const grid = document.getElementById('clusters-grid');
  const countBadge = document.getElementById('cluster-count-badge');

  if (!clusters || !clusters.length) {
    grid.innerHTML = '<p style="color: var(--text-muted); font-size: 0.85rem;">No problem clusters detected.</p>';
    countBadge.textContent = '0 Clusters';
    return;
  }

  countBadge.textContent = `${clusters.length} Synthesized Problem Clusters`;

  grid.innerHTML = clusters.map(c => `
    <div class="cluster-card">
      <div class="cluster-header">
        <h4 class="cluster-title">${escapeHtml(c.title)}</h4>
        <span class="badge-urgency ${c.urgency}">${c.urgency}</span>
      </div>
      <div style="display: flex; gap: 8px; align-items: center;">
        <span class="cluster-count">${c.count} Reports</span>
        <span class="intent-tag">${c.intent}</span>
      </div>
      <p class="cluster-quote">"${escapeHtml(c.sample_quote)}"</p>
      <div class="cluster-rec">
        <strong>Action:</strong> ${escapeHtml(c.recommendation)}
      </div>
    </div>
  `).join('');
}

// ---------------------------------------------------------------------------
// Analytics Charts (Chart.js)
// ---------------------------------------------------------------------------
function renderTrendChart(trend) {
  if (typeof Chart === 'undefined' || !trend) return;
  const ctx = document.getElementById('trend-chart');
  if (!ctx) return;
  const labels = trend.map(t => t.date.slice(5));
  const data = {
    labels,
    datasets: [
      { label: 'Positive', data: trend.map(t => t.positive), borderColor: COLORS.positive, backgroundColor: COLORS.positive, tension: 0.35 },
      { label: 'Negative', data: trend.map(t => t.negative), borderColor: COLORS.negative, backgroundColor: COLORS.negative, tension: 0.35 },
      { label: 'Neutral', data: trend.map(t => t.neutral), borderColor: COLORS.neutral, backgroundColor: COLORS.neutral, tension: 0.35 },
    ],
  };

  if (trendChart) {
    trendChart.data = data;
    trendChart.update();
    return;
  }

  trendChart = new Chart(ctx, {
    type: 'line',
    data,
    options: baseChartOptions({ legend: true }),
  });
}

function renderSentimentChart(counts) {
  if (typeof Chart === 'undefined' || !counts) return;
  const ctx = document.getElementById('sentiment-chart');
  if (!ctx) return;
  const keys = ['positive', 'negative', 'neutral'].filter(k => counts[k]);
  const data = {
    labels: keys.map(k => k.charAt(0).toUpperCase() + k.slice(1)),
    datasets: [{
      data: keys.map(k => counts[k]),
      backgroundColor: keys.map(k => COLORS[k]),
      borderWidth: 0,
    }],
  };

  if (sentimentChart) {
    sentimentChart.data = data;
    sentimentChart.update();
    return;
  }

  sentimentChart = new Chart(ctx, {
    type: 'doughnut',
    data,
    options: {
      cutout: '68%',
      responsive: true,
      plugins: {
        legend: { position: 'bottom', labels: { color: COLORS.text, boxWidth: 12 } },
      },
    },
  });
}

function renderChannelChart(channels) {
  if (typeof Chart === 'undefined' || !channels) return;
  const ctx = document.getElementById('channel-chart');
  if (!ctx) return;
  const labels = Object.keys(channels || {});
  
  const data = {
    labels,
    datasets: [
      {
        label: 'Positive',
        data: labels.map(l => channels[l].positive || 0),
        backgroundColor: COLORS.positive,
        borderRadius: 4,
      },
      {
        label: 'Negative',
        data: labels.map(l => channels[l].negative || 0),
        backgroundColor: COLORS.negative,
        borderRadius: 4,
      },
      {
        label: 'Neutral',
        data: labels.map(l => channels[l].neutral || 0),
        backgroundColor: COLORS.neutral,
        borderRadius: 4,
      },
    ],
  };

  if (channelChart) {
    channelChart.data = data;
    channelChart.update();
    return;
  }

  channelChart = new Chart(ctx, {
    type: 'bar',
    data,
    options: {
      responsive: true,
      plugins: {
        legend: { display: true, position: 'bottom', labels: { color: COLORS.text, boxWidth: 12 } },
      },
      scales: {
        x: { stacked: true, grid: { color: COLORS.gridline }, ticks: { color: COLORS.text } },
        y: { stacked: true, grid: { color: COLORS.gridline }, ticks: { color: COLORS.text }, beginAtZero: true },
      },
    },
  });
}

function baseChartOptions({ legend = false } = {}) {
  return {
    responsive: true,
    plugins: {
      legend: { display: legend, position: 'bottom', labels: { color: COLORS.text, boxWidth: 12 } },
    },
    scales: {
      x: { grid: { color: COLORS.gridline }, ticks: { color: COLORS.text } },
      y: { grid: { color: COLORS.gridline }, ticks: { color: COLORS.text }, beginAtZero: true },
    },
  };
}

function renderPainPoints(painPoints) {
  const el = document.getElementById('pain-points');
  if (!painPoints || !painPoints.length) {
    el.innerHTML = '<li>No negative friction recorded yet.</li>';
    return;
  }
  el.innerHTML = painPoints.map(([topic, count]) => `
    <li>${escapeHtml(topic)}<span class="pain-count">${count} complaints</span></li>
  `).join('');
}

// ---------------------------------------------------------------------------
// Filtering & Table View
// ---------------------------------------------------------------------------
function applyFilters() {
  const q = activeFilters.search.toLowerCase().trim();

  const filtered = rawFeedback.filter(item => {
    if (q) {
      const matchText = item.text.toLowerCase().includes(q);
      const matchTopic = (item.topics || []).some(t => t.toLowerCase().includes(q));
      const matchIntent = (item.intent || '').toLowerCase().includes(q);
      const matchSource = (item.source || '').toLowerCase().includes(q);
      if (!matchText && !matchTopic && !matchIntent && !matchSource) return false;
    }

    if (activeFilters.channel && item.source !== activeFilters.channel) {
      return false;
    }

    if (activeFilters.intent && item.intent !== activeFilters.intent) {
      return false;
    }

    if (activeFilters.sentiment && item.sentiment !== activeFilters.sentiment) {
      return false;
    }

    if (activeFilters.urgency && item.urgency !== activeFilters.urgency) {
      return false;
    }

    return true;
  });

  renderTable(filtered);
  document.getElementById('filtered-count').textContent =
    filtered.length === rawFeedback.length
      ? `Showing all ${rawFeedback.length} entries`
      : `Showing ${filtered.length} of ${rawFeedback.length} entries`;
}

function renderTable(items) {
  const tbody = document.querySelector('#feedback-table tbody');
  if (!items.length) {
    tbody.innerHTML = '<tr><td colspan="7" style="text-align:center; padding: 24px; color: var(--text-muted);">No entries match the current filter criteria.</td></tr>';
    return;
  }

  tbody.innerHTML = items.map(item => `
    <tr>
      <td>${escapeHtml(item.date)}</td>
      <td><strong>${escapeHtml(item.source)}</strong></td>
      <td class="feedback-text">${escapeHtml(item.text)}</td>
      <td>
        <div class="intent-tag">${escapeHtml(item.intent || 'General')}</div>
        <div>${(item.topics || []).map(t => `<span class="topic-tag">${escapeHtml(t)}</span>`).join('')}</div>
      </td>
      <td>
        <span class="badge-urgency ${item.urgency || 'P3'}">${item.urgency || 'P3'}</span>
      </td>
      <td>
        <span class="badge ${item.sentiment}">${item.sentiment}</span>
      </td>
      <td>
        <button class="btn-triage" onclick="openTriageModal(${item.id})">⚡ Triage</button>
      </td>
    </tr>
  `).join('');
}

// ---------------------------------------------------------------------------
// Triage Drawer & Action Synthesis
// ---------------------------------------------------------------------------
window.openTriageModal = async function(id) {
  const item = rawFeedback.find(i => i.id === id);
  if (!item) return;

  const modal = document.getElementById('triage-modal');
  const badgeEl = document.getElementById('modal-urgency-badge');
  badgeEl.className = `modal-badge ${item.urgency}`;
  badgeEl.textContent = `${item.urgency} Urgency (${item.urgency_score || 0}/100)`;

  document.getElementById('modal-channel').textContent = item.source;
  document.getElementById('modal-date').textContent = item.date;
  document.getElementById('modal-text').textContent = item.text;

  const tagsEl = document.getElementById('modal-tags');
  tagsEl.innerHTML = `
    <span class="topic-tag">${item.intent}</span>
    ${(item.topics || []).map(t => `<span class="topic-tag">${t}</span>`).join('')}
    <span class="badge ${item.sentiment}">${item.sentiment}</span>
  `;

  // Fetch or generate response drafts
  document.getElementById('draft-reply-text').value = 'Generating contextual customer response...';
  document.getElementById('ticket-markdown-text').value = 'Formatting developer ticket markdown...';

  modal.classList.add('open');

  try {
    const [replyRes, ticketRes] = await Promise.all([
      fetch('/api/feedback/draft-reply', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: item.id, text: item.text }),
      }).then(r => r.json()),
      fetch('/api/feedback/create-ticket', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: item.id, text: item.text }),
      }).then(r => r.json()),
    ]);

    document.getElementById('draft-reply-text').value = replyRes.reply;
    document.getElementById('ticket-markdown-text').value = ticketRes.ticket;
  } catch (err) {
    console.error('Failed to generate action templates:', err);
  }
};

function closeTriageModal() {
  document.getElementById('triage-modal').classList.remove('open');
}

// ---------------------------------------------------------------------------
// Batch Upload & File Ingestion
// ---------------------------------------------------------------------------
function initBatchModal() {
  const modal = document.getElementById('batch-modal');
  const dropZone = document.getElementById('drop-zone');
  const fileInput = document.getElementById('batch-file-input');
  const statusEl = document.getElementById('batch-status');

  document.getElementById('btn-open-batch').addEventListener('click', () => {
    statusEl.textContent = '';
    modal.classList.add('open');
  });

  document.getElementById('btn-close-batch').addEventListener('click', () => {
    modal.classList.remove('open');
  });

  document.getElementById('btn-browse-file').addEventListener('click', () => {
    fileInput.click();
  });

  fileInput.addEventListener('change', (e) => {
    if (e.target.files.length) uploadFile(e.target.files[0]);
  });

  ['dragenter', 'dragover'].forEach(eventName => {
    dropZone.addEventListener(eventName, (e) => {
      e.preventDefault();
      dropZone.classList.add('dragover');
    });
  });

  ['dragleave', 'drop'].forEach(eventName => {
    dropZone.addEventListener(eventName, (e) => {
      e.preventDefault();
      dropZone.classList.remove('dragover');
    });
  });

  dropZone.addEventListener('drop', (e) => {
    if (e.dataTransfer.files.length) {
      uploadFile(e.dataTransfer.files[0]);
    }
  });

  async function uploadFile(file) {
    statusEl.textContent = `Processing ${file.name}...`;
    const reader = new FileReader();

    reader.onload = async (e) => {
      const content = e.target.result;
      const isJson = file.name.endsWith('.json');

      try {
        const res = await fetch('/api/feedback/batch', {
          method: 'POST',
          headers: {
            'Content-Type': isJson ? 'application/json' : 'text/csv',
          },
          body: content,
        });

        const data = await res.json();
        statusEl.innerHTML = `<span style="color: var(--positive);">✓ Ingested ${data.imported_count || 0} entries successfully!</span>`;
        setTimeout(() => {
          modal.classList.remove('open');
          loadAll();
        }, 1200);
      } catch (err) {
        statusEl.innerHTML = '<span style="color: var(--negative);">Upload failed. Please check file structure.</span>';
      }
    };

    reader.readAsText(file);
  }
}

// ---------------------------------------------------------------------------
// Toast Notification
// ---------------------------------------------------------------------------
function showToast(message) {
  const toast = document.getElementById('toast');
  toast.textContent = message;
  toast.classList.add('show');
  setTimeout(() => toast.classList.remove('show'), 2200);
}

// ---------------------------------------------------------------------------
// UI Interactions & Event Wiring
// ---------------------------------------------------------------------------
function initInteractions() {
  // Live search
  document.getElementById('filter-search').addEventListener('input', (e) => {
    activeFilters.search = e.target.value;
    applyFilters();
  });

  // Select dropdown filters
  document.getElementById('filter-channel').addEventListener('change', (e) => {
    activeFilters.channel = e.target.value;
    applyFilters();
  });

  document.getElementById('filter-intent').addEventListener('change', (e) => {
    activeFilters.intent = e.target.value;
    applyFilters();
  });

  document.getElementById('filter-sentiment').addEventListener('change', (e) => {
    activeFilters.sentiment = e.target.value;
    applyFilters();
  });

  // Urgency pill tabs
  document.querySelectorAll('.urgency-pill').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.urgency-pill').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      activeFilters.urgency = btn.dataset.urgency;
      applyFilters();
    });
  });

  // Close modals
  document.getElementById('btn-close-triage').addEventListener('click', closeTriageModal);
  document.getElementById('triage-modal').addEventListener('click', (e) => {
    if (e.target.id === 'triage-modal') closeTriageModal();
  });

  // Tab switching in triage drawer
  document.querySelectorAll('.action-tabs .tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.action-tabs .tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
      btn.classList.add('active');
      document.getElementById(btn.dataset.tab).classList.add('active');
    });
  });

  // Clipboard copy actions
  document.getElementById('btn-copy-reply').addEventListener('click', () => {
    const text = document.getElementById('draft-reply-text').value;
    navigator.clipboard.writeText(text);
    showToast('Customer reply copied to clipboard!');
  });

  document.getElementById('btn-copy-ticket').addEventListener('click', () => {
    const text = document.getElementById('ticket-markdown-text').value;
    navigator.clipboard.writeText(text);
    showToast('Developer ticket markdown copied!');
  });

  // Export handlers
  document.getElementById('btn-export-csv').addEventListener('click', () => {
    window.location.href = '/api/export?format=csv';
  });

  document.getElementById('btn-export-json').addEventListener('click', () => {
    window.location.href = '/api/export?format=json';
  });

  // Single feedback ingestion
  document.getElementById('feedback-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const textEl = document.getElementById('feedback-text');
    const sourceEl = document.getElementById('feedback-source');
    const resultEl = document.getElementById('form-result');
    const text = textEl.value.trim();
    if (!text) return;

    try {
      const res = await fetch('/api/feedback', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, source: sourceEl.value }),
      });
      const item = await res.json();

      resultEl.textContent = `Classified as ${item.urgency} · ${item.intent} (${item.sentiment})`;
      resultEl.className = `form-result ${item.sentiment}`;
      textEl.value = '';

      loadAll();
    } catch (err) {
      resultEl.textContent = 'Submission error. Check console.';
      resultEl.className = 'form-result negative';
    }
  });

  initBatchModal();
}

// ---------------------------------------------------------------------------
// 3D Panel Tilt
// ---------------------------------------------------------------------------
function initTilt() {
  document.querySelectorAll('.tilt').forEach(el => {
    if (el.dataset.tiltBound) return;
    el.dataset.tiltBound = 'true';

    el.addEventListener('mousemove', (e) => {
      const rect = el.getBoundingClientRect();
      const x = (e.clientX - rect.left) / rect.width - 0.5;
      const y = (e.clientY - rect.top) / rect.height - 0.5;
      const rotateX = (-y * 5).toFixed(2);
      const rotateY = (x * 5).toFixed(2);
      el.style.transform = `perspective(1000px) rotateX(${rotateX}deg) rotateY(${rotateY}deg) translateY(-2px)`;
    });

    el.addEventListener('mouseleave', () => {
      el.style.transform = 'perspective(1000px) rotateX(0deg) rotateY(0deg) translateY(0)';
    });
  });
}

function escapeHtml(str) {
  if (typeof str !== 'string') return '';
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

// ---------------------------------------------------------------------------
// Animated Custom Green Cursor Controller
// ---------------------------------------------------------------------------
function initCustomCursor() {
  const dot = document.getElementById('cursor-dot');
  const ring = document.getElementById('cursor-ring');
  if (!dot || !ring) return;

  if (window.matchMedia('(pointer: coarse)').matches) return;

  let mouseX = window.innerWidth / 2;
  let mouseY = window.innerHeight / 2;
  let ringX = mouseX;
  let ringY = mouseY;
  let isVisible = false;

  window.addEventListener('mousemove', (e) => {
    mouseX = e.clientX;
    mouseY = e.clientY;
    if (!isVisible) {
      isVisible = true;
      dot.classList.add('cursor-visible');
      ring.classList.add('cursor-visible');
    }
    dot.style.transform = `translate(${mouseX}px, ${mouseY}px) translate(-50%, -50%)`;
  });

  document.addEventListener('mouseleave', () => {
    isVisible = false;
    dot.classList.remove('cursor-visible');
    ring.classList.remove('cursor-visible');
  });

  document.addEventListener('mouseenter', () => {
    isVisible = true;
    dot.classList.add('cursor-visible');
    ring.classList.add('cursor-visible');
  });

  window.addEventListener('mousedown', () => {
    ring.classList.add('clicking');
    dot.classList.add('clicking');
  });

  window.addEventListener('mouseup', () => {
    ring.classList.remove('clicking');
    dot.classList.remove('clicking');
  });

  const interactiveSelector = 'a, button, select, option, input, textarea, .btn-secondary, .btn-ghost, .btn-triage, .urgency-pill, .tab-btn, .cluster-card, .kpi, .drop-zone, tr, [role="button"]';

  document.addEventListener('mouseover', (e) => {
    if (e.target.closest(interactiveSelector)) {
      ring.classList.add('hovering');
      dot.classList.add('hovering');
    }
  });

  document.addEventListener('mouseout', (e) => {
    if (e.target.closest(interactiveSelector)) {
      ring.classList.remove('hovering');
      dot.classList.remove('hovering');
    }
  });

  function renderCursor() {
    ringX += (mouseX - ringX) * 0.18;
    ringY += (mouseY - ringY) * 0.18;
    ring.style.transform = `translate(${ringX}px, ${ringY}px) translate(-50%, -50%)`;
    requestAnimationFrame(renderCursor);
  }
  requestAnimationFrame(renderCursor);
}

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', () => {
  initInteractions();
  initCustomCursor();
  loadAll();
});