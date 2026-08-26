#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import csv
import json
import mimetypes
import os
from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

BASE_DIR = Path(__file__).resolve().parent
DATA_FILE = Path(os.environ.get("HNA_FLIGHT_CSV", BASE_DIR / "data" / "flight_daily.csv"))

AIRLINE_MAP = {
    "HU": "海南航空", "GS": "天津航空", "JD": "首都航空", "PN": "西部航空",
    "UQ": "乌鲁木齐航空", "8L": "祥鹏航空", "9H": "长安航空", "CN": "大新华航空",
    "FU": "福州航空", "GX": "北部湾航空", "Y8": "金鹏航空",
}
WEEKDAY_CN = {1: "一", 2: "二", 3: "三", 4: "四", 5: "五", 6: "六", 7: "日"}


def pinyin_initial(text):
    """返回中文城市名的拼音首字母，用于前端机场选择器分组。"""
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


def parse_datetime(date_text, time_text):
    return datetime.strptime(f"{date_text} {time_text}", "%Y-%m-%d %H:%M")


def airline_code(flight_no):
    return str(flight_no or "")[:2]


def product_for_departure(departure_time):
    # 用户规则：666=08:00前或20:00后；2666=全天。
    if departure_time and (departure_time < "08:00" or departure_time > "20:00"):
        return "666/2666"
    return "2666"


def product_eligible(departure_time, membership):
    if membership in ("", "all", "2666"):
        return True
    if membership == "666":
        return departure_time < "08:00" or departure_time > "20:00"
    return True




def _time_minutes(value):
    value = str(value or "").strip()
    if not value or ":" not in value:
        return -1
    try:
        hour, minute = value[:5].split(":", 1)
        hour, minute = int(hour), int(minute)
    except (TypeError, ValueError):
        return -1
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return -1
    return hour * 60 + minute


def _arrival_clock_minutes(arrival_time, cross_day):
    minutes = _time_minutes(arrival_time)
    if minutes < 0:
        return minutes
    return minutes + int(cross_day or 0) * 1440


def representative_schedule_rows(flights, tolerance_minutes=30):
    """
    将同一航班号的轻微时刻变化合并。

    - 先按航班号分组；
    - 完全相同的起降时刻先计数；
    - 以出现次数最多的时刻作为聚类中心；
    - 起飞、到达时刻均在 tolerance_minutes 内的变体归为同一簇；
    - 每簇只展示出现次数最多的主时刻；
    - 若同一航班号存在相差明显的大时段（> tolerance），仍保留为独立时刻。

    返回的 flight_no/times 一一对应，避免原先航班号与时刻列错位。
    """
    by_flight = defaultdict(list)
    for flight in flights:
        by_flight[flight["flight_no"]].append(flight)

    display_rows = []
    for flight_no in sorted(by_flight):
        counts = Counter(
            (f["departure_time"], f["arrival_time"], int(f.get("cross_day") or 0))
            for f in by_flight[flight_no]
        )
        remaining = set(counts)
        reps = []

        while remaining:
            seed = min(
                remaining,
                key=lambda v: (
                    -counts[v],
                    _time_minutes(v[0]),
                    _arrival_clock_minutes(v[1], v[2]),
                    v,
                ),
            )
            seed_dep = _time_minutes(seed[0])
            seed_arr = _arrival_clock_minutes(seed[1], seed[2])

            cluster = []
            for variant in remaining:
                dep = _time_minutes(variant[0])
                arr = _arrival_clock_minutes(variant[1], variant[2])
                if dep < 0 or arr < 0 or seed_dep < 0 or seed_arr < 0:
                    same = variant == seed
                else:
                    same = (
                        abs(dep - seed_dep) <= tolerance_minutes
                        and abs(arr - seed_arr) <= tolerance_minutes
                    )
                if same:
                    cluster.append(variant)

            representative = min(
                cluster,
                key=lambda v: (
                    -counts[v],
                    _time_minutes(v[0]),
                    _arrival_clock_minutes(v[1], v[2]),
                    v,
                ),
            )
            total_observations = sum(counts[v] for v in cluster)
            reps.append((representative, total_observations, len(cluster)))
            remaining.difference_update(cluster)

        reps.sort(key=lambda item: (
            _time_minutes(item[0][0]),
            _arrival_clock_minutes(item[0][1], item[0][2]),
        ))
        for (departure_time, arrival_time, cross_day), observations, variant_count in reps:
            display_rows.append({
                "flight_no": flight_no,
                "departure_time": departure_time,
                "arrival_time": arrival_time,
                "cross_day": cross_day,
                "observations": observations,
                "merged_variants": variant_count,
            })

    return display_rows

def minutes_text(minutes):
    minutes = int(minutes or 0)
    h, m = divmod(minutes, 60)
    if h and m:
        return f"{h}小时{m}分"
    if h:
        return f"{h}小时"
    return f"{m}分"


def csv_bool(value):
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "t", "✓"}


class FlightStore:
    def __init__(self, csv_path):
        self.csv_path = Path(csv_path)
        self.flights = []
        self.by_date_origin = defaultdict(list)
        self.by_origin_sorted = defaultdict(list)
        self.by_origin_times = defaultdict(list)
        self.airports = {}
        self.airlines = {}
        self.date_min = ""
        self.date_max = ""
        self.route_overview = {}
        self.load()

    def load(self):
        if not self.csv_path.exists():
            raise FileNotFoundError(f"找不到数据文件：{self.csv_path}")

        raw, dates, seen = [], [], set()
        with self.csv_path.open("r", encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                origin = (row.get("origin") or row.get("departure_airport") or "").strip().upper()
                destination = (row.get("destination") or row.get("arrival_airport") or "").strip().upper()
                dep_date = (row.get("departure_date") or row.get("query_date") or "").strip()
                dep_time = (row.get("departure_time") or "").strip()
                arr_date = (row.get("arrival_date") or dep_date).strip()
                arr_time = (row.get("arrival_time") or "").strip()
                flight_no = (row.get("flight_no") or "").strip().upper()
                if not all([origin, destination, dep_date, dep_time, arr_date, arr_time, flight_no]):
                    continue

                dedupe = (origin, destination, flight_no, dep_date, dep_time, arr_date, arr_time)
                if dedupe in seen:
                    continue
                seen.add(dedupe)

                try:
                    dep_dt = parse_datetime(dep_date, dep_time)
                    arr_dt = parse_datetime(arr_date, arr_time)
                except ValueError:
                    continue

                origin_name = (row.get("origin_name") or row.get("departure_city") or origin).strip()
                destination_name = (row.get("destination_name") or row.get("arrival_city") or destination).strip()
                code = airline_code(flight_no)
                try:
                    duration = int(float(row.get("duration_minutes") or 0))
                except Exception:
                    duration = int((arr_dt - dep_dt).total_seconds() // 60)

                flight = {
                    "origin": origin,
                    "origin_name": origin_name,
                    "destination": destination,
                    "destination_name": destination_name,
                    "flight_no": flight_no,
                    "operating_flight_no": (row.get("operating_flight_no") or flight_no).strip().upper(),
                    "airline_code": code,
                    "airline": AIRLINE_MAP.get(code, code),
                    "departure_date": dep_date,
                    "departure_time": dep_time,
                    "arrival_date": arr_date,
                    "arrival_time": arr_time,
                    "departure_dt": dep_dt,
                    "arrival_dt": arr_dt,
                    "duration_minutes": duration,
                    "duration_text": minutes_text(duration),
                    "aircraft": (row.get("aircraft") or "").strip(),
                    "code_share": str(row.get("code_share") or "").lower() == "true",
                    "stop_quantity": int(float(row.get("stop_quantity") or 0)),
                    "product": product_for_departure(dep_time),
                    "cross_day": (arr_dt.date() - dep_dt.date()).days,

                    # 新 flight_daily.csv 的 B 舱 / 规则状态。
                    # 这里只给日历使用，不改变原页面其他查询和布局。
                    "flight_running": csv_bool(row.get("flight_running", True)),
                    "b_status": (row.get("b_status") or "").strip(),
                    "b_expected_or_seen": csv_bool(row.get("b_expected_or_seen")),
                    "b_visible_raw": csv_bool(row.get("b_visible_raw")),
                    "holiday_blocked": csv_bool(row.get("holiday_blocked")),
                    "status_666": (row.get("status_666") or "").strip(),
                    "eligible_666": csv_bool(row.get("eligible_666")),
                    "status_2666": (row.get("status_2666") or "").strip(),
                    "eligible_2666": csv_bool(row.get("eligible_2666")),
                }
                raw.append(flight)
                dates.append(dep_date)
                self.airports[origin] = origin_name
                self.airports[destination] = destination_name
                self.airlines[code] = AIRLINE_MAP.get(code, code)

        raw.sort(key=lambda x: x["departure_dt"])
        self.flights = raw
        if dates:
            self.date_min, self.date_max = min(dates), max(dates)

        for flight in self.flights:
            self.by_date_origin[(flight["departure_date"], flight["origin"])].append(flight)
            self.by_origin_sorted[flight["origin"]].append(flight)

        for origin, flights in self.by_origin_sorted.items():
            flights.sort(key=lambda x: x["departure_dt"])
            self.by_origin_times[origin] = [f["departure_dt"] for f in flights]

        self._build_route_overview()

    def _build_route_overview(self):
        groups = defaultdict(lambda: {
            "weekdays": set(), "dates": set(), "flight_nos": set(), "times": set(),
            "airlines": set(), "products": set()
        })
        for f in self.flights:
            g = groups[(f["origin"], f["destination"])]
            g["weekdays"].add(f["departure_dt"].weekday() + 1)
            g["dates"].add(f["departure_date"])
            g["flight_nos"].add(f["flight_no"])
            g["times"].add((f["departure_time"], f["arrival_time"], f["cross_day"]))
            g["airlines"].add(f["airline"])
            g["products"].add(f["product"])

        overview = defaultdict(list)
        for (origin, destination), g in groups.items():
            overview[origin].append({
                "origin": origin,
                "origin_name": self.airports.get(origin, origin),
                "destination": destination,
                "destination_name": self.airports.get(destination, destination),
                "schedule": "".join(str(x) for x in sorted(g["weekdays"])),
                "schedule_text": " ".join(f"周{WEEKDAY_CN[x]}" for x in sorted(g["weekdays"])),
                "flight_nos": sorted(g["flight_nos"]),
                "times": [{"departure_time": d, "arrival_time": a, "cross_day": c} for d, a, c in sorted(g["times"])],
                "airlines": sorted(g["airlines"]),
                "products": sorted(g["products"]),
                "operating_days": len(g["dates"]),
                "first_date": min(g["dates"]),
                "last_date": max(g["dates"]),
            })
        for origin in overview:
            overview[origin].sort(key=lambda x: (x["destination_name"], x["destination"]))
        self.route_overview = dict(overview)

    def meta(self):
        airports = []
        for c, n in self.airports.items():
            initial = pinyin_initial(n)
            airports.append({
                "code": c,
                "name": n,
                "initial": initial,
                "label": f"{n} {c}",
                "search": f"{n} {c} {initial}".upper(),
            })
        airports.sort(key=lambda x: (x["initial"], x["name"], x["code"]))
        airlines = [{"code": c, "name": n, "label": f"{n} {c}"} for c, n in sorted(self.airlines.items(), key=lambda x: (x[1], x[0]))]
        return {
            "date_min": self.date_min,
            "date_max": self.date_max,
            "flight_records": len(self.flights),
            "route_count": len({(f["origin"], f["destination"]) for f in self.flights}),
            "airport_count": len(self.airports),
            "airports": airports,
            "airlines": airlines,
            "membership_rules": {"666": "08:00前或20:00后出发", "2666": "全天覆盖"},
        }

    @staticmethod
    def _basic_filter(f, membership="all", airline="", flight_no=""):
        if not product_eligible(f["departure_time"], membership):
            return False
        if airline and f["airline_code"] != airline:
            return False
        if flight_no and flight_no.upper() not in f["flight_no"]:
            return False
        return True

    def _departures_between(self, origin, start_dt, end_dt, membership, airline, flight_no):
        flights = self.by_origin_sorted.get(origin, [])
        times = self.by_origin_times.get(origin, [])
        if not flights:
            return []
        left, right = bisect_left(times, start_dt), bisect_right(times, end_dt)
        return [f for f in flights[left:right] if self._basic_filter(f, membership, airline, flight_no)]

    def search_itineraries(self, origin, destination, date, membership="all", airline="", flight_no="",
                           max_stops=0, min_connect_minutes=60, max_connect_minutes=1440,
                           max_total_minutes=2880, max_results=120):
        if origin == destination:
            return []
        first_legs = [
            f for f in self.by_date_origin.get((date, origin), [])
            if self._basic_filter(f, membership, airline, flight_no)
        ]
        itineraries, seen = [], set()

        def add(segments):
            if segments[-1]["destination"] != destination:
                return
            total = int((segments[-1]["arrival_dt"] - segments[0]["departure_dt"]).total_seconds() // 60)
            if total > max_total_minutes:
                return
            key = tuple((s["flight_no"], s["departure_dt"]) for s in segments)
            if key in seen:
                return
            seen.add(key)
            itineraries.append({
                "segments": segments, "stops": len(segments) - 1,
                "total_minutes": total, "total_text": minutes_text(total),
                "departure_dt": segments[0]["departure_dt"], "arrival_dt": segments[-1]["arrival_dt"],
                "product": "666/2666" if all(s["product"] == "666/2666" for s in segments) else "2666",
            })

        for first in first_legs:
            if first["destination"] == destination:
                add([first])

        if max_stops <= 0:
            return itineraries[:max_results]

        for first in first_legs:
            if first["destination"] == destination:
                continue
            second_legs = self._departures_between(
                first["destination"],
                first["arrival_dt"] + timedelta(minutes=min_connect_minutes),
                first["arrival_dt"] + timedelta(minutes=max_connect_minutes),
                membership, airline, flight_no,
            )
            for second in second_legs:
                if second["destination"] == origin:
                    continue
                if second["destination"] == destination:
                    add([first, second])

                if max_stops < 2 or second["destination"] in {origin, first["destination"]}:
                    continue
                third_legs = self._departures_between(
                    second["destination"],
                    second["arrival_dt"] + timedelta(minutes=min_connect_minutes),
                    second["arrival_dt"] + timedelta(minutes=max_connect_minutes),
                    membership, airline, flight_no,
                )
                for third in third_legs:
                    if third["destination"] == destination and third["destination"] not in {origin, first["destination"]}:
                        add([first, second, third])
                        if len(itineraries) >= max_results * 3:
                            break
            if len(itineraries) >= max_results * 3:
                break

        return itineraries[:max_results]

    def search(self, origin, destination, date, membership="all", airline="", flight_no="", max_stops=0, sort="departure"):
        items = self.search_itineraries(origin, destination, date, membership, airline, flight_no, max_stops)
        if sort == "arrival":
            items.sort(key=lambda x: (x["arrival_dt"], x["stops"], x["total_minutes"]))
        elif sort == "duration":
            items.sort(key=lambda x: (x["total_minutes"], x["stops"], x["departure_dt"]))
        elif sort == "stops":
            items.sort(key=lambda x: (x["stops"], x["total_minutes"], x["departure_dt"]))
        else:
            items.sort(key=lambda x: (x["departure_dt"], x["stops"], x["total_minutes"]))
        return items

    def routes_from(self, origin, membership="all", airline="", query=""):
        """
        动态生成航线总览。

        页面布局和原筛选方式保持不变；这里额外把新 flight_daily.csv 中的
        B 舱状态按日期聚合给日历：
        - b_candidate_dates：有 / 有过 B 舱（当前可见或规则上应有但已隐藏/售罄）
        - running_only_dates：航班运行，但该会员规则下不算 B 候选（节假日/时段过滤）
        - b_visible_dates：当前响应里明确看到了 B（仅供 tooltip，页面不展示余票）
        """
        q = (query or "").strip().lower()

        groups = defaultdict(lambda: {
            "weekdays": set(),
            "dates": set(),
            "flight_nos": set(),
            "flight_records": [],
            "airlines": set(),
            "products": set(),
            "b_candidate_dates": set(),
            "b_visible_dates": set(),
            "running_only_dates": set(),
            "holiday_blocked_dates": set(),
            "date_flights": defaultdict(set),
        })

        for f in self.by_origin_sorted.get(origin, []):
            # 保持原网站的会员筛选逻辑，不改页面其他结果。
            if not product_eligible(f["departure_time"], membership):
                continue
            if airline and f["airline_code"] != airline:
                continue

            if q:
                haystack = " ".join([
                    f["destination"],
                    f["destination_name"],
                    f["flight_no"],
                    f["airline"],
                    f["airline_code"],
                ]).lower()
                if q not in haystack:
                    continue

            g = groups[f["destination"]]
            g["weekdays"].add(f["departure_dt"].weekday() + 1)
            g["dates"].add(f["departure_date"])
            g["flight_nos"].add(f["flight_no"])
            g["flight_records"].append(f)
            g["airlines"].add(f["airline"])
            g["products"].add(f["product"])
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

            if f["holiday_blocked"]:
                g["holiday_blocked_dates"].add(f["departure_date"])

        out = []
        for destination, g in groups.items():
            operating_dates = sorted(g["dates"])
            candidate_dates = sorted(g["b_candidate_dates"])
            visible_dates = sorted(g["b_visible_dates"])
            running_only_dates = sorted(g["running_only_dates"] - g["b_candidate_dates"])
            holiday_blocked_dates = sorted(g["holiday_blocked_dates"])
            schedule_rows = representative_schedule_rows(g["flight_records"], tolerance_minutes=30)

            out.append({
                "origin": origin,
                "origin_name": self.airports.get(origin, origin),
                "destination": destination,
                "destination_name": self.airports.get(destination, destination),
                "schedule": "".join(str(x) for x in sorted(g["weekdays"])),
                "schedule_text": " ".join(f"周{WEEKDAY_CN[x]}" for x in sorted(g["weekdays"])),
                # 总览时刻采用“同航班号 + 30 分钟容错 + 众数时刻”。
                # 如存在真正相差较大的换季时段，则同一航班号会保留多个代表时刻。
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
                "products": sorted(g["products"]),
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
                "first_date": operating_dates[0] if operating_dates else "",
                "last_date": operating_dates[-1] if operating_dates else "",
                "data_start": self.date_min,
                "data_end": self.date_max,
            })

        out.sort(key=lambda x: (x["destination_name"], x["destination"]))
        return out



STORE = FlightStore(DATA_FILE)


def serialize_flight(f):
    return {k: v for k, v in f.items() if k not in {"departure_dt", "arrival_dt"}}


def serialize_itinerary(i):
    return {
        "segments": [serialize_flight(s) for s in i["segments"]],
        "stops": i["stops"], "total_minutes": i["total_minutes"],
        "total_text": i["total_text"], "product": i["product"],
    }


def one(qs, key, default=""):
    values = qs.get(key)
    return values[0] if values else default


class Handler(BaseHTTPRequestHandler):
    server_version = "HNAPlusRoute/1.0"

    def log_message(self, fmt, *args):
        print(f"[{self.log_date_time_string()}] {fmt % args}")

    def send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_file(self, path):
        path = Path(path)
        if not path.exists() or not path.is_file():
            self.send_error(404)
            return
        data = path.read_bytes()
        ctype = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", ctype + ("; charset=utf-8" if ctype.startswith("text/") or ctype == "application/javascript" else ""))
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        parsed = urlparse(self.path)
        path, qs = parsed.path, parse_qs(parsed.query)

        if path == "/":
            return self.send_file(BASE_DIR / "templates" / "index.html")
        if path == "/static/style.css":
            return self.send_file(BASE_DIR / "static" / "style.css")
        if path == "/static/app.js":
            return self.send_file(BASE_DIR / "static" / "app.js")
        if path == "/api/health":
            return self.send_json({"ok": True, "data_file": str(DATA_FILE), "records": len(STORE.flights)})
        if path == "/api/meta":
            return self.send_json(STORE.meta())
        if path == "/api/routes":
            origin = one(qs, "origin").strip().upper()
            if not origin:
                return self.send_json({"error": "origin 为必填项"}, 400)
            rows = STORE.routes_from(
                origin,
                membership=one(qs, "membership", "all"),
                airline=one(qs, "airline").strip().upper(),
                query=one(qs, "q"),
            )
            return self.send_json({"origin": origin, "origin_name": STORE.airports.get(origin, origin), "count": len(rows), "routes": rows})
        if path == "/api/search":
            origin = one(qs, "origin").strip().upper()
            destination = one(qs, "destination").strip().upper()
            date = one(qs, "date").strip()
            if not origin or not destination or not date:
                return self.send_json({"error": "origin、destination、date 为必填项"}, 400)
            if date < STORE.date_min or date > STORE.date_max:
                return self.send_json({"error": f"日期超出数据范围 {STORE.date_min} ~ {STORE.date_max}"}, 400)
            try:
                max_stops = max(0, min(2, int(one(qs, "max_stops", "0"))))
            except ValueError:
                max_stops = 0
            items = STORE.search(
                origin=origin, destination=destination, date=date,
                membership=one(qs, "membership", "all"),
                airline=one(qs, "airline").strip().upper(),
                flight_no=one(qs, "flight_no").strip().upper(),
                max_stops=max_stops,
                sort=one(qs, "sort", "departure"),
            )
            return self.send_json({
                "origin": origin, "destination": destination, "date": date,
                "count": len(items), "results": [serialize_itinerary(x) for x in items],
            })
        return self.send_error(404)


def main():
    parser = argparse.ArgumentParser(description="海航 PLUS 航线查询工具（无第三方依赖）")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5000)
    args = parser.parse_args()
    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"数据：{DATA_FILE}")
    print(f"记录：{len(STORE.flights):,}，航线：{STORE.meta()['route_count']:,}，日期：{STORE.date_min} ~ {STORE.date_max}")
    print(f"打开：http://{args.host}:{args.port}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
