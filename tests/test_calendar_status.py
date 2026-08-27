import unittest
import app


class CalendarStatusTest(unittest.TestCase):
    def _pek_hgh(self, membership="all"):
        rows = app.STORE.routes_from("PEK", membership=membership, query="HGH")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["destination"], "HGH")
        return rows[0]

    def test_database_fields_loaded(self):
        sample = next(f for f in app.STORE.flights if f["origin"] == "PEK" and f["destination"] == "HGH")
        self.assertIn("b_status", sample)
        self.assertIn("b_expected_or_seen", sample)
        self.assertIn("eligible_666", sample)
        self.assertIn("eligible_2666", sample)

    def test_pek_hgh_calendar_all(self):
        route = self._pek_hgh("all")
        self.assertEqual(route["operating_days"], 54)
        self.assertIn("2026-09-01", route["b_candidate_dates"])
        self.assertIn("2026-10-01", route["running_only_dates"])
        self.assertNotIn("2026-10-01", route["b_candidate_dates"])
        self.assertIn("2026-10-01", route["holiday_blocked_dates"])

    def test_pek_hgh_calendar_666(self):
        route = self._pek_hgh("666")
        self.assertIn("2026-09-01", route["b_candidate_dates"])
        self.assertIn("2026-10-01", route["running_only_dates"])

    def test_pek_hgh_calendar_2666(self):
        route = self._pek_hgh("2666")
        self.assertIn("2026-09-01", route["b_candidate_dates"])
        self.assertIn("2026-10-01", route["running_only_dates"])

    def test_city_origin_resolution(self):
        codes, name, aggregate = app.STORE.resolve_origins("北京")
        self.assertEqual(name, "北京")
        self.assertTrue(aggregate)
        self.assertEqual(set(codes), {"PEK", "PKX"})

    def test_route_weekday_filter(self):
        rows = app.STORE.routes_from("PEK", membership="666", weekday="2")
        self.assertTrue(rows)
        for route in rows:
            self.assertEqual(route["schedule"], "2")
            self.assertTrue(all(__import__("datetime").date.fromisoformat(d).isoweekday() == 2 for d in route["operating_dates"]))

    def test_city_overview_aggregates_origins(self):
        rows = app.STORE.routes_from("北京", membership="all")
        self.assertTrue(rows)
        self.assertTrue(all(route["aggregate"] for route in rows))
        seen_origins = set(code for route in rows for code in route["origin_codes"])
        self.assertTrue({"PEK", "PKX"}.issubset(seen_origins))

    def test_pek_hgh_schedule_time_tolerance(self):
        route = self._pek_hgh("all")
        # 同一航班号的 5~30 分钟轻微时刻变化应合并成一个主时刻。
        self.assertEqual(route["flight_nos"], ["HU7177", "HU7277", "HU7377", "HU7577"])
        self.assertEqual(
            [(x["departure_time"], x["arrival_time"], x["cross_day"]) for x in route["times"]],
            [
                ("21:00", "23:20", 0),
                ("08:00", "10:15", 0),
                ("22:05", "00:25", 1),
                ("06:55", "09:15", 0),
            ],
        )
        self.assertEqual([x["observations"] for x in route["times"]], [54, 54, 54, 54])


if __name__ == "__main__":
    unittest.main()
