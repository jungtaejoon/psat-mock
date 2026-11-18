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
  from: number;
  to: number;
}

function ExamCard({ exam, stat }: { exam: ExamDef; stat?: Stat }) {
  const live = exam.status === "live" && !!stat;
  const body = (
    <>
      <span className="ex-name">{exam.name}</span>
      <span className="ex-desc">{exam.desc}</span>
      {live ? (
        <span className="ex-stat">
          {stat.from}–{stat.to} · {stat.questions.toLocaleString()}문항
          {stat.explained >= stat.questions
            ? " · 전 문항 해설"
            : stat.explained > 0
              ? ` · 해설 ${Math.round((stat.explained / stat.questions) * 100)}%`
              : ""}
        </span>
      ) : (
        <span className="ex-soon">준비 중</span>
      )}
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
        from: p.year,
        to: p.year,
      };
      s.papers++;
      s.questions += p.count;
      s.explained += p.explained ?? 0;
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

  return (
    <div className="home-wrap">
      <div className="home">
        <header className="hero">
          <h1>기출 모의고사 alltests</h1>
          <p>
            공무원·자격증 시험 기출문제를 실제 시험처럼 풀고, 문항마다 해설로
            복습하세요. 타이머·답안지 실전 모드, 랜덤 모의고사, 오답노트를
            무료로 씁니다.
            {total > 0 && (
              <>
                <br />
                <strong>
                  지금 {total.toLocaleString()}문항 · 시험은 계속 늘어나요
                </strong>
              </>
            )}
          </p>
        </header>

        {recent.length > 0 && (
          <section className="recent">
            <h2>이어서 풀기</h2>
            <ul>
              {recent.map((s) => (
                <li key={s.id}>
                  <button
                    className="link"
                    onClick={() =>
                      navigate(
                        s.finishedAt ? `/result/${s.id}` : `/exam/${s.id}`,
                      )
                    }
                  >
                    <span className="h-title">{s.title}</span>
                    <span className="muted">
                      {getExam(s.exam ?? "psat")?.name} ·{" "}
                      {s.finishedAt
                        ? "채점 완료"
                        : `진행 중 ${Object.keys(s.answers).length}/${s.items.length}`}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </section>
        )}

        <input
          className="ex-search"
          type="search"
          placeholder="시험 이름으로 찾기 (예: PSAT, 공인중개사)"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          aria-label="시험 찾기"
        />

        <div className="ad-inline">
          <SlopAd />
        </div>

        {CATEGORIES.map((cat) => {
          const list = sorted(
            EXAMS.filter((e) => e.category === cat && match(e)),
          );
          if (!list.length) return null;
          return (
            <section key={cat} className="ex-cat">
              <h2>{cat}</h2>
              <div className="ex-grid">
                {list.map((e) => (
                  <ExamCard key={e.id} exam={e} stat={stats.get(e.id)} />
                ))}
              </div>
            </section>
          );
        })}
        {needle && !EXAMS.some(match) && (
          <p className="muted empty">"{needle}"에 맞는 시험이 아직 없어요.</p>
        )}
      </div>
      <aside className="side-rail">
        <SlopAd />
      </aside>
    </div>
  );
}
