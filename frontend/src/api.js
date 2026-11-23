// All calls to the Django dashboard API.
//
// JWT tokens are kept in localStorage:
// - access: sent as "Authorization: Bearer <access>" on every call (expires after ~15 min)
// - refresh: only used to get a new access token (POST /api/auth/refresh/); each refresh returns a new one

export class ApiError extends Error {
  constructor(status, message, details) {
    super(message);
    this.status = status;
    this.details = details;
  }
}

const ACCESS_KEY = "gw_access_token";
const REFRESH_KEY = "gw_refresh_token";

function readToken(key) {
  try {
    return localStorage.getItem(key) ?? "";
  } catch {
    return ""; // storage blocked (e.g. some private windows): behave as logged out
  }
}

function saveTokens(access, refresh) {
  try {
    localStorage.setItem(ACCESS_KEY, access);
    localStorage.setItem(REFRESH_KEY, refresh);
  } catch {
    /* storage blocked: the login only lasts until the page is reloaded */
  }
}

export function clearTokens() {
  try {
    localStorage.removeItem(ACCESS_KEY);
    localStorage.removeItem(REFRESH_KEY);
  } catch {
    /* nothing stored */
  }
}

export function hasTokens() {
  return readToken(REFRESH_KEY) !== "";
}

// Called when the tokens cannot be refreshed any more (refresh token expired or logged out).
let onSignedOut = () => {};
export function setSignedOutHandler(handler) {
  onSignedOut = handler;
}

// One refresh at a time: requests that get a 401 at the same moment share the same refresh call
// (the refresh token rotates, so two parallel refreshes would make the second one fail).
let refreshing = null;

function refreshTokens() {
  if (!refreshing) {
    refreshing = (async () => {
      const refresh = readToken(REFRESH_KEY);
      if (!refresh) return false;
      try {
        const res = await fetch("/api/auth/refresh/", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ refresh }),
        });
        if (!res.ok) return false;
        const data = await res.json();
        saveTokens(data.access, data.refresh ?? refresh);
        return true;
      } catch {
        return false;
      }
    })().finally(() => {
      refreshing = null;
    });
  }
  return refreshing;
}

/** fetch with the access token. On 401 (access token expired): refresh once and retry. */
async function authFetch(url, init = {}) {
  const send = () => {
    const headers = { "Content-Type": "application/json" };
    const access = readToken(ACCESS_KEY);
    if (access) headers.Authorization = `Bearer ${access}`;
    return fetch(url, { ...init, headers });
  };
  let res = await send();
  if (res.status === 401 && hasTokens()) {
    if (await refreshTokens()) {
      res = await send();
    } else {
      clearTokens();
      onSignedOut();
    }
  }
  return res;
}

/** Turns the backend's {"error": {"message", "details"}} into a readable message. */
function errorMessage(data, status) {
  const error = data?.error;
  if (!error) return `Request failed (${status})`;
  if (error.details && typeof error.details === "object") {
    const parts = Object.entries(error.details).map(([field, problems]) => `${field}: ${[].concat(problems).join(" ")}`);
    if (parts.length) return parts.join(" · ");
  }
  return error.message || `Request failed (${status})`;
}

async function request(url, { method = "GET", body } = {}) {
  const res = await authFetch(url, { method, body: body === undefined ? undefined : JSON.stringify(body) });
  if (res.status === 204) return null;
  const data = await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(res.status, errorMessage(data, res.status), data?.error?.details);
  return data;
}

/** {month: "2026-11", department: ""} -> "?month=2026-11" (empty values left out) */
function query(params) {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") search.set(key, value);
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}

export const api = {
  async login(username, password) {
    const res = await fetch("/api/auth/login/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    const data = await res.json().catch(() => null);
    if (!res.ok) throw new ApiError(res.status, data?.error?.message || "Login failed");
    saveTokens(data.access, data.refresh);
    return api.me();
  },

  async logout() {
    const refresh = readToken(REFRESH_KEY);
    clearTokens();
    try {
      await fetch("/api/auth/logout/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh }),
      });
    } catch {
      /* logged out locally either way */
    }
  },

  me: () => request("/api/auth/me/"),

  // statistics
  summary: (month) => request(`/api/dashboard/summary/${query({ month })}`),
  daily: (month, department) => request(`/api/dashboard/daily/${query({ month, department })}`),
  modelsUsage: (month, department) => request(`/api/dashboard/models-usage/${query({ month, department })}`),
  alerts: (month) => request(`/api/dashboard/alerts/${query({ month })}`),
  requests: (params) => request(`/api/dashboard/requests/${query(params)}`),

  // departments (create / change: admin only)
  departments: () => request("/api/dashboard/departments/"),
  createDepartment: (body) => request("/api/dashboard/departments/", { method: "POST", body }),
  updateDepartment: (id, body) => request(`/api/dashboard/departments/${id}/`, { method: "PATCH", body }),

  // API keys
  apiKeys: (department) => request(`/api/dashboard/api-keys/${query({ department })}`),
  createApiKey: (department, name) => request("/api/dashboard/api-keys/", { method: "POST", body: { department, name } }),
  revokeApiKey: (id) => request(`/api/dashboard/api-keys/${id}/revoke/`, { method: "POST" }),

  // models and prices (create / change: admin only)
  models: () => request("/api/dashboard/models/"),
  createModel: (body) => request("/api/dashboard/models/", { method: "POST", body }),
  updateModel: (id, body) => request(`/api/dashboard/models/${id}/`, { method: "PATCH", body }),
};
