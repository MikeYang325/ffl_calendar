import json
import os
import sqlite3
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse

FUNCTION_DIR = Path(__file__).resolve().parent
FUNCTION_ROOT = FUNCTION_DIR.parent
DB_FILE = FUNCTION_DIR / "data" / "flights.db"
sys.path.insert(0, str(FUNCTION_ROOT))

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


def load_meta():
    if not DB_FILE.exists():
        raise FileNotFoundError(f"找不到数据库：{DB_FILE}")

    with sqlite3.connect(DB_FILE) as conn:
        date_min, date_max, flight_records, route_count = conn.execute(
            """
            SELECT MIN(departure_date), MAX(departure_date), COUNT(*),
                   COUNT(DISTINCT origin || '>' || destination)
            FROM flights
            """
        ).fetchone()

        airport_rows = conn.execute(
            """
            SELECT code, MAX(name) AS name FROM (
                SELECT origin AS code, origin_name AS name FROM flights
                UNION ALL
                SELECT destination AS code, destination_name AS name FROM flights
            )
            GROUP BY code
            ORDER BY code
            """
        ).fetchall()

        airline_codes = [row[0] for row in conn.execute(
            "SELECT DISTINCT SUBSTR(flight_no, 1, 2) FROM flights WHERE flight_no <> '' ORDER BY 1"
        )]

    airports = []
    airport_codes = set()
    for code, name in airport_rows:
        airport_codes.add(code)
        initial = pinyin_initial(name)
        airports.append({
            "code": code,
            "name": name,
            "initial": initial,
            "label": f"{name} {code}",
            "search": f"{name} {code} {initial}".upper(),
        })
    airports.sort(key=lambda x: (x["initial"], x["name"], x["code"]))

    airlines = [
        {"code": code, "name": AIRLINE_MAP.get(code, code), "label": f"{AIRLINE_MAP.get(code, code)} {code}"}
        for code in airline_codes if code
    ]
    cities = []
    for city, codes in sorted(CITY_AIRPORT_MAP.items()):
        present = [code for code in codes if code in airport_codes]
        if len(present) >= 2:
            cities.append({"name": city, "codes": present, "label": f"{city}（{'/'.join(present)}）"})

    return {
        "date_min": date_min or "",
        "date_max": date_max or "",
        "flight_records": int(flight_records or 0),
        "route_count": int(route_count or 0),
        "airport_count": len(airports),
        "airports": airports,
        "airlines": airlines,
        "cities": cities,
        "membership_rules": {"666": "08:00前或20:00后出发", "2666": "全天覆盖"},
    }


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
        if urlparse(self.path).path == "/api/meta":
            try:
                return self.send_json(load_meta())
            except Exception as exc:
                return self.send_json({"error": str(exc)}, 500)

        os.environ["HNA_FLIGHT_DB"] = str(DB_FILE)
        from app import Handler as AppHandler
        return AppHandler.do_GET(self)
