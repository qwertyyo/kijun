"""경사형 연혁집의 출처·연혁·수식과 실제 게시 파일의 검색/참조 회귀 검사."""
import functools
import hashlib
import http.server
import json
from pathlib import Path
import re
import subprocess
import sys
import threading
import unittest

from PIL import Image
import pymupdf
from playwright.sync_api import sync_playwright

from browser_support import browser_path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'build'))
from incline_parse import SOURCE_SHA256


def page_data(raw):
    return json.loads(re.search(r'<script id="data" type="application/json">(.*?)</script>', raw, re.S)[1])


class InclineData(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = page_data((ROOT / 'index.html').read_text(encoding='utf-8'))
        cls.entries = {e['id']:e for e in cls.data['b23']}

    def test_provided_source_and_all_sections_preserved(self):
        pdf = ROOT / 'build/hist_incline/hist.pdf'
        self.assertEqual(hashlib.sha256(pdf.read_bytes()).hexdigest(), SOURCE_SHA256)
        with pymupdf.open(pdf) as doc:
            self.assertEqual(len(doc),207)
        supplements = [e for e in self.entries.values() if e.get('group')]
        self.assertEqual({e['pages'][0] for e in supplements},set(range(161,208)))
        self.assertEqual(len(supplements),47)
        for key in ['1','3.1','6.8','7.4.3.1','Ⅷ.7.2.1.2','Ⅻ.3','XⅢ']:
            self.assertIn('b23-' + key,self.entries)
        self.assertIn('15°',self.entries['b23-1']['text'])
        self.assertIn('로봇',self.entries['b23-XⅢ']['title'])

    def test_all_55_history_blocks_and_book_dates_are_not_enactment_dates(self):
        blocks = [b for h in self.data['hist_incline'].values() for b in h['blocks']]
        self.assertEqual(sum(not b.get('legacy_supplement') for b in blocks),55)
        self.assertEqual(sum(bool(b.get('legacy_supplement')) for b in blocks),42)
        for block in blocks:
            self.assertTrue(block['text'].strip(),block['head'])
            if block.get('date_unknown'):
                self.assertIsNone(block['from'])
                self.assertIsNone(block['to'])
                self.assertIn('적용일 미확인',block['head'])
            self.assertNotIn('수록본',block['head'])
        current = self.entries['b23-3.1']['text']
        self.assertIn('문열림출발',self.entries['b23-3.1']['title'])
        self.assertNotIn('개문출발',current)
        self.assertIn('개문출발',self.data['hist_incline']['3.1']['blocks'][0]['text'])

    def test_all_substantive_source_lines_are_represented(self):
        content = ''.join(e['num'] + e['title'] + e['text'] for e in self.entries.values())
        content += ''.join(b['head'] + b.get('source_head','') + b['text'] for h in self.data['hist_incline'].values() for b in h['blocks'])
        content = re.sub(r'\s+', '', content)
        missing = []
        with pymupdf.open(ROOT / 'build/hist_incline/hist.pdf') as doc:
            for pn in range(2,160):
                for block in doc[pn].get_text('dict')['blocks']:
                    if block['type'] != 0:
                        continue
                    for line in block['lines']:
                        if not 55 <= line['bbox'][1] < 798 or (pn == 2 and line['bbox'][1] < 180):
                            continue
                        text = re.sub(r'\s+', '', ''.join(s['text'] for s in line['spans'])).lstrip('➥')
                        if len(text) > 15 and text not in content:
                            missing.append((pn+1,text[:80]))
        self.assertEqual(missing,[])

    def test_every_crop_is_readable_and_has_a_source_rectangle(self):
        audit = json.loads((ROOT / 'build/incline-audit.json').read_text(encoding='utf-8'))
        self.assertEqual({c['page'] for c in audit['coverage']},set(range(3,161)))
        for image in audit['images']:
            with Image.open(ROOT / 'fig' / image['file']) as im:
                self.assertEqual(im.size,(image['width'],image['height']))
                self.assertLess(im.convert('L').getextrema()[0],200,image['file'])
            self.assertGreater(image['rect'][3],image['rect'][1])
        for num in ['Ⅷ.7.2.1.2','Ⅷ.7.2.1.3','Ⅷ.7.2.1.4','Ⅷ.7.2.1.5']:
            self.assertIn('\x10',self.entries['b23-'+num]['text'],'윤곽 수식 누락: '+num)

    def test_image_search_text_works_with_existing_line_renderer(self):
        texts = [e['text'] for e in self.entries.values()]
        texts += [b['text'] for h in self.data['hist_incline'].values() for b in h['blocks']]
        for text in texts:
            for marker in re.findall(r'\x10[^\x11]*\x11', text):
                self.assertNotIn('\n', marker)

    def test_unlocated_source_reference_and_public_letter_redaction(self):
        note = self.entries['b23-8.2.3.3']['unresolved_refs']
        self.assertEqual([(r['kind'],r['num']) for r in note],[('figure','11')])
        letter = self.entries['b23-methods-p199']['text']
        self.assertIsNone(re.search(r'\d{2,3}-\d{3,4}-\d{4}|[\w.+-]+@[\w.-]+',letter))

    def test_all_original_diagrams_and_vector_math_glyphs_are_uncut(self):
        audit = json.loads((ROOT / 'build/incline-audit.json').read_text(encoding='utf-8'))
        clips = {}
        for item in audit['images']:
            clips.setdefault(item['page'],[]).append(pymupdf.Rect(item['rect']) + (-1,-1,1,1))
        missing = []
        with pymupdf.open(ROOT / 'build/hist_incline/hist.pdf') as doc:
            for pn in range(2,160):
                page = doc[pn]
                regions = [pymupdf.Rect(im['bbox']) for im in page.get_image_info()]
                regions += [pymupdf.Rect(d['rect']) for d in page.get_drawings()
                            if d['fill'] is not None and any(i[0]=='c' for i in d['items'])
                            and 55 <= d['rect'].y0 and d['rect'].y1 < 798]
                for region in regions:
                    if not any(clip.contains(region) for clip in clips.get(pn+1,[])):
                        missing.append((pn+1,[round(v,1) for v in region]))
        self.assertEqual(missing,[])

    def test_existing_content_unchanged(self):
        baseline = subprocess.check_output(['git','show','10c9b2d9398bf65eaadf32a34b19aaef8bbd208b:index.html'],cwd=ROOT).decode('utf-8')
        old = page_data(baseline)
        for key in ['b22','b24','hist','hist_es','std','fail','es_figures','es_tables','std_asset_links']:
            self.assertEqual(hashlib.sha256(json.dumps(self.data[key],sort_keys=True,ensure_ascii=False).encode()).hexdigest(),hashlib.sha256(json.dumps(old[key],sort_keys=True,ensure_ascii=False).encode()).hexdigest(),key+' 기존 내용 변경')


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self,*args):
        pass


class InclineBrowser(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(QuietHandler,directory=str(ROOT)))
        threading.Thread(target=cls.server.serve_forever,daemon=True).start()
        cls.url = f'http://127.0.0.1:{cls.server.server_port}/'
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch(executable_path=browser_path(),args=['--no-sandbox'])

    @classmethod
    def tearDownClass(cls):
        cls.browser.close(); cls.pw.stop(); cls.server.shutdown(); cls.server.server_close()

    def setUp(self):
        self.page = self.browser.new_page(viewport={'width':390,'height':844},has_touch=True)
        self.errors=[]
        self.page.on('pageerror',lambda e:self.errors.append(str(e)))
        self.page.route('https://**/*',lambda route:route.abort())
        self.page.goto(self.url,wait_until='networkidle')
        self.page.locator('[data-src="b23"]').click()

    def tearDown(self):
        self.assertEqual(self.errors,[])
        self.page.close()

    def search(self,text):
        self.page.get_by_role('searchbox',name='검색어').fill(text)
        self.page.get_by_role('button',name='검색',exact=True).click()
        # 입력 지연 검색이 남아 연혁을 연 직후 결과를 다시 그리지 않도록 기다린다.
        self.page.wait_for_timeout(200)

    def test_mobile_tabs_history_and_no_other_source_leakage(self):
        self.assertTrue(self.page.get_by_role('heading',name='경사형 엘리베이터 연혁집 · 보완 v0.3').is_visible())
        for button in self.page.locator('.srcbar button').all():
            rect=button.bounding_box();self.assertGreaterEqual(rect['x'],0);self.assertLessEqual(rect['x']+rect['width'],391)
        self.search('문열림출발')
        self.assertGreater(self.page.locator('.card').count(),0)
        self.assertEqual(self.page.locator('.card:not(.b23)').count(),0)
        card=self.page.locator('[id="b23-3.1"]')
        card.get_by_role('button',name='적용 연혁').click()
        self.assertIn('개문출발',card.locator('.hist').inner_text())
        self.search('유압식')
        self.assertGreater(self.page.locator('.card .hsum').count(),0)
        self.assertNotIn('미시행',self.page.locator('#results').inner_text())

    def test_clause_references_stay_in_incline_and_supplements_are_searchable(self):
        self.search('점검 트랩문')
        refs=self.page.locator('.card.b23 .body [data-ref-ids]')
        self.assertGreater(refs.count(),0)
        for value in refs.evaluate_all('(bs)=>bs.map(b=>b.dataset.refIds)'):
            self.assertTrue(all(k.startswith('b23-') for k in value.split(',')),value)
        refs.first.click()
        self.assertIn('경사형',self.page.locator('.ref-title').inner_text())
        self.page.locator('[data-ref-close]').click()
        self.search('자동구출운전')
        self.assertGreater(self.page.locator('[id^="b23-methods-"]').count(),0)

    def test_source_images_load_and_formula_can_be_enlarged(self):
        self.page.locator('[data-view="b23"][data-key="Ⅷ"]').click()
        card=self.page.locator('[id="b23-Ⅷ.7.2.1.2"]')
        button=card.locator('.body [data-lbfile]').first
        if not button.count():
            button=card.locator('.body .fig button').first
        button.click()
        image=self.page.locator('#lb img')
        image.evaluate('(im)=>im.decode()')
        self.assertGreater(image.evaluate('(im)=>im.naturalWidth'),100)

    def test_legacy_history_preserves_scope_and_its_original_figure(self):
        self.search('과부하')
        card=self.page.locator('[id="b23-15.2.5.2"]')
        card.get_by_role('button',name='적용 연혁').click()
        legacy=card.locator('.hp').filter(has_text='구 14.2.5.2')
        self.assertIn('65 ㎏',legacy.inner_text())
        self.assertIn('유압식',legacy.inner_text())
        self.assertEqual(legacy.locator('[data-ref-ids]').count(),0)
        self.assertNotIn('PDF',card.locator('.path').inner_text())
        self.search('문열림출발')
        card=self.page.locator('[id="b23-10.11.5"]')
        card.get_by_role('button',name='적용 연혁').click()
        legacy=card.locator('.hp').filter(has_text='구 9.13.5')
        self.assertIn('1.2 m',legacy.inner_text())
        image=legacy.locator('img[src*="legacy_hydraulic_2014_figure4"]')
        self.assertEqual(image.count(),1)
        legacy.locator('[data-ref-assets]').first.click()
        self.assertIn('카의 의도되지 않은 움직임',self.page.locator('.ref-content').inner_text())
        self.assertEqual(self.page.locator('.ref-content img').evaluate('(im)=>im.decode().then(()=>im.naturalWidth)'),1210)


if __name__=='__main__':
    unittest.main()
