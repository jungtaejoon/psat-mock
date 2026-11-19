import { useMemo } from "react";
import katex from "katex";
import "katex/dist/katex.min.css";
import { CIRCLED, dataUrl } from "./data";
import type { ChoiceState } from "./QuestionView";
import type { TextItem } from "./types";

const ALLOWED = new Set(["P", "BR", "U", "B", "I", "SUP", "SUB", "DIV", "TABLE", "THEAD", "TBODY", "TR", "TH", "TD", "IMG", "SPAN"]);
const ATTRS = new Set(["class", "colspan", "rowspan", "data-fig"]);

/** 수식 \( … \) / \[ … \] 을 KaTeX 로 바꾼다 (글자 노드 안에서만) */
function renderMath(root: HTMLElement) {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  const nodes: Text[] = [];
  while (walker.nextNode()) nodes.push(walker.currentNode as Text);
  for (const node of nodes) {
    const t = node.data;
    if (!/\\\(|\\\[/.test(t)) continue;
    const frag = document.createDocumentFragment();
    let last = 0;
    for (const m of t.matchAll(/\\\((.+?)\\\)|\\\[(.+?)\\\]/gs)) {
      frag.append(t.slice(last, m.index));
      const span = document.createElement("span");
      const display = m[2] !== undefined;
      try {
        katex.render((m[1] ?? m[2]).trim(), span, { displayMode: display, throwOnError: false, output: "html" });
        if (display) span.className = "tq-math-block";
      } catch {
        span.textContent = m[0];
      }
      frag.append(span);
      last = (m.index ?? 0) + m[0].length;
    }
    frag.append(t.slice(last));
    node.replaceWith(frag);
  }
}

/** 변환된 HTML 을 허용한 태그·속성만 남기고, 그림 자리에 그림을, 수식에 KaTeX 를 넣는다 */
function toSafeHtml(src: string, figs: Record<string, string>): string {
  const doc = new DOMParser().parseFromString(`<div>${src}</div>`, "text/html");
  const root = doc.body.firstElementChild as HTMLElement;
  const walk = (el: Element) => {
    for (const c of [...el.children]) {
      if (!ALLOWED.has(c.tagName)) {
        c.replaceWith(...c.childNodes);
        continue;
      }
      for (const a of [...c.attributes]) if (!ATTRS.has(a.name)) c.removeAttribute(a.name);
      if (c.tagName === "IMG") {
        const f = figs[c.getAttribute("data-fig") ?? ""];
        if (!f) {
          c.remove();
          continue;
        }
        // 그림은 200dpi 로 잘라 두었다. 1.3x 로 표시하면 PDF 보기(약 150dpi)와 같은 크기가 된다
        c.setAttribute("src", dataUrl(f));
        c.setAttribute("srcset", `${dataUrl(f)} 1.3x`);
        c.setAttribute("alt", "문제 그림");
        c.setAttribute("loading", "lazy");
        c.className = "tq-fig";
        continue;
      }
      if (c.tagName === "TABLE") {
        const wrap = doc.createElement("div");
        wrap.className = "tq-table";
        c.replaceWith(wrap);
        wrap.appendChild(c);
      }
      walk(c);
    }
  };
  walk(root);
  renderMath(root);
  return root.innerHTML;
}

/** 글자로 옮긴 문항. 보기를 눌러 답을 고른다 */
export function TextQuestion({ item, no, choice }: { item: TextItem; no: number; choice?: ChoiceState }) {
  const stem = useMemo(() => toSafeHtml(item.stem, item.figs), [item]);
  const choices = useMemo(() => item.choices.map((c) => toSafeHtml(c, item.figs)), [item]);
  const graded = !!choice?.correct;
  return (
    <div className="tq">
      <div className="tq-stem">
        <span className="tq-no">{no}.</span>
        <div dangerouslySetInnerHTML={{ __html: stem }} />
      </div>
      <div className="tq-choices" role={choice?.onChoose ? "radiogroup" : undefined} aria-label={choice?.onChoose ? "답 선택" : undefined}>
        {choices.map((c, i) => {
          const n = i + 1;
          const sel = choice?.selected === n;
          let cls = "tq-choice";
          if (sel) cls += " sel";
          if (graded && choice!.correct!.includes(n)) cls += " correct";
          if (graded && sel && !choice!.correct!.includes(n)) cls += " wrong";
          const body = (
            <>
              <span className="tq-mark" aria-hidden="true">
                {CIRCLED[i]}
              </span>
              <span className="tq-choice-text" dangerouslySetInnerHTML={{ __html: c }} />
            </>
          );
          return choice?.onChoose && !graded ? (
            <button key={n} type="button" className={cls} role="radio" aria-checked={sel} onClick={() => choice.onChoose!(n)}>
              {body}
            </button>
          ) : (
            <div key={n} className={cls}>
              {body}
            </div>
          );
        })}
      </div>
    </div>
  );
}
