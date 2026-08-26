import unittest
import app


class CalendarStatusTest(unittest.TestCase):
    def _pek_hgh(self, membership="all"):
        rows = app.STORE.routes_from("PEK", membership=membership, query="HGH")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["destination"], "HGH")
        return rows[0]

    def test_new_csv_fields_loaded(self):
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
