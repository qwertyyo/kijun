"""표준화 PDF의 그림을 잘라 해당 안건(std id)에 연결한다."""
import pymupdf, json, re, os, sys, hashlib

PDF = 'stdzip/std.pdf'
OUT = 'stdimg'
os.makedirs(OUT, exist_ok=True)

def norm(s):
    return re.sub(r'[\s‣▪▸•·ㆍ\-\[\]()（）]', '', s or '')

# 그림 주인: 본문과 같은 기준(쪽 배치) — 같은 쪽에서 그림 윗변 바로 위에 있는 본문 줄의 안건.
# 그 쪽에서 그림 위에 글이 없으면(그림만 있는 쪽 등) 앞쪽의 마지막 본문 줄의 안건.
# 줄 위치는 std_geo.json(줄번호→[쪽, y, x, 글자크기]), 안건별 줄번호는 parse.py 가 쓴 std_li.json
import bisect
GEO = {int(k): v for k, v in json.load(open('std_geo.json')).items()}
OWN = {}
for iid, lis in json.load(open('std_li.json')).items():
    for l in lis: OWN[l] = iid
bypg = {}
for l, iid in OWN.items():
    if l in GEO: bypg.setdefault(GEO[l][0], []).append((GEO[l][1], l, iid))
for v in bypg.values(): v.sort()
seq = sorted((GEO[l][0], GEO[l][1], l, iid) for l, iid in OWN.items() if l in GEO)
skeys = [(a, b) for a, b, _, _ in seq]
def owner(pno, y):
    above = [x for x in bypg.get(pno, []) if x[0] <= y + 4]
    if above: return above[-1][2]
    j = bisect.bisect_left(skeys, (pno, -1)) - 1
    return seq[j][3] if j >= 0 else None
doc = pymupdf.open(PDF)

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
