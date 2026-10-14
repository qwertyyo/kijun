"""한글(HWP) 수식 스크립트 → 읽기 쉬운 한 줄 텍스트"""
import re

GREEK = {'alpha': 'α', 'beta': 'β', 'gamma': 'γ', 'delta': 'δ', 'epsilon': 'ε', 'zeta': 'ζ', 'eta': 'η', 'theta': 'θ',
         'iota': 'ι', 'kappa': 'κ', 'lambda': 'λ', 'mu': 'μ', 'nu': 'ν', 'xi': 'ξ', 'omicron': 'ο', 'pi': 'π', 'rho': 'ρ',
         'sigma': 'σ', 'tau': 'τ', 'upsilon': 'υ', 'phi': 'φ', 'chi': 'χ', 'psi': 'ψ', 'omega': 'ω'}
GREEK_UP = {k.upper(): v.upper() for k, v in GREEK.items()}
SYM = {'BULLET': '·', 'CDOT': '·', 'TIMES': '×', 'DIV': '÷', 'LEQ': '≤', 'LE': '≤', 'GEQ': '≥', 'GE': '≥',
       'NEQ': '≠', 'APPROX': '≈', 'PM': '±', 'MP': '∓', 'INF': '∞', 'INFTY': '∞', 'DEG': '°', 'PRIME': '′',
       'CDOTS': '⋯', 'LDOTS': '…', 'SIM': '~', 'PROPTO': '∝', 'SUM': 'Σ', 'INT': '∫', 'PARTIAL': '∂',
       'LARROW': '←', 'RARROW': '→', 'LRARROW': '↔', 'THEREFORE': '∴', 'BECAUSE': '∵', 'ANGLE': '∠',
       'PREC': '≺', 'SUCC': '≻', 'LL': '≪', 'GG': '≫', 'EQUIV': '≡', 'SMALLSUM': 'Σ', 'DOT': '·', 'CIRC': '°',
       'LNOT': '¬', 'NABLA': '∇', 'TRIANGLE': '△', 'SQUARE': '□', 'BOX': '□', 'CENTIGRADE': '℃', 'OHM': 'Ω',
       'ANGSTROM': 'Å', 'MHO': '℧', 'LEFT': '', 'RIGHT': '', 'IT': '', 'RM': '', 'BOLD': '', 'BIG': ''}
FUNCS = {'sin', 'cos', 'tan', 'log', 'ln', 'exp', 'max', 'min', 'lim', 'arcsin', 'arccos', 'arctan', 'sinh', 'cosh', 'tanh', 'sec', 'csc', 'cot', 'det', 'mod'}
SUB = str.maketrans('0123456789+-=()aehijklmnoprstuvx', '₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎ₐₑₕᵢⱼₖₗₘₙₒₚᵣₛₜᵤᵥₓ')
SUP = str.maketrans('0123456789+-=()n', '⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿ')
SUBOK = set('0123456789+-=()aehijklmnoprstuvx')
SUPOK = set('0123456789+-=()n')

KEYS = None
def split_word(w):
    global KEYS
    if KEYS is None:
        KEYS = sorted(set(list(SYM) + [k.upper() for k in GREEK] + ['OVER', 'ATOP', 'SQRT', 'ROOT', 'LEFT', 'RIGHT'] + [f.upper() for f in FUNCS]), key=len, reverse=True)
    lo = w.lower(); up = w.upper()
    if w in GREEK or w in GREEK_UP or up in SYM or lo in FUNCS or lo in ('over', 'atop', 'sqrt', 'root', 'left', 'right', 'pile', 'cases', 'matrix'):
        return [w]
    # 'BULLETg', 'bulletv' 처럼 키워드에 변수가 붙은 경우 분리 (키워드 4글자 이상만)
    for k in KEYS:
        if len(k) >= 4 and up.startswith(k) and len(w) > len(k) and (w[:len(k)] == k or w[:len(k)] == k.lower()):
            return [w[:len(k)], ' '] + split_word(w[len(k):])
    return [w]

def tokenize(s):
    toks = []
    i = 0
    while i < len(s):
        c = s[i]
        if c in '{}^_#&':
            toks.append(c); i += 1
        elif c in ' \t\r\n~`':
            toks.append(' '); i += 1
        elif c.isalpha() and c.isascii():
            j = i
            while j < len(s) and s[j].isascii() and s[j].isalpha(): j += 1
            w = s[i:j]
            toks.extend(split_word(w)); i = j
        elif c.isdigit() or c == '.':
            j = i
            while j < len(s) and (s[j].isdigit() or s[j] == '.'): j += 1
            toks.append(s[i:j]); i = j
        elif c == '"':
            j = s.find('"', i + 1); j = len(s) if j < 0 else j
            toks.append(('TEXT', s[i + 1:j])); i = j + 1
        else:
            toks.append(c); i += 1
    return toks

class P:
    def __init__(s, toks): s.t = toks; s.i = 0
    def peek(s, skipsp=True):
        j = s.i
        while skipsp and j < len(s.t) and s.t[j] == ' ': j += 1
        return s.t[j] if j < len(s.t) else None
    def next(s, skipsp=True):
        while skipsp and s.i < len(s.t) and s.t[s.i] == ' ': s.i += 1
        if s.i >= len(s.t): return None
        v = s.t[s.i]; s.i += 1; return v

    def expr(s, stop=('}',)):
        parts = []
        while True:
            pk = s.peek(False)
            if pk is None or pk in stop: break
            if pk == ' ':
                s.i += 1; parts.append(' '); continue
            a = s.atom()
            if a is None: continue
            # postfix sub/sup
            while s.peek() in ('_', '^'):
                op = s.next(); arg = s.atom()
                a = a + (sub(arg) if op == '_' else sup(arg))
            # binary over
            nxt = s.peek()
            if isinstance(nxt, str) and nxt.lower() in ('over', 'atop'):
                s.next(); den = s.atom()
                while s.peek() in ('_', '^'):
                    op = s.next(); arg = s.atom(); den = den + (sub(arg) if op == '_' else sup(arg))
                a = frac(a, den)
                prev = ''.join(parts).rstrip()
                mm = re.search(r'([a-z]+)$', prev)
                if mm and mm.group(1) in FUNCS: a = '(' + a + ')'
            parts.append(a)
        out = ''.join(parts)
        return re.sub(r'\s+', ' ', out).strip()

    def atom(s):
        t = s.next()
        if t is None: return ''
        if isinstance(t, tuple): return t[1]
        if t == '{':
            v = s.expr(('}',)); s.next(); return v
        if t in ('}',): return ''
        if t in ('#', '&'): return '; ' if t == '#' else ' '
        lo = t.lower(); up = t.upper()
        if lo == 'sqrt':
            arg = s.atom(); return '√' + (arg if len(arg) <= 1 else '(' + arg + ')')
        if lo == 'root':
            n = s.atom(); kw = s.next(); arg = s.atom(); return (sup(n) if n else '') + '√(' + arg + ')'
        if lo in ('bar', 'hat', 'vec', 'dot', 'ddot', 'tilde', 'under', 'acute', 'grave', 'dyad', 'arch', 'check'):
            return s.atom()
        if lo in ('it', 'rm', 'bold'):
            return ''
        if lo in ('pile', 'lpile', 'rpile', 'matrix', 'cases', 'eqalign', 'bmatrix', 'pmatrix', 'dmatrix'):
            arg = s.atom(); return ('{' + arg + '}') if lo == 'cases' else arg
        if lo in ('left', 'right'):
            d = s.next(False)
            while d == ' ': d = s.next(False)
            return '' if d in (None, '.') else str(d)
        if t in GREEK: return GREEK[t]
        if t in GREEK_UP: return GREEK_UP[t]
        if up in SYM and (t == up or t == lo or lo in ('bullet', 'times', 'leq', 'geq', 'le', 'ge', 'pm', 'mp', 'cdot', 'deg', 'prec', 'succ', 'approx', 'neq', 'div', 'centigrade', 'ohm', 'inf', 'prime')):
            return SYM[up]
        if lo in FUNCS: return lo + ' '
        if t in ('^', '_'): return ''
        return t

def sub(x):
    x = re.sub(r'\s+', '', x)
    if not x: return ''
    tail = ''
    if x.endswith('='): x, tail = x[:-1], ' ='
    if x and all(c in SUBOK for c in x): return x.translate(SUB) + tail
    return '_' + x + tail

def sup(x):
    x = re.sub(r'\s+', '', x)
    if not x: return ''
    if all(c in SUPOK for c in x): return x.translate(SUP)
    return '^' + (x if re.fullmatch(r'[\w.]+', x) else '(' + x + ')')

SIMPLE = re.compile(r'([0-9.]+|[A-Za-zα-ωΑ-Ω가-힣]+?([₀-₉ₐ-ₜᵢ-ᵥ₊₋₌]+|_[A-Za-z0-9.]+)?([⁰-⁹ⁿ]+|\^[\w.]+)?|[가-힣 ]+)')
def balanced_group(x):
    if not (x.startswith('(') and x.endswith(')')): return False
    d = 0
    for i, c in enumerate(x):
        d += c == '('; d -= c == ')'
        if d == 0 and i < len(x) - 1: return False
    return True
def wrap(x):
    x = x.strip()
    if SIMPLE.fullmatch(x) or balanced_group(x): return x
    return '(' + x + ')'

def frac(a, b):
    return wrap(a) + '/' + wrap(b)

def convert(script):
    s = script.replace('\r', ' ').replace('\n', ' ')
    s = s.replace('+-', ' PM ').replace('-+', ' MP ').replace('<=', ' LEQ ').replace('>=', ' GEQ ')
    r = P(tokenize(s)).expr(stop=())
    r = re.sub(r'\s*([=≤≥≺≻<>±∓+×])\s*', r' \1 ', r)
    r = re.sub(r'\s*·\s*', '·', r)
    r = re.sub(r'\s+', ' ', r).strip()
    r = r.replace('( ', '(').replace(' )', ')')
    return r

if __name__ == '__main__':
    import json, sys
    eqs = json.load(open(sys.argv[1], encoding='utf-8'))
    seen = set()
    for e in eqs:
        if e in seen: continue
        seen.add(e); print(repr(e)[:90], '  →  ', convert(e))
