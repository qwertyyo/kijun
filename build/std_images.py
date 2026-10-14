"""표준화 PDF의 그림을 잘라 해당 안건(std id)에 연결한다."""
import pymupdf, json, re, os, sys, hashlib

PDF = 'stdzip/std.pdf'
OUT = 'stdimg'
os.makedirs(OUT, exist_ok=True)

def norm(s):
    return re.sub(r'[\s‣▪▸•·ㆍ\-\[\]()（）]', '', s or '')

d = json.load(open('data.json'))
items = [x for x in d['std'] if x['title'] != '목차']
# 텍스트 파일(insp.txt)은 이 PDF에서 뽑은 것이므로, 공백을 뺀 문자열 위치로 페이지·안건을 맞춘다
def nz(s): return re.sub(r'\s', '', s or '')
N = nz(open('insp.txt', encoding='utf-8').read())
# 안건 시작 위치: 파싱 순서대로 제목을 순차 검색
item_off = []
pos = 0
for x in items:
    k = nz(x.get('_ot') or x['title'])[:18]   # 제목을 고쳐 쓴 안건은 원문 제목으로 위치를 찾는다
    if len(k) < 4: continue
    i = -1
    # 본문 머리는 '번호+제목'(점 없이), 목차는 '번호.제목' 이므로 번호 붙은 형태를 먼저 찾는다
    # '[기타안건] 실제 안건명'처럼 꼬리표를 붙여 만든 제목은 꼬리표 뺀 것도 후보로(원문엔 꼬리표가 없을 수 있음)
    k2 = nz(re.sub(r'^\[[^\]]*\]\s*', '', x.get('_ot') or x['title']))[:18]
    keys = [k] + ([k2] if k2 != k and len(k2) >= 4 else [])
    if x['num']:
        for kk in keys[:1]:   # 번호+제목 형태는 원래 제목으로만(꼬리표 뺀 제목을 번호에 붙이면 다른 회차 안건과 겹침)
            for pre in (x['num'], x['num'] + '‣', x['num'] + '▪'):
                j = N.find(pre + kk, pos)
                if j >= 0 and j - pos < 60000 and (i < 0 or j < i): i = j + len(pre)
    if i < 0:
        for kk in keys:
            j = N.find(kk, pos)
            if j >= 0 and j - pos < 60000 and (i < 0 or j < i): i = j
    if i < 0: continue
    item_off.append((i, x['id'])); pos = i + 1
print('items located', len(item_off), '/', len(items))
doc = pymupdf.open(PDF)
import statistics
# 페이지 줄 중 텍스트 파일 전체에서 딱 한 번 나오는 줄만 위치 기준으로 사용(머리글 반복·목차 혼동 방지)
cnt_cache = {}
def once(k):
    if k not in cnt_cache: cnt_cache[k] = N.count(k)
    return cnt_cache[k] == 1
raw = []
for pno in range(len(doc)):
    ls = []
    for b in doc[pno].get_text('dict')['blocks']:
        for l in b.get('lines', []):
            t = nz(''.join(s['text'] for s in l['spans']))
            if len(t) >= 10 and once(t[:40]): ls.append((l['bbox'][1], N.find(t[:40])))
    ls.sort(); raw.append(ls)
med = [int(statistics.median([o for _, o in ls])) if ls else None for ls in raw]
# 빈 페이지는 앞 페이지 값으로
last = 0
for i in range(len(med)):
    if med[i] is None: med[i] = last
    last = med[i]
page_lines = []
prev_end = 0
for i, ls in enumerate(raw):
    lo = med[i - 1] - 3000 if i else 0
    hi = (med[i + 1] if i + 1 < len(med) else 10**9) + 3000
    kept = [(y, o) for y, o in ls if lo <= o <= hi]
    page_lines.append((prev_end, kept))
    if kept: prev_end = max(prev_end, max(o for _, o in kept))
def text_off(pno, y):
    start, kept = page_lines[pno]
    best = start
    for ly, o in kept:
        if ly <= y: best = max(best, o)
    return best
def owner(pno, y):
    o = text_off(pno, y); best = None
    for i, iid in item_off:
        if i <= o: best = iid
        else: break
    return best

# 2) 그림 위치 → 잘라내기
res = {}
done = set()
n = 0
for pno in range(len(doc)):
    pg = doc[pno]
    W, H = pg.rect.width, pg.rect.height
    for info in pg.get_image_info(xrefs=True):
        x0, y0, x1, y1 = info['bbox']
        w, h = x1 - x0, y1 - y0
        if w > W * 0.9 and h > H * 0.9: continue        # 슬라이드 배경(로고 머리글)
        if w < 40 or h < 25: continue                   # 아이콘·장식
        if y1 < 60: continue                            # 상단 로고
        oid = owner(pno, y0)
        if not oid: continue
        clip = pymupdf.Rect(max(0, x0 - 2), max(0, y0 - 2), min(W, x1 + 2), min(H, y1 + 2))
        # 원본 해상도에 맞춰 렌더(작게 배치된 고해상도 스캔도 원본 픽셀을 살림)
        native_dpi = info['width'] / (w / 72) if w else 150
        dpi = int(min(600, max(150, native_dpi * 1.05)))
        pix = pg.get_pixmap(clip=clip, dpi=dpi)
        png = pix.tobytes('png')
        hsh = hashlib.md5(png).hexdigest()[:10]
        if (oid, hsh) in done: continue
        done.add((oid, hsh))
        fn = f'{oid}_{hsh}.webp'
        from PIL import Image
        import io
        im = Image.open(io.BytesIO(png)).convert('RGB')
        if im.width > 1600: im = im.resize((1600, int(im.height * 1600 / im.width)), Image.LANCZOS)
        im.save(os.path.join(OUT, fn), 'WEBP', quality=82, method=6)
        hand = '배포자료' in pg.get_text()[:300]
        res.setdefault(oid, []).append({'f': fn, 'p': pno + 1, 'w': im.width, 'h': im.height, 'hand': hand, 'lo': native_dpi < 100})
        n += 1
json.dump(res, open('stdimg.json', 'w', encoding='utf-8'), ensure_ascii=False)
tot = sum(os.path.getsize(os.path.join(OUT, f)) for f in os.listdir(OUT))
print('images', n, 'items with images', len(res), 'size MB', round(tot / 1e6, 2))
