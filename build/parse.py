import re, json, sys

# ---------- 별표24 ----------
def parse_b24(path):
    lines = open(path, encoding='utf-8').read().split('\n')
    entries = []
    cur = None
    seen_nums = set()
    parents = {}  # heading number -> title, for context
    clause_re = re.compile(r'^\s{0,2}((?:[ⅠⅡⅢⅣⅤⅥⅦⅧ]\.)?\d+(?:\.\d+)*)\s+(\S.*)$')
    annex_re = re.compile(r'^\s*부속서\s+([ⅠⅡⅢⅣⅤⅥⅦⅧ])\s*$')
    footer_re = re.compile(r'^\s*-\s*\d+\s*-\s*$')
    annex = None
    for ln in lines:
        if footer_re.match(ln) or ln.startswith('\f'):
            continue
        ln = ln.replace('\f', '')
        m = annex_re.match(ln)
        if m:
            annex = m.group(1)
            cur = {'num': '부속서 ' + annex, 'title': '', 'body': []}
            entries.append(cur)
            continue
        m = clause_re.match(ln)
        if m:
            num, rest = m.group(1), m.group(2).strip()
            # skip things like "1 장애물(기둥 등)" inside figures? keep anyway but need digits sanity
            # avoid matching table rows like "0.50 ㎧ ..." : require num not containing '.' followed by digits only pattern like 0.50
            unit_start = re.match(r'^(㎜|mm|㎝|cm|㎠|㎨|㎧|㎐|㎏|kg|kN|N|%|°|m|m/s|㎡|㎥|㎞|km|lx|Ω|V|A|J|Hz|㎏f|kgf)(?![A-Za-z])|^(및|이상|이하|초과|미만|의|를|을|과|와|에|로|참조|배|개|초|분|회|년|월|일|도|번|호|항|목|조|대|명|개소|단)(?![가-힣A-Za-z])', rest)
            if re.match(r'^0\.', num) or unit_start or (cur is not None and num in seen_nums):
                if cur is not None: cur['body'].append(ln.strip())
                continue
            seen_nums.add(num)
            # heading-only line (short, no sentence end) -> record as parent
            cur = {'num': num, 'title': rest, 'body': []}
            entries.append(cur)
            continue
        if cur is not None:
            s = ln.strip()
            if s:
                cur['body'].append(s)
    out = []
    # drop applicability-table rows (duplicate clause numbers with ○/× marks)
    seen = set(); kept = []
    for e in entries:
        if e['num'] in seen or ('○' in e['title'] or '×' in e['title']):
            continue
        seen.add(e['num']); kept.append(e)
    entries = kept
    # build parent titles
    titles = {}
    for e in entries:
        titles.setdefault(e['num'], e['title'])
    for e in entries:
        num = e['num']
        body = smart_join(e['body'])
        title = e['title']
        # if title is a sentence (long), the clause has no heading: title is text
        is_heading = len(title) <= 30 and not title.endswith('.') and not title.endswith('다')
        text = (title + ' ' + body).strip() if not is_heading else body
        # parent chain
        chain = []
        parts = num.split('.')
        for i in range(1, len(parts)):
            p = '.'.join(parts[:i])
            if p in titles and titles[p] and len(titles[p]) <= 30:
                chain.append(f'{p} {titles[p]}')
        if annex_of(num) and ('부속서 ' + annex_of(num)) in titles:
            chain.insert(0, '부속서 ' + annex_of(num))
        out.append({
            'src': 'b24',
            'id': 'b24-' + num,
            'num': num,
            'title': title if is_heading else '',
            'path': ' › '.join(chain),
            'text': text,
        })
    return [o for o in out if o['text'] or o['title']]

def dw(s):
    return sum(2 if ord(c) > 0x2000 else 1 for c in s)

def smart_join(lines):
    out = ''
    for s in lines:
        if not out:
            out = s; continue
        if re.match(r'^([가-하]\)|\d{1,2}\)|[①-⑳]|비고\b|주\)|－|-\s)', s):
            out += '\n' + s
        elif re.search(r'[가-힣]$', out) and re.match(r'^[가-힣]', s) and dw(out.split('\n')[-1]) >= 66 and not out.endswith(('다', '한다', '.')):
            out += s
        else:
            out += ' ' + s
    return out

def annex_of(num):
    m = re.match(r'^([ⅠⅡⅢⅣⅤⅥⅦⅧ])\.', num)
    return m.group(1) if m else None

# ---------- 표준화 ----------
class Body(list):
    """본문 줄 + 각 줄의 원문 줄 번호(LI)"""
    def __init__(s): super().__init__(); s.li = []
    def append(s, x): super().append(x); s.li.append(CURLI[0])
CURLI = [0]

def parse_std(path):
    lines = open(path, encoding='utf-8').read().split('\n')
    # 회차 머리: '2016년 [1차]_검사방법', '2017년 1차_검사기준', '2017년 제 3차 검사기준 [7차]', '2017년 제9차 [전산]', '18년 기술자문 간담회…', '2017년 기타' 등
    # '2023년 1차에 변동 됨', '2024년 1차에 표준화 있음' 같은 주석 줄은 제외
    hdr_re = re.compile(r'^\s*((?:20)?\d{2}년\s*(?:\[\d+차\]|제\s*\d+차(?!에)|\d+차_|기타\s*$|기술자문).*)$')
    item_re = re.compile(r'^\s*(\d{1,3})\s+(\S.*)$')
    session = None
    items = []
    cur = None
    toc = None
    i = 0
    # skip personal header block (first ~22 lines until first year header)
    start = 0
    for idx, ln in enumerate(lines):
        if hdr_re.match(ln):
            start = idx; break
    prev_hdr = False
    pending_num = None
    bare = None
    # 같은 회차에서 번호가 겹치는 안건('3 문턱간 …' 다음 '3 [기타안건]…')은 제목으로 구분한다.
    # 쪽마다 되풀이되는 안건 머리 줄은 파일에 여러 번 나오므로, 그런 줄이나 '[…]'로 시작하는 줄만 새 안건으로 본다
    import collections
    LINECNT = collections.Counter(re.sub(r'\s+', '', l) for l in lines)
    tn = lambda t: re.sub(r'[\W_]', '', t.lstrip('‣▪ '))[:10]
    # 회차 안의 묶음 머리 줄(번호 없음): 이 뒤의 번호 줄은 정규 안건과 번호가 겹쳐도 별도 안건
    SUBHDR = [(re.compile(r'^(?:□\s*|-\s*)?\[?기타안건\]?(?:\s|\[|$)'), '[기타안건] '),
              (re.compile(r'^기타$'), '[기타] '),
              (re.compile(r'^제\s*\d+차\s*기술서류\s*업무\s*표준화'), '§'),
              (re.compile(r'^(?:승강기 |제\s*\d+차 .*)?기술자문\s*간담회.{0,30}$'), '§')]
    sub = None; lastcur = None; subraw = None
    COLHDR = re.compile(r'^NO\s*(?:검사업무\s*표준화\(기\s*회신\)\s*검사업무\s*표준화\(변경\)|의견\s*협의내용\s*및\s*결과)$')
    import os
    GEO0 = {int(k): v for k, v in json.load(open('std_geo.json')).items()} if os.path.exists('std_geo.json') else {}
    toprow = lambda li: 55 <= GEO0.get(li, [0, 999])[1] <= 100   # 슬라이드 맨 위 제목 자리
    for LI, ln in enumerate(lines[start:], start):
        CURLI[0] = LI
        s = ln.replace('\f', '').strip()
        if not s:
            continue
        m = hdr_re.match(s)
        if m and LI in GEO0 and abs(GEO0[LI][2] - 36.4) > 3: m = None   # 회차 머리는 슬라이드 왼쪽 띠(x≈36)에만 — 본문 속 '23년 제4차 … 수정' 같은 줄은 아님
        if m and len(s) < 90:
            if m.group(1).strip() != session: sub = None; subraw = None   # 회차가 바뀌면 묶음(기타안건 등)도 끝
            session = m.group(1).strip()
            prev_hdr = True
            if cur is not None: lastcur = cur
            cur = None
            continue
        # 쪽마다 되풀이되는 표의 칸 머리 줄('NO 검사업무 표준화(기 회신) 검사업무 표준화(변경)', 'NO 의견 협의내용 및 결과')은 본문이 아님
        if COLHDR.match(s): continue
        s = re.sub(r'^NO\s+의견\s+(?=▪)', '', s)
        if re.match(r'^\d{1,3}$', s):
            if bare is not None and cur is not None:
                cur['body'].append(bare)
            bare = s
            g_ = GEO0.get(LI, [])
            bignum = len(g_) > 3 and g_[3] >= 12 and g_[2] < 50   # 슬라이드 왼쪽 큰 번호(14pt) = 안건 번호
            if prev_hdr or bignum: pending_num = s; bare = None
            prev_hdr = False
            continue
        prev_hdr = False
        if len(s) < 70:
            sh = next((t for r_, t in SUBHDR if r_.match(s)), None)
            if sh:
                # 목차 속 '[기타안건]' 같은 줄은 제외: 바로 뒤(회차 머리 줄은 건너뜀)가 번호 줄이어야 묶음 머리
                nx = next((l.strip() for l in lines[LI + 1:LI + 6] if l.strip() and not hdr_re.match(l.strip())), '')
                if not re.match(r'^\d{1,3}(\s|$)', nx): sh = None
            elif any(r_.match(s) for r_, t in SUBHDR if t == '§'):
                continue   # '…기술자문 간담회(4차)' 같은 묶음 머리 줄은 본문에 넣지 않음
            if sh:
                sub = sh; subraw = s
                if cur is not None: lastcur = cur
                cur = None
                continue
        forced = False
        if pending_num and not re.search(r'[가-힣A-Za-z]{2}', s):
            # 왼쪽 세로 글자 칸('ISO/P RF 8100- 1 :2023')의 숫자 줄은 안건 번호가 아니다
            if cur is not None: cur['body'].append(pending_num)
            pending_num = None
        if pending_num:
            s = pending_num + ' ' + s
            pending_num = None
            forced = True
        elif bare is not None:
            if s.startswith(('‣', '▪')):
                s = bare + ' ' + s; forced = True
            elif cur is not None:
                cur['body'].append(bare)
            bare = None
        if s.startswith('구분 ') and LI > 0 and re.match(r'^No\.\s*20\d\d-\d+', lines[LI - 1].strip()):
            # '표준화 시트'(No. 2022-0011 / 구분 안건명) 쪽: 같은 회차의 같은 이름 안건 본문
            tt = tn(s[3:])
            tgt = next((it for it in items if it['key'][:1] == (session,) and it['key'][1] != 'toc' and tn(re.sub(r'^\[[^\]]*\]\s*', '', it['title'])) == tt), None)
            if tgt is not None:
                if cur is not None and cur['body'] and re.match(r'^No\.\s*20\d\d-\d+', cur['body'][-1]):
                    cur['body'].pop(); cur['body'].li.pop()
                if cur is not None: lastcur = cur
                cur = tgt; tgt['hli'].append(LI); continue
        m = item_re.match(s)
        if m and session and len(m.group(2)) > 3 and (forced or (not re.match(r'^\d', m.group(2)) and not re.match(r'^(㎜|mm|m|%|㎏|kg|N|개|명|회|층|대|초|분|년|월|일|㎧|Ω|°|V|A|㎞|㎝|cm|㎡|㎥|lx|조|항|호|목|또는|및|이상|이하|미만|초과|이내|배|단|개소)(?![가-힣A-Za-z])', m.group(2)))):
            num, title = m.group(1), m.group(2).strip()
            small = len(GEO0.get(LI, [])) > 3 and GEO0[LI][3] < 9.5   # 9pt 이하 작은 글자(표 안의 번호 칸)는 안건 머리가 아니다
            if small or (not forced and (int(num) > 60 or re.search(r'\d+\.\d+(?:\.\d+)+\s+\d+\.\d+', title))):
                # '300 N의 힘을…'(문장), '7 자동구출운전수단 13.2.3.6 1.3.1.7'(표의 행)은 안건 머리가 아니다
                tgt = cur if cur is not None else lastcur
                if tgt is not None: tgt['body'].append(s); cur = tgt
                continue
            same = [it for it in items if it['key'][:2] == (session, num)]
            found = next((it for it in same if it['key'][2] == tn(title)), None)
            if found:
                cur = found   # 쪽 넘김으로 되풀이된 안건 머리
                found['hli'].append(LI)
                if not found.get('sub'): sub = None
                continue
            if same and not sub and not (forced or title.lstrip('‣▪ ').startswith('[') or LINECNT[re.sub(r'\s+', '', s)] >= 2 or toprow(LI)):
                # 번호가 겹치는데 안건 머리 같지 않은 줄(표의 행, 번호 목록, 줄바꿈된 문장) → 지금 안건의 본문
                tgt = cur if cur is not None else lastcur
                if tgt is not None: tgt['body'].append(s); cur = tgt
                continue
            key = (session, num, tn(title))
            t0 = title.lstrip('‣▪ ').strip()
            cur = {'key': key, 'session': session, 'num': num, 'title': (sub + t0) if sub and sub != '§' and not t0.startswith('[') else t0, 'body': Body(), 'sub': sub, 'subraw': subraw if sub else None, 'hli': [LI]}
            items.append(cur)
            continue
        if s.startswith('❏'):
            # TOC bullets under a session
            key = (session, 'toc')
            found = None
            for it in items:
                if it['key'] == key:
                    found = it; break
            if not found:
                found = {'key': key, 'session': session, 'num': '', 'title': '목차', 'body': Body(), 'hli': []}
                items.append(found)
            found['body'].append(s)
            if cur and cur['key'] != key:
                pass
            continue
        if cur is not None:
            cur['body'].append(s)
        elif session:
            key = (session, 'toc')
            found = next((it for it in items if it['key'] == key), None)
            if not found:
                found = {'key': key, 'session': session, 'num': '', 'title': '목차', 'body': Body(), 'hli': []}
                items.append(found)
            found['body'].append(s)
    out = []
    import os
    IDS = json.load(open('std_ids.json')) if os.path.exists('std_ids.json') else {}
    used = set(IDS.values()); nxt = max([int(v.split('-')[1]) for v in used] + [-1]) + 1
    # ---- 쪽 배치로 본문 주인 다시 정하기: 슬라이드의 각 줄은 같은 쪽에서 그 줄 위에 있는 가장 가까운 안건 머리의 것
    # (본문 속 번호 줄·표가 텍스트 추출 순서 때문에 다른 안건 뒤에 붙던 문제 해결). 쪽 위치는 stdgeo.py → std_geo.json
    import os
    if os.path.exists('std_geo.json'):
        GEO = {int(k): v for k, v in json.load(open('std_geo.json')).items()}
        # 목차 쪽: '1. 안건명' 목록이 3줄 이상이고 '[…]' 묶음 머리나 ❏ 가 있는 쪽 → 그 쪽의 머리 인식은 무시, 글은 회차 목차로
        bypage = {}
        for li_, g_ in GEO.items(): bypage.setdefault(g_[0], []).append(li_)
        TOCPG = set()
        for pg_, lis in bypage.items():
            ts = [lines[i].strip() for i in lis]
            listy = sum(1 for t in ts if re.match(r'^\d{1,2}\.?\s*\S', t) and len(t) < 70 or t.startswith('❏') or re.match(r'^\[[^\]]+\]\s*$', t) or hdr_re.match(t))
            if sum(1 for t in ts if re.match(r'^\d{1,2}\.\s*\S', t)) >= 3 and any(re.match(r'^\[[^\]]*(안건|질의|답변|기타사항|표준화)[^\]]*\]\s*$', t) for t in ts) and listy >= 0.7 * len(ts):
                TOCPG.add(pg_)
        for it in items:
            if it.get('hli'): it['hli'] = [h for h in it['hli'] if GEO.get(h, [None])[0] not in TOCPG]
        # 같은 회차의 표지 머리('…협의 결과 2026. 3.')와 쪽 머리('…협의 결과 2026. 3. 26.')는 날짜 꼬리만 다르다
        sesskey = lambda s_: re.sub(r'[\s_]|(\d{4}\.\s*\d{1,2}\.\s*(\d{1,2}\.)?|\d{1,2}\.\s*\d{1,2}\.)\s*$', '', re.sub(r'[\s_]*(\d{4}\.\s*)?\d{1,2}\.\s*(\d{1,2}\.|00\.)?\s*$', '', s_.replace('협의체', '협의')))
        tocmv = 0
        for it in list(items):
            if it['key'][1] == 'toc' or not isinstance(it['body'], Body): continue
            if not any(GEO.get(l, [None])[0] in TOCPG for l in it['body'].li): continue
            toc = next((x for x in items if x['key'] == (it['session'], 'toc')), None)
            if toc is None:
                toc = {'key': (it['session'], 'toc'), 'session': it['session'], 'num': '', 'title': '목차', 'body': Body(), 'hli': []}
                items.insert(items.index(it), toc)
            b = Body()
            for t, l in zip(it['body'], it['body'].li):
                if GEO.get(l, [None])[0] in TOCPG: list.append(toc['body'], t); toc['body'].li.append(l); tocmv += 1
                else: list.append(b, t); b.li.append(l)
            it['body'] = b
        print('toc pages', len(TOCPG), 'lines to toc', tocmv)
        heads = []   # (page, y, LI, item)
        for it in items:
            if it['key'][1] == 'toc': continue
            for h in it.get('hli', []):
                if h in GEO: heads.append((GEO[h][0], GEO[h][1], h, id(it), it))
        heads.sort(key=lambda x: (x[0], x[1], x[2]))
        hkeys = [(h[0], h[1] - 8) for h in heads]   # 머리 줄과 같은 높이(번호·제목이 나란히, 몇 pt 위)도 그 안건
        import bisect
        moves = []
        for it in items:
            if it['key'][1] == 'toc' or not isinstance(it['body'], Body): continue
            for k, (txt, li) in enumerate(zip(it['body'], it['body'].li)):
                if li not in GEO: continue
                pg, y = GEO[li][:2]
                j = bisect.bisect_right(hkeys, (pg, y)) - 1
                if j < 0: continue
                own = heads[j][4]
                # 머리가 원문 줄 순서상 이 줄보다 뒤에 있는 같은 쪽 안건이면(제목 줄 위 장식 등) 건드리지 않음
                if own is not it: moves.append((it, k, own))
        # 회차 머리 줄(쪽마다 되풀이)이 쪽 중간에서 읽히면 그 뒤 본문이 회차 목차로 빠졌다 → 목차 쪽이 아닌 줄은
        # 같은 회차에서 그 줄 위(앞 쪽 포함)의 가장 가까운 안건 머리 것으로 (머리 없는 이어지는 쪽·참고자료 쪽은 앞 안건에 붙음)
        for it in items:
            if it['key'][1] != 'toc' or not isinstance(it['body'], Body): continue
            for k, (txt, li) in enumerate(zip(it['body'], it['body'].li)):
                if li not in GEO or GEO[li][0] in TOCPG or txt.startswith('❏') or any(r_.match(txt) for r_, _ in SUBHDR): continue
                pg, y = GEO[li][:2]
                j = bisect.bisect_right(hkeys, (pg, y)) - 1
                if j < 0 or sesskey(heads[j][4]['session']) != sesskey(it['session']): continue
                moves.append((it, k, heads[j][4]))
        take = {}
        for it, k, own in moves: take.setdefault(id(it), set()).add(k)
        for it, k, own in moves:
            own['body'].append(it['body'][k]); own['body'].li[-1] = it['body'].li[k]
        for it in items:
            ks = take.get(id(it))
            if ks:
                keep = [(t, l) for i_, (t, l) in enumerate(zip(it['body'], it['body'].li)) if i_ not in ks]
                b = Body(); b.extend([]); 
                for t, l in keep: list.append(b, t); b.li.append(l)
                it['body'] = b
        for it in items:   # 원문 순서대로
            if isinstance(it['body'], Body) and it['body']:
                pairs = sorted(zip(it['body'].li, range(len(it['body'])), it['body']))
                b = Body()
                for l, _, t in pairs: list.append(b, t); b.li.append(l)
                it['body'] = b
        print('geo moves', len(moves))
        # 안건 첫 머리 줄보다 앞선 줄(목차 쪽 글 등)은 그 회차 목차로
        pre = 0
        for it in list(items):
            if it['key'][1] == 'toc' or not it.get('hli') or not isinstance(it['body'], Body): continue
            h0 = min(it['hli'])
            if not any(l < h0 for l in it['body'].li): continue
            toc = next((x for x in items if x['key'] == (it['session'], 'toc')), None)
            if toc is None:
                toc = {'key': (it['session'], 'toc'), 'session': it['session'], 'num': '', 'title': '목차', 'body': Body(), 'hli': []}
                items.insert(items.index(it), toc)
            b = Body()
            for t, l in zip(it['body'], it['body'].li):
                if l < h0: list.append(toc['body'], t); toc['body'].li.append(l); pre += 1
                else: list.append(b, t); b.li.append(l)
            it['body'] = b
        print('pre-header lines to toc', pre)
        import collections
        C = collections.Counter((a['session'][:12] + ' ' + a['num'] + ' ' + a['title'][:22], o['session'][:12] + ' ' + o['num'] + ' ' + o['title'][:22]) for a, k, o in moves)
        json.dump([[a, b, c] for (a, b), c in C.most_common()], open('geo_moves.json', 'w'), ensure_ascii=False, indent=0)
    # 원문 확인으로 찾은 '안건처럼 보이는 본문 줄'(표의 행·인용 조문·쪽 머리 참고문) → 바로 앞 안건 본문으로 합침
    NOTITEM = [('18년 기술자문 간담회(2차)', '1', '다음의 부품을 제외한'), ('2026년 제1차', '4', '안전 요건'), ('20년 제 3차 표준화', None, '참고 장애인등 편의법')]
    for sess_, num_, t_ in NOTITEM * 4:   # 같은 줄이 여러 쪽에 되풀이될 수 있음
        for k, it in enumerate(items):
            if it['session'].startswith(sess_) and num_ in (None, it['num']) and it['title'].startswith(t_):
                prev = next((items[j] for j in range(k - 1, -1, -1) if items[j]['session'] == it['session'] and items[j]['key'][1] != 'toc'), None)
                if prev is not None and isinstance(prev['body'], Body) and isinstance(it['body'], Body):
                    list.append(prev['body'], (it['num'] + ' ' + it['title'])); prev['body'].li.append(min(it.get('hli') or [0]))
                    for t2, l2 in zip(it['body'], it['body'].li): list.append(prev['body'], t2); prev['body'].li.append(l2)
                    pairs = sorted(zip(prev['body'].li, range(len(prev['body'])), prev['body'])); nb = Body()
                    for l2, _, t2 in pairs: list.append(nb, t2); nb.li.append(l2)
                    prev['body'] = nb
                    items.pop(k)
                break
    # 일반적인 제목('주요내용(현안)', '(전산개발 내용)', '「…간담회 안건」')은 본문 첫 줄의 실제 안건명으로
    for it in items:
        t = it['title']
        if not it['body'] or not re.match(r'^(주요내용\(현안\)|\(전산개발 내용\)|「[^」]*안건」)$', t.strip()): continue
        head = it['body'][0].strip()
        if re.fullmatch(r'\d+\.\s*현안사항\s*', head) and len(it['body']) > 1: head = it['body'][1].strip()
        head = re.sub(r'^\d+\.\s*(현안사항)?\s*[:：]?\s*', '', head)
        head = re.sub(r'^[:：]\s*', '', head)
        head = re.sub(r'^[‣▪▸\-\s]+', '', head)
        head = re.split(r'\s+(?:\d+\.\s|\[관련|협의|-\s)', head)[0].strip()[:60]
        if len(head) < 4: continue
        it['_ot'] = t
        if t.startswith('「'): it['title'] = f'{head} ({t.strip("「」")})'
        elif t.startswith('(전산'): it['title'] = f'[전산개발] {head}'
        else: it['title'] = head
    TAGONLY = re.compile(r'^[\[(]?\s*(차기 표준화 회의 시 재-협의|기타안건|제외안건|협의제외|질의답변|기타사항|안내|검토의견)\s*[\])]?\s*(\[[^\]]*\])?\s*$')
    items = [it for it in items if it['body'] or it['key'][1] == 'toc' or it['num'] == '']
    for n, it in enumerate(items):
        if TAGONLY.match(it['title']) and it['body']:
            # '(기타안건) [주요내용은 …]' 처럼 꼬리표뿐인 제목은 다음 줄(실제 안건명)을 붙인다
            tag = TAGONLY.match(it['title']).group(1)
            li_ = list(getattr(it['body'], 'li', []))[1:]
            it['title'] = f'[{tag}] ' + it['body'][0].strip(); it['body'] = it['body'][1:]
            if li_: it['_li1'] = li_
        it['sec'] = sectionize(it['body'])
        year = re.match(r'^(20)?(\d{2})년', it['session'])
        y = ('20' + year.group(2)) if year else ''
        out.append({
            'src': 'std',
            'id': None,
            'num': it['num'],
            'title': it['title'],
            'path': it['session'],
            '_sub': it.get('subraw'),
            **({'_ot': it['_ot']} if it.get('_ot') else {}),
            'year': y,
            'text': '\n'.join(it['body']),
            'sec': it['sec'],
            '_li': (it.get('_li1') or list(getattr(it['body'], 'li', []))) if it['body'] else [None],
            '_hli': list(it.get('hli', [])),
        })
    # 안건 id 는 회차|번호|제목으로 고정(그림·요지가 id 로 연결되어 있으므로). 새 안건만 새 번호
    for o in out:
        k = f"{o['path']}|{o['num']}|{o['title']}"
        if k not in IDS:
            IDS[k] = f'std-{nxt}'; nxt += 1
        o['id'] = IDS[k]
    # 묶음(기술서류 표준화·간담회 n차·기타) 안의 안건은 회차 이름에 묶음 이름을 덧붙여 구분(목차에서 따로 보이게)
    for o in out:
        sr = o.pop('_sub', None)
        if sr:
            sr = re.sub(r'^[□\-\s]+|\[주요내용[^\]]*\]|\[단순안내[^\]]*\]?', '', sr).strip(' []')
            if sr and sr not in o['path']: o['path'] = o['path'] + ' · ' + sr
    # 본문 줄마다 원문 줄 번호(_li)를 std_fix 단계 내내 같이 옮긴다 → std_li.json (그림 주인 정하기·원문 순서 복원용)
    for o in out: assert len(o['_li']) == len(o['text'].split('\n')), o['id']
    heads0 = {o['id']: o.pop('_hli') for o in out}
    out = apply_fix(out, IDS, lambda: None)
    # 슬라이드 맨 위 제목 띠(x≈36, y<50)의 줄('배포자료', '기타', '…재안내' 같은 쪽 제목 둘째 줄)은 본문이 아님
    # (std_fix 의 자르기 기준으로 쓰일 수 있어 std_fix 다음에 뺀다)
    G0 = {int(k): v for k, v in json.load(open('std_geo.json')).items()}
    band = lambda l: l is not None and l in G0 and G0[l][1] < 50 and abs(G0[l][2] - 36.4) < 3
    for o in out:
        tl = o['text'].split('\n')
        if any(band(l) for l in o['_li']):
            keep = [(t, l) for t, l in zip(tl, o['_li']) if not band(l)]
            o['text'] = '\n'.join(t for t, _ in keep); o['_li'] = [l for _, l in keep]
            o['sec'] = sectionize([t for t, _ in keep])
    LI_OUT = {}
    for o in out:
        lis = o.pop('_li')
        LI_OUT[o['id']] = sorted(set(list(heads0.get(o['id'], [])) + [l_ for l_ in lis if l_ is not None]))
        # std_fix 로 옮기거나 합친 안건은 원문 순서대로 다시 늘어놓는다(덧붙인 블록이 맨 뒤에 몰리지 않게)
        pr = [(l_, k, s_) for k, (l_, s_) in enumerate(zip(lis, o['text'].split('\n'))) if s_.strip() or l_ is not None]
        if o['id'] in FIX_TOUCHED and all(l_ is not None for l_, _, _ in pr):
            ls_ = sorted(pr)
            nt = '\n'.join(s_ for _, _, s_ in ls_)
            if nt != o['text']: o['text'] = nt; o['sec'] = sectionize(nt.split('\n'))
    json.dump(LI_OUT, open('std_li.json', 'w'))
    json.dump(IDS, open('std_ids.json', 'w'), ensure_ascii=False, indent=0)
    return out

FIX_TOUCHED = set()
def apply_fix(out, IDS, _):
    """원문 검토로 찾은 개별 수정(std_fix.json): 섞인 블록 떼어내기·새 안건 만들기·합치기·제목/회차 고치기"""
    import os
    if not os.path.exists('std_fix.json'): return out
    F = json.load(open('std_fix.json', encoding='utf-8'))
    byid = {o['id']: o for o in out}
    nxt = max(int(v.split('-')[1]) for v in IDS.values()) + 1
    touched = set(); log = []
    def L(o): return o['text'].split('\n')
    for c in F.get('cut', []):
        o = byid.get(c['id'])
        if not o: log.append('no ' + c['id']); continue
        ls = L(o); st = [x.strip() for x in ls]; li = o['_li']
        if c['first'].strip() not in st: log.append('nofirst ' + c['id']); continue
        i = st.index(c['first'].strip())
        j = len(ls) - 1 if not c['last'] else next((k for k in range(i, len(ls)) if st[k] == c['last'].strip()), None)
        if j is None: log.append('nolast ' + c['id']); continue
        block = ls[i:j + 1]; o['text'] = '\n'.join(ls[:i] + ls[j + 1:]); touched.add(o['id'])
        bli = li[i:j + 1]; o['_li'] = li[:i] + li[j + 1:]
        if c['to'] == 'drop': continue
        if c['to'] != 'new':
            t = byid[c['to']]; t['text'] = t['text'] + '\n' + '\n'.join(block); t['_li'] = t['_li'] + bli; touched.add(t['id']); continue
        parts = [block]; plis = [bli]
        if c.get('split_at'):
            bs = [x.strip() for x in block]; k = bs.index(c['split_at'].strip()); parts = [block[:k], block[k:]]; plis = [bli[:k], bli[k:]]
        pos = out.index(o)
        for n_, (part, pli, spec) in enumerate(zip(parts, plis, c['new'])):
            ot = re.sub(r'^\d+\s*[▪‣]?\s*', '', part[0].strip()) if part else spec['title']   # 그림 위치 찾기용 원문 첫 줄
            if part and spec['num'] and part[0].strip().startswith(spec['num'] + ' '): part = part[1:]; pli = pli[1:]
            key = f"{o['path']}|{spec['num']}|{spec['title']}"
            if key not in IDS: IDS[key] = f'std-{nxt}'; nxt += 1
            no = dict(o, id=IDS[key], num=spec['num'], title=spec['title'], text='\n'.join(part), _ot=ot, _li=list(pli))
            out.insert(pos + 1 + n_, no); byid[no['id']] = no; touched.add(no['id'])
    for m in F.get('merge', []):
        a, b = byid.get(m['from']), byid.get(m['into'])
        if not a or not b: log.append('nomerge ' + m['from']); continue
        b['text'] = b['text'] + '\n' + a['text']; b['_li'] = b['_li'] + a['_li']; out.remove(a); touched.add(b['id'])
    for i, t in F.get('title', {}).items():
        if i in byid: byid[i].setdefault('_ot', byid[i]['title']); byid[i]['title'] = t
    for i in F.get('dropfirst', []):
        if i in byid:
            ls = L(byid[i]); byid[i]['text'] = '\n'.join(ls[1:]); byid[i]['_li'] = byid[i]['_li'][1:]; touched.add(i)
    for i, pth in F.get('path', {}).items():
        if i in byid: byid[i]['path'] = pth
    for o in out:
        if o['id'] in touched: o['sec'] = sectionize([x for x in o['text'].split('\n')])
    FIX_TOUCHED.update(touched)
    print('std_fix applied', len(touched), 'items', log)
    return out

LABELS = {'목적/배경':'목적·배경','목적배경':'목적·배경','배경':'배경','관련법령/고시':'관련 법령·고시','관련법령':'관련 법령','관련법령고시':'관련 법령·고시',
 '관련기준':'관련 기준','관련규정':'관련 규정','적용':'적용','적용방안':'적용 방안','적용방법':'적용 방법','비고':'비고','안건':'안건','검토의견':'검토의견','검토결과':'검토 결과',
 '협의내용및결과':'협의내용 및 결과','협의내용':'협의내용','협의결과':'협의 결과','검사기준':'검사기준','표준화':'표준화','업무처리':'업무처리','업무처리방안':'업무처리 방안',
 '참고자료':'참고자료','참고':'참고','검사방법':'검사방법','검사방법표준화':'검사방법 표준화','내용':'내용','결과':'결과','질의':'질의','답변':'답변','회신':'회신','현황':'현황',
 '문제점':'문제점','개선방안':'개선방안','조치사항':'조치사항','조치':'조치','검토내용':'검토내용','사유':'사유','기준':'기준','해석':'해석','의견':'의견','요청사항':'요청사항',
 '건의사항':'건의사항','변경사항':'변경사항','변경내용':'변경내용','주요내용':'주요내용','안내':'안내','안내사항':'안내사항','적용시점':'적용 시점','시행일':'시행일','참고사항':'참고사항'}
BUL = re.compile(r'^([ⅠⅡⅢⅣⅤⅥⅦⅧ]\.\d|\d+\.\d+(\.\d+)*\s|ㅇ|○|▪|▫|‣|•|·|-|–|―|◆|◇|※|□|■|★|☆|→|⇒|[①-⑳]|\(?\d{1,2}[.)]|\(?[가-하][.)]|\(?[a-zA-Z][.)]|「|\[|<|예\)|\*)')

def sectionize(lines):
    secs = []; cur = {'h': '', 'p': []}
    i = 0; n = len(lines)
    while i < n:
        hit = None
        for k in (4, 3, 2, 1):
            if i + k <= n:
                j = ''.join(lines[i:i+k]).replace(' ', '').strip('<>[]:：/ ')
                if j in LABELS and all(len(x) <= 12 for x in lines[i:i+k]):
                    hit = (LABELS[j], k); break
        if not hit:
            s = lines[i].strip()
            m = re.match(r'^[<\[]\s*([^<>\[\]]{2,20})\s*[>\]]\s*$', s)
            if m: hit = (m.group(1).strip(), 1)
        if hit:
            if cur['p'] or cur['h']: secs.append(cur)
            cur = {'h': hit[0], 'p': []}; i += hit[1]; continue
        s = lines[i].strip()
        if cur['p'] and not BUL.match(s) and not cur['p'][-1].endswith(('.', ':', '：', '함', '음', '됨', '임', '것', '요', '다')):
            cur['p'][-1] += ' ' + s
        elif cur['p'] and not BUL.match(s) and cur['p'][-1].endswith(('.', ':', '：', '함', '음', '됨', '임', '것', '요', '다')) and len(cur['p'][-1]) > 70:
            cur['p'].append(s)
        else:
            cur['p'].append(s)
        i += 1
    if cur['p'] or cur['h']: secs.append(cur)
    return [s for s in secs if s['p']]

if __name__ == '__main__':
    b = parse_b24('b24.txt')
    s = parse_std('insp.txt')
    print(len(b), len(s))
    json.dump({'b24': b, 'std': s}, open('data.json', 'w', encoding='utf-8'), ensure_ascii=False)
