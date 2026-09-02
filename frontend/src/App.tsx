import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { LangProvider } from "./i18n/LangContext";
import { AuthProvider } from "./auth/AuthContext";
import InviteScreen from "./apps/worker/screens/Invite";
import AskScreen from "./apps/worker/screens/Ask";
import ReportScreen from "./apps/worker/screens/Report";
import QuizScreen from "./apps/worker/screens/Quiz";
import WorkerLayout from "./apps/worker/WorkerLayout";
import AdminReportsScreen from "./apps/admin/screens/Reports";
import AdminDashboardScreen from "./apps/admin/screens/Dashboard";
import AdminGlossaryScreen from "./apps/admin/screens/Glossary";
import AdminAuditLogScreen from "./apps/admin/screens/AuditLog";
import AdminUnansweredScreen from "./apps/admin/screens/Unanswered";
import AdminWorkersScreen from "./apps/admin/screens/Workers";
import AdminDocumentsScreen from "./apps/admin/screens/Documents";
import AdminLayout from "./apps/admin/AdminLayout";

export default function App() {
  return (
    <AuthProvider>
      <LangProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/" element={<Navigate to="/activate" replace />} />
            <Route path="/activate" element={<InviteScreen />} />
            <Route element={<WorkerLayout />}>
              <Route path="/ask" element={<AskScreen />} />
              <Route path="/report" element={<ReportScreen />} />
              <Route path="/quiz" element={<QuizScreen />} />
            </Route>
            <Route path="/admin" element={<AdminLayout />}>
              <Route path="reports" element={<AdminReportsScreen />} />
              <Route path="dashboard" element={<AdminDashboardScreen />} />
              <Route path="glossary" element={<AdminGlossaryScreen />} />
              <Route path="events" element={<AdminAuditLogScreen />} />
              <Route path="unanswered" element={<AdminUnansweredScreen />} />
              <Route path="workers" element={<AdminWorkersScreen />} />
              <Route path="documents" element={<AdminDocumentsScreen />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </LangProvider>
    </AuthProvider>
  );
}
