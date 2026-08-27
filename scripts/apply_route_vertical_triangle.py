from pathlib import Path

APP_FILES = [Path('static/app.js'), Path('public/static/app.js')]
CSS_FILES = [Path('static/style.css'), Path('public/static/style.css')]

for p in APP_FILES:
    text = p.read_text(encoding='utf-8')
    old = '<button type="button" class="date-detail-btn" data-target="${dateId}">查看具体日期</button>'
    new = '<button type="button" class="date-toggle-btn" data-target="${dateId}" aria-expanded="false" title="展开具体日期">▶</button>'
    if old not in text:
        raise SystemExit(f'date detail button pattern not found: {p}')
    text = text.replace(old, new, 1)

    old = """  $('routesTableBody').querySelectorAll('.date-detail-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const row = $(btn.dataset.target);
      if (!row) return;
      const opening = row.classList.contains('hidden');
      row.classList.toggle('hidden');
      btn.textContent = opening ? '收起日期' : '查看具体日期';
    });
  });
"""
    new = """  $('routesTableBody').querySelectorAll('.date-toggle-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const row = $(btn.dataset.target);
      if (!row) return;
      const opening = row.classList.contains('hidden');
      row.classList.toggle('hidden');
      btn.textContent = opening ? '▼' : '▶';
      btn.setAttribute('aria-expanded', opening ? 'true' : 'false');
      btn.title = opening ? '收起具体日期' : '展开具体日期';
    });
  });
"""
    if old not in text:
        raise SystemExit(f'date detail event pattern not found: {p}')
    text = text.replace(old, new, 1)
    p.write_text(text, encoding='utf-8')

css = r'''

/* route rows: vertically centered + compact date disclosure */
.routes-table .route-main-row > td {
  vertical-align: middle;
}
.routes-table .route-main-row .dest,
.routes-table .route-main-row .dest-title-line {
  align-items: center;
}
.date-toggle-btn {
  display: block;
  width: 22px;
  height: 18px;
  margin: 4px auto 0;
  padding: 0;
  border: 0;
  border-radius: 4px;
  background: transparent;
  color: var(--primary);
  font-size: 11px;
  font-weight: 800;
  line-height: 18px;
  text-align: center;
  cursor: pointer;
}
.date-toggle-btn:hover,
.date-toggle-btn:focus-visible {
  background: rgba(162, 11, 42, .08);
  outline: none;
}
'''

marker = '/* route rows: vertically centered + compact date disclosure */'
for p in CSS_FILES:
    text = p.read_text(encoding='utf-8')
    if marker not in text:
        text = text.rstrip() + css + '\n'
    p.write_text(text, encoding='utf-8')

print('route vertical alignment patch applied')
