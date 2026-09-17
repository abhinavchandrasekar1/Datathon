const COLORS = {
  positive: '#34c77b',
  negative: '#e2574c',
  neutral: '#c9a227',
  brand: '#5b8def',
  gridline: '#262c40',
  text: '#8b93a7',
};

let trendChart, sentimentChart, topicChart;

async function loadAll() {
  let feedback, summary;
  try {
    [feedback, summary] = await Promise.all([
      fetch('/api/feedback').then(r => r.json()),
      fetch('/api/summary').then(r => r.json()),
    ]);
  } catch (err) {
    console.error('Could not load data from the server:', err);
    document.querySelector('#feedback-table tbody').innerHTML =
      '<tr><td colspan="5">Could not reach the server. Is app.py still running?</td></tr>';
    return;
  }

  // Render the table and KPIs first — these have no dependency on Chart.js,
  // so they always show even if the charting library fails to load.
  const steps = [
    () => renderTable(feedback),
    () => renderKpis(summary),
    () => renderPainPoints(summary.top_pain_points),
    () => renderTrendChart(summary.trend),
    () => renderSentimentChart(summary.sentiment_counts),
    () => renderTopicChart(summary.topic_counts),
  ];

  for (const step of steps) {
    try {
      step();
    } catch (err) {
      console.error('Dashboard render step failed:', err);
    }
  }
}

function renderKpis(summary) {
  const pct = summary.sentiment_pct || {};
  const topTopic = Object.entries(summary.topic_counts || {})
    .sort((a, b) => b[1] - a[1])[0];

  const cards = [
    { value: summary.total_feedback, label: 'Total feedback analyzed' },
    { value: `${pct.positive || 0}%`, label: 'Positive sentiment' },
    { value: `${pct.negative || 0}%`, label: 'Negative sentiment' },
    { value: topTopic ? topTopic[0] : '—', label: 'Most discussed topic' },
  ];

  document.getElementById('kpis').innerHTML = cards.map(c => `
    <div class="kpi">
      <div class="kpi-value">${c.value}</div>
      <div class="kpi-label">${c.label}</div>
    </div>
  `).join('');
}

function renderTrendChart(trend) {
  const ctx = document.getElementById('trend-chart');
  const labels = trend.map(t => t.date.slice(5));
  const data = {
    labels,
    datasets: [
      { label: 'Positive', data: trend.map(t => t.positive), borderColor: COLORS.positive, backgroundColor: COLORS.positive, tension: 0.35 },
      { label: 'Negative', data: trend.map(t => t.negative), borderColor: COLORS.negative, backgroundColor: COLORS.negative, tension: 0.35 },
      { label: 'Neutral', data: trend.map(t => t.neutral), borderColor: COLORS.neutral, backgroundColor: COLORS.neutral, tension: 0.35 },
    ],
  };
  if (trendChart) { trendChart.data = data; trendChart.update(); return; }
  trendChart = new Chart(ctx, {
    type: 'line',
    data,
    options: baseOptions({ legend: true }),
  });
}

function renderSentimentChart(counts) {
  const ctx = document.getElementById('sentiment-chart');
  const labels = ['positive', 'negative', 'neutral'].filter(k => counts[k]);
  const data = {
    labels: labels.map(l => l[0].toUpperCase() + l.slice(1)),
    datasets: [{
      data: labels.map(l => counts[l]),
      backgroundColor: labels.map(l => COLORS[l]),
      borderWidth: 0,
    }],
  };
  if (sentimentChart) { sentimentChart.data = data; sentimentChart.update(); return; }
  sentimentChart = new Chart(ctx, {
    type: 'doughnut',
    data,
    options: {
      cutout: '65%',
      plugins: { legend: { position: 'bottom', labels: { color: COLORS.text } } },
    },
  });
}

function renderTopicChart(topicCounts) {
  const ctx = document.getElementById('topic-chart');
  const entries = Object.entries(topicCounts).sort((a, b) => b[1] - a[1]);
  const data = {
    labels: entries.map(e => e[0]),
    datasets: [{
      data: entries.map(e => e[1]),
      backgroundColor: COLORS.brand,
      borderRadius: 4,
      maxBarThickness: 28,
    }],
  };
  if (topicChart) { topicChart.data = data; topicChart.update(); return; }
  topicChart = new Chart(ctx, {
    type: 'bar',
    data,
    options: baseOptions({ legend: false, indexAxis: 'y' }),
  });
}

function baseOptions({ legend = false, indexAxis = 'x' } = {}) {
  return {
    indexAxis,
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
  if (!painPoints.length) {
    el.innerHTML = '<li>No negative feedback yet — nice.</li>';
    return;
  }
  el.innerHTML = painPoints.map(([topic, count]) => `
    <li>${topic}<span class="pain-count">${count}</span></li>
  `).join('');
}

function renderTable(feedback) {
  const tbody = document.querySelector('#feedback-table tbody');
  const rows = [...feedback].reverse().slice(0, 12);
  tbody.innerHTML = rows.map(item => `
    <tr>
      <td>${item.date}</td>
      <td>${item.source}</td>
      <td class="feedback-text">${escapeHtml(item.text)}</td>
      <td>${item.topics.map(t => `<span class="topic-tag">${t}</span>`).join('')}</td>
      <td><span class="badge ${item.sentiment}">${item.sentiment}</span></td>
    </tr>
  `).join('');
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

document.getElementById('feedback-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const textEl = document.getElementById('feedback-text');
  const sourceEl = document.getElementById('feedback-source');
  const resultEl = document.getElementById('form-result');
  const text = textEl.value.trim();
  if (!text) return;

  const res = await fetch('/api/feedback', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text, source: sourceEl.value }),
  });
  const item = await res.json();

  resultEl.textContent = `Scored as ${item.sentiment} · topics: ${item.topics.join(', ')}`;
  resultEl.className = `form-result ${item.sentiment}`;
  textEl.value = '';

  loadAll();
});

loadAll();