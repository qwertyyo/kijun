"""Load the site export of the completed incline history book."""
import json
from pathlib import Path
import re
from shutil import copyfile


BUILD = Path(__file__).resolve().parent
FIGURE = re.compile(r'\x10([^|]+)\|(\d+)\|(\d+)')


def apply_book_history(data):
    book = json.loads((BUILD / 'incline_book_history.json').read_text(encoding='utf-8'))
    entries = {row['id']: row for row in data['b23']}
    if not set(book['cards']) <= entries.keys():
        raise ValueError('경사형 연혁집에 연결할 사이트 조문이 없습니다.')
    data['incline_book'] = book['cards']
    assets = book['assets']
    for asset in assets.values():
        for page in asset['pages']:
            file = page['file']
            copyfile(BUILD.parent / 'fig' / file, BUILD / 'fig' / file)
    for card in data['incline_book'].values():
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
