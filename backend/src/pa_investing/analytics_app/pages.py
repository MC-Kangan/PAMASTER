def portfolio_page() -> str:
    return """
    <html>
      <head><title>Portfolio Analysis</title></head>
      <body>
        <h1>Portfolio Analysis</h1>
        <p>Phase 1 analytics cockpit link target.</p>
      </body>
    </html>
    """


def signal_page(signal_id: str) -> str:
    return f"""
    <html>
      <head><title>Signal Analysis</title></head>
      <body>
        <h1>Signal Analysis</h1>
        <p>Signal ID: {signal_id}</p>
      </body>
    </html>
    """
