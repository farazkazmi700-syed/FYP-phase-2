const statusEl = document.getElementById("analytics-status");
const insightsEl = document.getElementById("session-insights");
const topicEl = document.getElementById("topic-performance");
const graphsEl = document.getElementById("analytics-graphs");
const tablesEl = document.getElementById("analytics-tables");

function formatValue(value) {
  if (value === null || value === undefined) return "N/A";
  return typeof value === "number" ? Number(value.toFixed(2)) : value;
}

function card(label, value) {
  return `<article class="metric-card"><span>${label}</span><strong>${formatValue(value)}</strong></article>`;
}

function table(title, rows) {
  if (!rows.length) {
    return `<section class="analytics-table"><h2>${title}</h2><p class="empty-state">No data yet.</p></section>`;
  }

  const columns = Object.keys(rows[0]);
  const header = columns.map((column) => `<th>${column.replaceAll("_", " ")}</th>`).join("");
  const body = rows.map((row) => {
    const cells = columns.map((column) => `<td>${formatValue(row[column])}</td>`).join("");
    return `<tr>${cells}</tr>`;
  }).join("");

  return `
    <section class="analytics-table">
      <h2>${title}</h2>
      <div class="table-scroll">
        <table>
          <thead><tr>${header}</tr></thead>
          <tbody>${body}</tbody>
        </table>
      </div>
    </section>
  `;
}

function barGraph(graph) {
  const max = Math.max(...graph.values.filter((value) => value !== null), 1);
  const bars = graph.labels.map((label, index) => {
    const value = graph.values[index] || 0;
    const height = Math.max((value / max) * 160, value ? 8 : 0);
    const x = 24 + index * 58;
    return `
      <rect x="${x}" y="${180 - height}" width="34" height="${height}" rx="4"></rect>
      <text x="${x + 17}" y="198" text-anchor="middle">${String(label).slice(0, 8)}</text>
    `;
  }).join("");

  return `<svg class="chart-svg" viewBox="0 0 420 220" role="img">${bars}</svg>`;
}

function lineGraph(graph) {
  const values = graph.values.map((value) => value || 0);
  const max = Math.max(...values, 1);
  const points = values.map((value, index) => {
    const x = 24 + index * (360 / Math.max(values.length - 1, 1));
    const y = 180 - (value / max) * 150;
    return `${x},${y}`;
  }).join(" ");

  return `
    <svg class="chart-svg" viewBox="0 0 420 220" role="img">
      <polyline points="${points}" fill="none" stroke-width="3"></polyline>
      ${points.split(" ").map((point) => {
        const [x, y] = point.split(",");
        return `<circle cx="${x}" cy="${y}" r="4"></circle>`;
      }).join("")}
    </svg>
  `;
}

function pieGraph(graph) {
  const total = graph.values.reduce((sum, value) => sum + value, 0);
  if (!total) return `<p class="empty-state">No data yet.</p>`;

  const legend = graph.labels.map((label, index) => {
    const value = graph.values[index];
    const percent = Math.round((value / total) * 100);
    return `<li><span></span>${label}: ${percent}%</li>`;
  }).join("");

  return `<div class="pie-placeholder"><ul>${legend}</ul></div>`;
}

function graphCard(key, graph) {
  const graphHtml = graph.type === "line"
    ? lineGraph(graph)
    : graph.type === "pie"
      ? pieGraph(graph)
      : barGraph(graph);

  return `
    <article class="graph-card" data-graph="${key}">
      <h2>${graph.title}</h2>
      ${graphHtml}
    </article>
  `;
}

function renderDashboard(data) {
  const metrics = data.metrics;
  const correctness = metrics.correctness_evaluation;

  // FR21: session-level insights are displayed as compact metric cards.
  insightsEl.innerHTML = [
    card("Sessions", data.sessions.length),
    card("Response avg ms", metrics.response_time_statistics.average_ms),
    card("Rating average", metrics.rating_averages.average),
    card("Correctness %", correctness.overall_correctness_percentage),
  ].join("");

  // FR21: topic-based performance appears as its own dashboard table.
  topicEl.innerHTML = `
    <h2>Topic-based performance</h2>
    ${table("Topic vs accuracy", data.tables.topic_vs_accuracy)}
  `;

  graphsEl.innerHTML = Object.entries(data.graphs)
    .map(([key, graph]) => graphCard(key, graph))
    .join("");

  // FR21: analytical tables are displayed for review and reporting.
  tablesEl.innerHTML = `
    <h2>Analytical tables</h2>
    ${table("Reply correctness", data.tables.reply_correctness_table)}
    ${table("Phase-wise accuracy", data.tables.phase_wise_accuracy)}
    ${table("Response time summary", data.tables.response_time_summary)}
    ${table("Rating distribution", data.tables.rating_distribution)}
    ${table("Length preference", data.tables.length_preference)}
  `;
}

async function loadAnalytics() {
  try {
    const response = await fetch("/api/analytics/sessions");
    if (!response.ok) throw new Error("Unable to load analytics.");
    const data = await response.json();
    renderDashboard(data);
    statusEl.textContent = "Analytics loaded.";
  } catch (error) {
    statusEl.textContent = error.message;
    statusEl.classList.add("error");
  }
}

loadAnalytics();
