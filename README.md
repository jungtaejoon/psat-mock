# PSAT 기출 모의고사

인사혁신처 국가공무원 채용시스템에 공개된 PSAT 기출(5급 공채·외교관, 7급 공채·민경채, 지역인재 7급)을
실제 시험처럼 풀어 보는 정적 웹사이트입니다. → **https://alltests.ai.kr/**

- **연도별 기출**: 시험 계열·연도·영역 선택, 전 영역 연속 응시
- **랜덤 모의고사**: 영역·시험·연도 범위·문항 수를 골라 무작위 출제 (안 푼 문제 우선)
- **실전 모드**: 실제 시험 기준 제한 시간(40문항 90분, 25문항 60분), OMR 답안지, 제출 후 채점
- **연습 모드**: 문항마다 바로 채점, 해설 보기
- **기록·오답노트**: 브라우저에 풀이 기록 저장, 틀린 문제만 다시 풀기
- **AI 해설**: 문항별 풀이·선택지 판단·시간 단축 요령 (Claude 생성, 사용자가 원할 때만 열람)

## 구조

```
pipeline/scrape.py    공식 API → 문제 PDF + 정답 수집 (data/catalog.json, data/raw/)
pipeline/segment.py   PDF → 문항별 좌표·텍스트 (web/public/data/papers/*.json)
pipeline/explain.py   문항 이미지 → Claude Batches API → 해설 (web/public/data/explanations/*.json)
web/                  Vite + React 정적 사이트. pdf.js 로 문항 영역만 잘라 렌더링
.github/workflows/update.yml   매일 신규 시험 수집 → 분할 → 해설 → GitHub Pages 배포
```

### 데이터 출처 API (gongmuwon.gosi.kr)

| 용도 | 엔드포인트 |
|---|---|
| 시험별 과목 | `POST /oprut/EvmArChcPrblmCransSbjctLst.do` (testCd) |
| 연도별 문제 목록 | `POST /oprut/EvmArChcPrblmCransSbjctInqSbjctTblLst.do` |
| 정답 (모의고사용, 비트마스크) | `POST /oprut/EvmArSimuTestSbjctPstIdOne.do` → `wholAnswVl1` |
| 구형 시험 정답 | `GET /oprut/GosiJungdap.do` (HTML) |
| 당해 연도 정답 | 정답 공개 게시글 첨부 PDF(정답표) |
| 첨부 파일 경로 | `POST /oprut/GetAtchFileLst.do` → `/rccom/view{filePathNm}` |

당해 연도 문제 PDF 는 RAONK 다운로더로만 내려받을 수 있어 Playwright 를 씁니다.

## 로컬 실행

```bash
python3 -m venv .venv && .venv/bin/pip install -r pipeline/requirements.txt
.venv/bin/python -m playwright install chromium
.venv/bin/python pipeline/scrape.py
.venv/bin/python pipeline/segment.py
ANTHROPIC_API_KEY=... .venv/bin/python pipeline/explain.py run --limit 20   # 선택
cd web && npm install && npm run dev
```

## 배포 설정 (GitHub)

- Settings → Pages → Source: **GitHub Actions**
- Variables (해설 생성용, Workload Identity Federation — 저장된 API 키 없음. 없으면 해설 단계만 건너뜀): `ANTHROPIC_FEDERATION_RULE_ID`, `ANTHROPIC_ORGANIZATION_ID`, `ANTHROPIC_SERVICE_ACCOUNT_ID`, (규칙이 여러 워크스페이스에 걸치면) `ANTHROPIC_WORKSPACE_ID`
- Variables (선택): `CONTACT` 게시 중단 요청 연락처, `AD_CLIENT` 광고 클라이언트 ID

## 유료화 전환 지점

`web/src/monetization.tsx` 의 `canViewExplanation()` 과 `<AdSlot/>`, 그리고 풀이 기록을 담당하는
`web/src/store.ts` 만 바꾸면 회원제·구독·광고로 전환할 수 있게 분리해 두었습니다.
