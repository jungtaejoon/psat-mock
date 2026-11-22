import { useRoute } from "./router";
import Hub from "./pages/Hub";
import ExamHome from "./pages/Home";
import Exam from "./pages/Exam";
import Result from "./pages/Result";
import StartPaper from "./StartPaper";
import { getExam } from "./exams";
import { SiteFooter, SiteHeader } from "./SiteChrome";

export default function App() {
  const [page, id, arg] = useRoute();
  const exam = page === "x" && id ? getExam(id) : undefined;
  const chrome = page !== "exam" && page !== "start";
  return (
    <>
      {chrome && <SiteHeader />}
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
      {chrome && <SiteFooter source={exam?.source} />}
    </>
  );
}
