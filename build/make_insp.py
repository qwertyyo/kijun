"""표준화 PDF(stdzip/std.pdf)를 새 판으로 바꿀 때: insp.txt(쪽 글을 차례로 이은 것) 다시 만들기 + std_geo.json 삭제
insp.txt 는 PyMuPDF get_text() 를 쪽마다 이어 붙인 것이어야 한다(stdgeo.py 가 글자 수로 쪽 위치를 맞춤)."""
import sys, os, subprocess
if not sys.flags.utf8_mode:
    sys.exit(subprocess.call([sys.executable, '-X', 'utf8'] + sys.argv))
import pymupdf
os.chdir(os.path.dirname(os.path.abspath(__file__)))
d = pymupdf.open('stdzip/std.pdf')
open('insp.txt', 'w', encoding='utf-8').write(''.join(p.get_text() for p in d))
if os.path.exists('std_geo.json'): os.remove('std_geo.json')
print('insp.txt', d.page_count, '쪽')
