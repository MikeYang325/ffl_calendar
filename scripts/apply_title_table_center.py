from pathlib import Path

# Remove the English eyebrow from both served/template copies.
for path in ('templates/index.html', 'public/index.html'):
    p = Path(path)
    text = p.read_text(encoding='utf-8')
    text = text.replace('          <div class="eyebrow">HNA FEIFEILE PLUS</div>\n', '')
    p.write_text(text, encoding='utf-8')

css = r'''

/* route overview table centered presentation */
.routes-table th,
.routes-table td {
  text-align: center;
}
.routes-table .dest .dest-title-line {
  justify-content: center;
}
.routes-table .dest .sub,
.routes-table .sub {
  text-align: center;
}
.routes-table td .date-detail-btn {
  display: block;
  margin-left: auto;
  margin-right: auto;
}
.routes-table td .tag {
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
'''

for path in ('static/style.css', 'public/static/style.css'):
    p = Path(path)
    text = p.read_text(encoding='utf-8')
    marker = '/* route overview table centered presentation */'
    if marker not in text:
        text = text.rstrip() + css + '\n'
    p.write_text(text, encoding='utf-8')

print('patch applied')
