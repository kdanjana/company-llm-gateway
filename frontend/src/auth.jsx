import { createContext, useContext, useEffect, useState } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { api, clearTokens, hasTokens, setSignedOutHandler } from "./api.js";

// me: null = still checking, {authenticated: false}, or {authenticated: true, username, role, department}
const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [me, setMe] = useState(null);

  useEffect(() => {
    // If the tokens can no longer be refreshed while the app is open, go back to the login page.
    setSignedOutHandler(() => setMe({ authenticated: false }));

    // Page (re)loaded: tokens saved from an earlier login? Ask who they belong to.
    if (!hasTokens()) {
      setMe({ authenticated: false });
      return;
    }
    api
      .me()
      .then((data) => setMe({ ...data, authenticated: true }))
      .catch(() => {
        clearTokens();
        setMe({ authenticated: false });
      });
  }, []);

  async function login(username, password) {
    const data = await api.login(username, password);
    setMe({ ...data, authenticated: true });
  }

  async function logout() {
    await api.logout();
    setMe({ authenticated: false });
  }

  return <AuthContext.Provider value={{ me, login, logout }}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const state = useContext(AuthContext);
  if (!state) throw new Error("useAuth must be used inside <AuthProvider>");
  return state;
}

/** Shows children only to logged-in users (and only to admins with adminOnly). */
export function RequireAuth({ children, adminOnly = false }) {
  const { me } = useAuth();
  const location = useLocation();
  if (me === null) return <p className="page-message">Loading…</p>;
  if (!me.authenticated) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  if (adminOnly && me.role !== "admin") return <Navigate to="/" replace />;
  return children;
}
