#!/usr/bin/env python3
from pathlib import Path
import re


def replace_once(text, old, new, label):
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected 1 occurrence, got {count}")
    return text.replace(old, new, 1)


# HTML：标题 + 航线总览恢复与航班搜索相同的机场选择器外壳。
for file_name in ["templates/index.html", "public/index.html"]:
    path = Path(file_name)
    text = path.read_text(encoding="utf-8")
    text = text.replace("<title>海航 PLUS 航线查询</title>", "<title>海航PLUS快捷查询</title>")
    text = text.replace("<h1>海航 PLUS · 航线搜索</h1>", "<h1>海航PLUS快捷查询</h1>")
    old = '''              <input id="overviewOrigin" list="overviewOriginOptions" placeholder="城市 / 机场 / 三字码" autocomplete="off" />
              <datalist id="overviewOriginOptions"></datalist>'''
    new = '''              <select id="overviewOriginSelect"></select>'''
    text = replace_once(text, old, new, f"{file_name}: overview origin control")
    path.write_text(text, encoding="utf-8")


# JS：复用原热门/字母机场选择器；总览搜索时额外提供多机场城市聚合项。
for file_name in ["static/app.js", "public/static/app.js"]:
    path = Path(file_name)
    text = path.read_text(encoding="utf-8")

    old = '''function airportLabel(code) {
  const item = airportInfo(code);
  return item ? `${item.name} ${item.code}` : '';
}'''
    new = '''function airportLabel(code) {
  const item = airportInfo(code);
  if (item) return `${item.name} ${item.code}`;
  const city = META?.cities?.find(x => x.name === code);
  return city ? `${city.name} ${city.codes.join('/')}` : '';
}'''
    text = replace_once(text, old, new, f"{file_name}: airportLabel")

    text = replace_once(
        text,
        "function enhanceAirportSelect(selectId, placeholder) {",
        "function enhanceAirportSelect(selectId, placeholder, allowCities=false) {",
        f"{file_name}: picker signature",
    )

    # 同一机场卡片组件允许总览的城市聚合项携带独立 value。
    text = text.replace(
        'data-code="${esc(item.code)}"',
        'data-value="${esc(item.value || item.code)}"',
    )
    text = text.replace(
        "if (first) choose(first.dataset.code);",
        "if (first) choose(first.dataset.value);",
    )
    text = text.replace(
        "if (btn) choose(btn.dataset.code);",
        "if (btn) choose(btn.dataset.value);",
    )

    old = '''    if (keyword) {
      const matched = (META.airports || []).filter(item => airportMatches(item, keyword));
      renderTabs();
      renderGrid(matched, `搜索结果 · ${matched.length}`, false);
      return;
    }'''
    new = '''    if (keyword) {
      const matchedAirports = (META.airports || []).filter(item => airportMatches(item, keyword));
      const normalized = keyword.trim().toUpperCase().replace(/\\s+/g, '');
      const matchedCities = allowCities ? (META.cities || [])
        .filter(city => [city.name, city.label, ...(city.codes || [])]
          .some(v => String(v || '').toUpperCase().replace(/\\s+/g, '').includes(normalized)))
        .map(city => ({
          name: city.name,
          code: (city.codes || []).join('/'),
          value: city.name,
          label: city.label,
          aggregate: true,
        })) : [];
      const matched = [...matchedCities, ...matchedAirports];
      renderTabs();
      renderGrid(matched, `搜索结果 · ${matched.length}`, false);
      return;
    }'''
    text = replace_once(text, old, new, f"{file_name}: city search results")

    old = '''  const hasBeijing = (META.cities || []).some(x => x.name === '北京');
  $('overviewOrigin').value = hasBeijing ? '北京' : (origin.value || 'PEK');
  refreshAllAirportPickers();'''
    new = '''  const overview = $('overviewOriginSelect');
  const hasBeijing = (META.cities || []).some(x => x.name === '北京');
  overview.value = hasBeijing && [...overview.options].some(o => o.value === '北京')
    ? '北京'
    : (origin.value || 'PEK');
  refreshAllAirportPickers();'''
    text = replace_once(text, old, new, f"{file_name}: default overview origin")

    old = '''  $('overviewOriginOptions').innerHTML = [
    ...(META.cities || []).map(x => `<option value="${esc(x.name)}" label="${esc(x.label)}"></option>`),
    ...(META.airports || []).map(x => `<option value="${esc(x.code)}" label="${esc(x.name)} ${esc(x.code)}"></option>`)
  ].join('');
  enhanceAirportSelect('originSelect', '输入出发城市 / 机场 / 三字码');
  enhanceAirportSelect('destinationSelect', '输入到达城市 / 机场 / 三字码');'''
    new = '''  $('overviewOriginSelect').innerHTML = optionHtml(META.airports, '选择出发城市 / 机场')
    + (META.cities || []).map(x => `<option value="${esc(x.name)}">${esc(x.label)}</option>`).join('');
  enhanceAirportSelect('originSelect', '输入出发城市 / 机场 / 三字码');
  enhanceAirportSelect('destinationSelect', '输入到达城市 / 机场 / 三字码');
  enhanceAirportSelect('overviewOriginSelect', '输入出发城市 / 机场 / 三字码', true);'''
    text = replace_once(text, old, new, f"{file_name}: init overview picker")

    text = replace_once(
        text,
        "const origin = $('overviewOrigin').value.trim() || $('originSelect').value;",
        "const origin = $('overviewOriginSelect').value.trim() || $('originSelect').value;",
        f"{file_name}: load overview origin",
    )
    old = '''  $('overviewOrigin').addEventListener('change', loadOverview);
  $('overviewOrigin').addEventListener('keydown', e => { if (e.key === 'Enter') loadOverview(); });'''
    new = '''  $('overviewOriginSelect').addEventListener('change', loadOverview);'''
    text = replace_once(text, old, new, f"{file_name}: overview origin events")

    # 日历只保留“有航线 / 无航线”两个业务状态。
    new_calendar = '''function routeCalendarHtml(route) {
  const startText = route.data_start || META.date_min;
  const endText = route.data_end || META.date_max;
  const operating = new Set(route.operating_dates || []);
  const dateFlights = route.date_flights || {};
  const weekdayFilter = Number(route.weekday_filter || 0);

  const matchesWeekday = (date) => {
    if (!weekdayFilter) return true;
    const day = new Date(`${date}T00:00:00`).getDay();
    return (day === 0 ? 7 : day) === weekdayFilter;
  };

  const start = new Date(`${startText}T00:00:00`);
  const end = new Date(`${endText}T00:00:00`);
  const months = [];
  let cursor = new Date(start.getFullYear(), start.getMonth(), 1);
  const lastMonth = new Date(end.getFullYear(), end.getMonth(), 1);

  while (cursor <= lastMonth) {
    const year = cursor.getFullYear();
    const month = cursor.getMonth() + 1;
    const daysInMonth = new Date(year, month, 0).getDate();
    const firstDay = new Date(year, month - 1, 1);
    const mondayOffset = (firstDay.getDay() + 6) % 7;
    const cells = [];

    for (let i = 0; i < mondayOffset; i++) {
      cells.push('<span class="calendar-day blank"></span>');
    }

    for (let day = 1; day <= daysInMonth; day++) {
      const date = isoDateLocal(year, month, day);
      const inRange = date >= startText && date <= endText;
      const selectedWeekday = matchesWeekday(date);
      const isOperating = operating.has(date) && selectedWeekday;
      const flights = (dateFlights[date] || []).join(' / ');

      let cls = 'calendar-day';
      let title = '';
      if (!inRange || (weekdayFilter && !selectedWeekday)) {
        cls += ' outside';
      } else if (isOperating) {
        cls += ' route-on';
        title = `${date}：有航线${flights ? `；${flights}` : ''}`;
      } else {
        cls += ' route-off';
        title = `${date}：无航线`;
      }
      cells.push(`<span class="${cls}" title="${esc(title)}">${day}</span>`);
    }

    months.push(`
      <div class="route-calendar-month">
        <div class="calendar-month-title">${year}年${month}月</div>
        <div class="calendar-weekdays">
          <span>一</span><span>二</span><span>三</span><span>四</span><span>五</span><span>六</span><span>日</span>
        </div>
        <div class="calendar-days">${cells.join('')}</div>
      </div>
    `);
    cursor = new Date(year, month, 1);
  }

  return `
    <div class="route-date-panel">
      <div class="route-date-summary simple-route-legend">
        <div><span class="legend-dot route-on"></span><strong>有航线</strong></div>
        <div><span class="legend-dot route-off"></span><strong>无航线</strong></div>
      </div>
      <div class="route-calendars">${months.join('')}</div>
    </div>
  `;
}'''
    pattern = re.compile(
        r"function routeCalendarHtml\(route\) \{.*?\n\}\n\n\nasync function loadOverview\(\) \{",
        re.S,
    )
    text, count = pattern.subn(
        lambda _m: new_calendar + "\n\n\nasync function loadOverview() {",
        text,
        count=1,
    )
    if count != 1:
        raise SystemExit(f"{file_name}: calendar function replacement failed ({count})")

    old = '''        <td class="dest"><strong>${esc(x.destination_name)}</strong> <span class="tag aggregate-tag">${x.flight_records_count} 班</span><div class="sub">${esc(x.airlines.join(' / '))}</div></td>'''
    new = '''        <td class="dest"><div class="dest-title-line"><strong>${esc(x.destination_name)}</strong><span class="route-flight-count">${x.flight_records_count} 班</span></div><div class="sub">${esc(x.airlines.join(' / '))}</div></td>'''
    text = replace_once(text, old, new, f"{file_name}: flight count layout")

    path.write_text(text, encoding="utf-8")


css_extra = '''

/* 航线总览的目的地与记录数保持在同一行。 */
.dest-title-line {
  display:flex;
  align-items:center;
  gap:8px;
  min-height:24px;
  white-space:nowrap;
}
.routes-table .dest .dest-title-line strong { display:inline; }
.route-flight-count {
  display:inline-flex;
  align-items:center;
  justify-content:center;
  min-width:44px;
  height:22px;
  padding:0 8px;
  border-radius:999px;
  background:#eef5fb;
  color:#38658f;
  font-size:11px;
  font-weight:800;
  line-height:1;
}

.simple-route-legend {
  gap:18px;
  margin-bottom:14px;
  font-size:13px;
}
.legend-dot.route-on { background:#15966f; }
.legend-dot.route-off { background:#e4e9ee; border:1px solid #ced6de; }
.calendar-day.route-on {
  background:#daf4e9;
  color:#087452;
  border:1px solid #a9dfca;
  font-weight:800;
}
.calendar-day.route-off {
  background:#f0f2f4;
  color:#9ca6b1;
  border:1px solid #e1e5e9;
}
'''
for file_name in ["static/style.css", "public/static/style.css"]:
    path = Path(file_name)
    text = path.read_text(encoding="utf-8")
    marker = "/* 航线总览的目的地与记录数保持在同一行。 */"
    if marker not in text:
        text = text.rstrip() + css_extra + "\n"
    path.write_text(text, encoding="utf-8")

print("overview UI patch applied")
