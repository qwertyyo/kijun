"""배포용 index.html 원본으로 목차·저장된 열람 상태를 검사한다. HTML/데이터 주입 없음."""
import functools
import http.server
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import threading
import unittest

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'build'))
from reference_assets import NAMED, compact, number, prose, reference_source


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


class PublishedPage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        site = Path(cls.temp.name)
        cls.site = site
        original = (ROOT / 'index.html').read_bytes()
        (site / 'index.html').write_bytes(original)
        cls.data = json.loads(re.search(r'<script id="data" type="application/json">(.*?)</script>', original.decode(), re.S)[1])
        (site / 'config.json').write_text('{"synApi":""}')
        (site / 'release.json').write_bytes((ROOT / 'release.json').read_bytes())
        for name in ('fig','stdimg','katex'):
            (site / name).symlink_to(ROOT / name, target_is_directory=True)
        cls.server = http.server.ThreadingHTTPServer(('127.0.0.1',0), functools.partial(QuietHandler,directory=str(site)))
        threading.Thread(target=cls.server.serve_forever,daemon=True).start()
        cls.url = f'http://127.0.0.1:{cls.server.server_port}/'
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.server.shutdown()
        cls.server.server_close()
        cls.temp.cleanup()

    def setUp(self):
        self.page = self.browser.new_page(viewport={'width':390,'height':844},has_touch=True)
        self.errors = []
        self.page.on('pageerror',lambda e:self.errors.append(str(e)))
        self.page.route('https://**/*',lambda r:r.abort())
        response = self.page.goto(self.url,wait_until='networkidle')
        self.assertEqual(response.body(), (ROOT / 'index.html').read_bytes())
        self.page.wait_for_function('!!window.KIJUN')
        self.assertEqual(self.page.evaluate('KIJUN.build'),json.loads((ROOT / 'release.json').read_text())['version'])

    def tearDown(self):
        self.assertEqual(self.errors, [])
        self.page.close()

    def prepare_new_version(self):
        old = json.loads((ROOT / 'release.json').read_text())['version']
        new = 'f' * 16 if old != 'f' * 16 else 'e' * 16
        (self.site / 'index.html').write_text((ROOT / 'index.html').read_text().replace(old,new))
        (self.site / 'release.json').write_text(json.dumps({'version':new}))
        return new

    def publish_new_version(self):
        new=self.prepare_new_version()
        self.page.evaluate('document.dispatchEvent(new Event("visibilitychange"))')
        self.page.wait_for_url('**?v='+new+'*')
        self.page.wait_for_load_state('networkidle')
        self.assertEqual(self.page.evaluate('KIJUN.build'),new)

    def restore_published_version(self):
        (self.site / 'index.html').write_bytes((ROOT / 'index.html').read_bytes())
        (self.site / 'release.json').write_bytes((ROOT / 'release.json').read_bytes())

    def test_update_on_return_preserves_toc_and_reading_position(self):
        self.page.locator('[data-src="b24"]').click()
        self.page.locator('[data-view="b24"][data-key="Ⅳ"]').click()
        self.page.wait_for_timeout(600)
        self.page.evaluate('scrollTo(0,500)')
        position=self.page.evaluate('scrollY')
        try:
            self.publish_new_version()
            self.assertEqual(self.page.locator('[id="b24-Ⅳ"] .body [data-ref-table="Ⅱ.1"]').count(),4)
            self.assertAlmostEqual(self.page.evaluate('scrollY'),position,delta=2)
            self.page.locator('[id="b24-Ⅳ"] .body [data-ref-table="Ⅱ.1"]').first.click()
            self.assertEqual(self.page.locator('.ref-content img').count(),3)
        finally:
            self.restore_published_version()

    def test_update_on_return_preserves_search_and_source_filter(self):
        self.page.locator('[data-src="b24"]').click()
        self.page.locator('#q').fill('핸드레일')
        self.page.locator('#q').press('Enter')
        self.page.wait_for_timeout(600)
        self.page.evaluate('scrollTo(0,400)')
        position=self.page.evaluate('scrollY')
        try:
            self.publish_new_version()
            self.assertEqual(self.page.locator('#q').input_value(),'핸드레일')
            self.assertEqual(self.page.locator('[data-src="b24"]').get_attribute('aria-pressed'),'true')
            self.assertAlmostEqual(self.page.evaluate('scrollY'),position,delta=2)
        finally:
            self.restore_published_version()

    def test_failed_version_request_keeps_reading_page(self):
        self.page.route('**/release.json',lambda r:r.fulfill(status=503,body='Unavailable'))
        self.page.locator('[data-src="b24"]').click()
        self.page.locator('[data-view="b24"][data-key="Ⅳ"]').click()
        before=self.page.url
        self.page.evaluate('document.dispatchEvent(new Event("visibilitychange"))')
        self.page.wait_for_timeout(200)
        self.assertEqual(self.page.url,before)
        self.assertEqual(self.page.locator('[id="b24-Ⅳ"] .body [data-ref-table="Ⅱ.1"]').count(),4)

    def test_open_popup_is_not_interrupted_by_update(self):
        self.page.locator('[data-src="b24"]').click()
        self.page.locator('[data-view="b24"][data-key="Ⅳ"]').click()
        self.page.locator('[id="b24-Ⅳ"] .body [data-ref-table="Ⅱ.1"]').first.click()
        before=self.page.url
        try:
            new=self.prepare_new_version()
            self.page.evaluate('document.dispatchEvent(new Event("visibilitychange"))')
            self.page.wait_for_timeout(200)
            self.assertEqual(self.page.url,before)
            self.assertTrue(self.page.locator('.ref-window').is_visible())
            self.page.locator('[data-ref-close]').click()
            self.page.evaluate('document.dispatchEvent(new Event("visibilitychange"))')
            self.page.wait_for_url('**?v='+new+'*')
            self.page.wait_for_load_state('networkidle')
            self.assertEqual(self.page.evaluate('KIJUN.build'),new)
        finally:
            self.restore_published_version()

    def test_popup_opened_during_version_request_is_not_interrupted(self):
        self.page.locator('[data-src="b24"]').click()
        self.page.locator('[data-view="b24"][data-key="Ⅳ"]').click()
        pending=[]
        self.page.route('**/release.json',lambda route:pending.append(route))
        self.page.evaluate('document.dispatchEvent(new Event("visibilitychange"))')
        self.page.wait_for_timeout(100)
        self.assertEqual(len(pending),1)
        self.page.locator('[id="b24-Ⅳ"] .body [data-ref-table="Ⅱ.1"]').first.click()
        before=self.page.url
        try:
            new=self.prepare_new_version()
            pending[0].fulfill(status=200,content_type='application/json',body=json.dumps({'version':new}))
            self.page.wait_for_timeout(200)
            self.assertEqual(self.page.url,before)
            self.assertTrue(self.page.locator('.ref-window').is_visible())
        finally:
            self.restore_published_version()

    def test_table_from_toc_and_saved_view_after_reload(self):
        self.page.locator('[data-src="b24"]').click()
        self.page.locator('[data-view="b24"][data-key="Ⅳ"]').click()
        for reload in (False, True):
            if reload:
                self.page.reload(wait_until='networkidle')
            card = self.page.locator('[id="b24-Ⅳ"]')
            self.assertEqual(card.locator('.body [data-ref-table="Ⅱ.1"]').count(), 4)
            self.assertEqual(card.locator('.body [data-ref-ids="b24-3.1"], .body [data-ref-ids="b24-3.6"]').count(), 0)
            card.locator('.body [data-ref-table="Ⅱ.1"]').first.click()
            images = self.page.locator('.ref-content img')
            self.assertEqual(images.count(), 3)
            for image in images.all():
                image.evaluate('(e)=>e.decode()')
            self.page.locator('[data-ref-close]').click()

    def open_table_window(self):
        self.page.locator('[data-src="b24"]').click()
        self.page.locator('[data-view="b24"][data-key="Ⅳ"]').click()
        self.page.locator('[id="b24-Ⅳ"] .body [data-ref-table="Ⅱ.1"]').first.click()

    def assert_usable_window(self):
        box=self.page.locator('.ref-window').bounding_box()
        self.assertGreaterEqual(box['height'],96)
        self.assertGreater(box['width'],150)
        self.assertGreaterEqual(box['x'],-1)
        self.assertGreaterEqual(box['y'],-1)
        self.assertLessEqual(box['x']+box['width'],self.page.viewport_size['width']+1)
        self.assertLessEqual(box['y']+box['height'],self.page.viewport_size['height']+1)
        self.assertTrue(self.page.locator('[data-ref-close]').is_visible())
        self.assertGreater(self.page.locator('.ref-content').evaluate('(e)=>e.clientHeight'),30)

    def test_tablet_portrait_landscape_and_split_screen(self):
        for width,height in ((600,960),(960,600),(768,1024),(1280,800),(480,800),(360,640)):
            self.page.set_viewport_size({'width':width,'height':height})
            self.open_table_window()
            self.assert_usable_window()
            self.page.locator('.ref-content').evaluate('(e)=>e.scrollTop=120')
            self.assertGreater(self.page.locator('.ref-content').evaluate('(e)=>e.scrollTop'),0)
            self.page.locator('[data-ref-close]').click()
            self.assertNotEqual(self.page.locator('body').evaluate('(e)=>getComputedStyle(e).position'),'fixed')

    def test_popup_recovers_from_zero_height_css_and_zero_visual_viewport(self):
        self.page.add_init_script('''const v=new EventTarget();Object.assign(v,{width:0,height:0,offsetTop:0,offsetLeft:0});Object.defineProperty(window,'visualViewport',{value:v});''')
        self.page.reload(wait_until='networkidle')
        self.page.set_viewport_size({'width':960,'height':600})
        self.page.add_style_tag(content='.ref-window { height:0;max-height:0;width:0; }')
        self.open_table_window()
        self.assert_usable_window()
        self.page.set_viewport_size({'width':600,'height':960})
        self.page.wait_for_timeout(200)
        self.assert_usable_window()
        self.page.locator('[data-ref-close]').click()

    def test_popup_position_with_transformed_body(self):
        self.page.set_viewport_size({'width':960,'height':600})
        self.page.add_style_tag(content='body { transform:translateZ(0); }')
        self.open_table_window()
        self.assert_usable_window()
        self.page.screenshot(path='/workspace/kijun-local/tablet-transformed-popup.png')
        self.page.locator('[data-ref-close]').click()
        self.assertNotEqual(self.page.locator('body').evaluate('(e)=>getComputedStyle(e).position'),'fixed')

    def test_popup_render_failure_never_locks_background(self):
        self.page.locator('[data-src="b24"]').click()
        self.page.locator('[data-view="b24"][data-key="Ⅳ"]').click()
        self.page.evaluate('''() => {const p=Element.prototype,d=Object.getOwnPropertyDescriptor(p,'innerHTML');Object.defineProperty(p,'innerHTML',{get:d.get,set(v){if(this.classList.contains('ref-content')){Object.defineProperty(p,'innerHTML',d);throw Error('Expected render failure');}d.set.call(this,v);},configurable:true});}''')
        ref=self.page.locator('[id="b24-Ⅳ"] .body [data-ref-table="Ⅱ.1"]').first
        ref.click()
        self.assertTrue(self.page.locator('.ref-window').is_hidden())
        self.assertNotEqual(self.page.locator('body').evaluate('(e)=>getComputedStyle(e).position'),'fixed')
        ref.click()
        self.assert_usable_window()
        self.page.locator('[data-ref-close]').click()

    def test_drag_without_pointer_capture(self):
        self.page.set_viewport_size({'width':1200,'height':1000})
        self.page.evaluate('Element.prototype.setPointerCapture=undefined')
        self.open_table_window()
        old=self.page.locator('.ref-window').bounding_box()
        title=self.page.locator('.ref-title').bounding_box()
        x,y=title['x']+20,title['y']+10
        self.page.mouse.move(x,y);self.page.mouse.down();self.page.mouse.move(x+80,y+120);self.page.mouse.up()
        new=self.page.locator('.ref-window').bounding_box()
        self.assertAlmostEqual(new['x']-old['x'],80,delta=2)
        self.assertAlmostEqual(new['y']-old['y'],120,delta=2)

    def test_legacy_mouse_and_touch_drag(self):
        self.page.add_init_script('delete window.PointerEvent')
        self.page.reload(wait_until='networkidle')
        self.page.set_viewport_size({'width':1200,'height':1000})
        self.open_table_window()
        old=self.page.locator('.ref-window').bounding_box()
        title=self.page.locator('.ref-title').bounding_box();x,y=title['x']+20,title['y']+10
        self.page.mouse.move(x,y);self.page.mouse.down();self.page.mouse.move(x+60,y+100);self.page.mouse.up()
        moved=self.page.locator('.ref-window').bounding_box()
        self.assertAlmostEqual(moved['y']-old['y'],100,delta=2)
        title=self.page.locator('.ref-title').bounding_box();x,y=title['x']+20,title['y']+10
        session=self.page.context.new_cdp_session(self.page)
        session.send('Input.dispatchTouchEvent',{'type':'touchStart','touchPoints':[{'x':x,'y':y}]})
        session.send('Input.dispatchTouchEvent',{'type':'touchMove','touchPoints':[{'x':x,'y':y-60}]})
        session.send('Input.dispatchTouchEvent',{'type':'touchEnd','touchPoints':[]})
        new=self.page.locator('.ref-window').bounding_box()
        self.assertAlmostEqual(new['y']-moved['y'],-60,delta=3)

    def test_safety_factor_images_and_original_reference_typo(self):
        self.page.locator('[data-src="b22"]').click()
        self.page.locator('[data-view="b22"][data-key="Ⅹ"]').click()
        card=self.page.locator('[id="b22-Ⅹ.3"]')
        images=card.locator('.body img')
        self.assertEqual(images.count(),2)
        for image in images.all():
            image.scroll_into_view_if_needed()
            image.evaluate('(e)=>e.decode()')
            self.assertGreater(image.evaluate('(e)=>e.naturalWidth'),100)
        self.assertIn('Sf = 안전율',card.inner_text())
        ref=card.locator('.body [data-ref-assets]').filter(has_text='그림 Ⅸ.1')
        self.assertEqual(ref.get_attribute('data-ref-assets'),'b22-figure-Ⅹ.1')
        card.screenshot(path='/workspace/kijun-local/safety-factor-clean-card.png')
        ref.click()
        self.assertIn('그림 Ⅹ.1',self.page.locator('.ref-title').inner_text())
        self.assertIn('원문 본문은 그림 Ⅸ.1',self.page.locator('.ref-content').inner_text())
        self.assertIn('ref_b22_figure_Ⅹ_1',self.page.locator('.ref-content img').get_attribute('src'))

    def test_all_toc_groups_using_published_html(self):
        entries = {e['id']:e for src in ('b22','b24','std','fail') for e in self.data[src]}
        clauses = {e['id'] for src in ('b22','b24') for e in self.data[src]}
        catalog = self.data['ref_assets']
        expected = {}
        for src in ('b22','b24'):
            for entry in self.data[src]:
                targets = []
                for line in prose(entry['title']+'\n'+entry['text']).split('\n'):
                    line = compact(line)
                    for match in NAMED.finditer(line):
                        source = reference_source(line,match.start(),src)
                        if source == 'unsupported':
                            continue
                        kind, num = ('table' if match[1]=='표' else 'figure'), number(match[2])
                        allowed = {k for k,a in catalog.items() if not a.get('historical') and a['src']==source and a['kind']==kind and a['num']==num}
                        for alias in self.data['ref_aliases']:
                            if (alias['entry'],alias['kind'],alias['num'])==(entry['id'],kind,num):
                                allowed.add(alias['target'])
                        self.assertTrue(allowed,(entry['id'],match[0]))
                        targets.append(allowed)
                expected[entry['id']] = targets
        groups = self.page.locator('.tocitem[data-view]').evaluate_all('(es)=>es.map(e=>({src:e.dataset.view,key:e.dataset.key}))')
        seen = set()
        ledger = []
        for group in groups:
            selector = '[data-view='+json.dumps(group['src'])+'][data-key='+json.dumps(group['key'],ensure_ascii=False)+']'
            self.page.locator('.tocitem'+selector).click()
            layout = self.page.locator('#results .card').evaluate_all('''async cards => {
              await Promise.all(cards.flatMap(c=>Array.from(c.querySelectorAll('img'))).map(async im=>{
                im.loading='eager'; await im.decode();
              }));
              return cards.map(c=>({id:c.id,height:c.getBoundingClientRect().height,
                images:Array.from(c.querySelectorAll('img')).map(im=>({src:im.getAttribute('src'),
                  naturalWidth:im.naturalWidth,naturalHeight:im.naturalHeight,width:im.getBoundingClientRect().width,
                  parentWidth:im.parentElement.getBoundingClientRect().width}))}));
            }''')
            for card in layout:
                self.assertGreater(card['height'], 30, card['id'])
                for image in card['images']:
                    self.assertGreater(image['naturalWidth'], 0, image)
                    self.assertGreater(image['naturalHeight'], 0, image)
                    self.assertLessEqual(image['width'], image['parentWidth'] + 2, (card['id'], image))
            ledger.extend(layout)
            cards = self.page.locator('#results .card').evaluate_all('''es=>es.map(c=>({id:c.id,linked:c.dataset.refsLinked,
              clauses:Array.from(c.querySelectorAll('[data-ref-ids]')).flatMap(b=>b.dataset.refIds.split(',')),
              assets:Array.from(c.querySelectorAll('.body [data-ref-assets], h2 [data-ref-assets]')).flatMap(b=>b.dataset.refAssets.split(','))}))''')
            self.assertTrue(cards,group)
            for card in cards:
                self.assertIn(card['id'],entries)
                self.assertEqual(card['linked'],'1',card['id'])
                self.assertTrue(set(card['clauses'])<=clauses,card['id'])
                self.assertTrue(set(card['assets'])<=set(catalog),card['id'])
                for allowed in expected.get(card['id'],[]):
                    self.assertTrue(set(card['assets'])&allowed,(card['id'],allowed))
                seen.add(card['id'])
            self.page.locator('.vnav.top [data-totoc]').click()
        self.assertEqual(len(seen),2461)
        if os.environ.get('KIJUN_AUDIT_DIR'):
            output = Path(os.environ['KIJUN_AUDIT_DIR'])
            output.mkdir(parents=True,exist_ok=True)
            (output/'browser-card-ledger.json').write_text(json.dumps(ledger,ensure_ascii=False,indent=2))
        print('Published HTML UI audit:',len(groups),'TOC groups;',len(seen),'real cards; missing internal references: 0')


if __name__ == '__main__':
    unittest.main()
