# 수험생 이야기 (댓글·감정 반응) 백엔드

Supabase 프로젝트 `alltests` (ref `hzyvylezebigwugffxii`, 서울). 스키마는 프로젝트 마이그레이션 기록 `20261123063055_talk_comments_reactions` 에 있고, 프런트는 `web/src/talk/`.

- `comments`: 시험(`x:<examId>`)·문항(`q:<paperId>:<no>`)별 댓글. 읽기는 누구나(숨김 제외), 쓰기는 로그인한 회원만(익명 세션 불가), 5분에 5개.
  작성자 이름은 로그인 정보(닉네임/이름)에서 서버가 넣는다. 지우기는 본인만.
- `reactions`: 감정 반응(어려워요·헷갈려요·쉬웠어요·좋은 문제·정답 이상해요). 로그인 없이 기기 id 로 한 번씩, 함수(`toggle_reaction`, `get_reactions`)로만 접근.
- `comment_reports`: 서로 다른 기기 3곳이 신고하면 댓글을 자동으로 숨긴다(`report_comment`). 운영자는 대시보드에서 `hidden` 을 직접 바꿀 수 있다.
- 실전 모드(시험 중)에는 화면에 넣지 않는다. 연습 모드는 정답 확인 뒤, 결과 화면은 문항을 펼쳤을 때. "숨기기"는 기기에 저장돼 모든 화면에 적용.

## 로그인 켜기 (운영자가 직접)

1. Supabase 대시보드 → Authentication → URL Configuration: Site URL `https://alltests.ai.kr`, Redirect URLs 에 `https://alltests.ai.kr/**`, `http://localhost:5173/**`
2. Authentication → Sign In / Providers 에서 Kakao·Google 을 켜고, 각 개발자 콘솔에서 만든 Client ID·Secret 을 넣는다.
   콜백 URL 은 `https://hzyvylezebigwugffxii.supabase.co/auth/v1/callback`
3. `web/src/talk/api.ts` 의 `PROVIDERS` 에 켠 방법을 넣고 배포한다.

무료 플랜 프로젝트는 1주일 동안 요청이 없으면 일시 정지된다(대시보드에서 다시 켤 수 있음).
