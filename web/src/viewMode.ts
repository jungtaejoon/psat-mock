import { useEffect, useState } from "react";

/** 문제를 원본 PDF 그림으로 볼지, 글자로 옮긴 텍스트로 볼지 (기기에 기억) */
export type ViewMode = "pdf" | "text";

const KEY = "alltests.view";
const EVENT = "alltests:view";

export function getViewMode(): ViewMode {
  try {
    return localStorage.getItem(KEY) === "text" ? "text" : "pdf";
  } catch {
    return "pdf";
  }
}

export function setViewMode(m: ViewMode) {
  try {
    localStorage.setItem(KEY, m);
  } catch {
    /* 저장 못 해도 이번 화면에서는 바뀐다 */
  }
  window.dispatchEvent(new CustomEvent(EVENT, { detail: m }));
}

export function useViewMode(): [ViewMode, (m: ViewMode) => void] {
  const [mode, setMode] = useState<ViewMode>(getViewMode);
  useEffect(() => {
    const on = (e: Event) => setMode((e as CustomEvent<ViewMode>).detail);
    window.addEventListener(EVENT, on);
    return () => window.removeEventListener(EVENT, on);
  }, []);
  return [mode, setViewMode];
}
