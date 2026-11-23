# 수험생 이야기 (댓글·감정 반응) 백엔드

Supabase 프로젝트 `alltests` (ref `hzyvylezebigwugffxii`, 서울, 무료 플랜). 스키마는 프로젝트 마이그레이션 기록
`talk_comments_reactions`, `anonymous_comments`, `talk_year_targets` 에 있고, 프런트는 `web/src/talk/`.

로그인 없이 쓴다. 브라우저마다 무작위 기기 id(`localStorage alltests.device`)와 닉네임(`alltests.talk.name`)을 둔다.
표에는 직접 접근할 수 없고(권한 회수, RLS 정책 없음) 아래 함수로만 읽고 쓴다.

| 함수 | 하는 일 |
|---|---|
| `list_comments(target, device, limit)` | 숨김 제외 최신순. 기기 id 는 돌려주지 않고 `mine`(내 글인지)만 |
| `add_comment(target, body, mood, name, device)` | 2~1000자, 링크 금지, 같은 글 하루 1번. 기기당 1분 3개·1시간 20개, 접속 주소(해시)당 1시간 30개, 대상당 1분 20개. 운영자·관리자 같은 닉네임은 "수험생"으로 |
| `delete_comment(id, device)` | 쓴 기기에서만 |
| `report_comment(id, device)` | 서로 다른 기기 3곳이 신고하면 숨김 |
| `count_comments(targets)` | 여러 대상의 댓글 수 (연도 목록의 💬 숫자) |
| `toggle_reaction` / `get_reactions` | 감정 반응(어려워요·헷갈려요·쉬웠어요·좋은 문제·정답 이상해요), 기기당 한 번씩 |

- 대상(target): 시험 `x:<examId>`, 연도·회차 `y:<examId>:<계열(URL 인코딩)>:<연도>`, 문항 `q:<paperId>:<no>`
- 접속 주소는 원문 대신 해시(`ip_hash`)로만 저장한다.
- 운영: 대시보드 Table Editor 에서 `comments.hidden` 을 바꾸면 숨기거나 되살릴 수 있다.
- 화면: 실전 모드(시험 중)에는 넣지 않는다. 연습 모드는 정답 확인 뒤, 결과 화면은 문항을 펼쳤을 때, 시험 첫 화면은 "수험생 이야기" 탭과 연도별 목록의 💬 버튼(계열·연도별, 예: 2024년 1차).
  "숨기기"는 기기에 저장돼 모든 화면에 적용.
- 무료 플랜 프로젝트는 1주일 동안 요청이 없으면 일시 정지된다(대시보드에서 다시 켤 수 있음).
