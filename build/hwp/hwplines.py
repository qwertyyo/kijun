"""HWP 본문을 줄 목록으로: 일반 문단은 한 줄, 표는 한 줄의 표 표식(TBL + JSON 행렬)으로 만든다.
수식(eqed)은 eq2text 로 한 줄 텍스트로 바꿔 끼운다."""
import olefile, zlib, struct, json, re, sys
sys.path.insert(0, '.')
from hwpeq import records, para_text
import eq2text, eq2tex
PICS = {}   # 그림 BinData 번호 → (파일명, 폭, 높이) : extract_lines 호출 전에 채운다

PARA_HEADER, PARA_TEXT, CTRL_HEADER, LIST_HEADER, TABLE, EQEDIT = 66, 67, 71, 72, 77, 88
TBL = '⁣TBL'

class Para:
    def __init__(s, chars, ctrls): s.chars, s.ctrls, s.eq, s.pics = chars, ctrls, [], []
    def text(s):
        ch = s.chars[:]; ei = 0; gi = 0
        for pos, cid in s.ctrls:
            if cid == 'eqed' and ei < len(s.eq):
                # 수식: \x05 한 줄 텍스트(검색용) \x0e LaTeX(화면용) \x06
                ch[pos] = ' \x05' + eq2text.convert(s.eq[ei]) + '\x0e' + eq2tex.convert(s.eq[ei]) + '\x06 '; ei += 1
            elif cid == 'gso ' and gi < len(s.pics):
                # 그림: 따로 한 줄 \x10파일|폭|높이\x11 (한 개체에 그림이 여럿이면 모두)
                ch[pos] = ''.join('\n\x10%s|%d|%d\x11\n' % PICS[b] for b in s.pics[gi] if b in PICS); gi += 1
            else:
                ch[pos] = ''
        t = ''.join(ch).replace('\x00', '')
        out = []
        for l in t.split('\n'):
            l = re.sub(r'[ \t]+', ' ', l).strip()
            l = l.replace('( ', '(').replace(' )', ')')
            out.append(l)
        return out

class Table:
    def __init__(s, level, rows, cols):
        s.level, s.rows, s.cols = level, rows, cols
        s.cells = {}; s.cur = None
    def render(s):
        grid = [['' for _ in range(s.cols)] for _ in range(s.rows)]
        for (r, c), items in s.cells.items():
            if r < s.rows and c < s.cols:
                parts = []
                for it in items:
                    if isinstance(it, Para): parts.extend([x for x in it.text() if x])
                    elif isinstance(it, list): parts.append('\n'.join(' | '.join(x for x in row if x) for row in it))
                    else: parts.append(it)
                grid[r][c] = '\n'.join(parts)
        grid = [row for row in grid if any(x.strip() for x in row)]
        # 빈 열 제거
        keep = [j for j in range(s.cols) if any(row[j].strip() for row in grid)]
        grid = [[row[j] for j in keep] for row in grid]
        return grid

def extract_lines(path):
    ole = olefile.OleFileIO(path)
    hdr = ole.openstream('FileHeader').read()
    compressed = bool(struct.unpack_from('<I', hdr, 36)[0] & 1)
    secs = sorted([e for e in ole.listdir() if e[0] == 'BodyText'], key=lambda e: int(e[1][7:]))
    top = []            # Para | Table(완성된 grid list)
    stack = []          # 열린 표
    last_para = None
    n_eq = 0
    gso = []
    def sink(item):
        if stack and stack[-1].cur is not None:
            stack[-1].cells.setdefault(stack[-1].cur, []).append(item)
        else:
            top.append(item)
    def is_layout(t):
        # 1열 표나 문단이 아주 많은 셀이 있는 표는 본문을 감싼 틀(레이아웃)로 본다
        if t.cols == 1: return True
        return any(sum(1 for it in items if isinstance(it, Para)) > 25 for items in t.cells.values())
    def close_until(level):
        while stack and level < stack[-1].level:
            t = stack.pop()
            if is_layout(t):
                for key in sorted(t.cells):
                    for it in t.cells[key]: sink(it)
            else:
                sink(t.render())
    for s in secs:
        raw = ole.openstream(s).read()
        data = zlib.decompress(raw, -15) if compressed else raw
        for tag, level, p in records(data):
            close_until(level)
            if tag == TABLE:
                rows, cols = struct.unpack_from('<HH', p, 4)
                stack.append(Table(level, rows, cols))
            elif tag == LIST_HEADER and stack and level == stack[-1].level:
                if len(p) >= 16:
                    col, row = struct.unpack_from('<HH', p, 8)
                    stack[-1].cur = (row, col)
            elif tag == PARA_TEXT:
                chars, ctrls = para_text(p)
                last_para = Para(chars, ctrls)
                sink(last_para)
                for _, cid in ctrls:
                    if cid == 'gso ': gso.append((level, last_para)); last_para.pics.append([])
            elif tag == 85:   # SHAPE_COMPONENT_PICTURE → BinItem ID (오프셋 71)
                bid = struct.unpack_from('<H', p, 71)[0]
                own = next((pp for lv, pp in reversed(gso) if lv < level), None)
                if own is not None:
                    # 같은 문단에 그림 개체가 여럿이면 아직 안 채운 칸부터
                    slot = next((x for x in own.pics if not x), own.pics[-1]); slot.append(bid)
            elif tag == EQEDIT:
                attr, ln = struct.unpack_from('<IH', p, 0)
                script = p[6:6 + ln * 2].decode('utf-16-le', 'replace')
                if last_para is not None: last_para.eq.append(script); n_eq += 1
    close_until(-1)
    lines = []
    for it in top:
        if isinstance(it, Para):
            lines.extend(it.text())
        else:
            if it and any(any(c.strip() for c in row) for row in it):
                lines.append(TBL + json.dumps(it, ensure_ascii=False))
    return lines, n_eq

if __name__ == '__main__':
    lines, n = extract_lines(sys.argv[1])
    print(len(lines), 'lines', n, 'eq', sum(1 for l in lines if l.startswith(TBL)), 'tables')
