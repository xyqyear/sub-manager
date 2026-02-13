import axios from "axios";

const TOKEN_KEY = "sub_manager_admin_token";

export function getAdminToken(): string {
  return localStorage.getItem(TOKEN_KEY) ?? "";
}

export function setAdminToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearAdminToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

const api = axios.create({
  baseURL: "/api",
  timeout: 10_000,
});

api.interceptors.request.use((config) => {
  const token = getAdminToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

export function errorDetail(error: unknown): string {
  const response = (error as { response?: { data?: { detail?: unknown } } })
    ?.response;
  const detail = response?.data?.detail;
  if (typeof detail === "string" && detail.trim()) {
    return detail;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return String(error);
}

export default api;
