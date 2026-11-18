import type { ItemRef, Session } from "./types";

// 지금은 브라우저 저장소에만 기록한다. 회원제/유료화 전환 시 이 모듈만 서버 API 로 바꾸면 된다.
const KEY = "psat.sessions.v1";

function read(): Session[] {
  try {
    return JSON.parse(localStorage.getItem(KEY) || "[]");
  } catch {
    return [];
  }
}
function write(list: Session[]) {
  try {
    localStorage.setItem(KEY, JSON.stringify(list.slice(0, 200)));
  } catch {
    /* 저장 불가(사생활 보호 모드 등) — 무시 */
  }
}

export function listSessions(): Session[] {
  return read().sort((a, b) => b.startedAt - a.startedAt);
}
export function getSession(id: string): Session | undefined {
  return read().find((s) => s.id === id);
}
export function saveSession(s: Session) {
  const list = read().filter((x) => x.id !== s.id);
  list.unshift(s);
  write(list);
}
export function deleteSession(id: string) {
  write(read().filter((x) => x.id !== id));
}

export function newSession(init: Pick<Session, "title" | "mode" | "items" | "timeLimitSec"> & { exam?: string }): Session {
  const s: Session = {
    ...init,
    id: Math.random().toString(36).slice(2, 10),
    startedAt: Date.now(),
    answers: {},
    flags: [],
    revealed: [],
    current: 0,
    elapsedSec: 0,
  };
  saveSession(s);
  return s;
}

/** 지금까지 틀린 문항(최근 기록 기준) */
export function wrongItems(isCorrect: (ref: ItemRef, choice: number | undefined) => boolean | null): ItemRef[] {
  const latest = new Map<string, boolean>();
  for (const s of listSessions().reverse()) {
    if (!s.finishedAt) continue;
    s.items.forEach((ref, i) => {
      const ok = isCorrect(ref, s.answers[i]);
      if (ok !== null) latest.set(`${ref.paperId}#${ref.no}`, ok);
    });
  }
  return [...latest.entries()].filter(([, ok]) => !ok).map(([k]) => {
    const [paperId, no] = k.split("#");
    return { paperId, no: Number(no) };
  });
}

/** 푼 적 있는 문항 키 집합 */
export function seenKeys(): Set<string> {
  const set = new Set<string>();
  for (const s of read()) s.items.forEach((r, i) => s.answers[i] !== undefined && set.add(`${r.paperId}#${r.no}`));
  return set;
}
