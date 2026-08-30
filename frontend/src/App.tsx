import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { LangProvider } from "./i18n/LangContext";
import InviteScreen from "./apps/worker/screens/Invite";
import AskScreen from "./apps/worker/screens/Ask";
import AdminReportsScreen from "./apps/admin/screens/Reports";
import AdminDashboardScreen from "./apps/admin/screens/Dashboard";
import AdminGlossaryScreen from "./apps/admin/screens/Glossary";
import AdminAuditLogScreen from "./apps/admin/screens/AuditLog";
import AdminLayout from "./apps/admin/AdminLayout";

export default function App() {
  return (
    <LangProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Navigate to="/activate" replace />} />
          <Route path="/activate" element={<InviteScreen />} />
          <Route path="/ask" element={<AskScreen />} />
          <Route path="/admin" element={<AdminLayout />}>
            <Route path="reports" element={<AdminReportsScreen />} />
            <Route path="dashboard" element={<AdminDashboardScreen />} />
            <Route path="glossary" element={<AdminGlossaryScreen />} />
            <Route path="events" element={<AdminAuditLogScreen />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </LangProvider>
  );
}
