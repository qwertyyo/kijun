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
                 '6.1.8.3에 따른 기준', '6.1.8.8 참조']
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
        body = body[:hook_at] + 'window.__refTest = { card, historyHtml, linkClauseRefs, byId, REF_ENTRIES };\n' + body[hook_at:]
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
        ref.click()
        self.page.wait_for_selector('.ref-window:not([hidden])')
        return card

    def test_example_preserves_query_results_and_reading_position(self):
        card = self.open_example()
        before = self.page.evaluate('({q:document.querySelector("#q").value,y:scrollY,ids:KIJUN.results(20).map(e=>e.num)})')
        self.assertIn('17.3.5.1', self.page.locator('.ref-title').inner_text())
        self.assertIn('피난호출 스위치', self.page.locator('.ref-content').inner_text())
        self.assertEqual(len(self.page.context.pages), 1)
        self.page.locator('[data-ref-close]').click()
        after = self.page.evaluate('({q:document.querySelector("#q").value,y:scrollY,ids:KIJUN.results(20).map(e=>e.num)})')
        self.assertEqual(before, after)
        self.assertIn('open', card.get_attribute('class').split())

    def test_nested_reference_back_and_parent_clause(self):
        self.open_example()
        self.page.locator('[data-ref-close]').click()
        card = self.page.locator('[id="b22-17.3.5.7"]')
        card.locator('.body [data-ref-num="16.3"]').click()
        self.assertIn('16.3', self.page.locator('.ref-title').inner_text())
        self.assertGreater(self.page.locator('.ref-content .card').count(), 1)
        ref = self.page.locator('.ref-content .clause-ref').first
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

    def test_escalator_uses_escalator_clauses(self):
        self.page.evaluate('KIJUN.setSource("b24")')
        self.search('핸드레일')
        refs = self.page.locator('#results .card.b24 .clause-ref')
        self.assertGreater(refs.count(), 0)
        self.assertTrue(all(r.startswith('b24-') for r in refs.evaluate_all('(es)=>es.map(e=>e.dataset.refIds)')))
        refs.first.click()
        self.assertIn('에스컬레이터', self.page.locator('.ref-title').inner_text())

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

    def test_all_cards_and_history_keep_text_and_resolve_existing_targets(self):
        stats = self.page.evaluate('''() => {
          const t = window.__refTest;
          let cards = 0, histories = 0, links = 0;
          const check = (html, entry) => {
            const root = document.createElement('div'); root.innerHTML = html;
            const text = root.textContent;
            t.linkClauseRefs(root, entry);
            if (root.textContent !== text) throw Error('Text changed: ' + entry.id);
            root.querySelectorAll('.clause-ref').forEach(b => {
              if (b.querySelector('button')) throw Error('Nested button: ' + entry.id);
              b.dataset.refIds.split(',').forEach(id => { if (!t.REF_ENTRIES[id]) throw Error('Missing target: ' + id); });
              links++;
            });
          };
          for (const entry of Object.values(t.byId)) {
            check(t.card(entry, null), entry); cards++;
            if (entry.h) { check(t.historyHtml(entry), entry); histories++; }
          }
          return {cards, histories, links};
        }''')
        self.assertGreater(stats['cards'], 2000)
        self.assertGreater(stats['histories'], 900)
        self.assertGreater(stats['links'], 1000)
        print('All-data reference audit:', stats)


if __name__ == '__main__':
    unittest.main()
