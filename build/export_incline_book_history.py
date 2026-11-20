"""Export the verified incline history book to the site's existing cards.

The review receipts and source PDFs stay local. The site build reads the
generated JSON and public table crops, so it does not need the review archive.
"""
from collections import defaultdict
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess

import pymupdf
from PIL import Image

from incline_history_original_projection import clean_original, korean_date


BUILD = Path(__file__).resolve().parent
ROOT = BUILD.parent
RECEIPT = ROOT / 'tmp/pdfs/incline-history-original'
DATE = re.compile(r'^(\d{4})년\s+(\d{1,2})월\s+(\d{1,2})일')
BASE_RELEASE = 'b5dbbd69bda0d57e795032e2d115cd3ef08280e6'
PROVENANCE = re.compile(r'(?:[·ㆍ|]\s*)?원문\s*PDF\s*\d+\s*쪽')
# Multiple receipts can document the same change. Keep every receipt linked
# to the card and show its shared wording once in the date summary.
SHARED_SUMMARIES = {
    '2022/b23-15.2.3.3/stage-01': '비상통화 버튼 높이 0.8~1.2 m 추가 · 화물용 및 휠체어용 조작반의 예외',
    'incline-controls-reference-2019/15.2.3.3/stage-02': '비상통화 버튼 높이 0.8~1.2 m 추가 · 화물용 및 휠체어용 조작반의 예외',
    '2022/b23-7.4.4.1/stage-01': '피트·상부공간 정지 기능 유지 · 개문출발 → 문열림출발',
    'incline-hydraulic-general-transition-2019/7.4.4.1-h3/stage-02': '피트·상부공간 정지 기능 유지 · 개문출발 → 문열림출발',
    'incline-wireless-general-transition-2019/general-6.8/stage-01': '승강로 사용 제한 5.8 → 6.8 · 냉난방·소방·영상설비 예외 정비',
    'incline-wireless-general-transition-2019/wireless-reference/stage-01': '유·무선 전송기기 특례는 해당 설비의 대체검사기준 준용',
}
CURRENT_SUMMARIES = {
    'b23-6.8': '승강로 전용 사용 · 허용되는 난방 설비의 제어·조절장치는 승강로 밖에 설치',
    'b23-7.4.4.1': '피트·상부공간 작업 중 카 정지 · 각 공간 점검운전 · 승강로 밖에서 재설정',
    'b23-14.6': '로봇 안전성 평가 · 카에 높이 15 mm 이상으로 표시 · 무선통신장치 안전성 입증',
    'b23-15.2.3.3': '통화장치 이중 설치(상주 장소 2곳 미만은 1개 가능) · 내부 불통 시 외부 자동 연결 · 버튼 높이 0.8~1.2 m(예외 있음)',
}


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def date_key(label):
    date = DATE.match(label)
    if not date:
        raise ValueError(f'날짜 표기가 없는 연혁: {label}')
    y, m, d = map(int, date.groups())
    return f'{y:04d}.{m:02d}.{d:02d}'


def caption(value):
    value = re.sub(r'(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})\.(?=\s)', r'\1.\2.\3', value)
    value = korean_date(value.strip(' ·'))
    value = (value
            .replace('일부터 검사기준부터 시행', '일부터 검사기준 시행')
            .replace('일 검사기준부터 시행', '일부터 검사기준 시행')
            .replace('일 검사결과 판정지침 시행', '일부터 검사결과 판정지침 시행')
            .replace('일 검사결과 판정지침부터 시행', '일부터 검사결과 판정지침 시행')
            .replace('일 검사판정 적용', '일부터 검사판정 적용'))
    return re.sub(r'일 시행(?=\s*(?:·|$))', '일부터 시행', value)


def words(text):
    return re.sub(r'\s+', ' ', clean_original(text)).strip()


def compact(text):
    return re.sub(r'[\s\x01-\x04]', '', clean_original(text))


def legacy_caption(block):
    if not block.get('date_unknown'):
        return clean_original(block['head'])
    source = block['source_head']
    if source.startswith('2019'):
        return '2019년 4월 4일 시행 기준 준용'
    if source.startswith('2016') and '전송기기' in block['head']:
        return '2019년 4월 4일 시행 전 기준'
    if source.startswith('2014'):
        return '2014년 7월 1일 시행 기준 준용'
    raise ValueError(f'확정 연혁집에 없는 특례 날짜: {source}')


def history_text(value):
    # HWP repeats these three column labels in the middle of one selection.
    # The book omits those labels on the same selections.
    return re.sub(r'(?m)^항\s*목[ \t]*\n[ \t]*대체검사기준[ \t]*\n[ \t]*비\s*고[ \t]*\n', '', PROVENANCE.sub('', value)).strip()


def export():
    audit = read(RECEIPT / 'audit.json')
    review = read(RECEIPT / 'visual-review-final.json')
    pdf = ROOT / audit['path']
    source = BUILD / 'data.json'
    assert audit['visual_review_passed'] and review['visual_review_passed']
    assert digest(pdf) == audit['sha256'] == review['pdf_sha256']
    data = read(source)
    if digest(source) != audit['site_data_sha256']:
        # A site build can serialize the same data in a different key order.
        previous_html = subprocess.check_output(['git', 'show', BASE_RELEASE + ':index.html'], cwd=ROOT).decode('utf-8')
        baseline = json.loads(previous_html.split('<script id="data" type="application/json">', 1)[1].split('</script>', 1)[0])
        assert all(data[name] == baseline[name] for name in ('b23', 'hist_incline'))
    entries = {row['id']: row for row in data['b23']}
    assert {key for key, row in entries.items() if not row.get('group')} == set(audit['current_main_clause_ids'])
    base_history = data['hist_incline']
    chronology = read(ROOT / 'tmp/pdfs/comparison-chronology/audit.json')
    stage_sources = {}
    for receipt in chronology['chronology_audit']['receipts']:
        path = ROOT / receipt['path']
        assert digest(path) == receipt['sha256']
        for parent in read(path)['parent_rows']:
            if parent['source_row_id'] in audit['source_assignments']:
                for stage in parent['stages']:
                    stage_sources[stage['id']] = stage
    assert set(stage_sources) == set(audit['stage_placements'])

    include_path = ROOT / 'fig'
    include_path.mkdir(exist_ok=True)
    asset_key = 'incline-book-flatbelt-final-table'
    flatbelt_pages = []
    with pymupdf.open(pdf) as document:
        for page_number, original in audit['additional_source_pages'].items():
            page = document[int(page_number) - 1]
            pixmap = page.get_pixmap(clip=pymupdf.Rect(88, 120, 508, 714), dpi=190, alpha=False)
            image = Image.open(io.BytesIO(pixmap.tobytes('png')))
            name = f'hin_book_flatbelt_{-original}.webp'
            image.save(include_path / name, 'WEBP', quality=93, method=4)
            flatbelt_pages.append({'file': name, 'width': image.width, 'height': image.height,
                                   'page': int(page_number)})
    assets = {asset_key: {'key': asset_key, 'src': 'b23', 'kind': 'table', 'num': '',
                          'title': '플랫벨트 마모·손상 판정기준', 'historical': True,
                          'source': '2022년 10월 21일부터 검사판정 적용', 'pages': flatbelt_pages}}

    by_stage = defaultdict(list)
    panels = {}
    for record in audit['original_state_projection']:
        by_stage[record['stage_id']].append(record)
        if record['text']:
            assert isinstance(record['binding'], str) and record['binding'].startswith('panel/')
            panels.setdefault(record['binding'], record)
    used_panels = set()
    cards = defaultdict(lambda: {'stages': [], 'blocks': [], 'summary': [], 'legacy': {}})
    seen_blocks = defaultdict(set)
    represented_legacy = set()
    current_candidates = defaultdict(list)

    def add_block(card_id, label, body, context='', links=(), archive=False):
        label, body, context = caption(label), history_text(body), words(context)
        links = list(dict.fromkeys(links))
        key = (label, compact(body), context, tuple(links), archive)
        if key not in seen_blocks[card_id]:
            seen_blocks[card_id].add(key)
            cards[card_id]['blocks'].append({'head': label, 'text': body, 'sortdate': date_key(label),
                                             'context': context, 'links': links, 'archive': archive,
                                             'legacy_numbering': True, 'reference_only': True})

    def add_summary(card_id, label, description):
        label, description = caption(label), words(description)
        assert description
        item = {'label': label, 'date': date_key(label), 'text': description}
        if item not in cards[card_id]['summary']:
            cards[card_id]['summary'].append(item)

    def clauses_in(binding):
        if isinstance(binding, list):
            for part in binding:
                yield from clauses_in(part)
        elif isinstance(binding, str) and binding.startswith('clause/'):
            yield 'b23-' + binding.split('/')[1]

    def add_binding(card_id, record, binding):
        if isinstance(binding, list):
            for part in binding:
                add_binding(card_id, record, part)
        elif isinstance(binding, dict):
            if binding['kind'] == 'original_source_pdf_page':
                page = binding['source_page']
                if page < 0:
                    add_block(card_id, binding['date'], '플랫벨트 마모·손상 판정기준', links=(asset_key,), archive=True)
                else:
                    target = f'b23-methods-p{page}'
                    assert target in entries
                    add_block(card_id, binding['date'], entries[target]['title'], links=(target,), archive=True)
            else:
                assert binding['kind'] == 'source_proof' and record['supporting_context_only']
        elif binding.startswith('panel/'):
            owner = panels[binding]
            used_panels.add(binding)
            scope = owner.get('scope', '')
            if owner['stage_id'].startswith('incline-flatbelt-2022/') and owner['source_id'] == 'special-1638':
                scope = '플랫벨트 현수방식 대체검사기준'
            add_block(card_id, owner['caption'], owner['text'], scope)
        else:
            target, = clauses_in(binding)
            assert target in entries
            if record['side'] == 'before' or target != card_id:
                content = entries[target]['text'] or entries[target]['num'] + ' ' + entries[target]['title']
                add_block(card_id, record['caption'], content)

    for sid, placement in audit['stage_placements'].items():
        stage = stage_sources[sid]
        assignment = audit['source_assignments'][placement['source_row_id']]
        targets = set()
        for review_id in assignment['review_ids']:
            match = re.fullmatch(r'history/b23:([^:]+):h\d+', review_id)
            if match:
                targets.add('b23-' + match[1])
                represented_legacy.add(review_id)
            if review_id.startswith('current/b23-'):
                targets.add(review_id.removeprefix('current/'))
        anchor = assignment['anchor']
        if not anchor.startswith('appendix/'):
            targets.update('b23-' + number for number in [anchor, *assignment['related']])
        if sid.startswith('incline-judgment-2019/'):
            for record in by_stage[sid]:
                if record['side'] == 'before':
                    targets.update(clauses_in(record['binding']))
            for label in stage['before']['clause_labels']:
                for number in re.findall(r'(?<![\d.])\d+(?:\.\d+){1,5}(?![\d.])', label):
                    if 'b23-' + number in entries:
                        targets.add('b23-' + number)
        assert targets and targets <= entries.keys(), (sid, targets - entries.keys())
        label = placement['heading_date']
        if sid.startswith('incline-brake-ard-2026/'):
            label = '2026년 11월 1일부터 검사방법 적용'
        for target in sorted(targets):
            cards[target]['stages'].append(sid)
            add_summary(target, label, SHARED_SUMMARIES.get(sid, stage['change_summary']))
            for record in by_stage[sid]:
                add_binding(target, record, record['binding'])
                if record['side'] == 'after' and record['binding'] == f'clause/{entries[target]["num"]}/body':
                    description = words(stage['after']['summary'])
                    if 10 <= len(description) <= 100:
                        current_candidates[target].append((date_key(caption(label)), description))

    assert used_panels == set(panels)
    for number, history in base_history.items():
        card_id = 'b23-' + number
        for index, block in enumerate(history['blocks']):
            rid = f'history/b23:{number}:h{index+1}'
            label = legacy_caption(block)
            if label == '종전 기준':
                replacements = {part['head'] for part in cards[card_id]['blocks']
                                if part['head'].endswith('전 기준') and part['text'] == '해당 규정 없음.'}
                label, = replacements
            label = caption(label)
            cards[card_id]['legacy'][str(index)] = label
            if rid not in represented_legacy or block.get('legacy_supplement') or block.get('date_unknown') or rid in audit['retained_history_blocks']:
                gist = ('유압식 준용 · ' if block.get('legacy_supplement') else '') + block['g']
                add_summary(card_id, label, gist)
        if history.get('curg'):
            cards[card_id]['current'] = history['curg']

    assert {stage_id for card in cards.values() for stage_id in card['stages']} == set(audit['stage_placements'])
    for card_id, card in cards.items():
        if card_id in CURRENT_SUMMARIES:
            card['current'] = CURRENT_SUMMARIES[card_id]
        elif current_candidates[card_id] and (not card.get('current') or card['current'].endswith('…')):
            card['current'] = max(current_candidates[card_id])[1]
        card['summary'].sort(key=lambda item: (item['date'], '전 기준' not in item['label'], item['label']))
    output = {'book_sha256': audit['sha256'], 'stage_count': len(stage_sources), 'cards': dict(cards), 'assets': assets}
    (BUILD / 'incline_book_history.json').write_text(json.dumps(output, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')
    print(f'경사형 {len(cards)}개 카드, {len(stage_sources)}개 개정 단계, 원본 판정표 {len(flatbelt_pages)}장')


if __name__ == '__main__':
    export()
