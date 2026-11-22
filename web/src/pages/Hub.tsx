/** 사이트 첫 화면: 분야별 시험 목록과 최근 기록 */
import { useEffect, useMemo, useState } from "react";
import { loadIndex } from "../data";
import { listSessions } from "../store";
import { navigate } from "../router";
import SlopAd from "../SlopAd";
import { CATEGORIES, EXAMS, examOf, getExam, type ExamDef } from "../exams";
import type { PaperMeta } from "../types";

interface Stat {
  papers: number;
  questions: number;
  explained: number;
  text: number;
  from: number;
  to: number;
}

const CAT_TONE: Record<string, string> = {
  공무원: "t1",
  "부동산·안전": "t2",
  "법률·행정·경영": "t3",
  "보건·복지·교육": "t4",
  "문화·관광·물류": "t5",
};

function ExamCard({ exam, stat }: { exam: ExamDef; stat?: Stat }) {
  const live = exam.status === "live" && !!stat;
  const initial = exam.name.replace(/[0-9급\s]/g, "").slice(0, 1) || exam.name.slice(0, 1);
  const body = (
    <>
      <span className={`ex-mark ${CAT_TONE[exam.category] ?? "t1"}`} aria-hidden="true">
        {exam.id === "psat" ? "P" : /^\d/.test(exam.name) ? exam.name.match(/^\d+/)![0] : initial}
      </span>
      <span className="ex-main">
        <span className="ex-name">{exam.name}</span>
        <span className="ex-desc">{exam.desc}</span>
        {live ? (
          <span className="ex-meta">
            <span>
              {stat.from}–{stat.to}
            </span>
            <span>{stat.questions.toLocaleString()}문항</span>
            {stat.text >= stat.questions * 0.5 && <span className="tag">텍스트</span>}
            {stat.explained > 0 && (
              <span className="tag ok">
                해설{stat.explained >= stat.questions ? "" : ` ${Math.round((stat.explained / stat.questions) * 100)}%`}
              </span>
            )}
          </span>
        ) : (
          <span className="ex-soon">준비 중</span>
        )}
      </span>
    </>
  );
  return live ? (
    <a
      className="ex-card"
      href={`#/x/${exam.id}`}
      onClick={(e) => (e.preventDefault(), navigate(`/x/${exam.id}`))}
    >
      {body}
    </a>
  ) : (
    <div className="ex-card soon" aria-disabled="true">
      {body}
    </div>
  );
}

const POPULAR = ["gong9", "psat", "realtor", "social1", "gong7"];

export default function Hub() {
  const [papers, setPapers] = useState<PaperMeta[] | null>(null);
  const [q, setQ] = useState("");
  useEffect(() => {
    loadIndex().then(setPapers);
  }, []);

  const stats = useMemo(() => {
    const m = new Map<string, Stat>();
    for (const p of papers ?? []) {
      const id = examOf(p).id;
      const s = m.get(id) ?? {
        papers: 0,
        questions: 0,
        explained: 0,
        text: 0,
        from: p.year,
        to: p.year,
      };
      s.papers++;
      s.questions += p.count;
      s.explained += p.explained ?? 0;
      s.text += p.text ?? 0;
      s.from = Math.min(s.from, p.year);
      s.to = Math.max(s.to, p.year);
      m.set(id, s);
    }
    return m;
  }, [papers]);

  const total = EXAMS.filter((e) => e.status === "live").reduce(
    (n, e) => n + (stats.get(e.id)?.questions ?? 0),
    0,
  );
  const needle = q.trim();
  const match = (e: ExamDef) =>
    !needle || `${e.name} ${e.desc} ${e.category}`.includes(needle);
  // 열린 시험 먼저, 그다음 준비 중
  const isLive = (e: ExamDef) => e.status === "live" && stats.has(e.id);
  const sorted = (list: ExamDef[]) =>
    [...list].sort(
      (a, b) =>
        Number(isLive(b)) - Number(isLive(a)) ||
        EXAMS.indexOf(a) - EXAMS.indexOf(b),
    );
  const recent = listSessions().slice(0, 3);

  const liveExams = EXAMS.filter((e) => e.status === "live" && stats.has(e.id));
  const paperCount = papers?.length ?? 0;

  return (
    <div className="home-wrap">
      <div className="home">
        <header className="hub-hero">
          <p className="eyebrow">공무원 · PSAT · 국가전문자격</p>
          <h1>
            기출문제, <em>실제 시험처럼</em> 풀고
            <br />
            해설로 복습하세요
          </h1>
          <p className="lede">
            타이머와 OMR 답안지로 실전처럼 풀고, 공식 정답으로 바로 채점합니다. 문제는 원본 PDF 그대로 또는 읽기 쉬운 텍스트로 볼 수 있어요. 모두 무료입니다.
          </p>
          <label className="hub-search">
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <circle cx="11" cy="11" r="7" fill="none" stroke="currentColor" strokeWidth="2" />
              <path d="M20 20l-4-4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
            </svg>
            <input
              type="search"
              placeholder="시험 이름 검색 (예: 9급, 공인중개사)"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              aria-label="시험 찾기"
            />
          </label>
          <div className="quick">
            {POPULAR.map((id) => getExam(id))
              .filter((e): e is ExamDef => !!e && stats.has(e.id))
              .map((e) => (
                <button key={e.id} type="button" className="chip" onClick={() => navigate(`/x/${e.id}`)}>
                  {e.name}
                </button>
              ))}
          </div>
          {total > 0 && (
            <dl className="hub-stats">
              <div>
                <dt>시험</dt>
                <dd>{liveExams.length}</dd>
              </div>
              <div>
                <dt>문제지</dt>
                <dd>{paperCount.toLocaleString()}</dd>
              </div>
              <div>
                <dt>문항</dt>
                <dd>{total.toLocaleString()}</dd>
              </div>
              <div>
                <dt>이용료</dt>
                <dd>무료</dd>
              </div>
            </dl>
          )}
        </header>

        {recent.length > 0 && (
          <section className="recent">
            <h2>이어서 풀기</h2>
            <ul>
              {recent.map((s) => (
                <li key={s.id}>
                  <button
                    className="recent-card"
                    onClick={() => navigate(s.finishedAt ? `/result/${s.id}` : `/exam/${s.id}`)}
                  >
                    <span className="h-title">{s.title}</span>
                    <span className="muted">
                      {getExam(s.exam ?? "psat")?.name} ·{" "}
                      {s.finishedAt ? "채점 완료" : `진행 중 ${Object.keys(s.answers).length}/${s.items.length}`}
                    </span>
                    {!s.finishedAt && (
                      <span className="bar" aria-hidden="true">
                        <span style={{ width: `${(Object.keys(s.answers).length / s.items.length) * 100}%` }} />
                      </span>
                    )}
                  </button>
                </li>
              ))}
            </ul>
          </section>
        )}

        <div className="ad-inline">
          <SlopAd />
        </div>

        {CATEGORIES.map((cat) => {
          const list = sorted(EXAMS.filter((e) => e.category === cat && match(e)));
          if (!list.length) return null;
          return (
            <section key={cat} className="ex-cat" id={`cat-${cat}`}>
              <h2>
                {cat}
                <span className="count">{list.filter(isLive).length}개 시험</span>
              </h2>
              <div className="ex-grid">
                {list.map((e) => (
                  <ExamCard key={e.id} exam={e} stat={stats.get(e.id)} />
                ))}
              </div>
            </section>
          );
        })}
        {needle && !EXAMS.some(match) && <p className="muted empty">"{needle}"에 맞는 시험이 아직 없어요.</p>}
      </div>
      <aside className="side-rail">
        <SlopAd />
      </aside>
    </div>
  );
}
