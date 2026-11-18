export type Subject = "언어논리" | "자료해석" | "상황판단";
export const SUBJECTS: Subject[] = ["언어논리", "자료해석", "상황판단"];

export interface PaperMeta {
  id: string;
  year: number;
  subject: Subject;
  exams: string[];
  count: number;
  answersFinal: boolean;
}

export interface Region {
  page: number;
  x0: number;
  y0: number;
  x1: number;
  y1: number;
}

export interface Question {
  no: number;
  regions: Region[];
  text: string;
  /** 정답 선택지 번호(1~5). 복수 정답이면 여러 개, 전원 정답이면 [1,2,3,4,5] */
  answer: number[];
  shared?: { regions: Region[]; text: string };
  /** 선택지 ①~⑤ 의 클릭 영역 (r: regions 의 몇 번째 영역인지, 좌표는 PDF 페이지 기준). 못 찾은 문항은 없음 */
  choices?: ChoiceBox[];
}

export interface ChoiceBox {
  r: number;
  x0: number;
  y0: number;
  x1: number;
  y1: number;
}

export interface Paper extends Omit<PaperMeta, "count"> {
  booklet?: string;
  width: number;
  height: number;
  pages: number;
  questions: Question[];
}

export interface Explanation {
  key_point: string;
  explanation: string;
  choices: string[];
  tip: string;
}

export interface ItemRef {
  paperId: string;
  no: number;
}

export type Mode = "exam" | "practice";

export interface Session {
  id: string;
  title: string;
  mode: Mode;
  items: ItemRef[];
  timeLimitSec: number;
  startedAt: number;
  /** 문항 인덱스 → 고른 선택지 */
  answers: Record<number, number>;
  flags: number[];
  /** 연습 모드에서 정답을 확인한 문항 */
  revealed: number[];
  current: number;
  elapsedSec: number;
  finishedAt?: number;
}
