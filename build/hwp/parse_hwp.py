"""HWP 원본 → 조문 단위 JSON (수식은 한 줄 텍스트로 변환해 본문에 삽입)"""
import re, json, sys
sys.path.insert(0, '.')
import hwpeq, eq2text, hwplines

ROMAN = 'ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩⅪⅫ'
RV = {c: i + 1 for i, c in enumerate(ROMAN)}
RV['XⅢ'] = 13; RV['XⅣ'] = 14; RV['XIII'] = 13; RV['XIV'] = 14
RPAT = r'(?:XⅢ|XⅣ|XIII|XIV|[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩⅪⅫ])'

def hwp_lines(path):
    eqs, paras = hwpeq.extract(path)
    lines = []
    n_eq = 0
    for p in paras:
        ch = p['chars'][:]
        ei = 0
        for pos, cid in p['ctrls']:
            if cid == 'eqed' and ei < len(p['eq']):
                ch[pos] = ' ' + eq2text.convert(p['eq'][ei]) + ' '; ei += 1; n_eq += 1
            else:
                ch[pos] = ''
        t = ''.join(ch).replace('\x00', '')
        for l in t.split('\n'):
            l = re.sub(r'[ \t]+', ' ', l).rstrip()
            l = re.sub(r'\( ', '(', l); l = re.sub(r' \)', ')', l)
            lines.append(l)
    return lines, n_eq, len(eqs)

def key(num):
    m = re.match(r'^' + '(' + RPAT + ')' + r'(?:\.(.*))?$', num)
    if m:
        rest = tuple(int(x) for x in m.group(2).split('.')) if m.group(2) else ()
        return (100 + RV[m.group(1)],) + rest
    return tuple(int(x) for x in num.split('.'))

def plausible(prev, cand):
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

HEAD = re.compile(r'^\s{0,3}((?:' + RPAT + r'(?:\.\d+)+)|(?:\d+(?:\.\d+)+)|(?:\d{1,2}))\.?(?:\s+(\S.*))?$')
ANNEX = re.compile(r'^\s*부속서\s+(' + RPAT + r')\s*$')
BAD = re.compile(r'^(참조|및|또는|부터|까지|이상|이하|초과|미만|㎜|mm|m\b|㎝|N\b|kg|㎏|%|V\b(?!-)|A\b|lx|㏓|°|㎧|㎨|㎐|Hz|㎫|㎪|㎡|㎥|㎠|㎟|×|=|≤|≥)')

def parse(lines, prefix):
    lines = [re.sub(r'^(\d+(?:\.\d+)+)(?=「)', r'\1 ', l) for l in lines]   # '7.5.2.1「건축법」…' 번호 뒤 공백 누락
    marks = []  # (line index, num, rest)
    prev = None; cur_annex = None
    for i, l in enumerate(lines):
        m = ANNEX.match(l)
        if m:
            k = key(m.group(1))
            if prev is None or plausible(prev, k):
                cur_annex = m.group(1); marks.append((i, m.group(1), '')); prev = k
            continue
        m = HEAD.match(l)
        if not m: continue
        num, rest = m.group(1), (m.group(2) or '')
        if not rest and not re.match('^' + RPAT + r'\.', num): continue   # 번호만 있는 줄은 부속서 조문만 허용(본문은 표·그림 속 번호)
        if BAD.match(rest): continue
        rm = re.match('^(' + RPAT + r')\.', num)
        if rm and rm.group(1) != cur_annex: continue
        if re.fullmatch(r'\d{1,2}', num):
            if not re.match(r'^[가-힣]', rest): continue
            if prev is not None and (prev[0] >= 100 or int(num) != prev[0] + 1): continue
        try: k = key(num)
        except Exception: continue
        if k[0] < 100 and k[0] > 30: continue
        if not plausible(prev, k): continue
        marks.append((i, num, rest)); prev = k
    out = []
    titles = {}
    for j, (i, num, rest) in enumerate(marks):
        end = marks[j + 1][0] if j + 1 < len(marks) else len(lines)
        body = [l.strip() for l in lines[i + 1:end] if l.strip()]
        rest = rest.strip()
        is_heading = rest and len(rest) <= 40 and not rest.endswith(('.', '다')) and not re.search(r'[.다]\s', rest)
        if num in RV or re.fullmatch(RPAT, num):
            title = body[0] if body and len(body[0]) <= 50 else ''
            body = body[1:] if title else body
        elif is_heading:
            title = rest
        else:
            title = ''; body = [rest] + body
        titles.setdefault(num, title)
        out.append({'num': num, 'title': title, 'body': body})
    res = []
    for e in out:
        num = e['num']
        parts = num.split('.')
        chain = []
        for i in range(1, len(parts)):
            p = '.'.join(parts[:i])
            if titles.get(p): chain.append(f'{p} {titles[p]}')
        if chain and re.match('^' + RPAT + ' ', chain[0]):
            chain[0] = '부속서 ' + chain[0]
        text = '\n'.join(e['body'])
        res.append({'src': prefix, 'id': prefix + '-' + num, 'num': num, 'title': e['title'], 'path': ' › '.join(chain), 'text': text})
    return res

if __name__ == '__main__':
    src, prefix, outp = sys.argv[1], sys.argv[2], sys.argv[3]
    # 본문 그림(BinData) → ../fig/<접두>_NN.webp, 위치는 hwplines 가 그림 개체 자리에 표식으로 넣는다
    import olefile, zlib, io, os
    from PIL import Image
    tag = {'b22': 'el', 'b24': 'es'}[prefix]
    os.makedirs('../fig', exist_ok=True)
    ole = olefile.OleFileIO(src)
    for e in ole.listdir():
        if e[0] != 'BinData': continue
        bid = int(e[1].split('.')[0][3:], 16); ext = e[1].rsplit('.', 1)[-1].lower()
        raw = ole.openstream('/'.join(e)).read()
        try: raw = zlib.decompress(raw, -15)
        except Exception: pass
        im = Image.open(io.BytesIO(raw)).convert('RGB')
        fn = f'{tag}_{bid:02d}.webp'
        if ext == 'bmp': im.save('../fig/' + fn, 'WEBP', lossless=True, method=6)
        else: im.save('../fig/' + fn, 'WEBP', quality=88, method=6)
        hwplines.PICS[bid] = (fn, im.width, im.height)
    lines, n_eq = hwplines.extract_lines(src); tot = n_eq
    open(outp.replace('.json', '.txt'), 'w', encoding='utf-8').write('\n'.join(lines))
    r = parse(lines, prefix)
    json.dump(r, open(outp, 'w', encoding='utf-8'), ensure_ascii=False)
    print(src, 'equations inlined', n_eq, '/', tot, 'clauses', len(r), 'with text', sum(1 for e in r if e['text'].strip()))
