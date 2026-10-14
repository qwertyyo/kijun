# 검사기준 통합검색 (qwertyyo/kijun)

공단 동료용 웹 도구. 엘리베이터(별표22)·에스컬레이터(별표24) 안전기준 현행 본문, 「승강기 안전기준 연혁집」의 적용 연혁, 검사방법 표준화 협의 결과를 **현장용어**로 검색한다.
사이트: https://qwertyyo.github.io/kijun/ (GitHub Pages, main 브랜치 루트, 공개 저장소)

## 사용자
- 승강기 검사원(부산). 답은 **한국어**로, 짧고 정확하게. 추측 말고 원문으로 확인한 것만. 틀리면 바로 지적하는 분.
- "남기지 말고 알아서 정리해" — 문제를 찾으면 보고만 하지 말고 끝까지 고친다. 단, 원문 PDF 자체의 오류(슬라이드 복사 실수 등)는 원문대로 둔다.
- 사이트만 고친다(예전 아티팩트·zip 패키지는 더 이상 갱신 안 함).

## 폴더
- `index.html` — 사이트 페이지(데이터 내장). **직접 고치지 말고** `build/` 에서 빌드해 덮어쓴다.
- `fig/` — 기준 본문 그림(HWP 원본에서: `el_*`, `es_*`)과 연혁집 원문 그림·표·분수식 영역(`hel_*`, `hes_*`). 빌드 산출물.
- `stdimg/` — 표준화 그림(PDF에서 잘라 냄). `build.py --images` 일 때만 다시 만든다.
- `katex/` — 수식 표시(KaTeX 0.16.11, 고정 파일).
- `config.json` — `{"synApi": "<Apps Script /exec 주소>"}` 공용 현장용어 서버. 비면 기능 꺼짐. 여기서 고쳐도 됨.
- `gas/` — 공용 현장용어 서버(Google Apps Script). 아래 SETUP.
- `build/` — **원본 자료 + 빌드 스크립트 전부.**

## 빌드·배포 (build/ 에서)
```
pip install -r requirements.txt        # pymupdf, olefile, pillow (Python 3.10+)
python build.py                         # → app_pkg/kijun.html (약 1~2분)
python build.py --images                # 표준화 안건 나눔이 바뀌었을 때(그림 재연결까지, +1분)
python publish.py "커밋 메시지"           # 빌드 → 루트 index.html/fig/stdimg 복사 → git pull --rebase → commit → push
python publish.py "메시지" --no-build     # 이미 빌드했으면
python -m http.server -d .. 8765         # 로컬 확인: http://localhost:8765/
```
- 윈도우에서도 스크립트가 스스로 `-X utf8` 로 다시 실행한다(기본 cp949 로 JSON 읽다 깨지는 것 방지).
- 커밋 author 는 저장소 git 설정(qwertyyo) 그대로. 빌드는 결정적이다: 같은 입력이면 index.html 이 바이트 단위로 같다(클라우드에서 옮길 때 확인함).

## 데이터 흐름 (build/)
| 단계 | 스크립트 | 입력 | 출력 |
|---|---|---|---|
| 표준화 쪽 위치 | `stdgeo.py` | `stdzip/std.pdf`, `insp.txt` | `std_geo.json` (줄번호→[쪽, y, x, 글자크기]) |
| 표준화 안건 | `parse.py` | `insp.txt`, `std_geo.json`, `std_ids.json`, `std_fix.json` | `data.json` std |
| 표준화 그림 | `std_images.py` | `std.pdf`, `data.json` | `stdimg/`, `stdimg.json` |
| 별표22·24 | `hwp/parse_hwp.py` (+`hwplines.py`, `hwpeq.py`, `eq2text.py`, `eq2tex.py`) | `hwp/b22.hwp`, `hwp/b24.hwp` | `hwp/b22h.json`, `b24h.json`, `fig/el_*`, `fig/es_*` |
| 연혁 | `hist_parse.py el|es`, `hist_merge.py el|es` (+`restore_eq.py`) | `hist_src/hist.pdf`(엘리베이터), `hist_es/hist.pdf`(에스컬레이터 v2.0) | `hist_final.json`, `hist_es_final.json`, `fig/hel_*`, `fig/hes_*` |
| 요지 | (Claude가 작성) | — | `gists.json`(표준화 id→요지), `hist_gist_keyed.json`, `hist_es_gist_keyed.json`(연혁 블록 요지) |
| 페이지 | `build.py` | `template.html` + 위 전부 | `app_pkg/kijun.html` |

### 표준화(insp.txt) 파싱 요점
- 원본은 슬라이드 PDF(744쪽). `insp.txt` = 각 쪽 `get_text()` 를 이은 것(공백 뺀 글자 수가 PDF와 정확히 같아야 함). **2쪽(개인 연락처가 든 배포 안내문)은 공개 저장소라 빈 쪽으로 지웠다** — 다른 쪽 번호는 그대로.
- 안건 머리: `번호 제목` 줄. 회차 머리(`hdr_re`)가 바뀌면 새 회차. 같은 회차에서 번호가 겹치면: `[기타안건]`류 꼬리표·쪽마다 되풀이된 줄·슬라이드 맨 위(y 55~100)·왼쪽 큰 번호(14pt, x<50)이면 새 안건, 아니면 지금 안건 본문. 9pt 이하 작은 글자 줄은 안건 머리 아님(표의 번호 칸).
- 묶음 머리(`□ 기타안건`, `- 기타안건`, `기타`, `제1차 기술서류 업무 표준화`, `…기술자문 간담회(n차)…`) 아래 안건은 제목에 `[기타안건]`/`[기타]` 를 붙이거나 회차 이름에 `· 묶음이름` 을 덧붙인다.
- **쪽 배치 재배정**: 각 본문 줄은 같은 쪽에서 그 줄 바로 위(-8pt 허용)에 있는 안건 머리의 것(텍스트 추출 순서 때문에 표가 다음 안건 뒤에 붙던 문제 해결). 목차 쪽(`1. …` 목록 + `[…안건]`)의 글은 회차 목차로.
- **id 고정**: `std_ids.json` 의 `회차|번호|제목 → std-N`. 그림(stdimg.json)·요지(gists.json)가 id 로 연결되므로 **이 파일을 지우거나 되돌리지 말 것**(새 안건만 새 번호). 제목을 바꿀 땐 `std_fix.json` 의 `title` 로(아래) — id 는 원래 제목으로 유지된다.
- **개별 수정 `std_fix.json`** (원문 대조 검토로 찾은 것): `cut`(본문 블록 떼어내 drop / 다른 id로 이동 / `new` 새 안건, `split_at` 으로 여럿), `merge`(from→into), `title`, `dropfirst`(잘린 제목 꼬리가 본문 첫 줄로 간 경우), `path`(회차 이름). 줄은 본문 줄과 **정확히 같은 문자열**로 지정. 적용 결과는 빌드 로그 `std_fix applied N items []`(대괄호 안에 실패 목록).
- 그림 위치는 안건 제목을 원문에서 순서대로 찾아 정한다. 제목을 고쳐 쓴 안건은 `_ot`(원래 제목)로 찾는다.

### 별표22·24 (HWP)
- 수식: HWP 수식 스크립트 → `eq2text`(검색용 한 줄) + `eq2tex`(KaTeX LaTeX). 본문에 `\x05한줄\x0eLaTeX\x06` 로 들어가고 template 의 `rich()` 가 그린다. 분수 든 긴 식은 블록(`meqb`), 짧은 식은 글 속(`meq`).
- 그림: HWP BinData(BMP→무손실 webp)를 그림 개체 자리에 `\x10파일|폭|높이\x11` 로 넣음. 표 안에 그림만 있으면 표 대신 그림 줄.

### 연혁집
- 현행 조문 머리(글꼴·x 위치로) 아래 `➥` 블록 = 연혁(제목에서 날짜·허가/시행 기준 추출, 오른쪽 '시행' 표시). 초록/빨강 글자는 `\x01…\x02`/`\x03…\x04`.
- 블록 속 그림·선으로 그린 표·분수식은 원문 영역을 200dpi 로 잘라 `\x10파일|폭|높이\x0e검색용글자\x11` 로 넣는다(글자 대신 그림, 검색은 글자로).
- 기준일 모드: `curStart`/`pickBlock`/`applicable`(template). 엘리베이터 현행 기본 적용일 2019.04.04, 에스컬레이터 2019.03.28.

## 자주 하는 일
- **현장용어 추가**("A = B"): `build/template.html` 의 `BASE_SYN` 에서 같은 뜻 묶음에 넣거나 새 줄 추가 → `python publish.py "현장용어 추가: A = B"`. 넣은 뒤 그 말로 검색해 결과가 맞는지 확인(브라우저 콘솔 `KIJUN.search('A', 6)`).
- **표준화 새 판(예: 26년 3차 반영본)**: `stdzip/std.pdf` 교체 → (2쪽 개인정보 있으면 빈 쪽 처리) → `python make_insp.py` → `python build.py --images` → 새 안건·바뀐 안건 목록을 data.json 과 이전 것을 비교해 뽑고, 요지를 써서 `gists.json` 에 추가 → 원문 대조 검토(섞인 내용·잘린 제목) → 필요하면 `std_fix.json` → publish.
- **요지 쓰기 규칙**: 한 줄, ~110자, 결론 위주. 요지 속 숫자·조항·날짜는 반드시 그 안건 본문/제목에 있어야 함(스크립트로 확인). 꼬리표 제목이면 요지도 `[기타안건]` 등으로 시작. 결론이 없으면 "결론 없음(원문 참조)".
- **연혁집 새 판**: `hist_src/hist.pdf`(또는 `hist_es/hist.pdf`) 교체 → 빌드 → `hist_parse.py` 출력의 `detected/missing/rejected` 확인 → 새 블록 요지는 `hist_*_gist_keyed.json`(키: `조문|블록제목|scope|본문앞60자`).
- **안전기준 개정(HWP 새 판)**: `hwp/b22.hwp`·`b24.hwp` 교체 → 빌드. 연혁집 조문번호와 맞는지 `hist_parse.py` 의 missing 확인.
- 검증 습관: 바꾼 뒤 로컬 서버로 휴대폰 폭(390px)에서 해당 카드를 직접 보고, 대표 검색어(로프브레이크, 행거, 차단기, 포토 등) 결과 순서가 엉뚱하게 바뀌지 않았는지 본다.

## SETUP: 공용 현장용어 서버 배포 (2026-10-14 완료)
- 시트: https://drive.google.com/open?id=1FQxh4BhWzcwN2D6OCCPx9pgs7MFwfeeZq4RxFxYsoz8
- 스크립트 ID `14GUzpo7gzTJG9hLXiVp-mxGU7ucuEa65O8JT66MImdJ0WmbjowBflrpW`, 웹 앱 배포 ID `AKfycbw6jHKm0bHPsAqveMq3wWkQ0ejwE9W4OFCYnmBuHrhq_5af7GyiFl33UEl-VRn2GW0` (config.json 에 들어 있음)
- 다른 PC·새 세션에서 다시 배포하려면: `clasp login` → `gas/.clasp.json` 을 `{"scriptId":"<스크립트 ID>","rootDir":""}` 로 만들고 → `gas/secret.gs` 다시 작성(비밀번호는 사용자에게) → `clasp push -f && clasp deploy -i <배포 ID>`.
- 권한 승인 완료(시크릿 창 편집기에서 doGet 실행). 사용자 브라우저에 구글 계정이 여럿이라 일반 창에선 편집기·웹 앱 관리자 페이지가 "현재 파일을 열 수 없습니다". 그래서 **승인은 시트에서 직접**: '제안' 탭 상태(E열) 드롭다운을 승인/반려로 바꾸면 끝(onEdit 가 처리시각 기록). 시트 주소 `…/spreadsheets/d/<ID>/edit?authuser=qwertyyo119@gmail.com` 는 일반 창에서 열린다. 사이트의 fetch 는 쿠키 없이 익명이라 이 문제와 무관.
- 웹 앱 v2(2026-10-14): 시트 직접 승인용 드롭다운·onEdit 추가.
- 클라우드 세션은 script.google.com 이 네트워크 정책으로 막혀 있어 웹 앱 호출 확인(curl)은 못 한다(clasp 는 API 라 됨). 클라우드에서 `clasp login --no-localhost` 는 사용자가 승인 후 localhost 주소를 붙여 넣으면 된다.

처음 설치 절차(기록용):
목표: 구글 시트(제안 저장) + 웹 앱(제안 접수·승인 목록·관리자 페이지)을 사용자 구글 계정(qwertyyo119@gmail.com)에 만들고, 웹 앱 주소를 `config.json`에 넣어 푸시.

1. `npm i -g @google/clasp` 설치 확인.
2. 사용자에게 https://script.google.com/home/usersettings 에서 **Google Apps Script API**를 켜 달라고 요청(사용자만 가능, 토글 1번).
3. `clasp login` — 브라우저에서 사용자가 구글 계정 승인.
4. `cd gas && clasp create --type sheets --title "현장용어 제안" --rootDir .` → 시트+스크립트 생성(.clasp.json은 커밋하지 말 것).
5. 관리자 비밀번호를 사용자에게 물어서 `gas/secret.gs`에 `const ADMIN_KEY_CONST = '...';` 로 저장(커밋 금지, .gitignore 됨).
6. `clasp push -f` 후 `clasp deploy --description "v1"` → 배포 ID로 웹 앱 주소 `https://script.google.com/macros/s/<배포ID>/exec`.
7. 처음 한 번은 스프레드시트 권한 승인이 필요하다: 사용자에게 웹 앱 주소를 브라우저로 열게 하거나 `clasp open`으로 편집기에서 `doGet`을 한 번 실행해 권한을 허용하게 한다. (승인 전에는 익명 요청이 실패함)
8. 확인: `curl -L "<주소>?action=list"` → `[]`, `curl -L -d "text=테스트 = 시험" "<주소>"` → `{"ok":true,"added":1}`, 시트 '제안'에 '대기' 행 생김.
9. `config.json`의 synApi에 주소를 넣고 커밋·푸시. 1~2분 뒤 사이트에서 '모두가 쓰도록 공유 제안'이 서버로 전송된다.
10. 사용자에게 관리자 주소 `<주소>?action=admin&key=<비밀번호>` 를 알려 준다(즐겨찾기 권장). 승인하면 모든 사용자에게 다음 접속부터 적용.

코드를 고쳐 다시 배포할 때는 `clasp push -f && clasp deploy -i <기존 배포ID>` (주소 유지).
승인된 공용 현장용어는 서버에서 바로 적용되지만, 오래 쓸 말은 `BASE_SYN` 에도 옮겨 두면 서버가 없어도 동작한다.

## 남은 일 / 메모
- 사용자가 예전에 기기에서 추가한 개인 현장용어('내 용어 복사' 결과)를 보내 주면 `BASE_SYN` 에 합친다.
- 원문 자체 오류로 그대로 둔 것: 2023년 2차 5번 슬라이드에 4번 이슈 박스가 복사돼 있음, 4번 관련법령에 승강기번호 표지 조문이 들어 있음.
