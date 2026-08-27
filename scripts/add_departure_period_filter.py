from pathlib import Path


def replace_once(text, old, new, label):
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected 1 occurrence, got {count}")
    return text.replace(old, new, 1)


# HTML：会员版本去掉“（全部）”，航线总览新增出发时段。
for file_name in ["templates/index.html", "public/index.html"]:
    path = Path(file_name)
    text = path.read_text(encoding="utf-8")
    text = text.replace('666/2666（全部）', '666/2666')

    old = '''            <label class="field">
              <span>出发星期</span>
              <select id="overviewWeekday">
                <option value="">全部</option>
                <option value="1">周一</option>
                <option value="2">周二</option>
                <option value="3">周三</option>
                <option value="4">周四</option>
                <option value="5">周五</option>
                <option value="6">周六</option>
                <option value="7">周日</option>
              </select>
            </label>'''
    new = old + '''
            <label class="field">
              <span>出发时段</span>
              <select id="overviewDeparturePeriod">
                <option value="">全部时段</option>
                <option value="morning">早上出发</option>
                <option value="evening">晚上出发</option>
              </select>
            </label>'''
    text = replace_once(text, old, new, f"{file_name}: departure period control")
    path.write_text(text, encoding="utf-8")


# JS：把出发时段传给航线总览接口，并在切换时即时刷新。
for file_name in ["static/app.js", "public/static/app.js"]:
    path = Path(file_name)
    text = path.read_text(encoding="utf-8")

    old = '''    membership: $('overviewMembership').value,
    weekday: $('overviewWeekday').value,
    airline: $('overviewAirline').value,'''
    new = '''    membership: $('overviewMembership').value,
    weekday: $('overviewWeekday').value,
    departure_period: $('overviewDeparturePeriod').value,
    airline: $('overviewAirline').value,'''
    text = replace_once(text, old, new, f"{file_name}: overview request")

    old = '''  $('overviewMembership').addEventListener('change', loadOverview);
  $('overviewWeekday').addEventListener('change', loadOverview);
  $('overviewAirline').addEventListener('change', loadOverview);'''
    new = '''  $('overviewMembership').addEventListener('change', loadOverview);
  $('overviewWeekday').addEventListener('change', loadOverview);
  $('overviewDeparturePeriod').addEventListener('change', loadOverview);
  $('overviewAirline').addEventListener('change', loadOverview);'''
    text = replace_once(text, old, new, f"{file_name}: departure period listener")
    path.write_text(text, encoding="utf-8")


# CSS：桌面六个筛选项保持一行，移动端沿用现有 2/1 列响应式规则。
for file_name in ["static/style.css", "public/static/style.css"]:
    path = Path(file_name)
    text = path.read_text(encoding="utf-8")
    text = replace_once(
        text,
        '.overview-filter-grid { grid-template-columns:repeat(5,minmax(0,1fr)); margin-top:14px; }',
        '.overview-filter-grid { grid-template-columns:repeat(6,minmax(0,1fr)); margin-top:14px; }',
        f"{file_name}: overview grid",
    )
    path.write_text(text, encoding="utf-8")


# 后端：早上 = 08:00 前，晚上 = 20:00 及以后。
path = Path("app.py")
text = path.read_text(encoding="utf-8")
text = replace_once(
    text,
    '    def routes_from(self, origin, membership="all", airline="", query="", weekday=""):',
    '    def routes_from(self, origin, membership="all", airline="", query="", weekday="", departure_period=""): ',
    'app.py: routes_from signature',
)

old = '''        if weekday_value not in {1, 2, 3, 4, 5, 6, 7}:
            weekday_value = None

        groups = defaultdict(lambda: {'''
new = '''        if weekday_value not in {1, 2, 3, 4, 5, 6, 7}:
            weekday_value = None

        departure_period = str(departure_period or "").strip().lower()
        if departure_period not in {"morning", "evening"}:
            departure_period = ""

        groups = defaultdict(lambda: {'''
text = replace_once(text, old, new, 'app.py: normalize departure period')

old = '''                if weekday_value and f["departure_dt"].weekday() + 1 != weekday_value:
                    continue
                if not product_eligible(f["departure_time"], membership):
                    continue'''
new = '''                if weekday_value and f["departure_dt"].weekday() + 1 != weekday_value:
                    continue
                if departure_period == "morning" and f["departure_time"] >= "08:00":
                    continue
                if departure_period == "evening" and f["departure_time"] < "20:00":
                    continue
                if not product_eligible(f["departure_time"], membership):
                    continue'''
text = replace_once(text, old, new, 'app.py: filter departure period')

old = '''                query=one(qs, "q"),
                weekday=one(qs, "weekday"),
            )'''
new = '''                query=one(qs, "q"),
                weekday=one(qs, "weekday"),
                departure_period=one(qs, "departure_period"),
            )'''
text = replace_once(text, old, new, 'app.py: route API argument')
path.write_text(text, encoding="utf-8")


# 补一个回归测试，确保早晚时段过滤不互相串。
test_path = Path("tests/test_calendar_status.py")
test = test_path.read_text(encoding="utf-8")
anchor = '''    def test_route_weekday_filter(self):'''
if anchor not in test:
    raise SystemExit('tests: route weekday anchor not found')
new_test = '''    def test_route_departure_period_filter(self):
        morning = self.store.routes_from("PEK", membership="666", departure_period="morning")
        evening = self.store.routes_from("PEK", membership="666", departure_period="evening")
        self.assertTrue(morning)
        self.assertTrue(evening)
        self.assertTrue(all(t["departure_time"] < "08:00" for row in morning for t in row["times"]))
        self.assertTrue(all(t["departure_time"] >= "20:00" for row in evening for t in row["times"]))

'''
test = test.replace(anchor, new_test + anchor, 1)
test_path.write_text(test, encoding="utf-8")

print("departure period patch applied")
