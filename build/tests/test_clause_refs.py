"""Browser regression checks: run with a Python environment containing playwright.

Uses system Chromium (or CHROMIUM_PATH); no browser download or remote service.
The current template is rendered with the checked-in data in a temporary site.
"""
import functools
import http.server
import json
import os
from pathlib import Path
import re
import tempfile
import threading
import unittest

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[2]


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


class ClauseReferences(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        site = Path(cls.temp.name)
        original = (ROOT / 'index.html').read_text()
        raw = re.search(r'<script id="data" type="application/json">(.*?)</script>', original, re.S)[1]
        data = json.loads(raw)
        # One neutral standardization card exercises ambiguous and non-clause numbers.
        lines = ['5.1에 따른 기준', '5.1 m 이상', '그림 5.1 참조',
                 '2014.07.01부터 적용', '19.3.5.1에 따른 기준',
                 'KS B ISO 4190-1의 5.1 참조', '부속서 Ⅰ.2.4 참조',
                 '6.1.8.3에 따른 기준', '6.1.8.8 참조', '5.6.2.1에 따른 기준']
        data['std'].append(dict(src='std', id='std-ref-test', num='999',
                                title='조문연결시험', path='시험', year='2026',
                                text='\n'.join(lines), sec=[dict(h='표준화', p=lines)]))
        data['fail'].append(dict(src='fail', id='fail-ref-test', num='5.1',
                                 title='미보유기준시험', path='별표23 경사형 엘리베이터 안전기준',
                                 text='5.1에 따른 기준'))
        body = (ROOT / 'build/template.html').read_text().replace(
            '__DATA__', json.dumps(data, ensure_ascii=False).replace('</', '<\\/'))
        # A test-only hook exercises every real card/history, without exporting app internals.
        hook_at = body.rfind('})();')
        body = body[:hook_at] + 'window.__refTest = { card, historyHtml, linkClauseRefs, byId, REF_ENTRIES, ES_TABLES, REF_ASSETS, assetMentions, assetTargets, referenceSource };\n' + body[hook_at:]
        # Preserve the real build wrapper, including its [hidden] rule for the image viewer.
        (site / 'index.html').write_text(original.split('<body>', 1)[0] + '<body>' + body + '</body></html>')
        (site / 'config.json').write_text('{"synApi":""}')
        for name in ['fig', 'stdimg', 'katex']:
            (site / name).symlink_to(ROOT / name, target_is_directory=True)
        cls.server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(QuietHandler, directory=str(site)))
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f'http://127.0.0.1:{cls.server.server_port}/'
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch(executable_path=os.environ.get('CHROMIUM_PATH', '/usr/bin/chromium'), args=['--no-sandbox'])

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.server.shutdown()
        cls.server.server_close()
        cls.temp.cleanup()

    def setUp(self):
        self.page = self.browser.new_page(viewport=dict(width=390, height=844), has_touch=True)
        self.errors = []
        self.page.on('pageerror', lambda e: self.errors.append(str(e)))
        self.page.route('https://**/*', lambda r: r.abort())
        self.page.goto(self.url, wait_until='networkidle')
        self.page.wait_for_function('!!window.KIJUN')

    def tearDown(self):
        self.assertEqual(self.errors, [])
        self.page.close()

    def search(self, q):
        return self.page.evaluate('(q) => KIJUN.search(q, 20)', q)

    def open_example(self):
        self.search('피난용')
        card = self.page.locator('[id="b22-17.3.5.7"]')
        self.assertEqual(card.count(), 1)
        if 'open' not in card.get_attribute('class').split():
            card.locator('.more').click()
        ref = card.locator('.body [data-ref-num="17.3.5.1"]').first
        self.assertEqual(ref.get_attribute('data-ref-ids'), 'b22-17.3.5.1')
        ref.scroll_into_view_if_needed()
        self.reading_scroll = self.page.evaluate('scrollY')
        ref.click()
        self.page.wait_for_selector('.ref-window:not([hidden])')
        return card

    def test_example_preserves_query_results_and_reading_position(self):
        card = self.open_example()
        before = self.page.evaluate('({q:document.querySelector("#q").value,ids:KIJUN.results(20).map(e=>e.num)})')
        top_before = card.bounding_box()['y']
        self.assertIn('17.3.5.1', self.page.locator('.ref-title').inner_text())
        self.assertIn('피난호출 스위치', self.page.locator('.ref-content').inner_text())
        self.assertEqual(len(self.page.context.pages), 1)
        self.page.locator('[data-ref-close]').click()
        after = self.page.evaluate('({q:document.querySelector("#q").value,ids:KIJUN.results(20).map(e=>e.num)})')
        self.assertEqual(before, after)
        self.assertAlmostEqual(card.bounding_box()['y'], top_before, delta=1)
        self.assertAlmostEqual(self.page.evaluate('scrollY'), self.reading_scroll, delta=1)
        self.assertIn('open', card.get_attribute('class').split())

    def test_nested_reference_back_and_parent_clause(self):
        self.open_example()
        self.page.locator('[data-ref-close]').click()
        card = self.page.locator('[id="b22-17.3.5.7"]')
        card.locator('.body [data-ref-num="16.3"]').click()
        self.assertIn('16.3', self.page.locator('.ref-title').inner_text())
        self.assertGreater(self.page.locator('.ref-content .card').count(), 1)
        ref = self.page.locator('.ref-content [data-ref-ids]').first
        n = ref.get_attribute('data-ref-num')
        self.page.locator('.ref-content').evaluate('(e) => e.scrollTop = 40')
        ref.click()
        self.assertIn(n, self.page.locator('.ref-title').inner_text())
        self.page.locator('[data-ref-back]').click()
        self.assertIn('16.3', self.page.locator('.ref-title').inner_text())
        self.page.keyboard.press('Escape')
        self.assertTrue(self.page.locator('.ref-window').is_hidden())

    def test_ambiguous_numbers_units_dates_annex_and_missing_references(self):
        self.search('조문연결시험')
        card = self.page.locator('#std-ref-test')
        card.locator('.more').click()
        self.assertEqual(card.locator('[data-ref-num="5.1"]').count(), 1)
        self.assertEqual(card.locator('[data-ref-num="2014.07.01"], [data-ref-num="19.3.5.1"]').count(), 0)
        self.assertEqual(card.locator('[data-ref-num="Ⅰ.2.4"]').get_attribute('data-ref-ids'), 'b24-Ⅰ.2.4')
        card.locator('[data-ref-num="5.1"]').click()
        choices = self.page.locator('.ref-choice')
        self.assertEqual(choices.count(), 2)
        choices.filter(has_text='에스컬레이터').click()
        self.assertIn('승강기번호', self.page.locator('.ref-content').inner_text())
        self.page.locator('[data-ref-close]').click()
        self.search('미보유기준시험')
        self.assertEqual(self.page.locator('#fail-ref-test .clause-ref').count(), 0)

    def test_drag_keyboard_resize_and_no_background_scroll(self):
        self.page.set_viewport_size(dict(width=1200, height=900))
        self.open_example()
        window = self.page.locator('.ref-window')
        bar = self.page.locator('.ref-bar')
        a = window.bounding_box()
        scroll_before = self.page.evaluate('scrollY')
        grip = self.page.locator('.ref-title').bounding_box()
        self.page.mouse.move(grip['x'] + 15, grip['y'] + 10)
        self.page.mouse.down()
        self.page.mouse.move(grip['x'] + 95, grip['y'] + 90, steps=5)
        self.page.mouse.up()
        b = window.bounding_box()
        self.assertAlmostEqual(b['x'] - a['x'], 80, delta=2)
        self.assertAlmostEqual(b['y'] - a['y'], 80, delta=2)
        self.assertEqual(self.page.evaluate('scrollY'), scroll_before)
        bar.focus()
        self.page.keyboard.press('ArrowLeft')
        self.assertAlmostEqual(window.bounding_box()['x'], b['x'] - 10, delta=2)
        self.page.set_viewport_size(dict(width=360, height=640))
        box = window.bounding_box()
        self.assertGreaterEqual(box['x'], 0)
        self.assertGreaterEqual(box['y'], 0)
        self.assertLessEqual(box['x'] + box['width'], 360)
        self.assertLessEqual(box['y'] + box['height'], 640)

    def test_highlighted_number_links_and_history_links(self):
        self.search('조문연결시험 6.1.8.3')
        self.assertEqual(self.page.locator('#std-ref-test [data-ref-num="6.1.8.3"]').count(), 1)
        self.assertTrue(self.page.locator('#std-ref-test [data-ref-num="6.1.8.3"]').evaluate('(e) => !!(e.closest("mark") || e.querySelector("mark"))'))
        self.open_example()
        self.page.locator('[data-ref-close]').click()
        card = self.page.locator('[id="b22-17.3.5.7"]')
        card.locator('[data-hist]').click()
        self.assertGreater(card.locator('.hist .clause-ref').count(), 0)
        card.locator('.hist .clause-ref').first.click()
        self.assertTrue(self.page.locator('.ref-window').is_visible())

    def test_touch_drag_content_scroll_and_mobile_layout(self):
        self.open_example()
        window = self.page.locator('.ref-window')
        a = window.bounding_box()
        grip = self.page.locator('.ref-title').bounding_box()
        x, y = grip['x'] + 15, grip['y'] + 10
        session = self.page.context.new_cdp_session(self.page)
        session.send('Input.dispatchTouchEvent', dict(type='touchStart', touchPoints=[dict(x=x, y=y)]))
        session.send('Input.dispatchTouchEvent', dict(type='touchMove', touchPoints=[dict(x=x, y=y+60)]))
        session.send('Input.dispatchTouchEvent', dict(type='touchEnd', touchPoints=[]))
        self.assertAlmostEqual(window.bounding_box()['y'] - a['y'], 60, delta=3)
        self.assertEqual(self.page.locator('.ref-bar').evaluate('(e)=>getComputedStyle(e).touchAction'), 'none')
        self.assertNotEqual(self.page.locator('.ref-content').evaluate('(e)=>getComputedStyle(e).touchAction'), 'none')
        self.assertTrue(self.page.locator('body').evaluate('(e)=>e.scrollWidth <= innerWidth'))
        self.page.screenshot(path='/workspace/kijun-local/clause-mobile.png')

    def swipe_content(self, distance):
        box = self.page.locator('.ref-content').bounding_box()
        x, y = box['x'] + box['width'] - 6, box['y'] + box['height'] / 2
        session = self.page.context.new_cdp_session(self.page)
        session.send('Input.dispatchTouchEvent', dict(type='touchStart', touchPoints=[dict(x=x, y=y)]))
        for step in range(1, 7):
            session.send('Input.dispatchTouchEvent', dict(type='touchMove', touchPoints=[dict(x=x, y=y + distance * step / 6)]))
            self.page.wait_for_timeout(20)
        session.send('Input.dispatchTouchEvent', dict(type='touchEnd', touchPoints=[]))
        self.page.wait_for_timeout(300)

    def test_short_popup_content_swipe_never_scrolls_search_page(self):
        # Some mobile browsers/webviews do not contain scroll chaining using CSS alone.
        self.page.add_style_tag(content='.ref-content { overscroll-behavior: auto !important; }')
        card = self.open_example()
        before = card.bounding_box()['y']
        self.assertTrue(self.page.locator('.ref-content').evaluate('(e)=>e.scrollHeight <= e.clientHeight'))
        for distance in [-120, 120]:
            self.swipe_content(distance)
            self.assertAlmostEqual(card.bounding_box()['y'], before, delta=1)

    def test_long_popup_scrolls_internally_without_background_scroll_at_edges(self):
        self.page.add_style_tag(content='.ref-content { overscroll-behavior: auto !important; }')
        self.open_example()
        self.page.locator('[data-ref-close]').click()
        card = self.page.locator('[id="b22-17.3.5.7"]')
        card.locator('.body [data-ref-num="16.3"]').click()
        content = self.page.locator('.ref-content')
        before = card.bounding_box()['y']
        self.swipe_content(-100)
        self.assertGreater(content.evaluate('(e)=>e.scrollTop'), 0)
        self.assertAlmostEqual(card.bounding_box()['y'], before, delta=1)
        for edge, direction in [(0, 120), ('bottom', -120)]:
            content.evaluate('(e,edge)=>e.scrollTop = edge === "bottom" ? e.scrollHeight : 0', edge)
            self.swipe_content(direction)
            self.assertAlmostEqual(card.bounding_box()['y'], before, delta=1)

    def test_popup_close_restores_existing_page_styles_and_scroll(self):
        self.page.evaluate('''() => {
          document.documentElement.style.overflow = 'scroll';
          document.documentElement.style.overscrollBehavior = 'contain';
          document.body.style.position = 'relative';
          document.body.style.setProperty('color', 'rgb(20, 40, 60)', 'important');
        }''')
        before = self.page.evaluate('({html:document.documentElement.style.cssText,body:document.body.style.cssText})')
        self.open_example()
        # Closing with Escape must release the lock just like the close button.
        self.page.keyboard.press('Escape')
        after = self.page.evaluate('({html:document.documentElement.style.cssText,body:document.body.style.cssText})')
        self.assertEqual(before, after)
        self.assertAlmostEqual(self.page.evaluate('scrollY'), self.reading_scroll, delta=1)

    def test_escalator_uses_escalator_clauses(self):
        self.page.evaluate('KIJUN.setSource("b24")')
        self.search('핸드레일')
        refs = self.page.locator('#results .card.b24 [data-ref-ids]')
        self.assertGreater(refs.count(), 0)
        self.assertTrue(all(r.startswith('b24-') for r in refs.evaluate_all('(es)=>es.map(e=>e.dataset.refIds)')))
        refs.first.click()
        self.assertIn('에스컬레이터', self.page.locator('.ref-title').inner_text())

    def open_table_card(self):
        self.page.evaluate('KIJUN.setSource("b24")')
        self.search('안전회로 설계 지침')
        card = self.page.locator('[id="b24-Ⅳ"]')
        self.assertEqual(card.count(), 1)
        if 'open' not in card.get_attribute('class').split():
            card.locator('.more').click()
        return card

    def test_annex_table_opens_all_current_pages_and_enlarges(self):
        card = self.open_table_card()
        ref = card.locator('.body [data-ref-table="Ⅱ.1"]').filter(has_text='표').first
        self.assertEqual(card.locator('.body [data-ref-ids="b24-3.1"], .body [data-ref-ids="b24-3.6"]').count(), 0)
        ref.click()
        self.assertIn('표 Ⅱ.1', self.page.locator('.ref-title').inner_text())
        table = self.page.locator('.ref-table')
        self.assertIn('고장 배제', table.inner_text())
        images = table.locator('img')
        self.assertEqual(images.count(), 3)
        self.assertEqual(images.evaluate_all('(es)=>es.map(e=>e.getAttribute("src"))'),
                         ['fig/hes_p139_0.webp', 'fig/hes_p140_0.webp', 'fig/hes_p141_1.webp'])
        for image in images.all():
            image.evaluate('(e)=>e.decode()')
            self.assertGreater(image.evaluate('(e)=>e.naturalWidth'), 1000)
        self.assertEqual(len(self.page.context.pages), 1)
        self.assertTrue(self.page.locator('body').evaluate('(e)=>e.scrollWidth <= innerWidth'))
        self.page.screenshot(path='/workspace/kijun-local/table-popup-mobile.png')
        table.locator('[data-table-page="1"] button').click()
        self.assertTrue(self.page.locator('#lb').is_visible())
        self.assertIn('hes_p140_0.webp', self.page.locator('#lb img').get_attribute('src'))
        self.page.keyboard.press('Escape')
        self.assertTrue(self.page.locator('.ref-window').is_visible())

    def test_table_row_opens_matching_page_and_preserves_background(self):
        card = self.open_table_card()
        for number in ('3.1', '3.6'):
            ref = card.locator('.body [data-ref-table="Ⅱ.1"]').filter(has_text=re.compile('^' + re.escape(number) + '$'))
            self.assertEqual(ref.count(), 1)
            ref.click()
            before = card.bounding_box()['y']
            content = self.page.locator('.ref-content')
            target = self.page.locator('[data-table-page="1"]')
            self.assertAlmostEqual(target.bounding_box()['y'], content.bounding_box()['y'], delta=2)
            self.swipe_content(-100)
            self.assertAlmostEqual(card.bounding_box()['y'], before, delta=1)
            self.page.screenshot(path='/workspace/kijun-local/table-row-mobile.png')
            self.page.locator('[data-ref-close]').click()
            self.assertAlmostEqual(card.bounding_box()['y'], before, delta=1)

    def test_clause_to_table_back_and_source_and_highlight_resolution(self):
        self.page.evaluate('KIJUN.setSource("b24")')
        self.search('현재의 전자기술')
        card = self.page.locator('[id="b24-Ⅱ.2"]')
        if 'open' not in card.get_attribute('class').split():
            card.locator('.more').click()
        card.locator('.body [data-ref-ids="b24-Ⅳ"]').click()
        self.page.locator('.ref-content').evaluate('(e)=>e.scrollTop=30')
        self.page.locator('.ref-content [data-ref-table="Ⅱ.1"]').first.click()
        self.page.locator('[data-ref-back]').click()
        self.assertIn('Ⅳ', self.page.locator('.ref-title').inner_text())
        self.assertEqual(self.page.locator('.ref-content .ref-table').count(), 0)
        self.assertEqual(self.page.locator('.ref-content').evaluate('(e)=>e.scrollTop'), 30)
        cases = self.page.evaluate('''() => {
          const check = (html, src) => {
            const root = document.createElement('div');root.innerHTML=html;
            __refTest.linkClauseRefs(root, {src});
            return {text:root.textContent, tables:root.querySelectorAll('[data-ref-table]').length,
              clauses:Array.from(root.querySelectorAll('[data-ref-ids]')).map(e=>e.dataset.refIds),
              highlight:!!root.querySelector('[data-ref-table] mark')};
          };
          return [check('표 <mark>Ⅱ.1</mark>의 3.1 및 3.6에 따른 기준', 'b24'),
            check('표 II.1의 3.1 및 3.6에 따른 기준', 'b24'),
            check('표 Ⅱ.1의 3.1 및 3.6에 따른 기준', 'b22'),
            check('별표24 5.1에 따른 기준', 'std'),
            check('KS C IEC 60664-1 표 Ⅱ.1의 3.1 및 3.6', 'b24')];
        }''')
        self.assertEqual([c['tables'] for c in cases], [3, 3, 0, 0, 0])
        self.assertTrue(cases[0]['highlight'])
        self.assertEqual(cases[0]['text'], '표 Ⅱ.1의 3.1 및 3.6에 따른 기준')
        self.assertEqual(cases[2]['clauses'], [])
        self.assertEqual(cases[3]['clauses'], ['b24-5.1'])

    def test_escalator_figure_previews_load_on_matching_clause(self):
        self.page.evaluate('KIJUN.setSource("b24")')
        self.search('손잡이 외형')
        card = self.page.locator('[id="b24-5.6.2.1"]')
        self.assertEqual(card.count(), 1)
        self.assertEqual(card.locator('[data-es-figure="6"]').count(), 1)
        figure = card.locator('[data-es-figure="7"]')
        self.assertIn('치수·기호표', figure.inner_text())
        image = figure.locator('img');image.scroll_into_view_if_needed()
        image.evaluate('(e)=>e.decode()')
        self.assertGreater(image.evaluate('(e)=>e.naturalWidth'), 400)
        self.assertTrue(figure.is_visible())  # 전체 보기를 누르기 전에도 그림이 보인다.
        self.assertTrue(self.page.locator('body').evaluate('(e)=>e.scrollWidth <= innerWidth'))
        self.page.screenshot(path='/workspace/kijun-local/es-figure-card-mobile.png')
        figure.locator('button').click()
        self.assertTrue(self.page.locator('#lb').is_visible())
        self.assertIn('es_figure_7.webp', self.page.locator('#lb img').get_attribute('src'))

    def test_escalator_figures_also_show_in_reference_window_and_long_image_viewer(self):
        self.search('조문연결시험')
        self.page.locator('#std-ref-test .more').click()
        self.page.locator('#std-ref-test [data-ref-num="5.6.2.1"]').click()
        if self.page.locator('.ref-choice').count():
            self.page.locator('.ref-choice').filter(has_text='에스컬레이터').click()
        self.assertEqual(self.page.locator('.ref-content [data-es-figure="7"]').count(), 1)
        # A two-page figure must be reachable from its top to its final caption.
        self.page.locator('[data-ref-close]').click()
        self.page.evaluate('KIJUN.setSource("b24")')
        self.search('손잡이 외형')
        self.page.locator('[id="b24-5.6.2.1"] .path .clause-ref').filter(has_text='5.6').first.click()
        figure = self.page.locator('.ref-content [data-es-figure="5"]').first
        figure.locator('button').click()
        viewer = self.page.locator('#lb .lbscroll');image = viewer.locator('img')
        image.evaluate('(e)=>e.decode()')
        self.assertGreaterEqual(image.bounding_box()['y'], viewer.bounding_box()['y'] - 1)
        viewer.evaluate('(e)=>e.scrollTop = e.scrollHeight')
        a,b=image.bounding_box(),viewer.bounding_box()
        self.assertLessEqual(a['y']+a['height'],b['y']+b['height']+1)

    def test_popup_figures_and_escape_layer_order(self):
        self.search('조문연결시험')
        card = self.page.locator('#std-ref-test')
        card.locator('.more').click()
        card.locator('[data-ref-num="6.1.8.8"]').click()
        image = self.page.locator('.ref-content [data-fz]').first
        image.click()
        self.assertTrue(self.page.locator('#lb').is_visible())
        self.assertTrue(self.page.locator('.ref-window').is_visible())
        self.page.keyboard.press('Escape')
        self.assertTrue(self.page.locator('#lb').is_hidden())
        self.assertTrue(self.page.locator('.ref-window').is_visible())
        self.page.keyboard.press('Escape')
        self.assertTrue(self.page.locator('.ref-window').is_hidden())

    def test_every_asset_opens_and_every_image_loads_at_mobile_width(self):
        keys = self.page.evaluate('Object.keys(__refTest.REF_ASSETS)')
        self.assertGreaterEqual(len(keys), 121)
        for start in range(0, len(keys), 15):
            self.page.evaluate('''async (keys) => {
              for (const key of keys) {
                const asset = __refTest.REF_ASSETS[key];
                const button = document.createElement('button');button.dataset.refAssets=key;
                document.body.appendChild(button);button.click();button.remove();
                const root = document.querySelector('.ref-content');
                if (root.querySelector('[data-asset-key]')?.dataset.assetKey !== key) throw Error('Wrong asset: '+key);
                const images = Array.from(root.querySelectorAll('img'));
                if (images.length !== asset.pages.length) throw Error('Incomplete asset: '+key);
                for (let i=0;i<images.length;i++) {
                  await images[i].decode();
                  if (images[i].naturalWidth !== asset.pages[i].width || images[i].naturalHeight !== asset.pages[i].height) throw Error('Image dimensions: '+key);
                }
                if (document.body.scrollWidth > innerWidth) throw Error('Mobile overflow: '+key);
                document.querySelector('[data-ref-close]').click();
              }
            }''', keys[start:start+15])
        print('All reference popups/images verified:', len(keys))

    def test_all_current_internal_named_references_resolve(self):
        audit = self.page.evaluate('''() => {
          const t=__refTest, missing=[], external=[];let checked=0;
          for (const e of Object.values(t.REF_ENTRIES)) {
            const text=(e.title+'\\n'+e.text).replace(/\\x10[^\\x11]*\\x11/g,'').replace(/\\[[^\\]]*\\]/g,'');
            for (const line of text.split('\\n')) for (const m of t.assetMentions(line)) {
              checked++;
              if (t.referenceSource(e,line.slice(0,m.at))==='unsupported') {external.push(e.id+': '+m.text);continue;}
              if (!t.assetTargets(m.kind,m.num,e,line,m.at).assets.length) missing.push(e.id+': '+m.text);
            }
          }
          return {checked,missing,external};
        }''')
        self.assertGreater(audit['checked'], 150)
        self.assertEqual(audit['missing'], [])
        print('Current named-reference audit:', audit)

    def test_duplicate_numbers_external_standards_and_old_captions(self):
        cases = self.page.evaluate('''() => {
          const t=__refTest;
          const get=(id,text,kind,num)=>t.assetTargets(kind,num,t.REF_ENTRIES[id],text,text.indexOf(kind==='table'?'표':'그림'));
          return {
            buttons:get('b22-16.1.5.2.4','표 16 참조','table','16').assets,
            verification:get('b22-18.2','표 16 참조','table','16').assets,
            rail:get('b22-Ⅷ.2.1','그림 Ⅷ.1 참조','figure','Ⅷ.1').assets,
            ladder:get('b22-Ⅶ.5','그림 Ⅷ.1 참조','figure','Ⅷ.1').assets,
            ks:get('b22-9.7.2','KS B ISO 13857, 표 4에 따른다','table','4').assets,
            oldCaption:get('b24-5.5.3.4','[ 그림 1 스커트 디플렉터의 요건 ]','figure','1').assets,
            alias:get('b22-Ⅻ','다음 표 Ⅱ.1은 고장 배제를 기술한다','table','Ⅱ.1'),
            compound:t.assetMentions('그림 24.1 및 24.2, 그림 27.1, 27.2 및 27.3').map(m=>m.num)
          };
        }''')
        self.assertEqual(cases['buttons'], ['b22-table-16'])
        self.assertEqual(cases['verification'], ['b22-table-16-verification'])
        self.assertEqual(cases['rail'], ['b22-figure-Ⅷ.1-p331'])
        self.assertEqual(cases['ladder'], ['b22-figure-Ⅷ.1'])
        self.assertEqual(cases['ks'], [])
        self.assertEqual(cases['oldCaption'], [])
        self.assertEqual(cases['alias']['assets'], ['b22-table-Ⅻ.1'])
        self.assertIn('표 Ⅻ.1', cases['alias']['note'])
        self.assertEqual(cases['compound'], ['24.1','24.2','27.1','27.2','27.3'])

    def test_parenthesized_table_row_is_not_a_definition_clause(self):
        actual = self.page.evaluate('''() => {
          const t=__refTest,e=t.REF_ENTRIES['b22-14.3.2.2'];
          document.querySelector('#results').innerHTML=t.card(e,null);
          t.linkClauseRefs(document.querySelector('#results'),e);
          const buttons=Array.from(document.querySelectorAll('.body [data-ref-assets]'));
          const row=buttons.find(b=>b.textContent==='3.6');
          if (!row) throw Error('Missing table row');row.click();
          return {target:row.dataset.refAssets, wrong:document.querySelectorAll('.body [data-ref-ids="b22-3.6"]').length};
        }''')
        self.assertEqual(actual, {'target':'b22-table-Ⅻ.1','wrong':0})
        self.assertIn('표 Ⅻ.1', self.page.locator('.ref-title').inner_text())
        content=self.page.locator('.ref-content');target=self.page.locator('[data-table-page="3"]')
        self.assertAlmostEqual(target.bounding_box()['y'],content.bounding_box()['y'],delta=2)

    def test_history_uses_its_own_illustrations(self):
        stats = self.page.evaluate('''() => {
          const t=__refTest;let historical=0;
          for (const e of Object.values(t.byId)) {
            if (!e.h) continue;
            const root=document.createElement('div');root.className='hist';root.innerHTML=t.historyHtml(e);t.linkClauseRefs(root,e);
            root.querySelectorAll('[data-ref-assets]').forEach(b=>{
              for (const key of b.dataset.refAssets.split(',')) {
                if (!t.REF_ASSETS[key].historical) throw Error('Current image in history: '+e.id+' '+key);
                historical++;
              }
            });
          }
          return historical;
        }''')
        self.assertGreater(stats, 10)
        print('Historical references to their own images:', stats)

    def test_standardization_external_and_historical_references(self):
        self.page.evaluate('KIJUN.setSource("std")')
        self.search('더블랩 권상도르래')
        card = self.page.locator('#std-424')
        if 'open' not in card.get_attribute('class').split():
            card.locator('.more').click()
        self.assertEqual(card.locator('.body [data-ref-assets*="table-4"]').count(), 0)
        self.assertGreater(card.locator('.body [data-ref-assets="b22-figure-19"]').count(), 0)
        self.search('화물용 문열림출발방지장치')
        card = self.page.locator('#std-722')
        if 'open' not in card.get_attribute('class').split():
            card.locator('.more').click()
        card.locator('.body [data-ref-assets="b22-figure-20"]').click()
        self.assertIn('그림 20', self.page.locator('.ref-title').inner_text())
        self.page.locator('[data-ref-close]').click()
        self.search('화물용 자동차용 제원')
        card = self.page.locator('#std-329')
        if 'open' not in card.get_attribute('class').split():
            card.locator('.more').click()
        if card.locator('.bg[hidden]').count():
            card.locator('.bgtoggle').click()
        card.locator('.body [data-ref-assets^="history-"]').first.click()
        self.assertIn('적용 연혁', self.page.locator('.ref-title').inner_text())
        self.assertIn('hel_p111_', self.page.locator('.ref-content img').first.get_attribute('src'))

    def test_external_clause_scope_survives_paragraph_breaks_in_quotations(self):
        refs=self.page.evaluate('''() => {
          const t=__refTest,e=t.byId['std-757'];const root=document.createElement('div');root.innerHTML=t.card(e,null);t.linkClauseRefs(root,e);
          const actual=Array.from(root.querySelectorAll('[data-ref-ids]')).map(b=>({text:b.textContent,ids:b.dataset.refIds}));
          const sample=document.createElement('div');sample.innerHTML='<section class="sec"><h3>관련 법령 / 고시</h3><p>별표22</p><p>16.3.2에 따른 기준</p><p>참고: EN81-20</p><p>5.12.3.2에 따른 외부 규격</p><p>별표24</p><p>5.12.3.2에 따른 기준</p></section>';
          t.linkClauseRefs(sample,{src:'std',title:''});
          return {actual,sample:Array.from(sample.querySelectorAll('[data-ref-ids]')).map(b=>b.dataset.refIds)};
        }''')
        self.assertTrue(any(r['text']=='16.3.2' and r['ids']=='b22-16.3.2' for r in refs['actual']))
        self.assertFalse(any(r['text']=='5.12.3.2' for r in refs['actual']))
        self.assertEqual(refs['sample'],['b22-16.3.2','b24-5.12.3.2'])

    def test_all_cards_and_history_keep_text_and_resolve_existing_targets(self):
        stats = self.page.evaluate('''() => {
          const t = window.__refTest;
          let cards = 0, histories = 0, links = 0;
          const check = (html, entry, historical=false) => {
            const root = document.createElement('div'); root.innerHTML = html;
            if (historical) root.className='hist';
            const text = root.textContent;
            t.linkClauseRefs(root, entry);
            if (root.textContent !== text) throw Error('Text changed: ' + entry.id);
            root.querySelectorAll('.clause-ref').forEach(b => {
              if (b.querySelector('button')) throw Error('Nested button: ' + entry.id);
              if (b.dataset.refAssets) {
                b.dataset.refAssets.split(',').forEach(key => { if (!t.REF_ASSETS[key]) throw Error('Missing asset: ' + key); });
              } else b.dataset.refIds.split(',').forEach(id => { if (!t.REF_ENTRIES[id]) throw Error('Missing target: ' + id); });
              links++;
            });
          };
          for (const entry of Object.values(t.byId)) {
            check(t.card(entry, null), entry); cards++;
            if (entry.h) { check(t.historyHtml(entry), entry, true); histories++; }
          }
          return {cards, histories, links};
        }''')
        self.assertGreater(stats['cards'], 2000)
        self.assertGreater(stats['histories'], 900)
        self.assertGreater(stats['links'], 1000)
        print('All-data reference audit:', stats)


if __name__ == '__main__':
    unittest.main()
