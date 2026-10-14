/**
 * 검사기준 통합검색 — 현장용어 제안·승인 서버 (Google Apps Script 웹 앱)
 * 시트 '제안' 열: 시각 | 현장용어 | 기준용어 | 메모 | 상태(대기/승인/반려) | 처리시각
 *  - 사이트 → POST  (제안 접수, 상태 '대기')
 *  - 사이트 → GET ?action=list           (승인된 것만 JSON: [["가바나","조속기"], ...])
 *  - 관리자 → GET ?action=admin&key=...  (대기 목록 + 승인/반려 버튼 페이지)
 *  - 또는 시트에서 바로: 상태 칸 드롭다운을 '승인'/'반려'로 바꾸면 처리시각이 자동 기록(onEdit)
 *    (브라우저에 구글 계정이 여럿이면 웹 앱 관리자 페이지가 안 열리므로 이 방법을 쓴다)
 * 관리자 키: 프로젝트 설정 > 스크립트 속성에 ADMIN_KEY 로 저장
 */
const SHEET = '제안';

function sheet_() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sh = ss.getSheetByName(SHEET);
  if (!sh) { sh = ss.insertSheet(SHEET); sh.appendRow(['시각', '현장용어', '기준용어', '메모', '상태', '처리시각']); sh.setFrozenRows(1); }
  return sh;
}
const clean_ = s => String(s || '').replace(/[\r\n\t]/g, ' ').trim().slice(0, 60);
const json_ = o => ContentService.createTextOutput(JSON.stringify(o)).setMimeType(ContentService.MimeType.JSON);
// 관리자 키: 스크립트 속성 ADMIN_KEY, 없으면 secret.gs 의 ADMIN_KEY_CONST (secret.gs 는 GitHub에 올리지 않음)
const adminKey_ = () => PropertiesService.getScriptProperties().getProperty('ADMIN_KEY') || (typeof ADMIN_KEY_CONST !== 'undefined' ? ADMIN_KEY_CONST : '');
const isAdmin_ = key => !!key && key === adminKey_();

// 제안 접수: 본문은 "현장용어 = 기준용어1, 기준용어2" 줄들(text) 또는 a/b 필드
function doPost(e) {
  const p = (e && e.parameter) || {};
  const lines = (p.text || (p.a ? p.a + ' = ' + (p.b || '') : '')).split(/\n/).slice(0, 50);
  const sh = sheet_(), now = new Date(); let n = 0;
  lines.forEach(line => {
    const m = line.split(/[=＝→]/); if (m.length < 2) return;
    const a = clean_(m[0]), b = clean_(m.slice(1).join(','));
    if (!a || !b || a.length > 30) return;
    sh.appendRow([now, a, b, clean_(p.note), '대기', '']); n++;
  });
  if (n) statusDropdown_(sh);
  return json_({ ok: true, added: n });
}

// 상태 칸(E열)을 대기/승인/반려 드롭다운으로
function statusDropdown_(sh) {
  const rule = SpreadsheetApp.newDataValidation().requireValueInList(['대기', '승인', '반려'], true).setAllowInvalid(false).build();
  sh.getRange(2, 5, Math.max(sh.getLastRow() - 1, 1), 1).setDataValidation(rule);
}

// 시트에서 상태를 직접 바꾸면 처리시각 기록 (단순 트리거라 따로 설정 불필요)
function onEdit(e) {
  const r = e && e.range;
  if (!r || r.getSheet().getName() !== SHEET || r.getColumn() > 5 || r.getLastColumn() < 5 || r.getRow() < 2) return;
  r.getSheet().getRange(Math.max(r.getRow(), 2), 6, r.getLastRow() - Math.max(r.getRow(), 2) + 1, 1).setValue(new Date());
}

function doGet(e) {
  const p = (e && e.parameter) || {};
  if (p.action === 'list') {
    const rows = sheet_().getDataRange().getValues().slice(1).filter(r => r[4] === '승인');
    return json_(rows.map(r => [String(r[1])].concat(String(r[2]).split(/[,，/]/).map(s => s.trim()).filter(Boolean))));
  }
  if (p.action === 'admin') {
    if (!isAdmin_(p.key)) return HtmlService.createHtmlOutput('<p style="font:16px sans-serif;padding:20px">관리자 키가 맞지 않습니다.</p>');
    const t = HtmlService.createTemplate(ADMIN_HTML); t.key = p.key;
    return t.evaluate().setTitle('현장용어 승인').addMetaTag('viewport', 'width=device-width, initial-scale=1');
  }
  return json_({ ok: true });
}

// 관리자 페이지에서 호출
function adminList(key) {
  if (!isAdmin_(key)) throw new Error('권한 없음');
  return sheet_().getDataRange().getValues().slice(1).map((r, i) => ({ row: i + 2, at: String(r[0]), a: r[1], b: r[2], note: r[3], st: r[4] })).reverse();
}
function adminSet(key, row, status, b) {
  if (!isAdmin_(key)) throw new Error('권한 없음');
  const sh = sheet_();
  if (b != null) sh.getRange(row, 3).setValue(clean_(b));
  sh.getRange(row, 5, 1, 2).setValues([[status, new Date()]]);
  return true;
}

const ADMIN_HTML = `<!doctype html><html><head><base target="_top"><style>
body{font:15px -apple-system,"Apple SD Gothic Neo","Malgun Gothic",sans-serif;margin:0;padding:14px;background:#f6f7f9;color:#16202b}
h1{font-size:18px;margin:0 0 10px} .tabs button{font:inherit;padding:5px 12px;border:1px solid #ccd;border-radius:999px;background:#fff;margin-right:4px}
.tabs button.on{background:#0f5f8c;color:#fff;border-color:#0f5f8c}
.it{background:#fff;border:1px solid #dde;border-radius:10px;padding:10px;margin:8px 0}
.it b{font-size:16px} .it input{font:inherit;width:100%;box-sizing:border-box;padding:6px;margin:6px 0;border:1px solid #ccd;border-radius:6px}
.it small{color:#667} .act button{font:inherit;padding:6px 14px;border-radius:7px;border:0;margin-right:6px}
.ok{background:#1f7a4d;color:#fff}.no{background:#e5e7eb}.st{float:right;font-size:12px;color:#667}
</style></head><body><h1>현장용어 제안 승인</h1>
<div class="tabs"><button data-f="대기" class="on">대기</button><button data-f="승인">승인됨</button><button data-f="반려">반려</button></div>
<div id="list">불러오는 중…</div>
<script>
const KEY = <?= JSON.stringify(key) ?>; let F = '대기', ALL = [];
const esc = s => String(s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
function load(){ google.script.run.withSuccessHandler(r => { ALL = r; draw(); }).adminList(KEY); }
function draw(){ const L = ALL.filter(x => x.st === F);
  document.getElementById('list').innerHTML = L.length ? L.map(x => '<div class="it"><span class="st">'+esc(x.at.slice(0,21))+'</span><b>'+esc(x.a)+'</b> = <input value="'+esc(x.b)+'" id="b'+x.row+'">'+(x.note?'<small>'+esc(x.note)+'</small><br>':'')+'<div class="act">'+(F!=='승인'?'<button class="ok" data-r="'+x.row+'" data-s="승인">승인</button>':'')+(F!=='반려'?'<button class="no" data-r="'+x.row+'" data-s="반려">'+(F==='승인'?'승인 취소':'반려')+'</button>':'')+'</div></div>').join('') : '<p>없음</p>'; }
document.addEventListener('click', ev => { const t = ev.target;
  if (t.dataset.f) { F = t.dataset.f; document.querySelectorAll('.tabs button').forEach(b => b.classList.toggle('on', b === t)); draw(); }
  if (t.dataset.r) { t.disabled = true; const r = +t.dataset.r, b = document.getElementById('b'+r).value;
    google.script.run.withSuccessHandler(load).adminSet(KEY, r, t.dataset.s, b); } });
load();
</script></body></html>`;
