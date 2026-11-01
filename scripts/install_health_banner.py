"""Install the NOAA health warning in the published dashboard."""
from pathlib import Path

path = Path("index.html")
html = path.read_text(encoding="utf-8")
marker = "cu-forecast-health-monitor"
if marker not in html:
    snippet = """
<script id="cu-forecast-health-monitor">
(() => {
  const id = 'cu-forecast-health-banner';
  function show(message, warning) {
    let banner = document.getElementById(id);
    if (!banner) {
      banner = document.createElement('div');
      banner.id = id;
      banner.setAttribute('role', 'status');
      banner.style.cssText = 'position:sticky;top:0;z-index:9999;padding:12px 16px;margin-bottom:12px;border-radius:8px;font:600 14px/1.5 system-ui,sans-serif;color:white';
      document.body.prepend(banner);
    }
    banner.style.background = warning ? '#71332c' : '#185547';
    banner.textContent = message;
  }
  async function refresh() {
    try {
      const response = await fetch('./forecast_health.json?t=' + Date.now(), {cache:'no-store'});
      if (!response.ok) throw Error('health report unavailable');
      const report = await response.json();
      const age = Math.max(0, Math.round((Date.now() - Date.parse(report.checked_at))/60000));
      if (!Number.isFinite(age)) throw Error('invalid report timestamp');
      const parts = Object.entries(report.models || {}).map(([name, m]) => {
        const updatedAge = Math.round((Date.now() - Date.parse(m.updated))/60000);
        const stale = m.state !== 'current' || !Number.isFinite(updatedAge) || updatedAge > 90;
        const cycle = m.cycle ? new Date(m.cycle).getUTCHours().toString().padStart(2,'0') + 'Z' : '?';
        return name.toUpperCase() + ' ' + cycle + ' ' + (m.hours ?? '?') + '/' + (m.expected_hours ?? '?') + ' h' + (stale ? ' STALE' : '');
      });
      const bad = age > 90 || report.overall !== 'current' || Object.values(report.models || {}).some(m => m.state !== 'current' || Date.now() - Date.parse(m.updated) > 5400000);
      show((bad ? '⚠ FORECAST FRESHNESS WARNING: ' : 'NOAA forecast status: ') + parts.join(' | ') + ' · health check ' + age + ' min ago', bad);
    } catch (error) {
      show('⚠ Forecast freshness cannot be verified: ' + error.message, true);
    }
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', refresh);
  else refresh();
  setInterval(refresh, 60000);
})();
</script>
"""
    if "</body>" not in html:
        raise SystemExit("index.html missing closing body tag")
    path.write_text(html.replace("</body>", snippet + "</body>", 1), encoding="utf-8")
    print("Installed NOAA freshness banner")
else:
    print("NOAA freshness banner already installed")
