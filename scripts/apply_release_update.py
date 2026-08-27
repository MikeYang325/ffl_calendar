#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Apply the SQLite + search/UI release changes to the checked-out repository."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def replace_between(text, start_token, end_token, replacement):
    start = text.index(start_token)
    end = text.index(end_token, start)
    return text[:start] + replacement + text[end:]


def update_app():
    path = ROOT / "app.py"
    text = path.read_text(encoding="utf-8")
    text = text.replace("import csv\n", "import sqlite3\n")
    text = text.replace(
        'DATA_FILE = Path(os.environ.get("HNA_FLIGHT_CSV", BASE_DIR / "data" / "flight_daily.csv"))',
        'DB_FILE = Path(os.environ.get("HNA_FLIGHT_DB", BASE_DIR / "data" / "flights.db"))',
    )

    city_map = '''\nCITY_AIRPORT_MAP = {\n    "北京": ("PEK", "PKX"),\n    "上海": ("SHA", "PVG"),\n    "成都": ("CTU", "TFU"),\n    "重庆": ("CKG", "WSK"),\n    "遵义": ("ZYI", "WMT"),\n    "东京": ("HND", "NRT"),\n    "首尔": ("ICN", "GMP"),\n    "大阪": ("KIX", "ITM"),\n    "台北": ("TPE", "TSA"),\n}\n'''
    anchor = 'WEEKDAY_CN = {1: "一", 2: "二", 3: "三", 4: "四", 5: "五", 6: "六", 7: "日"}\n'
    if "CITY_AIRPORT_MAP" not in text:
        text = text.replace(anchor, anchor + city_map)

    loader = '''class FlightStore:\n    def __init__(self, db_path):\n        self.db_path = Path(db_path)\n        self.flights = []\n        self.by_date_origin = defaultdict(list)\n        self.by_origin_sorted = defaultdict(list)\n        self.by_origin_times = defaultdict(list)\n        self.airports = {}\n        self.airlines = {}\n        self.city_airports = {}\n        self.city_by_airport = {}\n        self.date_min = ""\n        self.date_max = ""\n        self.route_overview = {}\n        self.load()\n\n    def load(self):\n        if not self.db_path.exists():\n            raise FileNotFoundError(f"找不到数据库：{self.db_path}")\n\n        raw, dates = [], []\n        with sqlite3.connect(self.db_path) as conn:\n            conn.row_factory = sqlite3.Row\n            rows = conn.execute("""\n                SELECT origin, origin_name, destination, destination_name,\n                       flight_no, operating_flight_no, departure_date, departure_time,\n                       arrival_date, arrival_time, duration_minutes, aircraft,\n                       code_share, stop_quantity, flight_running, b_status,\n                       b_expected_or_seen, b_visible_raw, holiday_blocked,\n                       status_666, eligible_666, status_2666, eligible_2666\n                FROM flights\n                ORDER BY departure_date, departure_time, origin, destination, flight_no\n            """)\n            for db_row in rows:\n                row = dict(db_row)\n                dep_dt = parse_datetime(row["departure_date"], row["departure_time"])\n                arr_dt = parse_datetime(row["arrival_date"], row["arrival_time"])\n                code = airline_code(row["flight_no"])\n                duration = int(row["duration_minutes"] or 0)\n                flight = {\n                    "origin": row["origin"],\n                    "origin_name": row["origin_name"],\n                    "destination": row["destination"],\n                    "destination_name": row["destination_name"],\n                    "flight_no": row["flight_no"],\n                    "operating_flight_no": row["operating_flight_no"],\n                    "airline_code": code,\n                    "airline": AIRLINE_MAP.get(code, code),\n                    "departure_date": row["departure_date"],\n                    "departure_time": row["departure_time"],\n                    "arrival_date": row["arrival_date"],\n                    "arrival_time": row["arrival_time"],\n                    "departure_dt": dep_dt,\n                    "arrival_dt": arr_dt,\n                    "duration_minutes": duration,\n                    "duration_text": minutes_text(duration),\n                    "aircraft": row["aircraft"],\n                    "code_share": bool(row["code_share"]),\n                    "stop_quantity": int(row["stop_quantity"] or 0),\n                    "product": product_for_departure(row["departure_time"]),\n                    "cross_day": (arr_dt.date() - dep_dt.date()).days,\n                    "flight_running": bool(row["flight_running"]),\n                    "b_status": row["b_status"],\n                    "b_expected_or_seen": bool(row["b_expected_or_seen"]),\n                    "b_visible_raw": bool(row["b_visible_raw"]),\n                    "holiday_blocked": bool(row["holiday_blocked"]),\n                    "status_666": row["status_666"],\n                    "eligible_666": bool(row["eligible_666"]),\n                    "status_2666": row["status_2666"],\n                    "eligible_2666": bool(row["eligible_2666"]),\n                }\n                raw.append(flight)\n                dates.append(row["departure_date"])\n                self.airports[row["origin"]] = row["origin_name"]\n                self.airports[row["destination"]] = row["destination_name"]\n                self.airlines[code] = AIRLINE_MAP.get(code, code)\n\n        raw.sort(key=lambda x: x["departure_dt"])\n        self.flights = raw\n        if dates:\n            self.date_min, self.date_max = min(dates), max(dates)\n\n        for flight in self.flights:\n            self.by_date_origin[(flight["departure_date"], flight["origin"])].append(flight)\n            self.by_origin_sorted[flight["origin"]].append(flight)\n\n        for origin, flights in self.by_origin_sorted.items():\n            flights.sort(key=lambda x: x["departure_dt"])\n            self.by_origin_times[origin] = [f["departure_dt"] for f in flights]\n\n        self.city_airports = {\n            city: [code for code in codes if code in self.airports]\n            for city, codes in CITY_AIRPORT_MAP.items()\n        }\n        self.city_airports = {city: codes for city, codes in self.city_airports.items() if codes}\n        self.city_by_airport = {\n            code: city for city, codes in self.city_airports.items() for code in codes\n        }\n        self._build_route_overview()\n\n    def city_options(self):\n        return [\n            {"name": city, "codes": codes, "label": f"{city}（{'/'.join(codes)}）"}\n            for city, codes in sorted(self.city_airports.items())\n            if len(codes) >= 2\n        ]\n\n    def resolve_origins(self, value):\n        raw = str(value or "").strip()\n        if not raw:\n            return [], "", False\n        upper = raw.upper()\n        if upper in self.airports:\n            return [upper], self.airports.get(upper, upper), False\n        if raw in self.city_airports:\n            codes = self.city_airports[raw]\n            return list(codes), raw, len(codes) > 1\n\n        matched = [\n            code for code, name in self.airports.items()\n            if raw.lower() in str(name).lower()\n        ]\n        if matched:\n            matched = sorted(set(matched))\n            mapped_cities = {self.city_by_airport.get(code) for code in matched}\n            mapped_cities.discard(None)\n            if len(mapped_cities) == 1:\n                city = next(iter(mapped_cities))\n                city_codes = [c for c in self.city_airports.get(city, []) if c in matched]\n                if city_codes:\n                    return city_codes, city, len(city_codes) > 1\n            if len(matched) == 1:\n                code = matched[0]\n                return matched, self.airports.get(code, code), False\n            return matched, raw, len(matched) > 1\n        return [], raw, False\n\n'''
    text = replace_between(text, "class FlightStore:", "    def _build_route_overview(self):", loader)

    text = text.replace(
        '            "airlines": airlines,\n            "membership_rules": {"666": "08:00前或20:00后出发", "2666": "全天覆盖"},',
        '            "airlines": airlines,\n            "cities": self.city_options(),\n            "membership_rules": {"666": "08:00前或20:00后出发", "2666": "全天覆盖"},',
    )

    routes_method = '''    def routes_from(self, origin, membership="all", airline="", query="", weekday=""):\n        origin_codes, origin_name, aggregate_mode = self.resolve_origins(origin)\n        if not origin_codes:\n            return []\n\n        q = (query or "").strip().lower()\n        try:\n            weekday_value = int(str(weekday).strip()) if str(weekday).strip() else None\n        except (TypeError, ValueError):\n            weekday_value = None\n        if weekday_value not in {1, 2, 3, 4, 5, 6, 7}:\n            weekday_value = None\n\n        groups = defaultdict(lambda: {\n            "weekdays": set(),\n            "dates": set(),\n            "flight_records": [],\n            "airlines": set(),\n            "products": set(),\n            "origins": set(),\n            "destinations": set(),\n            "airport_pairs": set(),\n            "b_candidate_dates": set(),\n            "b_visible_dates": set(),\n            "running_only_dates": set(),\n            "holiday_blocked_dates": set(),\n            "date_flights": defaultdict(set),\n        })\n\n        for origin_code in origin_codes:\n            for f in self.by_origin_sorted.get(origin_code, []):\n                if weekday_value and f["departure_dt"].weekday() + 1 != weekday_value:\n                    continue\n                if not product_eligible(f["departure_time"], membership):\n                    continue\n                if airline and f["airline_code"] != airline:\n                    continue\n\n                destination_city = self.city_by_airport.get(f["destination"])\n                if q:\n                    haystack = " ".join([\n                        f["destination"], f["destination_name"], destination_city or "",\n                        f["flight_no"], f["airline"], f["airline_code"],\n                    ]).lower()\n                    if q not in haystack:\n                        continue\n\n                if aggregate_mode and destination_city:\n                    group_key = f"CITY:{destination_city}"\n                    destination_name = destination_city\n                else:\n                    group_key = f["destination"]\n                    destination_name = f["destination_name"]\n\n                g = groups[group_key]\n                g["destination_name"] = destination_name\n                g["weekdays"].add(f["departure_dt"].weekday() + 1)\n                g["dates"].add(f["departure_date"])\n                g["flight_records"].append(f)\n                g["airlines"].add(f["airline"])\n                g["products"].add(f["product"])\n                g["origins"].add(f["origin"])\n                g["destinations"].add(f["destination"])\n                g["airport_pairs"].add((f["origin"], f["destination"]))\n                g["date_flights"][f["departure_date"]].add(f["flight_no"])\n\n                if membership == "666":\n                    b_candidate = f["eligible_666"]\n                    b_visible = f["eligible_666"] and f["b_visible_raw"]\n                elif membership == "2666":\n                    b_candidate = f["eligible_2666"]\n                    b_visible = f["eligible_2666"] and f["b_visible_raw"]\n                else:\n                    b_candidate = f["b_expected_or_seen"]\n                    b_visible = f["b_visible_raw"] and f["b_expected_or_seen"]\n\n                if b_candidate:\n                    g["b_candidate_dates"].add(f["departure_date"])\n                else:\n                    g["running_only_dates"].add(f["departure_date"])\n                if b_visible:\n                    g["b_visible_dates"].add(f["departure_date"])\n                if f["holiday_blocked"]:\n                    g["holiday_blocked_dates"].add(f["departure_date"])\n\n        out = []\n        for group_key, g in groups.items():\n            operating_dates = sorted(g["dates"])\n            candidate_dates = sorted(g["b_candidate_dates"])\n            visible_dates = sorted(g["b_visible_dates"])\n            running_only_dates = sorted(g["running_only_dates"] - g["b_candidate_dates"])\n            holiday_blocked_dates = sorted(g["holiday_blocked_dates"])\n            schedule_rows = representative_schedule_rows(g["flight_records"], tolerance_minutes=30)\n            destination_codes = sorted(g["destinations"])\n            route_origin_codes = sorted(g["origins"])\n            destination = "/".join(destination_codes)\n\n            out.append({\n                "origin": "/".join(route_origin_codes),\n                "origin_name": origin_name,\n                "origin_codes": route_origin_codes,\n                "destination": destination,\n                "destination_codes": destination_codes,\n                "destination_name": g["destination_name"],\n                "aggregate": bool(aggregate_mode),\n                "airport_pairs": [\n                    {"origin": a, "destination": b}\n                    for a, b in sorted(g["airport_pairs"])\n                ],\n                "schedule": "".join(str(x) for x in sorted(g["weekdays"])),\n                "schedule_text": " ".join(f"周{WEEKDAY_CN[x]}" for x in sorted(g["weekdays"])),\n                "schedule_rows": schedule_rows,\n                "flight_nos": [row["flight_no"] for row in schedule_rows],\n                "times": [\n                    {\n                        "departure_time": row["departure_time"],\n                        "arrival_time": row["arrival_time"],\n                        "cross_day": row["cross_day"],\n                        "observations": row["observations"],\n                        "merged_variants": row["merged_variants"],\n                    }\n                    for row in schedule_rows\n                ],\n                "airlines": sorted(g["airlines"]),\n                "products": sorted(g["products"]),\n                "flight_records_count": len(g["flight_records"]),\n                "operating_days": len(operating_dates),\n                "operating_dates": operating_dates,\n                "b_candidate_dates": candidate_dates,\n                "b_visible_dates": visible_dates,\n                "running_only_dates": running_only_dates,\n                "holiday_blocked_dates": holiday_blocked_dates,\n                "date_flights": {\n                    date: sorted(flights)\n                    for date, flights in sorted(g["date_flights"].items())\n                },\n                "first_date": operating_dates[0] if operating_dates else "",\n                "last_date": operating_dates[-1] if operating_dates else "",\n                "data_start": self.date_min,\n                "data_end": self.date_max,\n                "weekday_filter": weekday_value or 0,\n            })\n\n        out.sort(key=lambda x: (x["destination_name"], x["destination"]))\n        return out\n\n\n'''
    text = replace_between(text, "    def routes_from(self, origin, membership=\"all\", airline=\"\", query=\"\"):", "STORE = FlightStore(DATA_FILE)", routes_method)
    text = text.replace("STORE = FlightStore(DATA_FILE)", "STORE = FlightStore(DB_FILE)")

    old_routes_api = '''        if path == "/api/routes":\n            origin = one(qs, "origin").strip().upper()\n            if not origin:\n                return self.send_json({"error": "origin 为必填项"}, 400)\n            rows = STORE.routes_from(\n                origin,\n                membership=one(qs, "membership", "all"),\n                airline=one(qs, "airline").strip().upper(),\n                query=one(qs, "q"),\n            )\n            return self.send_json({"origin": origin, "origin_name": STORE.airports.get(origin, origin), "count": len(rows), "routes": rows})\n'''
    new_routes_api = '''        if path == "/api/routes":\n            origin = one(qs, "origin").strip()\n            if not origin:\n                return self.send_json({"error": "origin 为必填项"}, 400)\n            origin_codes, origin_name, aggregate = STORE.resolve_origins(origin)\n            if not origin_codes:\n                return self.send_json({"error": "没有找到这个城市或机场"}, 400)\n            rows = STORE.routes_from(\n                origin,\n                membership=one(qs, "membership", "all"),\n                airline=one(qs, "airline").strip().upper(),\n                query=one(qs, "q"),\n                weekday=one(qs, "weekday"),\n            )\n            return self.send_json({\n                "origin": origin, "origin_name": origin_name, "origin_codes": origin_codes,\n                "aggregate": aggregate, "count": len(rows), "routes": rows\n            })\n'''
    if old_routes_api not in text:
        raise RuntimeError("routes API block not found")
    text = text.replace(old_routes_api, new_routes_api)
    text = text.replace(
        'return self.send_json({"ok": True, "data_file": str(DATA_FILE), "records": len(STORE.flights)})',
        'return self.send_json({"ok": True, "database": str(DB_FILE), "records": len(STORE.flights)})',
    )
    text = text.replace('    print(f"数据：{DATA_FILE}")', '    print(f"数据库：{DB_FILE}")')
    text = text.replace("新 flight_daily.csv 中的", "数据库中的")
    path.write_text(text, encoding="utf-8")


def update_html(filename):
    path = ROOT / filename
    html = path.read_text(encoding="utf-8")
    html = html.replace('          <p>基于 flight_daily.csv 的航班计划快照，查询直飞、中转、666 / 2666 适用航班。</p>\n', '')
    html = html.replace('          <div class="rule-tip"><b>规则：</b>666 = 08:00 前或 20:00 后出发；2666 = 全天覆盖。中转默认要求 1–24 小时，总行程不超过 48 小时。</div>\n', '')
    html = html.replace('              <p>查看某个出发机场在整个数据周期内出现过的全部 PLUS 目的地。</p>\n', '')

    html = html.replace('''              <select id="membershipSelect">\n                <option value="all">全部</option>\n                <option value="666">666（08:00前 / 20:00后）</option>\n                <option value="2666">2666（全天）</option>\n              </select>''', '''              <select id="membershipSelect">\n                <option value="666" selected>666</option>\n                <option value="all">666/2666（全部）</option>\n              </select>''')

    html = html.replace('<div class="search-grid advanced-grid">\n            <label class="field">\n              <span>出发城市 / 机场</span>\n              <select id="overviewOrigin"></select>', '<div class="search-grid overview-filter-grid">\n            <label class="field">\n              <span>出发城市 / 机场</span>\n              <input id="overviewOrigin" list="overviewOriginOptions" placeholder="城市 / 机场 / 三字码" autocomplete="off" />\n              <datalist id="overviewOriginOptions"></datalist>')

    html = html.replace('''              <select id="overviewMembership">\n                <option value="all">全部</option>\n                <option value="666">666</option>\n                <option value="2666">2666</option>\n              </select>''', '''              <select id="overviewMembership">\n                <option value="666" selected>666</option>\n                <option value="all">666/2666（全部）</option>\n              </select>''')

    weekday_field = '''            <label class="field">\n              <span>出发星期</span>\n              <select id="overviewWeekday">\n                <option value="">全部</option>\n                <option value="1">周一</option>\n                <option value="2">周二</option>\n                <option value="3">周三</option>\n                <option value="4">周四</option>\n                <option value="5">周五</option>\n                <option value="6">周六</option>\n                <option value="7">周日</option>\n              </select>\n            </label>\n'''
    membership_close = '''              </select>\n            </label>\n            <label class="field">\n              <span>航司</span>\n              <select id="overviewAirline"><option value="">全部航司</option></select>'''
    if 'id="overviewWeekday"' not in html:
        html = html.replace(membership_close, '              </select>\n            </label>\n' + weekday_field + '            <label class="field">\n              <span>航司</span>\n              <select id="overviewAirline"><option value="">全部航司</option></select>', 1)

    html = html.replace('<span>筛选目的地 / 航班号</span>', '<span>搜索</span>')
    html = html.replace('placeholder="例如 福州 / HU7195"', 'placeholder="目的地 / 机场 / 航班号"')
    html = html.replace('id="overviewBtn">查看全部航线</button>', 'id="overviewBtn">查看航线</button>')
    path.write_text(html, encoding="utf-8")


def update_js(filename):
    path = ROOT / filename
    js = path.read_text(encoding="utf-8")
    js = js.replace("let tripMode = 'oneway';", "let tripMode = 'oneway';\nlet overviewQueryTimer = null;")

    old_default = '''function setDefaultAirports() {\n  const origin = $('originSelect');\n  const dest = $('destinationSelect');\n  if ([...origin.options].some(o => o.value === 'PEK')) origin.value = 'PEK';\n  if ([...dest.options].some(o => o.value === 'CAN')) dest.value = 'CAN';\n  $('overviewOrigin').value = origin.value || 'PEK';\n  refreshAllAirportPickers();\n}'''
    new_default = '''function setDefaultAirports() {\n  const origin = $('originSelect');\n  const dest = $('destinationSelect');\n  if ([...origin.options].some(o => o.value === 'PEK')) origin.value = 'PEK';\n  if ([...dest.options].some(o => o.value === 'CAN')) dest.value = 'CAN';\n  const hasBeijing = (META.cities || []).some(x => x.name === '北京');\n  $('overviewOrigin').value = hasBeijing ? '北京' : (origin.value || 'PEK');\n  refreshAllAirportPickers();\n}'''
    if old_default not in js:
        raise RuntimeError(f"default airports block not found: {filename}")
    js = js.replace(old_default, new_default)

    js = js.replace("  $('overviewOrigin').innerHTML = optionHtml(META.airports, '选择出发机场');\n", "  $('overviewOriginOptions').innerHTML = [\n    ...(META.cities || []).map(x => `<option value=\"${esc(x.name)}\" label=\"${esc(x.label)}\"></option>`),\n    ...(META.airports || []).map(x => `<option value=\"${esc(x.code)}\" label=\"${esc(x.name)} ${esc(x.code)}\"></option>`)\n  ].join('');\n")
    js = js.replace("  enhanceAirportSelect('overviewOrigin', '输入出发城市 / 机场 / 三字码');\n", "")
    js = js.replace("  $('overviewAirline').innerHTML = $('airlineSelect').innerHTML;", "  $('overviewAirline').innerHTML = $('airlineSelect').innerHTML;\n  $('membershipSelect').value = '666';\n  $('overviewMembership').value = '666';")

    js = js.replace(
        "  const serviceDates = dateRangeList(serviceStart, serviceEnd);\n  const inactiveDates = serviceDates.filter(d => !operating.has(d));",
        "  const weekdayFilter = Number(route.weekday_filter || 0);\n  const matchesWeekday = (date) => {\n    if (!weekdayFilter) return true;\n    const day = new Date(`${date}T00:00:00`).getDay();\n    return (day === 0 ? 7 : day) === weekdayFilter;\n  };\n  const serviceDates = dateRangeList(serviceStart, serviceEnd).filter(matchesWeekday);\n  const inactiveDates = serviceDates.filter(d => !operating.has(d));",
    )
    js = js.replace(
        "      if (!inRange) {\n        cls += ' outside';",
        "      if (!inRange) {\n        cls += ' outside';\n      } else if (weekdayFilter && !matchesWeekday(date)) {\n        cls += ' outside-window';\n        title = `${date}：未选择该星期`;",
    )
    js = js.replace('        <div class="calendar-note">航线首末出现：${esc(serviceStart)} ～ ${esc(serviceEnd)}；完整数据范围：${esc(startText)} ～ ${esc(endText)}。日历只展示航班运行与 B 舱状态，不展示余票。</div>\n', '')

    old_overview_start = '''async function loadOverview() {\n  const origin = $('overviewOrigin').value || $('originSelect').value;\n  if (!origin) return;\n  const p = new URLSearchParams({\n    origin,\n    membership: $('overviewMembership').value,\n    airline: $('overviewAirline').value,\n    q: $('overviewQuery').value.trim(),\n  });'''
    new_overview_start = '''async function loadOverview() {\n  const origin = $('overviewOrigin').value.trim() || $('originSelect').value;\n  if (!origin) return;\n  const p = new URLSearchParams({\n    origin,\n    membership: $('overviewMembership').value,\n    weekday: $('overviewWeekday').value,\n    airline: $('overviewAirline').value,\n    q: $('overviewQuery').value.trim(),\n  });'''
    if old_overview_start not in js:
        raise RuntimeError(f"overview request block not found: {filename}")
    js = js.replace(old_overview_start, new_overview_start)

    old_render = '''    const dateId = `route-dates-${idx}`;\n    const scheduleTip = x.schedule === '1234567'\n      ? '<div class="sub schedule-warning">周一至周日均有出现 ≠ 每天运行</div>'\n      : `<div class="sub">${esc(x.schedule_text)}</div>`;\n\n    return `\n      <tr class="route-main-row">\n        <td class="dest"><strong>${esc(x.destination_name)}</strong><div class="sub">${esc(x.airlines.join(' / '))}</div></td>\n        <td>${esc(x.destination)}</td>\n        <td>${x.flight_nos.map(esc).join('<br>')}</td>\n        <td class="mono">${times}</td>\n        <td><strong>${esc(x.schedule)}</strong>${scheduleTip}</td>\n        <td>\n          <strong>${x.operating_days} 天</strong>\n          <div class="sub">${esc(x.first_date)} ~ ${esc(x.last_date)}</div>\n          <button type="button" class="date-detail-btn" data-target="${dateId}">查看具体日期</button>\n        </td>\n        <td>${x.products.map(p => `<span class="tag product">${esc(p)}</span>`).join(' ')}</td>\n      </tr>'''
    new_render = '''    const dateId = `route-dates-${idx}`;\n    const airportText = x.aggregate\n      ? `${(x.origin_codes || []).map(esc).join('/')} → ${(x.destination_codes || []).map(esc).join('/')}`\n      : (x.destination_codes || [x.destination]).map(esc).join('/');\n\n    return `\n      <tr class="route-main-row">\n        <td class="dest"><strong>${esc(x.destination_name)}</strong> <span class="tag aggregate-tag">${x.flight_records_count} 班</span><div class="sub">${esc(x.airlines.join(' / '))}</div></td>\n        <td>${airportText}</td>\n        <td>${x.flight_nos.map(esc).join('<br>')}</td>\n        <td class="mono">${times}</td>\n        <td><strong>${esc(x.schedule)}</strong></td>\n        <td>\n          <strong>${x.operating_days} 天</strong>\n          <div class="sub">${esc(x.first_date)} ~ ${esc(x.last_date)}</div>\n          <button type="button" class="date-detail-btn" data-target="${dateId}">查看具体日期</button>\n        </td>\n        <td>${x.products.map(p => `<span class="tag product">${esc(p)}</span>`).join(' ')}</td>\n      </tr>'''
    if old_render not in js:
        raise RuntimeError(f"overview render block not found: {filename}")
    js = js.replace(old_render, new_render)

    old_events = '''  $('overviewOrigin').addEventListener('change', loadOverview);\n  $('overviewMembership').addEventListener('change', loadOverview);\n  $('overviewAirline').addEventListener('change', loadOverview);\n  $('overviewQuery').addEventListener('keydown', e => { if (e.key === 'Enter') loadOverview(); });'''
    new_events = '''  $('overviewOrigin').addEventListener('change', loadOverview);\n  $('overviewOrigin').addEventListener('keydown', e => { if (e.key === 'Enter') loadOverview(); });\n  $('overviewMembership').addEventListener('change', loadOverview);\n  $('overviewWeekday').addEventListener('change', loadOverview);\n  $('overviewAirline').addEventListener('change', loadOverview);\n  $('overviewQuery').addEventListener('input', () => {\n    clearTimeout(overviewQueryTimer);\n    overviewQueryTimer = setTimeout(loadOverview, 250);\n  });\n  $('overviewQuery').addEventListener('keydown', e => {\n    if (e.key === 'Enter') {\n      clearTimeout(overviewQueryTimer);\n      loadOverview();\n    }\n  });'''
    if old_events not in js:
        raise RuntimeError(f"overview events block not found: {filename}")
    js = js.replace(old_events, new_events)
    path.write_text(js, encoding="utf-8")


def update_css(filename):
    path = ROOT / filename
    css = path.read_text(encoding="utf-8")
    css = css.replace(
        ".advanced-grid { grid-template-columns:repeat(4,minmax(0,1fr)); margin-top:14px; }",
        ".advanced-grid { grid-template-columns:repeat(4,minmax(0,1fr)); margin-top:14px; }\n.overview-filter-grid { grid-template-columns:repeat(5,minmax(0,1fr)); margin-top:14px; }\n.aggregate-tag { margin-left:6px; vertical-align:middle; }",
    )
    css = css.replace(
        ".options-row,.advanced-grid { grid-template-columns:1fr 1fr; }",
        ".options-row,.advanced-grid,.overview-filter-grid { grid-template-columns:1fr 1fr; }",
    )
    css = css.replace(
        ".options-row,.advanced-grid { grid-template-columns:1fr; }",
        ".options-row,.advanced-grid,.overview-filter-grid { grid-template-columns:1fr; }",
    )
    path.write_text(css, encoding="utf-8")


def update_readme():
    path = ROOT / "README.md"
    text = path.read_text(encoding="utf-8")
    text = text.replace(
        '这是一个直接读取 `data/flight_daily.csv` 的本地网页工具，使用 Python 标准库实现，**不需要 pip 安装任何第三方包**。',
        '这是一个直接读取 `data/flights.db` SQLite 数据库的网页工具，使用 Python 标准库实现，**不需要 pip 安装任何第三方包**。',
    )
    text = text.replace("- 666 / 2666 筛选", "- 会员筛选默认 666，可切换 666/2666（全部）")
    text = text.replace("- 航司、航班号筛选", "- 航司、航班号筛选；航线总览支持周一至周日筛选")
    if "城市级航线总览" not in text:
        text = text.replace("- 航线总览：按出发机场查看整个数据周期的全部目的地、航班号、时刻、班期、运行天数", "- 航线总览：按出发机场查看整个数据周期的全部目的地、航班号、时刻、班期、运行天数\n- 城市级航线总览：输入北京、上海、成都等城市时，自动合并该城市多个机场，并按目的城市汇总")
    old_update = '''## 更新航班数据\n\n以后重新抓取数据，只需要覆盖：\n\n```text\ndata/flight_daily.csv\n```\n\n然后重启网页程序即可，不需要改代码。'''
    new_update = '''## 更新航班数据\n\n运行时数据使用 SQLite：\n\n```text\ndata/flights.db\n```\n\n拿到新的 `flight_daily.csv` 后执行：\n\n```bash\npython3 scripts/import_csv_to_sqlite.py /path/to/flight_daily.csv data/flights.db\n```\n\n生成新的数据库后提交 `data/flights.db`。生产运行不再读取 CSV。'''
    text = text.replace(old_update, new_update)
    text = text.replace("- 当班期显示 `1234567` 时增加提示：这只表示周一至周日都曾出现，不代表每天运行\n", "")
    text = text.replace("## 新 flight_daily.csv 日历状态", "## 数据库日历状态")
    text = text.replace("当天 CSV 没有航班运行记录", "当天数据库没有航班运行记录")
    text = text.replace("单日航班搜索仍显示 CSV 中当天的真实起降时刻，不做合并。", "单日航班搜索仍显示数据库中当天的真实起降时刻，不做合并。")
    path.write_text(text, encoding="utf-8")


def update_tests():
    path = ROOT / "tests" / "test_calendar_status.py"
    text = path.read_text(encoding="utf-8")
    text = text.replace("def test_new_csv_fields_loaded(self):", "def test_database_fields_loaded(self):")
    marker = '''    def test_pek_hgh_calendar_2666(self):\n        route = self._pek_hgh("2666")\n        self.assertIn("2026-09-01", route["b_candidate_dates"])\n        self.assertIn("2026-10-01", route["running_only_dates"])\n'''
    extra = '''\n    def test_city_origin_resolution(self):\n        codes, name, aggregate = app.STORE.resolve_origins("北京")\n        self.assertEqual(name, "北京")\n        self.assertTrue(aggregate)\n        self.assertEqual(set(codes), {"PEK", "PKX"})\n\n    def test_route_weekday_filter(self):\n        rows = app.STORE.routes_from("PEK", membership="666", weekday="2")\n        self.assertTrue(rows)\n        for route in rows:\n            self.assertEqual(route["schedule"], "2")\n            self.assertTrue(all(__import__("datetime").date.fromisoformat(d).isoweekday() == 2 for d in route["operating_dates"]))\n\n    def test_city_overview_aggregates_origins(self):\n        rows = app.STORE.routes_from("北京", membership="all")\n        self.assertTrue(rows)\n        self.assertTrue(all(route["aggregate"] for route in rows))\n        seen_origins = set(code for route in rows for code in route["origin_codes"])\n        self.assertTrue({"PEK", "PKX"}.issubset(seen_origins))\n'''
    if "test_city_origin_resolution" not in text:
        if marker not in text:
            raise RuntimeError("test insertion marker not found")
        text = text.replace(marker, marker + extra)
    path.write_text(text, encoding="utf-8")


def update_gitignore():
    path = ROOT / ".gitignore"
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    for pattern in ("data/*.csv", "archive.b64", "archive.b64.*"):
        if pattern not in lines:
            lines.append(pattern)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main():
    update_app()
    for filename in ("templates/index.html", "public/index.html"):
        update_html(filename)
    for filename in ("static/app.js", "public/static/app.js"):
        update_js(filename)
    for filename in ("static/style.css", "public/static/style.css"):
        update_css(filename)
    update_readme()
    update_tests()
    update_gitignore()
    print("Release update applied.")


if __name__ == "__main__":
    main()
