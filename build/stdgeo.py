"""표준화 PDF(슬라이드)의 각 줄 쪽·세로 위치를 insp.txt 줄 번호에 맞춘다 → std_geo.json {줄번호: [쪽, y]}
insp.txt 는 이 PDF 각 쪽 글(get_text)을 차례로 이은 것(공백 뺀 글자 수가 정확히 같음)이므로,
PDF 줄(dict)을 순서대로 이어 붙인 글자 위치로 insp.txt 줄과 1:1 대응시킨다."""
import pymupdf, re, json, bisect
nz = lambda s: re.sub(r'\s', '', s)
d = pymupdf.open('stdzip/std.pdf')
L = open('insp.txt', encoding='utf-8').read().split('\n')
N = ''; lstart = []
for l in L: lstart.append(len(N)); N += nz(l)
lstart.append(len(N))
offs = []; info = []; off = 0; bad = 0
for pi, p in enumerate(d):
    base = off
    for blk in p.get_text('dict')['blocks']:
        for l in blk.get('lines', []):
            t = nz(''.join(s['text'] for s in l['spans']))
            if not t: continue
            offs.append(off); info.append((pi, round(l['bbox'][1], 1), round(l['bbox'][0], 1), round(max(sp['size'] for sp in l['spans']), 1))); off += len(t)
    if off - base != len(nz(p.get_text())): bad += 1; off = base + len(nz(p.get_text()))
assert off == len(N), (off, len(N))
geo = {}
for i, l in enumerate(L):
    if not nz(l): continue
    k = bisect.bisect_right(offs, lstart[i]) - 1
    geo[i] = list(info[k])
json.dump(geo, open('std_geo.json', 'w'))
print('pages with dict/text mismatch', bad, '| lines', len(geo))
