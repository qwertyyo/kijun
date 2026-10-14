# 검사기준 통합검색 (qwertyyo/kijun)

GitHub Pages 정적 사이트: https://qwertyyo.github.io/kijun/
- `index.html` — 검색 페이지 전체(데이터 내장). **직접 고치지 말 것**: 원본 빌드는 Claude 클라우드 세션에서 하고 통째로 덮어쓴다.
- `stdimg/` — 표준화 그림
- `config.json` — `{"synApi": "<Apps Script 웹 앱 /exec 주소>"}`. 공용 현장용어(관리자 승인) 기능의 서버 주소. 비어 있으면 기능 꺼짐. **이 파일은 여기서 고쳐도 된다.**
- `gas/` — 공용 현장용어 서버(Google Apps Script). 아래 SETUP 절차로 사용자 구글 계정에 배포한다.

## SETUP: 공용 현장용어 서버 배포 (Claude Code가 사용자 PC에서 수행)
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
