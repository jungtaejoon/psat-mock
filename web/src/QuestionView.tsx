import { useEffect, useRef, useState } from "react";
import { CIRCLED, loadExplanations, loadQuestion, pdfUrl } from "./data";
import { renderRegion } from "./pdf";
import { canViewExplanation } from "./monetization";
import type { Explanation, ItemRef, Paper, Question, Region } from "./types";

function RegionCanvas({ url, region, width }: { url: string; region: Region; width: number }) {
  const ref = useRef<HTMLDivElement>(null);
  const [err, setErr] = useState(false);
  useEffect(() => {
    if (!ref.current || width <= 0) return;
    let alive = true;
    const h = (width * (region.y1 - region.y0)) / (region.x1 - region.x0);
    ref.current.style.minHeight = `${h}px`;
    renderRegion(url, region, width).then(
      (c) => alive && ref.current?.replaceChildren(c),
      (e) => {
        console.error("render failed", url, region, e);
        if (alive) setErr(true);
      },
    );
    return () => {
      alive = false;
    };
  }, [url, region, width]);
  if (err) return <div className="render-error">문제 이미지를 불러오지 못했습니다.</div>;
  return <div ref={ref} className="region-box" />;
}

/** 문항 영역들을 화면 폭에 맞춰 그린다 */
export function QuestionImage({ item }: { item: ItemRef }) {
  const box = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(0);
  const [data, setData] = useState<{ paper: Paper; q: Question } | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setData(null);
    setError(null);
    loadQuestion(item).then(setData, (e) => setError(String(e)));
  }, [item.paperId, item.no]);

  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setWidth(Math.min(el.clientWidth, 640)));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const url = pdfUrl(item.paperId);
  return (
    <div className="qimg" ref={box}>
      {error && <div className="render-error">{error}</div>}
      {!data && !error && <div className="skeleton" />}
      {data && width > 0 && (
        <>
          {data.q.shared && (
            <div className="shared">
              {data.q.shared.regions.map((r, i) => (
                <RegionCanvas key={`s${i}`} url={url} region={r} width={width * Math.min(1, (r.x1 - r.x0) / (data.paper.width / 2))} />
              ))}
            </div>
          )}
          {data.q.regions.map((r, i) => (
            <RegionCanvas key={i} url={url} region={r} width={width * Math.min(1, (r.x1 - r.x0) / (data.paper.width / 2))} />
          ))}
        </>
      )}
    </div>
  );
}

function Rich({ text }: { text: string }) {
  // **굵게** 와 줄바꿈만 처리
  return (
    <>
      {text.split("\n").map((line, i) => (
        <p key={i}>
          {line.split(/(\*\*[^*]+\*\*)/g).map((seg, j) =>
            seg.startsWith("**") && seg.endsWith("**") ? <strong key={j}>{seg.slice(2, -2)}</strong> : seg,
          )}
        </p>
      ))}
    </>
  );
}

export function ExplanationPanel({ item, answer }: { item: ItemRef; answer: number[] }) {
  const [open, setOpen] = useState(false);
  const [ex, setEx] = useState<Explanation | null | undefined>(undefined);

  useEffect(() => {
    setOpen(false);
    setEx(undefined);
  }, [item.paperId, item.no]);

  useEffect(() => {
    if (!open || ex !== undefined) return;
    loadExplanations(item.paperId).then((m) => setEx(m[String(item.no)] ?? null));
  }, [open, ex, item.paperId, item.no]);

  if (!canViewExplanation(item)) return <div className="expl locked">해설은 이용권 회원에게 제공됩니다.</div>;

  return (
    <div className="expl">
      <button className="btn ghost" onClick={() => setOpen((v) => !v)} aria-expanded={open}>
        {open ? "해설 닫기" : "해설 보기"}
      </button>
      {open && (
        <div className="expl-body">
          {ex === undefined && <div className="muted">불러오는 중…</div>}
          {ex === null && <div className="muted">이 문항의 해설은 준비 중입니다.</div>}
          {ex && (
            <>
              <div className="kp">💡 {ex.key_point}</div>
              <Rich text={ex.explanation} />
              {ex.choices?.length === 5 && answer.length < 5 && (
                <ol className="choices">
                  {ex.choices.map((c, i) => (
                    <li key={i} className={answer.includes(i + 1) ? "ok" : ""}>
                      <span className="num">{CIRCLED[i]}</span>
                      <span>{c}</span>
                    </li>
                  ))}
                </ol>
              )}
              {ex.tip && <div className="tip">⏱ {ex.tip}</div>}
              <div className="ai-note">AI가 작성한 해설입니다. 공식 정답은 인사혁신처 발표 기준입니다.</div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
