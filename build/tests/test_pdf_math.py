"""잘못된 수식 괄호 bbox가 빈 세로 그림을 만드는 회귀를 검사한다."""
from collections import Counter
from pathlib import Path
import sys
import unittest

import pymupdf

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT / 'build'))
from pdf_math import prepare_math_rows
from restore_eq import restore


class PdfMath(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc=pymupdf.open(ROOT / 'build/hist_src/hist.pdf')
        cls.rows=[]
        for block in cls.doc[350].get_text('rawdict')['blocks']:
            for line in block.get('lines',[]):
                first=line['spans'][0]
                text=''.join(c['c'] for span in line['spans'] for c in span['chars'])
                if text.strip():
                    cls.rows.append((line['bbox'][1],line['bbox'][0],first['font'],round(first['size']),text,line))

    @classmethod
    def tearDownClass(cls):
        cls.doc.close()

    def test_six_phantom_extenders_are_removed_without_losing_other_text(self):
        rows,discarded=prepare_math_rows(self.rows)
        self.assertEqual(len(discarded),6)
        self.assertEqual(Counter(r[4] for r in rows)+Counter(r[4] for r in discarded),Counter(r[4] for r in self.rows))
        self.assertTrue(all(r[4] in ('\ue07d','\ue080') for r in discarded))

    def test_symbol_definitions_share_their_description_line(self):
        rows,_=prepare_math_rows(self.rows)
        for symbol,description in [('Sf','= 안전율'),('Dt','= 권상 도르래의 직경'),('dr','= 로프의 직경')]:
            left=next(r for r in rows if r[1]<100 and restore(r[4]).strip()==symbol)
            right=next(r for r in rows if r[4].strip()==description)
            self.assertEqual(left[0],right[0])
            self.assertLess(left[1],right[1])


if __name__ == '__main__':
    unittest.main()
