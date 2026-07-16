import json
from html import escape

from pa_investing.presentation.fields import (
    PERFORMANCE_POINT_FIELDS,
    PERFORMANCE_SUMMARY_FIELDS,
)


def portfolio_page() -> str:
    summary_cards = "".join(
        f"""
            <article class="summary-card">
              <div class="summary-label">{field.label}</div>
              <div class="summary-value" id="{field.key}">--</div>
            </article>
        """
        for field in PERFORMANCE_SUMMARY_FIELDS
    )
    table_headers = "".join(
        f"<th>{field.label}</th>"
        for field in PERFORMANCE_POINT_FIELDS
    )
    field_config = json.dumps(
        {
            "summary": [
                {"key": field.key, "display_kind": field.display_kind}
                for field in PERFORMANCE_SUMMARY_FIELDS
            ],
            "points": [
                {"key": field.key, "display_kind": field.display_kind}
                for field in PERFORMANCE_POINT_FIELDS
            ],
        }
    )
    html = """
    <html>
      <head>
        <title>Portfolio Analysis</title>
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <style>
          :root {
            color-scheme: light;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
          }
          body {
            margin: 0;
            background: #f5f7fb;
            color: #111827;
          }
          main {
            max-width: 1100px;
            margin: 0 auto;
            padding: 24px 16px 48px;
          }
          h1, h2, p {
            margin: 0;
          }
          .intro {
            display: grid;
            gap: 8px;
            margin-bottom: 24px;
          }
          .summary-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 12px;
            margin: 20px 0 24px;
          }
          .summary-card,
          .chart-panel {
            background: #ffffff;
            border: 1px solid #dbe4f0;
            border-radius: 8px;
            padding: 16px;
          }
          .summary-label {
            color: #4b5563;
            font-size: 14px;
            margin-bottom: 6px;
          }
          .summary-value {
            font-size: 24px;
            font-weight: 600;
            overflow-wrap: anywhere;
            font-variant-numeric: tabular-nums;
          }
          .chart-panel {
            display: grid;
            gap: 12px;
          }
          .chart-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 12px;
            margin-bottom: 12px;
          }
          .chart-stage {
            min-height: 260px;
            display: grid;
            place-items: center;
          }
          .donut-layout {
            width: 100%;
            display: grid;
            grid-template-columns: minmax(140px, 220px) minmax(0, 1fr);
            align-items: center;
            gap: 20px;
          }
          .donut {
            width: 100%;
            aspect-ratio: 1;
            border-radius: 50%;
            position: relative;
            background: #e5e7eb;
          }
          .donut::after {
            content: "";
            position: absolute;
            inset: 28%;
            border-radius: 50%;
            background: #ffffff;
          }
          .legend {
            display: grid;
            gap: 8px;
          }
          .legend-row {
            display: grid;
            grid-template-columns: 12px minmax(0, 1fr) auto;
            gap: 8px;
            align-items: center;
            font-size: 13px;
          }
          .legend-swatch {
            width: 12px;
            height: 12px;
            border-radius: 3px;
          }
          .legend-label {
            overflow-wrap: anywhere;
          }
          .nav-svg {
            width: 100%;
            height: 260px;
            overflow: visible;
          }
          .chart-note {
            color: #64748b;
            font-size: 13px;
          }
          .table-shell {
            overflow-x: auto;
            border-radius: 6px;
            border: 1px solid #dbe4f0;
            background: #f8fbff;
          }
          table {
            width: 100%;
            border-collapse: collapse;
            min-width: 720px;
          }
          th,
          td {
            padding: 12px;
            text-align: left;
            font-size: 12px;
            color: #334155;
            border-bottom: 1px solid #dbe4f0;
            font-variant-numeric: tabular-nums;
            white-space: nowrap;
          }
          tbody tr:last-child td {
            border-bottom: 0;
          }
          .empty-state {
            padding: 16px;
            color: #4b5563;
          }
          @media (max-width: 640px) {
            .donut-layout {
              grid-template-columns: 1fr;
            }
            .donut {
              max-width: 190px;
              justify-self: center;
            }
          }
        </style>
      </head>
      <body>
        <main>
              <section class="intro">
                <h1>Portfolio Analysis</h1>
                <p>Performance History</p>
              </section>
              <section class="summary-grid">
            __SUMMARY_CARDS__
              </section>
              <section class="chart-grid">
                <article class="chart-panel">
                  <h2>Position Allocation</h2>
                  <div class="chart-stage">
                    <div class="donut-layout">
                      <div class="donut" id="allocation-donut"></div>
                      <div class="legend" id="allocation-legend">
                        <div class="chart-note">Loading current holdings...</div>
                      </div>
                    </div>
                  </div>
                </article>
                <article class="chart-panel">
                  <h2>NAV History</h2>
                  <div class="chart-stage" id="nav-chart">
                    <div class="chart-note">Loading performance history...</div>
                  </div>
                </article>
              </section>
              <section class="chart-panel" id="performance-history">
                <h2>Performance History</h2>
                <div class="table-shell">
                  <table>
                    <thead>
                      <tr>__TABLE_HEADERS__</tr>
                    </thead>
                    <tbody id="performance-body">
                      <tr>
                        <td class="empty-state" colspan="__COLUMN_COUNT__">
                          Loading /analysis/performance ...
                        </td>
                      </tr>
                </tbody>
              </table>
            </div>
          </section>
        </main>
        <script>
          const fieldConfig = __FIELD_CONFIG__;
          const chartColors = [
            '#2563eb', '#0f766e', '#ca8a04', '#dc2626', '#7c3aed',
            '#0891b2', '#4d7c0f', '#c2410c', '#475569', '#be185d'
          ];

          function escapeHtml(value) {
            return String(value)
              .replaceAll('&', '&amp;')
              .replaceAll('<', '&lt;')
              .replaceAll('>', '&gt;')
              .replaceAll('"', '&quot;')
              .replaceAll("'", '&#039;');
          }

          function formatValue(value, displayKind) {
            if (value === null || value === undefined) {
              return '--';
            }
            if (displayKind === 'percent') {
              const numeric = Number(value);
              if (Number.isNaN(numeric)) {
                return value;
              }
              return `${(numeric * 100).toFixed(2)}%`;
            }
            if (displayKind === 'currency') {
              const numeric = Number(value);
              if (Number.isNaN(numeric)) {
                return value;
              }
              return new Intl.NumberFormat(undefined, {
                minimumFractionDigits: 0,
                maximumFractionDigits: 2,
              }).format(numeric);
            }
            return value;
          }

          async function loadPerformance() {
            const response = await fetch('/analysis/performance');
            const payload = await response.json();

            for (const field of fieldConfig.summary) {
              const element = document.getElementById(field.key);
              if (element) {
                element.textContent = formatValue(payload[field.key], field.display_kind);
              }
            }

            renderNavChart(payload.points);

            const body = document.getElementById('performance-body');
            if (!payload.points.length) {
              body.innerHTML = `
                <tr>
                  <td class="empty-state" colspan="__COLUMN_COUNT__">
                    No performance history available.
                  </td>
                </tr>
              `;
              return;
            }

            body.innerHTML = payload.points.map((point) => {
              const cells = fieldConfig.points.map((field) => {
                return `<td>${formatValue(point[field.key], field.display_kind)}</td>`;
              }).join('');
              return `<tr>${cells}</tr>`;
            }).join('');
          }

          function renderNavChart(points) {
            const chart = document.getElementById('nav-chart');
            if (!points.length) {
              chart.innerHTML = '<div class="chart-note">No NAV history available.</div>';
              return;
            }
            const values = points.map((point) => Number(point.nav));
            const min = Math.min(...values);
            const max = Math.max(...values);
            const spread = max - min || 1;
            const width = 640;
            const height = 240;
            const padding = 24;
            const coordinates = values.map((value, index) => {
              const x = points.length === 1
                ? width / 2
                : padding + index * ((width - padding * 2) / (points.length - 1));
              const y = height - padding - ((value - min) / spread) * (height - padding * 2);
              return {x, y};
            });
            const polyline = coordinates.map((point) => `${point.x},${point.y}`).join(' ');
            const circles = coordinates.map((point) => (
              `<circle cx="${point.x}" cy="${point.y}" r="4" fill="#2563eb"></circle>`
            )).join('');
            chart.innerHTML = `
              <svg class="nav-svg" viewBox="0 0 ${width} ${height}" role="img"
                   aria-label="Portfolio NAV history">
                <line x1="${padding}" y1="${height - padding}" x2="${width - padding}"
                      y2="${height - padding}" stroke="#cbd5e1"></line>
                <polyline fill="none" stroke="#2563eb" stroke-width="3"
                          stroke-linecap="round" stroke-linejoin="round"
                          points="${polyline}"></polyline>
                ${circles}
              </svg>
              <div class="chart-note">
                ${points.length} persisted snapshot${points.length === 1 ? '' : 's'}
              </div>
            `;
          }

          async function loadCurrentPortfolio() {
            const response = await fetch('/analysis/current');
            const payload = await response.json();
            const holdings = payload.holdings.filter(
              (holding) => holding.reporting_market_value !== null
            );
            const donut = document.getElementById('allocation-donut');
            const legend = document.getElementById('allocation-legend');
            if (!holdings.length) {
              donut.style.background = '#e5e7eb';
              legend.innerHTML = '<div class="chart-note">No allocation available.</div>';
              return;
            }
            let cursor = 0;
            const segments = [];
            holdings.forEach((holding, index) => {
              const weight = Number(holding.portfolio_weight || 0) * 100;
              const start = cursor;
              cursor += weight;
              segments.push(`${chartColors[index % chartColors.length]} ${start}% ${cursor}%`);
            });
            donut.style.background = `conic-gradient(${segments.join(', ')})`;
            legend.innerHTML = holdings.map((holding, index) => {
              const weight = Number(holding.portfolio_weight || 0) * 100;
              return `
                <div class="legend-row">
                  <span class="legend-swatch"
                        style="background:${chartColors[index % chartColors.length]}"></span>
                  <span class="legend-label">${escapeHtml(holding.symbol)}</span>
                  <strong>${weight.toFixed(1)}%</strong>
                </div>
              `;
            }).join('');
          }
          loadPerformance().catch(() => {
            document.getElementById('performance-body').innerHTML = `
              <tr>
                <td class="empty-state" colspan="__COLUMN_COUNT__">
                  Performance history unavailable.
                </td>
              </tr>
              `;
          });
          loadCurrentPortfolio().catch(() => {
            document.getElementById('allocation-legend').innerHTML =
              '<div class="chart-note">Allocation unavailable.</div>';
          });
        </script>
      </body>
    </html>
    """
    return (
        html.replace("__SUMMARY_CARDS__", summary_cards)
        .replace("__TABLE_HEADERS__", table_headers)
        .replace("__COLUMN_COUNT__", str(len(PERFORMANCE_POINT_FIELDS)))
        .replace("__FIELD_CONFIG__", field_config)
    )


def signal_page(signal_id: str) -> str:
    return f"""
    <html>
      <head><title>Signal Analysis</title></head>
      <body>
        <h1>Signal Analysis</h1>
        <p>Signal ID: {escape(signal_id)}</p>
      </body>
    </html>
    """
