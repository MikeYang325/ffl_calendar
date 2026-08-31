#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import sqlite3
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
DB_FILE = Path(os.environ.get("HNA_FLIGHT_DB", BASE_DIR / "data" / "flights.db"))

AIRLINE_MAP = {
    "HU": "海南航空", "GS": "天津航空", "JD": "首都航空", "PN": "西部航空",
    "UQ": "乌鲁木齐航空", "8L": "祥鹏航空", "9H": "长安航空", "CN": "大新华航空",
    "FU": "福州航空", "GX": "北部湾航空", "Y8": "金鹏航空",
}
WEEKDAY_CN = {1: "一", 2: "二", 3: "三", 4: "四", 5: "五", 6: "六", 7: "日"}

# 飞飞乐 PLUS 已确认的硬性无票期。即使后续重新导入数据库，规则也不会丢失。
TICKET_BLACKOUT_RANGES = (("2026-10-01", "2026-10-08"),)

def ticket_blackout(date_text):
    value = str(date_text or "").strip()
    return any(start <= value <= end for start, end in TICKET_BLACKOUT_RANGES)

CITY_AIRPORT_MAP = {
    "北京": ("PEK", "PKX"),
    "上海": ("SHA", "PVG"),
    "成都": ("CTU", "TFU"),
    "重庆": ("CKG", "WSK"),
    "遵义": ("ZYI", "WMT"),
    "东京": ("HND", "NRT"),
    "首尔": ("ICN", "GMP"),
    "大阪": ("KIX", "ITM"),
    "台北": ("TPE", "TSA"),
}


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
    # 666 是基础适用版本；2666 是父级版本，继承 666 并额外覆盖全天。
    # 产品标签表示“最低适用版本”，因此不再使用 666/2666 这种并列写法。
    if departure_time and (departure_time < "08:00" or departure_time > "20:00"):
        return "666"
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
    def __init__(self, db_path):
        self.db_path = Path(db_path)
        self.flights = []
        self.by_date_origin = defaultdict(list)
        self.by_origin_sorted = defaultdict(list)
        self.by_origin_times = defaultdict(list)
        self.by_destination_sorted = defaultdict(list)
        self.airports = {}
        self.airlines = {}
        self.city_airports = {}
        self.city_by_airport = {}
        self.date_min = ""
        self.date_max = ""
        self.route_overview = {}
        self.load()

    def load(self):
        if not self.db_path.exists():
            raise FileNotFoundError(f"找不到数据库：{self.db_path}")

        raw, dates = [], []
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT origin, origin_name, destination, destination_name,
                       flight_no, operating_flight_no, departure_date, departure_time,
                       arrival_date, arrival_time, duration_minutes, aircraft,
                       code_share, stop_quantity, flight_running, b_status,
                       b_expected_or_seen, b_visible_raw, holiday_blocked,
                       status_666, eligible_666, status_2666, eligible_2666
                FROM flights
                ORDER BY departure_date, departure_time, origin, destination, flight_no
            """)
            for db_row in rows:
                row = dict(db_row)
                dep_dt = parse_datetime(row["departure_date"], row["departure_time"])
                arr_dt = parse_datetime(row["arrival_date"], row["arrival_time"])
                code = airline_code(row["flight_no"])
                duration = int(row["duration_minutes"] or 0)
                flight = {
                    "origin": row["origin"],
                    "origin_name": row["origin_name"],
                    "destination": row["destination"],
                    "destination_name": row["destination_name"],
                    "flight_no": row["flight_no"],
                    "operating_flight_no": row["operating_flight_no"],
                    "airline_code": code,
                    "airline": AIRLINE_MAP.get(code, code),
                    "departure_date": row["departure_date"],
                    "departure_time": row["departure_time"],
                    "arrival_date": row["arrival_date"],
                    "arrival_time": row["arrival_time"],
                    "departure_dt": dep_dt,
                    "arrival_dt": arr_dt,
                    "duration_minutes": duration,
                    "duration_text": minutes_text(duration),
                    "aircraft": row["aircraft"],
                    "code_share": bool(row["code_share"]),
                    "stop_quantity": int(row["stop_quantity"] or 0),
                    "product": product_for_departure(row["departure_time"]),
                    "cross_day": (arr_dt.date() - dep_dt.date()).days,
                    "flight_running": bool(row["flight_running"]),
                    "b_status": row["b_status"],
                    "b_expected_or_seen": bool(row["b_expected_or_seen"]),
                    "b_visible_raw": bool(row["b_visible_raw"]),
                    "holiday_blocked": bool(row["holiday_blocked"]),
                    "status_666": row["status_666"],
                    "eligible_666": bool(row["eligible_666"]),
                    "status_2666": row["status_2666"],
                    "eligible_2666": bool(row["eligible_2666"]),
                }
                raw.append(flight)
                dates.append(row["departure_date"])
                self.airports[row["origin"]] = row["origin_name"]
                self.airports[row["destination"]] = row["destination_name"]
                self.airlines[code] = AIRLINE_MAP.get(code, code)

        raw.sort(key=lambda x: x["departure_dt"])
        self.flights = raw
        if dates:
            self.date_min, self.date_max = min(dates), max(dates)

        for flight in self.flights:
            self.by_date_origin[(flight["departure_date"], flight["origin"])].append(flight)
            self.by_origin_sorted[flight["origin"]].append(flight)
            self.by_destination_sorted[flight["destination"]].append(flight)

        for origin, flights in self.by_origin_sorted.items():
            flights.sort(key=lambda x: x["departure_dt"])
            self.by_origin_times[origin] = [f["departure_dt"] for f in flights]

        self.city_airports = {
            city: [code for code in codes if code in self.airports]
            for city, codes in CITY_AIRPORT_MAP.items()
        }
        self.city_airports = {city: codes for city, codes in self.city_airports.items() if codes}
        self.city_by_airport = {
            code: city for city, codes in self.city_airports.items() for code in codes
        }
        self._build_route_overview()

    def city_options(self):
        return [
            {"name": city, "codes": codes, "label": f"{city}（{'/'.join(codes)}）"}
            for city, codes in sorted(self.city_airports.items())
            if len(codes) >= 2
        ]

    def resolve_origins(self, value):
        raw = str(value or "").strip()
        if not raw:
            return [], "", False
        upper = raw.upper()
        if upper in self.airports:
            return [upper], self.airports.get(upper, upper), False
        if raw in self.city_airports:
            codes = self.city_airports[raw]
            return list(codes), raw, len(codes) > 1

        matched = [
            code for code, name in self.airports.items()
            if raw.lower() in str(name).lower()
        ]
        if matched:
            matched = sorted(set(matched))
            mapped_cities = {self.city_by_airport.get(code) for code in matched}
            mapped_cities.discard(None)
            if len(mapped_cities) == 1:
                city = next(iter(mapped_cities))
                city_codes = [c for c in self.city_airports.get(city, []) if c in matched]
                if city_codes:
                    return city_codes, city, len(city_codes) > 1
            if len(matched) == 1:
                code = matched[0]
                return matched, self.airports.get(code, code), False
            return matched, raw, len(matched) > 1
        return [], raw, False

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
            "cities": self.city_options(),
            "membership_rules": {"666": "08:00前或20:00后出发", "2666": "全天覆盖"},
        }

    @staticmethod
    def _basic_filter(f, membership="all", airline="", flight_no=""):
        # holiday_blocked 来自数据导入；ticket_blackout 是业务规则双保险。
        if f.get("holiday_blocked") or ticket_blackout(f.get("departure_date")):
            return False
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
                "product": "666" if all(s["product"] == "666" for s in segments) else "2666",
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

    def routes_from(self, origin, membership="all", airline="", query="", weekday="", departure_period=""):
        return self._routes_by_location(
            origin, direction="departure", membership=membership, airline=airline,
            query=query, weekday=weekday, departure_period=departure_period,
        )

    def routes_to(self, destination, membership="all", airline="", query="", weekday="", departure_period=""):
        return self._routes_by_location(
            destination, direction="arrival", membership=membership, airline=airline,
            query=query, weekday=weekday, departure_period=departure_period,
        )

    def routes_overview(self, location, direction="departure", membership="all", airline="", query="",
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

    def _routes_by_location(self, location, direction="departure", membership="all", airline="", query="",
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


STORE = FlightStore(DB_FILE)


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
        if path == "/lovefly-tools.css":
            return self.send_file(BASE_DIR / "lovefly-tools.css")
        if path == "/lovefly-wordmark.svg":
            return self.send_file(BASE_DIR / "lovefly-wordmark.svg")
        if path == "/api/health":
            return self.send_json({"ok": True, "database": str(DB_FILE), "records": len(STORE.flights)})
        if path == "/api/meta":
            return self.send_json(STORE.meta())
        if path == "/api/routes":
            location = one(qs, "location", one(qs, "origin")).strip()
            if not location:
                return self.send_json({"error": "location 为必填项"}, 400)
            selected_codes, selected_name, aggregate = STORE.resolve_origins(location)
            if not selected_codes:
                return self.send_json({"error": "没有找到这个城市或机场"}, 400)
            direction = one(qs, "direction", "departure").strip().lower()
            if direction not in {"departure", "arrival", "roundtrip"}:
                direction = "departure"
            membership = one(qs, "membership", "666").strip()
            if membership not in {"666", "2666"}:
                membership = "666"
            rows = STORE.routes_overview(
                location, direction=direction, membership=membership,
                airline=one(qs, "airline").strip().upper(),
                query=one(qs, "q"),
                weekday=one(qs, "weekday"),
                departure_period=one(qs, "departure_period"),
            )
            return self.send_json({
                "location": location, "selected_name": selected_name, "selected_codes": selected_codes,
                "direction": direction, "membership": membership, "aggregate": aggregate,
                "count": len(rows), "routes": rows
            })
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
    print(f"数据库：{DB_FILE}")
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
