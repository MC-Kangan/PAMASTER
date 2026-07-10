from html import escape


def portfolio_page() -> str:
    return """
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
          }
          .chart-panel {
            display: grid;
            gap: 12px;
          }
          .chart-shell {
            min-height: 220px;
            border-radius: 6px;
            border: 1px dashed #c7d2e3;
            background: linear-gradient(180deg, #f8fbff 0%, #eef4fb 100%);
            padding: 12px;
          }
          .chart-shell code {
            display: block;
            white-space: pre-wrap;
            word-break: break-word;
            font-size: 12px;
            color: #334155;
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
            <article class="summary-card">
              <div class="summary-label">Ending NAV</div>
              <div class="summary-value" id="ending-nav">--</div>
            </article>
            <article class="summary-card">
              <div class="summary-label">Window Return</div>
              <div class="summary-value" id="window-return">--</div>
            </article>
            <article class="summary-card">
              <div class="summary-label">Max Drawdown</div>
              <div class="summary-value" id="max-drawdown">--</div>
            </article>
          </section>
          <section class="chart-panel" id="performance-history">
            <h2>Performance History</h2>
            <div class="chart-shell">
              <code id="performance-data">Loading /analysis/performance ...</code>
            </div>
          </section>
        </main>
        <script>
          async function loadPerformance() {
            const response = await fetch('/analysis/performance');
            const payload = await response.json();
            document.getElementById('ending-nav').textContent = payload.ending_nav ?? '--';
            document.getElementById('window-return').textContent = payload.simple_return ?? '--';
            document.getElementById('max-drawdown').textContent = payload.max_drawdown ?? '--';
            document.getElementById('performance-data').textContent =
              JSON.stringify(payload.points, null, 2);
          }
          loadPerformance().catch(() => {
            document.getElementById('performance-data').textContent =
              'Performance history unavailable.';
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
