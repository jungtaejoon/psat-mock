import * as pdfjs from "pdfjs-dist";
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import type { PDFDocumentProxy } from "pdfjs-dist";
import type { Region } from "./types";

pdfjs.GlobalWorkerOptions.workerSrc = workerUrl;

const docs = new Map<string, Promise<PDFDocumentProxy>>();

export function getDoc(url: string) {
  let d = docs.get(url);
  if (!d) {
    d = pdfjs.getDocument({
      url,
      cMapUrl: "./pdfjs/cmaps/",
      cMapPacked: true,
      standardFontDataUrl: "./pdfjs/standard_fonts/",
    }).promise;
    docs.set(url, d);
  }
  return d;
}

/** 다음 문항 PDF 를 미리 받아 둔다 */
export function prefetchPdf(url: string) {
  getDoc(url).catch(() => docs.delete(url));
}

/**
 * PDF 의 한 영역만 그린다. cssWidth 는 화면에 보일 폭(px).
 * 같은 캔버스에 렌더가 겹치지 않도록 새 캔버스에 그려서 돌려준다.
 */
export async function renderRegion(url: string, r: Region, cssWidth: number): Promise<HTMLCanvasElement> {
  const canvas = document.createElement("canvas");
  const doc = await getDoc(url);
  const page = await doc.getPage(r.page + 1);
  const w = r.x1 - r.x0;
  const h = r.y1 - r.y0;
  const dpr = Math.min(window.devicePixelRatio || 1, 3);
  const scale = (cssWidth / w) * dpr;
  const viewport = page.getViewport({ scale, offsetX: -r.x0 * scale, offsetY: -r.y0 * scale });
  canvas.width = Math.ceil(w * scale);
  canvas.height = Math.ceil(h * scale);
  canvas.style.width = `${cssWidth}px`;
  canvas.style.height = `${(cssWidth * h) / w}px`;
  const ctx = canvas.getContext("2d")!;
  ctx.fillStyle = "#fff";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  await page.render({ canvasContext: ctx, viewport }).promise;
  canvas.className = "region";
  return canvas;
}
