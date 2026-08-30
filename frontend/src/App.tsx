import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { LangProvider } from "./i18n/LangContext";
import InviteScreen from "./apps/worker/screens/Invite";
import AskScreen from "./apps/worker/screens/Ask";
import AdminReportsScreen from "./apps/admin/screens/Reports";
import AdminDashboardScreen from "./apps/admin/screens/Dashboard";
import AdminGlossaryScreen from "./apps/admin/screens/Glossary";

export default function App() {
  return (
    <LangProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Navigate to="/activate" replace />} />
          <Route path="/activate" element={<InviteScreen />} />
          <Route path="/ask" element={<AskScreen />} />
          <Route path="/admin/reports" element={<AdminReportsScreen />} />
          <Route path="/admin/dashboard" element={<AdminDashboardScreen />} />
          <Route path="/admin/glossary" element={<AdminGlossaryScreen />} />
        </Routes>
      </BrowserRouter>
    </LangProvider>
  );
}
