import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { LangProvider } from "./i18n/LangContext";
import InviteScreen from "./apps/worker/screens/Invite";
import AskScreen from "./apps/worker/screens/Ask";
import AdminReportsScreen from "./apps/admin/screens/Reports";

export default function App() {
  return (
    <LangProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Navigate to="/activate" replace />} />
          <Route path="/activate" element={<InviteScreen />} />
          <Route path="/ask" element={<AskScreen />} />
          <Route path="/admin/reports" element={<AdminReportsScreen />} />
        </Routes>
      </BrowserRouter>
    </LangProvider>
  );
}
