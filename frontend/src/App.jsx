import { Navigate, Route, Routes } from "react-router-dom";
import { RequireAuth } from "./auth.jsx";
import Layout from "./components/Layout.jsx";
import ApiKeysPage from "./pages/ApiKeysPage.jsx";
import LoginPage from "./pages/LoginPage.jsx";
import OverviewPage from "./pages/OverviewPage.jsx";
import RequestsPage from "./pages/RequestsPage.jsx";
import SettingsPage from "./pages/SettingsPage.jsx";

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        element={
          <RequireAuth>
            <Layout />
          </RequireAuth>
        }
      >
        <Route index element={<OverviewPage />} />
        <Route path="requests" element={<RequestsPage />} />
        <Route path="api-keys" element={<ApiKeysPage />} />
        <Route
          path="settings"
          element={
            <RequireAuth adminOnly>
              <SettingsPage />
            </RequireAuth>
          }
        />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
