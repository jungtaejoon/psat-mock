/**
 * 자체 광고: slop.ai.kr (AI가 만든 것들을 써 보고 ▲보석 ▼슬롭으로 판정하는 커뮤니티).
 * PSAT 문항 모양을 빌려 "판정"이라는 공통점으로 잇는다. 시험 화면(Exam)에는 넣지 않는다.
 */
import { useState } from "react";

const URL = "https://slop.ai.kr/?utm_source=alltests&utm_medium=house_ad#/judge";

const QUESTIONS = [
  {
    stem: "다음 중 AI가 만든 앱을 판정하는 방법으로 가장 적절한 것은?",
    choices: ["설명만 읽고 보석이라 믿는다", "AI가 만들었으니 슬롭이라 단정한다", "직접 써 보고 ▲보석 ▼슬롭을 고른다"],
    answer: 2,
    verdict: "정답 ③. 근거 없이 판단하지 않는 것, PSAT이랑 똑같죠.",
  },
  {
    stem: "<보기>의 진술 중 참인 것만을 고르면?",
    choices: ["ㄱ. AI가 만든 것은 전부 슬롭이다", "ㄴ. AI가 만든 것은 전부 보석이다", "ㄷ. 써 봐야 어느 쪽인지 안다"],
    answer: 2,
    verdict: "정답 ③(ㄷ). ㄱ·ㄴ은 전칭 명제라 반례 하나면 거짓이에요.",
  },
  {
    stem: "기출을 다 풀어 판단력이 오른 수험생이 쉬는 시간에 할 일로 가장 적절한 것은?",
    choices: ["판단력을 그냥 쉬게 둔다", "또 같은 문제를 푼다", "AI가 만든 게임·앱을 판정해 본다"],
    answer: 2,
    verdict: "정답 ③. 5분이면 카드 몇 장 넘기며 판정할 수 있어요.",
  },
];

function Gem() {
  return (
    <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true">
      <path d="M6 3h12l4 6-10 12L2 9z" fill="currentColor" opacity=".9" />
      <path d="M2 9h20M9 3l3 18M15 3l-3 18M6 3l3 6M18 3l-3 6" stroke="var(--slop-bg)" strokeWidth="1.1" fill="none" />
    </svg>
  );
}

export default function SlopAd() {
  // 날짜마다 다른 문항 (같은 날엔 고정)
  const [q] = useState(() => QUESTIONS[Math.floor(Date.now() / 86_400_000) % QUESTIONS.length]);
  const [picked, setPicked] = useState<number | null>(null);

  return (
    <aside className="slop-ad" aria-label="광고: Slop">
      <div className="slop-ad-head">
        <span className="slop-ad-brand">
          <Gem />
          <b>Slop.</b>
          <span>AI가 만든 것들 속에서 보석을 캐는 곳</span>
        </span>
        <span className="slop-ad-tag">광고</span>
      </div>
      <p className="slop-ad-stem">
        <b>문 41.</b> {q.stem}
      </p>
      <ol className="slop-ad-choices">
        {q.choices.map((c, i) => (
          <li key={i}>
            <button
              className={picked === null ? "" : i === q.answer ? "ok" : i === picked ? "no" : "dim"}
              onClick={() => setPicked(i)}
              disabled={picked !== null}
            >
              <span className="n">{"①②③"[i]}</span>
              {c}
            </button>
          </li>
        ))}
      </ol>
      <div className="slop-ad-foot">
        <span>{picked === null ? "PSAT이 참·거짓을 가린다면, Slop은 보석·슬롭을 가려요." : q.verdict}</span>
        <a className="slop-ad-cta" href={URL} target="_blank" rel="noopener">
          ▲▼ 판정하러 가기
        </a>
      </div>
    </aside>
  );
}
