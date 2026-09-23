import unittest
import json
import threading
from urllib.request import urlopen
from urllib.error import HTTPError
from http.server import ThreadingHTTPServer
from unittest.mock import patch
import app
import facets
import server


class RegressionTests(unittest.TestCase):
    def setUp(self):
        facets._products_cache.clear()
        facets._sorts_cache.clear()

    def test_outage_not_cached_and_recovery(self):
        with patch.object(server, '_get', side_effect=RuntimeError('offline')):
            with self.assertRaises(RuntimeError):
                facets.get_products('test')
        self.assertNotIn('test', facets._products_cache)
        with patch.object(server, '_get', return_value={'data': {'products': [], 'pager': {'total_pages': 0}}}) as get:
            self.assertEqual(facets.get_products('test'), [])
            get.assert_called_once()
        self.assertIn('test', facets._products_cache)

    def test_partial_failure_not_cached(self):
        def get(url, params):
            if params['page'] == 2:
                raise RuntimeError('page failed')
            return {'data': {'products': [], 'pager': {'total_pages': 2}}}
        with patch.object(server, '_get', side_effect=get):
            with self.assertRaises(RuntimeError):
                facets.get_products('test')
        self.assertNotIn('test', facets._products_cache)

    def test_volumes(self):
        for title in ['کرم 1.5 میلی لیتر', 'کرم ۱٫۵ میلی‌لیتر']:
            self.assertEqual(facets.unit_price({'title': title, 'price_toman': 150000}), (10000000, 'ml'))
        self.assertEqual(facets.unit_price({'title': 'کرم ۰ میلی لیتر', 'price_toman': 150000}), (None, None))
        self.assertEqual(facets.unit_price({'title': 'کرم 50 ml بسته 2 عددی', 'price_toman': 150000}), (150000, '×2ml'))
        self.assertEqual(facets.unit_price({'title': 'کرم 50 ml و 20 گرم', 'price_toman': 150000}), (None, None))
        self.assertFalse(facets._direct_match({'_t': 'کرم 50 گرم'}, 'حجم', '50 میلی لیتر'))
        self.assertTrue(facets._direct_match({'_t': 'کرم 50 میلی لیتر'}, 'حجم', '50 ml'))

    def test_rank_ignores_unavailable_and_zero_price(self):
        cards = [{'id': i, 'title': 'test', 'in_stock': stock, 'price_toman': price, 'rating_pct': 80, 'votes': 100}
                 for i, stock, price in [(1, False, 0), (2, True, 0), (3, True, 100), (4, True, 200), (5, True, 300)]]
        with patch.object(facets, 'get_products', return_value=cards), patch.object(facets, 'facets_for', return_value=[]):
            result = facets.tiered_rank('test', [])
        self.assertEqual({c['id'] for t in result['tiers'] for c in t['items']}, {3, 4, 5})

    def test_smart_pick_zero_match_excluded(self):
        products = [{'id': i, 'title_fa': 'test', 'status': 'marketable', 'rating': {'rate': rate, 'count': 10000}}
                    for i, rate in [(1, 100), (2, 20)]]
        with patch.object(server, '_get', return_value={'data': {'products': products}}), patch.object(server, '_jev', return_value={'1': {'noul': 0}, '2': {'noul': .5}}):
            result = json.loads(server.smart_pick('test', 'test'))
        self.assertEqual([c['id'] for c in result['items']], [2])
        self.assertEqual(result['items'][0]['final'], round(.5 * server._bayes(20, 10000), 3))

    def test_http_invalid_page_is_400(self):
        http = ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
        thread = threading.Thread(target=http.serve_forever, daemon=True)
        thread.start()
        try:
            for value in ['abc', '0', '-1', '1.5']:
                with self.assertRaises(HTTPError) as caught:
                    urlopen(f'http://127.0.0.1:{http.server_port}/api/search?q=test&page={value}')
                self.assertEqual(caught.exception.code, 400)
                self.assertIn('error', json.loads(caught.exception.read()))
        finally:
            http.shutdown()
            http.server_close()
            thread.join()

    def test_original_facets_restored(self):
        cards = [{'id': i, 'title': title, '_t': facets.norm(title)}
                 for i, title in enumerate(['کرم پوست خشک', 'کرم پوست خشک', 'کرم پوست چرب', 'کرم پوست چرب'])]
        with patch.object(facets, 'get_products', return_value=cards):
            groups = facets.facets_for('کرم')
        self.assertIn('نوع پوست', [g['group'] for g in groups])
        self.assertFalse(any('عبارت عنوان' in g['group'] for g in groups))


if __name__ == '__main__':
    unittest.main()
