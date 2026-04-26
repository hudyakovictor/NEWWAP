import TopBar from "./components/TopBar";
import TimelineView from "./components/timeline/TimelineView";
import PhotosPage from "./pages/PhotosPage";
import PairAnalysisPage from "./pages/PairAnalysisPage";
import CalibrationPage from "./pages/CalibrationPage";
import JobsPage from "./pages/JobsPage";
import ReportsPage from "./pages/ReportsPage";
import SettingsPage from "./pages/SettingsPage";
import InvestigationsPage from "./pages/InvestigationsPage";
import AnomaliesPage from "./pages/AnomaliesPage";
import EvidencePage from "./pages/EvidencePage";
import MatrixPage from "./pages/MatrixPage";
import AgeingPage from "./pages/AgeingPage";
import CachePage from "./pages/CachePage";
import PipelinePage from "./pages/PipelinePage";
import ApiExplorerPage from "./pages/ApiExplorerPage";
import ReportBuilderPage from "./pages/ReportBuilderPage";
import LogsPage from "./pages/LogsPage";
import GroundTruthPage from "./pages/GroundTruthPage";
import AuditPage from "./pages/AuditPage";
import SignalsPage from "./pages/SignalsPage";
import ProgressPage from "./pages/ProgressPage";
import ClustersPage from "./pages/ClustersPage";
import IterationsPage from "./pages/IterationsPage";
import DiaryPage from "./pages/DiaryPage";
import CommandPalette from "./components/common/CommandPalette";
import { useApp } from "./store/appStore";
import "./App.css";

export default function App() {
  const { page, setPage } = useApp();

  return (
    <div className="h-screen w-screen flex flex-col bg-bg text-white/90 overflow-hidden">
      <TopBar current={page} onNav={setPage} />
      {page === "timeline" && <TimelineView />}
      {page === "photos" && <PhotosPage />}
      {page === "pairs" && <PairAnalysisPage />}
      {page === "matrix" && <MatrixPage />}
      {page === "evidence" && <EvidencePage />}
      {page === "ageing" && <AgeingPage />}
      {page === "anomalies" && <AnomaliesPage />}
      {page === "investigations" && <InvestigationsPage />}
      {page === "calibration" && <CalibrationPage />}
      {page === "pipeline" && <PipelinePage />}
      {page === "cache" && <CachePage />}
      {page === "jobs" && <JobsPage />}
      {page === "reports" && <ReportsPage />}
      {page === "report_builder" && <ReportBuilderPage />}
      {page === "api" && <ApiExplorerPage />}
      {page === "logs" && <LogsPage />}
      {page === "ground_truth" && <GroundTruthPage />}
      {page === "audit" && <AuditPage />}
      {page === "signals" && <SignalsPage />}
      {page === "progress" && <ProgressPage />}
      {page === "clusters" && <ClustersPage />}
      {page === "iterations" && <IterationsPage />}
      {page === "diary" && <DiaryPage />}
      {page === "settings" && <SettingsPage />}
      <CommandPalette />
    </div>
  );
}
