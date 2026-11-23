/** AI 모의고사 문항 평가 (좋아요·별로예요·오류 있어요). 나쁜 평가가 쌓이면 다음 날 창고에서 빠지고 새 문항으로 바뀐다 */
import { useEffect, useState } from "react";
import { friendlyError, getRawReactions, toggleRaw } from "./api";

const KINDS = [
  { k: "good", e: "👍", label: "좋은 문제" },
  { k: "bad", e: "👎", label: "별로예요" },
  { k: "wrong_answer", e: "🚨", label: "오류 있어요" },
] as const;

export function isAiItem(paperId: string) {
  return paperId.startsWith("ai-");
}

export default function AiFeedback({ paperId, no }: { paperId: string; no: number }) {
  const target = `a:${paperId}:${no}`;
  const [mine, setMine] = useState<Record<string, boolean>>({});
  const [msg, setMsg] = useState("");
  useEffect(() => {
    setMine({});
    setMsg("");
    getRawReactions(target)
      .then((rs) => setMine(Object.fromEntries(rs.filter((r) => r.mine).map((r) => [r.kind, true]))))
      .catch(() => undefined);
  }, [target]);

  const press = async (k: string) => {
    setMine((m) => ({ ...m, [k]: !m[k] }));
    try {
      await toggleRaw(target, k);
      setMsg(k === "wrong_answer" && !mine[k] ? "알려 주셔서 고마워요. 확인되면 이 문항은 빠져요." : "");
    } catch (e) {
      setMine((m) => ({ ...m, [k]: !m[k] }));
      setMsg(friendlyError(e));
    }
  };

  return (
    <div className="ai-fb">
      <span className="ai-tag">AI 출제</span>
      <span className="muted">이 문항 어땠나요?</span>
      {KINDS.map((x) => (
        <button key={x.k} className={`react ${mine[x.k] ? "on" : ""}`} aria-pressed={!!mine[x.k]} onClick={() => press(x.k)}>
          <span className="e">{x.e}</span>
          {x.label}
        </button>
      ))}
      {msg && <span className="talk-msg">{msg}</span>}
    </div>
  );
}
