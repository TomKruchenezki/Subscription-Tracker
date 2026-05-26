import type { Subscription, EmailRecord, ScanResult, Summary } from "@/types/api";

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, options);
  if (!res.ok) {
    throw new Error(`API error ${res.status}: ${await res.text()}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => apiFetch<{ status: string; mode: string; version: string }>("/api/health"),
  scan: () => apiFetch<ScanResult>("/api/scan", { method: "POST" }),
  subscriptions: (status?: string) =>
    apiFetch<Subscription[]>(`/api/subscriptions${status ? `?status=${status}` : ""}`),
  subscription: (id: string) =>
    apiFetch<{ subscription: Subscription; email_records: EmailRecord[] }>(
      `/api/subscriptions/${id}`
    ),
  emailRecords: (disposition?: string) =>
    apiFetch<EmailRecord[]>(
      `/api/email-records${disposition ? `?disposition=${disposition}` : ""}`
    ),
  summary: () => apiFetch<Summary>("/api/summary"),
};
