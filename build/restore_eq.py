# HWP 수식 글꼴(HyhwpEQ) 사설코드 → 문자 복원
# 근거: 별표24 PDF에 내장된 HyhwpEQ 글리프를 직접 렌더링해 확인(글리프 검증) + 별표22 문맥 다중 일치(문맥 검증)
import re, sys
M = {}
for i in range(26):
    M[0xe000 + i] = chr(65 + i)      # A–Z  (F,P,Q 문맥 검증)
    M[0xe0e5 + i] = chr(97 + i)      # a–z  (b,h,l,v,x,y,z 글리프 / g,n,k,m,p,q,r 문맥)
for i, g in enumerate('αβγδεζηθικλμνξοπρστυφχψω'):
    M[0xe09d + i] = g                # α–ω  (α,β,γ,μ 글리프 / λ,σ,ω 문맥)
for i in range(9):
    M[0xe034 + i] = str(i + 1)       # 1–9  (1–5,7,8 글리프)
M[0xe03d] = '0'                      # 0.035 문맥
M.update({0xe047: '=', 0xe044: '(', 0xe045: ')', 0xe048: '+', 0xe053: '.', 0xe054: '/',
          0xe052: ',', 0xe046: '−', 0xe049: '[', 0xe04a: ']'})   # 연산자: F = 4·gn·(P+Q), 0.035·v², N/㎟, Rm − 370 등 문맥

RUN = re.compile(r'(?:[-][^\S\n]*[∙ㆍ·,]?[^\S\n]*)+')

def restore(text):
    def fix(m):
        run = m.group()
        if all((ord(c) in M) for c in run if 0xe000 <= ord(c) <= 0xf8ff):
            return ''.join(M.get(ord(c), c) for c in run)
        return '[수식] '        # 분수선·큰 괄호 등 구조 기호가 섞인 수식은 원문 확인 필요
    out = RUN.sub(fix, text)
    return re.sub(r'(\[수식\] ){2,}', '[수식] ', out)

if __name__ == '__main__':
    src, dst = sys.argv[1], sys.argv[2]
    s = open(src, encoding='utf-8').read()
    r = restore(s)
    open(dst, 'w', encoding='utf-8').write(r)
    print(dst, 'PUA before', sum(1 for c in s if 0xe000 <= ord(c) <= 0xf8ff), 'markers', r.count('[수식]'))
