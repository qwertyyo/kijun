"""HWP 5.0 BodyText 에서 문단 텍스트와 수식(eqed) 스크립트를 순서대로 뽑는다."""
import olefile, zlib, struct, sys, json

TAG_BEGIN = 16
PARA_TEXT = TAG_BEGIN + 51      # 67
CTRL_HEADER = TAG_BEGIN + 55    # 71
EQEDIT = TAG_BEGIN + 72         # 88

def records(data):
    i = 0
    while i < len(data):
        h = struct.unpack_from('<I', data, i); h = h[0]; i += 4
        tag = h & 0x3FF; level = (h >> 10) & 0x3FF; size = (h >> 20) & 0xFFF
        if size == 0xFFF:
            size = struct.unpack_from('<I', data, i)[0]; i += 4
        yield tag, level, data[i:i + size]
        i += size

def para_text(payload):
    """제어문자를 처리해 (텍스트, 확장컨트롤 위치 목록) 반환"""
    out = []; ctrls = []
    n = len(payload) // 2
    w = struct.unpack('<%dH' % n, payload[:n * 2])
    i = 0
    while i < n:
        c = w[i]
        if c < 32:
            if c in (0, 10, 13, 24, 25, 26, 27, 28, 29, 30, 31):   # char 컨트롤
                if c == 10 or c == 13: out.append('\n')
                elif c == 30 or c == 31: out.append(' ')
                i += 1
            else:                                                   # inline/extended: 8 WCHAR
                ctrlid = struct.pack('<4H', *w[i + 1:i + 5])[:4][::-1].decode('latin1', 'replace')
                if c in (1, 2, 3, 11, 12, 14, 15, 16, 17, 18, 21, 22, 23):
                    ctrls.append((len(out), ctrlid))
                    out.append('\x00')      # placeholder
                elif c == 9:
                    out.append('\t')
                i += 8
        else:
            out.append(chr(c)); i += 1
    return out, ctrls

def extract(path):
    ole = olefile.OleFileIO(path)
    hdr = ole.openstream('FileHeader').read()
    compressed = bool(struct.unpack_from('<I', hdr, 36)[0] & 1)
    secs = sorted([e for e in ole.listdir() if e[0] == 'BodyText'], key=lambda e: int(e[1][7:]))
    eqs = []
    paras = []
    for s in secs:
        raw = ole.openstream(s).read()
        data = zlib.decompress(raw, -15) if compressed else raw
        cur_ctrl = None
        for tag, level, p in records(data):
            if tag == PARA_TEXT:
                txt, ctrls = para_text(p)
                paras.append({'chars': txt, 'ctrls': ctrls, 'eq': []})
            elif tag == CTRL_HEADER:
                cur_ctrl = p[:4][::-1].decode('latin1', 'replace')
            elif tag == EQEDIT:
                attr, ln = struct.unpack_from('<IH', p, 0)
                script = p[6:6 + ln * 2].decode('utf-16-le', 'replace')
                eqs.append(script)
                if paras: paras[-1]['eq'].append(script)
    return eqs, paras

if __name__ == '__main__':
    eqs, paras = extract(sys.argv[1])
    json.dump(eqs, open(sys.argv[2], 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
    print(len(eqs), 'equations')
    for e in eqs[:25]: print(repr(e))
