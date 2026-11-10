"""표 Ⅱ.1이 현행 세 쪽을 가리키고 과거 3.6을 섞지 않는지 검사한다."""
import copy
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'build'))
from es_tables import build_tables


class EscalatorTables(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.base = Path(cls.temp.name)
        (cls.base / 'fig').symlink_to(ROOT / 'fig', target_is_directory=True)
        (cls.base / 'hist_es').symlink_to(ROOT / 'build/hist_es', target_is_directory=True)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        html = (ROOT / 'index.html').read_text()
        self.entries = json.loads(re.search(
            r'<script id="data" type="application/json">(.*?)</script>', html, re.S)[1])['b24']

    def test_current_table_complete_without_historical_row(self):
        before = copy.deepcopy(self.entries)
        table = build_tables(self.entries, self.base)['Ⅱ.1']
        self.assertEqual([p['page'] for p in table['pages']], [139, 140, 141])
        self.assertEqual([p['file'] for p in table['pages']],
                         ['hes_p139_0.webp', 'hes_p140_0.webp', 'hes_p141_1.webp'])
        self.assertEqual(table['row_pages'], {'3.1': 1, '3.6': 1})
        self.assertEqual(self.entries, before)

    def test_missing_current_page_fails_instead_of_showing_incomplete_table(self):
        entry = next(e for e in self.entries if e['num'] == 'Ⅱ.2')
        entry['text'] = entry['text'].replace('hes_p140_0.webp', 'missing.webp')
        with self.assertRaisesRegex(ValueError, 'hes_p140_0.webp'):
            build_tables(self.entries, self.base)


if __name__ == '__main__':
    unittest.main()
