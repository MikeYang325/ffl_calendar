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

DB_FILE = Path('/tmp/flights.db')
DB_URL = 'https://ffl-calendar-new.edgeone.dev/data/flights.db'
BLACKOUT_START = '2026-10-01'
BLACKOUT_END = '2026-10-08'

AIRLINE_MAP = {
    'HU': '海南航空', 'GS': '天津航空', 'JD': '首都航空', 'PN': '西部航空',
    'UQ': '乌鲁木齐航空', '8L': '祥鹏航空', '9H': '长安航空', 'CN': '大新华航空',
    'FU': '福州航空', 'GX': '北部湾航空', 'Y8': '金鹏航空',
}
CITY_AIRPORT_MAP = {
    '北京': ('PEK', 'PKX'), '上海': ('SHA', 'PVG'), '成都': ('CTU', 'TFU'),
    '重庆': ('CKG', 'WSK'), '遵义': ('ZYI', 'WMT'), '东京': ('HND', 'NRT'),
    '首尔': ('ICN', 'GMP'), '大阪': ('KIX', 'ITM'), '台北': ('TPE', 'TSA'),
}
CITY_BY_AIRPORT = {code: city for city, codes in CITY_AIRPORT_MAP.items() for code in codes}


def ensure_db():
    if DB_FILE.exists() and DB_FILE.stat().st_size > 1024 * 1024:
        return
    tmp = Path(f'{DB_FILE}.{os.getpid()}.{threading.get_ident()}.download')
    try:
        with urllib.request.urlopen(DB_URL, timeout=60) as response, tmp.open('wb') as out:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                out.write(chunk)
        if not (DB_FILE.exists() and DB_FILE.stat().st_size > 1024 * 1024):
            tmp.replace(DB_FILE)
    finally:
        tmp.unlink(missing_ok=True)
    with DB_FILE.open('rb') as source:
        if source.read(16) != b'SQLite format 3\x00':
            DB_FILE.unlink(missing_ok=True)
            raise RuntimeError('flights.db 不是有效 SQLite 文件')


def connect():
    ensure_db()
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def one(qs, key, default=''):
    values = qs.get(key)
    return values[0] if values else default


def as_int(value, default, minimum=None, maximum=None):
    try:
        result = int(value)
    except Exception:
        result = default
    if minimum is not None:
        result = max(minimum, result)
    if maximum is not None:
        result = min(maximum, result)
    return result


def date_range(start, end):
    current = datetime.strptime(start, '%Y-%m-%d').date()
    finish = datetime.strptime(end, '%Y-%m-%d').date()
    while current <= finish:
        yield current.isoformat()
        current += timedelta(days=1)


def is_blackout(date_text):
    return BLACKOUT_START <= date_text <= BLACKOUT_END


def json_response(handler, payload, status=200):
    body = json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    handler.send_response(status)
    handler.send_header('Content-Type', 'application/json; charset=utf-8')
    handler.send_header('Cache-Control', 'no-store')
    handler.send_header('Content-Length', str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def airport_codes_for_location(location):
    raw = (location or '').strip()
    upper = raw.upper()
    if upper in AIRPORTS_BY_CODE:
        return [upper]
    if raw in CITY_AIRPORT_MAP:
        return list(CITY_AIRPORT_MAP[raw])
    if raw in CODES_BY_CITY:
        return CODES_BY_CITY[raw]
    return []


def load_meta(conn):
    global AIRPORTS_BY_CODE, CODES_BY_CITY
    airports = {}
    codes_by_city = defaultdict(list)
    for row in conn.execute('SELECT code, name, city, country FROM airports ORDER BY city, code'):
        item = {'code': row['code'], 'name': row['name'] or '', 'city': row['city'] or '', 'country': row['country'] or ''}
        airports[row['code']] = item
        if item['city']:
            codes_by_city[item['city']].append(row['code'])
    AIRPORTS_BY_CODE = airports
    CODES_BY_CITY = dict(codes_by_city)


def meta_payload(conn):
    load_meta(conn)
    row = conn.execute('SELECT MIN(flight_date) AS date_min, MAX(flight_date) AS date_max, COUNT(*) AS flight_records FROM flights').fetchone()
    route_count = conn.execute('SELECT COUNT(*) AS n FROM routes').fetchone()['n']
    airlines = sorted({r['airline'] for r in conn.execute("SELECT DISTINCT airline FROM flights WHERE airline IS NOT NULL AND airline != ''")})
    return {
        'date_min': row['date_min'],
        'date_max': row['date_max'],
        'flight_records': row['flight_records'],
        'route_count': route_count,
        'airport_count': len(AIRPORTS_BY_CODE),
        'airports': list(AIRPORTS_BY_CODE.values()),
        'airlines': [{'code': code, 'name': AIRLINE_MAP.get(code, code)} for code in airlines],
        'cities': sorted(CODES_BY_CITY),
    }


def routes_payload(conn, qs):
    load_meta(conn)
    location = one(qs, 'location')
    direction = one(qs, 'direction', 'departure')
    membership = one(qs, 'membership', '666')
    weekday = one(qs, 'weekday')
    period = one(qs, 'period')
    airline = one(qs, 'airline')
    codes = airport_codes_for_location(location)
    if not codes:
        return {'selected_name': location, 'count': 0, 'routes': []}

    origin_col, dest_col = ('origin', 'destination') if direction == 'departure' else ('destination', 'origin')
    placeholders = ','.join('?' for _ in codes)
    sql = f'''SELECT f.origin, f.destination, f.airline, f.flight_no, f.flight_date, f.departure_time, f.arrival_time,
                     a.city AS destination_city, a.name AS destination_airport
              FROM flights f
              LEFT JOIN airports a ON a.code = f.{dest_col}
              WHERE f.{origin_col} IN ({placeholders})'''
    params = list(codes)
    if weekday:
        sql += ' AND f.weekday = ?'
        params.append(weekday)
    if period:
        sql += ' AND f.period = ?'
        params.append(period)
    if airline:
        sql += ' AND f.airline = ?'
        params.append(airline)
    sql += ' ORDER BY f.flight_date, f.departure_time, f.flight_no'
    rows = conn.execute(sql, params).fetchall()

    grouped = {}
    for row in rows:
        key = (row['origin'], row['destination'], row['airline'], row['flight_no'])
        item = grouped.setdefault(key, {
            'origin': row['origin'], 'destination': row['destination'], 'airline': row['airline'],
            'flight_no': row['flight_no'], 'dates': [], 'departure_time': row['departure_time'] or '',
            'arrival_time': row['arrival_time'] or '', 'destination_city': row['destination_city'] or '',
            'destination_airport': row['destination_airport'] or '',
        })
        item['dates'].append(row['flight_date'])

    items = []
    for item in grouped.values():
        dates = sorted(set(item.pop('dates')))
        item['date_min'] = dates[0] if dates else ''
        item['date_max'] = dates[-1] if dates else ''
        item['frequency'] = len(dates)
        item['membership'] = membership
        items.append(item)
    items.sort(key=lambda x: (x['destination_city'], x['destination'], x['flight_no']))
    return {'selected_name': location, 'count': len(items), 'routes': items}


def search_payload(conn, qs):
    load_meta(conn)
    origin = one(qs, 'origin').upper()
    destination = one(qs, 'destination').upper()
    date = one(qs, 'date')
    membership = one(qs, 'membership', '666')
    max_stops = as_int(one(qs, 'max_stops', '0'), 0, 0, 2)
    if not origin or not destination or not date:
        return {'count': 0, 'results': []}
    if is_blackout(date):
        return {'count': 0, 'results': [], 'blackout': True}

    rows = conn.execute('''SELECT origin, destination, airline, flight_no, flight_date, departure_time, arrival_time
                           FROM flights WHERE origin = ? AND destination = ? AND flight_date = ?
                           ORDER BY departure_time, flight_no''', (origin, destination, date)).fetchall()
    results = [{
        'segments': [dict(row)], 'stops': 0, 'membership': membership,
    } for row in rows]
    if results or max_stops == 0:
        return {'count': len(results), 'results': results}

    first_legs = conn.execute('''SELECT origin, destination, airline, flight_no, flight_date, departure_time, arrival_time
                                 FROM flights WHERE origin = ? AND flight_date = ? ORDER BY departure_time''', (origin, date)).fetchall()
    by_mid = defaultdict(list)
    for leg in first_legs:
        by_mid[leg['destination']].append(leg)
    for mid, legs in by_mid.items():
        if mid in {origin, destination}:
            continue
        second_legs = conn.execute('''SELECT origin, destination, airline, flight_no, flight_date, departure_time, arrival_time
                                      FROM flights WHERE origin = ? AND destination = ? AND flight_date = ? ORDER BY departure_time''',
                                   (mid, destination, date)).fetchall()
        for first in legs:
            for second in second_legs:
                results.append({'segments': [dict(first), dict(second)], 'stops': 1, 'membership': membership})
    return {'count': len(results), 'results': results}


AIRPORTS_BY_CODE = {}
CODES_BY_CITY = {}


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            parsed = urlparse(self.path)
            qs = parse_qs(parsed.query)
            if parsed.path == '/api/meta':
                with connect() as conn:
                    payload = meta_payload(conn)
                return json_response(self, payload)
            if parsed.path == '/api/routes':
                with connect() as conn:
                    payload = routes_payload(conn, qs)
                return json_response(self, payload)
            if parsed.path == '/api/search':
                with connect() as conn:
                    payload = search_payload(conn, qs)
                return json_response(self, payload)
            return json_response(self, {'error': 'Not found'}, 404)
        except Exception as exc:
            return json_response(self, {'error': str(exc)}, 500)
