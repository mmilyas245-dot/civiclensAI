// Shared helpers for the CivicLens admin pages.
//
// The login token is created and verified by the Flask backend.
// It is kept in sessionStorage (cleared when the tab is closed) and sent
// as "Authorization: Bearer <token>" on every admin request.

export const API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:5000"
).replace(/\/+$/, "");

const TOKEN_KEY = "civiclens_admin_token";

export function getToken(): string | null {
  try {
    return sessionStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function saveToken(token: string) {
  try {
    sessionStorage.setItem(TOKEN_KEY, token);
  } catch {
    /* storage blocked - login will not persist */
  }
}

export function clearToken() {
  try {
    sessionStorage.removeItem(TOKEN_KEY);
  } catch {
    /* ignore */
  }
}

export async function adminFetch(
  path: string,
  init: RequestInit = {}
): Promise<Response> {
  const headers = new Headers(init.headers);
  const token = getToken();

  if (token) headers.set("Authorization", `Bearer ${token}`);

  return fetch(`${API_BASE_URL}${path}`, { ...init, headers });
}

export type AdminStatus = "Pending" | "In Progress" | "Resolved";

export const STATUSES: AdminStatus[] = ["Pending", "In Progress", "Resolved"];

export type AdminReport = {
  report_id: number;
  problem: string;
  category: string;
  severity: "Low" | "Medium" | "High" | "Critical";
  priority_score: number;
  responsible_department: string;
  description: string;
  risk: string;
  recommended_action: string;
  location: {
    latitude: number;
    longitude: number;
    address?: string | null;
  };
  address?: string | null;
  status: AdminStatus;
  created_at: string;
  resolved_at?: string;
  report_count?: number;
  photo_count: number;
  additional_information?: string;
  status_history?: {
    status: string;
    at: string;
    note?: string;
    by?: string;
  }[];
};

export function formatId(id: number) {
  return `CL-${String(id).padStart(4, "0")}`;
}

export function shortAddress(report: AdminReport) {
  const address = report.address || report.location?.address;

  if (address) return address.split(",").slice(0, 3).join(",").trim();

  const { latitude, longitude } = report.location || {};

  return typeof latitude === "number" && typeof longitude === "number"
    ? `${latitude.toFixed(4)}, ${longitude.toFixed(4)}`
    : "Location unknown";
}

export function timeAgo(iso: string) {
  const seconds = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);

  if (seconds < 60) return "just now";
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  if (seconds < 86400 * 7) return `${Math.floor(seconds / 86400)}d ago`;

  return new Date(iso).toLocaleDateString();
}

export function fullDate(iso: string) {
  return new Date(iso).toLocaleString();
}
