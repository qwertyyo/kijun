"""한글(HWP) 수식 스크립트 → LaTeX (KaTeX로 화면에 그리기 위함)
HWP 문법: a over b(분수, 왼쪽 피연산자는 바로 앞 한 덩어리), sqrt, root n of x, LEFT ( … RIGHT ),
sum _{} ^{}, _ ^ 첨자, # 줄바꿈, ` ~ 간격, "문자열", TIMES·BULLET·LEQ 등 기호 키워드"""
import re

GREEK = ['alpha', 'beta', 'gamma', 'delta', 'epsilon', 'zeta', 'eta', 'theta', 'iota', 'kappa', 'lambda', 'mu', 'nu', 'xi',
         'omicron', 'pi', 'rho', 'sigma', 'tau', 'upsilon', 'phi', 'chi', 'psi', 'omega']
UPGREEK = {'Gamma', 'Delta', 'Theta', 'Lambda', 'Xi', 'Pi', 'Sigma', 'Upsilon', 'Phi', 'Psi', 'Omega'}
SYM = {'TIMES': r'\times', 'BULLET': r'\cdot', 'CDOT': r'\cdot', 'DIV': r'\div', 'LEQ': r'\le', 'LE': r'\le', 'GEQ': r'\ge',
       'GE': r'\ge', 'NEQ': r'\ne', 'APPROX': r'\approx', 'PM': r'\pm', 'MP': r'\mp', 'INF': r'\infty', 'INFTY': r'\infty',
       'DEG': r'^{\circ}', 'PRIME': r"'", 'CDOTS': r'\cdots', 'LDOTS': r'\ldots', 'SIM': r'\sim', 'PROPTO': r'\propto',
       'PREC': r'\prec', 'SUCC': r'\succ', 'LL': r'\ll', 'GG': r'\gg', 'EQUIV': r'\equiv', 'THEREFORE': r'\therefore',
       'BECAUSE': r'\because', 'ANGLE': r'\angle', 'PARTIAL': r'\partial', 'NABLA': r'\nabla', 'CIRC': r'\circ',
       'LARROW': r'\leftarrow', 'RARROW': r'\rightarrow', 'LRARROW': r'\leftrightarrow', 'TRIANGLE': r'\triangle'}
BIGOP = {'sum': r'\sum', 'smallsum': r'\sum', 'int': r'\int', 'prod': r'\prod', 'lim': r'\lim'}
FUNCS = {'sin', 'cos', 'tan', 'log', 'ln', 'exp', 'max', 'min', 'sinh', 'cosh', 'tanh', 'sec', 'csc', 'cot', 'det', 'arcsin', 'arccos', 'arctan'}
ACCENT = {'bar': r'\bar', 'hat': r'\hat', 'vec': r'\vec', 'dot': r'\dot', 'ddot': r'\ddot', 'tilde': r'\tilde', 'under': r'\underline'}
UNI = {'±': r'\pm', '∓': r'\mp', 'ㆍ': r'\cdot', '·': r'\cdot', '×': r'\times', '≤': r'\le', '≥': r'\ge', '−': '-', '°': r'^{\circ}'}
KEYWORDS = sorted(set(list(SYM) + [g.upper() for g in GREEK]), key=len, reverse=True)


def split_word(w):
    """'BULLETg', 'TIMESomega' 처럼 키워드에 변수가 붙어 있으면 떼어 낸다"""
    if w.lower() in GREEK or w in UPGREEK or w.upper() in SYM or w.lower() in FUNCS or w.lower() in BIGOP or w.lower() in ACCENT:
        return [w]
    for k in KEYWORDS:
        if len(k) >= 4 and len(w) > len(k) and (w[:len(k)] == k or w[:len(k)] == k.lower()):
            return [w[:len(k)]] + split_word(w[len(k):])
    return [w]


def tokenize(s):
    s = s.replace('+-', ' PM ').replace('-+', ' MP ').replace('<=', ' LEQ ').replace('>=', ' GEQ ')
    toks = []; i = 0
    while i < len(s):
        c = s[i]
        if c in '{}^_#&':
            toks.append(c); i += 1
        elif c in ' \t\r\n':
            i += 1
        elif c in '`~':
            j = i
            while j < len(s) and s[j] in '`~ \t\r\n': j += 1
            n = s[i:j].count('`') + 4 * s[i:j].count('~')
            toks.append(('SP', n)); i = j
        elif c.isascii() and c.isalpha():
            j = i
            while j < len(s) and s[j].isascii() and s[j].isalpha(): j += 1
            toks.extend(split_word(s[i:j])); i = j
        elif c.isdigit() or c == '.':
            j = i
            while j < len(s) and (s[j].isdigit() or s[j] == '.'): j += 1
            toks.append(('NUM', s[i:j])); i = j
        elif c == '"':
            j = s.find('"', i + 1); j = len(s) if j < 0 else j
            toks.append(('TXT', s[i + 1:j])); i = j + 1
        elif '가' <= c <= '힣' or c in '㎟㎜㎝㎡㎏㎧':
            j = i
            while j < len(s) and ('가' <= s[j] <= '힣' or s[j] in '㎟㎜㎝㎡㎏㎧'): j += 1
            toks.append(('TXT', s[i:j])); i = j
        else:
            toks.append(c); i += 1
    return toks


def space(n):
    if n <= 0: return ''
    if n >= 6: return r'\quad '
    if n >= 3: return r'\;'
    return r'\,'


class P:
    def __init__(s, toks): s.t = toks; s.i = 0
    def peek(s, k=0): return s.t[s.i + k] if s.i + k < len(s.t) else None
    def next(s):
        v = s.peek(); s.i += 1; return v
    def skip_sp(s):
        while isinstance(s.peek(), tuple) and s.peek()[0] == 'SP': s.i += 1

    def expr(s, stops=('}',)):
        rows = [[]]
        while True:
            t = s.peek()
            if t is None or (isinstance(t, str) and (t in stops or t.upper() in stops)): break
            if t == '#':
                s.next(); rows.append([]); continue
            if t == '&':
                s.next(); continue
            a = s.operand()
            if a is None: continue
            # 분수: 바로 앞 덩어리 over 다음 덩어리
            j = s.i
            while isinstance(s.peek(), tuple) and s.peek()[0] == 'SP': s.i += 1
            if isinstance(s.peek(), str) and s.peek().lower() in ('over', 'atop'):
                kw = s.next().lower(); s.skip_sp()
                b = s.operand(nosp=True) or ''
                a = (r'\frac{%s}{%s}' if kw == 'over' else r'\genfrac{}{}{0pt}{}{%s}{%s}') % (strip_brace(a), strip_brace(b))
            else:
                s.i = j
            rows[-1].append(a)
        rows = [''.join(r).strip() for r in rows]
        rows = [r for r in rows if r] or ['']
        if len(rows) == 1: return rows[0]
        return r'\begin{array}{l}' + r' \\ '.join(rows) + r'\end{array}'

    def operand(s, nosp=False):
        """한 덩어리 + 뒤따르는 첨자"""
        if nosp: s.skip_sp()
        t = s.peek()
        if isinstance(t, tuple) and t[0] == 'SP':
            s.next(); return space(t[1])
        a = s.atom()
        if a is None: return None
        sub = sup = None
        while True:
            k = s.i; s.skip_sp()
            if s.peek() in ('_', '^'):
                op = s.next(); s.skip_sp(); arg = s.atom_arg()
                if op == '_': sub = arg
                else: sup = arg
            else:
                s.i = k; break
        if sub is not None or sup is not None:
            base = a if a else '{}'
            if re.search(r'[_^]', base) and not base.startswith('{'): base = '{' + base + '}'
            if sub is not None: base += '_{' + sub + '}'
            if sup is not None: base += '^{' + (r'\textstyle ' if '\\frac' in sup else '') + sup + '}'   # 지수 속 분수는 읽을 수 있는 크기로
            return base
        return a

    def atom_arg(s):
        t = s.peek()
        if t == '{':
            s.next(); v = s.expr(('}',)); s.next() if s.peek() == '}' else None; return v.strip()
        a = s.atom()
        return (a or '').strip()

    def atom(s):
        t = s.next()
        if t is None: return None
        if isinstance(t, tuple):
            if t[0] == 'NUM': return t[1]
            if t[0] == 'TXT': return r'\text{' + t[1] + '}'
            if t[0] == 'SP': return space(t[1])
        if t == '{':
            v = s.expr(('}',))
            if s.peek() == '}': s.next()
            return '{' + v + '}'
        if t == '}': return None
        if t in ('_', '^'): return None
        lo, up = t.lower(), t.upper()
        if lo == 'sqrt':
            s.skip_sp(); return r'\sqrt{' + strip_brace(s.atom_arg()) + '}'
        if lo == 'root':
            s.skip_sp(); n = s.atom_arg(); s.skip_sp()
            if isinstance(s.peek(), str) and s.peek().lower() == 'of': s.next()
            s.skip_sp(); return r'\sqrt[' + n + ']{' + strip_brace(s.atom_arg()) + '}'
        if lo in ('left', 'right'):
            s.skip_sp(); d = s.next()
            d = {'(': '(', ')': ')', '[': '[', ']': ']', '{': r'\{', '}': r'\}', '|': '|', '.': '.'}.get(d if isinstance(d, str) else '.', '.')
            if lo == 'right': return r'\right' + d
            inner = s.expr(('RIGHT',))
            close = '.'
            if isinstance(s.peek(), str) and s.peek().upper() == 'RIGHT':
                s.next(); s.skip_sp(); c = s.next()
                close = {'(': '(', ')': ')', '[': '[', ']': ']', '{': r'\{', '}': r'\}', '|': '|', '.': '.'}.get(c if isinstance(c, str) else '.', '.')
            return r'\left' + d + ' ' + inner + r' \right' + close
        if lo in BIGOP:
            op = BIGOP[lo]
            s.skip_sp()
            if isinstance(s.peek(), str) and s.peek().lower() == 'from':
                s.next(); s.skip_sp(); op += '_{' + s.atom_arg() + '}'; s.skip_sp()
                if isinstance(s.peek(), str) and s.peek().lower() == 'to':
                    s.next(); s.skip_sp(); op += '^{' + s.atom_arg() + '}'
            return op + ' '
        if lo in ACCENT:
            s.skip_sp(); return ACCENT[lo] + '{' + strip_brace(s.atom_arg()) + '}'
        if lo in ('rm', 'it', 'bold'): return ''
        if lo in ('pile', 'lpile', 'rpile', 'cases', 'matrix', 'pmatrix', 'bmatrix', 'eqalign'):
            s.skip_sp()
            if s.peek() == '{':
                s.next(); inner = s.expr(('}',))
                if s.peek() == '}': s.next()
            else: inner = s.atom_arg()
            if lo == 'cases': return r'\left\{' + inner + r'\right.'
            return inner
        if lo in GREEK and (t == lo):
            return '\\' + lo + ' '
        if t in UPGREEK: return '\\' + t + ' '
        if t.isupper() and lo in GREEK:
            u = lo[0].upper() + lo[1:]
            return ('\\' + u + ' ') if u in UPGREEK else {'alpha': 'A', 'beta': 'B', 'epsilon': 'E', 'zeta': 'Z', 'eta': 'H', 'iota': 'I', 'kappa': 'K', 'mu': 'M', 'nu': 'N', 'omicron': 'O', 'rho': 'P', 'tau': 'T', 'chi': 'X'}.get(lo, t)
        if up in SYM and (t == up or t == lo): return SYM[up] + ' '
        if lo in FUNCS: return '\\' + lo + ' '
        if t in UNI: return UNI[t] + ' '
        if t in ('#', '&'): return ' '
        if t == '%': return r'\%'
        if t == '$': return r'\$'
        if t == '\\': return r'\backslash '
        if isinstance(t, str) and t.isascii() and t.isalpha():
            return t if len(t) == 1 else r'\mathit{' + t + '}'
        if isinstance(t, str) and not t.isascii(): return r'\text{' + t + '}'
        return t


def strip_brace(x):
    x = x.strip()
    if x.startswith('{') and x.endswith('}'):
        d = 0
        for i, c in enumerate(x):
            d += c == '{'; d -= c == '}'
            if d == 0 and i < len(x) - 1: return x
        return x[1:-1]
    return x


def grow_parens(r):
    """분수·합이 든 ( … ), [ … ] 는 \\left \\right 로 키워 읽기 쉽게 (같은 중괄호 깊이에서 짝이 맞을 때만)"""
    out = list(r); st = []; depth = 0; i = 0
    while i < len(r):
        c = r[i]
        if c == '\\':
            m = re.match(r'\\(left|right)(\\\{|\\\}|.)|\\[A-Za-z]+|\\.', r[i:])
            i += len(m.group(0)); continue
        if c == '{': depth += 1
        elif c == '}': depth -= 1
        elif c in '([': st.append((c, i, depth))
        elif c in ')]':
            if st and st[-1][0] == {')': '(', ']': '['}[c] and st[-1][2] == depth:
                o, j, _ = st.pop()
                inner = r[j + 1:i]
                if re.search(r'\\frac|\\sum|\\sqrt', inner):
                    out[j] = r'\left' + o + ' '; out[i] = r' \right' + c
            else:
                st = [x for x in st if x[2] != depth]
        i += 1
    return ''.join(out)


def convert(script):
    r = P(tokenize(script)).expr(stops=())
    r = grow_parens(r)
    r = re.sub(r'(\\quad\s*){2,}', r'\\quad ', r)
    if re.search(r'\\frac|\\sum|\\sqrt', r):   # 줄 안 수식이라도 분수는 크게(HWP 화면과 같게)
        if r.startswith(r'\begin{array}{l}'):
            r = r.replace(r'\begin{array}{l}', r'\begin{array}{l}\displaystyle ', 1).replace(r' \\ ', r' \\ \displaystyle ')
        else:
            r = r'\displaystyle ' + r
    r = re.sub(r'^(\\[,;]|\\quad\s*)+|(\\[,;]|\\quad\s*)+$', '', r.strip())
    return re.sub(r'\s+', ' ', r).strip()


if __name__ == '__main__':
    import json, sys
    for f in sys.argv[1:]:
        for e in dict.fromkeys(json.load(open(f, encoding='utf-8'))):
            print(repr(e)[:100], ' → ', convert(e))
