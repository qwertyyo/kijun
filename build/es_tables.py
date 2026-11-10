"""참조 표를 연혁집의 현행 표 이미지에 연결한다. 원문·연혁은 수정하지 않는다."""
from pathlib import Path
import re

import pymupdf
from PIL import Image


def build_tables(entries, base=None):
    base = Path(base or Path(__file__).parent)
    entry = next(e for e in entries if e['num'] == 'Ⅱ.2')
    images = {m[1]: m for m in re.finditer(
        r'\x10([^|]+)\|(\d+)\|(\d+)\x0e(.*?)\x11', entry['text'], re.S)}
    # 141쪽의 _0은 2013년 적용 연혁이다. 현행 표는 _1까지 세 영역이다.
    parts = [
        ('hes_p139_0.webp', 139, '수동 소자·반도체', ('1.1', '2.6')),
        ('hes_p140_0.webp', 140, '기타 · 3.1 커넥터 단자 플러그 · 3.6 인쇄회로기판(PCB)', ('3.1', '3.6')),
        ('hes_p141_1.webp', 141, 'PCB 부품의 조립품', ('4 PCB', '(10)')),
    ]
    with pymupdf.open(base / 'hist_es/hist.pdf') as pdf:
        caption = re.sub(r'\s+', '', pdf[138].get_text())
        if '[표Ⅱ.1고장배제]' not in caption:
            raise ValueError('표 Ⅱ.1 원문 위치를 다시 확인해야 합니다.')
    pages = []
    for filename, page, title, required in parts:
        image = images.get(filename)
        if image is None or any(word not in image[4] for word in required):
            raise ValueError(f'표 Ⅱ.1의 현행 표 영역을 확인해야 합니다: {filename}')
        width, height = int(image[2]), int(image[3])
        with Image.open(base / 'fig' / filename) as cropped:
            if cropped.size != (width, height):
                raise ValueError(f'표 이미지 크기가 다릅니다: {filename}')
        pages.append(dict(file=filename, width=width, height=height,
                          page=page, title=title))
    return {'Ⅱ.1': dict(id='Ⅱ.1', title='고장 배제', source='승강기 안전기준 연혁집 v2.0',
                         pages=pages, row_pages={'3.1': 1, '3.6': 1})}
