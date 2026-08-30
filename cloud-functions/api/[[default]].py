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


def parse_dt(date_text, time_text):
    return datetime.strptime(f'{date_text} {time_text}', '%Y-%m-%d %H:%M')


def blocked(row):
    date = row['departure_date']
    return bool(row['holiday_blocked']) or BLACKOUT_START <= date <= BLACKOUT_END


def product_eligible(time_text, membership):
    return membership != '666' or time_text < '08:00' or time_text > '20:00'


def product_for_time(time_text):
    return '666' if time_text < '08:00' or time_text > '20:00' else '2666'


def duration_text(minutes):
    minutes = int(minutes or 0)
    hours, mins = divmod(minutes, 60)
    if hours and mins:
        return f'{hours}小时{mins}分'
    if hours:
        return f'{hours}小时'
    return f'{mins}分'


def pinyin_initial(text):
    text = str(text or '').strip()
    if not text:
        return '#'
    ch = text[0].upper()
    if 'A' <= ch <= 'Z':
        return ch
    try:
        gb = ch.encode('gbk')
        code = gb[0] * 256 + gb[1] - 65536
    except Exception:
        return '#'
    ranges = [
        (-20319, 'A'), (-20283, 'B'), (-19775, 'C'), (-19218, 'D'), (-18710, 'E'),
        (-18526, 'F'), (-18239, 'G'), (-17922, 'H'), (-17417, 'J'), (-16474, 'K'),
        (-16212, 'L'), (-15640, 'M'), (-15165, 'N'), (-14922, 'O'), (-14914, 'P'),
        (-14630, 'Q'), (-14149, 'R'), (-14090, 'S'), (-13318, 'T'), (-12838, 'W'),
        (-12556, 'X'), (-11847, 'Y'), (-11055, 'Z'),
    ]
    for index in range(len(ranges) - 1):
        if ranges[index][0] <= code < ranges[index + 1][0]:
            return ranges[index][1]
    return ranges[-1][1] if code >= ranges[-1][0] else '#'


def get_airports(conn):
    sql = (
        'SELECT code, MAX(name) AS name FROM ('
        'SELECT origin AS code, origin_name AS name FROM flights UNION ALL '
        'SELECT destination AS code, destination_name AS name FROM flights'
        ') GROUP BY code'
    )
    return {row['code']: row['name'] for row in conn.execute(sql)}


def meta_api():
    with connect() as conn:
        date_min, date_max, records, route_count = conn.execute(
            "SELECT MIN(departure_date),MAX(departure_date),COUNT(*),COUNT(DISTINCT origin||'>'||destination) FROM flights"
        ).fetchone()
        airport_dict = get_airports(conn)
        airline_codes = [row[0] for row in conn.execute(
            "SELECT DISTINCT SUBSTR(flight_no,1,2) FROM flights WHERE flight_no<>'' ORDER BY 1"
        )]
    airports = []
    for code, name in airport_dict.items():
        initial = pinyin_initial(name)
        airports.append({
            'code': code, 'name': name, 'initial': initial,
            'label': f'{name} {code}', 'search': f'{name} {code} {initial}'.upper(),
        })
    airports.sort(key=lambda item: (item['initial'], item['name'], item['code']))
    airlines = [
        {'code': code, 'name': AIRLINE_MAP.get(code, code), 'label': f'{AIRLINE_MAP.get(code, code)} {code}'}
        for code in airline_codes if code
    ]
    cities = []
    for city, codes in sorted(CITY_AIRPORT_MAP.items()):
        present = [code for code in codes if code in airport_dict]
        if len(present) >= 2:
            cities.append({'name': city, 'codes': present, 'label': f"{city}（{'/'.join(present)}）"})
    return {
        'date_min': date_min or '', 'date_max': date_max or '', 'flight_records': int(records or 0),
        'route_count': int(route_count or 0), 'airport_count': len(airports),
        'airports': airports, 'airlines': airlines, 'cities': cities,
        'membership_rules': {'666': '08:00前或20:00后出发', '2666': '全天覆盖'},
    }


def resolve_location(conn, value):
    raw = str(value or '').strip()
    airports = get_airports(conn)
    upper = raw.upper()
    if upper in airports:
        return [upper], airports[upper], False
    if raw in CITY_AIRPORT_MAP:
        codes = [code for code in CITY_AIRPORT_MAP[raw] if code in airports]
        if codes:
            return codes, raw, len(codes) > 1
    matched = sorted(code for code, name in airports.items() if raw and raw.lower() in str(name).lower())
    if matched:
        return matched, raw, len(matched) > 1
    return [], raw, False


def schedule_rows(rows):
    by_flight = defaultdict(Counter)
    for row in rows:
        dep_date = datetime.strptime(row['departure_date'], '%Y-%m-%d').date()
        arr_date = datetime.strptime(row['arrival_date'], '%Y-%m-%d').date()
        by_flight[row['flight_no']][(row['departure_time'], row['arrival_time'], (arr_date - dep_date).days)] += 1
    result = []
    for flight_no in sorted(by_flight):
        for (dep, arr, cross), count in by_flight[flight_no].most_common():
            result.append({
                'flight_no': flight_no, 'departure_time': dep, 'arrival_time': arr,
                'cross_day': cross, 'observations': count, 'merged_variants': 1,
            })
    result.sort(key=lambda item: (item['departure_time'], item['flight_no']))
    return result


def route_direction(conn, location, direction, membership, airline, query, weekday, period):
    selected, selected_name, aggregate = resolve_location(conn, location)
    if not selected:
        return [], selected_name, selected, aggregate
    column = 'destination' if direction == 'arrival' else 'origin'
    placeholders = ','.join('?' for _ in selected)
    sql = (
        'SELECT origin,origin_name,destination,destination_name,flight_no,'
        'departure_date,departure_time,arrival_date,arrival_time,holiday_blocked '
        f'FROM flights WHERE {column} IN ({placeholders})'
    )
    params = list(selected)
    if membership == '666':
        sql += " AND (departure_time<'08:00' OR departure_time>'20:00')"
    if airline:
        sql += ' AND SUBSTR(flight_no,1,2)=?'
        params.append(airline)
    rows = [dict(row) for row in conn.execute(sql, params)]
    try:
        weekday_num = int(weekday) if weekday else 0
    except ValueError:
        weekday_num = 0
    q = str(query or '').strip().lower()
    groups = defaultdict(lambda: {
        'rows': [], 'dates': set(), 'weekdays': set(), 'origins': set(), 'destinations': set(),
        'counterpart_codes': set(), 'airlines': set(), 'date_flights': defaultdict(set),
    })
    for row in rows:
        wd = datetime.strptime(row['departure_date'], '%Y-%m-%d').isoweekday()
        if weekday_num and wd != weekday_num:
            continue
        if period == 'morning' and row['departure_time'] >= '08:00':
            continue
        if period == 'evening' and row['departure_time'] < '20:00':
            continue
        counterpart = row['origin'] if direction == 'arrival' else row['destination']
        counterpart_name = row['origin_name'] if direction == 'arrival' else row['destination_name']
        counterpart_city = CITY_BY_AIRPORT.get(counterpart)
        if q:
            haystack = ' '.join([
                counterpart, counterpart_name, counterpart_city or '', row['flight_no'],
                AIRLINE_MAP.get(row['flight_no'][:2], row['flight_no'][:2]),
            ]).lower()
            if q not in haystack:
                continue
        key = f'CITY:{counterpart_city}' if aggregate and counterpart_city else counterpart
        group = groups[key]
        group['counterpart_name'] = counterpart_city if aggregate and counterpart_city else counterpart_name
        group['counterpart_codes'].add(counterpart)
        group['rows'].append(row)
        group['weekdays'].add(wd)
        group['origins'].add(row['origin'])
        group['destinations'].add(row['destination'])
        group['airlines'].add(AIRLINE_MAP.get(row['flight_no'][:2], row['flight_no'][:2]))
        if not blocked(row):
            group['dates'].add(row['departure_date'])
            group['date_flights'][row['departure_date']].add(row['flight_no'])
    data_start, data_end = conn.execute('SELECT MIN(departure_date),MAX(departure_date) FROM flights').fetchone()
    output = []
    for key, group in groups.items():
        dates = sorted(group['dates'])
        if not dates:
            continue
        schedules = schedule_rows(group['rows'])
        output.append({
            'direction': direction, '_counterpart_key': key,
            'counterpart_name': group['counterpart_name'],
            'counterpart_codes': sorted(group['counterpart_codes']),
            'selected_name': selected_name, 'selected_codes': selected,
            'origin': '/'.join(sorted(group['origins'])), 'origin_codes': sorted(group['origins']),
            'destination': '/'.join(sorted(group['destinations'])), 'destination_codes': sorted(group['destinations']),
            'aggregate': aggregate, 'schedule': ''.join(str(x) for x in sorted(group['weekdays'])),
            'schedule_rows': schedules, 'flight_nos': [item['flight_no'] for item in schedules],
            'times': [
                {'departure_time': item['departure_time'], 'arrival_time': item['arrival_time'], 'cross_day': item['cross_day']}
                for item in schedules
            ],
            'airlines': sorted(group['airlines']), 'products': [membership],
            'operating_days': len(dates), 'operating_dates': dates,
            'date_flights': {date: sorted(values) for date, values in sorted(group['date_flights'].items())},
            'first_date': dates[0], 'last_date': dates[-1], 'data_start': data_start, 'data_end': data_end,
            'weekday_filter': weekday_num,
        })
    output.sort(key=lambda item: (item['counterpart_name'], '/'.join(item['counterpart_codes'])))
    return output, selected_name, selected, aggregate


def routes_api(qs):
    location = one(qs, 'location', one(qs, 'origin')).strip()
    if not location:
        return {'error': 'location 为必填项'}, 400
    direction = one(qs, 'direction', 'departure').strip().lower()
    if direction not in {'departure', 'arrival', 'roundtrip'}:
        direction = 'departure'
    membership = one(qs, 'membership', '666').strip()
    if membership not in {'666', '2666'}:
        membership = '666'
    airline = one(qs, 'airline').strip().upper()
    query = one(qs, 'q')
    weekday = one(qs, 'weekday')
    period = one(qs, 'departure_period')
    with connect() as conn:
        if direction != 'roundtrip':
            rows, selected_name, selected, aggregate = route_direction(
                conn, location, direction, membership, airline, query, weekday, period
            )
        else:
            outbound, selected_name, selected, aggregate = route_direction(
                conn, location, 'departure', membership, airline, query, weekday, period
            )
            inbound, _, _, _ = route_direction(
                conn, location, 'arrival', membership, airline, query, weekday, period
            )
            out_map = {item['_counterpart_key']: item for item in outbound}
            in_map = {item['_counterpart_key']: item for item in inbound}
            rows = []
            for key in sorted(set(out_map) & set(in_map)):
                out = out_map[key]
                back = in_map[key]
                rows.append({
                    'direction': 'roundtrip', '_counterpart_key': key,
                    'counterpart_name': out['counterpart_name'],
                    'counterpart_codes': sorted(set(out['counterpart_codes'] + back['counterpart_codes'])),
                    'aggregate': aggregate, 'products': [membership], 'outbound': out, 'inbound': back,
                })
    if not selected:
        return {'error': '没有找到这个城市或机场'}, 400
    return {
        'location': location, 'selected_name': selected_name, 'selected_codes': selected,
        'direction': direction, 'membership': membership, 'aggregate': aggregate,
        'count': len(rows), 'routes': rows,
    }, 200


def make_flight(row):
    dep_dt = parse_dt(row['departure_date'], row['departure_time'])
    arr_dt = parse_dt(row['arrival_date'], row['arrival_time'])
    airline_code = row['flight_no'][:2]
    return {
        'origin': row['origin'], 'origin_name': row['origin_name'],
        'destination': row['destination'], 'destination_name': row['destination_name'],
        'flight_no': row['flight_no'], 'operating_flight_no': row['operating_flight_no'],
        'departure_date': row['departure_date'], 'departure_time': row['departure_time'],
        'arrival_date': row['arrival_date'], 'arrival_time': row['arrival_time'],
        'duration_minutes': int(row['duration_minutes'] or 0),
        'duration_text': duration_text(row['duration_minutes']), 'aircraft': row['aircraft'],
        'code_share': bool(row['code_share']), 'stop_quantity': int(row['stop_quantity'] or 0),
        'airline_code': airline_code, 'airline': AIRLINE_MAP.get(airline_code, airline_code),
        'product': product_for_time(row['departure_time']),
        'cross_day': (arr_dt.date() - dep_dt.date()).days,
        '_departure_dt': dep_dt, '_arrival_dt': arr_dt, 'holiday_blocked': bool(row['holiday_blocked']),
    }


def search_api(qs):
    origin = one(qs, 'origin').strip().upper()
    destination = one(qs, 'destination').strip().upper()
    date = one(qs, 'date').strip()
    if not origin or not destination or not date:
        return {'error': 'origin、destination、date 为必填项'}, 400
    membership = one(qs, 'membership', 'all').strip()
    airline = one(qs, 'airline').strip().upper()
    flight_no = one(qs, 'flight_no').strip().upper()
    try:
        max_stops = max(0, min(2, int(one(qs, 'max_stops', '0'))))
    except ValueError:
        max_stops = 0
    start = datetime.strptime(date, '%Y-%m-%d')
    end_date = (start + timedelta(days=3)).strftime('%Y-%m-%d')
    sql = (
        'SELECT origin,origin_name,destination,destination_name,flight_no,operating_flight_no,'
        'departure_date,departure_time,arrival_date,arrival_time,duration_minutes,aircraft,'
        'code_share,stop_quantity,holiday_blocked FROM flights '
        'WHERE departure_date>=? AND departure_date<=? ORDER BY departure_date,departure_time'
    )
    with connect() as conn:
        data_min, data_max = conn.execute('SELECT MIN(departure_date),MAX(departure_date) FROM flights').fetchone()
        if date < data_min or date > data_max:
            return {'error': f'日期超出数据范围 {data_min} ~ {data_max}'}, 400
        rows = conn.execute(sql, (date, end_date)).fetchall()
    flights = []
    for row in rows:
        flight = make_flight(row)
        if blocked(flight) or not product_eligible(flight['departure_time'], membership):
            continue
        if airline and flight['airline_code'] != airline:
            continue
        if flight_no and flight_no not in flight['flight_no']:
            continue
        flights.append(flight)
    by_origin = defaultdict(list)
    for flight in flights:
        by_origin[flight['origin']].append(flight)
    first_legs = [flight for flight in by_origin.get(origin, []) if flight['departure_date'] == date]
    itineraries = []
    seen = set()

    def add(segments):
        if segments[-1]['destination'] != destination:
            return
        total = int((segments[-1]['_arrival_dt'] - segments[0]['_departure_dt']).total_seconds() // 60)
        if total < 0 or total > 2880:
            return
        key = tuple((segment['flight_no'], segment['departure_date'], segment['departure_time']) for segment in segments)
        if key in seen:
            return
        seen.add(key)
        itineraries.append({
            'segments': segments, 'stops': len(segments) - 1, 'total_minutes': total,
            'total_text': duration_text(total), '_departure_dt': segments[0]['_departure_dt'],
            '_arrival_dt': segments[-1]['_arrival_dt'],
            'product': '666' if all(segment['product'] == '666' for segment in segments) else '2666',
        })

    def next_legs(flight):
        low = flight['_arrival_dt'] + timedelta(minutes=60)
        high = flight['_arrival_dt'] + timedelta(minutes=1440)
        return [candidate for candidate in by_origin.get(flight['destination'], []) if low <= candidate['_departure_dt'] <= high]

    for first in first_legs:
        if first['destination'] == destination:
            add([first])
        if max_stops < 1 or first['destination'] == destination:
            continue
        for second in next_legs(first):
            if second['destination'] == origin:
                continue
            if second['destination'] == destination:
                add([first, second])
            if max_stops < 2 or second['destination'] in {origin, first['destination'], destination}:
                continue
            for third in next_legs(second):
                if third['destination'] == destination:
                    add([first, second, third])
    sort_key = one(qs, 'sort', 'departure')
    if sort_key == 'arrival':
        itineraries.sort(key=lambda item: (item['_arrival_dt'], item['stops'], item['total_minutes']))
    elif sort_key == 'duration':
        itineraries.sort(key=lambda item: (item['total_minutes'], item['stops'], item['_departure_dt']))
    elif sort_key == 'stops':
        itineraries.sort(key=lambda item: (item['stops'], item['total_minutes'], item['_departure_dt']))
    else:
        itineraries.sort(key=lambda item: (item['_departure_dt'], item['stops'], item['total_minutes']))

    def public_segment(segment):
        return {key: value for key, value in segment.items() if not key.startswith('_') and key != 'holiday_blocked'}

    results = [
        {
            'segments': [public_segment(segment) for segment in item['segments']],
            'stops': item['stops'], 'total_minutes': item['total_minutes'],
            'total_text': item['total_text'], 'product': item['product'],
        }
        for item in itineraries[:120]
    ]
    return {'origin': origin, 'destination': destination, 'date': date, 'count': len(results), 'results': results}, 200


class handler(BaseHTTPRequestHandler):
    def send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)
        try:
            if path == '/api/meta':
                return self.send_json(meta_api())
            if path == '/api/routes':
                data, status = routes_api(qs)
                return self.send_json(data, status)
            if path == '/api/search':
                data, status = search_api(qs)
                return self.send_json(data, status)
            if path == '/api/health':
                with connect() as conn:
                    records = conn.execute('SELECT COUNT(*) FROM flights').fetchone()[0]
                return self.send_json({'ok': True, 'database': str(DB_FILE), 'records': records})
            return self.send_json({'error': 'not found'}, 404)
        except Exception as exc:
            return self.send_json({'error': str(exc)}, 500)
