"""승강기 설치검사 및 안전검사 결과 판정 및 확인검사 지침(2019.9.27 제정) PDF → 불합격 카드(fail.json)
- 지침 본문(제1조~부칙): 조 단위 카드
- 별표2 '설치검사 및 안전검사 검사항목 별 불합격 내용': 표의 한 행 = 카드 {검사항목(조항) · 검사대상 · 불합격 내용}
  표는 PyMuPDF find_tables 로 칸을 잡고, 칸 안 글자는 글자 간격으로 띄어쓰기를 되살린다(한글 PDF라 공백 글자가 없음).
  위 행과 합쳐진 칸(None)은 위 행 값을 쓰고, 첫 두 칸이 빈 행은 앞 쪽에서 이어지는 행.
사용: python fail_parse.py  →  fail.json"""
import pymupdf, re, json, sys, os
os.chdir(os.path.dirname(os.path.abspath(__file__)))
SRC = 'fail_src/fail.pdf'
GAP = 2.5   # 글자 사이가 이만큼(pt) 벌어지면 띄어쓰기

def chars_text(cs):
    out = ''
    for a, c in zip([None] + cs, cs):
        if a is not None and c['c'] != ' ' and a['c'] != ' ' and c['bbox'][0] - a['bbox'][2] > GAP: out += ' '
        out += c['c']
    return re.sub(r' {2,}', ' ', out).strip()

def lines_in(blocks, rect):
    """rect 안의 줄들 [(x0, y0, x1, 글자)] — 글자 하나하나의 가운데가 rect 안에 든 것만(칸 경계를 넘는 줄 조각이 옆 칸에 섞이지 않게)"""
    out = []
    for b in blocks:
        for l in b.get('lines', []):
            cs = [c for s in l['spans'] for c in s['chars'] if rect.contains(pymupdf.Point((c['bbox'][0] + c['bbox'][2]) / 2, (c['bbox'][1] + c['bbox'][3]) / 2))]
            t = chars_text(cs)
            if t: out.append((cs[0]['bbox'][0], l['bbox'][1], cs[-1]['bbox'][2], t))
    out.sort(key=lambda r: (round(r[1]), r[0]))
    # 같은 높이 줄은 하나로
    merged = []
    for r in out:
        if merged and abs(merged[-1][1] - r[1]) < 3: merged[-1] = (merged[-1][0], merged[-1][1], r[2], merged[-1][3] + ' ' + r[3])
        else: merged.append(r)
    return merged

NEWL = re.compile(r'^(?:[․·•\-※]|\(|\d+\.|[가-하]\.|[①-⑳])')
# 한글 PDF는 줄 끝 띄어쓰기 정보가 없고 칸 글은 양쪽 맞춤이라 줄 길이로도 알 수 없다.
# 그래서 줄 끝 낱말 + 다음 줄 첫 낱말을 붙인 말이 안전기준·표준화 원문(어휘집)에 있으면 붙이고('작'|'업구역' → 작업구역), 없으면 띄운다('브레이크'|'미작동')
VOCAB = set()
def load_vocab():
    import os
    texts = []
    for f in ('base_el.json', 'base_es.json'):
        if os.path.exists(f): texts += [e['title'] + ' ' + e['text'] for e in json.load(open(f, encoding='utf-8'))]
    if os.path.exists('data.json'): texts += [e.get('text', '') for e in json.load(open('data.json', encoding='utf-8')).get('std', [])]
    for s in texts:
        for w in re.findall(r'[가-힣A-Za-z0-9]+', s): VOCAB.add(w)
def joiner(prev, nxt):
    if prev.endswith('/'): return ''   # '로프/' + '관련 부품' → '로프/관련'
    a = re.search(r'([가-힣A-Za-z0-9]+)$', prev); b = re.match(r'^([가-힣A-Za-z0-9]+)', nxt)
    if not a or not b: return ' '
    g = a.group(1) + b.group(1)
    # 붙인 말(조사 1~2자를 뗀 것 포함)이 어휘집에 있으면 낱말 중간에서 끊긴 것
    if any(len(f) > len(a.group(1)) and f in VOCAB for f in (g, g[:-1], g[:-2])): return ''
    # 다음 줄이 한 글자 낱말로 시작하면(광커|튼, 미취|부) 앞 낱말의 꼬리
    if len(b.group(1)) == 1 and re.match(r'[가-힣]', b.group(1)) and b.group(1) not in '및등시카수중후전각문외내위상하': return ''
    return ' '
def cell_text(rows, rect):
    """칸 안 줄 → 글. 글머리(․ - ( 1. 가.)로 시작하면 새 줄, 아니면 앞 줄에 잇는다(줄이 칸 오른쪽 끝까지 찼으면 붙이고, 아니면 띄움)"""
    paras = []; prev = None
    for x0, y0, x1, t in rows:
        if paras and not NEWL.match(t):
            glue = joiner(paras[-1], t)
            paras[-1] += glue + t
        else: paras.append(t)
        prev = (x0, y0, x1)
    return '\n'.join(paras)

def main():
    load_vocab()
    d = pymupdf.open(SRC)
    out = []
    # ---- 1) 지침 본문(2~5쪽): 조 단위
    body = []
    for pi in range(1, 5):
        bl = d[pi].get_text('rawdict')['blocks']
        for x0, y0, x1, t in lines_in(bl, d[pi].rect):
            if re.fullmatch(r'\d+', t) or t in ('부', '칙'): continue
            body.append((pi, x0, x1, t))
    arts = []; sect = '지침'
    for pi, x0, x1, t in body:
        if t.startswith('승강기 설치검사 및 안전검사 결과 판정') or t.startswith('제정'): continue
        m = re.match(r'^(제\d+조)\s*\(([^)]+)\)\s*(.*)$', t)
        if m:
            if arts and m.group(1) == '제1조': sect = '부칙'
            arts.append({'num': m.group(1), 'title': m.group(2), 'sect': sect, 'lines': [(x0, x1, m.group(3))]}); continue
        if arts: arts[-1]['lines'].append((x0, x1, t))
    for a in arts:
        paras = []
        for x0, x1, t in a['lines']:
            if not t: continue
            if paras and not NEWL.match(t): paras[-1] += joiner(paras[-1], t) + t
            else: paras.append(t)
        out.append({'src': 'fail', 'id': 'fail-' + ('b' if a['sect'] == '부칙' else 'j') + a['num'][1:-1], 'num': ('부칙 ' if a['sect'] == '부칙' else '') + a['num'],
                    'title': a['title'], 'path': '판정 지침 ' + ('부칙' if a['sect'] == '부칙' else '본문'), 'text': '\n'.join(paras)})
    # ---- 2) 별표2 불합격 내용 표(6쪽~)
    sec = None; prevrow = None; n = 0; notepre = None
    for pi in range(5, d.page_count):
        pg = d[pi]; bl = pg.get_text('rawdict')['blocks']
        tabs = pg.find_tables().tables
        for x0, y0, x1, t in lines_in(bl, pg.rect):
            m = re.match(r'^\d\.\s*별표\s*(\d+)\s*(.+?)\s*안전기준', t)
            if m and not any(pymupdf.Rect(tb.bbox).contains(pymupdf.Point(x0 + 1, y0 + 1)) for tb in tabs):
                sec = f'별표{m.group(1)} {m.group(2)}'; prevrow = None
        for tb in tabs:
            for row in tb.rows:
                cells = [pymupdf.Rect(c) if c else None for c in row.cells]
                vals = [cell_text(lines_in(bl, c), c) if c else None for c in cells]
                if vals[0] and vals[0].replace(' ', '') == '검사항목': continue
                if vals[0] and vals[1] is None and vals[2] is None and vals[0].startswith('※') and len(vals[0]) <= 30:
                    notepre = vals[0]; continue   # 비고 머리('※ 추가사항')만 이 쪽 끝에 있고 내용은 다음 쪽(별표23)
                if vals[0] and vals[1] is None and vals[2] is None and len(vals[0]) > 30:   # 표 끝의 비고(행 전체 합친 칸)
                    txt = (notepre + ' ' + vals[0]) if notepre and not vals[0].startswith('※') else vals[0]; notepre = None
                    out.append({'src': 'fail', 'id': f'fail-{sec.split()[0]}-note', 'num': '', 'title': '비고', 'path': sec + ' 안전기준', 'text': txt}); continue
                if prevrow and (vals[1] or '') == '' and (vals[0] or '' or vals[2]):   # 앞 쪽에서 이어지는 행(검사대상 칸이 빈 행)
                    if vals[2]:
                        v = vals[2]
                        prevrow['text'] += ('\n' if NEWL.match(v) else joiner(prevrow['text'], v)) + v
                    if vals[0]:   # 이어지는 행에 다른 조항 번호가 붙어 있으면(8.5.2.3 → 9.7.2.3) 같은 내용의 카드 하나 더
                        n += 1; e = dict(prevrow, id=f'fail-{n}', num=vals[0].replace('\n', ' · ')); out.append(e); prevrow = e
                    continue
                num = vals[0] if vals[0] is not None else (prevrow['num'] if prevrow else '')
                title = vals[1] if vals[1] is not None else (prevrow['title'] if prevrow else '')
                text = vals[2] if vals[2] is not None else (prevrow['text'] if prevrow else '')
                n += 1
                e = {'src': 'fail', 'id': f'fail-{n}', 'num': num.replace('\n', ' · '), 'title': title.replace('\n', ' '), 'path': sec + ' 안전기준', 'text': text, 'p': pi + 1}
                out.append(e); prevrow = e
    # 글머리 '․'(한 점 리더)는 가운뎃점으로, 목차는 별표 표를 먼저·지침 본문은 뒤로
    for e in out: e['text'] = re.sub(r'(?m)^․\s*', '· ', e['text'])
    out = [e for e in out if not e['path'].startswith('판정 지침')] + [e for e in out if e['path'].startswith('판정 지침')]
    json.dump(out, open('fail.json', 'w', encoding='utf-8'), ensure_ascii=False)
    print('fail cards', len(out), {s: sum(1 for e in out if e['path'] == s) for s in dict.fromkeys(e['path'] for e in out)})

if __name__ == '__main__':
    main()
