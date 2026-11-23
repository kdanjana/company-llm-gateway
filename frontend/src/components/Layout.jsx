import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../auth.jsx";

export default function Layout() {
  const { me, logout } = useAuth();
  const isAdmin = me.role === "admin";
  const who = isAdmin ? "Admin" : `Department head · ${me.department?.name ?? ""}`;

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">LLM Gateway</div>
        <nav className="nav">
          <NavLink to="/" end>
            Overview
          </NavLink>
          <NavLink to="/requests">Requests</NavLink>
          <NavLink to="/api-keys">API keys</NavLink>
          {isAdmin && <NavLink to="/settings">Settings</NavLink>}
        </nav>
        <div className="user">
          <span className="user-name">{me.username}</span>
          <span className="muted">{who}</span>
          <button type="button" className="button ghost" onClick={logout}>
            Log out
          </button>
        </div>
      </header>
      <main className="content">
        <Outlet />
      </main>
    </div>
  );
}
