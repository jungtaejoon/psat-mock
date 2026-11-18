/** #/start/<paperId>/<exam|practice> — 검색 페이지(/psat/...)에서 문제지 하나를 바로 시작한다 */
import { useEffect, useState } from "react";
import { loadIndex } from "./data";
import { examOf, groupOf, timeLimitOf } from "./exams";
import { newSession } from "./store";
import { navigate } from "./router";
import type { Mode } from "./types";

export default function StartPaper({
  paperId,
  mode,
}: {
  paperId: string;
  mode: Mode;
}) {
  const [error, setError] = useState(false);
  useEffect(() => {
    let alive = true;
    loadIndex().then((papers) => {
      if (!alive) return;
      const p = papers.find((x) => x.id === paperId);
      if (!p) return setError(true);
      const exam = examOf(p);
      const items = Array.from({ length: p.count }, (_, i) => ({
        paperId: p.id,
        no: i + 1,
      }));
      const s = newSession({
        exam: exam.id,
        title: `${p.year} ${groupOf(p)} ${p.subject}`,
        mode,
        items,
        timeLimitSec: mode === "exam" ? timeLimitOf(exam, items.length) : 0,
      });
      // 기록을 바꿔치기해서 뒤로 가기로 시작 화면에 다시 오지 않게 한다 (hashchange 도 발생)
      window.location.replace(`#/exam/${s.id}`);
    });
    return () => {
      alive = false;
    };
  }, [paperId, mode]);
  if (error)
    return (
      <div className="center">
        문제지를 찾지 못했습니다.{" "}
        <button className="btn" onClick={() => navigate("/")}>
          처음으로
        </button>
      </div>
    );
  return <div className="center muted">문제지를 여는 중…</div>;
}
