#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Convert a flight_daily CSV snapshot into the SQLite database used by ffl_calendar."""

import argparse
import csv
import sqlite3
from datetime import datetime
from pathlib import Path


def csv_bool(value):
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "t", "✓"}


def parse_datetime(date_text, time_text):
    return datetime.strptime(f"{date_text} {time_text}", "%Y-%m-%d %H:%M")


def normalize_row(row):
    origin = (row.get("origin") or row.get("departure_airport") or "").strip().upper()
    destination = (row.get("destination") or row.get("arrival_airport") or "").strip().upper()
    dep_date = (row.get("departure_date") or row.get("query_date") or "").strip()
    dep_time = (row.get("departure_time") or "").strip()
    arr_date = (row.get("arrival_date") or dep_date).strip()
    arr_time = (row.get("arrival_time") or "").strip()
    flight_no = (row.get("flight_no") or "").strip().upper()
    if not all([origin, destination, dep_date, dep_time, arr_date, arr_time, flight_no]):
        return None

    try:
        dep_dt = parse_datetime(dep_date, dep_time)
        arr_dt = parse_datetime(arr_date, arr_time)
    except ValueError:
        return None

    try:
        duration = int(float(row.get("duration_minutes") or 0))
    except Exception:
        duration = int((arr_dt - dep_dt).total_seconds() // 60)

    try:
        stop_quantity = int(float(row.get("stop_quantity") or 0))
    except Exception:
        stop_quantity = 0

    return (
        origin,
        (row.get("origin_name") or row.get("departure_city") or origin).strip(),
        destination,
        (row.get("destination_name") or row.get("arrival_city") or destination).strip(),
        flight_no,
        (row.get("operating_flight_no") or flight_no).strip().upper(),
        dep_date,
        dep_time,
        arr_date,
        arr_time,
        duration,
        (row.get("aircraft") or "").strip(),
        1 if str(row.get("code_share") or "").lower() == "true" else 0,
        stop_quantity,
        1 if csv_bool(row.get("flight_running", True)) else 0,
        (row.get("b_status") or "").strip(),
        1 if csv_bool(row.get("b_expected_or_seen")) else 0,
        1 if csv_bool(row.get("b_visible_raw")) else 0,
        1 if csv_bool(row.get("holiday_blocked")) else 0,
        (row.get("status_666") or "").strip(),
        1 if csv_bool(row.get("eligible_666")) else 0,
        (row.get("status_2666") or "").strip(),
        1 if csv_bool(row.get("eligible_2666")) else 0,
    )


SCHEMA = """
CREATE TABLE flights (
    id INTEGER PRIMARY KEY,
    origin TEXT NOT NULL,
    origin_name TEXT NOT NULL,
    destination TEXT NOT NULL,
    destination_name TEXT NOT NULL,
    flight_no TEXT NOT NULL,
    operating_flight_no TEXT NOT NULL,
    departure_date TEXT NOT NULL,
    departure_time TEXT NOT NULL,
    arrival_date TEXT NOT NULL,
    arrival_time TEXT NOT NULL,
    duration_minutes INTEGER NOT NULL DEFAULT 0,
    aircraft TEXT NOT NULL DEFAULT '',
    code_share INTEGER NOT NULL DEFAULT 0,
    stop_quantity INTEGER NOT NULL DEFAULT 0,
    flight_running INTEGER NOT NULL DEFAULT 1,
    b_status TEXT NOT NULL DEFAULT '',
    b_expected_or_seen INTEGER NOT NULL DEFAULT 0,
    b_visible_raw INTEGER NOT NULL DEFAULT 0,
    holiday_blocked INTEGER NOT NULL DEFAULT 0,
    status_666 TEXT NOT NULL DEFAULT '',
    eligible_666 INTEGER NOT NULL DEFAULT 0,
    status_2666 TEXT NOT NULL DEFAULT '',
    eligible_2666 INTEGER NOT NULL DEFAULT 0,
    UNIQUE(origin, destination, flight_no, departure_date, departure_time, arrival_date, arrival_time)
);
CREATE INDEX idx_flights_date_origin ON flights(departure_date, origin);
CREATE INDEX idx_flights_origin_departure ON flights(origin, departure_date, departure_time);
CREATE INDEX idx_flights_origin_destination ON flights(origin, destination);
CREATE INDEX idx_flights_flight_no ON flights(flight_no);
"""

INSERT_SQL = """
INSERT OR IGNORE INTO flights (
    origin, origin_name, destination, destination_name, flight_no, operating_flight_no,
    departure_date, departure_time, arrival_date, arrival_time, duration_minutes, aircraft,
    code_share, stop_quantity, flight_running, b_status, b_expected_or_seen, b_visible_raw,
    holiday_blocked, status_666, eligible_666, status_2666, eligible_2666
) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
"""


def convert(csv_path, db_path):
    csv_path = Path(csv_path)
    db_path = Path(db_path)
    if not csv_path.exists():
        raise FileNotFoundError(csv_path)

    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    total = inserted = 0
    batch = []
    with sqlite3.connect(db_path) as conn:
        conn.executescript(SCHEMA)
        with csv_path.open("r", encoding="utf-8-sig", newline="") as source:
            for row in csv.DictReader(source):
                total += 1
                normalized = normalize_row(row)
                if normalized is None:
                    continue
                batch.append(normalized)
                if len(batch) >= 5000:
                    before = conn.total_changes
                    conn.executemany(INSERT_SQL, batch)
                    inserted += conn.total_changes - before
                    batch.clear()
            if batch:
                before = conn.total_changes
                conn.executemany(INSERT_SQL, batch)
                inserted += conn.total_changes - before
        conn.execute("ANALYZE")
        conn.commit()
        row_count = conn.execute("SELECT COUNT(*) FROM flights").fetchone()[0]
        date_min, date_max = conn.execute(
            "SELECT MIN(departure_date), MAX(departure_date) FROM flights"
        ).fetchone()

    print(f"CSV rows: {total:,}")
    print(f"Database rows: {row_count:,} (inserted {inserted:,})")
    print(f"Date range: {date_min} ~ {date_max}")
    print(f"Database: {db_path} ({db_path.stat().st_size / 1024 / 1024:.1f} MiB)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert flight_daily.csv to SQLite")
    parser.add_argument("csv", nargs="?", default="data/flight_daily.csv")
    parser.add_argument("db", nargs="?", default="data/flights.db")
    args = parser.parse_args()
    convert(args.csv, args.db)
