from pathlib import Path


def replace_once(path, old, new):
    p = Path(path)
    text = p.read_text(encoding='utf-8')
    if old not in text:
        raise SystemExit(f'pattern not found in {path}: {old[:100]!r}')
    p.write_text(text.replace(old, new, 1), encoding='utf-8')


# 1) 后端：10/1-10/8 为硬性无票期，数据库标记和代码规则双保险。
app = Path('app.py')
text = app.read_text(encoding='utf-8')

old = 'WEEKDAY_CN = {1: "一", 2: "二", 3: "三", 4: "四", 5: "五", 6: "六", 7: "日"}\n\nCITY_AIRPORT_MAP = {'
new = '''WEEKDAY_CN = {1: "一", 2: "二", 3: "三", 4: "四", 5: "五", 6: "六", 7: "日"}\n\n# 飞飞乐 PLUS 已确认的硬性无票期。即使后续重新导入数据库，规则也不会丢失。\nTICKET_BLACKOUT_RANGES = (("2026-10-01", "2026-10-08"),)\n\ndef ticket_blackout(date_text):\n    value = str(date_text or "").strip()\n    return any(start <= value <= end for start, end in TICKET_BLACKOUT_RANGES)\n\nCITY_AIRPORT_MAP = {'''
if old not in text:
    raise SystemExit('blackout constant insertion point not found')
text = text.replace(old, new, 1)

old = '''    @staticmethod\n    def _basic_filter(f, membership="all", airline="", flight_no=""):\n        if not product_eligible(f["departure_time"], membership):\n            return False\n'''
new = '''    @staticmethod\n    def _basic_filter(f, membership="all", airline="", flight_no=""):\n        # holiday_blocked 来自数据导入；ticket_blackout 是业务规则双保险。\n        if f.get("holiday_blocked") or ticket_blackout(f.get("departure_date")):\n            return False\n        if not product_eligible(f["departure_time"], membership):\n            return False\n'''
if old not in text:
    raise SystemExit('_basic_filter insertion point not found')
text = text.replace(old, new, 1)

old = '''                g = groups[group_key]\n                g["destination_name"] = destination_name\n                g["weekdays"].add(f["departure_dt"].weekday() + 1)\n                g["dates"].add(f["departure_date"])\n                g["flight_records"].append(f)\n                g["airlines"].add(f["airline"])\n                g["products"].add(f["product"])\n                g["origins"].add(f["origin"])\n                g["destinations"].add(f["destination"])\n                g["airport_pairs"].add((f["origin"], f["destination"]))\n                g["date_flights"][f["departure_date"]].add(f["flight_no"])\n\n                if membership == "666":\n'''
new = '''                g = groups[group_key]\n                g["destination_name"] = destination_name\n                g["weekdays"].add(f["departure_dt"].weekday() + 1)\n                # 航班号/主时刻仍来自完整计划快照；有票日期单独按业务规则计算。\n                g["flight_records"].append(f)\n                g["airlines"].add(f["airline"])\n                g["products"].add(f["product"])\n                g["origins"].add(f["origin"])\n                g["destinations"].add(f["destination"])\n                g["airport_pairs"].add((f["origin"], f["destination"]))\n\n                blocked = f["holiday_blocked"] or ticket_blackout(f["departure_date"])\n                if blocked:\n                    g["holiday_blocked_dates"].add(f["departure_date"])\n                    continue\n\n                g["dates"].add(f["departure_date"])\n                g["date_flights"][f["departure_date"]].add(f["flight_no"])\n\n                if membership == "666":\n'''
if old not in text:
    raise SystemExit('route date accounting insertion point not found')
text = text.replace(old, new, 1)

# 删除后面重复的 holiday_blocked 记录，因为 blocked 分支已统一处理。
old = '''                if f["holiday_blocked"]:\n                    g["holiday_blocked_dates"].add(f["departure_date"])\n\n        out = []\n'''
new = '''\n        out = []\n'''
if old not in text:
    raise SystemExit('duplicate holiday block not found')
text = text.replace(old, new, 1)

old = '''        for group_key, g in groups.items():\n            operating_dates = sorted(g["dates"])\n            candidate_dates = sorted(g["b_candidate_dates"])\n'''
new = '''        for group_key, g in groups.items():\n            operating_dates = sorted(g["dates"])\n            # 当前筛选下全落在无票期的航线，不应该出现在“可用航线”列表。\n            if not operating_dates:\n                continue\n            candidate_dates = sorted(g["b_candidate_dates"])\n'''
if old not in text:
    raise SystemExit('empty route guard insertion point not found')
text = text.replace(old, new, 1)

app.write_text(text, encoding='utf-8')

# 2) 标题：模板与 public 镜像保持一致。
for html_path in ('templates/index.html', 'public/index.html'):
    p = Path(html_path)
    text = p.read_text(encoding='utf-8')
    text = text.replace('<title>海航PLUS快捷查询</title>', '<title>海航飞飞乐PLUS快速查询</title>')
    text = text.replace('<div class="eyebrow">HNA PLUS ROUTE FINDER</div>', '<div class="eyebrow">HNA FEIFEILE PLUS</div>')
    text = text.replace('<h1>海航PLUS快捷查询</h1>', '<h1>海航飞飞乐PLUS快速查询</h1>')
    p.write_text(text, encoding='utf-8')

# 3) 海航红金配色 + 两个页面都做移动端紧凑布局。
css_block = r'''

/* HNA burgundy & gold visual refresh + compact mobile forms v2 */
:root {
  --bg: #f5f1ed;
  --card: #fffdfb;
  --ink: #2d1d22;
  --muted: #796b6f;
  --primary: #a20b2a;
  --primary-dark: #7f081f;
  --accent: #c69a4b;
  --line: #eaded9;
  --soft: #f7ece9;
  --shadow: 0 14px 38px rgba(87, 35, 40, .10);
}
body { background:linear-gradient(180deg,#f3eee9 0,#f7f4f1 55%,#f3eee9 100%); }
.hero {
  background:linear-gradient(135deg,#570816 0%,#8d1026 64%,#b0792f 100%);
  box-shadow:inset 0 -1px 0 rgba(255,220,157,.24);
}
.eyebrow { color:#f4d6a1; opacity:.95; }
.data-badge {
  border-color:rgba(239,204,142,.55);
  background:rgba(255,245,225,.10);
}
.tab.active { color:var(--primary); }
.primary-btn {
  background:linear-gradient(90deg,#941027,#bd1836);
  box-shadow:0 8px 18px rgba(151,16,42,.20);
}
.primary-btn:hover { background:linear-gradient(90deg,#79091f,#a90f2d); }
.field input:focus,.field select:focus,.airport-input:focus,.airport-search:focus {
  border-color:#ba6f7e;
  box-shadow:0 0 0 3px rgba(162,11,42,.08);
}
.tag.product { background:#f7ece1; color:#8b5b16; }

@media (max-width: 520px) {
  .hero { padding:20px 14px 42px; }
  .hero h1 { margin:6px 0 5px; font-size:25px; line-height:1.12; letter-spacing:-.02em; }
  .eyebrow { font-size:9px; letter-spacing:.16em; }
  .data-badge { margin-top:10px; padding:6px 10px; font-size:10px; }
  .container { padding:0 9px; margin-top:-26px; }
  .main-tabs { gap:5px; margin-bottom:9px; }
  .tab { padding:9px 14px; border-radius:10px; font-size:13px; }

  /* 航班搜索也使用紧凑布局，避免只优化航线总览。 */
  #searchPanel .search-card {
    padding:13px;
    border-radius:16px;
  }
  #searchPanel .segmented {
    margin-bottom:11px;
    padding:3px;
    border-radius:10px;
  }
  #searchPanel .segmented button {
    padding:7px 17px;
    border-radius:8px;
    font-size:13px;
  }
  #searchPanel .search-grid { gap:8px; }
  #searchPanel .route-row {
    position:relative;
    grid-template-columns:repeat(2,minmax(0,1fr));
    gap:8px;
    align-items:end;
  }
  #searchPanel .route-row > .field:first-child { grid-column:1; }
  #searchPanel .route-row > .field:last-child { grid-column:2; }
  #searchPanel .route-row .swap-btn {
    position:absolute;
    left:50%;
    top:31px;
    transform:translateX(-50%);
    width:30px;
    height:30px;
    z-index:4;
    background:#fffaf4;
    border-color:#dfc5b3;
    color:var(--primary);
    font-size:15px;
    box-shadow:0 3px 10px rgba(83,30,35,.08);
  }
  #searchPanel .field { min-width:0; gap:4px; }
  #searchPanel .field > span { font-size:11px; line-height:1.2; }
  #searchPanel .field input,
  #searchPanel .field select,
  #searchPanel .airport-input {
    height:40px;
    min-width:0;
    padding-left:9px;
    padding-right:9px;
    border-radius:10px;
    font-size:13px;
  }
  #searchPanel .airport-input { padding-right:28px; text-overflow:ellipsis; }
  #searchPanel .airport-picker::after { right:9px; top:9px; }
  #searchPanel .options-row,
  #searchPanel .advanced-grid {
    grid-template-columns:repeat(2,minmax(0,1fr)) !important;
    gap:8px;
    margin-top:9px;
  }
  #searchPanel .advanced {
    margin-top:10px;
    padding-top:9px;
  }
  #searchPanel .advanced summary { font-size:12px; }
  #searchPanel .primary-btn {
    margin-top:11px;
    min-height:41px;
    padding:10px 14px;
    border-radius:11px;
    font-size:14px;
  }
  #searchPanel .stats-grid {
    grid-template-columns:repeat(3,minmax(0,1fr));
    gap:6px;
    margin:9px 0;
  }
  #searchPanel .stat { padding:9px 7px; border-radius:11px; text-align:center; }
  #searchPanel .stat strong { margin-top:2px; font-size:17px; }
  #searchPanel .stat span { font-size:9px; }
  #searchPanel .results-section { margin-top:11px; }

  /* 航线总览继续保持两列紧凑筛选。 */
  .route-overview-controls { padding:13px; border-radius:16px; }
  .overview-title h2 { font-size:20px; }
  .route-count { font-size:22px; }
  .overview-filter-grid {
    grid-template-columns:repeat(2,minmax(0,1fr)) !important;
    gap:8px;
    margin-top:9px;
  }
  .overview-filter-grid .field { min-width:0; gap:4px; }
  .overview-filter-grid .field > span { font-size:11px; line-height:1.2; }
  .overview-filter-grid .field input,
  .overview-filter-grid .field select,
  .route-overview-controls .airport-input {
    height:40px;
    min-width:0;
    padding-left:9px;
    padding-right:9px;
    border-radius:10px;
    font-size:13px;
  }
  .route-overview-controls .airport-input { padding-right:28px; }
  .route-overview-controls .airport-picker::after { right:9px; top:9px; }
  .route-overview-controls .primary-btn.secondary {
    margin-top:11px;
    min-height:40px;
    padding:9px 17px;
    border-radius:10px;
    font-size:13px;
  }
  .table-card { margin-top:10px; }
}
'''

for css_path in ('static/style.css', 'public/static/style.css'):
    p = Path(css_path)
    text = p.read_text(encoding='utf-8')
    marker = '/* HNA burgundy & gold visual refresh + compact mobile forms v2 */'
    if marker not in text:
        text = text.rstrip() + css_block + '\n'
    p.write_text(text, encoding='utf-8')

# 4) 回归测试：无票期在总览和直接搜索都必须被硬性排除。
test_path = Path('tests/test_calendar_status.py')
t = test_path.read_text(encoding='utf-8')
t = t.replace('self.assertEqual(route["operating_days"], 54)', 'self.assertEqual(route["operating_days"], 46)')
t = t.replace('self.assertIn("2026-10-01", route["running_only_dates"])\n        self.assertNotIn("2026-10-01", route["b_candidate_dates"])', 'self.assertNotIn("2026-10-01", route["operating_dates"])\n        self.assertNotIn("2026-10-01", route["running_only_dates"])\n        self.assertNotIn("2026-10-01", route["b_candidate_dates"])', 1)
t = t.replace('''    def test_pek_hgh_calendar_666(self):\n        route = self._pek_hgh("666")\n        self.assertIn("2026-09-01", route["b_candidate_dates"])\n        self.assertIn("2026-10-01", route["running_only_dates"])\n''', '''    def test_pek_hgh_calendar_666(self):\n        route = self._pek_hgh("666")\n        self.assertIn("2026-09-01", route["b_candidate_dates"])\n        self.assertNotIn("2026-10-01", route["operating_dates"])\n        self.assertIn("2026-10-01", route["holiday_blocked_dates"])\n''')
t = t.replace('''    def test_pek_hgh_calendar_2666(self):\n        route = self._pek_hgh("2666")\n        self.assertIn("2026-09-01", route["b_candidate_dates"])\n        self.assertIn("2026-10-01", route["running_only_dates"])\n''', '''    def test_pek_hgh_calendar_2666(self):\n        route = self._pek_hgh("2666")\n        self.assertIn("2026-09-01", route["b_candidate_dates"])\n        self.assertNotIn("2026-10-01", route["operating_dates"])\n        self.assertIn("2026-10-01", route["holiday_blocked_dates"])\n\n    def test_october_blackout_is_hard_blocked(self):\n        for day in range(1, 9):\n            date = f"2026-10-{day:02d}"\n            self.assertTrue(app.ticket_blackout(date))\n            self.assertEqual(app.STORE.search("PEK", "HGH", date, membership="all", max_stops=0), [])\n            route = self._pek_hgh("all")\n            self.assertNotIn(date, route["operating_dates"])\n        self.assertFalse(app.ticket_blackout("2026-10-09"))\n        self.assertGreater(len(app.STORE.search("PEK", "HGH", "2026-10-09", membership="all", max_stops=0)), 0)\n''')
test_path.write_text(t, encoding='utf-8')

print('patch applied')
