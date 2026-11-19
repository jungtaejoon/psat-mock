import type { Explanation, ItemRef, Paper, PaperMeta, Question, TextItem } from "./types";

const BASE = "./data";
const paperCache = new Map<string, Promise<Paper>>();
const explCache = new Map<string, Promise<Record<string, Explanation>>>();
let indexPromise: Promise<PaperMeta[]> | null = null;

export function loadIndex(): Promise<PaperMeta[]> {
  indexPromise ??= fetch(`${BASE}/index.json`, { cache: "no-cache" })
    .then((r) => r.json())
    .then((d) => d.papers as PaperMeta[]);
  return indexPromise;
}

export function loadPaper(id: string): Promise<Paper> {
  let p = paperCache.get(id);
  if (!p) {
    p = fetch(`${BASE}/papers/${id}.json`).then((r) => {
      if (!r.ok) throw new Error(`paper ${id} not found`);
      return r.json();
    });
    paperCache.set(id, p);
  }
  return p;
}

export async function loadQuestion(ref: ItemRef): Promise<{ paper: Paper; q: Question }> {
  const paper = await loadPaper(ref.paperId);
  const q = paper.questions.find((x) => x.no === ref.no);
  if (!q) throw new Error(`question ${ref.paperId}#${ref.no} not found`);
  return { paper, q };
}

export function loadExplanations(paperId: string): Promise<Record<string, Explanation>> {
  let p = explCache.get(paperId);
  if (!p) {
    p = fetch(`${BASE}/explanations/${paperId}.json`)
      .then((r) => (r.ok ? r.json() : {}))
      .catch(() => ({}));
    explCache.set(paperId, p);
  }
  return p;
}

const textCache = new Map<string, Promise<Record<string, TextItem>>>();

/** 글자로 옮긴 문항들 (문제지에 없으면 빈 객체) */
export function loadText(paperId: string): Promise<Record<string, TextItem>> {
  let p = textCache.get(paperId);
  if (!p) {
    p = fetch(`${BASE}/text/${paperId}.json`)
      .then((r) => (r.ok ? r.json() : {}))
      .catch(() => ({}));
    textCache.set(paperId, p);
  }
  return p;
}

/** data 폴더 안의 상대 경로(예: fig/…png) → 주소 */
export function dataUrl(path: string) {
  return `${BASE}/${path}`;
}

// 문제지 PDF 는 용량이 커서 별도 사이트(Cloudflare Pages, VITE_PDF_BASE)에 둘 수 있다. 비어 있으면 같은 사이트의 data/pdf
const PDF_BASE = (import.meta.env.VITE_PDF_BASE as string | undefined)?.replace(/\/$/, "") || `${BASE}/pdf`;

export function pdfUrl(paper: { id: string; pdf?: string }) {
  return `${PDF_BASE}/${paper.pdf ?? paper.id}.pdf`;
}

export const CIRCLED = ["①", "②", "③", "④", "⑤"];

/** 정답 표기: 선택지를 전부 정답 처리했으면 "전원 정답" */
export function answerLabel(answer: number[], choices: number): string {
  return answer.length >= choices ? "전원 정답" : answer.map((a) => CIRCLED[a - 1]).join(", ");
}
