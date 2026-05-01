import TopBar from "./components/TopBar";
import TimelineView from "./components/timeline/TimelineView";
import PhotosPage from "./pages/PhotosPage";
import PairAnalysisPage from "./pages/PairAnalysisPage";
import ComparisonPage from "./pages/ComparisonPage";
import CalibrationPage from "./pages/CalibrationPage";
import JobsPage from "./pages/JobsPage";
import ReportBuilderPage from "./pages/ReportBuilderPage";
import SettingsPage from "./pages/SettingsPage";
import InvestigationsPage from "./pages/InvestigationsPage";
import AnomaliesPage from "./pages/AnomaliesPage";
import MatrixPage from "./pages/MatrixPage";
import AgeingPage from "./pages/AgeingPage";
import PipelinePage from "./pages/PipelinePage";
import LogsPage from "./pages/LogsPage";
import AuditPage from "./pages/AuditPage";
import SignalsPage from "./pages/SignalsPage";
import ProgressPage from "./pages/ProgressPage";
import ClustersPage from "./pages/ClustersPage";
import IterationsPage from "./pages/IterationsPage";
import DiaryPage from "./pages/DiaryPage";
import EvidenceMapPage from "./pages/EvidenceMapPage";
import UploadPage from "./pages/UploadPage";
import CommandPalette from "./components/common/CommandPalette";
import { useApp } from "./store/appStore";
import "./App.css";

export default function App() {
  const { page, setPage } = useApp();

  return (
    <div className="h-screen w-screen flex flex-col bg-bg text-white/90 overflow-hidden">
      <TopBar current={page} onNav={setPage} />
      <div className="flex-1 flex items-center justify-center">
        <div>Страница: {page}</div>
      </div>
      {page === "timeline" && <TimelineView />}
      {page === "photos" && <PhotosPage />}
      {page === "upload" && <UploadPage />}
      {page === "pairs" && <PairAnalysisPage />}
      {page === "comparison" && <ComparisonPage />}
      {page === "matrix" && <MatrixPage />}
      {page === "ageing" && <AgeingPage />}
      {page === "anomalies" && <AnomaliesPage />}
      {page === "iterations" && <IterationsPage />}
      {page === "calibration" && <CalibrationPage />}
      {page === "pipeline" && <PipelinePage />}
      {page === "jobs" && <JobsPage />}
      {page === "investigations" && <InvestigationsPage />}
      {page === "diary" && <DiaryPage />}
      {page === "report_builder" && <ReportBuilderPage />}
      {page === "settings" && <SettingsPage />}
      {page === "signals" && <SignalsPage />}
      {page === "progress" && <ProgressPage />}
      {page === "clusters" && <ClustersPage />}
      {page === "audit" && <AuditPage />}
      {page === "logs" && <LogsPage />}
      {page === "evidence_map" && <EvidenceMapPage />}
      <CommandPalette />
    </div>
  );
}
