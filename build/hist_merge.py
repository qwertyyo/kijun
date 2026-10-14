"""연혁집 연혁을 현행 조문(본문 있는 것)에 붙인다. 제목만 있는 조문(예: 10.6)의 연혁은 바로 다음 본문 조문으로 옮기고 scope 표시"""
import json, sys, re
sys.path.insert(0, '.')
from restore_eq import restore   # 수식 글꼴 사설코드 복원
MODE = sys.argv[1] if len(sys.argv) > 1 else 'el'
SRC, BASE, OUT, GKF = {'el': ('hist.json', 'hwp/b22h.json', 'hist_final.json', 'hist_gist_keyed.json'), 'es': ('hist_es.json', 'hwp/b24h.json', 'hist_es_final.json', 'hist_es_gist_keyed.json')}[MODE]
h = json.load(open(SRC)); b = json.load(open(BASE))
order = [e['num'] for e in b]; has = {e['num']: bool(e['text'].strip()) for e in b}; title = {e['num']: e['title'] for e in b}
out = {}
for n, v in h.items():
    if has.get(n):
        out.setdefault(n, {'cur': None, 'blocks': []})
        out[n]['cur'] = v['cur']; out[n]['blocks'] = v['blocks'] + out[n]['blocks']
    else:
        i = order.index(n); j = next((k for k in range(i + 1, len(order)) if has[order[k]] and order[k].startswith(n + '.')), None)
        if j is None: continue
        t = order[j]; o = out.setdefault(t, {'cur': None, 'blocks': []})
        o['blocks'] = o['blocks'] + [dict(x, scope=f'{n} {title[n]}') for x in v['blocks']]
        if v['cur'] and not o['cur']: o['cur'] = dict(v['cur'], scope=n)
for v in out.values():
    for x in v['blocks']: x['text'] = re.sub(r'(?<=[가-힣])\?(?=[가-힣])', '·', restore(x['text']))
# 연혁 요지(하위 에이전트가 원문 블록별로 작성, 조문|제목|범위|본문앞부분 으로 매칭)
import os
if os.path.exists(GKF):
    GK = json.load(open(GKF))
    # 그림 영역 표식(\x10파일|폭|높이\x0e글자\x11)은 요지 키를 만들 때 안의 글자만 남긴다(그림 넣기 전과 같은 키)
    pl = lambda s: re.sub(r'[\x01-\x04\s]', '', re.sub(r'\x10[^\x0e]*\x0e([^\x11]*)\x11', r'\1', s))[:60]
    byhead = {}
    for k, g in GK['blk'].items(): byhead.setdefault(k.rsplit('|', 1)[0], []).append(g)
    miss = 0
    for n, v in out.items():
        if n in GK['cur']: v['curg'] = GK['cur'][n]
        for x in v['blocks']:
            hk = n + '|' + x['head'] + '|' + x.get('scope', '')
            g = GK['blk'].get(hk + '|' + pl(x['text']))
            if not g and len(byhead.get(hk, [])) == 1: g = byhead[hk][0]   # 그림 때문에 앞부분 글자가 달라진 블록
            if not g and hk in byhead:   # 같은 제목 블록이 여럿이면 앞부분 글자가 가장 비슷한 것
                import difflib
                cands = [(difflib.SequenceMatcher(None, k.rsplit('|', 1)[1], pl(x['text'])).ratio(), gg) for k, gg in GK['blk'].items() if k.rsplit('|', 1)[0] == hk]
                best = max(cands, key=lambda c: c[0])
                if best[0] >= 0.5: g = best[1]
            if g: x['g'] = g
            elif hk in byhead: miss += 1
    print('gist misses', miss)
json.dump(out, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
print(len(out), 'clauses', sum(len(v['blocks']) for v in out.values()), 'blocks')
