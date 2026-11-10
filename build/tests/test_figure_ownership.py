"""끝 조문 뒤에 모아 실린 공통 도해를 해당 조문의 내용으로 오인하지 않는다."""
import json
from pathlib import Path
import re
import unittest

import pymupdf

ROOT = Path(__file__).resolve().parents[2]


def compact(text):
    return re.sub(r'\s+', '', text)


class FigureOwnership(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(re.search(r'<script id="data" type="application/json">(.*?)</script>',
                                       (ROOT / 'index.html').read_text(), re.S)[1])
        cls.entries = {e['id']: e for src in ('b22', 'b24') for e in cls.data[src]}

    def test_power_supply_is_exactly_its_own_source_paragraph(self):
        with pymupdf.open(ROOT / 'build/hist_es/hist.pdf') as doc:
            text = doc[130].get_text().split('Ⅰ.6 전력 공급', 1)[1]
        expected = re.sub(r'<[^>]*>', '', text)
        actual = self.entries['b24-Ⅰ.6']
        self.assertEqual(compact(actual['text']), compact(expected))
        self.assertFalse(actual.get('figure_refs'))
        self.assertFalse(self.data['hist_es']['Ⅰ.6']['blocks'])

    def test_transport_does_not_inherit_dimension_and_step_figures(self):
        entry = self.entries['b24-5.10']
        self.assertNotIn('\x10', entry['text'])
        self.assertNotIn('그림', entry['text'])
        self.assertFalse(entry.get('figure_refs'))
        old = self.data['hist_es']['5.10']['blocks']
        self.assertEqual(len(old), 1)
        self.assertIn('양중장치', old[0]['text'])
        self.assertNotIn('\x10', old[0]['text'])

    def test_common_figures_and_their_own_history_are_preserved_under_the_section(self):
        for num, file_prefix, count in [('Ⅰ', 'hes_p13', 5), ('5', 'hes_p6', 11)]:
            entry = self.entries['b24-' + num]
            files = re.findall(r'\x10([^|]+)\|', entry['text'])
            self.assertEqual(len(files), count, num)
            self.assertTrue(any(f.startswith(file_prefix) for f in files), num)
            history = self.data['hist_es'][num]['blocks']
            self.assertTrue(any('\x10' in b['text'] for b in history), num)
            self.assertTrue(all(b.get('g') for b in history), num)

    def test_old_annex_dimensions_stay_in_their_own_history(self):
        self.assertNotIn('hes_p133_1.webp', self.entries['b24-Ⅰ']['text'])
        self.assertNotIn('그림 11', self.entries['b24-Ⅰ']['text'])
        old = self.data['hist_es']['Ⅰ']['blocks'][0]['text']
        self.assertIn('hes_p133_0.webp', old)
        self.assertIn('hes_p133_1.webp', old)
        self.assertRegex(old, r'그림\s+11')

    def test_figure_catalog_and_related_clauses_agree_on_scope(self):
        catalog = self.data['ref_assets']
        for n in range(1, 5):
            self.assertEqual(catalog[f'b24-figure-Ⅰ.{n}']['owner'], 'b24-Ⅰ')
        for n in range(5, 12):
            self.assertEqual(catalog[f'b24-figure-{n}']['owner'], 'b24-5')
        self.assertIn('Ⅰ.2', {r['id'] for r in self.entries['b24-Ⅰ.2.4']['figure_refs']})
        self.assertIn('Ⅰ.3', {r['id'] for r in self.entries['b24-Ⅰ.2.7']['figure_refs']})
        self.assertEqual({r['id'] for r in self.entries['b24-Ⅰ.5']['figure_refs']}, {'Ⅰ.3', 'Ⅰ.4'})

    def test_ladder_types_belong_to_types_not_only_the_last_position_clause(self):
        self.assertNotIn('\x10', self.entries['b22-Ⅶ.5']['text'])
        types = self.entries['b22-Ⅶ.1']
        self.assertIn('hel_p330_0.webp', types['text'])
        self.assertIn('형식 4', types['text'])
        self.assertEqual(self.data['ref_assets']['b22-figure-Ⅷ.1']['owner'], types['id'])


if __name__ == '__main__':
    unittest.main()
