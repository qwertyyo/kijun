"""별표24 원문 그림을 잘라 본문 참조·치수표의 조문 번호로 연결한다.

현행/연혁 본문은 hist_parse.py 결과를 유지한다. 이 PDF는 그림 보완용이며
과거 연혁의 그림 번호를 현행 번호로 자동 연결하지 않는다.
"""
import hashlib
import io
import json
from pathlib import Path
import re

from PIL import Image
import pymupdf


INLINE_FIG = re.compile(r'\x10[^\x11]*\x11')
CAPTION = re.compile(r'\[\s*그림[^\]]*\]', re.S)
NUMBER = r'(?:[ⅠⅤIV]+\s*\.\s*)?\d+'
REF = re.compile(r'그\s*림\s*(' + NUMBER + r')(?![\d.])((?:\s*(?:,|및|~|∼|부터|내지)\s*(?:그\s*림\s*)?' + NUMBER + r'(?![\d.]))*)')


def normalized(number):
    return re.sub(r'\s+', '', number).replace('V.', 'Ⅴ.').replace('I.', 'Ⅰ.')


def figure_references(text):
    """일반 그림 5와 부속서 그림 Ⅰ.1을 구분하고 '그림 5 및 7'도 읽는다."""
    plain = CAPTION.sub('', INLINE_FIG.sub('', text))
    result = []
    for match in REF.finditer(plain):
        ids = [normalized(n) for n in re.findall(NUMBER, match.group())]
        if re.search(r'~|∼|부터|내지', match.group()) and len(ids) == 2 and all(n.isdigit() for n in ids):
            first, last = map(int, ids)
            if first <= last <= 14:
                ids = [str(n) for n in range(first, last + 1)]
        for number in ids:
            if number not in result:
                result.append(number)
    return result


def build_figures(entries, base_dir='.'):
    base = Path(base_dir)
    config = json.loads((base / 'es_figures_map.json').read_text(encoding='utf-8'))
    source = base / config['source']
    if hashlib.sha256(source.read_bytes()).hexdigest() != config['sha256']:
        raise ValueError('별표24 그림 원본이 변경됨: 자르기 영역과 조문 연결을 재검토하세요.')
    output = base / 'fig'
    output.mkdir(exist_ok=True)
    by_num = {e['num']: e for e in entries}
    catalog = {}
    table_refs = {}
    with pymupdf.open(source) as doc:
        for spec in config['figures']:
            key = spec['id']
            images, texts = [], []
            for page, x0, y0, x1, y1 in spec['clips']:
                pg = doc[page - 1]
                rect = pymupdf.Rect(x0, y0, x1, y1)
                if not pg.rect.contains(rect):
                    raise ValueError(f'그림 {key}: 원문 밖 자르기 영역')
                texts.append(pg.get_text(clip=rect))
                pix = pg.get_pixmap(clip=rect, dpi=200)
                images.append(Image.open(io.BytesIO(pix.tobytes('png'))).convert('RGB'))
            # 그림 5는 도해와 치수표가 두 쪽에 나뉘어 있어 한 이미지로 보인다.
            width = max(im.width for im in images)
            height = sum(im.height for im in images) + 16 * (len(images) - 1)
            image = Image.new('RGB', (width, height), 'white')
            y = 0
            for im in images:
                image.paste(im, ((width - im.width) // 2, y))
                y += im.height + 16
            filename = 'es_figure_' + key.replace('.', '_') + '.webp'
            image.save(output / filename, 'WEBP', quality=90, method=6)
            text = '\n'.join(texts)
            # 잘린 제목/다른 그림의 혼입을 빌드 단계에서 발견한다.
            captions = re.findall(r'\[\s*그림\s*(' + NUMBER + r')', text)
            if [normalized(c) for c in captions] != [key]:
                raise ValueError(f'그림 {key}: 원문 제목 확인 실패 {captions}')
            refs = set()
            for number in re.findall(r'(?:[ⅠⅤIV]+\s*\.\s*)?\d+(?:\.\d+)+', text):
                number = normalized(number)
                if number in by_num:
                    refs.add(number)
            table_refs[key] = refs
            catalog[key] = dict(id=key, title=spec['title'], file=filename, width=width,
                                height=height, pages=list(dict.fromkeys(c[0] for c in spec['clips'])),
                                source=config['source_title'], edition=config['edition'], owner='b24-' + spec['owner'])
            if spec['owner'] not in by_num:
                raise ValueError(f'그림 {key}: 소속 조문이 없음: {spec["owner"]}')
    for e in entries:
        e.pop('figure_refs', None)
        explicit = figure_references(e['text'])
        # 재검토한 쪽의 파일명에는 내용 해시가 붙는다. 연결 소속은 원래
        # 쪽/그림 번호로 비교해 캐시 갱신 뒤에도 현행 그림 링크를 유지한다.
        inline = {re.sub(r'_[0-9a-f]{10}(?=\.webp$)', '', name)
                  for name in re.findall(r'\x10([^|]+)\|', e['text'])}
        linked = []
        for spec in config['figures']:
            key = spec['id']
            reasons = []
            if inline.intersection(spec['inline_files']):
                reasons.append('본문 수록 그림')  # 접힌 카드에서도 도해·기호설명·치수표를 함께 확대할 수 있다.
            if key in explicit:
                reasons.append('본문 참조')
            if e['num'] in table_refs[key]:
                reasons.append('그림의 치수·기호표에 표시된 조문')
            if reasons:
                linked.append(dict(id=key, reason=' · '.join(reasons)))
        if linked:
            e['figure_refs'] = linked
    print('es figures', len(catalog), '| linked clauses', sum(bool(e.get('figure_refs')) for e in entries))
    return catalog
