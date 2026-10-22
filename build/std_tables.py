"""표준화 PDF 슬라이드 안의 표(선으로 그린 표)를 찾아 std_tables.json 에 쪽별 영역으로 적는다(없을 때만 build.py 가 실행, 약 30초).
parse.py 가 이 영역의 본문 줄을 원문 표 그림(stdimg/stb_*.webp)으로 바꾼다 — 글자만 이어 붙이면 칸·행이 뒤섞여 읽기 어려워서.
슬라이드 틀(쪽 테두리 표)과 제목 띠는 빼고, 슬라이드 안쪽의 표만."""
import pymupdf, json, os, sys
os.chdir(os.path.dirname(os.path.abspath(__file__)))
d = pymupdf.open('stdzip/std.pdf')
# 표로 잡히지만 표가 아닌 것(사진 묶음·글 문단·도장)은 뺀다: 칸 15개 이상(글자 깨진 영역), 349쪽(사진), 2칸짜리는 아래 쪽만(나머지는 글 문단 틀)
TWO_COL_OK = {169, 174, 223, 415, 458}
NOT_TABLE = {5, 349}   # 5쪽 목차 목록, 349쪽 사진
# 표로 안 잡히지만 표·흐름도인 것(원문 대조로 넣음): 277쪽 흐름도, 223쪽 통보 절차 흐름도, 419·420쪽 벨트 판정 표 V.3(쪽 끝까지 그은 선),
# 643~647쪽 배포자료 '제어반 인증만료일' 목록(쪽 그림 + 숨은 글자층 — 글자만으로는 칸이 뒤섞임)
EXTRA = {277: [[66, 189, 572, 385]], 223: [[27, 348, 428, 525]], 419: [[0, 197, 588, 819]], 420: [[0, 197, 588, 706]],
         **{p: [[12, 83, 540, 830, 12, 83, 590, 830]] for p in range(643, 648)}}
# 뒤 4개 값이 있으면 본문 줄을 고르는 영역(자르는 영역과 다를 때: 643~647쪽 글자층은 그림 오른쪽 밖 x≈552 에 1pt 글자로 숨어 있음)
out = {}
for i in range(len(d)):
    try: ts = d[i].find_tables().tables
    except Exception: continue
    keep = []
    for t in ts:
        x0, y0, x1, y1 = t.bbox
        if x0 <= 12 and x1 >= 575: continue   # 슬라이드 틀(쪽 테두리 표)
        if y0 < 55 or x0 < 13 or x1 - x0 < 150 or y1 - y0 < 40 or t.row_count < 2 or t.col_count < 2: continue
        if t.col_count >= 15 or i + 1 in NOT_TABLE: continue
        if t.col_count == 2 and i + 1 not in TWO_COL_OK: continue
        keep.append([round(x0, 1), round(y0, 1), round(x1, 1), round(y1, 1)])
    keep += EXTRA.get(i + 1, [])
    if keep: out[str(i + 1)] = keep
json.dump(out, open('std_tables.json', 'w'), separators=(',', ':'))
print('std tables', sum(len(v) for v in out.values()), 'pages', len(out))
