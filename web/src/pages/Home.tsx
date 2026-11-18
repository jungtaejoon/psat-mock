import { useEffect, useMemo, useState } from "react";
import { EXAM_GROUPS, examGroup, loadIndex, loadPaper, timeLimitFor } from "../data";
import { deleteSession, listSessions, newSession, seenKeys, wrongItems } from "../store";
import { navigate } from "../router";
import { AdSlot } from "../monetization";
import SlopAd from "../SlopAd";
import { SUBJECTS, type ItemRef, type Mode, type PaperMeta, type Subject } from "../types";

type Tab = "year" | "random" | "history";

function ModeToggle({ mode, setMode }: { mode: Mode; setMode: (m: Mode) => void }) {
  return (
    <div className="seg" role="radiogroup" aria-label="풀이 방식">
      <button role="radio" aria-checked={mode === "exam"} className={mode === "exam" ? "on" : ""} onClick={() => setMode("exam")}>
        실전 모드<small>시간 제한 · 제출 후 채점</small>
      </button>
      <button role="radio" aria-checked={mode === "practice"} className={mode === "practice" ? "on" : ""} onClick={() => setMode("practice")}>
        연습 모드<small>문항마다 바로 채점 · 해설</small>
      </button>
    </div>
  );
}

function start(title: string, mode: Mode, items: ItemRef[]) {
  const s = newSession({ title, mode, items, timeLimitSec: mode === "exam" ? timeLimitFor(items.length) : 0 });
  navigate(`/exam/${s.id}`);
}

function YearTab({ papers, mode }: { papers: PaperMeta[]; mode: Mode }) {
  const [group, setGroup] = useState(EXAM_GROUPS[0]);
  const rows = useMemo(() => {
    const byYear = new Map<number, Partial<Record<Subject, PaperMeta>>>();
    for (const p of papers) {
      if (examGroup(p.exams) !== group) continue;
      const row = byYear.get(p.year) ?? {};
      row[p.subject] = p;
      byYear.set(p.year, row);
    }
    return [...byYear.entries()].sort((a, b) => b[0] - a[0]);
  }, [papers, group]);

  const startPaper = (p: PaperMeta) =>
    start(`${p.year} ${group} ${p.subject}`, mode, Array.from({ length: p.count }, (_, i) => ({ paperId: p.id, no: i + 1 })));

  const startAll = (year: number, row: Partial<Record<Subject, PaperMeta>>) => {
    const items = SUBJECTS.flatMap((s) => {
      const p = row[s];
      return p ? Array.from({ length: p.count }, (_, i) => ({ paperId: p.id, no: i + 1 })) : [];
    });
    start(`${year} ${group} 전 영역`, mode, items);
  };

  return (
    <>
      <div className="chips" role="tablist">
        {EXAM_GROUPS.filter((g) => papers.some((p) => examGroup(p.exams) === g)).map((g) => (
          <button key={g} role="tab" aria-selected={g === group} className={g === group ? "chip on" : "chip"} onClick={() => setGroup(g)}>
            {g}
          </button>
        ))}
      </div>
      <div className="year-list">
        {rows.map(([year, row]) => (
          <div key={year} className="year-row">
            <div className="year">{year}</div>
            <div className="subj-btns">
              {SUBJECTS.map((s) => {
                const p = row[s];
                return p ? (
                  <button key={s} className="btn subj" onClick={() => startPaper(p)} title={p.exams.join(", ")}>
                    {s}
                    <small>
                      {p.count}문항{!p.answersFinal && " · 가답안"}
                    </small>
                  </button>
                ) : (
                  <span key={s} className="btn subj disabled">
                    {s}
                    <small>없음</small>
                  </span>
                );
              })}
              {SUBJECTS.filter((s) => row[s]).length > 1 && (
                <button className="btn primary subj" onClick={() => startAll(year, row)}>
                  전 영역
                  <small>연속 응시</small>
                </button>
              )}
            </div>
          </div>
        ))}
      </div>
    </>
  );
}

function shuffle<T>(a: T[]): T[] {
  const b = [...a];
  for (let i = b.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [b[i], b[j]] = [b[j], b[i]];
  }
  return b;
}

function RandomTab({ papers, mode }: { papers: PaperMeta[]; mode: Mode }) {
  const years = papers.map((p) => p.year);
  const minY = Math.min(...years);
  const maxY = Math.max(...years);
  const [subjects, setSubjects] = useState<Subject[]>(["언어논리"]);
  const [groups, setGroups] = useState<string[]>(EXAM_GROUPS);
  const [count, setCount] = useState(25);
  const [from, setFrom] = useState(Math.max(minY, maxY - 9));
  const [to, setTo] = useState(maxY);
  const [unseen, setUnseen] = useState(true);
  const [busy, setBusy] = useState(false);

  const pool = papers.filter((p) => subjects.includes(p.subject) && groups.includes(examGroup(p.exams)) && p.year >= from && p.year <= to);
  const poolSize = pool.reduce((n, p) => n + p.count, 0);

  const toggle = <T,>(list: T[], v: T) => (list.includes(v) ? list.filter((x) => x !== v) : [...list, v]);

  const go = async () => {
    setBusy(true);
    const seen = unseen ? seenKeys() : new Set<string>();
    let refs: ItemRef[] = pool.flatMap((p) => Array.from({ length: p.count }, (_, i) => ({ paperId: p.id, no: i + 1 })));
    refs = shuffle(refs);
    const fresh = refs.filter((r) => !seen.has(`${r.paperId}#${r.no}`));
    const rest = refs.filter((r) => seen.has(`${r.paperId}#${r.no}`));
    let picked = [...fresh, ...rest].slice(0, count);
    // 공통 지문 세트 문제는 같이 나오도록, 그리고 영역별로 묶어 정렬
    await Promise.all([...new Set(picked.map((r) => r.paperId))].map(loadPaper));
    const order = (r: ItemRef) => SUBJECTS.indexOf(papers.find((p) => p.id === r.paperId)!.subject);
    picked = picked.sort((a, b) => order(a) - order(b));
    setBusy(false);
    start(`랜덤 ${subjects.join("·")} ${picked.length}문항`, mode, picked);
  };

  return (
    <div className="form">
      <fieldset>
        <legend>영역</legend>
        <div className="chips">
          {SUBJECTS.map((s) => (
            <button key={s} className={subjects.includes(s) ? "chip on" : "chip"} aria-pressed={subjects.includes(s)} onClick={() => setSubjects(toggle(subjects, s))}>
              {s}
            </button>
          ))}
        </div>
      </fieldset>
      <fieldset>
        <legend>시험</legend>
        <div className="chips">
          {EXAM_GROUPS.filter((g) => papers.some((p) => examGroup(p.exams) === g)).map((g) => (
            <button key={g} className={groups.includes(g) ? "chip on" : "chip"} aria-pressed={groups.includes(g)} onClick={() => setGroups(toggle(groups, g))}>
              {g}
            </button>
          ))}
        </div>
      </fieldset>
      <fieldset>
        <legend>출제 연도</legend>
        <div className="row">
          <select value={from} onChange={(e) => setFrom(Number(e.target.value))} aria-label="시작 연도">
            {Array.from({ length: maxY - minY + 1 }, (_, i) => minY + i).map((y) => (
              <option key={y}>{y}</option>
            ))}
          </select>
          <span>~</span>
          <select value={to} onChange={(e) => setTo(Number(e.target.value))} aria-label="끝 연도">
            {Array.from({ length: maxY - minY + 1 }, (_, i) => minY + i).map((y) => (
              <option key={y}>{y}</option>
            ))}
          </select>
        </div>
      </fieldset>
      <fieldset>
        <legend>문항 수</legend>
        <div className="chips">
          {[10, 20, 25, 40].map((n) => (
            <button key={n} className={count === n ? "chip on" : "chip"} aria-pressed={count === n} onClick={() => setCount(n)}>
              {n}문항
            </button>
          ))}
        </div>
      </fieldset>
      <label className="check">
        <input type="checkbox" checked={unseen} onChange={(e) => setUnseen(e.target.checked)} /> 안 푼 문제 우선 출제
      </label>
      <div className="row between">
        <span className="muted">
          출제 대상 {poolSize.toLocaleString()}문항{mode === "exam" && ` · 제한 시간 ${timeLimitFor(Math.min(count, poolSize)) / 60}분`}
        </span>
        <button className="btn primary lg" disabled={!poolSize || busy} onClick={go}>
          {busy ? "준비 중…" : "시작하기"}
        </button>
      </div>
    </div>
  );
}

function HistoryTab({ papers }: { papers: PaperMeta[] }) {
  const [sessions, setSessions] = useState(listSessions());
  const [wrong, setWrong] = useState<ItemRef[] | null>(null);

  useEffect(() => {
    // 오답 계산엔 정답이 필요해서 관련 문제지를 불러온다
    const ids = [...new Set(sessions.filter((s) => s.finishedAt).flatMap((s) => s.items.map((r) => r.paperId)))];
    Promise.all(ids.map((id) => loadPaper(id).catch(() => null))).then((ps) => {
      const map = new Map(ps.filter(Boolean).map((p) => [p!.id, p!]));
      setWrong(
        wrongItems((ref, choice) => {
          const q = map.get(ref.paperId)?.questions.find((x) => x.no === ref.no);
          if (!q || choice === undefined) return q ? false : null;
          return q.answer.includes(choice);
        }),
      );
    });
  }, [sessions]);

  if (!sessions.length) return <p className="muted empty">아직 푼 기록이 없습니다. 연도별 또는 랜덤 모의고사를 시작해 보세요.</p>;
  const subjOf = (id: string) => papers.find((p) => p.id === id)?.subject;

  return (
    <>
      {wrong && wrong.length > 0 && (
        <div className="card wrong-card">
          <div>
            <strong>오답노트</strong>
            <div className="muted">
              최근 기록 기준 틀린 문항 {wrong.length}개 ·{" "}
              {SUBJECTS.map((s) => `${s} ${wrong.filter((w) => subjOf(w.paperId) === s).length}`).join(" / ")}
            </div>
          </div>
          <button className="btn primary" onClick={() => start(`오답 다시 풀기 ${wrong.length}문항`, "practice", shuffle(wrong))}>
            틀린 문제 다시 풀기
          </button>
        </div>
      )}
      <ul className="history">
        {sessions.map((s) => {
          const answered = Object.keys(s.answers).length;
          return (
            <li key={s.id}>
              <button className="link" onClick={() => navigate(s.finishedAt ? `/result/${s.id}` : `/exam/${s.id}`)}>
                <span className="h-title">{s.title}</span>
                <span className="muted">
                  {new Date(s.startedAt).toLocaleString("ko-KR", { dateStyle: "short", timeStyle: "short" })} · {s.mode === "exam" ? "실전" : "연습"} ·{" "}
                  {s.finishedAt ? "채점 완료" : `진행 중 ${answered}/${s.items.length}`}
                </span>
              </button>
              <button
                className="icon"
                aria-label="기록 삭제"
                onClick={() => {
                  deleteSession(s.id);
                  setSessions(listSessions());
                }}
              >
                ×
              </button>
            </li>
          );
        })}
      </ul>
    </>
  );
}

export default function Home() {
  const [papers, setPapers] = useState<PaperMeta[] | null>(null);
  const [tab, setTab] = useState<Tab>("year");
  const [mode, setMode] = useState<Mode>("exam");
  useEffect(() => {
    loadIndex().then(setPapers);
  }, []);

  const total = papers?.reduce((n, p) => n + p.count, 0) ?? 0;
  const years = papers ? `${Math.min(...papers.map((p) => p.year))}–${Math.max(...papers.map((p) => p.year))}` : "";

  return (
    <div className="home">
      <header className="hero">
        <h1>PSAT 기출 모의고사</h1>
        <p>
          5급 공채·외교관, 7급 공채·민경채, 지역인재 PSAT 기출을 실제 시험처럼 풀고, 문항별 해설로 복습하세요.
          {papers && (
            <>
              <br />
              <strong>
                {years}년 · 문제지 {papers.length}개 · {total.toLocaleString()}문항
              </strong>
            </>
          )}
        </p>
      </header>

      <nav className="tabs" role="tablist">
        {(
          [
            ["year", "연도별 기출"],
            ["random", "랜덤 모의고사"],
            ["history", "기록·오답노트"],
          ] as [Tab, string][]
        ).map(([k, label]) => (
          <button key={k} role="tab" aria-selected={tab === k} className={tab === k ? "on" : ""} onClick={() => setTab(k)}>
            {label}
          </button>
        ))}
      </nav>

      {!papers ? (
        <div className="skeleton tall" />
      ) : (
        <section className="panel">
          {tab !== "history" && <ModeToggle mode={mode} setMode={setMode} />}
          {tab === "year" && <YearTab papers={papers} mode={mode} />}
          {tab === "random" && <RandomTab papers={papers} mode={mode} />}
          {tab === "history" && <HistoryTab papers={papers} />}
        </section>
      )}
      <SlopAd />
      <AdSlot slot="home-bottom" />
    </div>
  );
}
