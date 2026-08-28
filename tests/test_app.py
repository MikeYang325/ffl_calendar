import unittest
import app

class StoreTest(unittest.TestCase):
    def test_meta(self):
        meta = app.STORE.meta()
        self.assertGreater(meta['flight_records'], 40000)
        self.assertEqual(meta['date_min'], '2026-09-01')
        self.assertEqual(meta['date_max'], '2026-10-24')

    def test_pek_routes(self):
        self.assertEqual(len(app.STORE.routes_from('PEK')), 29)

    def test_pek_ckg(self):
        results = app.STORE.search('PEK','CKG','2026-09-01',max_stops=0)
        self.assertGreaterEqual(len(results), 1)

    def test_666_rule(self):
        self.assertEqual(app.product_for_departure('07:59'), '666')
        self.assertEqual(app.product_for_departure('08:00'), '2666')
        self.assertEqual(app.product_for_departure('20:00'), '2666')
        self.assertEqual(app.product_for_departure('20:01'), '666')

if __name__ == '__main__':
    unittest.main()
