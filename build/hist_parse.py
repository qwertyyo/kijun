"""승강기 안전기준 연혁집(한국승강기안전공단, 2025.10) PDF → 현행 별표22 조문번호별 연혁 블록
hist.json = {조문번호: {"cur": {"d","basis","raw"}|null, "blocks": [{"head","from","to","basis","siheng","text"}]}}
- 현행 조문: H2mjsM 12pt, 왼쪽 여백(x<66)에서 번호로 시작하는 줄
- 현행 조문 적용 표시: T14 '<2019년4월4일이후건축허가분부터적용>'
- 연혁 블록: '➥' + H2gtrE 제목(…이후의 건축허가분부터 적용 / …부터 시행 / …전의 … 종전 기준), 오른쪽 Gulim '… 시행' 표시
- 연혁 본문(8pt)은 PDF에서 띄어쓰기가 글자 간격으로만 남아 있어 간격(>1.5pt)으로 공백을 되살린다
- 초록(변경된 내용)·빨강(강조) 글자는 \x01…\x02 / \x03…\x04 로 표시해 둔다"""
import pymupdf, re, json, sys
# 사용: hist_parse.py el  (엘리베이터 연혁집 → hist.json)   /   hist_parse.py es  (에스컬레이터 연혁집 v2.0 → hist_es.json)
MODE = sys.argv[1] if len(sys.argv) > 1 else 'el'
CFG = {
    'el': dict(src='hist_src/hist.pdf', base='hwp/b22h.json', out='hist.json', curout='hist_cur.json', start=2,
               cur_font=('H2mjsM', 'Haansoft Batang'), cur_min=10, head_x=66, mark_font='T14', skip_fonts=()),
    'es': dict(src='hist_es/hist.pdf', base='hwp/b24h.json', out='hist_es.json', curout='hist_es_cur.json', start=8,
               cur_font=('TT5CF94827',), cur_min=11, head_x=80, mark_font='TT5CF94827', skip_fonts=('TTE7E4FEC1', 'TT7FCCDD19', 'HaansoftBatang')),
}[MODE]
SRC = CFG['src']
b22nums = [e['num'] for e in json.load(open(CFG['base']))]
NUMSET = set(b22nums)
_nz = lambda s: re.sub(r'[\s\W_ᆞㆍ‧·]+', '', s)
B22HEAD = {e['num']: _nz(e['title'] + e['text'])[:80] for e in json.load(open(CFG['base']))}
def head_ok(num, rest):
    r = _nz(rest)[:6]
    if MODE == 'es': r = r[:4]
    return not r or r in B22HEAD.get(num, '')
ORDER = {n: i for i, n in enumerate(b22nums)}
DRE = r'(\d{4})\s*년\s*(\d{1,2})\s*[월일]\s*(\d{1,2})\s*일?'
def dates(s): return [f'{a}.{int(b):02d}.{int(c):02d}' for a, b, c in re.findall(DRE, s)]
GREEN, RED = 0x008000, 0xff0000
def line_text(l):
    """rawdict 줄 → 텍스트(간격으로 공백 복원, 색 표시)"""
    out = []; prev = None; mode = 0
    for s in l['spans']:
        col = s['color']; m = 1 if col == GREEN else 2 if col == RED else 0
        for c in s['chars']:
            ch = c['c']
            if prev is not None and ch != ' ' and prev['c'] != ' ' and c['bbox'][0] - prev['bbox'][2] > 1.5: out.append(' ')
            if m != mode:
                if mode == 1: out.append('\x02')
                if mode == 2: out.append('\x04')
                if m == 1: out.append('\x01')
                if m == 2: out.append('\x03')
                mode = m
            out.append(ch); prev = c
    if mode == 1: out.append('\x02')
    if mode == 2: out.append('\x04')
    return re.sub(r' {2,}', ' ', ''.join(out))
HEADRE = re.compile(r'^((?:XⅢ|XⅣ|[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩⅪⅫ])(?:\.\d+)*|\d+(?:\.\d+)*)\.?(?=\s|「|$)')
NEWPARA = re.compile(r'^\s*(?:\[[^\]]{1,6}\]|\d+(?:\.\d+)+(?:\(\d+\))?[①-⑳]?|\d+\.\d+\(\d+\)|[①-⑳]|[가-하]\)|[a-z]\)|\([가-하]\)|[가-하]\.|비고|<|※|-|\d+\))')
def join(lines):
    paras = []
    for t in lines:
        if isinstance(t, list):   # 그림 영역: \x10파일|폭|높이\x0e검색용 글자\x11
            name, w, h, txts = t
            paras.append('\x10%s|%d|%d\x0e%s\x11' % (name, w, h, re.sub(r'[\x01-\x04]', '', ' '.join(txts)))); continue
        plain = re.sub(r'[\x01-\x04]', '', t).strip()
        if not plain: continue
        prevp = re.sub(r'[\x01-\x04]', '', paras[-1]) if paras else ''
        if prevp.startswith('\x10'): paras.append(t.strip()); continue
        # '8.2.3 정원'처럼 번호+짧은 제목만 있는 줄 다음은 새 문단
        title_only = bool(re.match(r'^(?:\[[^\]]+\]\s*)?\d+(?:\.\d+)+(?:\(\d+\))?\s+[^.。]{1,30}$', prevp)) and not re.search(r'(다|며|고|여|한)$', prevp)
        if not paras or NEWPARA.match(plain) or title_only: paras.append(t.strip())
        else:
            prevp = re.sub(r'[\x01-\x04]', '', paras[-1])
            paras[-1] += (' ' if re.search(r'[,.)」”은는을를의에며고서면나와과및수등할된될야도]$', prevp) else '') + t.strip()
    return '\n'.join(paras)
def classify(head):
    h = re.sub(r'\s+', ' ', head)
    ds = dates(h)
    f = t = None
    if '종전' in h or re.search(r'전\S*의 건축허가분|전까지', h):
        m = re.search(DRE + r'\s*(이후|부터)', h)
        if m and len(ds) >= 2: f, t = ds[0], ds[1]
        elif ds: t = ds[-1]
    elif ds: f = ds[0]
    basis = '허가' if '건축허가' in h else '시행' if '시행' in h else ''
    return f, t, basis
DET = []
REJ = []
# ---- 연혁 블록 속 그림·표·수식: 글자로 뽑으면 뒤죽박죽이 되므로 원문 영역을 그림으로 잘라 넣는다
import os, io
from PIL import Image
FIGDIR = 'fig'; os.makedirs(FIGDIR, exist_ok=True)
PUA = re.compile('[-]')
def regions(pg, rows):
    """그림(이미지)·선으로 그린 도형/표·수식 줄을 묶어 영역 목록으로"""
    H = pg.rect.height
    seeds = []
    for info in pg.get_image_info():
        r = pymupdf.Rect(info['bbox'])
        if r.width < 30 or r.height < 20 or (r.width > 500 and r.height < 80) or r.y1 < 45: continue   # 머리글 띠 그림 제외
        seeds.append((r, 'img'))
    for dr in pg.get_drawings():
        r = dr['rect']
        if r.width < 1.5 and r.height < 1.5: continue            # 점선 구분선 조각
        if dr.get('fill') is not None and r.height < 16 and r.width > 100: continue   # 연혁 제목 띠
        if r.y1 < 45 or r.y0 > H - 40: continue                   # 머리글·바닥글
        seeds.append((pymupdf.Rect(r.x0 - 0.5, r.y0 - 0.5, r.x1 + 0.5, r.y1 + 0.5), 'dr'))   # 폭 0인 선도 겹침 판정되게
    for y, x, font, size, txt, l in rows:
        if PUA.search(txt):
            pr = pymupdf.Rect()
            for sp in l['spans']:
                for c in sp['chars']:
                    if PUA.match(c['c']): pr |= pymupdf.Rect(c['bbox'])
            if pr.height < 16: continue   # 한 줄짜리 기호(Rm, b1 등)는 글자로 둔다(분수가 아니면)
            seeds.append((pymupdf.Rect(l['bbox']), 'eq'))   # 수식이 든 줄은 줄 전체를 그림으로
    # 가까운 것끼리 묶기(수식 2pt, 그림·도형 8pt — 그림 옆 설명 도형까지 한 덩어리로)
    cl = []
    for r, k in seeds:
        rr = pymupdf.Rect(r); kinds = {k}; cnt = 1
        merged = True
        while merged:
            merged = False
            for c in cl[:]:
                g = 2 if ('eq' in kinds and c[1] == {'eq'}) or (kinds == {'eq'}) else 8
                if (c[0] + (-g, -g, g, g)).intersects(rr + (-g, -g, g, g)):
                    rr |= c[0]; kinds |= c[1]; cnt += c[2]; cl.remove(c); merged = True
        cl.append((rr, kinds, cnt))
    out = []
    for r, kinds, cnt in cl:
        if 'img' not in kinds and 'eq' not in kinds and (r.width < 40 or r.height < 25): continue
        if kinds == {'eq'} and r.height < 16: continue   # 한 줄짜리 기호(Rm, b1 등)는 글자로 둔다(분수가 아니면)
        if r.height > H * 0.8: continue
        # 영역 안 글자 줄도 포함되도록 넓히고, 연혁 제목(➥)이나 현행 조문 제목이 들어 있으면 틀(테두리)이므로 버린다
        bad = False
        for y, x, font, size, txt, l in rows:
            lb = pymupdf.Rect(l['bbox']); cx, cy = (lb.x0 + lb.x1) / 2, (lb.y0 + lb.y1) / 2
            if r.contains(pymupdf.Point(cx, cy)):
                m = HEADRE.match(txt.strip())
                if '➥' in txt or (font.startswith(CFG['cur_font']) and size >= CFG['cur_min'] and m and lb.x0 < CFG['head_x'] and m.group(1) in NUMSET): bad = True
                r |= lb
        if bad: continue
        # 영역 밖 글자 줄이 위아래로 걸치면 그만큼 잘라 낸다(앞뒤 문장이 그림에 묻어 나오지 않게)
        for y, x, font, size, txt, l in rows:
            lb = pymupdf.Rect(l['bbox']); cy = (lb.y0 + lb.y1) / 2
            if r.contains(pymupdf.Point((lb.x0 + lb.x1) / 2, cy)) or lb.x1 < r.x0 or lb.x0 > r.x1: continue
            if lb.y1 > r.y0 and cy < r.y0: r.y0 = lb.y1
            elif lb.y0 < r.y1 and cy > r.y1: r.y1 = lb.y0
        if r.height <= 6: continue
        if kinds == {'dr'}:   # 선만 있는 영역: 글자 1~2줄을 감싼 테두리 상자는 글자로 둔다
            inside = [l for y, x, font, size, txt, l in rows if r.contains(pymupdf.Point((l['bbox'][0] + l['bbox'][2]) / 2, (l['bbox'][1] + l['bbox'][3]) / 2))]
            if r.height < 45 and len(inside) <= 3: continue
            if cnt < 12 and len(inside) > 3: continue   # 글 문단을 두른 틀(선 몇 개)은 표가 아니다
        out.append(r)
    return out
def crop(pg, r, name):
    pix = pg.get_pixmap(clip=(r + (-2, -1, 2, 1)) & pg.rect, dpi=200)
    im = Image.open(io.BytesIO(pix.tobytes('png'))).convert('RGB')
    im.save(os.path.join(FIGDIR, name), 'WEBP', quality=88, method=6)
    return im.width, im.height
def main():
    d = pymupdf.open(SRC)
    hist = {}; cur = None; blk = None; prev_num = None; CUR = {}
    def close():
        nonlocal blk
        if blk is not None and cur:
            blk['text'] = join(blk.pop('lines')); hist.setdefault(cur, {'cur': None, 'blocks': []})['blocks'].append(blk)
        blk = None
    for pi in range(CFG['start'], d.page_count):
        pg = d[pi]
        rows = []
        for b in pg.get_text('rawdict')['blocks']:
            for l in b.get('lines', []):
                if not l['spans']: continue
                s0 = l['spans'][0]
                txt = ''.join(c['c'] for s in l['spans'] for c in s['chars'])
                if not txt.strip(): continue
                rows.append((l['bbox'][1], l['bbox'][0], s0['font'], round(s0['size']), txt, l))
        regs = regions(pg, rows)
        for k, r in enumerate(regs): rows.append((r.y0 - 0.5, r.x0, '__REG__', 0, str(k), r))
        rows.sort(key=lambda r: (round(r[0]), r[1]))
        act = {}   # 이 쪽에서 블록 안에 들어간 영역 번호 → 그 줄(나중에 글자 모음)
        # 같은 높이의 오른쪽 '시행' 표시(Gulim 8pt)
        siheng_y = [r[0] for r in rows if r[2] == 'Gulim' and r[3] == 8 and r[4].strip().endswith('시행')]
        for y, x, font, size, txt, l in rows:
            if font == '__REG__':
                if blk is not None:
                    name = f'h{MODE}_p{pi + 1}_{txt}.webp'; w, h = crop(pg, l, name)
                    act[int(txt)] = [name, w, h, []]; blk['lines'].append(act[int(txt)])
                continue
            if font != '__REG__' and act:
                lb = l['bbox']; cx, cy = (lb[0] + lb[2]) / 2, (lb[1] + lb[3]) / 2
                hit = next((k for k in act if regs[k].contains(pymupdf.Point(cx, cy))), None)
                if hit is not None:
                    act[hit][3].append(line_text(l)); continue
            st = txt.strip()
            if font == 'Gulim' and (size == 10 and re.fullmatch(r'\d+', st) or size == 8): continue   # 쪽번호, '시행' 표시
            if font.startswith(CFG['skip_fonts']) if CFG['skip_fonts'] else False: continue   # 머리글·쪽번호
            if '➥' in txt:
                close()
                head = st.replace('➥', '').strip()
                blk = {'head': head, 'lines': [], 'y': y, 'pi': pi, 'siheng': any(abs(sy - y) < 4 for sy in siheng_y)}
                continue
            if font == 'H2gtrE' and blk is not None and not blk['head']:
                blk['head'] = st; blk['siheng'] = blk['siheng'] or any(abs(sy - y) < 4 for sy in siheng_y); continue
            if font.startswith(CFG['mark_font']) and size == 10 and st.startswith('<'):
                if blk is not None and blk['lines']:
                    pass
                if cur and re.search(r'적용|시행|삭제', st):
                    close()
                    ds = dates(st)
                    hist.setdefault(cur, {'cur': None, 'blocks': []})['cur'] = {'raw': st, 'd': ds[0] if ds else None, 'basis': '허가' if '건축허가' in st else '시행'}
                continue
            if font.startswith(CFG['cur_font']) and size >= CFG['cur_min']:
                m = HEADRE.match(st)
                if m and x < CFG['head_x'] and m.group(1) not in NUMSET: REJ.append((pi+1, st[:50]))
                if m and x < CFG['head_x'] and m.group(1) in NUMSET and (prev_num is not None and ORDER[m.group(1)] <= ORDER[prev_num]): REJ.append((pi+1, 'ORDER '+st[:50]))
                if m and x < CFG['head_x'] and m.group(1) in NUMSET and head_ok(m.group(1), st[m.end():]) and (prev_num is None or ORDER[m.group(1)] > ORDER[prev_num]):
                    close(); cur = prev_num = m.group(1); DET.append(cur); CUR.setdefault(cur, []).append(st)
                else:
                    if blk is not None: close()   # 현행 본문이 이어지면 블록 끝
                    if cur: CUR.setdefault(cur, []).append(txt.rstrip())
                continue
            if blk is None and cur and size >= 9 and font not in ('Gulim',):
                CUR.setdefault(cur, []).append(txt.rstrip()); continue
            if blk is not None and size <= 10 and not font.startswith(CFG['cur_font']):
                blk['lines'].append(line_text(l))
    close()
    out = {}
    for n, h in hist.items():
        bl = []
        for b in h['blocks']:
            f, t, basis = classify(b['head'])
            bl.append({'head': re.sub(r'\s+', ' ', b['head']), 'from': f, 'to': t, 'basis': basis, 'siheng': b['siheng'], 'text': b['text']})
        out[n] = {'cur': h['cur'], 'blocks': bl}
    json.dump(out, open(CFG['out'], 'w', encoding='utf-8'), ensure_ascii=False)
    json.dump(CUR, open(CFG['curout'], 'w', encoding='utf-8'), ensure_ascii=False)
    nb = sum(len(v['blocks']) for v in out.values())
    print('clauses with history', sum(1 for v in out.values() if v['blocks']), 'blocks', nb, 'cur markers', sum(1 for v in out.values() if v['cur']))
main()
import sys
b=json.load(open(CFG['base']))
withtext=[e['num'] for e in b if e['text'].strip()]
miss=[n for n in withtext if n not in set(DET)]
print('detected',len(DET),'b22 with text',len(withtext),'missing',len(miss), miss[:60])
print('rejected', REJ[:40]); i=[k for k,x in enumerate(DET) if x.startswith('11.2.1')]; print(DET[i[0]-3:i[-1]+6] if i else DET[150:200])
