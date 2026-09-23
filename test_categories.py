import json
import unittest
from unittest.mock import patch
import app
import facets
import server


class CategoryTests(unittest.TestCase):
    def detect(self, slugs):
        def get(url, params=None):
            if '/search/' in url:
                return {'data': {'products': [{'id': i+1, 'title_fa': 'test'} for i in range(len(slugs))]}}
            i = int(url.rstrip('/').split('/')[-1]) - 1
            if slugs[i] is None:
                raise RuntimeError('unavailable')
            return {'data': {'product': {'category': {'id': i, 'code': slugs[i], 'title_fa': slugs[i]}}}}
        with patch.object(server, '_get', side_effect=get):
            return json.loads(server.detect_categories('test'))

    def test_five_same_auto(self):
        r = self.detect(['cream'] * 5)
        self.assertEqual(r['selected_category']['slug'], 'cream')
        self.assertFalse(r['requires_choice'])
        self.assertEqual(r['categories'][0]['count'], 5)

    def test_mixed_requires_choice(self):
        r = self.detect(['cream', 'cream', 'shampoo', 'soap', 'soap'])
        self.assertIsNone(r['selected_category'])
        self.assertTrue(r['requires_choice'])
        self.assertEqual(len(r['categories']), 3)

    def test_missing_or_short_sample_never_auto(self):
        for sample in [['cream']*4+[None], ['cream']*3, []]:
            self.assertIsNone(self.detect(sample)['selected_category'])

    def test_category_pool_uses_category_endpoint_without_query(self):
        with patch.object(server, '_get', return_value={'data': {'products': [], 'pager': {'total_pages': 1}}}) as get:
            facets._search_products('@category:cream')
        get.assert_called_once_with(server.API+'/categories/cream/search/', {'page': 1})

    def test_browse_page_is_not_capped_to_pool(self):
        h=object.__new__(app.Handler)
        h.path='/api/search?q=old&category=cream&page=25'
        sent=[]
        h._send=lambda *args: sent.append(args)
        with patch.object(server, '_get', return_value={'data': {'products': [], 'pager': {'total_pages': 50}}}) as get:
            h.do_GET()
        get.assert_called_once_with(server.API+'/categories/cream/search/', {'page': 25})
        self.assertEqual(sent[0][0], 200)

    def test_category_filters_use_distinct_cache_scope(self):
        h=object.__new__(app.Handler)
        h.path='/api/rank?q=old&category=cream&bypass_jev=1'
        h._send=lambda *args: None
        with patch.object(facets,'tiered_rank',return_value={}) as rank:
            h.do_GET()
        rank.assert_called_once_with('@category:cream',[],bypass_jev=True)

    def test_invalid_slug_rejected(self):
        h=object.__new__(app.Handler)
        h.path='/api/search?q=test&category=../invalid'
        sent=[]
        h._send=lambda *args: sent.append(args)
        h.do_GET()
        self.assertEqual(sent[0][0],400)
