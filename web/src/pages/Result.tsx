import { useEffect, useMemo, useState } from "react";
import { CIRCLED, examGroup, loadPaper } from "../data";
import { getSession, newSession } from "../store";
import { navigate } from "../router";
import { ExplanationPanel, QuestionImage } from "../QuestionView";
import { AdSlot } from "../monetization";
import SlopAd from "../SlopAd";
import { SUBJECTS, type Paper } from "../types";

function fmtMin(sec: number) {
  const m = Math.floor(sec / 60);
  return `${m}분 ${Math.floor(sec % 60)}초`;
}

export default function Result({ id }: { id: string }) {
  const s = getSession(id);
  const [papers, setPapers] = useState<Map<string, Paper> | null>(null);
  const [onlyWrong, setOnlyWrong] = useState(false);
  const [open, setOpen] = useState<number | null>(null);

  useEffect(() => {
    if (!s) return;
    Promise.all([...new Set(s.items.map((r) => r.paperId))].map(loadPaper)).then((ps) => setPapers(new Map(ps.map((p) => [p.id, p]))));
  }, [id]); // eslint-disable-line react-hooks/exhaustive-deps

  const rows = useMemo(() => {
    if (!s || !papers) return [];
    return s.items.map((r, i) => {
      const p = papers.get(r.paperId)!;
      const q = p.questions.find((x) => x.no === r.no)!;
      const mine = s.answers[i];
      return { i, ref: r, paper: p, q, mine, ok: mine !== undefined && q.answer.includes(mine) };
    });
  }, [s, papers]);

  if (!s) return <div className="center">기록을 찾을 수 없습니다.</div>;
  if (!papers) return <div className="skeleton tall" />;

  const correct = rows.filter((r) => r.ok).length;
  const score = Math.round((correct / rows.length) * 1000) / 10;
  const bySubj = SUBJECTS.map((sub) => {
    const rs = rows.filter((r) => r.paper.subject === sub);
    return { sub, n: rs.length, c: rs.filter((r) => r.ok).length };
  }).filter((x) => x.n);
  const wrong = rows.filter((r) => !r.ok);

  return (
    <div className="result">
      <div className="exam-bar">
        <button className="btn ghost sm" onClick={() => navigate("/")}>
          ← 처음으로
        </button>
        <div className="exam-title">{s.title} · 채점 결과</div>
      </div>

      <section className="score-card">
        <div className="score">
          <span className="big">{score}</span>
          <span>점</span>
        </div>
        <div className="score-meta">
          <div>
            {correct} / {rows.length} 정답 · 풀이 시간 {fmtMin(s.elapsedSec)}
            {s.timeLimitSec > 0 && ` (제한 ${s.timeLimitSec / 60}분)`}
          </div>
          <div className="subj-scores">
            {bySubj.map((x) => (
              <div key={x.sub} className="subj-score">
                <span>{x.sub}</span>
                <div className="bar">
                  <i style={{ width: `${(x.c / x.n) * 100}%` }} />
                </div>
                <span>
                  {x.c}/{x.n}
                </span>
              </div>
            ))}
          </div>
        </div>
        {wrong.length > 0 && (
          <button
            className="btn primary"
            onClick={() => {
              const ns = newSession({ title: `${s.title} 오답 다시 풀기`, mode: "practice", items: wrong.map((r) => r.ref), timeLimitSec: 0 });
              navigate(`/exam/${ns.id}`);
            }}
          >
            틀린 {wrong.length}문항 다시 풀기
          </button>
        )}
      </section>

      <SlopAd />
      <AdSlot slot="result-top" />

      <div className="row between list-head">
        <strong>문항별 결과</strong>
        <label className="check">
          <input type="checkbox" checked={onlyWrong} onChange={(e) => setOnlyWrong(e.target.checked)} /> 틀린 문제만
        </label>
      </div>

      <ul className="result-list">
        {rows
          .filter((r) => !onlyWrong || !r.ok)
          .map((r) => (
            <li key={r.i} className={r.ok ? "ok" : "no"}>
              <button className="result-row" onClick={() => setOpen(open === r.i ? null : r.i)} aria-expanded={open === r.i}>
                <span className="mark">{r.ok ? "○" : "✕"}</span>
                <span className="rn">문 {r.i + 1}</span>
                <span className="muted src">
                  {r.paper.year} {examGroup(r.paper.exams)} {r.paper.subject} {r.q.no}번
                </span>
                <span className="ans">
                  내 답 {r.mine ? CIRCLED[r.mine - 1] : "–"} · 정답 {r.q.answer.length === 5 ? "전원" : r.q.answer.map((a) => CIRCLED[a - 1]).join(",")}
                </span>
              </button>
              {open === r.i && (
                <div className="result-detail">
                  <QuestionImage item={r.ref} />
                  <ExplanationPanel item={r.ref} answer={r.q.answer} />
                </div>
              )}
            </li>
          ))}
      </ul>
    </div>
  );
}
