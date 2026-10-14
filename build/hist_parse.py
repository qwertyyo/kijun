"""승강기 안전기준 연혁집 PDF 하나로 (1) 현행 조문 목록·본문 → base_el.json / base_es.json (사이트의 엘리베이터·에스컬레이터 카드)
(2) 조문번호별 연혁 블록 → hist.json / hist_es.json 을 만든다. 별표22·24 HWP 는 쓰지 않는다.
- 현행 조문 머리: 현행 본문 글꼴, 왼쪽 여백(x<head_x)에서 번호로 시작하는 줄 + 번호가 앞 조문 다음으로 그럴듯할 것(plausible)
- 부속서: 가운데 '부속서 Ⅰ' 줄 + 바로 아래 가운데 줄(제목)
- 현행 본문 문단: 앞을 공백으로 들여 쓴 줄은 새 문단, 들여쓰기 없는 줄은 앞 줄에 잇는다(앞 줄 끝에 공백이 있을 때만 띄움)
- 현행 조문 적용 표시: '<2019년4월4일이후건축허가분부터적용>' 같은 줄
- 연혁 블록: '➥' + H2gtrE 제목(…이후의 건축허가분부터 적용 / …부터 시행 / …전의 … 종전 기준), 오른쪽 Gulim '… 시행' 표시
- 연혁 본문(8pt)은 PDF에서 띄어쓰기가 글자 간격으로만 남아 있어 간격(>1.5pt)으로 공백을 되살린다
- 초록(변경된 내용)·빨강(강조) 글자는 \x01…\x02 / \x03…\x04 로 표시해 둔다
- 본문·연혁 속 그림·선으로 그린 표·분수식은 원문 영역을 200dpi 로 잘라 \x10파일|폭|높이\x0e검색용 글자\x11 로 넣는다"""
import pymupdf, re, json, sys
sys.path.insert(0, '.')   # build.py 가 -I 로 실행해도 restore_eq 를 찾게
# 사용: hist_parse.py el  (엘리베이터 연혁집 → hist.json)   /   hist_parse.py es  (에스컬레이터 연혁집 v2.0 → hist_es.json)
MODE = sys.argv[1] if len(sys.argv) > 1 else 'el'
CFG = {
    'el': dict(src='hist_src/hist.pdf', prefix='b22', baseout='base_el.json', out='hist.json', start=2,
               cur_font=('H2mjsM', 'Haansoft Batang'), cur_min=10, head_x=66, mark_font='T14', skip_fonts=()),
    'es': dict(src='hist_es/hist.pdf', prefix='b24', baseout='base_es.json', out='hist_es.json', start=8,
               cur_font=('TT5CF94827',), cur_min=11, head_x=80, mark_font='TT5CF94827', skip_fonts=('TTE7E4FEC1',), num_fonts=('TT7FCCDD19', 'HaansoftBatang')),
}[MODE]
SRC = CFG['src']
# ---- 조문 번호 순서(부속서는 100+로마숫자)
ROMAN = 'ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩⅪⅫ'
RV = {c: i + 1 for i, c in enumerate(ROMAN)}; RV['XⅢ'] = 13; RV['XⅣ'] = 14
RPAT = r'(?:XⅢ|XⅣ|[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩⅪⅫ])'
def key(num):
    m = re.match(r'^(' + RPAT + r')(?:\.(.*))?$', num)
    if m: return (100 + RV[m.group(1)],) + (tuple(int(x) for x in m.group(2).split('.')) if m.group(2) else ())
    return tuple(int(x) for x in num.split('.'))
def plausible(prev, cand):
    """앞 조문 번호 다음에 올 수 있는 번호인가(본문 속 '6.4.3.1 참조' 같은 줄을 조문 머리로 잡지 않게)"""
    if prev is None: return cand == (1,)
    if cand <= prev: return False
    if cand[0] >= 100 and prev[0] < 100: return cand == (101,) and prev[0] >= 5
    if cand[0] >= 100 and cand[0] != prev[0]: return len(cand) == 1 and cand[0] == prev[0] + 1
    c = 0
    while c < len(prev) and c < len(cand) and prev[c] == cand[c]: c += 1
    if c == len(cand): return False
    if c == len(prev): return all(x == 1 for x in cand[c:]) and len(cand) - c <= 2
    step = cand[c] - prev[c]
    if not (1 <= step <= 2): return False
    return all(x == 1 for x in cand[c + 1:]) and len(cand) - c <= 3
BAD = re.compile(r'^(참조|및|또는|부터|까지|이상|이하|초과|미만|㎜|mm|m\b|㎝|N\b|kg|㎏|%|V\b(?!-)|A\b|lx|㏓|°|㎧|㎨|㎐|Hz|㎫|㎪|㎡|㎥|㎠|㎟|×|=|≤|≥)')
ANNEX = re.compile(r'^부속서\s*(' + RPAT + r')$')
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
            paras.append('\x10%s|%d|%d\x0e%s\x11' % (name, w, h, figtext(txts))); continue
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
ENDFIG = []   # 연혁 블록 끝 점선 다음 그림이라 현행 본문으로 보낸 것(확인용)
REJ = []
# ---- 연혁 블록 속 그림·표·수식: 글자로 뽑으면 뒤죽박죽이 되므로 원문 영역을 그림으로 잘라 넣는다
import os, io
from PIL import Image
FIGDIR = 'fig'; os.makedirs(FIGDIR, exist_ok=True)
PUA = re.compile('[-]')
from restore_eq import M as EQMAP   # 글자로 되살릴 수 있는 수식 글꼴 코드
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
            if pr.height < 16 and all(ord(c) in EQMAP for c in txt if PUA.match(c)): continue   # 한 줄짜리 기호(Rm, b1 등)는 글자로 둔다(분수가 아니면)
            seeds.append((pymupdf.Rect(l['bbox']), 'eq1' if pr.height < 16 else 'eq'))   # 수식이 든 줄은 줄 전체를 그림으로
    # 가까운 것끼리 묶기(수식 2pt, 그림·도형 8pt — 그림 옆 설명 도형까지 한 덩어리로)
    cl = []
    for r, k in seeds:
        rr = pymupdf.Rect(r); kinds = {k}; cnt = 1
        merged = True
        while merged:
            merged = False
            for c in cl[:]:
                E = {'eq', 'eq1'}
                g = 2 if (kinds & E and c[1] <= E) or kinds <= E else 8
                if (c[0] + (-g, -g, g, g)).intersects(rr + (-g, -g, g, g)):
                    rr |= c[0]; kinds |= c[1]; cnt += c[2]; cl.remove(c); merged = True
        cl.append((rr, kinds, cnt))
    out = []
    for r, kinds, cnt in cl:
        if 'img' not in kinds and not kinds & {'eq', 'eq1'} and (r.width < 40 or r.height < 25): continue
        if kinds == {'eq'} and r.height < 16: continue   # 한 줄짜리 기호(Rm, b1 등)는 글자로 둔다(분수가 아니면)
        if r.height > H * (0.92 if 'img' in kinds else 0.8): continue   # 쪽 테두리는 버리되, 그림이 든 쪽 전체 표(피트 사다리 형식 등)는 살린다
        # 영역 안 글자 줄도 포함되도록 넓히고, 연혁 제목(➥)이나 현행 조문 제목이 들어 있으면 틀(테두리)이므로 버린다
        bad = False
        for y, x, font, size, txt, l in rows:
            lb = pymupdf.Rect(l['bbox']); cx, cy = (lb.x0 + lb.x1) / 2, (lb.y0 + lb.y1) / 2
            if r.contains(pymupdf.Point(cx, cy)):
                m = HEADRE.match(txt.strip())
                if '➥' in txt or (font.startswith(CFG['cur_font']) and size >= CFG['cur_min'] and m and lb.x0 < CFG['head_x'] and txt.strip()[m.end():].strip()): bad = True
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
def figtext(txts):
    """그림 영역의 검색용 글자: 색 표시 빼고, 수식 글꼴 코드는 되살릴 수 있는 것만 글자로(나머지는 버림)"""
    from restore_eq import restore
    return re.sub(r'\[수식\]\s*', '', ' '.join(restore(re.sub(r'[\x01-\x04]', '', x)) for x in txts)).strip()
def para_join(items):
    """현행 본문 줄 → 문단. 앞 줄이 오른쪽 끝까지 찼고 이 줄이 들여쓰기 없이 시작하면 앞 줄에 잇는다(앞 줄 끝에 공백이 있을 때만 띄움).
    그 밖(들여 쓴 줄, 짧은 제목 줄 다음)은 새 문단"""
    paras = []; glue = False; trail = False
    for it in items:
        if isinstance(it, list):   # 그림 영역
            name, w, h, txts = it
            paras.append('\x10%s|%d|%d\x0e%s\x11' % (name, w, h, figtext(txts))); glue = False; continue
        it, full = it[:2]   # full: 앞 줄이 오른쪽 끝까지 찬 줄(문단이 다음 줄로 이어짐)
        if not it.strip(): continue
        if paras and glue and not it[:1].isspace(): paras[-1] += (' ' if trail else '') + it.strip()
        else: paras.append(it.strip())
        trail = it[-1:].isspace(); glue = full
    return [re.sub(r' {2,}', ' ', x) if not x.startswith('\x10') else x for x in paras]
def main():
    d = pymupdf.open(SRC)
    hist = {}; cur = None; blk = None; prev = None; cur_annex = None
    BASE = []        # [{'num', 'rest', 'items': [줄 또는 그림]}]
    annex_title = None; annex_y = 0   # '부속서 Ⅰ' 바로 아래 가운데 제목 줄을 기다리는 중
    def close():
        nonlocal blk
        if blk is not None and cur:
            blk['text'] = join(blk.pop('lines')); hist.setdefault(cur, {'cur': None, 'blocks': []})['blocks'].append(blk)
        blk = None
    def head(st, x, font, size):
        """현행 조문 머리이면 (번호, 나머지)"""
        if not (font.startswith(CFG['cur_font']) and size >= CFG['cur_min'] and x < CFG['head_x']): return None
        m = HEADRE.match(st)
        if not m: return None
        num, rest = m.group(1), st[m.end():].strip()
        if not rest and not re.match('^' + RPAT + r'\.', num): REJ.append((pi + 1, st[:50])); return None
        if BAD.match(rest): return None
        rm = re.match('^(' + RPAT + r')\.', num)
        if rm and rm.group(1) != cur_annex: REJ.append((pi + 1, st[:50])); return None
        if re.fullmatch(r'\d{1,2}', num):
            if not re.match(r'^[가-힣]', rest): return None
            if prev is not None and (prev[0] >= 100 or int(num) != prev[0] + 1): return None
        try: k = key(num)
        except Exception: return None
        if k[0] < 100 and k[0] > 30: return None
        if not plausible(prev, k): REJ.append((pi + 1, 'ORDER ' + st[:50])); return None
        return num, rest
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
        FULL = pg.rect.width * 0.82
        def add_cur(txt, l):
            """현행 본문 줄 추가. 같은 높이에서 오른쪽에 이어지는 줄('F' | ': 멈춤 쇠 장치가 …', '… 및 그' | '작동수단')은 한 줄로"""
            its = BASE[-1]['items']; lb = l['bbox']
            if its and not isinstance(its[-1], list) and len(its[-1]) == 4 and abs(its[-1][2] - lb[1]) < 3 and lb[0] > its[-1][3] - 1:
                its[-1] = (its[-1][0].rstrip() + ' ' + txt.lstrip(), lb[2] >= FULL, lb[1], lb[2])
            else: its.append((txt, lb[2] >= FULL, lb[1], lb[2]))
        regs = regions(pg, rows)
        # 같은 높이의 오른쪽 '시행' 표시(Gulim 8pt)
        siheng_y = [r[0] for r in rows if r[2] == 'Gulim' and r[3] == 8 and r[4].strip().endswith('시행')]
        # 그림 영역 안에 가운데가 든 줄은 그 그림의 검색용 글자로(줄 윗변이 영역보다 위여도 — 분수식의 'F =' 등)
        members = {k: [] for k in range(len(regs))}; keep = []
        for row in rows:
            lb = row[5]['bbox']; c = pymupdf.Point((lb[0] + lb[2]) / 2, (lb[1] + lb[3]) / 2)
            k = next((k for k, r in enumerate(regs) if r.contains(c)), None)
            st_ = row[4].strip()
            if '➥' in row[4] or (row[2].startswith(CFG['mark_font']) and row[3] == 10 and st_.startswith('<')): k = None   # 연혁 제목·적용 표시 줄은 그림에 넣지 않는다
            (keep if k is None else members[k]).append(row)
        rows = keep + [(r.y0 - 0.5, r.x0, '__REG__', 0, str(k), r) for k, r in enumerate(regs)]
        # 연혁 블록 아래 점선(작은 선분 100개 이상이 한 줄로 300pt 넘게): 그 바로 다음이 그림이면 블록은 끝난 것(그림은 현행 본문)
        tiny = {}; bands = []
        for dr in pg.get_drawings():
            r = dr['rect']
            if r.width < 1.5 and r.height < 1.5: tiny.setdefault(round(r.y0), []).append(r)
            elif dr.get('fill') is not None and r.height < 16 and r.width > 100: bands.append(r)   # 연혁 제목 띠
        for yy, rs in tiny.items():
            if len(rs) >= 100 and max(r.x1 for r in rs) - min(r.x0 for r in rs) > 300 and not any(abs(yy - b.y1) < 6 for b in bands):
                # 제목 띠 바로 아래 점선은 블록 윗줄, 쪽 맨 위 점선은 앞 쪽에서 이어지는 블록의 윗줄(블록이 안 끝남)
                rows.append((yy, 0, '__END__' if yy > 135 else '__CONT__', 0, '', None))
        rows.sort(key=lambda r: (round(r[0]), r[1]))
        for ri, (y, x, font, size, txt, l) in enumerate(rows):
            if font == '__END__':
                if blk is not None: blk['endy'] = (pi, y)
                continue
            if font == '__CONT__':
                if blk is not None: blk.pop('endy', None)
                continue
            if font == '__REG__':
                if blk is not None and blk.get('endy') and (blk['endy'][0] < pi or blk['endy'][1] < l.y0):
                    # 그림 바로 다음 글이 연혁 본문 글자(9pt 이하)면 다음 쪽으로 이어진 연혁 블록의 옛 그림('<그림3>' 등)
                    nxt = next((r_ for r_ in rows[ri + 1:] if not r_[2].startswith('__') and r_[4].strip()), None)
                    if nxt is not None and nxt[3] <= 9 and not nxt[2].startswith(CFG['cur_font']): blk.pop('endy', None)
                    else: ENDFIG.append((pi + 1, round(l.y0), cur)); close()
                if blk is not None or BASE:
                    name = f'h{MODE}_p{pi + 1}_{txt}.webp'; w, h = crop(pg, l, name)
                    fig = [name, w, h, [line_text(m[5]) for m in sorted(members[int(txt)], key=lambda m: (round(m[0]), m[1]))]]
                    (blk['lines'] if blk is not None else BASE[-1]['items']).append(fig)
                continue
            st = txt.strip()
            if font == 'Gulim' and (size == 10 and re.fullmatch(r'\d+', st) or size == 8): continue   # 쪽번호, '시행' 표시
            if font.startswith(CFG['skip_fonts']) if CFG['skip_fonts'] else False: continue   # 머리글
            if font.startswith(CFG.get('num_fonts') or ('\0',)) and re.fullmatch(r'❙?\s*\d+\s*❙?', st): continue   # 쪽번호('54 ❙') — 같은 글꼴의 그림 제목은 둔다
            if '➥' in txt:
                close()
                hd = st.replace('➥', '').strip()
                blk = {'head': hd, 'lines': [], 'y': y, 'pi': pi, 'siheng': any(abs(sy - y) < 4 for sy in siheng_y)}
                continue
            if font == 'H2gtrE' and blk is not None and not blk['head']:
                blk['head'] = st; blk['siheng'] = blk['siheng'] or any(abs(sy - y) < 4 for sy in siheng_y); continue
            if font.startswith(CFG['mark_font']) and size == 10 and st.startswith('<'):
                if cur and re.search(r'적용|시행|삭제', st):
                    close()
                    ds = dates(st)
                    hist.setdefault(cur, {'cur': None, 'blocks': []})['cur'] = {'raw': st, 'd': ds[0] if ds else None, 'basis': '허가' if '건축허가' in st else '시행'}
                continue
            if font.startswith(CFG['cur_font']) and size >= CFG['cur_min']:
                ma = ANNEX.match(re.sub(r'\s+', ' ', st))
                if ma and x > 150:
                    k = key(ma.group(1))
                    if plausible(prev, k):
                        close(); cur = ma.group(1); cur_annex = cur; prev = k; DET.append(cur)
                        BASE.append({'num': cur, 'rest': '', 'items': []}); annex_title = []; annex_y = y
                    continue
                if annex_title is not None:
                    if x > 90 and abs((l['bbox'][0] + l['bbox'][2]) / 2 - pg.rect.width / 2) < 50 and not HEADRE.match(st) and y - annex_y < 30:
                        annex_title.append(st); annex_y = y; BASE[-1]['rest'] = ' '.join(annex_title); continue
                    BASE[-1]['rest'] = ' '.join(annex_title); annex_title = None
                hh = head(st, x, font, size)
                if hh:
                    close(); cur = hh[0]; prev = key(cur); DET.append(cur)
                    # 머리 줄 끝에 공백을 남기고 끊긴 제목('10.2 추락방지안전장치 및 그␣␣' / '작동수단')도 다음 줄로 잇는다
                    BASE.append({'num': cur, 'rest': hh[1], 'items': [(' ' + txt.lstrip()[len(cur):].lstrip('.'), l['bbox'][2] >= FULL or txt[-1:].isspace(), l['bbox'][1], l['bbox'][2])]})
                else:
                    if blk is not None: close()   # 현행 본문이 이어지면 블록 끝
                    if BASE: add_cur(txt, l)
                continue
            if blk is None and BASE and size >= 9 and font not in ('Gulim',):
                add_cur(txt, l); continue
            if blk is not None and size <= 10 and not font.startswith(CFG['cur_font']):
                blk['lines'].append(line_text(l)); blk.pop('endy', None)
    close()
    if annex_title: BASE[-1]['rest'] = ' '.join(annex_title)
    out = {}
    for n, h in hist.items():
        bl = []
        for b in h['blocks']:
            f, t, basis = classify(b['head'])
            bl.append({'head': re.sub(r'\s+', ' ', b['head']), 'from': f, 'to': t, 'basis': basis, 'siheng': b['siheng'], 'text': b['text']})
        out[n] = {'cur': h['cur'], 'blocks': bl}
    json.dump(out, open(CFG['out'], 'w', encoding='utf-8'), ensure_ascii=False)
    # ---- 현행 조문 목록(사이트 카드): 제목은 번호 뒤 짧은 머리말(40자 이하, 문장 아님), 경로는 상위 조문 제목
    from restore_eq import restore
    res = []; titles = {}
    for e in BASE:
        paras = para_join(e['items'])
        num = e['num']
        if re.fullmatch(RPAT, num):
            title = e['rest']; body = [p_ for p_ in paras if p_]
        else:
            first = paras[0] if paras else ''
            is_heading = first and len(first) <= 40 and not first.endswith(('.', '다')) and not re.search(r'[.다]\s', first)
            title, body = (first, paras[1:]) if is_heading else ('', paras)
        titles.setdefault(num, title)
        nd = lambda s: s.replace('ᆞ', 'ㆍ').replace('･', 'ㆍ')   # 연혁집의 가운뎃점(ᆞ, ･)을 보통 쓰는 ㆍ로(검색)
        text = nd(re.sub(r'(?<=[가-힣])\?(?=[가-힣])', '·', restore('\n'.join(body))))
        res.append({'num': num, 'title': nd(restore(title)), 'text': text})
    base = []
    for e in res:
        parts = e['num'].split('.'); chain = []
        for i in range(1, len(parts)):
            p_ = '.'.join(parts[:i])
            if titles.get(p_): chain.append(f'{p_} {titles[p_]}')
        if chain and re.match('^' + RPAT + ' ', chain[0]): chain[0] = '부속서 ' + chain[0]
        base.append({'src': CFG['prefix'], 'id': CFG['prefix'] + '-' + e['num'], 'num': e['num'], 'title': e['title'], 'path': ' › '.join(chain), 'text': e['text']})
    json.dump(base, open(CFG['baseout'], 'w', encoding='utf-8'), ensure_ascii=False)
    nb = sum(len(v['blocks']) for v in out.values())
    print('clauses', len(base), 'with text', sum(1 for e in base if e['text'].strip()), '| clauses with history', sum(1 for v in out.values() if v['blocks']), 'blocks', nb, 'cur markers', sum(1 for v in out.values() if v['cur']))
main()
print('rejected', len(REJ), REJ[:20]); print('figs after block end', len(ENDFIG), ENDFIG[:40])
