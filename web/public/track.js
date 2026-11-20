/* 방문 수 세기: 어떤 화면을 봤는지, 처음에 어디서 왔는지만 Slop 서버에 세요.
   IP·쿠키·풀이 기록 같은 방문자 정보는 보내지 않아요. 검색 로봇은 세지 않아요. */
(function () {
  if (navigator.webdriver || /bot|crawl|spider|slurp|headless|preview|lighthouse/i.test(navigator.userAgent)) return;
  var S = [[/(^|\.)google\./, "google"], [/(^|\.)naver\.(com|me)$/, "naver"], [/(^|\.)daum\.net$|(^|\.)kakao\.com$/, "daum-kakao"],
    [/(^|\.)bing\.com$/, "bing"], [/(^|\.)duckduckgo\.com$/, "duckduckgo"], [/(^|\.)yahoo\./, "yahoo"], [/^t\.co$|(^|\.)x\.com$|(^|\.)twitter\.com$/, "x"],
    [/(^|\.)facebook\.com$/, "facebook"], [/(^|\.)instagram\.com$/, "instagram"], [/(^|\.)threads\.(net|com)$/, "threads"], [/(^|\.)youtube\.com$/, "youtube"],
    [/(^|\.)reddit\.com$/, "reddit"], [/(^|\.)chatgpt\.com$|(^|\.)openai\.com$/, "chatgpt"], [/(^|\.)perplexity\.ai$/, "perplexity"],
    [/(^|\.)claude\.ai$/, "claude"], [/^slop\.ai\.kr$/, "slop"], [/^jungtaejoon\.github\.io$/, "slop-log"], [/(^|\.)dcinside\.com$/, "dcinside"]];
  function source() {
    var m = /[?&]utm_source=([^&#]+)/.exec(location.search);
    if (m) return ("utm:" + decodeURIComponent(m[1]).toLowerCase().replace(/[^a-z0-9._-]/g, "")).slice(0, 60);
    var r = document.referrer; if (!r) return "direct";
    var u; try { u = new URL(r); } catch (e) { return "direct"; }
    var h = u.hostname.toLowerCase().replace(/^(www|m|mobile)\./, "");
    if (h === location.hostname.replace(/^www\./, "")) return null;
    for (var i = 0; i < S.length; i++) if (S[i][0].test(h)) return S[i][1];
    return h.replace(/[^a-z0-9.-]/g, "").slice(0, 60) || "direct";
  }
  // 화면 이름: 홈, 시험 홈(#/x/시험), 풀기 시작(#/start/exam|practice), 푸는 중(#/exam), 결과(#/result), 검색용 정적 페이지(/psat/...)
  function key() {
    var p = location.pathname;
    if (p !== "/" && p !== "/index.html") return p;
    var h = location.hash.replace(/^#\/?/, "").split("/").filter(Boolean);
    if (!h.length) return "/";
    if (h[0] === "x" && h[1]) return "/#/x/" + h[1];
    if (h[0] === "start") return "/#/start/" + (h[2] === "practice" ? "practice" : "exam");
    if (h[0] === "exam" || h[0] === "result") return "/#/" + h[0];
    return "/#/other";
  }
  var src = null, first = false, last = "";
  try { src = sessionStorage.getItem("at-src"); } catch (e) {}
  if (!src) { src = source() || "direct"; first = true; try { sessionStorage.setItem("at-src", src); } catch (e) {} }
  function send() {
    var k = encodeURI(key()).replace(/[^A-Za-z0-9\/_.%~#-]/g, "").slice(0, 120);
    if (k === last) return; last = k;
    fetch("https://sbeickdtzkxxovlnnumo.supabase.co/rest/v1/rpc/track_site", { method: "POST", keepalive: true,
      headers: { "Content-Type": "application/json", apikey: "sb_publishable_y_GuNh3abdFpwTgZ0hvzFg_jww2I5w1", Authorization: "Bearer sb_publishable_y_GuNh3abdFpwTgZ0hvzFg_jww2I5w1" },
      body: JSON.stringify({ p_site: "alltests", p_path: k, p_source: src, p_first: first }) }).catch(function () {});
    first = false;
  }
  send();
  window.addEventListener("hashchange", send);
})();
