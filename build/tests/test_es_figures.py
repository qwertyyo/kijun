"""원문 그림 제목·조문 연결을 검증한다. python build/tests/test_es_figures.py -v"""
import copy
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile
import unittest

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'build'))
from es_figures import build_figures, figure_references


class EscalatorFigures(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        base = Path(cls.temp.name)
        (base / 'hist_es').mkdir()
        shutil.copy2(ROOT / 'build/es_figures_map.json', base / 'es_figures_map.json')
        shutil.copy2(ROOT / 'build/hist_es/standard_2022.pdf', base / 'hist_es/standard_2022.pdf')
        html = (ROOT / 'index.html').read_text()
        cls.original = json.loads(re.search(r'<script id="data" type="application/json">(.*?)</script>', html, re.S)[1])['b24']
        cls.entries = copy.deepcopy(cls.original)
        cls.catalog = build_figures(cls.entries, base)
        cls.by_num = {e['num']: e for e in cls.entries}

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def refs(self, number):
        return {r['id'] for r in self.by_num[number].get('figure_refs', [])}

    def test_twenty_captions_and_nonempty_image_files(self):
        expected = {str(n) for n in range(1, 15)} | {f'Ⅰ.{n}' for n in range(1, 5)} | {'Ⅴ.1', 'Ⅴ.2'}
        self.assertEqual(set(self.catalog), expected)
        for figure in self.catalog.values():
            with Image.open(Path(self.temp.name) / 'fig' / figure['file']) as image:
                self.assertEqual(image.size, (figure['width'], figure['height']))
                self.assertGreater(image.width, 400)
                self.assertGreater(image.height, 400)
                self.assertGreater(image.convert('L').getextrema()[1] - image.convert('L').getextrema()[0], 100)

    def test_figure_five_keeps_drawing_and_dimension_table_together(self):
        figure = self.catalog['5']
        self.assertEqual(figure['pages'], [30, 31])
        self.assertGreater(figure['height'], 2 * figure['width'])

    def test_explicit_references_and_dimension_table_associations(self):
        self.assertEqual(self.refs('5.3.3.2.1'), {'1', '2'})
        self.assertEqual(self.refs('5.3.2.2.5'), {'5'})
        self.assertEqual(self.refs('5.3.2.2.1'), {'8'})
        self.assertEqual(self.refs('5.6.2.1'), {'6', '7'})
        self.assertEqual(self.refs('Ⅰ.2.3'), {'Ⅰ.1'})
        self.assertEqual(self.refs('Ⅰ.2.7'), {'Ⅰ.3'})
        self.assertEqual(self.refs('Ⅰ.5'), {'Ⅰ.3', 'Ⅰ.4'})
        self.assertEqual(self.refs('Ⅰ.6'), set())
        self.assertEqual(self.refs('Ⅰ'), {'Ⅰ.1', 'Ⅰ.2', 'Ⅰ.3', 'Ⅰ.4'})
        self.assertEqual(self.refs('5.10'), set())
        self.assertEqual(self.refs('5'), {'5', '6', '7', '8', '9', '10', '11'})
        self.assertEqual(self.refs('Ⅴ'), {'Ⅴ.1', 'Ⅴ.2'})
        reasons = {r['id']: r['reason'] for r in self.by_num['5.6.2.1']['figure_refs']}
        self.assertIn('본문 참조', reasons['6'])
        self.assertIn('치수·기호표', reasons['7'])

    def test_all_known_current_references_have_matching_figures(self):
        for entry in self.entries:
            expected = set(figure_references(entry['text'])) & self.catalog.keys()
            self.assertLessEqual(expected, self.refs(entry['num']), entry['num'])
            self.assertEqual(len(entry.get('figure_refs', [])), len(self.refs(entry['num'])))

    def test_original_clause_text_and_history_inputs_are_unchanged(self):
        for before, after in zip(self.original, self.entries):
            before = {k: v for k, v in before.items() if k != 'figure_refs'}
            after = {k: v for k, v in after.items() if k != 'figure_refs'}
            self.assertEqual(before, after)

    def test_compound_roman_ranges_and_old_image_captions(self):
        self.assertEqual(figure_references('그림 5 및 7, 그림 I.1 및 Ⅰ.2 참조'), ['5', '7', 'Ⅰ.1', 'Ⅰ.2'])
        self.assertEqual(figure_references('그림 5~7 참조'), ['5', '6', '7'])
        self.assertEqual(figure_references('[그림 11 - 옛 그림]\n\x10old.webp|1|1\x0e그림 2\x11'), [])
        self.assertEqual(figure_references('그림 5.2와 표 6, 5.6.2.1 및 2022.01.01'), [])


if __name__ == '__main__':
    unittest.main()
