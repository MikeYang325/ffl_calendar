import json
import os
import sqlite3
import threading
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

DB_FILE = Path("/tmp/flights.db")
DB_URL = "https://calendar.lovefly.club/data/flights.db"

AIRLINE_MAP = {
    "HU": "海南航空", "GS": "天津航空", "JD": "首都航空", "PN": "西部航空",
    "UQ": "乌鲁木齐航空", "8L": "祥鹏航空", "9H": "长安航空", "CN": "大新华航空",
    "FU": "福州航空", "GX": "北部湾航空", "Y8": "金鹏航空",
}
CITY_AIRPORT_MAP = {
    "北京": ("PEK", "PKX"), "上海": ("SHA", "PVG"), "成都": ("CTU", "TFU"),
    "重庆": ("CKG", "WSK"), "遵义": ("ZYI", "WMT"), "东京": ("HND", "NRT"),
    "首尔": ("ICN", "GMP"), "大阪": ("KIX", "ITM"), "台北": ("TPE", "TSA"),
}
CITY_BY_AIRPORT = {code: city for city, codes in CITY_AIRPORT_MAP.items() for code in codes}
BLACKOUT_START = "2026-10-01"
BLACKOUT_END = "2026-10-08"


def download_file(url, path, min_size=1):
    if path.exists() and path.stat().st_size >= min_size:
        return
    tmp = Path(f"{path}.{os.getpid()}.{threading.get_ident()}.download")
    try:
        with urllib.request.urlopen(url, timeout=60) as response, tmp.open("wb") as out:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                out.write(chunk)
        if path.exists() and path.stat().st_size >= min_size:
            return
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)


def ensure_db():
    download_file(DB_URL, DB_FILE, 1024 * 1024)
    with DB_FILE.open("rb") as source:
        if source.read(16) != b"SQLite format 3\x00":
            DB_FILE.unlink(missing_ok=True)
            raise RuntimeError("flights.db 不是有效 SQLite 文件")


def one(qs, key, default=""):
    values = qs.get(key)
    return values[0] if values else default


def parse_dt(date_text, time_text):
    return datetime.strptime(f"{date_text} {time_text}", "%Y-%m-%d %H:%M")


def product_eligible(departure_time, membership):
    if membership == "666":
        return departure_time < "08:00" or departure_time > "20:00"
    return True


def product_for_departure(departure_time):
    return "666" if departure_time < "08:00" or departure_time > "20:00" else "2666"


def is_blocked(row):
    date = row["departure_date"]
    return bool(row["holiday_blocked"]) or BLACKOUT_START <= date <= BLACKOUT_END


def minutes_text(minutes):
    minutes = int(minutes or 0)
    h, m = divmod(minutes, 60)
    if h and m:
        return f"{h}小时{m}分"
    if h:
        return f"{h}小时"
    return f"{m}分"


def pinyin_initial(text):
    text = str(text or "").strip()
    if not text:
        return "#"
    ch = text[0].upper()
    if "A" <= ch <= "Z":
        return ch
    try:
        gb = ch.encode("gbk")
        code = gb[0] * 256 + gb[1] - 65536
    except Exception:
        return "#"
    ranges = [
        (-20319, "A"), (-20283, "B"), (-19775, "C"), (-19218, "D"), (-18710, "E"),
        (-18526, "F"), (-18239, "G"), (-17922, "H"), (-17417, "J"), (-16474, "K"),
        (-16212, "L"), (-15640, "M"), (-15165, "N"), (-14922, "O"), (-14914, "P"),
        (-14630, "Q"), (-14149, "R"), (-14090, "S"), (-13318, "T"), (-12838, "W"),
        (-12556, "X"), (-11847, "Y"), (-11055, "Z"),
    ]
    for i in range(len(ranges) - 1):
        if ranges[i][0] <= code < ranges[i + 1][0]:
            return ranges[i][1]
    return ranges[-1][1] if code >= ranges[-1][0] else "#"


def airport_map(conn):
    rows = conn.execute("""
        SELECT code, MAX(name) FROM (
            SELECT origin AS code, origin_name AS name FROM flights
            UNION ALL
            SELECT destination AS code, destination_name AS name FROM flights
        ) GROUP BY code
    "").fetchall()
    return {code: name for code, name in rows}


def resolve_location(conn, value):
    raw = str(value or "").strip()
    airports = airport_map(conn)
    upper = raw.upper()
    if upper in airports:
        return [upper], airports[upper], False, airports
    if raw in CITY_AIRPORT_MAP:
        codes = [c for c in CITY_AIRPORT_MAP[raw] if c in airports]
        if codes:
            return codes, raw, len(codes) > 1, airports
    matched = sorted(code for code, name in airports.items() if raw and raw.lower() in str(name).lower())
    if matched:
        return matched, raw, len(matched) > 1, airports
    return [], raw, False, airports


def load_meta():
    ensure_db()
    with sqlite3.connect(DB_FILE) as conn:
        date_min, date_max, flight_records, route_count = conn.execute("""
            SELECT MIN(departure_date), MAX(departure_date), COUNT(*),
                   COUNT(DISTINCT origin || '>' || destination)
            FROM flights
        """).fetchone()
        airports_dict = airport_map(conn)
        airline_codes = [row[0] for row in conn.execute(
            "SELECT DISTINCT SUBSTR(flight_no,1,2) FROM flights WHERE flight_no <> '' ORDER BY 1"
        )]

    airports = []
    for code, name in airports_dict.items():
        initial = pinyin_initial(name)
        airports.append({"code": code, "name": name, "initial": initial,
                         "label": f"{name} {code}", "search": f"{name} {code} {initial}".upper()})
    airports.sort(key=lambda x: (x["initial"], x["name"], x["code"]))
    airlines = [{"code": c, "name": AIRLINE_MAP.get(c, c), "label": f"{AIRLINE_MAP.get(c, c)} {c}"}
                for c in airline_codes if c]
    cities = []
    for city, codes in sorted(CITY_AIRPORT_MAP.items()):
        present = [c for c in codes if c in airports_dict]
        if len(present) >= 2:
            cities.append({"name": city, "codes": present, "label": f"{city}（{'/'.join(present)}）"})
    return {
        "date_min": date_min or "", "date_max": date_max or "",
        "flight_records": int(flight_records or 0), "route_count": int(route_count or 0),
        "airport_count": len(airports), "airports": airports, "airlines": airlines, "cities": cities,
        "membership_rules": {"666": "08:00前或20:00后出发", "2666": "全天覆盖"},
    }


def representative_schedule_rows(rows, tolerance=30):
    by_no = defaultdict(list)
    for r in rows:
        dep = r["departure_time"]
        arr = r["arrival_time"]
        cross = (datetime.strptime(r["arrival_date"], "%Y-%m-%d").date() -
                 datetime.strptime(r["departure_date"], "%Y-%m-%d").date()).days
        by_no[r["flight_no"]].append((dep, arr, cross))
    output = []
    for flight_no in sorted(by_no):
        counts = Counter(by_no[flight_no])
        remaining = set(counts)
        while remaining:
            seed = max(remaining, key=lambda x: counts[x])
            sh, sm = map(int, seed[0].split(':'))
            ah, am = map(int, seed[1].split(':'))
            seed_dep = sh * 60 + sm
            seed_arr = ah * 60 + am + seed[2] * 1440
            cluster = []
            for variant in remaining:
                dh, dm = map(int, variant[0].split(':'))
                vh, vm = map(int, variant[1].split(':'))
                dep = dh * 60 + dm
                arr = vh * 60 + vm + variant[2] * 1440
                if abs(dep - seed_dep) <= tolerance and abs(arr - seed_arr) <= tolerance:
                    cluster.append(variant)
            rep = max(cluster, key=lambda x: counts[x])
            output.append({"flight_no": flight_no, "departure_time": rep[0], "arrival_time": rep[1],
                           "cross_day": rep[2], "observations": sum(counts[x] for x in cluster),
                           "merged_variants": len(cluster)})
            remaining.difference_update(cluster)
    output.sort(key=lambda x: (x["departure_time"], x["flight_no"]))
    return output


def route_rows(conn, location, direction, membership, airline, query, weekday, departure_period):
    selected, selected_name, aggregate, airports = resolve_location(conn, location)
    if not selected:
        return [], selected_name, selected, aggregate
    direction = "arrival" if direction == "arrival" else "departure"
    column = "destination" if direction == "arrival" else "origin"
    placeholders = ",".join("?" for _ in selected)
    sql = f"""
        SELECT origin, origin_name, destination, destination_name, flight_no,
               departure_date, departure_time, arrival_date, arrival_time,
               holiday_blocked
        FROM flights WHERE {column} IN ({placeholders})
    """
    params = list(selected)
    if membership == "666":
        sql += " AND (departure_time < '08:00' OR departure_time > '20:00')"
    if airline:
        sql += " AND SUBSTR(flight_no,1,2)=?"
        params.append(airline)
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute(sql, params)]

    try:
        weekday_value = int(weekday) if weekday else 0
    except ValueError:
        weekday_value = 0
    q = str(query or "").strip().lower()
    groups = defaultdict(lambda: {
        "rows": [], "dates": set(), "weekdays": set(), "origins": set(), "destinations": set(),
        "counterpart_codes": set(), "airlines": set(), "date_flights": defaultdict(set)
    })
    for r in rows:
        wd = datetime.strptime(r["departure_date"], "%Y-%m-%d").isoweekday()
        if weekday_value and wd != weekday_value:
            continue
        if departure_period == "morning" and r["departure_time"] >= "08:00":
            continue
        if departure_period == "evening" and r["departure_time"] < "20:00":
            continue
        counterpart = r["origin"] if direction == "arrival" else r["destination"]
        counterpart_name_raw = r["origin_name"] if direction == "arrival" else r["destination_name"]
        counterpart_city = CITY_BY_AIRPORT.get(counterpart)
        if q:
            haystack = " ".join([counterpart, counterpart_name_raw, counterpart_city or "", r["flight_no"],
                                 AIRLINE_MAP.get(r["flight_no"][:2], r["flight_no"][:2])]).lower()
            if q not in haystack:
                continue
        key = f"CITY:{counterpart_city}" if aggregate and counterpart_city else counterpart
        g = groups[key]
        g["counterpart_name"] = counterpart_city if aggregate and counterpart_city else counterpart_name_raw
        g["counterpart_codes"].add(counterpart)
        g["rows"].append(r)
        g["weekdays"].add(wd)
        g["origins"].add(r["origin"])
        g["destinations"].add(r["destination"])
        g["airlines"].add(AIRLINE_MAP.get(r["flight_no"][:2], r["flight_no"][:2]))
        if not is_blocked(r):
            g["dates"].add(r["departure_date"])
            g["date_flights"][r["departure_date"]].add(r["flight_no"])

    data_min, data_max = conn.execute("SELECT MIN(departure_date),MAX(departure_date) FROM flights").fetchone()
    out = []
    for key, g in groups.items():
        dates = sorted(g["dates"])
        if not dates:
            continue
        schedule_rows = representative_schedule_rows(g["rows"])
        out.append({
            "direction": direction, "_counterpart_key": key,
            "counterpart_name": g["counterpart_name"], "counterpart_codes": sorted(g["counterpart_codes"]),
            "selected_name": selected_name, "selected_codes": selected,
            "origin": "/".join(sorted(g["origins"])), "origin_codes": sorted(g["origins"]),
            "destination": "/".join(sorted(g["destinations"])), "destination_codes": sorted(g["destinations"]),
            "aggregate": aggregate,
            "schedule": "".join(str(x) for x in sorted(g["weekdays"])),
            "schedule_rows": schedule_rows, "flight_nos": [x["flight_no"] for x in schedule_rows],
            "times": [{"departure_time": x["departure_time"], "arrival_time": x["arrival_time"],
                       "cross_day": x["cross_day"]} for x in schedule_rows],
            "airlines": sorted(g["airlines"]), "products": [membership],
            "operating_days": len(dates), "operating_dates": dates,
            "date_flights": {d: sorted(v) for d, v in sorted(g["date_flights"].items())},
            "first_date": dates[0], "last_date": dates[-1], "data_start": data_min, "data_end": data_max,
            "weekday_filter": weekday_value,
        })
    out.sort(key=lambda x: (x["counterpart_name"], "/".join(x["counterpart_codes"])))
    return out, selected_name, selected, aggregate


def routes_api(qs):
    ensure_db()
    location = one(qs, "location", one(qs, "origin")).strip()
    if not location:
        return {"error": "location 为必填项"}, 400
    direction = one(qs, "direction", "departure").strip().lower()
    if direction not in {"departure", "arrival", "roundtrip"}:
        direction = "departure"
    membership = one(qs, "membership", "666").strip()
    if membership not in {"666", "2666"}:
        membership = "666"
    with sqlite3.connect(DB_FILE) as conn:
        kwargs = (membership, one(qs, "airline").strip().upper(), one(qs, "q"),
                  one(qs, "weekday"), one(qs, "departure_period"))
        if direction != "roundtrip":
            rows, selected_name, selected, aggregate = route_rows(conn, location, direction, *kwargs)
        else:
            outbound, selected_name, selected, aggregate = route_rows(conn, location, "departure", *kwargs)
            inbound, _, _, _ = route_rows(conn, location, "arrival", *kwargs)
            out_map = {r["_counterpart_key"]: r for r in outbound}
            in_map = {r["_counterpart_key"]: r for r in inbound}
            rows = []
            for key in sorted(set(out_map) & set(in_map)):
                a, b = out_map[key], in_map[key]
                rows.append({"direction": "roundtrip", "_counterpart_key": key,
                             "counterpart_name": a["counterpart_name"],
                             "counterpart_codes": sorted(set(a["counterpart_codes"] + b["counterpart_codes"])),
                             "aggregate": aggregate, "products": [membership], "outbound": a, "inbound": b})
    if not selected:
        return {"error": "没有找到这个城市或机场"}, 400
    return {"location": location, "selected_name": selected_name, "selected_codes": selected,
            "direction": direction, "membership": membership, "aggregate": aggregate,
            "count": len(rows), "routes": rows}, 200


def flight_from_row(r):
    dep_dt = parse_dt(r["departure_date"], r["departure_time"])
    arr_dt = parse_dt(r["arrival_date"], r["arrival_time"])
    code = r["flight_no"][:2]
    return {
        "origin": r["origin"], "origin_name": r["origin_name"],
        "destination": r["destination"], "destination_name": r["destination_name"],
        "flight_no": r["flight_no"], "operating_flight_no": r["operating_flight_no"],
        "departure_date": r["departure_date"], "departure_time": r["departure_time"],
        "arrival_date": r["arrival_date"], "arrival_time": r["arrival_time"],
        "duration_minutes": int(r["duration_minutes"] or 0),
        "duration_text": minutes_text(r["duration_minutes"]), "aircraft": r["aircraft"],
        "code_share": bool(r["code_share"]), "stop_quantity": int(r["stop_quantity"] or 0),
        "airline_code": code, "airline": AIRLINE_MAP.get(code, code),
        "product": product_for_departure(r["departure_time"]),
        "cross_day": (arr_dt.date() - dep_dt.date()).days,
        "departure_dt": dep_dt, "arrival_dt": arr_dt,
        "holiday_blocked": bool(r["holiday_blocked"]),
    }


def search_api(qs):
    ensure_db()
    origin = one(qs, "origin").strip().upper()
    destination = one(qs, "destination").strip().upper()
    date = one(qs, "date").strip()
    if not origin or not destination or not date:
        return {"error": "origin、destination、date 为必填项"}, 400
    membership = one(qs, "membership", "all").strip()
    airline = one(qs, "airline").strip().upper()
    flight_no = one(qs, "flight_no").strip().upper()
    try:
        max_stops = max(0, min(2, int(one(qs, "max_stops", "0"))))
    except ValueError:
        max_stops = 0
    start_date = datetime.strptime(date, "%Y-%m-%d")
    end_date = (start_date + timedelta(days=3)).strftime("%Y-%m-%d")

    with sqlite3.connect(DB_FILE) as conn:
        conn.row_factory = sqlite3.Row
        data_min, data_max = conn.execute("SELECT MIN(departure_date),MAX(departure_date) FROM flights").fetchone()
        if date < data_min or date > data_max:
            return {"error": f"日期超出数据范围 {data_min} ~ {data_max}"}, 400
        rows = conn.execute("""
            SELECT origin,origin_name,destination,destination_name,flight_no,operating_flight_no,
                   departure_date,departure_time,arrival_date,arrival_time,duration_minutes,aircraft,
                   code_share,stop_quantity,holiday_blocked
            FROM flights WHERE departure_date >= ? AND departure_date <= ?
            ORDER BY departure_date, departure_time
        """, (date, end_date)).fetchall()

    flights = []
    for row in rows:
        f = flight_from_row(row)
        if is_blocked(f):
            continue
        if not product_eligible(f["departure_time"], membership):
            continue
        if airline and f["airline_code"] != airline:
            continue
        if flight_no and flight_no not in f["flight_no"]:
            continue
        flights.append(f)
    by_origin = defaultdict(list)
    for f in flights:
        by_origin[f["origin"]].append(f)

    first_legs = [f for f in by_origin.get(origin, []) if f["departure_date"] == date]
    itineraries, seen = [], set()

    def add(segments):
        if segments[-1]["destination"] != destination:
            return
        total = int((segments[-1]["arrival_dt"] - segments[0]["departure_dt"]).total_seconds() // 60)
        if total < 0 or total > 2880:
            return
        key = tuple((s["flight_no"], s["departure_date"], s["departure_time"]) for s in segments)
        if key in seen:
            return
        seen.add(key)
        itineraries.append({"segments": segments, "stops": len(segments)-1,
                            "total_minutes": total, "total_text": minutes_text(total),
                            "departure_dt": segments[0]["departure_dt"], "arrival_dt": segments[-1]["arrival_dt"],
                            "product": "666" if all(s["product"] == "666" for s in segments) else "2666"})

    def connections(f):
        lo = f["arrival_dt"] + timedelta(minutes=60)
        hi = f["arrival_dt"] + timedelta(minutes=1440)
        return [x for x in by_origin.get(f["destination"], []) if lo <= x["departure_dt"] <= hi]

    for first in first_legs:
        if first["destination"] == destination:
            add([first])
        if max_stops < 1 or first["destination"] == destination:
            continue
        for second in connections(first):
            if second["destination"] == origin:
                continue
            if second["destination"] == destination:
                add([first, second])
            if max_stops < 2 or second["destination"] in {origin, first["destination"], destination}:
                continue
            for third in connections(second):
                if third["destination"] == destination:
                    add([first, second, third])
                    if len(itineraries) >= 360:
                        break

    sort = one(qs, "sort", "departure")
    if sort == "arrival":
        itineraries.sort(key=lambda x: (x["arrival_dt"], x["stops"], x["total_minutes"]))
    elif sort == "duration":
        itineraries.sort(key=lambda x: (x["total_minutes"], x["stops"], x["departure_dt"]))
    elif sort == "stops":
        itineraries.sort(key=lambda x: (x["stops"], x["total_minutes"], x["departure_dt"]))
    else:
        itineraries.sort(key=lambda x: (x["departure_dt"], x["stops"], x["total_minutes"]))

    def public_segment(s):
        return {k: v for k, v in s.items() if k not in {"departure_dt", "arrival_dt", "holiday_blocked"}}
    results = [{"segments": [public_segment(s) for s in x["segments"]], "stops": x["stops"],
                "total_minutes": x["total_minutes"], "total_text": x["total_text"], "product": x["product"]}
               for x in itineraries[:120]]
    return {"origin": origin, "destination": destination, "date": date,
            "count": len(results), "results": results}, 200


class handler(BaseHTTPRequestHandler):
    def send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        path, qs = parsed.path, parse_qs(parsed.query)
        try:
            if path == "/api/meta":
                return self.send_json(load_meta())
            if path == "/api/routes":
                data, status = routes_api(qs)
                return self.send_json(data, status)
            if path == "/api/search":
                data, status = search_api(qs)
                return self.send_json(data, status)
            if path == "/api/health":
                ensure_db()
                with sqlite3.connect(DB_FILE) as conn:
                    records = conn.execute("SELECT COUNT(*) FROM flights").fetchone()[0]
                return self.send_json({"ok": True, "database": str(DB_FILE), "records": records})
            return self.send_json({"error": "not found"}, 404)
        except Exception as exc:
            return self.send_json({"error": str(exc)}, 500)
