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
          .nav-tabs {
            display: flex;
            gap: 18px;
          }
          .tab:not([aria-current="page"]) {
            border-bottom-color: transparent;
            color: #64748b;
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
          .pnl-text-positive {
            color: #166534;
            font-weight: 650;
          }
          .pnl-text-negative {
            color: #991b1b;
            font-weight: 650;
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
                <div class="nav-tabs">
                  <a class="tab" id="portfolio-tab" href="/analysis/portfolio"
                     aria-current="page">Portfolio</a>
                  <a class="tab" href="/analysis/position-chart">Position Chart</a>
                </div>
                <div class="refresh-controls">
                  <span class="refresh-status" id="refresh-status"
                        aria-live="polite"></span>
                  <button id="refresh-positions" type="button">Refresh Positions</button>
                  <button id="refresh-history" type="button">Refresh History</button>
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
                  <div class="kpi-label" id="dtd-pnl-label">DTD P&amp;L</div>
                  <div class="kpi-value" id="dtd-pnl-amount">--</div>
                </article>
                <article class="kpi-card">
                  <div class="kpi-label" id="dtd-return-label">DTD return</div>
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
                <h2 id="calendar-heading">P&amp;L Calendar</h2>
                <p class="chart-note" id="calendar-note">
                  Loading daily P&amp;L source...
                </p>
                <div id="pnl-calendar" aria-live="polite">
                  <div class="chart-note">Loading indicative daily P&amp;L...</div>
                </div>
              </section>
              <section class="chart-panel" aria-labelledby="broker-pnl-heading">
                <h2 id="broker-pnl-heading">Latest Broker P&amp;L Contributors</h2>
                <p class="chart-note" id="broker-pnl-note">
                  Loading broker-reported daily P&amp;L...
                </p>
                <div class="table-shell">
                  <table>
                    <thead>
                      <tr>
                        <th>Symbol</th>
                        <th>Asset</th>
                        <th>Close Qty</th>
                        <th>Prior Open MTM</th>
                        <th>Trade MTM</th>
                        <th>Commissions</th>
                        <th>Total</th>
                      </tr>
                    </thead>
                    <tbody id="broker-pnl-body">
                      <tr>
                        <td class="empty-state" colspan="7">
                          Loading /analysis/broker-daily-pnl ...
                        </td>
                      </tr>
                    </tbody>
                  </table>
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
            const exactCoverage = String(point.reporting_coverage);
            const coverageLabel = Number.isNaN(coverage)
              ? exactCoverage
              : `${(coverage * 100).toFixed(0)}%`;
            const amountLabel = amount === null
              ? '--'
              : formatCurrency(point.pnl_amount, currency);
            const tooltip = `Date: ${point.calendar_date}; reporting coverage: ${exactCoverage}`;
            return `
              <time class="calendar-cell ${tone}" datetime="${point.calendar_date}" tabindex="0"
                   title="${escapeHtml(tooltip)}"
                   aria-label="${escapeHtml(`${tooltip}; P&L: ${amountLabel}`)}">
                <span class="calendar-date">${escapeHtml(dateLabel)}</span>
                <span class="calendar-pnl">${escapeHtml(amountLabel)}</span>
                <span class="calendar-coverage">${escapeHtml(coverageLabel)}</span>
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
            document.getElementById('dtd-pnl-label').textContent = payload.indicative
              ? 'Indicative DTD P&L'
              : 'Broker DTD P&L';
            document.getElementById('dtd-return-label').textContent = payload.indicative
              ? 'Indicative DTD return'
              : 'Broker DTD return';
            document.getElementById('calendar-note').textContent = payload.indicative
              ? 'Indicative values compare available daily snapshots.'
              : 'Broker-reported daily P&L uses IBKR Change in NAV MTM.';

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

          function refreshErrorDetail(payload, fallback) {
            if (payload.detail?.message) {
              const stage = payload.detail.stage
                ? `${payload.detail.stage}: `
                : '';
              let detail = `${stage}${payload.detail.message}`;
              if (payload.detail.retry_after_seconds) {
                const minutes = Math.ceil(payload.detail.retry_after_seconds / 60);
                detail = `${detail} (${minutes} min)`;
              }
              return detail;
            }
            return payload.detail || fallback;
          }

          async function postRefresh(path) {
            const response = await fetch(path, {
              method: 'POST',
              headers: {
                'Content-Type': 'application/json',
                'X-PA-Request': 'refresh',
              },
              body: JSON.stringify({}),
            });
            if (!response.ok) {
              let detail = `Request failed (${response.status})`;
              try {
                detail = refreshErrorDetail(await response.json(), detail);
              } catch (_) {
                // Keep the HTTP status message when the response is not JSON.
              }
              throw new Error(detail);
            }
            return response.json();
          }

          async function refreshPositions() {
            const button = document.getElementById('refresh-positions');
            const status = document.getElementById('refresh-status');
            button.disabled = true;
            button.setAttribute('aria-busy', 'true');
            status.textContent = 'Refreshing IBKR positions...';
            try {
              try {
                const refreshPayload = await postRefresh('/analysis/refresh/positions');
                const positions = refreshPayload.position_import.positions_imported;
                status.textContent = [
                  `Positions refreshed: ${positions} positions`,
                  `${refreshPayload.position_import.transactions_imported} trades`,
                  'Dashboard refreshed.',
                ].join(', ');
              } catch (error) {
                status.textContent = `Positions refresh failed: ${error.message}`;
                return;
              }

              const reloadResults = await Promise.allSettled([
                loadCurrentPortfolio(),
                loadPerformance(),
                loadDailyPnl(),
              ]);
              if (reloadResults.some((result) => result.status === 'rejected')) {
                status.textContent = 'Positions refreshed, but some panels failed to reload.';
              }
            } finally {
              button.disabled = false;
              button.removeAttribute('aria-busy');
            }
          }

          async function refreshHistory() {
            const button = document.getElementById('refresh-history');
            const status = document.getElementById('refresh-status');
            button.disabled = true;
            button.setAttribute('aria-busy', 'true');
            status.textContent = 'Refreshing IBKR history...';
            try {
              let refreshPayload;
              try {
                refreshPayload = await postRefresh('/analysis/refresh/history');
                const navPoints = refreshPayload.history_import.nav_points_imported;
                status.textContent = [
                  `History refreshed: ${navPoints} NAV points`,
                  `${refreshPayload.history_import.pnl_points_imported} P&L points.`,
                ].join(', ');
              } catch (error) {
                status.textContent = `History refresh failed: ${error.message}`;
                return;
              }

              const reloadResults = await Promise.allSettled([
                loadPerformance(),
                loadDailyPnl(),
                loadBrokerDailyPnl(),
              ]);
              if (reloadResults.some((result) => result.status === 'rejected')) {
                status.textContent = 'History refreshed, but some panels failed to reload.';
              }
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

          async function loadBrokerDailyPnl() {
            const response = await fetch('/analysis/broker-daily-pnl?limit=12');
            if (!response.ok) {
              throw new Error(`Broker P&L request failed (${response.status})`);
            }
            const payload = await response.json();
            const body = document.getElementById('broker-pnl-body');
            const note = document.getElementById('broker-pnl-note');
            if (!payload.points.length) {
              note.textContent = 'No broker-reported daily P&L has been imported yet.';
              body.innerHTML = `
                <tr>
                  <td class="empty-state" colspan="7">
                    No broker daily P&L available.
                  </td>
                </tr>
              `;
              return;
            }
            note.textContent = `Latest report date: ${payload.latest_report_date}`;
            body.innerHTML = payload.points.map((point) => {
              const total = Number(point.total);
              const tone = Number.isNaN(total) || total === 0
                ? ''
                : total > 0 ? ' class="pnl-text-positive"' : ' class="pnl-text-negative"';
              return `
                <tr>
                  <td>${escapeHtml(point.symbol)}</td>
                  <td>${escapeHtml(point.asset_class)}</td>
                  <td>${formatValue(point.close_quantity, 'currency')}</td>
                  <td>${formatCurrency(point.prior_open_mtm, null)}</td>
                  <td>${formatCurrency(point.transaction_mtm, null)}</td>
                  <td>${formatCurrency(point.commissions, null)}</td>
                  <td${tone}>${formatCurrency(point.total, null)}</td>
                </tr>
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
          loadBrokerDailyPnl().catch(() => {
            document.getElementById('broker-pnl-note').textContent =
              'Broker-reported daily P&L unavailable.';
            document.getElementById('broker-pnl-body').innerHTML = `
              <tr>
                <td class="empty-state" colspan="7">
                  Broker daily P&L unavailable.
                </td>
              </tr>
            `;
          });
          document.getElementById('refresh-positions')
            .addEventListener('click', refreshPositions);
          document.getElementById('refresh-history')
            .addEventListener('click', refreshHistory);
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


def position_chart_page() -> str:
    return """
    <html>
      <head>
        <title>Position Chart</title>
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
        <style>
          :root {
            color-scheme: light;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
          }
          * { box-sizing: border-box; }
          body {
            margin: 0;
            background: #f5f7fb;
            color: #111827;
          }
          main {
            max-width: 1180px;
            margin: 0 auto;
            padding: 16px 12px 48px;
          }
          h1, h2, p { margin: 0; }
          .top-nav {
            display: flex;
            gap: 18px;
            margin-bottom: 24px;
            border-bottom: 1px solid #dbe4f0;
          }
          .tab {
            color: #64748b;
            border-bottom: 3px solid transparent;
            padding: 10px 4px 9px;
            font-weight: 650;
            text-decoration: none;
          }
          .tab[aria-current="page"] {
            color: #1d4ed8;
            border-bottom-color: #2563eb;
          }
          .intro {
            display: grid;
            gap: 7px;
            margin-bottom: 16px;
          }
          .subtitle { color: #64748b; font-size: 14px; }
          .panel {
            background: #ffffff;
            border: 1px solid #dbe4f0;
            border-radius: 10px;
            padding: 14px;
          }
          .controls {
            display: grid;
            gap: 14px;
            margin-bottom: 14px;
          }
          .control-row {
            display: flex;
            flex-wrap: wrap;
            align-items: end;
            gap: 12px;
          }
          label {
            display: grid;
            gap: 6px;
            color: #475569;
            font-size: 12px;
            font-weight: 650;
          }
          select {
            min-height: 40px;
            max-width: 100%;
            border: 1px solid #cbd5e1;
            border-radius: 7px;
            background: #ffffff;
            color: #111827;
            font: inherit;
            padding: 8px 34px 8px 10px;
          }
          #position-select { min-width: min(100%, 320px); }
          .button-group {
            display: flex;
            flex-wrap: wrap;
            gap: 6px;
          }
          .choice {
            min-height: 36px;
            border: 1px solid #cbd5e1;
            border-radius: 7px;
            background: #ffffff;
            color: #334155;
            cursor: pointer;
            font: inherit;
            font-size: 13px;
            font-weight: 650;
            padding: 7px 11px;
          }
          .choice.active {
            border-color: #2563eb;
            background: #eff6ff;
            color: #1d4ed8;
          }
          .choice:disabled {
            cursor: not-allowed;
            opacity: .42;
          }
          .indicator-menu {
            display: flex;
            flex-wrap: wrap;
            gap: 12px;
            min-height: 40px;
            align-items: center;
          }
          .indicator-menu label {
            display: flex;
            flex-direction: row;
            align-items: center;
            gap: 6px;
            color: #334155;
            font-weight: 550;
          }
          .kpis {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 8px;
            margin-bottom: 14px;
          }
          .kpi {
            min-width: 0;
            background: #ffffff;
            border: 1px solid #dbe4f0;
            border-radius: 9px;
            padding: 12px;
          }
          .kpi-label { color: #64748b; font-size: 12px; margin-bottom: 5px; }
          .kpi-value {
            font-size: clamp(17px, 4.5vw, 24px);
            font-weight: 680;
            font-variant-numeric: tabular-nums;
            overflow-wrap: anywhere;
          }
          .status-line {
            display: flex;
            flex-wrap: wrap;
            align-items: center;
            gap: 8px;
          }
          .badge {
            border-radius: 999px;
            background: #e0e7ff;
            color: #3730a3;
            font-size: 12px;
            font-weight: 650;
            padding: 5px 9px;
          }
          .reconciliation {
            border-radius: 8px;
            background: #ecfdf5;
            border: 1px solid #86efac;
            color: #166534;
            font-size: 13px;
            padding: 10px 12px;
          }
          .reconciliation.warning {
            background: #fffbeb;
            border-color: #fcd34d;
            color: #92400e;
          }
          .warnings {
            display: grid;
            gap: 6px;
            margin: 10px 0 0;
            padding: 0;
            list-style: none;
          }
          .warnings li {
            border-left: 3px solid #f59e0b;
            background: #fffbeb;
            color: #92400e;
            font-size: 12px;
            padding: 7px 9px;
          }
          .chart-shell {
            margin-top: 14px;
            min-height: 510px;
          }
          #position-chart { width: 100%; min-height: 500px; }
          .empty {
            min-height: 420px;
            display: grid;
            place-items: center;
            color: #64748b;
            text-align: center;
            padding: 30px;
          }
          .loading { opacity: .65; }
          @media (min-width: 760px) {
            main { padding: 24px 16px 48px; }
            .controls { grid-template-columns: minmax(260px, 1.4fr) 1fr 1fr 1fr; }
            .kpis { grid-template-columns: repeat(4, minmax(0, 1fr)); }
          }
        </style>
      </head>
      <body>
        <main>
          <nav class="top-nav" aria-label="Portfolio sections">
            <a class="tab" href="/analysis/portfolio">Portfolio</a>
            <a class="tab" href="/analysis/position-chart"
               aria-current="page">Position Chart</a>
          </nav>
          <section class="intro">
            <h1>Position Chart</h1>
            <p class="subtitle">
              Third-party candles reconciled against authoritative IBKR executions
            </p>
          </section>
          <section class="panel controls" aria-label="Chart controls">
            <label>
              Position
              <select id="position-select" aria-label="Position">
                <option value="">Loading positions...</option>
              </select>
            </label>
            <div>
              <label>Candle interval</label>
              <div class="button-group" id="interval-buttons">
                <button class="choice" data-value="5m" type="button">5m</button>
                <button class="choice active" data-value="1d" type="button">1D</button>
                <button class="choice" data-value="1wk" type="button">1W</button>
                <button class="choice" data-value="1mo" type="button">1M</button>
              </div>
            </div>
            <div>
              <label>Visible range</label>
              <div class="button-group" id="range-buttons">
                <button class="choice" data-value="1d" type="button">1D</button>
                <button class="choice" data-value="1m" type="button">1M</button>
                <button class="choice active" data-value="3m" type="button">3M</button>
                <button class="choice" data-value="ytd" type="button">YTD</button>
                <button class="choice" data-value="1y" type="button">1Y</button>
              </div>
            </div>
            <div>
              <label>Indicators</label>
              <div class="indicator-menu">
                <label><input id="indicator-sma" type="checkbox" /> SMA 20</label>
                <label><input id="indicator-volume" type="checkbox" /> Volume</label>
              </div>
            </div>
          </section>
          <section class="kpis" aria-label="Selected position summary">
            <article class="kpi">
              <div class="kpi-label">Quantity</div>
              <div class="kpi-value" id="quantity">--</div>
            </article>
            <article class="kpi">
              <div class="kpi-label">IBKR average cost</div>
              <div class="kpi-value" id="average-cost">--</div>
            </article>
            <article class="kpi">
              <div class="kpi-label">Latest chart price</div>
              <div class="kpi-value" id="latest-price">--</div>
            </article>
            <article class="kpi">
              <div class="kpi-label">Indicative unrealized P&amp;L</div>
              <div class="kpi-value" id="indicative-pnl">--</div>
            </article>
          </section>
          <section class="panel">
            <div class="status-line">
              <span class="badge" id="source-badge">Waiting for data</span>
              <span class="subtitle" id="instrument-label"></span>
            </div>
            <div class="reconciliation" id="reconciliation" aria-live="polite">
              Select a position to reconcile its executions.
            </div>
            <ul class="warnings" id="warnings"></ul>
            <div class="chart-shell" id="chart-shell">
              <div class="empty">Loading chart...</div>
            </div>
          </section>
        </main>
        <script>
          const state = {
            interval: '1d',
            range: '3m',
            payload: null,
          };

          const numberFormat = new Intl.NumberFormat(undefined, {
            maximumFractionDigits: 4,
          });

          function numeric(value) {
            if (value === null || value === undefined || value === '') return null;
            const parsed = Number(value);
            return Number.isFinite(parsed) ? parsed : null;
          }

          function formatNumber(value) {
            const parsed = numeric(value);
            return parsed === null ? '--' : numberFormat.format(parsed);
          }

          function formatMoney(value, currency) {
            const parsed = numeric(value);
            if (parsed === null) return '--';
            try {
              return new Intl.NumberFormat(undefined, {
                style: 'currency',
                currency,
                maximumFractionDigits: 2,
              }).format(parsed);
            } catch (_) {
              return `${numberFormat.format(parsed)} ${currency || ''}`.trim();
            }
          }

          function selectedPosition() {
            const option = document.getElementById('position-select').selectedOptions[0];
            if (!option || !option.value) return null;
            return {
              instrumentId: option.value,
              accountId: option.dataset.accountId,
              status: option.dataset.status,
            };
          }

          function updateCompatibility() {
            const rangeButtons = [...document.querySelectorAll('#range-buttons .choice')];
            for (const button of rangeButtons) {
              const incompatible = state.interval === '5m'
                && !['1d', '1m'].includes(button.dataset.value);
              button.disabled = incompatible;
            }
            if (state.interval === '5m' && !['1d', '1m'].includes(state.range)) {
              state.range = '1m';
            }
            syncButtons();
          }

          function syncButtons() {
            for (const button of document.querySelectorAll('#interval-buttons .choice')) {
              button.classList.toggle('active', button.dataset.value === state.interval);
            }
            for (const button of document.querySelectorAll('#range-buttons .choice')) {
              button.classList.toggle('active', button.dataset.value === state.range);
            }
          }

          async function loadPositions() {
            const response = await fetch('/analysis/position-chart/positions');
            if (!response.ok) throw new Error(`Position request failed (${response.status})`);
            const positions = await response.json();
            const select = document.getElementById('position-select');
            select.innerHTML = '';
            if (!positions.length) {
              const option = document.createElement('option');
              option.textContent = 'No position history';
              option.value = '';
              select.append(option);
              document.getElementById('chart-shell').innerHTML =
                '<div class="empty">Import IBKR positions and executions ' +
                'to populate this chart.</div>';
              return;
            }
            const openGroup = document.createElement('optgroup');
            openGroup.label = 'Open positions';
            const closedGroup = document.createElement('optgroup');
            closedGroup.label = 'Closed positions';
            for (const position of positions) {
              const option = document.createElement('option');
              option.value = position.instrument_id;
              option.dataset.accountId = position.account_id;
              option.dataset.status = position.status;
              option.textContent = position.status === 'open'
                ? `${position.symbol} · ${position.quantity} · ${position.currency}`
                : `${position.symbol} · closed · ${position.currency}`;
              (position.status === 'open' ? openGroup : closedGroup).append(option);
            }
            if (openGroup.children.length) select.append(openGroup);
            if (closedGroup.children.length) select.append(closedGroup);
            if (!openGroup.children.length && closedGroup.children.length) {
              state.interval = '1d';
              state.range = 'ytd';
              updateCompatibility();
            }
            await loadChart();
          }

          async function loadChart() {
            const selected = selectedPosition();
            if (!selected) return;
            const shell = document.getElementById('chart-shell');
            shell.classList.add('loading');
            const params = new URLSearchParams({
              account_id: selected.accountId,
              interval: state.interval,
              range: state.range,
            });
            try {
              const response = await fetch(
                `/analysis/position-chart/data/${encodeURIComponent(selected.instrumentId)}?${params}`
              );
              if (!response.ok) {
                const error = await response.json().catch(() => ({}));
                throw new Error(error.detail || `Chart request failed (${response.status})`);
              }
              state.payload = await response.json();
              render(state.payload);
            } catch (error) {
              console.error(error);
              shell.innerHTML = '';
              const empty = document.createElement('div');
              empty.className = 'empty';
              empty.textContent = error.message || 'Position chart unavailable.';
              shell.append(empty);
            } finally {
              shell.classList.remove('loading');
            }
          }

          function render(payload) {
            document.getElementById('quantity').textContent = formatNumber(payload.quantity);
            document.getElementById('average-cost').textContent =
              formatMoney(payload.average_cost, payload.currency);
            document.getElementById('latest-price').textContent =
              formatMoney(payload.latest_price, payload.currency);
            document.getElementById('indicative-pnl').textContent =
              formatMoney(payload.indicative_unrealized_pnl, payload.currency);
            document.getElementById('instrument-label').textContent =
              `${payload.symbol} · ${payload.name} · ` +
              `${payload.exchange || 'exchange unknown'} · ` +
              `${payload.position_status === 'closed' ? 'Closed position' : 'Open position'}`;
            const intervalLabel = payload.actual_interval || 'execution only';
            document.getElementById('source-badge').textContent =
              `${intervalLabel} · ${payload.provider || 'IBKR only'}` +
              `${payload.fallback ? ' · fallback' : ''}`;
            renderReconciliation(payload);
            renderWarnings(payload.warnings);
            renderPlot(payload);
          }

          function renderReconciliation(payload) {
            const counts = payload.reconciliation;
            const element = document.getElementById('reconciliation');
            const hasWarning = counts.warning > 0 || counts.unavailable > 0
              || payload.warnings.length > 0;
            element.classList.toggle('warning', hasWarning);
            element.textContent =
              `Reconciliation: ${counts.matched} matched · ${counts.near} near · ` +
              `${counts.warning} warning · ${counts.unavailable} unavailable · ` +
              `multiplier ${payload.price_multiplier} · ` +
              `${payload.provider_currency || 'currency unknown'} / ${payload.currency}`;
          }

          function renderWarnings(warnings) {
            const list = document.getElementById('warnings');
            list.innerHTML = '';
            for (const warning of warnings) {
              const item = document.createElement('li');
              item.textContent = warning;
              list.append(item);
            }
          }

          function executionTrace(executions, side, color, outlineColor, symbol) {
            const selected = executions.filter(item => item.side === side);
            const action = side === 'buy' ? 'BUY' : 'SELL';
            return {
              type: 'scatter',
              mode: 'markers+text',
              name: `${action} execution · IBKR`,
              x: selected.map(item => item.occurred_at),
              y: selected.map(item => numeric(item.price)),
              text: selected.map(() => action),
              textposition: side === 'buy' ? 'bottom center' : 'top center',
              textfont: {
                color: outlineColor,
                size: 10,
                family: '-apple-system, BlinkMacSystemFont, Segoe UI, sans-serif',
              },
              customdata: selected.map(item => [
                item.quantity,
                item.fees,
                item.status,
                item.difference_percent,
                item.reason,
                item.occurred_at,
              ]),
              marker: {
                color,
                size: selected.map(item =>
                  ['warning', 'unavailable'].includes(item.status) ? 19 : 16
                ),
                symbol,
                line: {
                  color: selected.map(item =>
                    ['warning', 'unavailable'].includes(item.status)
                      ? '#facc15'
                      : outlineColor
                  ),
                  width: selected.map(item =>
                    ['warning', 'unavailable'].includes(item.status) ? 4 : 2
                  ),
                },
              },
              cliponaxis: false,
              hoverlabel: {
                bgcolor: color,
                bordercolor: outlineColor,
                font: {color: '#ffffff'},
                namelength: -1,
              },
              hovertemplate:
                `<b>${action} · IBKR execution</b><br>` +
                'Time: %{customdata[5]}<br>' +
                `Execution price: %{y:.4f} ${state.payload.currency}<br>` +
                'Quantity: %{customdata[0]}<br>' +
                `Fees: %{customdata[1]} ${state.payload.currency}<br>` +
                'Reconciliation: %{customdata[2]}<br>' +
                'Difference: %{customdata[3]}<br>' +
                'Reason: %{customdata[4]}<extra></extra>',
            };
          }

          function renderPlot(payload) {
            const shell = document.getElementById('chart-shell');
            shell.innerHTML = '<div id="position-chart"></div>';
            const candles = payload.candles;
            const x = candles.map(item => item.observed_at);
            const traces = [];
            if (candles.length) {
              traces.push({
                type: 'candlestick',
                name: payload.symbol,
                x,
                open: candles.map(item => numeric(item.open)),
                high: candles.map(item => numeric(item.high)),
                low: candles.map(item => numeric(item.low)),
                close: candles.map(item => numeric(item.close)),
                increasing: {line: {color: '#16a34a'}},
                decreasing: {line: {color: '#dc2626'}},
                hoverlabel: {namelength: -1},
              });
            }
            if (document.getElementById('indicator-sma').checked && candles.length) {
              traces.push({
                type: 'scatter',
                mode: 'lines',
                name: 'SMA 20',
                x,
                y: payload.indicators.sma20.map(numeric),
                line: {color: '#7c3aed', width: 1.8},
                connectgaps: false,
              });
            }
            traces.push(
              executionTrace(
                payload.executions,
                'buy',
                '#2563eb',
                '#1e3a8a',
                'triangle-up',
              ),
              executionTrace(
                payload.executions,
                'sell',
                '#f97316',
                '#9a3412',
                'triangle-down',
              ),
            );
            const showVolume = document.getElementById('indicator-volume').checked
              && candles.some(item => item.volume !== null);
            if (showVolume) {
              traces.push({
                type: 'bar',
                name: 'Volume',
                x,
                y: candles.map(item => numeric(item.volume)),
                marker: {color: '#94a3b8'},
                opacity: .55,
                yaxis: 'y2',
                hovertemplate: 'Volume %{y}<extra></extra>',
              });
            }
            const shapes = [];
            if (numeric(payload.average_cost) !== null) {
              shapes.push({
                type: 'line',
                xref: 'paper',
                x0: 0,
                x1: 1,
                y0: numeric(payload.average_cost),
                y1: numeric(payload.average_cost),
                line: {color: '#2563eb', width: 1.5, dash: 'dot'},
              });
            }
            const annotations = numeric(payload.average_cost) === null ? [] : [{
              xref: 'paper',
              x: 1,
              y: numeric(payload.average_cost),
              text: `IBKR avg ${formatMoney(payload.average_cost, payload.currency)}`,
              showarrow: false,
              xanchor: 'right',
              yanchor: 'bottom',
              font: {color: '#1d4ed8', size: 11},
              bgcolor: 'rgba(255,255,255,.8)',
            }];
            const layout = {
              autosize: true,
              height: 500,
              margin: {l: 54, r: 24, t: 24, b: 48},
              paper_bgcolor: '#ffffff',
              plot_bgcolor: '#ffffff',
              font: {family: '-apple-system, BlinkMacSystemFont, Segoe UI, sans-serif'},
              hovermode: 'closest',
              hoverdistance: 50,
              dragmode: 'pan',
              showlegend: true,
              legend: {orientation: 'h', x: 0, y: 1.08},
              xaxis: {
                rangeslider: {visible: false},
                showgrid: true,
                gridcolor: '#eef2f7',
                type: 'date',
              },
              yaxis: {
                title: payload.currency,
                domain: showVolume ? [.24, 1] : [0, 1],
                showgrid: true,
                gridcolor: '#eef2f7',
                fixedrange: false,
              },
              shapes,
              annotations,
            };
            if (showVolume) {
              layout.yaxis2 = {
                domain: [0, .18],
                showgrid: false,
                title: 'Volume',
                fixedrange: false,
              };
            }
            Plotly.newPlot('position-chart', traces, layout, {
              responsive: true,
              displaylogo: false,
              scrollZoom: true,
              modeBarButtonsToRemove: ['select2d', 'lasso2d'],
            });
          }

          document.getElementById('position-select').addEventListener('change', () => {
            const selected = selectedPosition();
            if (selected?.status === 'closed') {
              state.interval = '1d';
              state.range = 'ytd';
              updateCompatibility();
            }
            loadChart();
          });
          for (const button of document.querySelectorAll('#interval-buttons .choice')) {
            button.addEventListener('click', () => {
              state.interval = button.dataset.value;
              updateCompatibility();
              loadChart();
            });
          }
          for (const button of document.querySelectorAll('#range-buttons .choice')) {
            button.addEventListener('click', () => {
              state.range = button.dataset.value;
              syncButtons();
              loadChart();
            });
          }
          document.getElementById('indicator-sma').addEventListener('change', () => {
            if (state.payload) renderPlot(state.payload);
          });
          document.getElementById('indicator-volume').addEventListener('change', () => {
            if (state.payload) renderPlot(state.payload);
          });

          loadPositions().catch(error => {
            const shell = document.getElementById('chart-shell');
            shell.innerHTML = '';
            const empty = document.createElement('div');
            empty.className = 'empty';
            empty.textContent = String(error.message || error);
            shell.append(empty);
          });
        </script>
      </body>
    </html>
    """


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
