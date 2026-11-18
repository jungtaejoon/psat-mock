import type { Explanation, ItemRef, Paper, PaperMeta, Question } from "./types";

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

export function pdfUrl(paperId: string) {
  return `${BASE}/pdf/${paperId}.pdf`;
}

/** 시험 계열 묶음 (중복 제거된 문제지는 여러 시험명을 가진다) */
export function examGroup(exams: string[]): string {
  if (exams.some((e) => e.startsWith("5급 공채") || e === "외교관후보자")) return "5급 공채·외교관";
  if (exams.some((e) => e.includes("민간경력자") || e === "7급 공채")) return "7급 공채·민경채";
  if (exams.some((e) => e.startsWith("지역인재"))) return "지역인재 7급";
  return exams[0] ?? "기타";
}
export const EXAM_GROUPS = ["5급 공채·외교관", "7급 공채·민경채", "지역인재 7급"];

/** 실제 시험 기준 제한 시간: 40문항 90분, 25문항 60분 */
export function timeLimitFor(count: number): number {
  if (count >= 40) return Math.round((count / 40) * 90) * 60;
  return Math.round(count * 2.4) * 60;
}

export const CIRCLED = ["①", "②", "③", "④", "⑤"];
