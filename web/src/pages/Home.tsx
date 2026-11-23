/** 시험 하나의 첫 화면: 연도별 기출 / 기출 섞어 풀기 / AI 모의고사 / 기록·오답노트 / 수험생 이야기 */
import { useEffect, useMemo, useState } from "react";
import Talk, { useTalkVisible } from "../talk/Talk";
import AiMockTab from "./AiMockTab";
import { countComments, yearTarget } from "../talk/api";
import { loadIndex, loadPaper } from "../data";
import {
  deleteSession,
  listSessions,
  newSession,
  seenKeys,
  wrongItems,
} from "../store";
import { navigate } from "../router";
import { AdSlot } from "../monetization";
import SlopAd from "../SlopAd";
import { examOf, groupOf, ordered, timeLimitOf, type ExamDef } from "../exams";
import type { ItemRef, Mode, PaperMeta, Session } from "../types";

type Tab = "year" | "random" | "ai" | "history" | "talk";

function ModeToggle({
  mode,
  setMode,
}: {
  mode: Mode;
  setMode: (m: Mode) => void;
}) {
  return (
    <div className="seg" role="radiogroup" aria-label="풀이 방식">
      <button
        role="radio"
        aria-checked={mode === "exam"}
        className={mode === "exam" ? "on" : ""}
        onClick={() => setMode("exam")}
      >
        실전 모드<small>시간 제한 · 제출 후 채점</small>
      </button>
      <button
        role="radio"
        aria-checked={mode === "practice"}
        className={mode === "practice" ? "on" : ""}
        onClick={() => setMode("practice")}
      >
        연습 모드<small>문항마다 바로 채점 · 해설</small>
      </button>
    </div>
  );
}

function start(exam: ExamDef, title: string, mode: Mode, items: ItemRef[]) {
  const s = newSession({
    exam: exam.id,
    title,
    mode,
    items,
    timeLimitSec: mode === "exam" ? timeLimitOf(exam, items.length) : 0,
  });
  navigate(`/exam/${s.id}`);
}

function YearTab({
  exam,
  papers,
  mode,
}: {
  exam: ExamDef;
  papers: PaperMeta[];
  mode: Mode;
}) {
  const groups = useMemo(
    () => ordered(exam.groups, papers.map(groupOf)),
    [exam, papers],
  );
  const subjects = useMemo(
    () =>
      ordered(
        exam.subjects,
        papers.map((p) => p.subject),
      ),
    [exam, papers],
  );
  const [group, setGroup] = useState(groups[0]);
  // 연도·회차별 이야기: 열어 둔 연도, 연도별 댓글 수
  const [talkYear, setTalkYear] = useState<number | null>(null);
  const [talkOn] = useTalkVisible();
  const [talkCounts, setTalkCounts] = useState<Record<string, number>>({});
  const rows = useMemo(() => {
    const byYear = new Map<number, Record<string, PaperMeta>>();
    for (const p of papers) {
      if (groupOf(p) !== group) continue;
      const row = byYear.get(p.year) ?? {};
      row[p.subject] ??= p;
      byYear.set(p.year, row);
    }
    return [...byYear.entries()].sort((a, b) => b[0] - a[0]);
  }, [papers, group]);
  // 이 계열에 실제로 나오는 과목만 열로 쓴다
  const allCols = subjects.filter((s) => rows.some(([, r]) => r[s]));
  // 과목이 많은 시험(공무원 등)은 과목을 먼저 고르고 그 과목의 연도 목록을 보여 준다
  const many = allCols.length > 6;
  const [pick, setPick] = useState("");
  const picked = many ? (allCols.includes(pick) ? pick : allCols[0]) : "";
  const cols = many ? [picked] : allCols;
  const shownRows = many ? rows.filter(([, r]) => r[picked]) : rows;

  const yearKeys = shownRows.map(([y]) => yearTarget(exam.id, group, y)).join("|");
  useEffect(() => {
    if (!talkOn || !yearKeys) return;
    countComments(yearKeys.split("|"))
      .then(setTalkCounts)
      .catch(() => setTalkCounts({}));
  }, [talkOn, yearKeys]);

  const startPaper = (p: PaperMeta) =>
    start(
      exam,
      `${p.year} ${group} ${p.subject}`,
      mode,
      Array.from({ length: p.count }, (_, i) => ({ paperId: p.id, no: i + 1 })),
    );
  const startAll = (year: number, row: Record<string, PaperMeta>) => {
    const items = cols.flatMap((s) =>
      row[s]
        ? Array.from({ length: row[s].count }, (_, i) => ({
            paperId: row[s].id,
            no: i + 1,
          }))
        : [],
    );
    start(exam, `${year} ${group} 전 과목`, mode, items);
  };

  return (
    <>
      {groups.length > 1 && (
        <div className="chips" role="tablist">
          {groups.map((g) => (
            <button
              key={g}
              role="tab"
              aria-selected={g === group}
              className={g === group ? "chip on" : "chip"}
              onClick={() => setGroup(g)}
            >
              {g}
            </button>
          ))}
        </div>
      )}
      {many && (
        <label className="subj-pick">
          과목{" "}
          <select value={picked} onChange={(e) => setPick(e.target.value)}>
            {allCols.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
          <span className="muted">{allCols.length}개 과목</span>
        </label>
      )}
      <div className="year-list">
        {shownRows.map(([year, row]) => (
          <div key={year} className="year-row">
            <div className="year">{year}</div>
            <div
              className="subj-btns"
              style={
                {
                  "--cols": Math.min(
                    cols.length + (cols.length > 1 ? 1 : 0),
                    6,
                  ),
                } as React.CSSProperties
              }
            >
              {cols.map((s) => {
                const p = row[s];
                return p ? (
                  <button
                    key={s}
                    className="btn subj"
                    onClick={() => startPaper(p)}
                    title={p.exams.join(", ")}
                  >
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
              {cols.filter((s) => row[s]).length > 1 && (
                <button
                  className="btn primary subj"
                  onClick={() => startAll(year, row)}
                >
                  전 과목
                  <small>연속 응시</small>
                </button>
              )}
            </div>
            {talkOn && (
              <button
                className={`year-talk ${talkYear === year ? "on" : ""}`}
                onClick={() => setTalkYear(talkYear === year ? null : year)}
                aria-expanded={talkYear === year}
                title={`${year} ${group} 이야기`}
              >
                💬<span>{talkCounts[yearTarget(exam.id, group, year)] ?? ""}</span>
              </button>
            )}
            {talkYear === year && (
              <div className="year-talk-box">
                <Talk
                  key={yearTarget(exam.id, group, year)}
                  target={yearTarget(exam.id, group, year)}
                  title={`${year}년 ${group} 이야기`}
                  hint={`${year}년 ${group} 시험 어땠나요? 체감 난이도, 합격선 예상, 과목별 소감을 남겨 주세요`}
                />
              </div>
            )}
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

function RandomTab({
  exam,
  papers,
  mode,
}: {
  exam: ExamDef;
  papers: PaperMeta[];
  mode: Mode;
}) {
  const allSubjects = useMemo(
    () =>
      ordered(
        exam.subjects,
        papers.map((p) => p.subject),
      ),
    [exam, papers],
  );
  const allGroups = useMemo(
    () => ordered(exam.groups, papers.map(groupOf)),
    [exam, papers],
  );
  const years = papers.map((p) => p.year);
  const minY = Math.min(...years);
  const maxY = Math.max(...years);
  const [subjects, setSubjects] = useState<string[]>(allSubjects.slice(0, 1));
  const [groups, setGroups] = useState<string[]>(allGroups);
  const [count, setCount] = useState(25);
  const [from, setFrom] = useState(Math.max(minY, maxY - 9));
  const [to, setTo] = useState(maxY);
  const [unseen, setUnseen] = useState(true);
  const [busy, setBusy] = useState(false);

  const pool = papers.filter(
    (p) =>
      subjects.includes(p.subject) &&
      groups.includes(groupOf(p)) &&
      p.year >= from &&
      p.year <= to,
  );
  const poolSize = pool.reduce((n, p) => n + p.count, 0);
  const toggle = <T,>(list: T[], v: T) =>
    list.includes(v) ? list.filter((x) => x !== v) : [...list, v];

  const go = async () => {
    setBusy(true);
    const seen = unseen ? seenKeys() : new Set<string>();
    let refs: ItemRef[] = shuffle(
      pool.flatMap((p) =>
        Array.from({ length: p.count }, (_, i) => ({
          paperId: p.id,
          no: i + 1,
        })),
      ),
    );
    const fresh = refs.filter((r) => !seen.has(`${r.paperId}#${r.no}`));
    const rest = refs.filter((r) => seen.has(`${r.paperId}#${r.no}`));
    refs = [...fresh, ...rest].slice(0, count);
    await Promise.all([...new Set(refs.map((r) => r.paperId))].map(loadPaper));
    const order = (r: ItemRef) =>
      allSubjects.indexOf(papers.find((p) => p.id === r.paperId)!.subject);
    refs.sort((a, b) => order(a) - order(b));
    setBusy(false);
    start(
      exam,
      `${exam.name} 기출 섞어 풀기 ${subjects.join("·")} ${refs.length}문항`,
      mode,
      refs,
    );
  };

  return (
    <div className="form">
      <fieldset>
        <legend>과목</legend>
        <div className="chips">
          {allSubjects.map((s) => (
            <button
              key={s}
              className={subjects.includes(s) ? "chip on" : "chip"}
              aria-pressed={subjects.includes(s)}
              onClick={() => setSubjects(toggle(subjects, s))}
            >
              {s}
            </button>
          ))}
        </div>
      </fieldset>
      {allGroups.length > 1 && (
        <fieldset>
          <legend>시험</legend>
          <div className="chips">
            {allGroups.map((g) => (
              <button
                key={g}
                className={groups.includes(g) ? "chip on" : "chip"}
                aria-pressed={groups.includes(g)}
                onClick={() => setGroups(toggle(groups, g))}
              >
                {g}
              </button>
            ))}
          </div>
        </fieldset>
      )}
      <fieldset>
        <legend>출제 연도</legend>
        <div className="row">
          <select
            value={from}
            onChange={(e) => setFrom(Number(e.target.value))}
            aria-label="시작 연도"
          >
            {Array.from({ length: maxY - minY + 1 }, (_, i) => minY + i).map(
              (y) => (
                <option key={y}>{y}</option>
              ),
            )}
          </select>
          <span>~</span>
          <select
            value={to}
            onChange={(e) => setTo(Number(e.target.value))}
            aria-label="끝 연도"
          >
            {Array.from({ length: maxY - minY + 1 }, (_, i) => minY + i).map(
              (y) => (
                <option key={y}>{y}</option>
              ),
            )}
          </select>
        </div>
      </fieldset>
      <fieldset>
        <legend>문항 수</legend>
        <div className="chips">
          {[10, 20, 25, 40].map((n) => (
            <button
              key={n}
              className={count === n ? "chip on" : "chip"}
              aria-pressed={count === n}
              onClick={() => setCount(n)}
            >
              {n}문항
            </button>
          ))}
        </div>
      </fieldset>
      <label className="check">
        <input
          type="checkbox"
          checked={unseen}
          onChange={(e) => setUnseen(e.target.checked)}
        />{" "}
        안 푼 문제 우선 출제
      </label>
      <div className="row between">
        <span className="muted">
          출제 대상 {poolSize.toLocaleString()}문항
          {mode === "exam" &&
            poolSize > 0 &&
            ` · 제한 시간 ${timeLimitOf(exam, Math.min(count, poolSize)) / 60}분`}
        </span>
        <button
          className="btn primary lg"
          disabled={!poolSize || busy}
          onClick={go}
        >
          {busy ? "준비 중…" : "시작하기"}
        </button>
      </div>
    </div>
  );
}

/** 이 시험의 기록만 (예전 기록은 exam 이 없으면 PSAT) */
export const sessionsOf = (examId: string): Session[] =>
  listSessions().filter((s) => (s.exam ?? "psat") === examId);

function HistoryTab({ exam, papers }: { exam: ExamDef; papers: PaperMeta[] }) {
  const [sessions, setSessions] = useState(() => sessionsOf(exam.id));
  const [wrong, setWrong] = useState<ItemRef[] | null>(null);
  const subjects = useMemo(
    () =>
      ordered(
        exam.subjects,
        papers.map((p) => p.subject),
      ),
    [exam, papers],
  );

  useEffect(() => {
    // 오답 계산엔 정답이 필요해서 관련 문제지를 불러온다
    const mine = new Set(papers.map((p) => p.id));
    const ids = [
      ...new Set(
        sessions
          .filter((s) => s.finishedAt)
          .flatMap((s) => s.items.map((r) => r.paperId)),
      ),
    ];
    Promise.all(ids.map((id) => loadPaper(id).catch(() => null))).then((ps) => {
      const map = new Map(ps.filter(Boolean).map((p) => [p!.id, p!]));
      setWrong(
        wrongItems((ref, choice) => {
          if (!mine.has(ref.paperId)) return null;
          const q = map
            .get(ref.paperId)
            ?.questions.find((x) => x.no === ref.no);
          if (!q || choice === undefined) return q ? false : null;
          return q.answer.includes(choice);
        }),
      );
    });
  }, [sessions, papers]);

  if (!sessions.length)
    return (
      <p className="muted empty">
        아직 푼 기록이 없습니다. 연도별 기출이나 기출 섞어 풀기를 시작해 보세요.
      </p>
    );
  const subjOf = (id: string) => papers.find((p) => p.id === id)?.subject;

  return (
    <>
      {wrong && wrong.length > 0 && (
        <div className="card wrong-card">
          <div>
            <strong>오답노트</strong>
            <div className="muted">
              최근 기록 기준 틀린 문항 {wrong.length}개 ·{" "}
              {subjects
                .map(
                  (s) =>
                    [
                      s,
                      wrong.filter((w) => subjOf(w.paperId) === s).length,
                    ] as const,
                )
                .filter(([, n]) => n > 0)
                .map(([s, n]) => `${s} ${n}`)
                .join(" / ")}
            </div>
          </div>
          <button
            className="btn primary"
            onClick={() =>
              start(
                exam,
                `${exam.name} 오답 다시 풀기 ${wrong.length}문항`,
                "practice",
                shuffle(wrong),
              )
            }
          >
            틀린 문제 다시 풀기
          </button>
        </div>
      )}
      <ul className="history">
        {sessions.map((s) => {
          const answered = Object.keys(s.answers).length;
          return (
            <li key={s.id}>
              <button
                className="link"
                onClick={() =>
                  navigate(s.finishedAt ? `/result/${s.id}` : `/exam/${s.id}`)
                }
              >
                <span className="h-title">{s.title}</span>
                <span className="muted">
                  {new Date(s.startedAt).toLocaleString("ko-KR", {
                    dateStyle: "short",
                    timeStyle: "short",
                  })}{" "}
                  · {s.mode === "exam" ? "실전" : "연습"} ·{" "}
                  {s.finishedAt
                    ? "채점 완료"
                    : `진행 중 ${answered}/${s.items.length}`}
                </span>
              </button>
              <button
                className="icon"
                aria-label="기록 삭제"
                onClick={() => {
                  deleteSession(s.id);
                  setSessions(sessionsOf(exam.id));
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

export default function ExamHome({ exam }: { exam: ExamDef }) {
  const [all, setAll] = useState<PaperMeta[] | null>(null);
  const [tab, setTab] = useState<Tab>("year");
  const [mode, setMode] = useState<Mode>("exam");
  useEffect(() => {
    loadIndex().then(setAll);
  }, []);
  const papers = useMemo(
    () => all?.filter((p) => examOf(p).id === exam.id) ?? null,
    [all, exam],
  );

  const total = papers?.reduce((n, p) => n + p.count, 0) ?? 0;
  const explained = papers?.reduce((n, p) => n + (p.explained ?? 0), 0) ?? 0;
  const years = papers?.length
    ? `${Math.min(...papers.map((p) => p.year))}–${Math.max(...papers.map((p) => p.year))}`
    : "";

  return (
    <div className="home-wrap">
      <div className="home">
        <nav className="crumb">
          <a href="#/" onClick={(e) => (e.preventDefault(), navigate("/"))}>
            ← 전체 시험
          </a>
        </nav>
        <header className="hero">
          <h1>{exam.name} 기출 모의고사</h1>
          <p>
            {exam.desc} 기출을 실제 시험처럼 풀고, 문항별 해설로 복습하세요.
            {papers && papers.length > 0 && (
              <>
                <br />
                <strong>
                  {years}년 · 문제지 {papers.length}개 ·{" "}
                  {total.toLocaleString()}문항
                  {explained > 0 &&
                    explained < total &&
                    ` · 해설 ${Math.round((explained / total) * 100)}%`}
                </strong>
              </>
            )}
          </p>
        </header>

        {papers && papers.length === 0 ? (
          <p className="muted empty">이 시험의 기출은 준비 중입니다.</p>
        ) : (
          <>
            <nav className="tabs" role="tablist">
              {(
                [
                  ["year", "연도별 기출"],
                  ["random", "기출 섞어 풀기"],
                  ["ai", "AI 모의고사"],
                  ["history", "기록·오답노트"],
                  ["talk", "수험생 이야기"],
                ] as [Tab, string][]
              ).map(([k, label]) => (
                <button
                  key={k}
                  role="tab"
                  aria-selected={tab === k}
                  className={tab === k ? "on" : ""}
                  onClick={() => setTab(k)}
                >
                  {label}
                </button>
              ))}
            </nav>
            {!papers ? (
              <div className="skeleton tall" />
            ) : (
              <section className="panel">
                {tab !== "history" && tab !== "talk" && (
                  <ModeToggle mode={mode} setMode={setMode} />
                )}
                <div className="ad-inline">
                  <SlopAd />
                </div>
                {tab === "year" && (
                  <YearTab exam={exam} papers={papers} mode={mode} />
                )}
                {tab === "ai" && <AiMockTab exam={exam} mode={mode} />}
                {tab === "random" && (
                  <RandomTab exam={exam} papers={papers} mode={mode} />
                )}
                {tab === "history" && (
                  <HistoryTab exam={exam} papers={papers} />
                )}
                {tab === "talk" && (
                  <Talk key={exam.id} target={`x:${exam.id}`} title={`${exam.name} 수험생 이야기`} big />
                )}
              </section>
            )}
          </>
        )}
        <AdSlot slot="home-bottom" />
      </div>
      <aside className="side-rail">
        <SlopAd />
      </aside>
    </div>
  );
}
