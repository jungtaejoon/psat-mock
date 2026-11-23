/**
 * 수험생 이야기: 감정 반응 + 닉네임 댓글 (둘 다 로그인 없이).
 * - 실전 모드(시험 중)에는 아예 넣지 않는다. 연습 모드는 정답 확인 뒤, 결과 화면은 문항을 펼쳤을 때만.
 * - "이야기 숨기기"를 누르면 모든 화면에서 접어 둔다(기기에 저장).
 */
import { useCallback, useEffect, useState } from "react";
import {
  MOODS,
  addComment,
  deleteComment,
  friendlyError,
  getReactions,
  listComments,
  reportComment,
  saveName,
  savedName,
  toggleReaction,
  type Comment,
  type Mood,
  type ReactionCount,
} from "./api";

const VIS_KEY = "alltests.talk";
const VIS_EVENT = "alltests:talk";

export function useTalkVisible(): [boolean, (v: boolean) => void] {
  const read = () => {
    try {
      return localStorage.getItem(VIS_KEY) !== "off";
    } catch {
      return true;
    }
  };
  const [on, setOn] = useState(read);
  useEffect(() => {
    const f = () => setOn(read());
    window.addEventListener(VIS_EVENT, f);
    return () => window.removeEventListener(VIS_EVENT, f);
  }, []);
  const set = (v: boolean) => {
    try {
      localStorage.setItem(VIS_KEY, v ? "on" : "off");
    } catch {
      /* 저장이 막히면 이 화면에서만 */
    }
    setOn(v);
    window.dispatchEvent(new Event(VIS_EVENT));
  };
  return [on, set];
}

function ago(iso: string): string {
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 60) return "방금";
  if (s < 3600) return `${Math.floor(s / 60)}분 전`;
  if (s < 86400) return `${Math.floor(s / 3600)}시간 전`;
  if (s < 86400 * 30) return `${Math.floor(s / 86400)}일 전`;
  return new Date(iso).toLocaleDateString("ko-KR");
}

export default function Talk({ target, title = "수험생 이야기", big = false }: { target: string; title?: string; big?: boolean }) {
  const [visible, setVisible] = useTalkVisible();
  const [reacts, setReacts] = useState<ReactionCount[] | null>(null);
  const [comments, setComments] = useState<Comment[] | null>(null);
  const [name, setName] = useState(savedName);
  const [body, setBody] = useState("");
  const [mood, setMood] = useState<Mood | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  const load = useCallback(() => {
    setMsg("");
    getReactions(target).then(setReacts).catch(() => setReacts([]));
    listComments(target).then(setComments).catch(() => setComments([]));
  }, [target]);

  useEffect(() => {
    if (!visible) return;
    setReacts(null);
    setComments(null);
    load();
  }, [visible, load]);

  if (!visible)
    return (
      <div className="talk talk-hidden">
        <button className="btn ghost sm" onClick={() => setVisible(true)}>
          💬 {title} 보기
        </button>
      </div>
    );

  const count = (k: Mood) => reacts?.find((r) => r.kind === k);
  const react = async (k: Mood) => {
    const cur = count(k);
    // 먼저 화면에 반영하고, 실패하면 되돌린다
    setReacts((rs) => {
      const rest = (rs ?? []).filter((r) => r.kind !== k);
      const n = (cur?.n ?? 0) + (cur?.mine ? -1 : 1);
      return n > 0 ? [...rest, { kind: k, n, mine: !cur?.mine }] : rest;
    });
    try {
      await toggleReaction(target, k);
    } catch (e) {
      setMsg(friendlyError(e));
      load();
    }
  };

  const post = async () => {
    if (!body.trim() || busy) return;
    setBusy(true);
    setMsg("");
    try {
      const c = await addComment(target, body.trim(), mood, name.trim());
      saveName(name.trim() || "수험생");
      setComments((cs) => [c, ...(cs ?? [])]);
      setBody("");
      setMood(null);
    } catch (e) {
      setMsg(friendlyError(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className={`talk ${big ? "big" : ""}`} aria-label={title}>
      <div className="talk-head">
        <h3>💬 {title}</h3>
        <button className="link-btn" onClick={() => setVisible(false)} title="모든 화면에서 이야기를 접어 둡니다">
          숨기기
        </button>
      </div>

      <div className="react-row" role="group" aria-label="감정 반응">
        {MOODS.map((m) => {
          const c = count(m.k);
          return (
            <button
              key={m.k}
              className={`react ${c?.mine ? "on" : ""}`}
              onClick={() => react(m.k)}
              aria-pressed={!!c?.mine}
              disabled={reacts === null}
            >
              <span className="e">{m.e}</span>
              {m.label}
              {c && c.n > 0 && <b>{c.n}</b>}
            </button>
          );
        })}
      </div>

      <div className="composer">
        <textarea
          value={body}
          onChange={(e) => setBody(e.target.value.slice(0, 1000))}
          placeholder={big ? "이 시험에 대한 생각, 공부 팁, 응원 한마디를 남겨 주세요" : "이 문제 어땠나요? 풀이 팁이나 헷갈린 점을 남겨 주세요"}
          rows={big ? 3 : 2}
        />
        <div className="composer-foot">
          <input
            className="nick"
            value={name}
            onChange={(e) => setName(e.target.value.slice(0, 20))}
            aria-label="닉네임"
            placeholder="닉네임"
          />
          <div className="mood-pick" role="radiogroup" aria-label="기분">
            {MOODS.map((m) => (
              <button
                key={m.k}
                role="radio"
                aria-checked={mood === m.k}
                className={mood === m.k ? "on" : ""}
                onClick={() => setMood(mood === m.k ? null : m.k)}
                title={m.label}
              >
                {m.e}
              </button>
            ))}
          </div>
          <button className="btn primary sm" disabled={body.trim().length < 2 || busy} onClick={post}>
            남기기
          </button>
        </div>
      </div>

      {msg && <p className="talk-msg">{msg}</p>}

      {comments === null ? (
        <div className="skeleton" style={{ height: 48 }} />
      ) : comments.length === 0 ? (
        <p className="muted talk-empty">아직 남긴 이야기가 없어요. 첫 의견을 남겨 보세요.</p>
      ) : (
        <ul className="comments">
          {comments.map((c) => {
            const m = MOODS.find((x) => x.k === c.mood);
            return (
              <li key={c.id}>
                <div className="c-meta">
                  <b>{c.author_name}</b>
                  {m && (
                    <span className="c-mood" title={m.label}>
                      {m.e} {m.label}
                    </span>
                  )}
                  <span className="muted">{ago(c.created_at)}</span>
                  <span className="c-act">
                    {c.mine ? (
                      <button
                        className="link-btn"
                        onClick={async () => {
                          await deleteComment(c.id).catch((e) => setMsg(friendlyError(e)));
                          setComments((cs) => cs?.filter((x) => x.id !== c.id) ?? null);
                        }}
                      >
                        삭제
                      </button>
                    ) : (
                      <button
                        className="link-btn"
                        onClick={async () => {
                          await reportComment(c.id).catch(() => undefined);
                          setMsg("신고했어요. 여러 명이 신고하면 자동으로 가려져요.");
                        }}
                      >
                        신고
                      </button>
                    )}
                  </span>
                </div>
                <p className="c-body">{c.body}</p>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
