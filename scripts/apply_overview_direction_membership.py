from pathlib import Path


def replace_once(text, old, new, label):
    if old not in text:
        raise SystemExit(f'pattern not found: {label}')
    return text.replace(old, new, 1)


# ---------- app.py ----------
p = Path('app.py')
text = p.read_text(encoding='utf-8')

text = replace_once(
    text,
    '''def product_for_departure(departure_time):\n    # 用户规则：666=08:00前或20:00后；2666=全天。\n    if departure_time and (departure_time < "08:00" or departure_time > "20:00"):\n        return "666/2666"\n    return "2666"\n''',
    '''def product_for_departure(departure_time):\n    # 666 是基础适用版本；2666 是父级版本，继承 666 并额外覆盖全天。\n    # 产品标签表示“最低适用版本”，因此不再使用 666/2666 这种并列写法。\n    if departure_time and (departure_time < "08:00" or departure_time > "20:00"):\n        return "666"\n    return "2666"\n''',
    'product hierarchy',
)

text = replace_once(
    text,
    '''        self.by_origin_sorted = defaultdict(list)\n        self.by_origin_times = defaultdict(list)\n''',
    '''        self.by_origin_sorted = defaultdict(list)\n        self.by_origin_times = defaultdict(list)\n        self.by_destination_sorted = defaultdict(list)\n''',
    'destination index init',
)
text = replace_once(
    text,
    '''        for flight in self.flights:\n            self.by_date_origin[(flight["departure_date"], flight["origin"])].append(flight)\n            self.by_origin_sorted[flight["origin"]].append(flight)\n''',
    '''        for flight in self.flights:\n            self.by_date_origin[(flight["departure_date"], flight["origin"])].append(flight)\n            self.by_origin_sorted[flight["origin"]].append(flight)\n            self.by_destination_sorted[flight["destination"]].append(flight)\n''',
    'destination index build',
)

text = replace_once(
    text,
    '''                "product": "666/2666" if all(s["product"] == "666/2666" for s in segments) else "2666",\n''',
    '''                "product": "666" if all(s["product"] == "666" for s in segments) else "2666",\n''',
    'itinerary product hierarchy',
)

start = text.index('    def routes_from(self, origin, membership="all", airline="", query="", weekday="", departure_period=""):\n')
end = text.index('\n\nSTORE = FlightStore(DB_FILE)', start)
new_methods = r'''    def routes_from(self, origin, membership="666", airline="", query="", weekday="", departure_period=""):
        return self._routes_by_location(
            origin, direction="departure", membership=membership, airline=airline,
            query=query, weekday=weekday, departure_period=departure_period,
        )

    def routes_to(self, destination, membership="666", airline="", query="", weekday="", departure_period=""):
        return self._routes_by_location(
            destination, direction="arrival", membership=membership, airline=airline,
            query=query, weekday=weekday, departure_period=departure_period,
        )

    def routes_overview(self, location, direction="departure", membership="666", airline="", query="",
                        weekday="", departure_period=""):
        direction = str(direction or "departure").strip().lower()
        if direction not in {"departure", "arrival", "roundtrip"}:
            direction = "departure"

        kwargs = dict(
            membership=membership, airline=airline, query=query,
            weekday=weekday, departure_period=departure_period,
        )
        if direction == "departure":
            return self.routes_from(location, **kwargs)
        if direction == "arrival":
            return self.routes_to(location, **kwargs)

        outbound = self.routes_from(location, **kwargs)
        inbound = self.routes_to(location, **kwargs)
        out_by_key = {row["_counterpart_key"]: row for row in outbound}
        in_by_key = {row["_counterpart_key"]: row for row in inbound}
        rows = []
        for key in sorted(set(out_by_key) & set(in_by_key)):
            out = out_by_key[key]
            back = in_by_key[key]
            rows.append({
                "direction": "roundtrip",
                "_counterpart_key": key,
                "counterpart_name": out["counterpart_name"],
                "counterpart_codes": sorted(set(out["counterpart_codes"]) | set(back["counterpart_codes"])),
                "aggregate": bool(out.get("aggregate") or back.get("aggregate")),
                "products": [membership] if membership in {"666", "2666"} else sorted(set(out["products"] + back["products"])),
                "outbound": out,
                "inbound": back,
            })
        rows.sort(key=lambda x: (x["counterpart_name"], "/".join(x["counterpart_codes"])))
        return rows

    def _routes_by_location(self, location, direction="departure", membership="666", airline="", query="",
                            weekday="", departure_period=""):
        selected_codes, selected_name, aggregate_mode = self.resolve_origins(location)
        if not selected_codes:
            return []

        direction = "arrival" if direction == "arrival" else "departure"
        q = (query or "").strip().lower()
        try:
            weekday_value = int(str(weekday).strip()) if str(weekday).strip() else None
        except (TypeError, ValueError):
            weekday_value = None
        if weekday_value not in {1, 2, 3, 4, 5, 6, 7}:
            weekday_value = None

        departure_period = str(departure_period or "").strip().lower()
        if departure_period not in {"morning", "evening"}:
            departure_period = ""

        groups = defaultdict(lambda: {
            "weekdays": set(),
            "dates": set(),
            "flight_records": [],
            "airlines": set(),
            "products": set(),
            "origins": set(),
            "destinations": set(),
            "airport_pairs": set(),
            "counterpart_codes": set(),
            "b_candidate_dates": set(),
            "b_visible_dates": set(),
            "running_only_dates": set(),
            "holiday_blocked_dates": set(),
            "date_flights": defaultdict(set),
        })

        for selected_code in selected_codes:
            source = (
                self.by_origin_sorted.get(selected_code, [])
                if direction == "departure"
                else self.by_destination_sorted.get(selected_code, [])
            )
            for f in source:
                if weekday_value and f["departure_dt"].weekday() + 1 != weekday_value:
                    continue
                if departure_period == "morning" and f["departure_time"] >= "08:00":
                    continue
                if departure_period == "evening" and f["departure_time"] < "20:00":
                    continue
                if not product_eligible(f["departure_time"], membership):
                    continue
                if airline and f["airline_code"] != airline:
                    continue

                counterpart_code = f["destination"] if direction == "departure" else f["origin"]
                counterpart_name_raw = f["destination_name"] if direction == "departure" else f["origin_name"]
                counterpart_city = self.city_by_airport.get(counterpart_code)
                if q:
                    haystack = " ".join([
                        counterpart_code, counterpart_name_raw, counterpart_city or "",
                        f["flight_no"], f["airline"], f["airline_code"],
                    ]).lower()
                    if q not in haystack:
                        continue

                if aggregate_mode and counterpart_city:
                    group_key = f"CITY:{counterpart_city}"
                    counterpart_name = counterpart_city
                else:
                    group_key = counterpart_code
                    counterpart_name = counterpart_name_raw

                g = groups[group_key]
                g["counterpart_name"] = counterpart_name
                g["counterpart_codes"].add(counterpart_code)
                g["weekdays"].add(f["departure_dt"].weekday() + 1)
                g["flight_records"].append(f)
                g["airlines"].add(f["airline"])
                g["products"].add(f["product"])
                g["origins"].add(f["origin"])
                g["destinations"].add(f["destination"])
                g["airport_pairs"].add((f["origin"], f["destination"]))

                blocked = f["holiday_blocked"] or ticket_blackout(f["departure_date"])
                if blocked:
                    g["holiday_blocked_dates"].add(f["departure_date"])
                    continue

                g["dates"].add(f["departure_date"])
                g["date_flights"][f["departure_date"]].add(f["flight_no"])

                if membership == "666":
                    b_candidate = f["eligible_666"]
                    b_visible = f["eligible_666"] and f["b_visible_raw"]
                elif membership == "2666":
                    b_candidate = f["eligible_2666"]
                    b_visible = f["eligible_2666"] and f["b_visible_raw"]
                else:
                    b_candidate = f["b_expected_or_seen"]
                    b_visible = f["b_visible_raw"] and f["b_expected_or_seen"]

                if b_candidate:
                    g["b_candidate_dates"].add(f["departure_date"])
                else:
                    g["running_only_dates"].add(f["departure_date"])
                if b_visible:
                    g["b_visible_dates"].add(f["departure_date"])

        out = []
        for group_key, g in groups.items():
            operating_dates = sorted(g["dates"])
            if not operating_dates:
                continue
            candidate_dates = sorted(g["b_candidate_dates"])
            visible_dates = sorted(g["b_visible_dates"])
            running_only_dates = sorted(g["running_only_dates"] - g["b_candidate_dates"])
            holiday_blocked_dates = sorted(g["holiday_blocked_dates"])
            schedule_rows = representative_schedule_rows(g["flight_records"], tolerance_minutes=30)
            destination_codes = sorted(g["destinations"])
            route_origin_codes = sorted(g["origins"])
            counterpart_codes = sorted(g["counterpart_codes"])

            products = [membership] if membership in {"666", "2666"} else sorted(g["products"])
            out.append({
                "direction": direction,
                "_counterpart_key": group_key,
                "counterpart_name": g["counterpart_name"],
                "counterpart_codes": counterpart_codes,
                "selected_name": selected_name,
                "selected_codes": list(selected_codes),
                "origin": "/".join(route_origin_codes),
                "origin_name": selected_name if direction == "departure" else g["counterpart_name"],
                "origin_codes": route_origin_codes,
                "destination": "/".join(destination_codes),
                "destination_codes": destination_codes,
                "destination_name": g["counterpart_name"] if direction == "departure" else selected_name,
                "aggregate": bool(aggregate_mode),
                "airport_pairs": [
                    {"origin": a, "destination": b}
                    for a, b in sorted(g["airport_pairs"])
                ],
                "schedule": "".join(str(x) for x in sorted(g["weekdays"])),
                "schedule_text": " ".join(f"周{WEEKDAY_CN[x]}" for x in sorted(g["weekdays"])),
                "schedule_rows": schedule_rows,
                "flight_nos": [row["flight_no"] for row in schedule_rows],
                "times": [
                    {
                        "departure_time": row["departure_time"],
                        "arrival_time": row["arrival_time"],
                        "cross_day": row["cross_day"],
                        "observations": row["observations"],
                        "merged_variants": row["merged_variants"],
                    }
                    for row in schedule_rows
                ],
                "airlines": sorted(g["airlines"]),
                "products": products,
                "flight_records_count": len(g["flight_records"]),
                "operating_days": len(operating_dates),
                "operating_dates": operating_dates,
                "b_candidate_dates": candidate_dates,
                "b_visible_dates": visible_dates,
                "running_only_dates": running_only_dates,
                "holiday_blocked_dates": holiday_blocked_dates,
                "date_flights": {
                    date: sorted(flights)
                    for date, flights in sorted(g["date_flights"].items())
                },
                "first_date": operating_dates[0],
                "last_date": operating_dates[-1],
                "data_start": self.date_min,
                "data_end": self.date_max,
                "weekday_filter": weekday_value or 0,
            })

        out.sort(key=lambda x: (x["counterpart_name"], "/".join(x["counterpart_codes"])))
        return out
'''
text = text[:start] + new_methods + text[end:]

old_handler = '''        if path == "/api/routes":\n            origin = one(qs, "origin").strip()\n            if not origin:\n                return self.send_json({"error": "origin 为必填项"}, 400)\n            origin_codes, origin_name, aggregate = STORE.resolve_origins(origin)\n            if not origin_codes:\n                return self.send_json({"error": "没有找到这个城市或机场"}, 400)\n            rows = STORE.routes_from(\n                origin,\n                membership=one(qs, "membership", "all"),\n                airline=one(qs, "airline").strip().upper(),\n                query=one(qs, "q"),\n                weekday=one(qs, "weekday"),\n                departure_period=one(qs, "departure_period"),\n            )\n            return self.send_json({\n                "origin": origin, "origin_name": origin_name, "origin_codes": origin_codes,\n                "aggregate": aggregate, "count": len(rows), "routes": rows\n            })\n'''
new_handler = '''        if path == "/api/routes":\n            location = one(qs, "location", one(qs, "origin")).strip()\n            if not location:\n                return self.send_json({"error": "location 为必填项"}, 400)\n            selected_codes, selected_name, aggregate = STORE.resolve_origins(location)\n            if not selected_codes:\n                return self.send_json({"error": "没有找到这个城市或机场"}, 400)\n            direction = one(qs, "direction", "departure").strip().lower()\n            if direction not in {"departure", "arrival", "roundtrip"}:\n                direction = "departure"\n            membership = one(qs, "membership", "666").strip()\n            if membership not in {"666", "2666"}:\n                membership = "666"\n            rows = STORE.routes_overview(\n                location, direction=direction, membership=membership,\n                airline=one(qs, "airline").strip().upper(),\n                query=one(qs, "q"),\n                weekday=one(qs, "weekday"),\n                departure_period=one(qs, "departure_period"),\n            )\n            return self.send_json({\n                "location": location, "selected_name": selected_name, "selected_codes": selected_codes,\n                "direction": direction, "membership": membership, "aggregate": aggregate,\n                "count": len(rows), "routes": rows\n            })\n'''
text = replace_once(text, old_handler, new_handler, 'routes handler')
p.write_text(text, encoding='utf-8')

# ---------- HTML (template + public mirror) ----------
for name in ('templates/index.html', 'public/index.html'):
    p = Path(name)
    text = p.read_text(encoding='utf-8')
    text = replace_once(
        text,
        '''      <nav class="main-tabs">\n        <button class="tab active" data-tab="searchPanel">航班搜索</button>\n        <button class="tab" data-tab="routesPanel">航线总览</button>\n      </nav>\n\n      <section id="searchPanel" class="panel active">''',
        '''      <nav class="main-tabs">\n        <button class="tab active" data-tab="routesPanel">航线总览</button>\n        <button class="tab" data-tab="searchPanel">航班搜索</button>\n      </nav>\n\n      <section id="searchPanel" class="panel">''',
        f'tab order {name}',
    )
    text = replace_once(text, '<section id="routesPanel" class="panel">', '<section id="routesPanel" class="panel active">', f'route default active {name}')
    text = replace_once(
        text,
        '''          <div class="search-grid overview-filter-grid">\n            <label class="field">\n              <span>出发城市 / 机场</span>\n              <select id="overviewOriginSelect"></select>\n            </label>\n            <label class="field">\n              <span>会员版本</span>\n              <select id="overviewMembership">\n                <option value="666" selected>666</option>\n                <option value="all">666/2666</option>\n              </select>\n            </label>''',
        '''          <div class="search-grid overview-filter-grid">\n            <label class="field">\n              <span>查询方向</span>\n              <select id="overviewDirection">\n                <option value="departure" selected>出发地</option>\n                <option value="arrival">到达地</option>\n                <option value="roundtrip">往返</option>\n              </select>\n            </label>\n            <label class="field">\n              <span id="overviewLocationLabel">出发城市 / 机场</span>\n              <select id="overviewOriginSelect"></select>\n            </label>\n            <label class="field">\n              <span>会员版本</span>\n              <select id="overviewMembership">\n                <option value="666" selected>666</option>\n                <option value="2666">2666</option>\n              </select>\n            </label>''',
        f'overview controls {name}',
    )
    text = replace_once(text, '<th>到达城市</th><th>机场</th>', '<th id="routeCounterpartHeader">到达城市</th><th>机场</th>', f'overview header {name}')
    p.write_text(text, encoding='utf-8')

# ---------- JavaScript ----------
for name in ('static/app.js', 'public/static/app.js'):
    p = Path(name)
    text = p.read_text(encoding='utf-8')

    text = replace_once(
        text,
        '''function routeCalendarHtml(route) {\n  const startText = route.data_start || META.date_min;''',
        '''function routeCalendarHtml(route) {\n  if (route?.direction === 'roundtrip' && route.outbound && route.inbound) {\n    return `\n      <div class="roundtrip-calendar-wrap">\n        <section class="roundtrip-calendar-side"><h4>去程</h4>${routeCalendarHtml(route.outbound)}</section>\n        <section class="roundtrip-calendar-side"><h4>返程</h4>${routeCalendarHtml(route.inbound)}</section>\n      </div>`;\n  }\n  const startText = route.data_start || META.date_min;''',
        f'roundtrip calendar {name}',
    )

    old_mobile = '''  const airportText = route.aggregate\n    ? `${(route.origin_codes || []).join('/')} → ${(route.destination_codes || []).join('/')}`\n    : `${route.origin || ''} → ${(route.destination_codes || [route.destination]).join('/')}`;\n  overlay.querySelector('.mobile-route-calendar-subtitle').textContent =\n    `${route.destination_name} · ${route.operating_days}天${airportText.trim() ? ` · ${airportText}` : ''}`;\n'''
    new_mobile = '''  if (route.direction === 'roundtrip' && route.outbound && route.inbound) {\n    overlay.querySelector('.mobile-route-calendar-subtitle').textContent =\n      `${route.counterpart_name} · 去${route.outbound.operating_days}天 / 返${route.inbound.operating_days}天`;\n  } else {\n    const airportText = `${(route.origin_codes || []).join('/')} → ${(route.destination_codes || []).join('/')}`;\n    overlay.querySelector('.mobile-route-calendar-subtitle').textContent =\n      `${route.counterpart_name || route.destination_name} · ${route.operating_days}天${airportText.trim() ? ` · ${airportText}` : ''}`;\n  }\n'''
    text = replace_once(text, old_mobile, new_mobile, f'mobile calendar subtitle {name}')

    start = text.index('async function loadOverview() {')
    end = text.index('\n\n\ndocument.addEventListener', start)
    new_load = r'''function updateOverviewDirectionUi() {
  const direction = $('overviewDirection')?.value || 'departure';
  const label = $('overviewLocationLabel');
  const header = $('routeCounterpartHeader');
  const picker = AIRPORT_PICKERS.overviewOriginSelect;
  if (direction === 'arrival') {
    if (label) label.textContent = '到达城市 / 机场';
    if (header) header.textContent = '出发城市';
    if (picker) picker.input.placeholder = '输入到达城市 / 机场 / 三字码';
  } else if (direction === 'roundtrip') {
    if (label) label.textContent = '城市 / 机场';
    if (header) header.textContent = '往返城市';
    if (picker) picker.input.placeholder = '输入城市 / 机场 / 三字码';
  } else {
    if (label) label.textContent = '出发城市 / 机场';
    if (header) header.textContent = '到达城市';
    if (picker) picker.input.placeholder = '输入出发城市 / 机场 / 三字码';
  }
}

function routeFlightTimePairs(route) {
  const rows = (route.schedule_rows || []).length
    ? route.schedule_rows
    : (route.flight_nos || []).map((flightNo, rowIndex) => ({
        flight_no: flightNo,
        departure_time: route.times?.[rowIndex]?.departure_time || '',
        arrival_time: route.times?.[rowIndex]?.arrival_time || '',
        cross_day: route.times?.[rowIndex]?.cross_day || 0,
      }));
  return `<div class="flight-time-pairs">${rows.map(row => `
    <div class="flight-time-pair">
      <strong class="flight-pair-no">${esc(row.flight_no)}</strong>
      <span class="flight-pair-time">${esc(row.departure_time)} → ${esc(row.arrival_time)}${row.cross_day ? ' +' + row.cross_day : ''}</span>
    </div>`).join('')}</div>`;
}

async function loadOverview() {
  const location = $('overviewOriginSelect').value.trim() || $('originSelect').value;
  if (!location) return;
  const direction = $('overviewDirection').value || 'departure';
  updateOverviewDirectionUi();
  const p = new URLSearchParams({
    location,
    direction,
    membership: $('overviewMembership').value,
    weekday: $('overviewWeekday').value,
    departure_period: $('overviewDeparturePeriod').value,
    airline: $('overviewAirline').value,
    q: $('overviewQuery').value.trim(),
  });
  if (overviewAbortController) overviewAbortController.abort();
  const controller = new AbortController();
  overviewAbortController = controller;
  $('routesTableBody').innerHTML = '<tr><td colspan="6">正在加载…</td></tr>';

  let r;
  try {
    r = await fetch('/api/routes?' + p.toString(), { signal: controller.signal });
  } catch (error) {
    if (error.name === 'AbortError') return;
    throw error;
  }
  if (overviewAbortController !== controller) return;
  overviewAbortController = null;
  const data = await r.json();
  if (!r.ok) {
    $('routesTableBody').innerHTML = `<tr><td colspan="6">${esc(data.error || '查询失败')}</td></tr>`;
    return;
  }
  $('routeCount').textContent = `${data.count} 条`;

  $('routesTableBody').innerHTML = data.routes.length ? data.routes.map((x, idx) => {
    const dateId = `route-dates-${idx}`;
    const isRoundtrip = x.direction === 'roundtrip';
    const counterpartName = x.counterpart_name || x.destination_name || x.origin_name;

    let airportText, flightTimeHtml, scheduleHtml, dateHtml, flightCountText, airlines, products;
    if (isRoundtrip) {
      const out = x.outbound;
      const back = x.inbound;
      airportText = `${(out.origin_codes || []).map(esc).join('/')} ⇄ ${(out.destination_codes || []).map(esc).join('/')}`;
      flightTimeHtml = `
        <div class="roundtrip-flight-times">
          <div class="roundtrip-direction-line"><span class="route-dir-badge">去</span>${routeFlightTimePairs(out)}</div>
          <div class="roundtrip-direction-line"><span class="route-dir-badge">返</span>${routeFlightTimePairs(back)}</div>
        </div>`;
      scheduleHtml = `<div class="roundtrip-schedule"><span><b>去</b> ${esc(out.schedule)}</span><span><b>返</b> ${esc(back.schedule)}</span></div>`;
      dateHtml = `
        <div class="route-days-line"><strong>去${out.operating_days} / 返${back.operating_days} 天</strong><button type="button" class="date-toggle-btn" data-target="${dateId}" data-route-index="${idx}" aria-expanded="false" title="展开具体日期">▶</button></div>
        <div class="sub">去 ${esc(out.first_date)} ~ ${esc(out.last_date)}</div>
        <div class="sub">返 ${esc(back.first_date)} ~ ${esc(back.last_date)}</div>`;
      flightCountText = `去${(out.flight_nos || []).length} / 返${(back.flight_nos || []).length}`;
      airlines = [...new Set([...(out.airlines || []), ...(back.airlines || [])])];
      products = x.products || [];
    } else {
      airportText = `${(x.origin_codes || []).map(esc).join('/')} → ${(x.destination_codes || []).map(esc).join('/')}`;
      flightTimeHtml = routeFlightTimePairs(x);
      scheduleHtml = `<strong>${esc(x.schedule)}</strong>`;
      dateHtml = `
        <div class="route-days-line"><strong>${x.operating_days} 天</strong><button type="button" class="date-toggle-btn" data-target="${dateId}" data-route-index="${idx}" aria-expanded="false" title="展开具体日期">▶</button></div>
        <div class="sub">${esc(x.first_date)} ~ ${esc(x.last_date)}</div>`;
      flightCountText = `${(x.flight_nos || []).length} 班`;
      airlines = x.airlines || [];
      products = x.products || [];
    }

    return `
      <tr class="route-main-row">
        <td class="dest"><div class="dest-title-line"><strong>${esc(counterpartName)}</strong><span class="route-flight-count">${esc(flightCountText)}</span></div><div class="sub">${airlines.map(esc).join(' / ')}</div></td>
        <td>${airportText}</td>
        <td class="flight-time-cell mono">${flightTimeHtml}</td>
        <td>${scheduleHtml}</td>
        <td>${dateHtml}</td>
        <td>${products.map(p => `<span class="tag product">${esc(p)}</span>`).join(' ')}</td>
      </tr>
      <tr class="route-date-row hidden" id="${dateId}">
        <td colspan="6">${routeCalendarHtml(x)}</td>
      </tr>`;
  }).join('') : '<tr><td colspan="6">没有匹配航线</td></tr>';

  $('routesTableBody').querySelectorAll('.date-toggle-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      if (window.matchMedia('(max-width: 640px)').matches) {
        const route = data.routes[Number(btn.dataset.routeIndex)];
        if (route) openMobileRouteCalendarSheet(route, btn);
        return;
      }
      const row = $(btn.dataset.target);
      if (!row) return;
      const opening = row.classList.contains('hidden');
      row.classList.toggle('hidden');
      btn.textContent = opening ? '▼' : '▶';
      btn.setAttribute('aria-expanded', opening ? 'true' : 'false');
      btn.title = opening ? '收起具体日期' : '展开具体日期';
    });
  });
}
'''
    text = text[:start] + new_load + text[end:]

    text = replace_once(
        text,
        '''  $('overviewBtn').addEventListener('click', loadOverview);\n  $('overviewOriginSelect').addEventListener('change', loadOverview);\n  $('overviewMembership').addEventListener('change', loadOverview);''',
        '''  $('overviewBtn').addEventListener('click', loadOverview);\n  $('overviewDirection').addEventListener('change', () => { updateOverviewDirectionUi(); loadOverview(); });\n  $('overviewOriginSelect').addEventListener('change', loadOverview);\n  $('overviewMembership').addEventListener('change', loadOverview);''',
        f'direction event {name}',
    )

    text = replace_once(
        text,
        '''  setDefaultAirports();\n  prewarmAirportPickers();\n  renderStats();\n  loadOverview();''',
        '''  setDefaultAirports();\n  updateOverviewDirectionUi();\n  prewarmAirportPickers();\n  renderStats();\n  loadOverview();''',
        f'direction init {name}',
    )
    p.write_text(text, encoding='utf-8')

# ---------- CSS ----------
css = r'''

/* overview direction / roundtrip presentation */
.overview-filter-grid { grid-template-columns:repeat(7,minmax(0,1fr)); }
.roundtrip-flight-times { display:flex; flex-direction:column; gap:5px; }
.roundtrip-direction-line {
  display:grid; grid-template-columns:24px minmax(0,1fr); align-items:center; gap:5px;
}
.route-dir-badge {
  display:inline-flex; align-items:center; justify-content:center;
  width:22px; height:22px; border-radius:6px;
  background:#f7ece9; color:var(--primary); font-size:10px; font-weight:800;
}
.roundtrip-direction-line + .roundtrip-direction-line { border-top:1px dashed #dccfc9; padding-top:5px; }
.roundtrip-direction-line .flight-time-pair + .flight-time-pair { border-top:1px dashed #eaded9; }
.roundtrip-schedule { display:flex; flex-direction:column; gap:4px; line-height:1.3; }
.roundtrip-schedule b { color:var(--primary); margin-right:3px; }
.roundtrip-calendar-wrap { display:grid; gap:14px; }
.roundtrip-calendar-side > h4 {
  margin:0; padding:8px 12px; border-bottom:1px solid #eaded9;
  color:var(--primary); background:#fffaf7; font-size:13px;
}
.roundtrip-calendar-side .route-date-panel { border-top:0; }
@media (max-width: 520px) {
  .overview-filter-grid { grid-template-columns:repeat(2,minmax(0,1fr)) !important; }
  .roundtrip-direction-line { grid-template-columns:20px minmax(0,1fr); gap:3px; }
  .route-dir-badge { width:19px; height:19px; font-size:9px; }
  .roundtrip-calendar-wrap { gap:8px; }
}
'''
for name in ('static/style.css', 'public/static/style.css'):
    p = Path(name)
    text = p.read_text(encoding='utf-8')
    marker = '/* overview direction / roundtrip presentation */'
    if marker not in text:
        text = text.rstrip() + css + '\n'
    p.write_text(text, encoding='utf-8')

# ---------- tests ----------
p = Path('tests/test_calendar_status.py')
t = p.read_text(encoding='utf-8')
insert = r'''
    def test_membership_hierarchy_labels(self):
        self.assertEqual(app.product_for_departure("06:55"), "666")
        self.assertEqual(app.product_for_departure("21:00"), "666")
        self.assertEqual(app.product_for_departure("12:00"), "2666")
        rows_666 = app.STORE.routes_from("PEK", membership="666")
        rows_2666 = app.STORE.routes_from("PEK", membership="2666")
        self.assertTrue(rows_666)
        self.assertTrue(rows_2666)
        self.assertTrue(all(row["products"] == ["666"] for row in rows_666))
        self.assertTrue(all(row["products"] == ["2666"] for row in rows_2666))

    def test_arrival_overview(self):
        rows = app.STORE.routes_overview("PEK", direction="arrival", membership="666")
        self.assertTrue(rows)
        self.assertTrue(all(row["direction"] == "arrival" for row in rows))
        self.assertTrue(all("PEK" in row["destination_codes"] for row in rows))

    def test_roundtrip_overview_requires_both_directions(self):
        rows = app.STORE.routes_overview("PEK", direction="roundtrip", membership="666")
        self.assertTrue(rows)
        for row in rows:
            self.assertEqual(row["direction"], "roundtrip")
            self.assertIn("outbound", row)
            self.assertIn("inbound", row)
            self.assertIn("PEK", row["outbound"]["origin_codes"])
            self.assertIn("PEK", row["inbound"]["destination_codes"])
            self.assertEqual(row["products"], ["666"])
'''
needle = '\n\nif __name__ == "__main__":\n'
if insert.strip() not in t:
    if needle not in t:
        raise SystemExit('test insertion point missing')
    t = t.replace(needle, '\n' + insert + needle, 1)
p.write_text(t, encoding='utf-8')

print('overview direction + membership patch applied')
