"""검사기준 통합검색 데이터·페이지 빌드 (build/ 폴더에서 실행: python build.py [--images])
1) stdgeo.py    : 표준화 PDF 각 줄의 쪽·위치 → std_geo.json (없을 때만)
2) parse.py     : 표준화(insp.txt) 안건 나누기 → data.json (std_fix.json 개별 수정, std_ids.json id 고정)
   --images     : std_images.py 로 표준화 그림을 다시 잘라 stdimg/ · stdimg.json 갱신(안건 나눔이 바뀌었을 때)
3) hist_parse.py / hist_merge.py : 승강기 안전기준 연혁집 PDF(엘리베이터·에스컬레이터) 하나로
   현행 조문 목록·본문(base_el.json·base_es.json) + 조문별 적용 연혁. 그림·표·분수식은 원문 영역을 잘라 fig/hel_*, fig/hes_*
   (별표22·24 HWP 는 쓰지 않는다)
4) template.html 에 데이터를 넣어 app_pkg/kijun.html 생성 → publish.py 가 저장소 루트 index.html 로 복사
"""
import json, subprocess, sys, re, os
if not sys.flags.utf8_mode:   # 윈도우 기본 인코딩(cp949) 대신 UTF-8 로 다시 실행
    sys.exit(subprocess.call([sys.executable, '-X', 'utf8'] + sys.argv))
os.chdir(os.path.dirname(os.path.abspath(__file__)))
PY = [sys.executable, '-X', 'utf8', '-I']   # 윈도우에서도 UTF-8 로 읽고 쓰기
os.makedirs('app_pkg', exist_ok=True); os.makedirs('fig', exist_ok=True)
if not os.path.exists('std_geo.json'):
    subprocess.run(PY + ['stdgeo.py'], check=True)
subprocess.run(PY + ['parse.py'], check=True)                     # 표준화(std) 파싱
if '--images' in sys.argv:
    subprocess.run(PY + ['std_images.py'], check=True)
d = json.load(open('data.json', encoding='utf-8')); g = json.load(open('gists.json', encoding='utf-8'))
for x in d['std']:
    if x['id'] in g: x['gist'] = g[x['id']]
import os
if os.path.exists('stdimg.json'):
    im = json.load(open('stdimg.json'))
    for x in d['std']:
        if x['id'] in im: x['img'] = [[i['f'], i['p'], i['w'], i['h'], 1 if i.get('hand') else 0, 1 if i.get('lo') else 0] for i in im[x['id']]]
import glob
for f in glob.glob('fig/*.webp'): os.remove(f)   # 연혁집 그림 영역은 매번 새로 자른다(예전 HWP 그림 el_*·es_* 도 정리)
for m in ('el', 'es'):   # 승강기 안전기준 연혁집(엘리베이터, 에스컬레이터) PDF → 현행 조문 + 조문별 연혁
    subprocess.run(PY + ['hist_parse.py', m], check=True)
    subprocess.run(PY + ['hist_merge.py', m], check=True)
d['b22'] = json.load(open('base_el.json'))   # 엘리베이터 현행 조문(연혁집)
d['b24'] = json.load(open('base_es.json'))   # 에스컬레이터 현행 조문(연혁집 v2.0)
d.pop('old', None); d.pop('links', None)
d['hist'] = json.load(open('hist_final.json'))   # 엘리베이터 조문번호별 연혁(연혁집)
d['hist_es'] = json.load(open('hist_es_final.json'))   # 에스컬레이터 조문번호별 연혁(연혁집 v2.0)
json.dump(d, open('data.json', 'w', encoding='utf-8'), ensure_ascii=False)
t = open('template.html', encoding='utf-8').read()
s = json.dumps(d, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/')
body = t.replace('__DATA__', s); open('kijun.html', 'w', encoding='utf-8').write(body)
full = '<!doctype html>\n<html lang="ko">\n<head>\n<meta charset="utf-8">\n<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n<style>:root{padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}img{max-width:100%}[hidden]{display:none!important}</style>\n</head>\n<body>\n' + body + '\n</body>\n</html>\n'
open('app_pkg/kijun.html', 'w', encoding='utf-8').write(full)
out = {'b22': [{k: e[k] for k in ('id', 'num', 'title', 'path', 'text')} for e in d['b22'] if e['text'].strip()],
       'b24': [{k: e[k] for k in ('id', 'num', 'title', 'path', 'text')} for e in d['b24'] if e['text'].strip()],
       'std': [{k: e.get(k, '') for k in ('id', 'num', 'title', 'path', 'year', 'gist', 'sec', 'text', 'img')} for e in d['std'] if e['title'] != '목차'],
       'hist': d['hist'], 'hist_es': d['hist_es']}
json.dump(out, open('app_pkg/kijun_data.json', 'w', encoding='utf-8'), ensure_ascii=False)
pua = sum(1 for k in ('b22', 'b24') for e in d[k] for c in e['text'] + e['title'] if 0xe000 <= ord(c) <= 0xf8ff)
print({k: len(v) for k, v in out.items()}, 'PUA left', pua, '[수식] left', sum(e['text'].count('[수식]') for k in ('b22', 'b24') for e in d[k]))
