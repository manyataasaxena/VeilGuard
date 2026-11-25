export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8001";

export interface UserInfo {
  id: string;
  full_name: string;
  email: string;
  role: string;
  org_id: string;
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("vg_token");
}

export function getSavedUser(): UserInfo | null {
  if (typeof window === "undefined") return null;
  const raw = localStorage.getItem("vg_user");
  return raw ? JSON.parse(raw) : null;
}

export function saveSession(token: string, user: UserInfo) {
  localStorage.setItem("vg_token", token);
  localStorage.setItem("vg_user", JSON.stringify(user));
}

export function clearSession() {
  localStorage.removeItem("vg_token");
  localStorage.removeItem("vg_user");
}

export async function loginWithDemo(email: string, password: string = "demo1234") {
  await fetch(`${API_BASE}/auth/demo-seed`, { method: "POST" });

  const res = await fetch(`${API_BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Login failed");
  }
  const data = await res.json();
  saveSession(data.access_token, data.user);
  return data;
}