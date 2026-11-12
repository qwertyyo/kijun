"""검토한 종전 유압식 특례/준용 기술조항을 경사형 연혁집에 보완한다."""
import hashlib
import json
from pathlib import Path
import re
import shutil

BASE = Path(__file__).parent
REVIEW = BASE / 'hist_incline/legacy_technical.json'


def supplement_history(entries, histories, catalog, history_links, base=BASE):
    review = json.loads(REVIEW.read_text(encoding='utf-8'))
    # 원 PDF의 강제 개행만 고친다. 수식/그림과 공백 이외의 글자는 그대로 둔다.
    layout = json.loads((BASE/'hist_incline/text_layout.json').read_text(encoding='utf-8'))
    def apply_layout(target, patch):
        if hashlib.sha256(target['text'].encode()).hexdigest() != patch['input_sha256']:
            raise ValueError('줄바꿈 검토 후 원문 변경: '+str(target.get('id',target.get('head'))))
        if re.sub(r'\s','',target['text']) != re.sub(r'\s','',patch['text']):
            raise ValueError('줄바꿈 보정에 내용 변경이 포함됨')
        target['text'] = patch['text']
    for key,patch in layout['current'].items():apply_layout(entries[key],patch)
    for key,patch in layout['history'].items():
        num,index=key.rsplit(':',1)
        apply_layout(histories[num]['blocks'][int(index)],patch)
    old_title=entries['b23-11.1']['title']
    title=old_title.replace('부 품','부품').replace('일반사 항','일반사항')
    entries['b23-11.1']['title']=title
    for entry in entries.values():entry['path']=entry['path'].replace(old_title,title)
    # 편찬월은 적용일로 표시하지 않는다. 날짜가 없는 인정자료는 별도 표시한다.
    for h in histories.values():
        for block in h['blocks']:
            old=block['head']
            if '수록본' in old:
                block['source_head']=old
                block['head']='적용일 미확인 · '+re.sub(r'^\d{4}\.\d{2} 수록본\s*·\s*','',old)
                block.update(when_label=block['head'],date_unknown=True,legacy_numbering=True,
                             date_note='특례 원인정일과 적용 대상 설비는 개별 인정서 확인 필요')
                block.pop('sortdate',None)
            elif old.startswith('2020. 3. 28.'):
                block.update(source_head=old,head='2020년 3월 28일 이후 출고·통관 제어반부터 적용',
                             when_label='2020년 3월 28일 이후 출고·통관 제어반부터 적용',basis='출고',**{'from':'2020.03.28'})
    by_num = {e['num']:e for e in entries.values()}
    for key,gist in review['original_gists'].items():
        num,index=key.rsplit(':',1)
        histories[num]['blocks'][int(index)]['g']=gist
    for num, gist in review['verified_special_gists'].items():
        original = [b for b in histories[num]['blocks'] if b.get('source_head','').startswith('2014.10 수록본')]
        if len(original) != 1:
            raise ValueError('원 연혁집의 유압식 특례를 찾지 못함: ' + num)
        original[0].update(g=gist,
                           legacy_numbering=True, verified_compilations=[v['compilation'] for v in review['verified_compilations']])
    for item in review['entries']:
        e = by_num[item['target']]
        h = histories.setdefault(e['num'], dict(cur=None,blocks=[]))
        block = dict(head=item['head'],text=item['text'],g=item['g'],basis=item['basis'],
                     siheng=item['basis']=='시행',sortdate=item['sortdate'],when_label=item['when_label'],
                     applies_to=item['applies_to'],date_basis=item['date_basis'],old_num=item['old_num'],
                     legacy_numbering=True,legacy_supplement=True,
                     source=review['sources'][item['source']]['title'],
                     reference_only=True,**{'from':item['effective_date'],'to':None})
        if item.get('effective_date'):
            block['reference_effective_date'] = item['effective_date']
        if item.get('figure'):
            figure = item['figure']
            block['figure_source']=item['figure_source']
            source_file = BASE / 'hist_incline' / figure['file']
            if hashlib.sha256(source_file.read_bytes()).hexdigest() != figure['sha256']:
                raise ValueError('검토한 종전 그림과 다른 입력: '+figure['file'])
            Path(base,'fig').mkdir(exist_ok=True)
            shutil.copy2(source_file,Path(base,'fig',figure['file']))
            block['text'] += '\n\x10%s|%d|%d\x0e%s\x11' % (figure['file'],figure['width'],figure['height'],figure['title'])
            key = 'history-legacy-' + e['id'] + '-figure-' + figure['num']
            catalog[key] = dict(key=key,src='b23',kind='figure',num=figure['num'],title=figure['title'],
                owner=e['id'],historical=True,history_head=block['head'],source=block['figure_source'],
                pages=[dict(file=figure['file'],width=figure['width'],height=figure['height'],page=0)])
            history_links[e['id'] + ':' + str(len(h['blocks']))] = {'figure-'+figure['num']:[key]}
        h['blocks'].append(block)
    for num,h in histories.items():
        e=by_num[num]
        text=re.sub(r'\x10[^\x0e]*\x0e([^\x11]*)\x11',r'\1',e['text'])
        text=re.sub(r'\s+',' ',text).strip()
        h['curg']=review['current_gists'].get(num,text[:110]+('…' if len(text)>110 else ''))
    return dict(review_version=review['version'],added_blocks=len(review['entries']),
                layout_current=len(layout['current']),layout_history=len(layout['history']),
                rechecked_special_blocks=len(review['verified_special_gists']),
                published_history_blocks=sum(len(h['blocks']) for h in histories.values()),
                scope_note=review['scope_note'])
