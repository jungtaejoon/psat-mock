import { useRoute } from "./router";
import Home from "./pages/Home";
import Exam from "./pages/Exam";
import Result from "./pages/Result";
import StartPaper from "./StartPaper";

/** 게시 중단 요청 연락처(이메일 또는 URL). 빌드 시 VITE_CONTACT 로 지정 */
const CONTACT = import.meta.env.VITE_CONTACT as string | undefined;

export default function App() {
  const [page, id, arg] = useRoute();
  return (
    <>
      {page === "start" && id ? (
        <StartPaper
          key={id + arg}
          paperId={decodeURIComponent(id)}
          mode={arg === "practice" ? "practice" : "exam"}
        />
      ) : page === "exam" && id ? (
        <Exam key={id} id={id} />
      ) : page === "result" && id ? (
        <Result key={id} id={id} />
      ) : (
        <Home />
      )}
      {page !== "exam" && (
        <footer className="footer">
          <a href="/psat/">PSAT 기출문제 정답·해설 전체 목록</a>
          <br />
          문제·정답 출처: 인사혁신처 국가공무원 채용시스템(gongmuwon.gosi.kr).
          해설은 AI가 작성했으며 오류가 있을 수 있습니다.
          {CONTACT && (
            <>
              <br />
              저작권 관련 문의나 게시 중단 요청은{" "}
              <a href={CONTACT.includes("@") ? `mailto:${CONTACT}` : CONTACT}>
                여기
              </a>
              로 보내 주세요.
            </>
          )}
        </footer>
      )}
    </>
  );
}
