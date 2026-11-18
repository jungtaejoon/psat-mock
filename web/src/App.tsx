import { useRoute } from "./router";
import Hub from "./pages/Hub";
import ExamHome from "./pages/Home";
import Exam from "./pages/Exam";
import Result from "./pages/Result";
import StartPaper from "./StartPaper";
import { getExam } from "./exams";

/** 게시 중단 요청 연락처(이메일 또는 URL). 빌드 시 VITE_CONTACT 로 지정 */
const CONTACT = import.meta.env.VITE_CONTACT as string | undefined;

export default function App() {
  const [page, id, arg] = useRoute();
  const exam = page === "x" && id ? getExam(id) : undefined;
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
      ) : exam ? (
        <ExamHome key={exam.id} exam={exam} />
      ) : (
        <Hub />
      )}
      {page !== "exam" && (
        <footer className="footer">
          <a href="/psat/">PSAT 기출문제 정답·해설 전체 목록</a>
          <br />
          문제·정답 출처:{" "}
          {exam
            ? exam.source
            : "각 시험 시행 기관(인사혁신처, 한국산업인력공단 등). 시험별 출처는 각 시험 화면에 표시합니다"}
          . 해설은 AI가 작성했으며 공식 해설이 아니고 오류가 있을 수 있습니다.
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
