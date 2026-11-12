"""종전 기술조항의 범위·번호·시점과 보완 PDF/게시 데이터의 동일성을 검사한다."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import unittest
import pymupdf

ROOT=Path(__file__).resolve().parents[2]
BUILD=ROOT/'build'
def page_data(text):
    return json.loads(re.search(r'<script id="data" type="application/json">(.*?)</script>',text,re.S)[1])


class LegacyTechnical(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.review=json.loads((BUILD/'hist_incline/legacy_technical.json').read_text(encoding='utf-8'))
        cls.data=page_data((ROOT/'index.html').read_text(encoding='utf-8'))
        cls.audit=json.loads((BUILD/'incline-book-audit.json').read_text(encoding='utf-8'))
        cls.pdf=ROOT/'output/pdf/경사형_엘리베이터_안전기준_연혁집_v0.3.pdf'

    def test_all_42_additions_keep_verified_dates_and_structural_scope(self):
        blocks=[b for h in self.data['hist_incline'].values() for b in h['blocks'] if b.get('legacy_supplement')]
        self.assertEqual(len(blocks),42)
        for block in blocks:
            self.assertIn('유압식',block['applies_to'])
            self.assertRegex(block['from'],r'^201[345]\.\d{2}\.\d{2}$')
            self.assertIsNone(block['to'])
            self.assertTrue(block['legacy_numbering'])
            self.assertTrue(block['reference_only'])
            self.assertIn('준용기준',block['when_label'])
            self.assertNotIn('수록',block['when_label'])
            self.assertRegex(block['head'],r'년 \d+월 \d+일(?:부터 시행| 이후의 건축허가분부터 적용)')
        for num in ('9.17.4','15.2.3.3'):
            oldest=next(b for b in self.data['hist_incline'][num]['blocks'] if b.get('legacy_supplement') and b['from']=='2013.09.15')
            self.assertEqual(oldest['basis'],'시행')
        glass=[b for b in self.data['hist_incline']['8.2.3.4']['blocks'] if b.get('legacy_supplement')]
        self.assertEqual({b['from'] for b in glass},{'2013.09.15','2015.07.02'})
        self.assertEqual(len({v['section_sha256'] for v in self.review['verified_compilations']}),1)
        self.assertEqual([v['compilation'] for v in self.review['verified_compilations']],['2014.10','2016.03','2017.04','2018.02'])

    def test_correspondence_uses_contents_rather_than_adding_one_to_numbers(self):
        pairs={(e['old_num'],e['target']) for e in self.review['entries']}
        for pair in [('7.3.1','8.3.1'),('7.3.2','8.3.2'),('9.13.7','10.11.6'),('9.13.12','10.11.11'),('14.2.1.3','15.2.1.4.1')]:
            self.assertIn(pair,pairs)
        self.assertIn('65 ㎏',next(e['text'] for e in self.review['entries'] if e['old_num']=='14.2.5.2'))
        self.assertIn('75 ㎏',next(e['text'] for e in self.data['b23'] if e['num']=='15.2.5.2'))
        prior=next(e for e in self.review['entries'] if e['old_num']=='9.13.1')
        self.assertIn('정지시킬 수 있는 수단',prior['text'])
        self.assertEqual(prior['g'],'유압식 문열림출발 방지수단 요구')

    def test_original_incline_current_and_55_history_bodies_are_preserved(self):
        prior=page_data(subprocess.check_output(['git','show','be1e2ef:index.html'],cwd=ROOT).decode('utf-8'))
        compact=lambda text:re.sub(r'\s','',text)
        self.assertEqual(len(self.data['b23']),len(prior['b23']))
        for now,old in zip(self.data['b23'],prior['b23']):
            self.assertEqual({k:v for k,v in now.items() if k not in ('text','title','path')},{k:v for k,v in old.items() if k not in ('text','title','path')})
            for field in ('title','path'):self.assertEqual(compact(now[field]),compact(old[field]))
            self.assertEqual(compact(now['text']),compact(old['text']),old['id'])
        for num,history in prior['hist_incline'].items():
            for index,block in enumerate(history['blocks']):
                now=self.data['hist_incline'][num]['blocks'][index]
                self.assertEqual(compact(now['text']),compact(block['text']),(num,index))
                self.assertEqual(now.get('source_head',now['head']) if now.get('date_unknown') else block['head'],block['head'])
        figures=[a for a in self.data['ref_assets'].values() if a['key'].startswith('history-legacy-')]
        self.assertEqual(len(figures),1)
        figure=figures[0]
        self.assertTrue(figure['historical']);self.assertEqual(figure['num'],'4')
        self.assertEqual(figure['owner'],'b23-10.11.5')

    def test_book_and_site_use_identical_data_and_all_appendices(self):
        canonical=json.dumps({'b23':self.data['b23'],'hist_incline':self.data['hist_incline']},ensure_ascii=False,sort_keys=True).encode()
        self.assertEqual(hashlib.sha256(canonical).hexdigest(),self.audit['canonical_sha256'])
        self.assertEqual(hashlib.sha256(self.pdf.read_bytes()).hexdigest(),self.audit['pdf_sha256'])
        self.assertEqual(len(self.audit['clause_pages']),889)
        self.assertEqual(self.audit['history_blocks'],97)
        self.assertEqual(set(self.audit['source_appendix_pages'].values()),set(range(161,208)))
        with pymupdf.open(self.pdf) as doc:
            self.assertEqual(len(doc),self.audit['pages'])
            self.assertIn(self.audit['canonical_sha256'],doc.metadata['keywords'])
            all_text=''.join(page.get_text() for page in doc)
            self.assertIn('보완 v0.3',all_text)
            self.assertNotRegex(all_text,r'[\w.+-]+@[\w.-]+')

    def test_book_preserves_all_visible_current_text_and_original_images(self):
        with pymupdf.open(self.pdf) as doc:
            text=''.join(''.join(b[4] for b in page.get_text('blocks') if b[1]>50 and b[3]<800) for page in doc)
        text=re.sub(r'\s+','',text)
        missing=[]
        figure_re=re.compile(r'\x10[^\x11]*\x11')
        for entry in self.data['b23']:
            if entry.get('group'):continue
            for line in figure_re.sub('',entry['text']).split('\n'):
                value=re.sub(r'\s+','',line)
                if len(value)>18 and value not in text:missing.append((entry['id'],value[:80]))
        self.assertEqual(missing,[])
        used=set(self.audit['images'])
        audit=json.loads((BUILD/'incline-audit.json').read_text(encoding='utf-8'))
        main={i['file'] for i in audit['images'] if i['page']<=160}
        self.assertTrue(main<=used,main-used)
        self.assertIn('legacy_hydraulic_2014_figure4.webp',used)

    def test_reviewed_paragraph_boundaries_and_card_design(self):
        by={e['num']:e for e in self.data['b23']}
        self.assertIn('장치가 설치되어야 한다',by['10.11.1']['text'])
        self.assertNotIn('잠\n기지',by['10.11.1']['text'])
        self.assertIn('법률」',by['17']['text'])
        self.assertIn('\n17.1.4.1 ',by['17']['text'])
        self.assertIn('브레이크 수단',by['13.4.1.2']['text'])
        html=(ROOT/'index.html').read_text(encoding='utf8')
        old=subprocess.check_output(['git','show','be1e2ef:index.html'],cwd=ROOT).decode('utf8')
        self.assertEqual(re.search(r'<style>(.*?)</style>',html,re.S)[1],re.search(r'<style>(.*?)</style>',old,re.S)[1])
        for h in self.data['hist_incline'].values():
            for block in h['blocks']:
                self.assertLessEqual(len(block['g']),80)
                self.assertNotRegex(block['g'],r'(?:했다|한다|있었다|이었다|않는다)[.]?$')


if __name__=='__main__':unittest.main()
