import { useEffect, useRef, useState } from "react";
import { CIRCLED, loadExplanations, loadQuestion, loadText, pdfUrl } from "./data";
import { renderRegion } from "./pdf";
import { canViewExplanation } from "./monetization";
import { TextQuestion } from "./TextQuestion";
import { useViewMode } from "./viewMode";
import type {
  ChoiceBox,
  Explanation,
  ItemRef,
  Paper,
  Question,
  Region,
  TextItem,
} from "./types";

function RegionCanvas({
  url,
  region,
  width,
  children,
}: {
  url: string;
  region: Region;
  width: number;
  children?: React.ReactNode;
}) {
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
  if (err)
    return (
      <div className="render-error">문제 이미지를 불러오지 못했습니다.</div>
    );
  return (
    <div className="region-wrap">
      <div ref={ref} className="region-box" />
      {children}
    </div>
  );
}

/** 선택지 표시 상태: 고른 것, 채점 후 정답/오답 */
export interface ChoiceState {
  selected?: number;
  correct?: number[];
  onChoose?: (n: number) => void;
}

function ChoiceLayer({
  boxes,
  region,
  ri,
  state,
}: {
  boxes: ChoiceBox[];
  region: Region;
  ri: number;
  state: ChoiceState;
}) {
  const w = region.x1 - region.x0;
  const h = region.y1 - region.y0;
  const graded = !!state.correct;
  return (
    <>
      {boxes.map((b, i) => {
        if (b.r !== ri) return null;
        const n = i + 1;
        const sel = state.selected === n;
        let cls = "choice-hit";
        if (sel) cls += " sel";
        if (graded && state.correct!.includes(n)) cls += " correct";
        if (graded && sel && !state.correct!.includes(n)) cls += " wrong";
        const style = {
          left: `${((b.x0 - region.x0) / w) * 100}%`,
          top: `${((b.y0 - region.y0) / h) * 100}%`,
          width: `${((b.x1 - b.x0) / w) * 100}%`,
          height: `${((b.y1 - b.y0) / h) * 100}%`,
        };
        const kind =
          graded && state.correct!.includes(n)
            ? "correct"
            : graded && sel
              ? "wrong"
              : sel
                ? "sel"
                : null;
        // 고른 보기는 ①~⑤ 기호 자체를 OMR 처럼 칠한다 (글자 위에 배지를 얹지 않도록)
        const dot =
          kind && b.m
            ? (() => {
                const [mx0, my0, mx1, my1] = b.m;
                const d = Math.max(mx1 - mx0, 6) * 1.18;
                const cx = (mx0 + mx1) / 2;
                const cy = my0 + (my1 - my0) * 0.47;
                return (
                  <svg
                    key={`d${n}`}
                    className={`choice-dot ${kind}`}
                    viewBox="0 0 20 20"
                    aria-hidden="true"
                    style={{
                      left: `${((cx - d / 2 - region.x0) / w) * 100}%`,
                      top: `${((cy - d / 2 - region.y0) / h) * 100}%`,
                      width: `${(d / w) * 100}%`,
                      height: `${(d / h) * 100}%`,
                    }}
                  >
                    <circle cx="10" cy="10" r="10" />
                    <text
                      x="10"
                      y="10.5"
                      textAnchor="middle"
                      dominantBaseline="central"
                    >
                      {n}
                    </text>
                  </svg>
                );
              })()
            : null;
        const hit =
          state.onChoose && !graded ? (
            <button
              key={n}
              className={cls}
              style={style}
              role="radio"
              aria-checked={sel}
              aria-label={`${CIRCLED[i]} 선택`}
              onClick={() => state.onChoose!(n)}
            />
          ) : (
            <div key={n} className={cls} style={style} aria-hidden="true" />
          );
        return [hit, dot];
      })}
    </>
  );
}

/** 문항 영역들을 화면 폭에 맞춰 그린다. choice 를 주면 선택지를 문제 위에서 직접 고를 수 있다 */
export function QuestionImage({
  item,
  choice,
  onChoicesKnown,
}: {
  item: ItemRef;
  choice?: ChoiceState;
  onChoicesKnown?: (has: boolean) => void;
}) {
  const box = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(0);
  const [data, setData] = useState<{ paper: Paper; q: Question; text?: TextItem } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useViewMode();

  useEffect(() => {
    setData(null);
    setError(null);
    Promise.all([loadQuestion(item), loadText(item.paperId)]).then(
      ([d, texts]) => setData({ ...d, text: texts[String(item.no)] }),
      (e) => setError(String(e)),
    );
  }, [item.paperId, item.no]);

  const asText = !!(data?.text && (mode === "text" || data.paper.ai));
  useEffect(() => {
    // 보기를 문제 위에서 직접 고를 수 있는지 (없으면 화면 아래 번호 버튼을 쓴다)
    if (data) onChoicesKnown?.(asText || !!data.q.choices);
  }, [data, asText]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const ro = new ResizeObserver(() =>
      setWidth(Math.min(el.clientWidth, 640)),
    );
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const url = data ? pdfUrl(data.paper) : "";
  return (
    <div className="qimg" ref={box}>
      {error && <div className="render-error">{error}</div>}
      {!data && !error && <div className="skeleton" />}
      {data?.text && !data.paper.ai && (
        <div className="view-toggle" role="group" aria-label="문제 보기 방식">
          <button type="button" aria-pressed={mode === "pdf"} onClick={() => setMode("pdf")}>
            원본 PDF
          </button>
          <button type="button" aria-pressed={mode === "text"} onClick={() => setMode("text")}>
            텍스트
          </button>
        </div>
      )}
      {data && asText && <TextQuestion item={data.text!} no={data.q.orig ?? data.q.slot ?? data.q.no} choice={choice} />}
      {data && !asText && width > 0 && (
        <>
          {data.q.shared && (
            <div className="shared">
              {data.q.shared.regions.map((r, i) => (
                <RegionCanvas
                  key={`s${i}`}
                  url={url}
                  region={r}
                  width={
                    width * Math.min(1, (r.x1 - r.x0) / (data.paper.width / 2))
                  }
                />
              ))}
            </div>
          )}
          <div
            className={`q-regions ${choice?.onChoose && !choice.correct ? "pickable" : ""}`}
            role={choice?.onChoose ? "radiogroup" : undefined}
            aria-label={choice?.onChoose ? "답 선택" : undefined}
          >
            {data.q.regions.map((r, i) => (
              <RegionCanvas
                key={i}
                url={url}
                region={r}
                width={
                  width * Math.min(1, (r.x1 - r.x0) / (data.paper.width / 2))
                }
              >
                {choice && data.q.choices && (
                  <ChoiceLayer
                    boxes={data.q.choices}
                    region={r}
                    ri={i}
                    state={choice}
                  />
                )}
              </RegionCanvas>
            ))}
          </div>
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
          {line
            .split(/(\*\*[^*]+\*\*)/g)
            .map((seg, j) =>
              seg.startsWith("**") && seg.endsWith("**") ? (
                <strong key={j}>{seg.slice(2, -2)}</strong>
              ) : (
                seg
              ),
            )}
        </p>
      ))}
    </>
  );
}

export function ExplanationPanel({
  item,
  answer,
}: {
  item: ItemRef;
  answer: number[];
}) {
  const [open, setOpen] = useState(false);
  const [ex, setEx] = useState<Explanation | null | undefined>(undefined);

  useEffect(() => {
    setOpen(false);
    setEx(undefined);
  }, [item.paperId, item.no]);

  useEffect(() => {
    if (!open || ex !== undefined) return;
    loadExplanations(item.paperId).then((m) =>
      setEx(m[String(item.no)] ?? null),
    );
  }, [open, ex, item.paperId, item.no]);

  if (!canViewExplanation(item))
    return (
      <div className="expl locked">해설은 이용권 회원에게 제공됩니다.</div>
    );

  return (
    <div className="expl">
      <button
        className="btn ghost"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        {open ? "해설 닫기" : "해설 보기"}
      </button>
      {open && (
        <div className="expl-body">
          {ex === undefined && <div className="muted">불러오는 중…</div>}
          {ex === null && (
            <div className="muted">이 문항의 해설은 준비 중입니다.</div>
          )}
          {ex && (
            <>
              <div className="kp">💡 {ex.key_point}</div>
              <Rich text={ex.explanation} />
              {ex.choices?.length > 0 && answer.length < ex.choices.length && (
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
              <div className="ai-note">
                {item.paperId.startsWith("ai-") ? "AI가 만든 문항과 해설입니다. 공식 정답이 아니며 오류가 있을 수 있습니다." : "AI가 작성한 해설입니다. 정답은 시험 시행기관의 공식 발표 기준입니다."}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
