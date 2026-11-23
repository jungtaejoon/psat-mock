/**
 * 검색엔진용 정적 페이지 생성 (vite build 뒤에 실행).
 *
 * 앱은 해시 라우팅(#/...)이라 검색엔진에는 첫 화면 하나로만 보인다.
 * 그래서 문제지마다 정답표·문항별 해설이 글자로 들어 있는 정적 HTML 을 따로 만든다.
 *   dist/<시험>/               시험별 전체 기출 목록 (허브) — PSAT 는 /psat/
 *   dist/<시험>/<slug>/        문제지 하나: 정답표 + 문항별 해설, 앱으로 바로 풀기 링크
 *   dist/sitemap.xml           위 페이지 전부
 * 데이터는 public/data(index.json, papers/, explanations/), 시험 목록은 src/exams.json 을 읽는다.
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import katex from "katex";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const DATA = path.join(ROOT, "public", "data");
const DIST = path.join(ROOT, "dist");
const SITE = "https://alltests.ai.kr";
const CIRCLED = "①②③④⑤";
const TODAY = new Date().toISOString().slice(0, 10);

const CATALOG = JSON.parse(
  fs.readFileSync(path.join(ROOT, "src", "exams.json"), "utf8"),
);
const EXAM = new Map(CATALOG.exams.map((e) => [e.id, e]));
const PSAT_GROUP = (exams) =>
  exams.some((e) => e.startsWith("5급 공채") || e === "외교관후보자")
    ? "5급 공채·외교관"
    : exams.some((e) => e.includes("민간경력자") || e === "7급 공채")
      ? "7급 공채·민경채"
      : exams.some((e) => e.startsWith("지역인재"))
        ? "지역인재 7급"
        : (exams[0] ?? "기타");
const groupOf = (p) =>
  p.group ??
  ((p.exam ?? "psat") === "psat" ? PSAT_GROUP(p.exams) : (p.exams[0] ?? ""));
/** 주소용 조각: 정해 둔 영문 키가 있으면 그것, 없으면 공백·기호만 정리한 원래 이름 */
const slugPart = (map, v) =>
  map?.[v] ??
  String(v)
    .trim()
    .replace(/[\s/·()]+/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "");
const ordered = (defined, seen) => {
  const uniq = [...new Set(seen)];
  return defined
    ? [
        ...defined.filter((d) => uniq.includes(d)),
        ...uniq.filter((u) => !defined.includes(u)),
      ]
    : uniq;
};

/** 제목 앞부분: 말이 겹치지 않게 ("국가직 9급" + "9급 공무원" → "국가직 9급 공무원", 자격증은 "공인중개사 1차") */
function titleCore(exam, label) {
  const lab = String(label ?? "").replace(/^필기$/, "");
  if ((exam.id ?? "") === "psat") return `${lab} PSAT`.trim();
  const last = lab.split(/\s+/).pop();
  if (last && exam.name.startsWith(last)) return `${lab} ${exam.name.slice(last.length).trim()}`.trim();
  if (exam.category === "공무원") return `${lab} ${exam.name}`.trim();
  return `${exam.name} ${lab}`.trim();
}

const esc = (s) =>
  String(s ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const read = (p) => JSON.parse(fs.readFileSync(p, "utf8"));

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
    if (list) (out.push(`<ul>${list.join("")}</ul>`), (list = null));
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
const spacedOk = (t) =>
  t.length > 0 && (t.match(/ /g)?.length ?? 0) / t.length > 0.08;

/** 글자로 옮긴 문항(data/text) 의 HTML: 허용 태그·속성만 남기고, 그림 자리에 그림, 수식은 KaTeX 로 미리 그린다 */
const TAGS = new Set(["p", "br", "u", "b", "i", "sup", "sub", "div", "table", "thead", "tbody", "tr", "th", "td", "img", "span"]);
const unesc = (s) => s.replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&amp;/g, "&");
function textHtml(src, figs) {
  let out = String(src ?? "").replace(/<(\/?)([a-zA-Z0-9]+)([^>]*)>/g, (m, close, tag, attrs) => {
    const t = tag.toLowerCase();
    if (!TAGS.has(t)) return "";
    if (close) return `</${t}>`;
    if (t === "img") {
      const id = /data-fig="([^"]+)"/.exec(attrs)?.[1];
      return id && figs?.[id] ? `<img class="fig" src="/data/${esc(figs[id])}" alt="문제 그림" loading="lazy">` : "";
    }
    const keep = [...attrs.matchAll(/\s(class|colspan|rowspan)="([^"]*)"/g)].map((a) => ` ${a[1]}="${esc(a[2])}"`).join("");
    return t === "table" ? `<div class="tw"><table${keep}>` : `<${t}${keep}>`;
  });
  out = out.replace(/<\/table>/g, "</table></div>");
  return out.replace(/\\\(([\s\S]+?)\\\)|\\\[([\s\S]+?)\\\]/g, (m, a, b) => {
    try {
      return katex.renderToString(unesc(a ?? b).trim(), { displayMode: b !== undefined, throwOnError: false, strict: "ignore", output: "html" });
    } catch {
      return esc(m);
    }
  });
}
const plainOf = (html) => unesc(String(html).replace(/<[^>]+>/g, " ")).replace(/\\[()[\]]/g, "").replace(/\s+/g, " ").trim();

function layout({ exam, title, description, canonical, body, jsonld, math = false }) {
  return `<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>${esc(title)}</title>
<meta name="description" content="${esc(description)}" />
<link rel="canonical" href="${canonical}" />
<meta property="og:type" content="article" />
<meta property="og:site_name" content="올테스트 · 기출 모의고사" />
<meta property="og:title" content="${esc(title)}" />
<meta property="og:description" content="${esc(description)}" />
<meta property="og:url" content="${canonical}" />
<meta property="og:image" content="${SITE}/og.png?v=4" />
<meta name="twitter:card" content="summary_large_image" />
<link rel="icon" href="/favicon.svg" type="image/svg+xml" />
<link rel="icon" href="/favicon.ico" sizes="48x48" />
<link rel="apple-touch-icon" href="/apple-touch-icon.png" />
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css" />
${math ? '<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.22/dist/katex.min.css" />' : ""}
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
.qt{margin:8px 0;font-size:15.5px}.qt p{margin:0 0 .45em}.qt .box{border:1px solid var(--ink);padding:8px 12px;margin:.5em 0}.qt .box-title{text-align:center}
.qt p.item{padding-left:1.6em;text-indent:-1.6em}.qt .cap{font-size:13px;color:var(--muted)}.qt .right{text-align:right}
.tw{overflow-x:auto;margin:.5em 0}.tw table{width:auto;margin:0 auto}.tw td{white-space:nowrap}
img.fig{display:block;max-width:100%;height:auto;margin:.5em auto;background:#fff;border-radius:4px}
ol.qc{list-style:none;padding:0;margin:6px 0 10px}ol.qc li{display:flex;gap:8px;margin:2px 0}ol.qc li.ok{color:var(--ok);font-weight:600}ol.qc .m{flex:none}
.katex-display{overflow-x:auto;overflow-y:hidden}
.chips{display:flex;flex-wrap:wrap;gap:6px}.chips a{padding:6px 12px;border-radius:999px;border:1px solid var(--line);background:var(--bg);color:var(--ink);text-decoration:none;font-size:14px}.chips a:hover{border-color:var(--brand);color:var(--brand)}
.top{position:sticky;top:0;z-index:5;background:var(--bg);border-bottom:1px solid var(--line)}.top div{max-width:860px;margin:0 auto;padding:0 16px;height:52px;display:flex;align-items:center;gap:10px}
.top a{display:flex;align-items:center;gap:8px;color:var(--ink);text-decoration:none;font-weight:800;font-size:17px;letter-spacing:-.03em}.top span{font-size:12px;color:var(--muted);font-weight:600}.top .go{margin-left:auto;font-size:13px;font-weight:700;color:var(--brand)}
</style>
</head>
<body>
<header class="top"><div><a href="/"><svg width="26" height="26" viewBox="0 0 28 28" aria-hidden="true"><rect x="1" y="1" width="26" height="26" rx="7" fill="#1f4fd8"/><circle cx="9" cy="10" r="3" fill="none" stroke="#fff" stroke-width="1.6"/><circle cx="19" cy="10" r="3.4" fill="#fff"/><circle cx="9" cy="19" r="3.4" fill="#fff"/><circle cx="19" cy="19" r="3" fill="none" stroke="#fff" stroke-width="1.6"/></svg>올테스트</a><span>기출 모의고사</span><a class="go" href="/${exam.seo ?? exam.id}/">${esc(exam.name)} 기출 전체</a></div></header>
<main>
${body}
<footer>문제·정답 출처: ${esc(exam.source)}. 해설은 AI(Claude)가 작성한 것으로 공식 해설이 아니며 오류가 있을 수 있습니다. · <a href="/">올테스트 홈</a> · <a href="/${exam.seo ?? exam.id}/">${esc(exam.name)} 기출 전체 목록</a></footer>
</main>
<script src="/track.js" defer></script>
</body>
</html>
`;
}

const index = read(path.join(DATA, "index.json")).papers;
let pages = 0;
const urls = [{ loc: `${SITE}/`, pri: "1.0", freq: "daily" }];
const recentLinks = [];
const examSummaries = [];
const rssItems = [];

function buildExam(exam, list) {
  const base = exam.seo ?? exam.id;
  const slugs = exam.slugs ?? {};
  const subjSlug = (sb) => encodeURIComponent(slugPart(slugs.subjects, sb));
  const ANS = (q) =>
    q.answer.length >= (q.choices ?? exam.choices)
      ? "전항"
      : q.answer.map((a) => CIRCLED[a - 1]).join("");

  // slug: 2025-g5-verbal (같은 해·계열·영역에 문제지가 둘 이상이면 -2, -3)
  const seen = new Map();
  const papers = [...list]
    .sort((a, b) => b.year - a.year || a.id.localeCompare(b.id))
    .map((p) => {
      const gl = groupOf(p);
      const g = { key: slugPart(slugs.groups, gl), label: gl };
      const sb = `${p.year}-${g.key}-${slugPart(slugs.subjects, p.subject)}`;
      const n = (seen.get(sb) ?? 0) + 1;
      seen.set(sb, n);
      return { ...p, g, slug: n === 1 ? sb : `${sb}-${n}` };
    });
  // 같은 슬롯에 둘 이상이면 제목에 시험 이름을 붙여 구별
  const dupBase = new Set([...seen].filter(([, n]) => n > 1).map(([b]) => b));
  for (const p of papers) {
    const sb = p.slug.replace(/-\d$/, "");
    p.label = dupBase.has(sb) ? p.exams.join("·") : p.g.label;
    p.title = `${p.year}년 ${titleCore(exam, p.label)} ${p.subject} 기출문제 정답·해설`;
  }

  fs.rmSync(path.join(DIST, base), { recursive: true, force: true });

  for (const p of papers) {
    const paper = read(path.join(DATA, "papers", `${p.id}.json`));
    const exPath = path.join(DATA, "explanations", `${p.id}.json`);
    const ex = fs.existsSync(exPath) ? read(exPath) : {};
    const txPath = path.join(DATA, "text", `${p.id}.json`);
    const tx = fs.existsSync(txPath) ? read(txPath) : {};
    const hasMath = Object.values(tx).some((t) => /\\[([]/.test(t.stem + t.choices.join("")));
    const qs = paper.questions;
    const url = `${SITE}/${base}/${p.slug}/`;
    const desc = `${p.year}년 ${p.exams.join(", ")} ${exam.name} ${p.subject} 기출 ${qs.length}문항의 공식 정답과 문항별 해설. 빠른 풀이, 선택지별 판단, 시간 단축 팁까지. 실제 시험처럼 타이머·OMR로 바로 풀어 볼 수 있어요.`;

    const ansRows = [];
    for (let i = 0; i < qs.length; i += 10) {
      const chunk = qs.slice(i, i + 10);
      ansRows.push(
        `<tr><th>문항</th>${chunk.map((q) => `<th><a href="#q${q.no}">${q.no}</a></th>`).join("")}</tr>` +
          `<tr><th>정답</th>${chunk.map((q) => `<td class="ans">${ANS({ ...q, choices: paper.choices })}</td>`).join("")}</tr>`,
      );
    }

    const items = qs
      .map((q) => {
        const e = ex[String(q.no)];
        const ans =
          q.answer.length >= (paper.choices ?? exam.choices)
            ? "모두 정답 처리"
            : q.answer.map((a) => CIRCLED[a - 1]).join(", ");
        const shared = q.shared?.text ?? "";
        const raw = (shared ? shared + "\n\n" : "") + q.text;
        // 제목은 해설의 핵심 요약(주제어가 담겨 검색에 유리). 발문은 띄어쓰기가 살아 있을 때만 아래에
        const t = tx[String(q.no)];
        let stem = t ? plainOf(t.stem) : stemOf(q);
        if (stem.length > 160) stem = stem.slice(0, 160) + "…";
        const heading = e?.key_point || stem;
        // 글자로 옮긴 문항은 문제 전체(지문·표·보기)를 싣는다
        const body = t
          ? `<div class="qt">${textHtml(t.stem, t.figs)}</div>
<ol class="qc">${t.choices.map((c, i) => `<li${q.answer.includes(i + 1) ? ' class="ok"' : ""}><span class="m">${CIRCLED[i]}</span><span>${textHtml(c, t.figs)}</span></li>`).join("")}</ol>`
          : "";
        return `<section class="card" id="q${q.no}">
<h2>문 ${q.no}. ${esc(heading)}</h2>
${body || (heading !== stem && spacedOk(stem) ? `<p class="tip">${esc(stem)}</p>` : "")}
<div>정답 <span class="ans">${ans}</span></div>
${
  e
    ? `
${md(e.explanation)}
<ol class="ch">${e.choices.map((c, i) => `<li${q.answer.includes(i + 1) ? ' class="ok"' : ""}>${CIRCLED[i]} ${esc(c)}</li>`).join("")}</ol>
${e.tip ? `<p class="tip">⏱ ${esc(e.tip)}</p>` : ""}`
    : `<p class="tip">이 문항의 해설은 준비 중이에요.</p>`
}
${!t && spacedOk(raw) ? `<details><summary>문항 원문 텍스트</summary><pre>${esc(raw)}</pre></details>` : ""}
</section>`;
      })
      .join("\n");

    const sameYear = papers.filter(
      (o) => o.year === p.year && o.g.key === p.g.key && o.id !== p.id,
    );
    const sameSubj = papers.filter(
      (o) =>
        o.subject === p.subject &&
        o.g.key === p.g.key &&
        o.id !== p.id &&
        Math.abs(o.year - p.year) <= 3,
    );
    const related = [...sameYear, ...sameSubj]
      .filter((o, i, a) => a.indexOf(o) === i)
      .slice(0, 8)
      .map(
        (o) =>
          `<a href="/${base}/${o.slug}/">${esc(`${o.year} ${o.label} ${o.subject}`)}</a>`,
      )
      .join("");

    const body = `<nav class="crumb"><a href="/">올테스트</a> › <a href="/${base}/">${esc(exam.name)} 기출</a> › <a href="/${base}/s/${subjSlug(p.subject)}/">${esc(p.subject)}</a> › ${p.year}</nav>
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
            {
              "@type": "ListItem",
              position: 1,
              name: "올테스트",
              item: `${SITE}/`,
            },
            {
              "@type": "ListItem",
              position: 2,
              name: `${exam.name} 기출`,
              item: `${SITE}/${base}/`,
            },
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
          about: `${exam.name} ${p.subject}`,
          isAccessibleForFree: true,
          provider: {
            "@type": "Organization",
            name: "올테스트",
            url: `${SITE}/`,
          },
        },
      ],
    };

    const dir = path.join(DIST, base, p.slug);
    fs.mkdirSync(dir, { recursive: true });
    fs.writeFileSync(
      path.join(dir, "index.html"),
      layout({
        exam,
        title: `${p.title} | 올테스트`,
        description: desc,
        canonical: url,
        body,
        jsonld,
        math: hasMath,
      }),
    );
    pages++;
  }

  // 허브: 계열 → 연도 → 과목
  const subjOrder = ordered(
    exam.subjects,
    papers.map((p) => p.subject),
  );
  const hubSections = ordered(
    exam.groups,
    papers.map((p) => p.g.label),
  )
    .map((gl) => {
      const mine = papers.filter((p) => p.g.label === gl);
      const years = [...new Set(mine.map((p) => p.year))].sort((a, b) => b - a);
      const rows = years
        .map((y) => {
          const links = mine
            .filter((p) => p.year === y)
            .sort(
              (a, b) =>
                subjOrder.indexOf(a.subject) - subjOrder.indexOf(b.subject) ||
                a.slug.localeCompare(b.slug),
            )
            .map(
              (p) =>
                `<a href="/${base}/${p.slug}/">${y} ${esc(p.label)} ${esc(p.subject)} <small>(${p.count}문항)</small></a>`,
            )
            .join("");
          return `<h3>${y}년</h3><div class="grid">${links}</div>`;
        })
        .join("\n");
      return `<section class="card"><h2>${esc(gl)} ${esc(exam.name)} 기출</h2>${rows}</section>`;
    })
    .join("\n");
  const total = papers.reduce((n, p) => n + p.count, 0);
  const minY = Math.min(...papers.map((p) => p.year));
  const maxY = Math.max(...papers.map((p) => p.year));

  // 과목별 모음: /<시험>/s/<과목>/ — "9급 국어 기출문제" 같은 검색어용
  const subjLinks = [];
  for (const sb of subjOrder) {
    const mine = papers.filter((p) => p.subject === sb);
    if (!mine.length) continue;
    const ys = mine.map((p) => p.year);
    const a = Math.min(...ys), b = Math.max(...ys);
    const n = mine.reduce((k, p) => k + p.count, 0);
    const url = `${SITE}/${base}/s/${subjSlug(sb)}/`;
    const t = `${exam.name} ${sb} 기출문제 모음 (${a}~${b}) 정답·해설`;
    const d = `${exam.name} ${sb} 기출문제 ${mine.length}회분 ${n.toLocaleString()}문항을 연도별로 모았습니다. 공식 정답과 문항별 해설을 보고, 실제 시험처럼 타이머·OMR 로 풀어 보세요.`;
    const rows = [...mine]
      .sort((x, y) => y.year - x.year || x.slug.localeCompare(y.slug))
      .map((p) => `<a href="/${base}/${p.slug}/">${p.year}년 ${esc(p.label)} ${esc(sb)} <small>(${p.count}문항)</small></a>`)
      .join("");
    const dir = path.join(DIST, base, "s", slugPart(slugs.subjects, sb));
    fs.mkdirSync(dir, { recursive: true });
    fs.writeFileSync(
      path.join(dir, "index.html"),
      layout({
        exam,
        title: `${t} | 올테스트`,
        description: d,
        canonical: url,
        jsonld: {
          "@context": "https://schema.org",
          "@graph": [
            {
              "@type": "BreadcrumbList",
              itemListElement: [
                { "@type": "ListItem", position: 1, name: "올테스트", item: `${SITE}/` },
                { "@type": "ListItem", position: 2, name: `${exam.name} 기출`, item: `${SITE}/${base}/` },
                { "@type": "ListItem", position: 3, name: `${sb} 기출`, item: url },
              ],
            },
            { "@type": "CollectionPage", name: t, description: d, url, inLanguage: "ko" },
          ],
        },
        body: `<nav class="crumb"><a href="/">올테스트</a> › <a href="/${base}/">${esc(exam.name)} 기출</a> › ${esc(sb)}</nav>
<h1>${esc(t.replace(" 정답·해설", ""))}</h1>
<p class="lead">${mine.length}회분 · ${n.toLocaleString()}문항 · 공식 정답과 문항별 AI 해설</p>
<div class="cta"><a class="btn" href="/#/x/${exam.id}">${esc(exam.name)} 실전 모의고사 풀기</a></div>
<section class="card"><h2>${esc(sb)} 연도별 기출문제</h2><div class="grid">${rows}</div></section>`,
      }),
    );
    pages++;
    urls.push({ loc: url, pri: "0.85", freq: "weekly" });
    subjLinks.push(`<a class="chip" href="/${base}/s/${subjSlug(sb)}/">${esc(sb)} <small>${mine.length}회</small></a>`);
  }
  const hubTitle = `${exam.name} 기출문제 정답·해설 전체 목록 (${minY}~${maxY}) | 올테스트`;
  const hubDesc = `${exam.desc} 기출 ${papers.length}개 문제지 ${total.toLocaleString()}문항의 정답표와 문항별 해설. ${subjOrder.join("·")}을 연도별로 보고 실제 시험처럼 풀어 보세요.`;
  fs.mkdirSync(path.join(DIST, base), { recursive: true });
  fs.writeFileSync(
    path.join(DIST, base, "index.html"),
    layout({
      exam,
      title: hubTitle,
      description: hubDesc,
      canonical: `${SITE}/${base}/`,
      jsonld: {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        name: hubTitle,
        description: hubDesc,
        url: `${SITE}/${base}/`,
        inLanguage: "ko",
      },
      body: `<nav class="crumb"><a href="/">올테스트</a> › ${esc(exam.name)} 기출</nav>
<h1>${esc(exam.name)} 기출문제 정답·해설 (${minY}~${maxY})</h1>
<p class="lead">문제지 ${papers.length}개 · ${total.toLocaleString()}문항 · 문항마다 AI 해설</p>
<div class="cta"><a class="btn" href="/#/x/${exam.id}">실전 모의고사 풀기</a><a class="btn ghost" href="/#/x/${exam.id}">랜덤 모의고사 만들기</a></div>
<section class="card"><h2>과목별 기출문제 모음</h2><div class="chips">${subjLinks.join("")}</div></section>
${hubSections}`,
    }),
  );
  pages++;
  urls.push({ loc: `${SITE}/${base}/`, pri: "0.9", freq: "weekly" });
  urls.push(
    ...papers.map((p) => ({
      loc: `${SITE}/${base}/${p.slug}/`,
      pri: p.year >= maxY - 2 ? "0.8" : "0.6",
      freq: "monthly",
    })),
  );
  recentLinks.push(
    ...papers
      .filter((p) => p.year >= maxY - 1)
      .map((p) => `<li><a href="/${base}/${p.slug}/">${esc(p.title)}</a></li>`),
  );
  examSummaries.push({ exam, base, papers: papers.length, total, minY, maxY, subjects: subjOrder.slice(0, 8) });
  rssItems.push(...papers.filter((p) => p.year >= maxY - 1).map((p) => ({ title: p.title, link: `${SITE}/${base}/${p.slug}/`, desc: `${p.title} — 공식 정답과 문항별 해설, 실제 시험처럼 풀기` })));
  return { papers: papers.length, total, minY, maxY };
}

const totals = { papers: 0, total: 0, minY: 9999, maxY: 0 };
for (const exam of CATALOG.exams) {
  const list = index.filter((p) => (p.exam ?? "psat") === exam.id);
  if (!list.length) continue;
  const t = buildExam(exam, list);
  totals.papers += t.papers;
  totals.total += t.total;
  totals.minY = Math.min(totals.minY, t.minY);
  totals.maxY = Math.max(totals.maxY, t.maxY);
}

// sitemap
fs.writeFileSync(
  path.join(DIST, "sitemap.xml"),
  `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
${urls.map((u) => `  <url><loc>${u.loc}</loc><lastmod>${TODAY}</lastmod><changefreq>${u.freq}</changefreq><priority>${u.pri}</priority></url>`).join("\n")}
</urlset>
`,
);

// 홈 index.html 의 정적 대체 내용(#root 안)에 최근 기출 링크를 채운다 — JS 를 실행하지 않는 수집기도 링크를 따라가게
const cats = [...new Set(examSummaries.map((x) => x.exam.category))];
const examsHtml = cats
  .map(
    (c) =>
      `<h2>${esc(c)} 기출문제</h2><ul>` +
      examSummaries
        .filter((x) => x.exam.category === c)
        .map(
          (x) =>
            `<li><a href="/${x.base}/">${esc(x.exam.name)} 기출문제 정답·해설 (${x.minY}~${x.maxY}, ${x.total.toLocaleString()}문항)</a> — ${esc(x.subjects.join("·"))}</li>`,
        )
        .join("") +
      "</ul>",
  )
  .join("");
// RSS (네이버 서치어드바이저 제출용): 최근 연도 문제지 페이지
const rss = `<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
<title>올테스트 기출문제 정답·해설</title>
<link>${SITE}/</link>
<description>공무원·자격증 기출문제를 실제 시험처럼 풀고 문항별 해설로 복습하는 무료 모의고사</description>
<language>ko</language>
<lastBuildDate>${new Date().toUTCString()}</lastBuildDate>
${rssItems
  .slice(0, 300)
  .map((it) => `<item><title>${esc(it.title)}</title><link>${it.link}</link><guid>${it.link}</guid><description>${esc(it.desc)}</description></item>`)
  .join("\n")}
</channel></rss>
`;
fs.writeFileSync(path.join(DIST, "rss.xml"), rss);

const homePath = path.join(DIST, "index.html");
const home = fs.readFileSync(homePath, "utf8");
fs.writeFileSync(
  homePath,
  home
    .replace("<!--SEO_EXAMS-->", examsHtml)
    .replace(/__EXAMS__/g, String(examSummaries.length))
    .replace("<!--SEO_RECENT-->", recentLinks.slice(0, 80).join(""))
    .replace(/__TOTAL__/g, totals.total.toLocaleString())
    .replace(/__PAPERS__/g, String(totals.papers))
    .replace(/__RANGE__/g, `${totals.minY}~${totals.maxY}`),
);

console.log(`seo: ${pages} pages, sitemap ${urls.length} urls`);
