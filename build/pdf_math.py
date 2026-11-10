"""HWP 수식 글꼴의 가짜 괄호 영역과 기호/설명 줄의 세로 위치 차이를 정리한다."""
import re

from restore_eq import M, restore


def prepare_math_rows(rows):
    result, discarded = [], []
    for row in rows:
        y, x, font, size, text, line = row
        box = line['bbox']
        # 늘어난 괄호의 연결 글리프는 PDF 추출 좌표가 실제 도형과 멀리 떨어져 있다.
        # 이를 독립된 수식으로 자르면 빈 세로 띠 또는 다음 그림의 글자가 잘린다.
        if (font.startswith('HyhwpEQ') and text.strip()
                and set(text.strip()) <= {'\ue07d', '\ue080'}
                and box[2] - box[0] < 10 and box[3] - box[1] > 25):
            discarded.append(row)
            continue
        result.append(row)
    aligned = []
    for row in result:
        y, x, font, size, text, line = row
        label = restore(text).strip()
        if (font.startswith('HyhwpEQ') and all(ord(c) in M for c in text if '\ue000' <= c <= '\uf8ff')
                and re.fullmatch(r'[A-Za-zα-ω][A-Za-zα-ω0-9]{0,7}', label)):
            right = [r for r in result if r[1] > line['bbox'][2] + 6
                     and abs(r[0] - y) < 2.5 and re.match(r'^\s*=\s*\S', r[4])]
            if right:
                neighbor = min(right, key=lambda r: (abs(r[0] - y), r[1]))
                # 실제 bbox는 유지하고 읽기 순서만 같은 줄로 맞춘다.
                row = (neighbor[0], *row[1:])
        aligned.append(row)
    return aligned, discarded
