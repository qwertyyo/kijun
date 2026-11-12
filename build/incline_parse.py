"""사용자 제공 경사형 연혁집 v0.2를 기존 카드/연혁 형식으로 변환한다.

글자층과 다른 벡터 수식, 표, 그림은 해당 원문 영역을 보존한다.
수록본 날짜를 법정 시행일로 간주하지 않는다. 원본은 수정하지 않는다.
"""
from collections import OrderedDict
import hashlib
import io
import json
from pathlib import Path
import re

from PIL import Image
import pymupdf

BASE = Path(__file__).parent
SOURCE = BASE / 'hist_incline/hist.pdf'
SOURCE_SHA256 = 'd781d2cca463e74cc6a78f699b52acaede661e7805bd90620d03ddaa9cf80636'
ROMAN = r'(?:XⅢ|[Ⅰ-Ⅻ])'
NUMBER = rf'(?:{ROMAN}(?:\.\d+)*|\d+(?:\.\d+)*)'
HEAD = re.compile(rf'^({NUMBER})(?:\s+|$)(.*)')
ASSET_NUMBER = rf'(?:{ROMAN}\.\d+(?:\.\d+)*|\d+(?:\.\d+)*)'
CAPTION = re.compile(rf'^\s*\[?\s*(표|그림)\s*({ASSET_NUMBER})(?![\d가-힣A-Za-z]|\.\d)\s*[-―–—. ]\s*(.*)')


def normalized(text):
    return re.sub(r'\s*\.\s*(?=\d)', '.', text.replace('\u3000', ' ')).strip()


def lines_on(page):
    raw = [line for block in page.get_text('dict')['blocks'] if block['type'] == 0
           for line in block['lines'] if 55 <= line['bbox'][1] < 798]
    rows = []
    for line in sorted(raw, key=lambda l: (round(l['bbox'][1], 1), l['bbox'][0])):
        if rows and abs(rows[-1]['y'] - line['bbox'][1]) < 2.1:
            rows[-1]['spans'].extend(line['spans'])
        else:
            rows.append({'y': line['bbox'][1], 'spans': list(line['spans'])})
    for row in rows:
        spans = row['spans'] = sorted(row['spans'], key=lambda s: s['bbox'][0])
        row['text'] = ''.join(s['text'] for s in spans).strip()
        row['bbox'] = tuple(pymupdf.Rect(spans[0]['bbox']))
        rect = pymupdf.Rect(row['bbox'])
        for span in spans[1:]:
            rect |= pymupdf.Rect(span['bbox'])
        row['bbox'] = tuple(rect)
    return rows


def paragraph_text(rows):
    # 원문의 물리적 줄바꿈을 유지한다. 단어 중간에서 임의의 공백을 만들지 않는다.
    return '\n'.join(row['text'].strip() for row in rows if row['text'].strip())


def build_incline(base=BASE):
    base = Path(base)
    source = base / 'hist_incline/hist.pdf'
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    doc = pymupdf.open(source)
    if digest != SOURCE_SHA256 or len(doc) != 207 or '경사형' not in doc.metadata.get('title', ''):
        raise ValueError('검토한 경사형 연혁집 v0.2(207쪽)와 다른 입력입니다.')
    # 기존 사이트의 공개자료 처리 규칙: 공문 수신/결재·연락처·직인만 가린다.
    # 디스크의 사용자 원본은 변경하지 않으며 이 PDF 자체를 공개하지 않는다.
    redactions = {199: [95, 580, 511, 750]}
    for pn, rect in redactions.items():
        doc[pn - 1].add_redact_annot(pymupdf.Rect(rect), fill=(.92,.92,.92))
        doc[pn - 1].apply_redactions(images=2, graphics=1, text=0)
    output = base / 'fig'
    output.mkdir(exist_ok=True)
    entries, histories, catalog, history_links = OrderedDict(), {}, {}, {}
    coverage = []
    images = []
    current = None
    destination = None
    title_open = False
    annex_title_pending = False
    crops = 0

    def entry(num, title, page):
        nonlocal current, destination, title_open
        key = 'b23-' + num
        if key not in entries:
            parents = ['.'.join(num.split('.')[:i]) for i in range(1, len(num.split('.')))]
            path = ' › '.join(p + ' ' + entries['b23-' + p]['title']
                              for p in parents if 'b23-' + p in entries)
            entries[key] = dict(src='b23', id=key, num=num, title=title,
                                path=path, text='', pages=[], collection='안전기준')
        elif title and title != entries[key]['title']:
            entries[key]['text'] += '\n' + title + '\n'
        current = entries[key]
        if page not in current['pages']:
            current['pages'].append(page)
        destination = current
        title_open = bool(title)

    def save_crop(page, rect, text):
        nonlocal crops
        rect = rect & pymupdf.Rect(60, 55, 541, 798)
        pix = page.get_pixmap(clip=rect, dpi=180, alpha=False)
        im = Image.open(io.BytesIO(pix.tobytes('png'))).convert('RGB')
        name = f'hin_p{page.number + 1}_{crops}_{digest[:8]}.webp'
        im.save(output / name, 'WEBP', quality=90, method=4)
        images.append(dict(file=name, page=page.number + 1, rect=list(rect), width=im.width, height=im.height))
        crops += 1
        # 기존 본문 렌더러는 줄 단위로 처리하므로 그림의 숨은 검색 글자는 한 줄로 둔다.
        searchable = re.sub(r'\s+', ' ', text).strip()
        return name, im.width, im.height, '\x10%s|%d|%d\x0e%s\x11' % (name, im.width, im.height, searchable)

    def append_region(page, rows, start, end, regions):
        if destination is None or end <= start:
            return
        selected = [r for r in rows if start <= r['y'] < end and not r.get('skip')]
        visual = [r for r in regions if r.y1 > start + 1 and r.y0 < end - 1]
        text = paragraph_text(selected)
        if not text and not visual:
            return
        if page.number + 1 not in current['pages']:
            current['pages'].append(page.number + 1)
        coverage.append(dict(page=page.number + 1, owner=current['id'],
                             history=destination is not current, lines=len(selected)))
        if visual:
            top = min([r['bbox'][1] for r in selected] + [max(start, r.y0) for r in visual]) - 2
            bottom = max([r['bbox'][3] for r in selected] + [min(end, r.y1) for r in visual]) + 2
            name, width, height, value = save_crop(page, pymupdf.Rect(62, max(start, top), 540, min(end, bottom)), text)
            for row in selected:
                match = CAPTION.match(normalized(row['text']))
                if not match:
                    continue
                label, num, title = match.groups()
                kind = 'table' if label == '표' else 'figure'
                historical = destination is not current
                idx = histories[current['num']]['blocks'].index(destination) if historical else None
                key = (f'history-{current["id"]}:{idx}' if historical else current['id']) + f'-{kind}-{num}'
                asset = catalog.setdefault(key, dict(key=key, src='b23', kind=kind, num=num,
                    title=title.strip(' ]') or row['text'], owner=current['id'], pages=[],
                    source='경사형 엘리베이터 안전기준 연혁집 · 초안 v0.2', historical=historical))
                if historical:
                    asset['history_head'] = destination['head']
                    history_links.setdefault(f'{current["id"]}:{idx}', {})[kind + '-' + num] = [key]
                asset['pages'].append(dict(file=name, width=width, height=height, page=page.number + 1))
        else:
            value = text
        destination['text'] = (destination['text'] + '\n' + value).strip()

    for pn in range(2, 160):
        page = doc[pn]
        rows = lines_on(page)
        tables = [pymupdf.Rect(t.bbox) for t in page.find_tables().tables if t.row_count >= 2 and t.col_count >= 2]
        regions = tables + [pymupdf.Rect(im['bbox']) for im in page.get_image_info()]
        # 윤곽선으로 저장된 수식은 글자 추출로 사라지므로 원문 영역으로 표시한다.
        regions += [pymupdf.Rect(d['rect']) for d in page.get_drawings()
                    if d['fill'] is not None and any(item[0] == 'c' for item in d['items'])
                    and d['rect'].y0 >= 55 and d['rect'].y1 < 798]
        start = 55
        for row in rows:
            raw = row['text']
            text = normalized(raw)
            spans = row['spans']
            in_table = any(t.contains(pymupdf.Point(row['bbox'][0] + 2, (row['bbox'][1] + row['bbox'][3])/2)) for t in tables)
            boldnum = spans and spans[0]['size'] >= 10.5 and 'Bold' in spans[0]['font']
            annex = re.fullmatch(rf'부속서\s*({ROMAN})', text)
            match = HEAD.match(text) if not in_table and row['bbox'][0] < 90 else None
            # 부속서 계산 예시의 소제목은 원문에서도 일반 글꼴이다.
            is_head = match and (boldnum or (re.match(ROMAN, text) and spans[0]['size'] >= 10.5))
            if pn == 2 and row['y'] < 180:
                row['skip'] = True
                continue
            if annex or is_head:
                append_region(page, rows, start, row['y'] - 1, regions)
                if annex:
                    entry(annex[1], '', pn + 1)
                    title_open = True
                    annex_title_pending = True
                else:
                    num, rest = match.groups()
                    allbold = (all('Bold' in s['font'] or re.fullmatch(r'[Ⅰ-ⅫX .\d]+', s['text']) for s in spans if s['text'].strip())
                               or (re.match(ROMAN, num) and len(rest) < 60 and not re.search(r'(?:다[.。]?|한다[.。]?)$', rest)))
                    entry(num, rest if allbold else '', pn + 1)
                    if not allbold and rest:
                        current['text'] += ('\n' if current['text'] else '') + rest
                # 제목 속 윤곽선 수학 기호도 글자층만으로 대체하지 않는다.
                if any(r.intersects(pymupdf.Rect(row['bbox'])) for r in regions):
                    append_region(page, rows, row['y'] - 2, row['bbox'][3] + 2, regions)
                row['skip'] = True
                start = row['bbox'][3] + 0.1
                continue
            if raw.startswith('➥') and current is not None:
                append_region(page, rows, start, row['y'] - 1, regions)
                head = raw.lstrip('➥').strip()
                h = histories.setdefault(current['num'], dict(cur=None, blocks=[]))
                date = re.search(r'(\d{4})\s*\.\s*(\d{1,2})\s*\.\s*(\d{1,2})', head)
                block = dict(head=head, text='', basis='시행' if date and '시행' in head else '수록',
                             siheng=bool(date and '시행' in head), **{'from': None, 'to': None})
                if date and '시행' in head:
                    block['from'] = f'{date[1]}.{int(date[2]):02d}.{int(date[3]):02d}'
                bookdate = re.search(r'(\d{4})\.(\d{2})\s*수록', head)
                if bookdate:
                    block['sortdate'] = bookdate[0].split()[0]
                h['blocks'].append(block)
                destination = block
                title_open = False
                row['skip'] = True
                start = row['bbox'][3] + 0.1
                continue
            is_current_font = any(s['font'].startswith(('BookSerif', 'BookSans')) and s['size'] >= 9 for s in spans)
            if current is not None and destination is not current and is_current_font:
                touching = [r.y0 - 2 for r in regions if r.intersects(pymupdf.Rect(row['bbox']))]
                boundary = min([row['y'] - 0.5] + touching)
                append_region(page, rows, start, boundary, regions)
                destination = current
                start = boundary
            if current is not None and annex_title_pending and destination is current and all('Bold' in s['font'] and s['size'] >= 10.5 for s in spans if s['text'].strip()):
                append_region(page, rows, start, row['y'] - 1, regions)
                current['title'] = raw
                annex_title_pending = False
                title_open = False
                row['skip'] = True
                start = row['bbox'][3] + 0.1
                continue
            if current is not None and title_open and destination is current:
                if (row['y'] - start < 12 and re.search(r'[가-힣A-Za-z]', raw)
                        and all('Bold' in s['font'] and s['size'] >= 10 for s in spans if s['text'].strip())):
                    current['title'] = (current['title'] + ' ' + raw).strip()
                    row['skip'] = True
                    start = row['bbox'][3] + 0.1
                    continue
                title_open = False
        append_region(page, rows, start, 798, regions)

    # 제목만 있는 절의 연혁은 첫 본문 자식 카드에서 상위 조항 연혁으로 표시.
    # 이 참조는 원문 34쪽(PDF 36쪽)에 있으나 그림 11의 수록 위치는 확인되지 않았다.
    entries['b23-8.2.3.3']['unresolved_refs'] = [dict(kind='figure', num='11',
        note='원문의 그림 11은 제공 연혁집에서 수록 위치를 확인하지 못했습니다.')]
    for num, h in list(histories.items()):
        owner = entries['b23-' + num]
        if not owner['text'].strip():
            child = next((e for e in entries.values() if e['num'].startswith(num + '.') and e['text'].strip()), None)
            if child:
                target = histories.setdefault(child['num'], dict(cur=None, blocks=[]))
                target['blocks'].extend(dict(b, scope=num + ' ' + owner['title']) for b in h['blocks'])
                del histories[num]

    # 상위 조항 연혁을 옮긴 뒤에도 당시 표·그림이 새 카드의 연혁에 연결되게 한다.
    for num, history in histories.items():
        text = entries['b23-' + num]['text']
        text = re.sub(r'\x10[^\x0e]*\x0e([^\x11]*)\x11', r'\1', text)
        text = re.sub(r'\s+', ' ', text).strip()
        history['curg'] = text[:110] + ('…' if len(text) > 110 else '')
    history_links = {}
    for num, history in histories.items():
        for index, block in enumerate(history['blocks']):
            files = set(re.findall(r'\x10([^|]+)\|', block['text']))
            for asset in catalog.values():
                if asset.get('historical') and files.intersection(p['file'] for p in asset['pages']):
                    history_links.setdefault(f'b23-{num}:{index}', {})[asset['kind'] + '-' + asset['num']] = [asset['key']]

    # 후반 검사서식과 발췌자료는 쪽별로 유지해 표의 열·그림·주석을 보존한다.
    supplement = [(161, 'install', '설치검사', '설치검사기준'), (182, 'precision', '정밀검사', '정밀안전검사기준'),
                  (183, 'methods', '검사방법', '검사방법·판정기준')]
    toc = [(title, page) for level, title, page in doc.get_toc() if page >= 184 and level == 2]
    for pn in range(160, len(doc)):
        page = doc[pn]
        _, code, _, section = next(s for s in reversed(supplement) if s[0] <= pn + 1)
        title = section if pn < 183 else next((t for t,p in reversed(toc) if p <= pn + 1), section)
        rows = lines_on(page)
        text = paragraph_text(rows)
        name, width, height, marker = save_crop(page, pymupdf.Rect(62, 55, 540, 798), text)
        key = f'b23-{code}-p{pn + 1}'
        entries[key] = dict(src='b23', id=key, num=f'{pn - 1}쪽', title=title,
                            path=f'경사형 연혁집 › {section} › 원문 {pn - 1}쪽 (PDF {pn + 1}쪽)',
                            text=marker, pages=[pn + 1], collection=section, group=code)
    report = dict(source='hist_incline/hist.pdf', sha256=digest, pages=len(doc),
                  clauses=len(entries)-47, supplement_pages=47, history_blocks=sum(len(h['blocks']) for h in histories.values()),
                  crops=crops, coverage=coverage, images=images, redactions=redactions)
    from incline_legacy import supplement_history
    report['legacy_review'] = supplement_history(entries, histories, catalog, history_links, base)
    (base / 'incline-audit.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    doc.close()
    print('incline', {k:v for k,v in report.items() if k not in ('coverage', 'images')})
    return list(entries.values()), histories, catalog, history_links


if __name__ == '__main__':
    data, history, assets, links = build_incline()
    for name, value in [('base_incline.json',data),('hist_incline_final.json',history),('incline_assets.json',assets),('incline_history_links.json',links)]:
        (BASE / name).write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8')
