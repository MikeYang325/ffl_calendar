from pathlib import Path

# 1) Template: add dynamic return title id in both template/public copies.
for path in ('templates/index.html', 'public/index.html'):
    p = Path(path)
    text = p.read_text(encoding='utf-8')
    old = '<h2>返程结果</h2>\n                <p id="returnSubtitle"></p>'
    new = '<h2 id="returnTitle">返程</h2>\n                <p id="returnSubtitle"></p>'
    if old not in text:
        raise SystemExit(f'return heading pattern missing in {path}')
    p.write_text(text.replace(old, new, 1), encoding='utf-8')

# 2) JS: make outbound/return direction explicit and clarify result semantics.
for path in ('static/app.js', 'public/static/app.js'):
    p = Path(path)
    text = p.read_text(encoding='utf-8')
    old = """    $('resultTitle').textContent = `${META.airports.find(x=>x.code===origin)?.name || origin} → ${META.airports.find(x=>x.code===destination)?.name || destination}`;\n    $('resultSubtitle').textContent = `${date} · 共 ${data.count} 个方案`;\n"""
    new = """    const originName = META.airports.find(x=>x.code===origin)?.name || origin;\n    const destinationName = META.airports.find(x=>x.code===destination)?.name || destination;\n    $('resultTitle').textContent = tripMode === 'roundtrip'\n      ? `去程 · ${originName} → ${destinationName}`\n      : `${originName} → ${destinationName}`;\n    $('resultSubtitle').textContent = `${date} · 共 ${data.count} 个方案`;\n"""
    if old not in text:
        raise SystemExit(f'outbound title pattern missing in {path}')
    text = text.replace(old, new, 1)

    old = """      $('returnResultsWrap').classList.remove('hidden');\n      $('returnSubtitle').textContent = `${returnDate} · 共 ${rd.count} 个方案`;\n      $('returnResults').innerHTML = rd.count ? rd.results.map(flightCard).join('') : '<div class=\"empty-state\">没有找到符合条件的返程航班</div>';\n"""
    new = """      $('returnResultsWrap').classList.remove('hidden');\n      $('returnTitle').textContent = `返程 · ${destinationName} → ${originName}`;\n      $('returnSubtitle').textContent = `${returnDate} · 共 ${rd.count} 个方案`;\n      $('returnResults').innerHTML = rd.count ? rd.results.map(flightCard).join('') : '<div class=\"empty-state\">没有找到符合条件的返程航班</div>';\n"""
    if old not in text:
        raise SystemExit(f'return title pattern missing in {path}')
    p.write_text(text.replace(old, new, 1), encoding='utf-8')

# 3) CSS: keep density but restore visual hierarchy and softer HNA palette.
css = r'''

/* mobile visual hierarchy & round-trip clarity v4 */
@media (max-width: 520px) {
  body {
    color:#493a3e;
    background:linear-gradient(180deg,#f7f2ee 0,#faf7f4 54%,#f4efeb 100%);
  }

  #searchPanel .search-card {
    background:#fffdfb;
    border-color:#eadfda;
    box-shadow:0 7px 20px rgba(92,44,51,.07);
    padding:11px 12px 12px;
  }
  #searchPanel .field > span {
    color:#7f6e73;
    font-weight:650;
  }
  #searchPanel .field input,
  #searchPanel .field select,
  #searchPanel .airport-input {
    height:38px;
    color:#493a3e;
    background:#fff;
    border-color:#eaded8;
    font-size:12.5px;
  }
  #searchPanel .route-row .swap-btn {
    top:27px;
    background:#fffaf6;
    border-color:#e5cfc7;
    color:#a20b2a;
  }
  #searchPanel .advanced {
    border-color:#ead9d5;
  }
  #searchPanel .advanced summary {
    color:#a20b2a;
    font-weight:750;
  }
  #searchPanel .primary-btn {
    background:linear-gradient(90deg,#a20b2a,#c52042);
    box-shadow:0 7px 15px rgba(162,11,42,.17);
  }

  #searchPanel .stats-grid {
    margin:8px 0 9px;
  }
  #searchPanel .stat {
    min-height:50px;
    background:#fffdfb;
    border-color:#eadfda;
    box-shadow:0 3px 10px rgba(90,48,52,.035);
  }
  #searchPanel .stat span {
    color:#9a8a8e;
    font-size:8.5px;
  }
  #searchPanel .stat strong {
    color:#a20b2a;
    font-size:16px;
    font-weight:800;
  }

  #searchPanel .section-heading {
    padding:1px 4px 6px;
  }
  #searchPanel .section-heading h2 {
    color:#4a383d;
    font-size:18px;
    font-weight:800;
    letter-spacing:-.015em;
  }
  #searchPanel .section-heading p {
    color:#97878b;
    font-size:10px;
  }
  #searchPanel .return-heading {
    margin-top:14px;
    padding-top:2px;
  }

  #searchPanel .results-list {
    gap:9px;
  }
  #searchPanel .flight-card {
    padding:12px 13px 11px;
    border-color:#eadfda;
    background:#fffdfb;
    box-shadow:0 5px 16px rgba(76,39,45,.045);
  }
  #searchPanel .flight-card-head {
    gap:8px;
    padding-bottom:8px;
    border-bottom-color:#f0e8e4;
  }
  #searchPanel .flight-card-head > div:first-child > strong {
    color:#49373c;
    font-size:14px;
    font-weight:780;
  }
  #searchPanel .flight-summary {
    color:#9a8b8e;
    font-size:9px;
  }
  #searchPanel .tag {
    background:#f2f4f6;
    color:#6f7b86;
    padding:3px 6px;
    font-size:9px;
    font-weight:700;
  }
  #searchPanel .tag.product {
    background:#f8ecdf;
    color:#956118;
  }
  #searchPanel .tag.stop {
    background:#f8efea;
    color:#a05d44;
  }

  #searchPanel .segment {
    grid-template-columns:74px minmax(0,1fr) 74px;
    gap:7px;
    padding:11px 0 8px;
  }
  #searchPanel .time-block strong {
    color:#821127;
    font-size:20px;
    font-weight:780;
  }
  #searchPanel .time-block span {
    color:#8e8285;
    font-size:9px;
    line-height:1.28;
  }
  #searchPanel .timeline {
    color:#8290a0;
    font-size:9px;
  }
  #searchPanel .timeline::before,
  #searchPanel .timeline::after {
    background:#d9e0e7;
  }
  #searchPanel .timeline .plane {
    color:#b21735;
  }
  #searchPanel .segment-meta {
    color:#8190a0;
    font-size:9px;
    line-height:1.3;
    gap:4px 8px;
  }
  #searchPanel .connection {
    color:#91651f;
    background:#fbf3e7;
  }
}
'''
for path in ('static/style.css', 'public/static/style.css'):
    p = Path(path)
    text = p.read_text(encoding='utf-8')
    marker = '/* mobile visual hierarchy & round-trip clarity v4 */'
    if marker not in text:
        text = text.rstrip() + css + '\n'
    p.write_text(text, encoding='utf-8')

print('mobile visual/return clarity patch applied')
