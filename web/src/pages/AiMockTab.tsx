/**
 * AI 모의고사: 기출의 형식·문항 수·배치를 본떠 AI 가 만든 문항 창고(pipeline/mock_gen.py)에서 세트를 꾸린다.
 * 문항 번호(칸)마다 후보가 여러 개라 사람마다 세트가 다르고, 안 푼 문항을 먼저 고른다.
 * 새 문항은 사이트 전체가 함께 쓰는 월 예산 안에서 매일 만들어 채운다 (선착순).
 */
import { useEffect, useMemo, useState } from "react";
import { loadPaper } from "../data";
import { newSession, seenKeys } from "../store";
import { navigate } from "../router";
import { timeLimitOf, type ExamDef } from "../exams";
import type { ItemRef, Mode, Paper } from "../types";

interface Track {
  exam: string;
  group: string;
  subject: string;
  paper: string;
  slots: number;
  choices: number;
  filled: number;
  active: number;
}
interface MockIndex {
  month: string;
  limitUsd: number;
  spentUsd: number;
  perQuestionUsd: number;
  total: number;
  tracks: Track[];
}

let mockIndexP: Promise<MockIndex | null> | null = null;
function loadMockIndex(): Promise<MockIndex | null> {
  mockIndexP ??= fetch("./data/mock/index.json", { cache: "no-cache" })
    .then((r) => (r.ok ? r.json() : null))
    .catch(() => null);
  return mockIndexP;
}

/** 칸마다 후보 하나: 안 푼 것 중 무작위, 다 풀었으면 전체에서 무작위 */
function pickSet(paper: Paper, seen: Set<string>): ItemRef[] {
  const bySlot = new Map<number, number[]>();
  for (const q of paper.questions) {
    if (q.retired || !q.slot) continue;
    bySlot.set(q.slot, [...(bySlot.get(q.slot) ?? []), q.no]);
  }
  const rnd = <T,>(a: T[]) => a[Math.floor(Math.random() * a.length)];
  return [...bySlot.keys()]
    .sort((a, b) => a - b)
    .map((s) => {
      const all = bySlot.get(s)!;
      const fresh = all.filter((no) => !seen.has(`${paper.id}#${no}`));
      return { paperId: paper.id, no: rnd(fresh.length ? fresh : all) };
    });
}

export default function AiMockTab({ exam, mode }: { exam: ExamDef; mode: Mode }) {
  const [ix, setIx] = useState<MockIndex | null | undefined>(undefined);
  const [busy, setBusy] = useState("");
  useEffect(() => {
    loadMockIndex().then(setIx);
  }, []);
  const tracks = useMemo(() => ix?.tracks.filter((t) => t.exam === exam.id) ?? [], [ix, exam]);
  const groups = useMemo(() => [...new Set(tracks.map((t) => t.group))], [tracks]);

  if (ix === undefined) return <div className="skeleton tall" />;

  const left = ix ? Math.max(ix.limitUsd - ix.spentUsd, 0) : 0;
  const pct = ix ? Math.round((left / ix.limitUsd) * 100) : 0;

  const go = async (ts: Track[], title: string) => {
    setBusy(title);
    try {
      const seen = seenKeys();
      const papers = await Promise.all(ts.map((t) => loadPaper(t.paper)));
      const items = papers.flatMap((p) => pickSet(p, seen));
      const s = newSession({
        exam: exam.id,
        title,
        mode,
        items,
        timeLimitSec: mode === "exam" ? timeLimitOf(exam, items.length) : 0,
      });
      navigate(`/exam/${s.id}`);
    } finally {
      setBusy("");
    }
  };

  return (
    <div className="ai-mock">
      <div className="ai-intro">
        <p>
          <b>AI가 이 시험의 기출을 분석해 새로 만든 모의고사</b>예요. 실제 시험과 같은 과목·문항 수·배치로 나오고, 칸마다 여러 후보 중에서 골라
          사람마다 세트가 달라요. 풀고 나서 문항마다 👍👎🚨로 평가해 주세요. 나쁜 평가가 쌓인 문항은 빠지고 새 문항으로 바뀌어요.
        </p>
        {ix && (
          <div className="ai-budget" title="새 문항을 만드는 데 쓰는 이번 달 공용 사용량 (매달 1일 초기화)">
            <span>이번 달 AI 출제 사용량</span>
            <div className="bar">
              <i style={{ width: `${pct}%` }} />
            </div>
            <span className="muted">
              {pct}% 남음 · 문항 창고 {ix.total.toLocaleString()}개
            </span>
          </div>
        )}
      </div>

      {tracks.length === 0 ? (
        <p className="muted empty">이 시험의 AI 문항을 만들고 있어요. 매일 조금씩 채워지니 곧 열려요.</p>
      ) : (
        groups.map((g) => {
          const ts = tracks.filter((t) => t.group === g);
          const ready = ts.filter((t) => t.filled >= t.slots);
          return (
            <section key={g} className="ai-group">
              {groups.length > 1 && <h3>{g}</h3>}
              <div className="ai-subjects">
                {ts.map((t) => {
                  const ok = t.filled >= t.slots;
                  return (
                    <button
                      key={t.paper}
                      className={`btn subj ${ok ? "" : "disabled"}`}
                      disabled={!ok || !!busy}
                      onClick={() => go([t], `${exam.name} AI 모의고사 ${t.subject}`)}
                    >
                      {t.subject}
                      <small>
                        {ok
                          ? `${t.slots}문항 · 후보 ${t.active}개`
                          : `준비 중 ${Math.round((t.filled / t.slots) * 100)}%`}
                      </small>
                    </button>
                  );
                })}
                {ready.length > 1 && (
                  <button
                    className="btn primary subj"
                    disabled={!!busy}
                    onClick={() => go(ready, `${exam.name} AI 모의고사 ${g} 전 과목`)}
                  >
                    전 과목
                    <small>{ready.reduce((n, t) => n + t.slots, 0)}문항</small>
                  </button>
                )}
              </div>
            </section>
          );
        })
      )}
      <p className="muted ai-note">
        AI가 만든 문항이라 오류가 있을 수 있어요. 다른 AI가 정답을 모른 채 다시 풀어 답이 같을 때만 실어요.
      </p>
    </div>
  );
}
