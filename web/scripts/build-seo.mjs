/**
 * 검색엔진용 정적 페이지 생성 (vite build 뒤에 실행).
 *
 * 앱은 해시 라우팅(#/...)이라 검색엔진에는 첫 화면 하나로만 보인다.
 * 그래서 문제지마다 정답표·문항별 해설이 글자로 들어 있는 정적 HTML 을 따로 만든다.
 *   dist/psat/                 전체 기출 목록 (허브)
 *   dist/psat/<slug>/          문제지 하나: 정답표 + 문항별 해설, 앱으로 바로 풀기 링크
 *   dist/sitemap.xml           위 페이지 전부
 * 데이터는 public/data(index.json, papers/, explanations/)를 그대로 읽는다.
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const DATA = path.join(ROOT, "public", "data");
const DIST = path.join(ROOT, "dist");
const SITE = "https://alltests.ai.kr";
const CIRCLED = "①②③④⑤";
const TODAY = new Date().toISOString().slice(0, 10);

const GROUPS = [
  { key: "g5", label: "5급 공채·외교관", test: (ex) => ex.some((e) => e.startsWith("5급 공채") || e === "외교관후보자") },
  { key: "g7", label: "7급 공채·민경채", test: (ex) => ex.some((e) => e.includes("민간경력자") || e === "7급 공채") },
  { key: "r7", label: "지역인재 7급", test: (ex) => ex.some((e) => e.startsWith("지역인재")) },
];
const SUBJ = { 언어논리: "verbal", 자료해석: "data", 상황판단: "situation" };
const SUBJ_ORDER = ["언어논리", "자료해석", "상황판단"];

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const read = (p) => JSON.parse(fs.readFileSync(p, "utf8"));
const group = (exams) => GROUPS.find((g) => g.test(exams)) ?? { key: "etc", label: exams[0] ?? "기타" };

/** 해설 마크업: **굵게**, "- " 목록, 줄바꿈만 허용 */
function md(text) {
  const out = [];
  let list = null;
  for (const raw of String(text ?? "").split("\n")) {
    const line = raw.trim();
    const inline = esc(line).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
    if (line.startsWith("- ")) {
      list ??= [];
      list.push(`<li>${inline.slice(2)}</li>`);
      continue;
    }
    if (list) out.push(`<ul>${list.join("")}</ul>`), (list = null);
    if (line) out.push(`<p>${inline}</p>`);
  }
  if (list) out.push(`<ul>${list.join("")}</ul>`);
  return out.join("\n");
}

/** PDF 에서 뽑은 문항 글. 띄어쓰기가 깨진 옛 문제지는 사람이 읽기 어려워 첫 줄(발문)만 쓴다 */
function stemOf(q) {
  const t = q.text.replace(/^\s*(?:문\s*)?\d{1,2}\s*\.\s*/, "");
  const first = t.split("\n").find((l) => l.trim()) ?? "";
  let stem = first.trim();
  // 발문이 두 줄에 걸치면 물음표까지 이어 붙인다
  if (!/[?？]\s*$/.test(stem)) {
    const lines = t.split("\n").map((l) => l.trim());
    const end = lines.findIndex((l) => /[?？]\s*$/.test(l));
    if (end >= 0 && end < 3) stem = lines.slice(0, end + 1).join(" ");
  }
  return stem.length > 160 ? stem.slice(0, 160) + "…" : stem;
}
const spacedOk = (t) => t.length > 0 && (t.match(/ /g)?.length ?? 0) / t.length > 0.08;

function layout({ title, description, canonical, body, jsonld }) {
  return `<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>${esc(title)}</title>
<meta name="description" content="${esc(description)}" />
<link rel="canonical" href="${canonical}" />
<meta property="og:type" content="article" />
<meta property="og:site_name" content="alltests · PSAT 기출 모의고사" />
<meta property="og:title" content="${esc(title)}" />
<meta property="og:description" content="${esc(description)}" />
<meta property="og:url" content="${canonical}" />
<meta property="og:image" content="${SITE}/og.png" />
<meta name="twitter:card" content="summary_large_image" />
<link rel="icon" href="/favicon.svg" type="image/svg+xml" />
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css" />
<script type="application/ld+json">${JSON.stringify(jsonld)}</script>
<style>
:root{--bg:#f4f5f7;--surface:#fff;--ink:#1b1f27;--muted:#6b7280;--line:#e3e5ea;--brand:#1f4fd8;--ok:#0f8a5f;--soft:#e8eefc}
@media (prefers-color-scheme:dark){:root{--bg:#111318;--surface:#1a1d24;--ink:#e8eaef;--muted:#9aa1ad;--line:#2b2f39;--brand:#6f97ff;--ok:#3ccf95;--soft:#1e2a4a}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.65 "Pretendard Variable",Pretendard,-apple-system,"Apple SD Gothic Neo","Noto Sans KR",sans-serif}
main{max-width:860px;margin:0 auto;padding:20px 16px 56px}a{color:var(--brand)}
nav.crumb{font-size:13px;color:var(--muted)}nav.crumb a{color:var(--muted)}
h1{font-size:26px;line-height:1.3;margin:10px 0 6px;letter-spacing:-.02em}h2{font-size:18px;margin:0 0 6px;line-height:1.45}
.lead{color:var(--muted);margin:0 0 16px}.cta{display:flex;gap:8px;flex-wrap:wrap;margin:14px 0 22px}
.btn{display:inline-block;padding:10px 16px;border-radius:10px;background:var(--brand);color:#fff;text-decoration:none;font-weight:700}
.btn.ghost{background:var(--surface);color:var(--ink);border:1px solid var(--line)}
.card{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:16px 18px;margin:12px 0}
table{border-collapse:collapse;width:100%;font-size:14px}td,th{border:1px solid var(--line);padding:4px 6px;text-align:center}th{background:var(--soft);font-weight:600}
.ans{color:var(--ok);font-weight:700}.kp{font-weight:700;margin:6px 0}.tip{color:var(--muted);font-size:14px}
ol.ch{padding-left:0;list-style:none;margin:8px 0}ol.ch li{margin:2px 0}ol.ch li.ok{font-weight:600;color:var(--ok)}
details{margin-top:8px;font-size:14px;color:var(--muted)}details pre{white-space:pre-wrap;font:inherit}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:6px}.grid a{display:block;padding:8px 10px;background:var(--surface);border:1px solid var(--line);border-radius:8px;text-decoration:none;color:var(--ink)}
footer{color:var(--muted);font-size:13px;margin-top:28px}
</style>
</head>
<body>
<main>
${body}
<footer>문제·정답 출처: 인사혁신처 국가공무원 채용시스템(gongmuwon.gosi.kr). 해설은 AI(Claude)가 작성했으며 오류가 있을 수 있습니다. · <a href="/">alltests 홈</a> · <a href="/psat/">PSAT 기출 전체 목록</a></footer>
</main>
</body>
</html>
`;
}

const index = read(path.join(DATA, "index.json")).papers;

// slug: 2025-g5-verbal (같은 해·계열·영역에 문제지가 둘 이상이면 -2, -3)
const seen = new Map();
const papers = [...index]
  .sort((a, b) => b.year - a.year || a.id.localeCompare(b.id))
  .map((p) => {
    const g = group(p.exams);
    const base = `${p.year}-${g.key}-${SUBJ[p.subject] ?? "etc"}`;
    const n = (seen.get(base) ?? 0) + 1;
    seen.set(base, n);
    return { ...p, g, slug: n === 1 ? base : `${base}-${n}` };
  });
// 같은 슬롯에 둘 이상이면 제목에 시험 이름을 붙여 구별
const dupBase = new Set([...seen].filter(([, n]) => n > 1).map(([b]) => b));
for (const p of papers) {
  const base = p.slug.replace(/-\d$/, "");
  p.label = dupBase.has(base) ? p.exams.join("·") : p.g.label;
  p.title = `${p.year}년 ${p.label} PSAT ${p.subject} 기출문제 정답·해설`;
}

fs.rmSync(path.join(DIST, "psat"), { recursive: true, force: true });
let pages = 0;

for (const p of papers) {
  const paper = read(path.join(DATA, "papers", `${p.id}.json`));
  const exPath = path.join(DATA, "explanations", `${p.id}.json`);
  const ex = fs.existsSync(exPath) ? read(exPath) : {};
  const qs = paper.questions;
  const url = `${SITE}/psat/${p.slug}/`;
  const desc = `${p.year}년 ${p.exams.join(", ")} PSAT ${p.subject} 기출 ${qs.length}문항의 공식 정답과 문항별 해설. 빠른 풀이, 선택지별 판단, 시간 단축 팁까지. 실제 시험처럼 타이머·OMR로 바로 풀어 볼 수 있어요.`;

  const ansRows = [];
  for (let i = 0; i < qs.length; i += 10) {
    const chunk = qs.slice(i, i + 10);
    ansRows.push(
      `<tr><th>문항</th>${chunk.map((q) => `<th><a href="#q${q.no}">${q.no}</a></th>`).join("")}</tr>` +
        `<tr><th>정답</th>${chunk.map((q) => `<td class="ans">${q.answer.length >= 5 ? "전항" : q.answer.map((a) => CIRCLED[a - 1]).join("")}</td>`).join("")}</tr>`,
    );
  }

  const items = qs
    .map((q) => {
      const e = ex[String(q.no)];
      const ans = q.answer.length >= 5 ? "모두 정답 처리" : q.answer.map((a) => CIRCLED[a - 1]).join(", ");
      const shared = q.shared?.text ?? "";
      const raw = (shared ? shared + "\n\n" : "") + q.text;
      // 제목은 해설의 핵심 요약(주제어가 담겨 검색에 유리). 발문은 띄어쓰기가 살아 있을 때만 아래에
      const stem = stemOf(q);
      const heading = e?.key_point || stem;
      return `<section class="card" id="q${q.no}">
<h2>문 ${q.no}. ${esc(heading)}</h2>
${heading !== stem && spacedOk(stem) ? `<p class="tip">${esc(stem)}</p>` : ""}
<div>정답 <span class="ans">${ans}</span></div>
${
  e
    ? `
${md(e.explanation)}
<ol class="ch">${e.choices.map((c, i) => `<li${q.answer.includes(i + 1) ? ' class="ok"' : ""}>${CIRCLED[i]} ${esc(c)}</li>`).join("")}</ol>
${e.tip ? `<p class="tip">⏱ ${esc(e.tip)}</p>` : ""}`
    : `<p class="tip">이 문항의 해설은 준비 중이에요.</p>`
}
${spacedOk(raw) ? `<details><summary>문항 원문 텍스트</summary><pre>${esc(raw)}</pre></details>` : ""}
</section>`;
    })
    .join("\n");

  const sameYear = papers.filter((o) => o.year === p.year && o.g.key === p.g.key && o.id !== p.id);
  const sameSubj = papers.filter((o) => o.subject === p.subject && o.g.key === p.g.key && o.id !== p.id && Math.abs(o.year - p.year) <= 3);
  const related = [...sameYear, ...sameSubj]
    .filter((o, i, a) => a.indexOf(o) === i)
    .slice(0, 8)
    .map((o) => `<a href="/psat/${o.slug}/">${esc(`${o.year} ${o.label} ${o.subject}`)}</a>`)
    .join("");

  const body = `<nav class="crumb"><a href="/">alltests</a> › <a href="/psat/">PSAT 기출</a> › ${p.year} ${esc(p.label)}</nav>
<h1>${esc(p.title)}</h1>
<p class="lead">${esc(p.exams.join(" · "))} · ${qs.length}문항${p.answersFinal ? "" : " · 정답 확정 전(가답안)"}</p>
<div class="cta"><a class="btn" href="/#/start/${encodeURIComponent(p.id)}/exam">실전 모드로 풀기 (타이머·OMR)</a><a class="btn ghost" href="/#/start/${encodeURIComponent(p.id)}/practice">연습 모드로 풀기</a></div>
<section class="card"><h2>정답표</h2><table>${ansRows.join("")}</table></section>
${items}
${related ? `<section><h2>같이 보면 좋은 기출</h2><div class="grid">${related}</div></section>` : ""}`;

  const jsonld = {
    "@context": "https://schema.org",
    "@graph": [
      {
        "@type": "BreadcrumbList",
        itemListElement: [
          { "@type": "ListItem", position: 1, name: "alltests", item: `${SITE}/` },
          { "@type": "ListItem", position: 2, name: "PSAT 기출", item: `${SITE}/psat/` },
          { "@type": "ListItem", position: 3, name: p.title, item: url },
        ],
      },
      {
        "@type": "LearningResource",
        name: p.title,
        description: desc,
        url,
        inLanguage: "ko",
        educationalLevel: p.g.label,
        learningResourceType: "기출문제 해설",
        about: `PSAT ${p.subject}`,
        isAccessibleForFree: true,
        provider: { "@type": "Organization", name: "alltests", url: `${SITE}/` },
      },
    ],
  };

  const dir = path.join(DIST, "psat", p.slug);
  fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(path.join(dir, "index.html"), layout({ title: `${p.title} | alltests`, description: desc, canonical: url, body, jsonld }));
  pages++;
}

// 허브: 계열 → 연도 → 영역
const hubSections = GROUPS.map((g) => {
  const mine = papers.filter((p) => p.g.key === g.key);
  if (!mine.length) return "";
  const years = [...new Set(mine.map((p) => p.year))].sort((a, b) => b - a);
  const rows = years
    .map((y) => {
      const links = mine
        .filter((p) => p.year === y)
        .sort((a, b) => SUBJ_ORDER.indexOf(a.subject) - SUBJ_ORDER.indexOf(b.subject) || a.slug.localeCompare(b.slug))
        .map((p) => `<a href="/psat/${p.slug}/">${y} ${esc(p.label)} ${p.subject} <small>(${p.count}문항)</small></a>`)
        .join("");
      return `<h3>${y}년</h3><div class="grid">${links}</div>`;
    })
    .join("\n");
  return `<section class="card"><h2>${g.label} PSAT 기출</h2>${rows}</section>`;
}).join("\n");
const total = papers.reduce((n, p) => n + p.count, 0);
const minY = Math.min(...papers.map((p) => p.year));
const maxY = Math.max(...papers.map((p) => p.year));
const hubTitle = `PSAT 기출문제 정답·해설 전체 목록 (${minY}~${maxY}) | alltests`;
const hubDesc = `5급 공채·외교관, 7급 공채·민경채, 지역인재 7급 PSAT 기출 ${papers.length}개 문제지 ${total.toLocaleString()}문항의 정답표와 문항별 해설. 언어논리·자료해석·상황판단을 연도별로 보고 실제 시험처럼 풀어 보세요.`;
fs.mkdirSync(path.join(DIST, "psat"), { recursive: true });
fs.writeFileSync(
  path.join(DIST, "psat", "index.html"),
  layout({
    title: hubTitle,
    description: hubDesc,
    canonical: `${SITE}/psat/`,
    jsonld: {
      "@context": "https://schema.org",
      "@type": "CollectionPage",
      name: hubTitle,
      description: hubDesc,
      url: `${SITE}/psat/`,
      inLanguage: "ko",
    },
    body: `<nav class="crumb"><a href="/">alltests</a> › PSAT 기출</nav>
<h1>PSAT 기출문제 정답·해설 (${minY}~${maxY})</h1>
<p class="lead">문제지 ${papers.length}개 · ${total.toLocaleString()}문항 · 문항마다 AI 해설</p>
<div class="cta"><a class="btn" href="/">실전 모의고사 풀기</a><a class="btn ghost" href="/#/">랜덤 모의고사 만들기</a></div>
${hubSections}`,
  }),
);
pages++;

// sitemap
const urls = [
  { loc: `${SITE}/`, pri: "1.0", freq: "daily" },
  { loc: `${SITE}/psat/`, pri: "0.9", freq: "weekly" },
  ...papers.map((p) => ({ loc: `${SITE}/psat/${p.slug}/`, pri: p.year >= maxY - 2 ? "0.8" : "0.6", freq: "monthly" })),
];
fs.writeFileSync(
  path.join(DIST, "sitemap.xml"),
  `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
${urls.map((u) => `  <url><loc>${u.loc}</loc><lastmod>${TODAY}</lastmod><changefreq>${u.freq}</changefreq><priority>${u.pri}</priority></url>`).join("\n")}
</urlset>
`,
);

// 홈 index.html 의 정적 대체 내용(#root 안)에 최근 기출 링크를 채운다 — JS 를 실행하지 않는 수집기도 링크를 따라가게
const homePath = path.join(DIST, "index.html");
const home = fs.readFileSync(homePath, "utf8");
const recent = papers
  .filter((p) => p.year >= maxY - 1)
  .map((p) => `<li><a href="/psat/${p.slug}/">${esc(p.title)}</a></li>`)
  .join("");
fs.writeFileSync(homePath, home.replace("<!--SEO_RECENT-->", recent).replace(/__TOTAL__/g, total.toLocaleString()).replace(/__PAPERS__/g, String(papers.length)).replace(/__RANGE__/g, `${minY}~${maxY}`));

console.log(`seo: ${pages} pages, sitemap ${urls.length} urls`);
