"""양쪽 안전기준의 표·그림 참조 목록. 검토한 원문 위치와 현행 영역만 사용한다."""
import hashlib
import io
import json
from pathlib import Path
import re

from PIL import Image
import pymupdf


def compact(text):
    return re.sub(r'[\s\x01-\x04]+', '', text)


def build_reference_assets(data, base=None):
    base = Path(base or Path(__file__).parent)
    config = json.loads((base / 'reference_assets_map.json').read_text(encoding='utf-8'))
    entries = {e['id']: e for src in ('b22', 'b24') for e in data[src]}
    docs = {}
    output = base / 'fig'
    output.mkdir(exist_ok=True)
    catalog = {}
    try:
        for src, spec in config['sources'].items():
            path = base / spec['pdf']
            if hashlib.sha256(path.read_bytes()).hexdigest() != spec['sha256']:
                raise ValueError(f'{src} 원문 변경: 표·그림 위치를 재검토해야 합니다.')
            docs[src] = pymupdf.open(path)
        for spec in config['assets']:
            key = spec['key']
            owner = entries[spec['owner']]
            pdf = docs[spec['src']]
            if compact(spec['caption']) not in compact(pdf[spec['caption_page'] - 1].get_text()):
                raise ValueError(f'{key}: 원문 표·그림 제목이 일치하지 않습니다.')
            pages = []
            for i, clip in enumerate(spec.get('clips', [])):
                pn, *coords = clip
                page = pdf[pn - 1]
                rect = pymupdf.Rect(coords)
                if not page.rect.contains(rect):
                    raise ValueError(f'{key}: 원문 밖 자르기 영역')
                pix = page.get_pixmap(clip=rect, dpi=200)
                image = Image.open(io.BytesIO(pix.tobytes('png'))).convert('RGB')
                filename = 'ref_' + key.replace('-', '_').replace('.', '_') + f'_{i}.webp'
                if spec.get('versioned'):
                    filename = filename.removesuffix('.webp') + '_' + hashlib.sha256(image.tobytes()).hexdigest()[:10] + '.webp'
                image.save(output / filename, 'WEBP', quality=88, method=6)
                pages.append(dict(file=filename, width=image.width, height=image.height, page=pn))
            inline = {m[1]: (int(m[2]), int(m[3])) for m in re.finditer(
                r'\x10([^|]+)\|(\d+)\|(\d+)\x0e', owner['text'])}
            for filename in spec.get('files', []):
                if filename not in inline:
                    raise ValueError(f'{key}: 현행 소속 조문에서 표 영역을 찾지 못했습니다: {filename}')
                with Image.open(output / filename) as image:
                    if image.size != inline[filename]:
                        raise ValueError(f'{key}: 이미지 크기 불일치')
                    width, height = image.size
                pn = int(re.search(r'_p(\d+)_', filename)[1])
                pages.append(dict(file=filename, width=width, height=height, page=pn))
            if not pages:
                raise ValueError(f'{key}: 표시할 표·그림이 없습니다.')
            item = {k: spec[k] for k in ('key', 'src', 'kind', 'num', 'owner', 'title')}
            item.update(pages=pages, source='승강기 안전기준 연혁집' + (' v2.0' if spec['src'] == 'b24' else ''),
                        caption_page=spec['caption_page'])
            if spec.get('row_pages'):
                item['row_pages'] = spec['row_pages']
            if key == 'b24-table-Ⅱ.1':
                item['row_pages'] = {'3.1': 1, '3.6': 1}
                for page, old in zip(pages, data['es_tables']['Ⅱ.1']['pages']):
                    page['title'] = old['title']
            catalog[key] = item
        for num, figure in data['es_figures'].items():
            key = f'b24-figure-{num}'
            catalog[key] = dict(key=key, src='b24', kind='figure', num=num, title=figure['title'],
                                source=figure['source'], owner=figure['owner'],
                                pages=[dict(file=figure['file'], width=figure['width'], height=figure['height'],
                                            page=figure['pages'][0], page_label='·'.join(map(str, figure['pages'])))])
    finally:
        for doc in docs.values():
            doc.close()
    for alias in config['aliases']:
        if alias['entry'] not in entries or alias['target'] not in catalog:
            raise ValueError(f'확인되지 않은 원문 참조 설명: {alias}')
    print('reference assets', len(catalog), '| aliases', len(config['aliases']))
    return catalog, config['aliases']


NUMBER = r'(?:(?:XⅢ|XⅣ|[Ⅰ-Ⅻ]|[IVX]+)\s*\.\s*)?\d+(?:\.\d+)*'
NAMED = re.compile(r'(?<!별)(표|그\s*림)\s*(' + NUMBER + r')(?![\d.])')
ROMAN = dict(zip(('I','II','III','IV','V','VI','VII','VIII','IX','X','XI','XII','XIII','XIV'),
                 ('Ⅰ','Ⅱ','Ⅲ','Ⅳ','Ⅴ','Ⅵ','Ⅶ','Ⅷ','Ⅸ','Ⅹ','Ⅺ','Ⅻ','XⅢ','XⅣ')))


def number(text):
    text = compact(text)
    return re.sub(r'^[IVX]+(?=\.)', lambda m: ROMAN.get(m[0], m[0]), text)


def prose(text):
    return re.sub(r'\[[^\]]*\]', '', re.sub(r'\x10.*?\x11', '', text, flags=re.S))


def reference_source(text, at, default=None):
    # 문장이 바뀌면 앞 문장에서 인용한 외부 규격의 범위도 끝난다.
    before = re.split(r'(?<=[다함음])\.', text[:at])[-1]
    markers = list(re.finditer(r'별표(\d+)|KS[A-Z]|(?:EN|ISO|IEC)\d', before, re.I))
    if not markers:
        return default
    marker = markers[-1]
    return {'22': 'b22', '24': 'b24'}.get(marker[1], 'unsupported')


def build_context_asset_links(data, catalog, base=None):
    """표준화 인용은 번호와 주변 문구가 같은 원문에만, 연혁은 해당 판에만 연결한다."""
    base = Path(base or Path(__file__).parent)
    config = json.loads((base / 'reference_assets_map.json').read_text(encoding='utf-8'))
    candidates = []
    history_links = {}
    for src, hkey in [('b22', 'hist'), ('b24', 'hist_es')]:
        for num, history in data[hkey].items():
            for index, block in enumerate(history['blocks']):
                text = block['text']
                images = list(re.finditer(r'\x10([^|]+)\|(\d+)\|(\d+)\x0e(.*?)\x11', text, re.S))
                if not images:
                    continue
                # 과거 번호가 실제 제목으로 수록된 경우만 당시 이미지를 사용한다.
                blockkey = f'{src}-{num}:{index}'
                captions = re.findall(r'(?:\[\s*|^\s*)(표|그\s*림)\s*(' + NUMBER + r')', re.sub(r'[\x01-\x04]', '', text), re.M)
                for override in config.get('history_overrides', []):
                    if override['block'] == blockkey:
                        with pymupdf.open(base / config['sources'][src]['pdf']) as doc:
                            if compact(override['caption']) not in compact(doc[override['caption_page'] - 1].get_text()):
                                raise ValueError(f'과거 표·그림 원문 위치 변경: {blockkey}')
                        captions.append(('표' if override['kind'] == 'table' else '그림', override['num']))
                for label, rawnum in captions:
                    kind, assetnum = ('table' if label == '표' else 'figure'), number(rawnum)
                    key = f'history-{blockkey}-{kind}-{assetnum}'
                    if key in catalog:
                        continue
                    pages = [dict(file=m[1], width=int(m[2]), height=int(m[3]),
                                  page=int(re.search(r'_p(\d+)_', m[1])[1])) for m in images]
                    catalog[key] = dict(key=key, src=src, kind=kind, num=assetnum, owner=f'{src}-{num}',
                                        title='해당 연혁에 수록된 원문 자료', source='승강기 안전기준 연혁집 · ' + block['head'],
                                        historical=True, history_head=block['head'], pages=pages)
                    history_links.setdefault(blockkey, {})[kind + '-' + assetnum] = [key]
    # 같은 판의 다른 조문에서 참조하는 옛 그림도 당시 제목·적용 연혁이 일치해야 한다.
    for src, hkey in [('b22', 'hist'), ('b24', 'hist_es')]:
        for num, history in data[hkey].items():
            for index, block in enumerate(history['blocks']):
                blockkey = f'{src}-{num}:{index}'
                text = compact(prose(block['text']))
                for match in NAMED.finditer(text):
                    if reference_source(text, match.start(), src) == 'unsupported':
                        continue
                    kind, assetnum = ('table' if match[1] == '표' else 'figure'), number(match[2])
                    label = kind + '-' + assetnum
                    keys = history_links.get(blockkey, {}).get(label)
                    if not keys:
                        keys = [a['key'] for a in catalog.values() if a.get('historical') and a['src'] == src
                                and a['kind'] == kind and a['num'] == assetnum and a['history_head'] == block['head']]
                        if keys:
                            history_links.setdefault(blockkey, {})[label] = keys
                    if keys:
                        candidates.append((kind, assetnum, text, keys))
    for src in ('b22', 'b24'):
        for entry in data[src]:
            text = compact(prose(entry['title'] + '\n' + entry['text']))
            for match in NAMED.finditer(text):
                source = reference_source(text, match.start(), src)
                if source == 'unsupported':
                    continue
                kind, num = ('table' if match[1] == '표' else 'figure'), number(match[2])
                assets = [a for a in catalog.values() if not a.get('historical') and a['src'] == source and a['kind'] == kind and a['num'] == num]
                alias = next((a for a in config['aliases'] if (a['entry'], a['kind'], a['num']) == (entry['id'], kind, num)), None)
                if alias and source == src:
                    assets = [catalog[alias['target']]]
                if len(assets) > 1:
                    owned = [a for a in assets if a['owner'] == entry['id']]
                    if owned:
                        assets = owned
                if assets:
                    candidates.append((kind, num, text, [a['key'] for a in assets]))
    def affinity(left, right, before, after):
        n = 0
        for a, b in zip(reversed(left[-60:]), reversed(before[-60:])):
            if a != b: break
            n += 1
        m = 0
        for a, b in zip(right[:60], after[:60]):
            if a != b: break
            m += 1
        return n + m if max(n, m) >= 18 or min(n, m) >= 10 else 0
    std_links = {}
    for entry in data['std']:
        text = compact(prose(entry['text']))
        for match in NAMED.finditer(text):
            if reference_source(text, match.start()) == 'unsupported':
                continue
            kind, num = ('table' if match[1] == '표' else 'figure'), number(match[2])
            scored = []
            for ck, cn, candidate, keys in candidates:
                if (ck, cn) != (kind, num):
                    continue
                for other in NAMED.finditer(candidate):
                    if number(other[2]) != num or ('table' if other[1] == '표' else 'figure') != kind:
                        continue
                    score = affinity(text[:match.start()], text[match.end():], candidate[:other.start()], candidate[other.end():])
                    if score >= 24:
                        scored.append((score, keys))
            if scored:
                best = max(s for s, _ in scored)
                winners = {tuple(keys) for score, keys in scored if score == best}
                selected = sorted({key for keys in winners for key in keys})
                links = std_links.setdefault(entry['id'], {})
                label = kind + '-' + num
                links[label] = sorted(set(links.get(label, []) + selected))
        # 해당 안건 자체에 제목이 실린 표·그림은 당시 원문 자료로 연다.
        local = re.findall(r'\[\s*(표|그\s*림)\s*(' + NUMBER + r')', entry['text'])
        images = [dict(file=m[0], width=m[2], height=m[3], page=m[1], folder='stdimg') for m in entry.get('img', [])]
        for m in re.finditer(r'\x10(stb_p(\d+)_\d+\.webp)\|(\d+)\|(\d+)\x0e', entry['text']):
            images.append(dict(file=m[1], width=int(m[3]), height=int(m[4]), page=int(m[2]), folder='stdimg'))
        if images:
            for label, rawnum in local:
                kind, num = ('table' if label == '표' else 'figure'), number(rawnum)
                key = entry['id'] + '-' + kind + '-' + num
                catalog[key] = dict(key=key, src='std', kind=kind, num=num, owner=entry['id'],
                                    title='해당 안건에 수록된 원문 자료', source=entry['path'] + ' · ' + entry['title'], pages=images)
                std_links.setdefault(entry['id'], {})[kind + '-' + num] = [key]
    by_id = {e['id']: e for e in data['std']}
    for spec in config.get('local_overrides', []):
        entry = by_id[spec['entry']]
        available = {m[0]: m for m in entry.get('img', [])}
        pages = []
        for filename in spec['files']:
            if filename not in available:
                raise ValueError(f'표준화 원문 이미지 소속 변경: {entry["id"]} {filename}')
            m = available[filename]
            pages.append(dict(file=m[0], width=m[2], height=m[3], page=m[1], folder='stdimg'))
        key = entry['id'] + '-' + spec['kind'] + '-' + spec['num']
        catalog[key] = dict(key=key, src='std', kind=spec['kind'], num=spec['num'], owner=entry['id'],
                            title=spec['title'], source=entry['path'] + ' · ' + entry['title'], pages=pages)
        std_links.setdefault(entry['id'], {})[spec['kind'] + '-' + spec['num']] = [key]
    for spec in config.get('standard_overrides', []):
        if spec['entry'] not in by_id or spec['target'] not in catalog:
            raise ValueError('표준화 참조 연결 근거 변경')
        std_links.setdefault(spec['entry'], {})[spec['kind'] + '-' + spec['num']] = [spec['target']]
    print('context assets', 'standardization', len(std_links), '| historical blocks', len(history_links))
    return std_links, history_links
