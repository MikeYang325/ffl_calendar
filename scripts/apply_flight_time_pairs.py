from pathlib import Path


def replace_once(path, old, new):
    p = Path(path)
    text = p.read_text(encoding='utf-8')
    if old not in text:
        raise SystemExit(f'pattern not found: {path}: {old[:120]!r}')
    p.write_text(text.replace(old, new, 1), encoding='utf-8')

# 合并表头：航班号与时刻必须作为一组展示，彻底消除逐行猜对应关系。
old_head = '<th>到达城市</th><th>机场</th><th>航班号</th><th>时刻</th><th>班期</th><th>实际运行日期</th><th>产品</th>'
new_head = '<th>到达城市</th><th>机场</th><th>航班 / 时刻</th><th>班期</th><th>实际运行日期</th><th>产品</th>'
for path in ('templates/index.html', 'public/index.html'):
    replace_once(path, old_head, new_head)

# JS：直接使用后端 schedule_rows，每条记录内部同时携带 flight_no + departure/arrival time。
for path in ('static/app.js', 'public/static/app.js'):
    p = Path(path)
    text = p.read_text(encoding='utf-8')

    old = '''  $('routesTableBody').innerHTML = '<tr><td colspan="7">正在加载…</td></tr>';'''
    new = '''  $('routesTableBody').innerHTML = '<tr><td colspan="6">正在加载…</td></tr>';'''
    if old not in text:
        raise SystemExit(f'loading colspan pattern not found in {path}')
    text = text.replace(old, new, 1)

    old = '''  $('routesTableBody').innerHTML = data.routes.length ? data.routes.map((x, idx) => {
    const times = x.times.map(t =>
      `${t.departure_time} → ${t.arrival_time}${t.cross_day ? ' +' + t.cross_day : ''}`
    ).join('<br>');

    const dateId = `route-dates-${idx}`;'''
    new = '''  $('routesTableBody').innerHTML = data.routes.length ? data.routes.map((x, idx) => {
    const scheduleRows = (x.schedule_rows || []).length
      ? x.schedule_rows
      : (x.flight_nos || []).map((flightNo, rowIndex) => ({
          flight_no: flightNo,
          departure_time: x.times?.[rowIndex]?.departure_time || '',
          arrival_time: x.times?.[rowIndex]?.arrival_time || '',
          cross_day: x.times?.[rowIndex]?.cross_day || 0,
        }));
    const flightTimeHtml = `
      <div class="flight-time-pairs">
        ${scheduleRows.map(row => `
          <div class="flight-time-pair">
            <strong class="flight-pair-no">${esc(row.flight_no)}</strong>
            <span class="flight-pair-time">${esc(row.departure_time)} → ${esc(row.arrival_time)}${row.cross_day ? ' +' + row.cross_day : ''}</span>
          </div>`).join('')}
      </div>`;

    const dateId = `route-dates-${idx}`;'''
    if old not in text:
        raise SystemExit(f'route render preamble pattern not found in {path}')
    text = text.replace(old, new, 1)

    old = '''        <td>${x.flight_nos.map(esc).join('<br>')}</td>
        <td class="mono">${times}</td>
        <td><strong>${esc(x.schedule)}</strong></td>'''
    new = '''        <td class="flight-time-cell mono">${flightTimeHtml}</td>
        <td><strong>${esc(x.schedule)}</strong></td>'''
    if old not in text:
        raise SystemExit(f'flight/time cells pattern not found in {path}')
    text = text.replace(old, new, 1)

    text = text.replace('<td colspan="7">${routeCalendarHtml(x)}</td>', '<td colspan="6">${routeCalendarHtml(x)}</td>', 1)
    text = text.replace("'<tr><td colspan=\"7\">没有匹配航线</td></tr>'", "'<tr><td colspan=\"6\">没有匹配航线</td></tr>'", 1)

    p.write_text(text, encoding='utf-8')

css = r'''

/* Bind each flight number to its own time row; dashed separators make each pair scanable. */
.flight-time-cell {
  min-width: 220px;
}
.flight-time-pairs {
  display: inline-flex;
  flex-direction: column;
  min-width: 205px;
  max-width: 100%;
  vertical-align: middle;
}
.flight-time-pair {
  display: grid;
  grid-template-columns: 72px minmax(118px, 1fr);
  align-items: center;
  gap: 9px;
  min-height: 28px;
  padding: 4px 5px;
  white-space: nowrap;
}
.flight-time-pair + .flight-time-pair {
  border-top: 1px dashed #dccfc9;
}
.flight-pair-no {
  color: var(--ink);
  text-align: right;
  font-size: 12px;
  letter-spacing: .01em;
}
.flight-pair-time {
  padding-left: 9px;
  border-left: 1px solid #eaded9;
  color: var(--ink);
  text-align: left;
  font-variant-numeric: tabular-nums;
  font-size: 12px;
}
@media (max-width: 640px) {
  .flight-time-cell { min-width: 195px; }
  .flight-time-pairs { min-width: 182px; }
  .flight-time-pair {
    grid-template-columns: 62px minmax(108px, 1fr);
    gap: 6px;
    min-height: 25px;
    padding: 3px 2px;
  }
  .flight-pair-no,
  .flight-pair-time { font-size: 11px; }
  .flight-pair-time { padding-left: 7px; }
}
'''
for path in ('static/style.css', 'public/static/style.css'):
    p = Path(path)
    text = p.read_text(encoding='utf-8')
    marker = '/* Bind each flight number to its own time row; dashed separators make each pair scanable. */'
    if marker not in text:
        text = text.rstrip() + css + '\n'
    p.write_text(text, encoding='utf-8')

print('flight/time pair patch applied')
