// pdf.js 의 한글 CMap·표준 폰트를 public 으로 복사 (CID 폰트 PDF 렌더링용)
import { cpSync, mkdirSync } from "node:fs";
mkdirSync("public/pdfjs", { recursive: true });
cpSync("node_modules/pdfjs-dist/cmaps", "public/pdfjs/cmaps", { recursive: true });
cpSync("node_modules/pdfjs-dist/standard_fonts", "public/pdfjs/standard_fonts", { recursive: true });
