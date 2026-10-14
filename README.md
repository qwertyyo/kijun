# 검사기준 통합검색

엘리베이터·에스컬레이터 안전기준(현행), 적용 연혁(승강기 안전기준 연혁집), 검사방법 표준화를 현장용어로 검색하는 정적 페이지.

- 페이지: index.html (데이터 내장, 오프라인 동작)
- 그림: stdimg/

## 다시 만들기
원본 자료와 빌드 스크립트는 `build/` 에 있습니다. 자세한 방법은 `CLAUDE.md`.
```
cd build
pip install -r requirements.txt
python publish.py "변경 내용"
```
