import json
import unittest
from unittest.mock import patch

import app
import facets
import server


class JevFilterTests(unittest.TestCase):
    def setUp(self):
        facets._jev_cache.clear()
        self.cards = [
            {'id': 1, 'title': 'کرم پوست خشک', '_t': facets.norm('کرم پوست خشک'), 'brand': 'A'},
            {'id': 2, 'title': 'کرم مرطوب کننده', '_t': facets.norm('کرم مرطوب کننده'), 'brand': 'A'},
            {'id': 3, 'title': 'کرم پوست چرب', '_t': facets.norm('کرم پوست چرب'), 'brand': 'B'},
        ]

    def test_prompt_includes_grouped_conditions_and_invalidates_old_cache(self):
        conds = [('نوع پوست', 'پوست خشک'), ('نوع پوست', 'پوست حساس'), ('بافت', 'کرم')]
        old_key = 'test|' + '&'.join(sorted(f'{g}:{facets.norm(v)}' for g, v in conds))
        facets._jev_cache[old_key] = (facets.time.time(), {'2': 0.1})
        with patch.object(server, '_jev', return_value={'2': {'noul': 0.8}}) as jev:
            result = facets._jev_score_multi('test', conds, [self.cards[1]])
        self.assertEqual(result['2'], 0.8)
        need = jev.call_args.args[0]['need']
        self.assertIn('«پوست خشک» یا «پوست حساس»', need)
        self.assertIn('«کرم»', need)
        self.assertIn('«بافت»', need)
        self.assertIn('«نوع پوست»', need)

    def test_bypass_preserves_direct_and_explicit_filters(self):
        with patch.object(facets, 'get_products', return_value=self.cards), patch.object(facets, 'facets_for', return_value=[]), patch.object(server, '_jev') as jev:
            result = facets.apply_filters('test', [('نوع پوست', 'پوست خشک'), ('برند', 'A')], bypass_jev=True)
        jev.assert_not_called()
        self.assertEqual([c['id'] for c in result['items']], [1])
        self.assertEqual(result['mode'], 'jev-bypass')
        self.assertEqual(result['stats']['jev_called'], 0)

    def test_default_still_calls_jev_for_ambiguous_products(self):
        with patch.object(facets, 'get_products', return_value=self.cards), patch.object(facets, 'facets_for', return_value=[]), patch.object(server, '_jev', return_value={'2': {'noul': 0.8}}) as jev:
            result = facets.apply_filters('test', [('نوع پوست', 'پوست خشک')])
        jev.assert_called_once()
        self.assertEqual([c['id'] for c in result['items']], [1, 2])

    def test_rank_forwards_bypass(self):
        with patch.object(facets, 'apply_filters', return_value={'error': 'test'}) as filters:
            facets.tiered_rank('test', [('بافت', 'کرم')], bypass_jev=True)
        filters.assert_called_once_with('test', [('بافت', 'کرم')], bypass_jev=True)

    def test_http_routes_forward_bypass_and_default(self):
        for route, function in [('filter', 'apply_filters'), ('rank', 'tiered_rank')]:
            for query, expected in [('', False), ('&bypass_jev=1', True), ('&bypass_jev=true', True)]:
                with self.subTest(route=route, query=query):
                    handler = object.__new__(app.Handler)
                    handler.path = f'/api/{route}?q=test&group=brand&value=A{query}'
                    handler._send = lambda *args: None
                    with patch.object(facets, function, return_value={'items': []}) as target:
                        handler.do_GET()
                    target.assert_called_once_with('test', [('brand', 'A')], bypass_jev=expected)


if __name__ == '__main__':
    unittest.main()
