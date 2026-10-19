import json,sys,re
sys.path.insert(0,'.')
from classes import C
import os; os.chdir(os.path.dirname(os.path.abspath(__file__))); B='../build/'
b22={e['num']:e for e in json.load(open(B+'base_el.json'))}
def clause_txt(n):
    e=b22.get(n); 
    if not e: return None
    # 하위 조항까지 포함
    t=' '.join((x.get('title') or '')+' '+x['text'] for k,x in b22.items() if k==n or k.startswith(n+'.'))
    return (e.get('path') or '')+' '+t
for key,ko,loc,al,refs in C:
    for r in refs:
        t=clause_txt(r)
        if t is None: print('NO CLAUSE',key,r); continue
        if not any(a.lower() in t.lower() for a in al): print('ALIAS NOT IN',key,r,(b22[r].get('title') or b22[r]['text'][:40]))
