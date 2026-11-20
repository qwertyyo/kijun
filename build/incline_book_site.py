"""Load the site export of the completed incline history book."""
import json
from pathlib import Path
import re
from shutil import copyfile


BUILD = Path(__file__).resolve().parent
FIGURE = re.compile(r'\x10([^|]+)\|(\d+)\|(\d+)')
DATE_HEADING = re.compile(r'^(\d{4})년 (\d{1,2})월 (\d{1,2})일')


def apply_book_history(data):
    book = json.loads((BUILD / 'incline_book_history.json').read_text(encoding='utf-8'))
    entries = {row['id']: row for row in data['b23']}
    if not set(book['cards']) <= entries.keys():
        raise ValueError('경사형 연혁집에 연결할 사이트 조문이 없습니다.')
    data['incline_book'] = book['cards']
    for number, history in data['hist_incline'].items():
        blocks = history['blocks']
        labels = book['cards']['b23-' + number]['legacy']
        if set(labels) != {str(i) for i in range(len(blocks))}:
            raise ValueError(f'경사형 연혁집 날짜 연결 불일치: {number}')
        for index, block in enumerate(blocks):
            head = labels[str(index)]
            if head != block['head']:
                block.setdefault('source_head', block['head'])
            if block.pop('date_unknown', False):
                match = DATE_HEADING.match(head)
                if not match or not (head.endswith('시행 기준 준용') or head.endswith('시행 전 기준')):
                    raise ValueError(f'경사형 특례의 준용 기준일 누락: {number}')
                year, month, day = map(int, match.groups())
                block['sortdate'] = f'{year:04d}.{month:02d}.{day:02d}'
                block['context'] = block['head'].partition(' · ')[2]
                block['when_label'] = head
                block['basis'] = '준용' if head.endswith('준용') else '시행 전 기준'
                block['reference_only'] = True
                block.pop('date_note', None)
            block['head'] = head
    assets = book['assets']
    for asset in assets.values():
        for page in asset['pages']:
            file = page['file']
            copyfile(BUILD.parent / 'fig' / file, BUILD / 'fig' / file)
    for card in data['incline_book'].values():
        card.pop('legacy')
        for block in card['blocks']:
            for index, reference in enumerate(block['links']):
                if reference not in entries:
                    if reference not in assets:
                        raise ValueError(f'경사형 연혁집 원본 표 누락: {reference}')
                    continue
                entry = entries[reference]
                key = 'incline-book-' + reference
                file, width, height = FIGURE.search(entry['text']).groups()
                block['links'][index] = key
                assets.setdefault(key, {'key': key, 'src': 'b23', 'kind': 'table', 'num': '',
                    'title': entry['title'], 'historical': True, 'source': block['head'],
                    'pages': [{'file': file, 'width': int(width), 'height': int(height), 'page': entry['pages'][0]}]})
    data['ref_assets'].update(assets)
