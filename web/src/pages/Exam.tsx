import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { CIRCLED, examGroup, loadPaper, pdfUrl } from "../data";
import { prefetchPdf } from "../pdf";
import { getSession, saveSession } from "../store";
import { navigate } from "../router";
import { ExplanationPanel, QuestionImage } from "../QuestionView";
import type { Paper, Session } from "../types";

function fmt(sec: number) {
  const s = Math.max(0, Math.floor(sec));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const ss = String(s % 60).padStart(2, "0");
  return h ? `${h}:${String(m).padStart(2, "0")}:${ss}` : `${m}:${ss}`;
}

export default function Exam({ id }: { id: string }) {
  const [s, setS] = useState<Session | undefined>(() => getSession(id));
  const [papers, setPapers] = useState<Map<string, Paper>>(new Map());
  const [omrOpen, setOmrOpen] = useState(false);
  const tick = useRef<number>(0);

  useEffect(() => {
    if (!s) return;
    if (s.finishedAt) navigate(`/result/${s.id}`);
    const ids = [...new Set(s.items.map((r) => r.paperId))];
    Promise.all(ids.map(loadPaper)).then((ps) =>
      setPapers(new Map(ps.map((p) => [p.id, p]))),
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const update = useCallback((fn: (x: Session) => Session) => {
    setS((prev) => {
      if (!prev) return prev;
      const next = fn(prev);
      saveSession(next);
      return next;
    });
  }, []);

  const submit = useCallback(
    (auto = false) => {
      if (!s) return;
      const left = s.items.length - Object.keys(s.answers).length;
      if (
        !auto &&
        !confirm(
          left
            ? `아직 ${left}문항을 풀지 않았습니다. 제출할까요?`
            : "답안을 제출하고 채점할까요?",
        )
      )
        return;
      update((x) => ({ ...x, finishedAt: Date.now() }));
      navigate(`/result/${s.id}`);
    },
    [s, update],
  );

  // 타이머: 1초마다 경과 시간 증가, 5초마다 저장. 탭이 숨겨져도 실제 시각 기준으로 계산.
  useEffect(() => {
    if (!s || s.finishedAt) return;
    let last = Date.now();
    tick.current = window.setInterval(() => {
      const now = Date.now();
      const d = (now - last) / 1000;
      last = now;
      setS((prev) => {
        if (!prev) return prev;
        const next = { ...prev, elapsedSec: prev.elapsedSec + d };
        if (Math.floor(next.elapsedSec) % 5 === 0) saveSession(next);
        return next;
      });
    }, 1000);
    return () => window.clearInterval(tick.current);
  }, [s?.id, s?.finishedAt]); // eslint-disable-line react-hooks/exhaustive-deps

  const timeUp =
    !!s &&
    s.mode === "exam" &&
    s.timeLimitSec > 0 &&
    s.elapsedSec >= s.timeLimitSec;
  useEffect(() => {
    if (timeUp) {
      alert("시험 시간이 끝났습니다. 답안을 자동 제출합니다.");
      submit(true);
    }
  }, [timeUp]); // eslint-disable-line react-hooks/exhaustive-deps

  const cur = s?.current ?? 0;
  const item = s?.items[cur];
  const paper = item ? papers.get(item.paperId) : undefined;
  const q = paper?.questions.find((x) => x.no === item!.no);
  const revealed = !!s && s.mode === "practice" && s.revealed.includes(cur);
  const chosen = s?.answers[cur];

  const choose = useCallback(
    (n: number) =>
      update((x) =>
        x.mode === "practice" && x.revealed.includes(x.current)
          ? x
          : { ...x, answers: { ...x.answers, [x.current]: n } },
      ),
    [update],
  );
  const go = useCallback(
    (i: number) =>
      update((x) => ({
        ...x,
        current: Math.max(0, Math.min(x.items.length - 1, i)),
      })),
    [update],
  );
  const reveal = () =>
    update((x) => ({
      ...x,
      revealed: [...new Set([...x.revealed, x.current])],
    }));
  const toggleFlag = () =>
    update((x) => ({
      ...x,
      flags: x.flags.includes(x.current)
        ? x.flags.filter((f) => f !== x.current)
        : [...x.flags, x.current],
    }));

  useEffect(() => {
    const on = (e: KeyboardEvent) => {
      if (
        e.target instanceof HTMLInputElement ||
        e.target instanceof HTMLSelectElement
      )
        return;
      if (/^[1-5]$/.test(e.key)) choose(Number(e.key));
      else if (e.key === "ArrowRight") go(cur + 1);
      else if (e.key === "ArrowLeft") go(cur - 1);
    };
    window.addEventListener("keydown", on);
    return () => window.removeEventListener("keydown", on);
  }, [choose, go, cur]);

  useEffect(() => {
    const next = s?.items[cur + 1];
    if (next) prefetchPdf(pdfUrl(next.paperId));
  }, [cur, s?.items]);

  const answeredCount = s ? Object.keys(s.answers).length : 0;
  const sectionBreaks = useMemo(() => {
    if (!s) return new Set<number>();
    const set = new Set<number>();
    s.items.forEach(
      (r, i) =>
        i > 0 &&
        papers.get(r.paperId)?.subject !==
          papers.get(s.items[i - 1].paperId)?.subject &&
        set.add(i),
    );
    return set;
  }, [s, papers]);

  if (!s) {
    return (
      <div className="center">
        <p>시험 기록을 찾을 수 없습니다.</p>
        <button className="btn" onClick={() => navigate("/")}>
          처음으로
        </button>
      </div>
    );
  }

  const remain =
    s.mode === "exam" ? s.timeLimitSec - s.elapsedSec : s.elapsedSec;
  const low = s.mode === "exam" && remain < 300;
  const isCorrect =
    q && chosen !== undefined ? q.answer.includes(chosen) : false;

  return (
    <div className="exam">
      <div className="exam-bar">
        <button
          className="btn ghost sm"
          onClick={() => navigate("/")}
          aria-label="나가기 (진행 상황은 저장됩니다)"
        >
          ← 나가기
        </button>
        <div className="exam-title">{s.title}</div>
        <div
          className={`timer ${low ? "low" : ""}`}
          aria-live="off"
          title={s.mode === "exam" ? "남은 시간" : "경과 시간"}
        >
          {s.mode === "exam" ? "남은 " : "경과 "}
          {fmt(remain)}
        </div>
        <button className="btn primary sm" onClick={() => submit()}>
          제출
        </button>
      </div>

      <div className="exam-body">
        <main className="q-area">
          <div className="q-head">
            <span className="q-no">
              문 {cur + 1}
              <span className="muted"> / {s.items.length}</span>
            </span>
            {paper && (
              <span className="q-src">
                {paper.year} {examGroup(paper.exams)} {paper.subject} {item!.no}
                번{!paper.answersFinal && " (가답안)"}
              </span>
            )}
            <button
              className={`flag ${s.flags.includes(cur) ? "on" : ""}`}
              onClick={toggleFlag}
              aria-pressed={s.flags.includes(cur)}
            >
              ⚑ 다시 보기
            </button>
          </div>

          {item && (
            <QuestionImage
              key={`${item.paperId}-${item.no}`}
              item={item}
              choice={{
                selected: chosen,
                onChoose: choose,
                correct: revealed ? q?.answer : undefined,
              }}
            />
          )}

          {q?.choices && !revealed && (
            <p className="pick-hint">
              {chosen === undefined
                ? "문제의 보기를 눌러 답을 고르세요 (키보드 1~5도 돼요)"
                : `${CIRCLED[chosen - 1]}을 골랐어요 · 다른 보기를 누르면 바뀌어요`}
            </p>
          )}

          <div
            className={`answer-row ${q?.choices ? "compact" : ""}`}
            role="radiogroup"
            aria-label="답 선택"
          >
            {CIRCLED.map((c, i) => {
              const n = i + 1;
              let cls = "bubble";
              if (chosen === n) cls += " chosen";
              if (revealed && q?.answer.includes(n)) cls += " correct";
              if (revealed && chosen === n && !q?.answer.includes(n))
                cls += " wrong";
              return (
                <button
                  key={n}
                  className={cls}
                  role="radio"
                  aria-checked={chosen === n}
                  onClick={() => choose(n)}
                  disabled={revealed}
                >
                  {c}
                </button>
              );
            })}
          </div>

          {s.mode === "practice" && q && (
            <div className="practice">
              {!revealed ? (
                <button
                  className="btn"
                  disabled={chosen === undefined}
                  onClick={reveal}
                >
                  정답 확인
                </button>
              ) : (
                <div className={`verdict ${isCorrect ? "ok" : "no"}`}>
                  {isCorrect
                    ? "정답입니다"
                    : `오답 · 정답 ${q.answer.length === 5 ? "전원 정답" : q.answer.map((a) => CIRCLED[a - 1]).join(", ")}`}
                </div>
              )}
              {revealed && <ExplanationPanel item={item!} answer={q.answer} />}
            </div>
          )}

          <div className="nav-row">
            <button
              className="btn"
              onClick={() => go(cur - 1)}
              disabled={cur === 0}
            >
              ← 이전
            </button>
            <button
              className="btn ghost omr-toggle"
              onClick={() => setOmrOpen(true)}
            >
              답안지 {answeredCount}/{s.items.length}
            </button>
            {cur < s.items.length - 1 ? (
              <button className="btn" onClick={() => go(cur + 1)}>
                다음 →
              </button>
            ) : (
              <button className="btn primary" onClick={() => submit()}>
                제출하기
              </button>
            )}
          </div>
        </main>

        <aside className={`omr ${omrOpen ? "open" : ""}`} aria-label="답안지">
          <div className="omr-head">
            <strong>답안지</strong>
            <span className="muted">
              {answeredCount}/{s.items.length}
            </span>
            <button
              className="icon omr-close"
              onClick={() => setOmrOpen(false)}
              aria-label="답안지 닫기"
            >
              ×
            </button>
          </div>
          <ol className="omr-list">
            {s.items.map((r, i) => {
              const p = papers.get(r.paperId);
              const qq = p?.questions.find((x) => x.no === r.no);
              const rev = s.mode === "practice" && s.revealed.includes(i);
              return (
                <li
                  key={i}
                  className={`${i === cur ? "cur" : ""} ${sectionBreaks.has(i) ? "brk" : ""}`}
                >
                  {sectionBreaks.has(i) || i === 0 ? (
                    <div className="omr-sec">{p?.subject}</div>
                  ) : null}
                  <button
                    className="omr-n"
                    onClick={() => (go(i), setOmrOpen(false))}
                  >
                    {i + 1}
                    {s.flags.includes(i) && <span className="fl">⚑</span>}
                  </button>
                  {[1, 2, 3, 4, 5].map((n) => (
                    <button
                      key={n}
                      className={`dot ${s.answers[i] === n ? "on" : ""} ${rev && qq?.answer.includes(n) ? "ans" : ""}`}
                      onClick={() => {
                        if (rev) return;
                        update((x) => ({
                          ...x,
                          current: i,
                          answers: { ...x.answers, [i]: n },
                        }));
                      }}
                      aria-label={`${i + 1}번 ${n}번 선택`}
                    >
                      {n}
                    </button>
                  ))}
                </li>
              );
            })}
          </ol>
        </aside>
      </div>
    </div>
  );
}
