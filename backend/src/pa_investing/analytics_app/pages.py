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
          loadPerformance().catch(() => {
            document.getElementById('performance-body').innerHTML = `
              <tr>
                <td class="empty-state" colspan="__COLUMN_COUNT__">
                  Performance history unavailable.
                </td>
              </tr>
            `;
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
