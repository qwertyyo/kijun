"""직접 원문 대조에서 확인된 잘림·식 순서 회귀를 검사한다."""
from pathlib import Path
import json
import re
import sys
import unittest

import pymupdf

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'build'))
from reviewed_crops import EL, STD, reviewed_std_clip


class ReviewedCrops(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(re.search(r'<script id="data" type="application/json">(.*?)</script>',
                                       (ROOT / 'index.html').read_text(), re.S)[1])

    def test_reviewed_equations_are_not_split_into_right_hand_fragments(self):
        entries = {e['id']: e for e in self.data['b22']}
        for number, count in [('Ⅷ.6', 1), ('Ⅷ.7.2.1.2', 1),
                              ('Ⅷ.7.2.1.3', 1), ('Ⅷ.7.2.1.4', 1), ('Ⅷ.7.2.1.5', 1)]:
            self.assertEqual(len(re.findall(r'\x10[^|]+\|', entries['b22-' + number]['text'])), count, number)
        self.assertEqual(len(re.findall(r'\x10hel_p337_[^|]+\|', entries['b22-Ⅷ.7.2.1.1']['text'])), 2)

    def test_omega_polynomial_exponents_keep_their_original_superscripts(self):
        entry = next(e for e in self.data['b22'] if e['id'] == 'b22-Ⅷ.3')
        regions = re.findall(r'\x10([^|]+)\|\d+\|\d+\x0e([^\x11]*)\x11', entry['text'])
        # 370MPa의 3줄, 다음 쪽의 이어지는 1줄, 520MPa의 4줄.
        for coefficient in ['0.00012920', '0.00016887', '0.00008240']:
            self.assertTrue(any(coefficient in text for _, text in regions), coefficient)

    def test_reviewed_source_regions_are_in_bounds_and_do_not_overlap(self):
        with pymupdf.open(ROOT / 'build/hist_src/hist.pdf') as doc:
            for pn, bounds in EL.items():
                regions = [pymupdf.Rect(b) for b in bounds]
                for i, region in enumerate(regions):
                    self.assertTrue(doc[pn - 1].rect.contains(region), pn)
                    self.assertFalse(any(region.intersects(other) for other in regions[i + 1:]), pn)

    def test_change_annotations_are_fully_inside_the_new_photo_crop(self):
        with pymupdf.open(ROOT / 'build/stdzip/std.pdf') as doc:
            for (pn, x, y), bounds in STD.items():
                clip = reviewed_std_clip(pn, (x, y, x + 10, y + 10), (0, 0, 1, 1))
                self.assertTrue(doc[pn - 1].rect.contains(clip), pn)
                matches = [pymupdf.Rect(line['bbox']) for block in doc[pn - 1].get_text('dict')['blocks']
                           for line in block.get('lines', [])
                           if any('변동' in s['text'] or '수정안내' in s['text'] for s in line['spans'])]
                self.assertTrue(matches, pn)
                self.assertTrue(all(clip.contains(b) for b in matches), (pn, matches, bounds))

    def test_wear_length_figure_does_not_include_the_preceding_table(self):
        config = json.loads((ROOT / 'build/reference_assets_map.json').read_text())
        asset = next(a for a in config['assets'] if a['key'] == 'b22-figure-Ⅳ.1')
        clip = pymupdf.Rect(asset['clips'][0][1:])
        self.assertGreater(clip.y0, 450)
        self.assertTrue(asset['versioned'])

    def test_decorative_header_is_not_an_escalator_figure(self):
        entry = next(e for e in self.data['b24'] if e['id'] == 'b24-Ⅰ.6')
        self.assertNotIn('hes_p134_1.webp', entry['text'])
        figures = re.findall(r'\x10([^|]+)\|(\d+)\|(\d+)\x0e', entry['text'])
        self.assertTrue(figures)
        for filename, width, height in figures:
            if filename.startswith('hes_p134_'):
                self.assertGreater(int(width), 250, filename)
                self.assertGreater(int(height), 250, filename)


if __name__ == '__main__':
    unittest.main()
