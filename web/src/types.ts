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
  /** 글자로 옮긴 문항 수 (원본 PDF 대신 텍스트로 풀 수 있음) */
  text?: number;
}

/** 글자로 옮긴 문항 (data/text/<문제지>.json 의 한 항목). stem·choices 는 제한된 HTML + LaTeX 수식 */
export interface TextItem {
  stem: string;
  choices: string[];
  /** 그림 id → data 폴더 안 경로 */
  figs: Record<string, string>;
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
  /** 시험지에 인쇄된 원래 번호 (과목별로 나눈 문제지에서 no 와 다를 수 있음) */
  orig?: number;
  /** AI 모의고사 문항: 기출의 몇 번 자리(칸)를 본떴는지, 평가가 나빠 빠졌는지(날짜) */
  slot?: number;
  retired?: string;
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
  /** AI 모의고사 문항 창고 (그림 없이 글자로만 보여 준다) */
  ai?: boolean;
  /** 문제 PDF 파일 id (여러 과목 문제지가 한 PDF 를 같이 쓸 때). 없으면 문제지 id */
  pdf?: string;
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
