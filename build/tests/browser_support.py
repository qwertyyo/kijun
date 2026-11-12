"""기존 회귀 검사를 Windows에서도 동일한 입력으로 실행한다."""
import os
from pathlib import Path
import shutil


def browser_path():
    if os.environ.get('CHROMIUM_PATH'):
        return os.environ['CHROMIUM_PATH']
    for path in ('/usr/bin/chromium',
                 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
                 'C:/Program Files/Google/Chrome/Application/chrome.exe'):
        if Path(path).is_file():
            return path
    raise RuntimeError('CHROMIUM_PATH에 설치된 Chromium 계열 브라우저를 지정하세요.')


def link_directory(link, target):
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError:
        shutil.copytree(target, link)


def screenshot_path(name):
    output = Path(__file__).resolve().parents[2] / 'tmp'
    output.mkdir(exist_ok=True)
    return str(output / name)
