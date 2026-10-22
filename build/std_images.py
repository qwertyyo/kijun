"""표준화 PDF의 그림을 잘라 해당 안건(std id)에 연결한다."""
import pymupdf, json, re, os, sys, hashlib

PDF = 'stdzip/std.pdf'
OUT = 'stdimg'
os.makedirs(OUT, exist_ok=True)

def norm(s):
    return re.sub(r'[\s‣▪▸•·ㆍ\-\[\]()（）]', '', s or '')

# 그림 주인: 본문과 같은 기준(쪽 배치) — 같은 쪽에서 그림 윗변 바로 위에 있는 본문 줄의 안건.
# 그 쪽에서 그림 위에 글이 없으면: 그림 아래 첫 글이 안건 머리면 그 안건, 아니면(그림만 있는 쪽 등) 앞쪽의 마지막 본문 줄의 안건.
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
FIRST = {}
for l, iid in OWN.items(): FIRST[iid] = min(FIRST.get(iid, l), l)
# 쪽 배치로 못 정하는 것(원문 대조로 확인): (쪽 번호, 그림 윗변 y) → 안건 id
# 266쪽 아래 표 3개 = 19년 4차 #8 '<붙임1 참조>'의 붙임1(안전부품 경과조치 적용방법·접수증) — 같은 쪽 #15 아래에 실려 있음
OVERRIDE = {(266, 559): 'std-425'}
def owner(pno, y):
    if (pno + 1, round(y)) in OVERRIDE: return OVERRIDE[(pno + 1, round(y))]
    above = [x for x in bypg.get(pno, []) if 50 <= x[0] <= y + 4]   # 맨 위 제목 띠 줄은 빼고
    if above: return above[-1][2]
    # 그림이 쪽 맨 위에 있고 그 아래 첫 글이 안건 머리면 그 안건 그림(38쪽 난간대 사진, 329쪽 그림1·2)
    below = [x for x in bypg.get(pno, []) if x[0] > y + 4]
    # (같은 높이 줄 여럿 — 왼쪽 번호 칸·오른쪽 칸 — 중 하나가 머리면 됨)
    for x in [x for x in below if x[0] <= below[0][0] + 4]:
        if FIRST.get(x[2]) == x[1]: return x[2]
    j = bisect.bisect_left(skeys, (pno, -1)) - 1
    return seq[j][3] if j >= 0 else None
doc = pymupdf.open(PDF)
TBL = {int(k): v for k, v in json.load(open('std_tables.json')).items()} if os.path.exists('std_tables.json') else {}

# 2) 그림 위치 → 잘라내기
res = {}
done = set()
n = 0
for pno in range(len(doc)):
    pg = doc[pno]
    W, H = pg.rect.width, pg.rect.height
    infos = pg.get_image_info(xrefs=True)
    def _ok(b): w, h = b[2] - b[0], b[3] - b[1]; return not (w > W * 0.9 and h > H * 0.9) and w >= 40 and h >= 25 and b[3] >= 60
    rects = [pymupdf.Rect(i['bbox']) & pg.rect if _ok(i['bbox']) else pymupdf.Rect() for i in infos]
    for k_, info in enumerate(infos):
        x0, y0, x1, y1 = info['bbox']
        # 다른 그림 영역 안에 거의 들어가는 그림은 잘라 보면 같은 장면이 두 번 나온다(39·118·380쪽) — 큰 쪽만
        A = rects[k_]
        if any(j != k_ and not (A & B).is_empty and (A & B).get_area() > 0.8 * A.get_area() and (A.get_area(), k_) < (B.get_area(), j) for j, B in enumerate(rects)): continue
        w, h = x1 - x0, y1 - y0
        if w > W * 0.9 and h > H * 0.9: continue        # 슬라이드 배경(로고 머리글)
        if w < 40 or h < 25: continue                   # 아이콘·장식
        if y1 < 60: continue                            # 상단 로고
        oid = owner(pno, y0)
        if not oid: continue
        if any(t[0] - 3 <= (x0 + x1) / 2 <= t[2] + 3 and t[1] - 3 <= (y0 + y1) / 2 <= t[3] + 3 for t in TBL.get(pno + 1, [])): continue   # 원문 표 그림(stb_) 안의 사진은 표째로 보인다
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
# 주인이 바뀌어 더는 안 쓰는 옛 그림 파일 지우기
used = {m['f'] for v in res.values() for m in v}
for f in os.listdir(OUT):
    if f.endswith('.webp') and f not in used and not f.startswith('stb_'): os.remove(os.path.join(OUT, f))   # stb_ = parse.py 의 표 그림
tot = sum(os.path.getsize(os.path.join(OUT, f)) for f in os.listdir(OUT))
print('images', n, 'items with images', len(res), 'size MB', round(tot / 1e6, 2))
