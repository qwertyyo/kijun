"""원문을 눈으로 대조한 수식·그림 범위(쪽 번호는 PDF의 1부터 시작).

분수/합 기호의 글꼴 bbox로 조각을 정렬하면 식의 우변이 먼저 나오는 경우가
있다. 검토한 식은 등호·부등호·지수·여러 줄의 후속 항까지 한 영역으로 둔다.
"""
import pymupdf


EL = {
    190: [(82, 153, 251, 187), (95, 257, 257, 289)],
    332: [(59, 346, 174, 379), (59, 565, 168, 597), (59, 745, 385, 808)],
    333: [(59, 267, 257, 304), (59, 400, 506, 480), (59, 769, 400, 806),
          (59, 58, 340, 79), (59, 124, 432, 207)],
    334: [(59, 58, 435, 96), (59, 631, 241, 708)],
    337: [(95, 571, 500, 611), (95, 633, 500, 683)],
    338: [(105, 637, 493, 677), (205, 698, 407, 758)],
    339: [(75, 117, 485, 156), (75, 215, 516, 252)],
    344: [(101, 674, 534, 752), (105, 754, 489, 795)],
    345: [(177, 59, 418, 114), (89, 134, 536, 223), (86, 224, 524, 318)],
    348: [(110, 59, 433, 128), (88, 190, 222, 247)],
    350: [(59, 223, 145, 261)],
    352: [(68, 65, 508, 309), (77, 337, 512, 590)],
    356: [(61, 523, 536, 694)],
}

# 이미지 밖에 덧쓴 변경 안내도 중간에서 끊기지 않게 함께 자른다.
# (PDF 쪽, 원래 이미지 왼쪽/윗변의 반올림 값) → 검토한 전체 범위
STD = {
    (21, 76, 430): (74, 428, 420, 619),
    (238, 74, 485): (72, 483, 435, 680),
    (349, 76, 528): (74, 518, 420, 745),
    # 주석이 사진 왼쪽의 적용 방법 위에 겹친 쪽: 문장 조각이 걸리지 않도록
    # 해당 표준화 설명 상자 전체를 포함한다(왼쪽 세로 구분 칸은 제외).
    (682, 305, 638): (65, 449, 574, 805),
}


def apply_reviewed_regions(mode, page, automatic):
    pn = page.number + 1
    revised = mode == 'el' and pn in EL or mode == 'es' and pn == 134
    if mode == 'el':
        manual = [pymupdf.Rect(r) for r in EL.get(pn, [])]
        automatic = [r for r in automatic if not any(r.intersects(m) for m in manual)]
        automatic += manual
    if mode == 'es' and pn == 134:
        # 기술 도해가 아닌 왼쪽 위 회색 머리글 화살표.
        automatic = [r for r in automatic if not (r.x0 < 2 and r.y0 < 2 and r.y1 < 80)]
    return automatic, revised


def reviewed_std_clip(page_number, image_bbox, default):
    x0, y0, _, _ = image_bbox
    return pymupdf.Rect(STD.get((page_number, round(x0), round(y0)), default))


def clean_formula_padding(page, region, clip):
    """검토한 세 쪽에서 바로 앞 문장 밑부분이 1pt 여백에 재유입되는 것을 막는다."""
    if page.number + 1 not in (19, 183, 347):
        return clip
    for block in page.get_text('dict')['blocks']:
        for line in block.get('lines', []):
            b = pymupdf.Rect(line['bbox'])
            if b.x1 <= region.x0 or b.x0 >= region.x1:
                continue
            center = (b.y0 + b.y1) / 2
            if center < region.y0 and clip.y0 < b.y1 <= region.y0 + .1:
                clip.y0 = max(clip.y0, b.y1 + .3)
            if center > region.y1 and region.y1 - .1 <= b.y0 < clip.y1:
                clip.y1 = min(clip.y1, b.y0 - .3)
    return clip
