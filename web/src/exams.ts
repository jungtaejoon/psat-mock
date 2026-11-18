/**
 * 시험 카탈로그. 사이트가 다루는 시험(=트랙)과 시험별 규칙을 한곳에 둔다.
 *
 * - 문제지(index.json 의 papers)는 `exam` 값으로 여기 항목과 연결된다. `exam` 이 없으면 PSAT.
 * - status "live": 문제지가 있으면 목록에 노출. "soon": 준비 중 카드로만 노출.
 * - 새 시험을 붙일 때: 여기 항목 추가 → 수집기가 index.json 에 exam/group/choices 를 넣으면 끝.
 */
import type { PaperMeta } from "./types";

import catalog from "./exams.json";

/** exams.json 한 항목 (검색 페이지 생성기 web/scripts/build-seo.mjs 도 같은 파일을 읽는다) */
interface ExamJson {
  id: string;
  name: string;
  /** 카드 아래 한 줄 설명 */
  desc: string;
  category: string;
  /** 기본 선택지 수 (문제지에 choices 가 있으면 그게 우선) */
  choices: number;
  /** 과목(영역) 표시 순서. 없으면 데이터에 나온 순서 */
  subjects?: string[];
  /** 시험 계열(그룹) 표시 순서. 없으면 데이터에 나온 순서 */
  groups?: string[];
  /** 실전 제한 시간 규칙: "psat" 이면 PSAT 규칙, 아니면 문항당 secPerQuestion 초 */
  timeRule?: "psat";
  secPerQuestion?: number;
  /** 문제·정답 출처 표기 */
  source: string;
  /** 검색용 정적 페이지 경로 (예: "psat" → /psat/). 없으면 id */
  seo?: string;
  status: "live" | "soon";
}

export interface ExamDef extends ExamJson {
  /** 문항 수 → 실전 모드 제한 시간(초) */
  timeLimit: (count: number) => number;
}

export const CATEGORIES: string[] = catalog.categories;

// PSAT 실제 시험 기준: 40문항 90분, 25문항 60분
const psatTime = (count: number) =>
  count >= 40
    ? Math.round((count / 40) * 90) * 60
    : Math.round(count * 2.4) * 60;

export const EXAMS: ExamDef[] = (catalog.exams as ExamJson[]).map((e) => ({
  ...e,
  timeLimit:
    e.timeRule === "psat"
      ? psatTime
      : (count: number) =>
          Math.round((count * (e.secPerQuestion ?? 60)) / 60) * 60,
}));

const BY_ID = new Map(EXAMS.map((e) => [e.id, e]));

export function examOf(p: Pick<PaperMeta, "exam">): ExamDef {
  return BY_ID.get(p.exam ?? "psat") ?? EXAMS[0];
}
export function getExam(id: string): ExamDef | undefined {
  return BY_ID.get(id);
}

/** PSAT 처럼 같은 문제지를 여러 시험이 함께 쓰는 경우, 시험 이름들로 계열을 정한다 */
function psatGroup(exams: string[]): string {
  if (exams.some((e) => e.startsWith("5급 공채") || e === "외교관후보자"))
    return "5급 공채·외교관";
  if (exams.some((e) => e.includes("민간경력자") || e === "7급 공채"))
    return "7급 공채·민경채";
  if (exams.some((e) => e.startsWith("지역인재"))) return "지역인재 7급";
  return exams[0] ?? "기타";
}

/** 문제지의 계열(그룹) 이름 */
export function groupOf(
  p: Pick<PaperMeta, "exam" | "group" | "exams">,
): string {
  return (
    p.group ??
    (examOf(p).id === "psat" ? psatGroup(p.exams) : (p.exams[0] ?? ""))
  );
}

/** 선택지 수 */
export function choicesOf(p: Pick<PaperMeta, "exam" | "choices">): number {
  return p.choices ?? examOf(p).choices;
}

/** 문항 묶음의 실전 제한 시간(초) */
export function timeLimitOf(exam: ExamDef, count: number): number {
  return exam.timeLimit(count);
}

/** 표시 순서대로 정렬한 값 목록 (정의된 순서 먼저, 나머지는 등장 순) */
export function ordered(
  defined: string[] | undefined,
  seen: string[],
): string[] {
  const uniq = [...new Set(seen)];
  if (!defined) return uniq;
  return [
    ...defined.filter((d) => uniq.includes(d)),
    ...uniq.filter((u) => !defined.includes(u)),
  ];
}
