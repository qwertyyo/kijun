"""빌드 후 사이트(저장소 루트)에 반영하고 커밋·푸시. build/ 에서: python publish.py "커밋 메시지"
  --no-build : 빌드 없이 복사만    --no-push : 커밋까지만
루트에 쓰는 것: index.html(제목·noindex 추가), fig/(기준 본문·연혁집 그림), stdimg/(표준화 그림). katex/ 는 고정 파일."""
import os, sys, shutil, subprocess
if not sys.flags.utf8_mode:
    sys.exit(subprocess.call([sys.executable, '-X', 'utf8'] + sys.argv))
B = os.path.dirname(os.path.abspath(__file__)); R = os.path.dirname(B)
args = [a for a in sys.argv[1:] if not a.startswith('--')]
msg = args[0] if args else '사이트 갱신'
if '--no-build' not in sys.argv:
    subprocess.run([sys.executable, '-X', 'utf8', os.path.join(B, 'build.py')] + (['--images'] if '--images' in sys.argv else []), check=True)
subprocess.run(['git', '-C', R, 'pull', '-q', '--rebase', 'origin', 'main'])   # config.json 등 다른 곳에서 고친 것 먼저 받기
t = open(os.path.join(B, 'app_pkg', 'kijun.html'), encoding='utf-8').read()
t = t.replace('<meta charset="utf-8">', '<meta charset="utf-8">\n<title>검사기준 통합검색</title>\n<meta name="robots" content="noindex">', 1)
open(os.path.join(R, 'index.html'), 'w', encoding='utf-8', newline='\n').write(t)
for d in ('fig', 'stdimg'):
    if not os.path.isdir(os.path.join(B, d)): continue   # stdimg/ 는 --images 로 다시 잘랐을 때만
    shutil.rmtree(os.path.join(R, d), ignore_errors=True)
    shutil.copytree(os.path.join(B, d), os.path.join(R, d))
subprocess.run(['git', '-C', R, 'add', '-A'], check=True)
if subprocess.run(['git', '-C', R, 'diff', '--cached', '--quiet']).returncode == 0:
    print('바뀐 것 없음'); sys.exit(0)
subprocess.run(['git', '-C', R, 'commit', '-qm', msg], check=True)
if '--no-push' not in sys.argv:
    subprocess.run(['git', '-C', R, 'push', 'origin', 'main'], check=True)
print('완료: 1~2분 뒤 https://qwertyyo.github.io/kijun/ 에 반영')
