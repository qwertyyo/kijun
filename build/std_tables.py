"""표준화 PDF 슬라이드 안의 표(선으로 그린 표)를 찾아 std_tables.json 에 쪽별 영역으로 적는다(없을 때만 build.py 가 실행, 약 30초).
parse.py 가 이 영역의 본문 줄을 원문 표 그림(stdimg/stb_*.webp)으로 바꾼다 — 글자만 이어 붙이면 칸·행이 뒤섞여 읽기 어려워서.
슬라이드 틀(왼쪽 '검사기준/표준화' 칸, x<40)과 제목 띠는 빼고, 슬라이드 안쪽의 표만."""
import pymupdf, json, os, sys
os.chdir(os.path.dirname(os.path.abspath(__file__)))
d = pymupdf.open('stdzip/std.pdf')
# 표로 잡히지만 표가 아닌 것(사진 묶음·글 문단·도장)은 뺀다: 칸 15개 이상(글자 깨진 영역), 349쪽(사진), 2칸짜리는 아래 쪽만(나머지는 글 문단 틀)
TWO_COL_OK = {174, 415, 458}
NOT_TABLE = {349}
out = {}
for i in range(len(d)):
    try: ts = d[i].find_tables().tables
    except Exception: continue
    keep = []
    for t in ts:
        x0, y0, x1, y1 = t.bbox
        if y0 < 55 or x0 < 40 or x1 - x0 < 150 or y1 - y0 < 40 or t.row_count < 2 or t.col_count < 2: continue
        if t.col_count >= 15 or i + 1 in NOT_TABLE: continue
        if t.col_count == 2 and i + 1 not in TWO_COL_OK: continue
        keep.append([round(x0, 1), round(y0, 1), round(x1, 1), round(y1, 1)])
    if keep: out[str(i + 1)] = keep
json.dump(out, open('std_tables.json', 'w'), separators=(',', ':'))
print('std tables', sum(len(v) for v in out.values()), 'pages', len(out))
