from pathlib import Path

OLD = '''        <td>\n          <strong>${x.operating_days} 天</strong>\n          <div class="sub">${esc(x.first_date)} ~ ${esc(x.last_date)}</div>\n          <button type="button" class="date-toggle-btn" data-target="${dateId}" aria-expanded="false" title="展开具体日期">▶</button>\n        </td>'''
NEW = '''        <td>\n          <div class="route-days-line"><strong>${x.operating_days} 天</strong><button type="button" class="date-toggle-btn" data-target="${dateId}" aria-expanded="false" title="展开具体日期">▶</button></div>\n          <div class="sub">${esc(x.first_date)} ~ ${esc(x.last_date)}</div>\n        </td>'''

for path in ('static/app.js', 'public/static/app.js'):
    p = Path(path)
    text = p.read_text(encoding='utf-8')
    if OLD not in text:
        raise SystemExit(f'pattern not found in {path}')
    p.write_text(text.replace(OLD, NEW, 1), encoding='utf-8')

css = '''\n/* inline route date triangle */\n.route-days-line {\n  display:flex;\n  align-items:center;\n  justify-content:center;\n  gap:4px;\n  line-height:1.2;\n}\n.route-days-line .date-toggle-btn {\n  width:18px;\n  height:18px;\n  margin:0;\n  padding:0;\n  display:inline-flex;\n  align-items:center;\n  justify-content:center;\n  border:0;\n  background:transparent;\n  color:var(--primary);\n  font-size:10px;\n  line-height:1;\n  vertical-align:middle;\n}\n.route-days-line .date-toggle-btn:hover {\n  background:var(--soft);\n  border-radius:4px;\n}\n'''
for path in ('static/style.css', 'public/static/style.css'):
    p = Path(path)
    text = p.read_text(encoding='utf-8')
    marker = '/* inline route date triangle */'
    if marker not in text:
        text = text.rstrip() + '\n' + css
    p.write_text(text, encoding='utf-8')

print('inline triangle patch applied')
