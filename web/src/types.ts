/** 과목(영역) 이름. 시험마다 다르다 (PSAT: 언어논리·자료해석·상황판단) */
export type Subject = string;

export interface PaperMeta {
  id: string;
  /** 시험 카탈로그 id (exams.ts). 없으면 "psat" */
  exam?: string;
  /** 시험 안의 계열(예: "5급 공채·외교관", "1차"). 없으면 시험별 규칙으로 계산 */
  group?: string;
  year: number;
  subject: Subject;
  exams: string[];
  count: number;
  answersFinal: boolean;
  /** 선택지 수. 없으면 시험 기본값 */
  choices?: number;
  /** 해설이 있는 문항 수 */
  explained?: number;
  /** 공공누리 유형 (1~4). 모르면 없음 */
  kogl?: number;
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
  /** ①~⑤ 기호 자체의 위치 [x0, y0, x1, y1] (고른 보기의 번호를 칠해 표시할 때 씀) */
  m?: [number, number, number, number];
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
  /** 시험 카탈로그 id. 예전 기록에는 없음(=psat) */
  exam?: string;
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
