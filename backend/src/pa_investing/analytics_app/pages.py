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
            padding: 16px 12px 48px;
          }
          h1, h2, p {
            margin: 0;
          }
          .top-nav {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 12px;
            margin-bottom: 24px;
            border-bottom: 1px solid #dbe4f0;
          }
          .tab {
            color: #1d4ed8;
            border-bottom: 3px solid #2563eb;
            padding: 10px 4px 9px;
            font-weight: 600;
            text-decoration: none;
          }
          .refresh-controls {
            display: flex;
            align-items: center;
            justify-content: flex-end;
            gap: 10px;
            min-width: 0;
          }
          .refresh-status {
            color: #475569;
            font-size: 13px;
            overflow-wrap: anywhere;
          }
          button {
            min-height: 40px;
            border: 1px solid #1d4ed8;
            border-radius: 6px;
            background: #2563eb;
            color: #ffffff;
            cursor: pointer;
            font: inherit;
            font-weight: 600;
            padding: 8px 14px;
          }
          button:hover:not(:disabled) {
            background: #1d4ed8;
          }
          button:focus-visible,
          .tab:focus-visible {
            outline: 3px solid #93c5fd;
            outline-offset: 2px;
          }
          button:disabled {
            cursor: wait;
            opacity: 0.65;
          }
          .intro {
            display: grid;
            gap: 8px;
            margin-bottom: 16px;
          }
          .kpi-grid {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 10px;
            margin-bottom: 16px;
          }
          .kpi-card {
            background: #ffffff;
            border: 1px solid #dbe4f0;
            border-radius: 8px;
            min-width: 0;
            padding: 14px;
          }
          .kpi-label {
            color: #4b5563;
            font-size: 13px;
            margin-bottom: 6px;
          }
          .kpi-value {
            font-size: clamp(20px, 5vw, 28px);
            font-variant-numeric: tabular-nums;
            font-weight: 650;
            overflow-wrap: anywhere;
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
          .calendar {
            display: grid;
            gap: 6px;
          }
          .calendar-grid {
            display: grid;
            grid-template-columns: repeat(7, minmax(0, 1fr));
            gap: 4px;
          }
          .calendar-weekday {
            color: #64748b;
            font-size: 11px;
            font-weight: 600;
            padding: 4px 0;
            text-align: center;
          }
          .calendar-cell,
          .calendar-spacer {
            min-height: 58px;
            border-radius: 6px;
          }
          .calendar-cell {
            display: grid;
            align-content: space-between;
            gap: 4px;
            border: 1px solid #dbe4f0;
            padding: 7px 5px;
            text-decoration: none;
            font-variant-numeric: tabular-nums;
            overflow: hidden;
          }
          .calendar-cell:focus-visible {
            outline: 3px solid #2563eb;
            outline-offset: 2px;
            position: relative;
            z-index: 1;
          }
          .calendar-date {
            font-size: 10px;
            color: #475569;
            white-space: nowrap;
          }
          .calendar-pnl {
            font-size: 12px;
            font-weight: 650;
            overflow-wrap: anywhere;
          }
          .calendar-coverage {
            color: #475569;
            font-size: 9px;
            line-height: 1.2;
            white-space: nowrap;
          }
          .pnl-positive {
            background: #ecfdf5;
            border-color: #86efac;
            color: #166534;
          }
          .pnl-negative {
            background: #fef2f2;
            border-color: #fca5a5;
            color: #991b1b;
          }
          .pnl-flat {
            background: #f8fafc;
            color: #475569;
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
            .top-nav {
              align-items: flex-start;
            }
            .refresh-controls {
              align-items: flex-end;
              flex-direction: column-reverse;
            }
            .calendar-cell,
            .calendar-spacer {
              min-height: 50px;
            }
            .calendar-date {
              font-size: 9px;
            }
            .donut-layout {
              grid-template-columns: 1fr;
            }
            .donut {
              max-width: 190px;
              justify-self: center;
            }
          }
          @media (min-width: 720px) {
            main {
              padding: 24px 16px 48px;
            }
            .kpi-grid {
              grid-template-columns: repeat(4, minmax(0, 1fr));
              gap: 12px;
            }
          }
        </style>
      </head>
      <body>
        <main>
              <nav class="top-nav" aria-label="Portfolio sections">
                <a class="tab" id="portfolio-tab" href="/analysis/portfolio"
                   aria-current="page">Portfolio</a>
                <div class="refresh-controls">
                  <span class="refresh-status" id="refresh-status"
                        aria-live="polite"></span>
                  <button id="refresh-portfolio" type="button">Refresh</button>
                </div>
              </nav>
              <section class="intro">
                <h1>Portfolio Analysis</h1>
                <p>Indicative P&amp;L, allocation, and performance history</p>
              </section>
              <section class="kpi-grid" aria-label="Portfolio summary">
                <article class="kpi-card">
                  <div class="kpi-label">NAV</div>
                  <div class="kpi-value" id="latest-nav">--</div>
                </article>
                <article class="kpi-card">
                  <div class="kpi-label">Indicative DTD P&amp;L</div>
                  <div class="kpi-value" id="dtd-pnl-amount">--</div>
                </article>
                <article class="kpi-card">
                  <div class="kpi-label">Indicative DTD return</div>
                  <div class="kpi-value" id="dtd-pnl-percent">--</div>
                </article>
                <article class="kpi-card">
                  <div class="kpi-label">Reporting coverage</div>
                  <div class="kpi-value" id="reporting-coverage">--</div>
                </article>
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
              <section class="chart-panel calendar" aria-labelledby="calendar-heading">
                <h2 id="calendar-heading">Indicative P&amp;L Calendar</h2>
                <p class="chart-note">
                  Cash flows are not adjusted; values compare available daily snapshots.
                </p>
                <div id="pnl-calendar" aria-live="polite">
                  <div class="chart-note">Loading indicative daily P&amp;L...</div>
                </div>
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

          function formatCurrency(value, currency) {
            if (value === null || value === undefined) {
              return '--';
            }
            const numeric = Number(value);
            if (Number.isNaN(numeric)) {
              return value;
            }
            if (currency) {
              return new Intl.NumberFormat(undefined, {
                style: 'currency',
                currency,
                maximumFractionDigits: 2,
              }).format(numeric);
            }
            return formatValue(numeric, 'currency');
          }

          function calendarCell(point, currency) {
            const amount = point.pnl_amount === null ? null : Number(point.pnl_amount);
            const tone = amount === null || amount === 0
              ? 'pnl-flat'
              : amount > 0 ? 'pnl-positive' : 'pnl-negative';
            const localDate = new Date(`${point.calendar_date}T00:00:00`);
            const dateLabel = new Intl.DateTimeFormat(undefined, {
              month: 'short',
              day: 'numeric',
            }).format(localDate);
            const coverage = Number(point.reporting_coverage);
            const coverageLabel = Number.isNaN(coverage)
              ? String(point.reporting_coverage)
              : `${(coverage * 100).toFixed(1)}%`;
            const amountLabel = amount === null
              ? '--'
              : formatCurrency(point.pnl_amount, currency);
            const tooltip = `Date: ${point.calendar_date}; reporting coverage: ${coverageLabel}`;
            return `
              <time class="calendar-cell ${tone}" datetime="${point.calendar_date}" tabindex="0"
                   title="${escapeHtml(tooltip)}"
                   aria-label="${escapeHtml(`${tooltip}; P&L: ${amountLabel}`)}">
                <span class="calendar-date">${escapeHtml(dateLabel)}</span>
                <span class="calendar-pnl">${escapeHtml(amountLabel)}</span>
                <span class="calendar-coverage">Coverage: ${escapeHtml(coverageLabel)}</span>
              </time>
            `;
          }

          async function loadDailyPnl() {
            const response = await fetch('/analysis/daily-pnl?days=90');
            if (!response.ok) {
              throw new Error(`Daily P&L request failed (${response.status})`);
            }
            const payload = await response.json();
            document.getElementById('latest-nav').textContent =
              formatCurrency(payload.latest_nav, payload.reporting_currency);
            document.getElementById('dtd-pnl-amount').textContent =
              formatCurrency(payload.dtd_pnl_amount, payload.reporting_currency);
            document.getElementById('dtd-pnl-percent').textContent =
              formatValue(payload.dtd_pnl_percent, 'percent');

            const latestPoint = payload.points[payload.points.length - 1];
            document.getElementById('reporting-coverage').textContent = latestPoint
              ? formatValue(latestPoint.reporting_coverage, 'percent')
              : '--';

            const calendar = document.getElementById('pnl-calendar');
            if (!payload.points.length) {
              calendar.innerHTML = '<div class="chart-note">No daily P&L available.</div>';
              return;
            }
            const firstDate = new Date(`${payload.points[0].calendar_date}T00:00:00`);
            const mondayOffset = (firstDate.getDay() + 6) % 7;
            const spacers = '<div class="calendar-spacer" aria-hidden="true"></div>'
              .repeat(mondayOffset);
            const weekdays = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
              .map((day) => `<div class="calendar-weekday">${day}</div>`)
              .join('');
            let previousDay = null;
            const cells = payload.points.map((point) => {
              const day = Date.parse(`${point.calendar_date}T00:00:00Z`);
              const missingDays = previousDay === null
                ? 0
                : Math.max(0, Math.round((day - previousDay) / 86400000) - 1);
              previousDay = day;
              const gaps = '<div class="calendar-spacer" aria-hidden="true"></div>'
                .repeat(missingDays);
              return `${gaps}${calendarCell(point, payload.reporting_currency)}`;
            }).join('');
            calendar.innerHTML = `
              <div class="calendar-grid">
                ${weekdays}${spacers}${cells}
              </div>
            `;
          }

          async function refreshPortfolio() {
            const button = document.getElementById('refresh-portfolio');
            const status = document.getElementById('refresh-status');
            button.disabled = true;
            button.setAttribute('aria-busy', 'true');
            status.textContent = 'Refreshing portfolio...';
            try {
              const response = await fetch('/analysis/refresh', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({}),
              });
              if (!response.ok) {
                let detail = `Request failed (${response.status})`;
                try {
                  const payload = await response.json();
                  detail = payload.detail || detail;
                } catch (_) {
                  // Keep the HTTP status message when the response is not JSON.
                }
                throw new Error(detail);
              }
              await Promise.all([loadCurrentPortfolio(), loadPerformance(), loadDailyPnl()]);
              status.textContent = 'Portfolio refreshed.';
            } catch (error) {
              status.textContent = `Refresh failed: ${error.message}`;
            } finally {
              button.disabled = false;
              button.removeAttribute('aria-busy');
            }
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
          loadDailyPnl().catch(() => {
            document.getElementById('pnl-calendar').innerHTML =
              '<div class="chart-note">Indicative daily P&L unavailable.</div>';
          });
          document.getElementById('refresh-portfolio')
            .addEventListener('click', refreshPortfolio);
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
