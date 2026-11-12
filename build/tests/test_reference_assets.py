"""전수 점검: 참조 원본·현행/연혁 구분·여러 쪽 표·외부 규격 오연결 방지."""
import collections
import copy
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile
import unittest
from browser_support import browser_path, link_directory

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'build'))
from reference_assets import build_reference_assets, build_context_asset_links


class ReferenceAssets(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.base = Path(cls.temp.name)
        (cls.base / 'fig').mkdir()
        for name in ('hist_src', 'hist_es'):
            link_directory(cls.base / name, ROOT / 'build' / name)
        link_directory(cls.base / 'stdimg', ROOT / 'stdimg')
        shutil.copy2(ROOT / 'build/reference_assets_map.json', cls.base / 'reference_assets_map.json')
        for p in (ROOT / 'fig').glob('*.webp'):
            if not p.name.startswith('ref_'):
                shutil.copy2(p, cls.base / 'fig' / p.name)
        html = (ROOT / 'index.html').read_text()
        cls.data = json.loads(re.search(r'<script id="data" type="application/json">(.*?)</script>', html, re.S)[1])
        cls.before = copy.deepcopy(cls.data)
        cls.catalog, cls.aliases = build_reference_assets(cls.data, cls.base)
        cls.std_links, cls.history_links = build_context_asset_links(cls.data, cls.catalog, cls.base)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_all_121_current_tables_and_figures_are_indexed(self):
        counts = collections.Counter((a['src'], a['kind']) for a in self.catalog.values()
                                     if a['src'] != 'std' and not a.get('historical'))
        self.assertEqual(counts, {('b22','table'):29, ('b22','figure'):57,
                                  ('b24','table'):14, ('b24','figure'):21})

    def test_all_catalog_images_exist_with_exact_dimensions(self):
        for key, asset in self.catalog.items():
            self.assertTrue(asset['pages'], key)
            for page in asset['pages']:
                with Image.open(self.base / page.get('folder', 'fig') / page['file']) as image:
                    self.assertEqual(image.size, (page['width'], page['height']), key)

    def test_every_original_card_and_history_image_has_a_readable_file(self):
        files = {}
        def inspect(text):
            for m in re.finditer(r'\x10([^|]+)\|(\d+)\|(\d+)\x0e', text):
                files[('stdimg' if m[1].startswith('stb_') else 'fig', m[1])] = (int(m[2]), int(m[3]))
        for src in ('b22','b24','std','fail'):
            for entry in self.data[src]:
                inspect(entry['text'])
                for image in entry.get('img', []):
                    files[('stdimg', image[0])] = (image[2], image[3])
        for key in ('hist','hist_es'):
            for history in self.data[key].values():
                for block in history['blocks']:
                    inspect(block['text'])
        for (folder, filename), dimensions in files.items():
            with Image.open(ROOT / folder / filename) as image:
                self.assertEqual(image.size, dimensions, filename)
                self.assertLess(image.convert('L').getextrema()[0],245,'Empty image: '+filename)
                image.verify()
        self.assertEqual(len(files), 670)
        print('Original card/history image files verified:', len(files))

    def test_multi_page_tables_include_first_rows_and_last_page(self):
        expected = {'b22-table-XⅢ.7':[369,370,371,372,373],
                    'b22-table-Ⅻ.1':[359,360,361,362,363],
                    'b22-table-XⅢ.2':[364,365], 'b22-table-XⅢ.3':[365,366],
                    'b24-table-8':[89,90], 'b24-table-11':[120,121,122],
                    'b24-table-Ⅱ.1':[139,140,141], 'b24-table-1':[16,17,18]}
        for key, pages in expected.items():
            self.assertEqual([p['page'] for p in self.catalog[key]['pages']], pages, key)
        self.assertNotIn('hes_p141_0.webp', [p['file'] for p in self.catalog['b24-table-Ⅱ.1']['pages']])

    def test_duplicate_numbers_retain_distinct_originals(self):
        self.assertNotEqual(self.catalog['b22-table-16']['owner'], self.catalog['b22-table-16-verification']['owner'])
        self.assertNotEqual(self.catalog['b22-figure-Ⅷ.1']['owner'], self.catalog['b22-figure-Ⅷ.1-p331']['owner'])
        self.assertNotEqual(self.catalog['b22-figure-Ⅹ.2']['pages'], self.catalog['b22-figure-Ⅹ.2-p352']['pages'])

    def test_standardization_uses_matching_version_and_excludes_KS_table_four(self):
        for entry in ('std-424','std-461','std-610','std-694','std-704'):
            self.assertNotIn('table-4', self.std_links.get(entry, {}), entry)
        self.assertEqual(self.std_links['std-722']['figure-20'], ['b22-figure-20'])
        for entry in ('std-304', 'std-315'):
            key = self.std_links[entry]['figure-4'][0]
            self.assertTrue(self.catalog[key]['historical'])
            self.assertEqual(self.catalog[key]['pages'][0]['page'], 178)
        key = self.std_links['std-206']['figure-2'][0]
        self.assertTrue(self.catalog[key]['historical'])
        self.assertEqual([p['page'] for p in self.catalog[key]['pages']], [66,66,67])
        self.assertEqual(self.std_links['std-77']['figure-1'], ['std-77-figure-1'])

    def test_original_text_and_history_are_never_rewritten(self):
        self.assertEqual(self.before, self.data)
        self.assertEqual(self.aliases[0]['entry'], 'b22-Ⅻ')
        self.assertEqual(self.aliases[0]['target'], 'b22-table-Ⅻ.1')


if __name__ == '__main__':
    unittest.main()
