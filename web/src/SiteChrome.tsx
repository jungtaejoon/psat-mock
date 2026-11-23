/** 모든 화면(시험 중 제외) 공통 머리글·꼬리말 */
import { navigate } from "./router";
import { CATEGORIES, EXAMS } from "./exams";

const CONTACT = import.meta.env.VITE_CONTACT as string | undefined;

export function Logo() {
  // OMR 답안지의 칠한 칸을 본뜬 표시
  return (
    <svg className="logo-mark" viewBox="0 0 28 28" aria-hidden="true">
      <rect x="1" y="1" width="26" height="26" rx="7" fill="var(--brand)" />
      <circle cx="9" cy="10" r="3" fill="none" stroke="var(--brand-ink)" strokeWidth="1.6" />
      <circle cx="19" cy="10" r="3.4" fill="var(--brand-ink)" />
      <circle cx="9" cy="19" r="3.4" fill="var(--brand-ink)" />
      <circle cx="19" cy="19" r="3" fill="none" stroke="var(--brand-ink)" strokeWidth="1.6" />
    </svg>
  );
}

export function SiteHeader() {
  const go = (cat?: string) => {
    const onHub = window.location.hash.replace(/^#\/?/, "") === "";
    const jump = () => document.getElementById(`cat-${cat}`)?.scrollIntoView({ block: "start" });
    if (cat && onHub) return jump();
    navigate("/");
    if (cat) setTimeout(jump, 120);
  };
  return (
    <header className="site-head">
      <div className="site-head-in">
        <a className="brand" href="#/" onClick={(e) => (e.preventDefault(), go())}>
          <Logo />
          <span className="brand-name">올테스트</span>
          <span className="brand-sub">기출 모의고사</span>
        </a>
        <nav className="site-nav" aria-label="시험 분류">
          {CATEGORIES.map((c) => (
            <button key={c} type="button" onClick={() => go(c)}>
              {c}
            </button>
          ))}
        </nav>
      </div>
    </header>
  );
}

export function SiteFooter({ source }: { source?: string }) {
  const live = EXAMS.filter((e) => e.status === "live");
  return (
    <footer className="site-foot">
      <div className="site-foot-in">
        <div className="foot-brand">
          <a className="brand" href="#/" onClick={(e) => (e.preventDefault(), navigate("/"))}>
            <Logo />
            <span className="brand-name">올테스트</span>
          </a>
          <p>
            공무원·자격증 기출문제를 실제 시험처럼 풀고, 공식 정답과 문항별 해설로 복습하는 무료 모의고사입니다.
          </p>
        </div>
        <nav className="foot-links" aria-label="시험별 기출문제 목록">
          <h2>시험별 기출문제 정답·해설</h2>
          <ul>
            {live.map((e) => (
              <li key={e.id}>
                <a href={`/${e.seo ?? e.id}/`}>{e.name} 기출문제</a>
              </li>
            ))}
          </ul>
        </nav>
      </div>
      <p className="foot-note">
        문제·정답 출처:{" "}
        {source ?? "각 시험 시행 기관(인사혁신처, 한국산업인력공단 등), 공공누리 표시 자료. 시험별 출처는 각 시험 화면에 표시합니다"}
        . 해설은 AI가 작성했으며 공식 해설이 아니고 오류가 있을 수 있습니다.
        {CONTACT && (
          <>
            {" "}
            저작권 문의·게시 중단 요청은{" "}
            <a href={CONTACT.includes("@") ? `mailto:${CONTACT}` : CONTACT}>여기</a>로 보내 주세요.
          </>
        )}
      </p>
    </footer>
  );
}
