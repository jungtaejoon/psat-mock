import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";
import App from "./App";

// 구글·카카오 로그인에서 돌아오면(?code=…) 세션을 만들고 원래 화면으로 (수험생 이야기)
if (/[?&](code|error)=/.test(location.search)) import("./talk/api").then((m) => m.finishLoginIfNeeded());

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
