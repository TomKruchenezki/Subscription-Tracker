import type { Subscription, EmailRecord, ScanRequest, ScanResult, Summary, ConnectedAccount, ScanJobStatus, PaymentEvent, CreateSubscriptionRequest, UpdateSubscriptionRequest } from "@/types/api";

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
  scan: (request?: ScanRequest) => {
    const params = new URLSearchParams();
    if (request?.mode) params.set("mode", request.mode);
    if (request?.scan_range) params.set("scan_range", request.scan_range);
    if (request?.date_from) params.set("date_from", request.date_from);
    if (request?.date_to) params.set("date_to", request.date_to);
    const qs = params.toString();
    return apiFetch<ScanResult>(`/api/scan${qs ? `?${qs}` : ""}`, { method: "POST" });
  },
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

  accounts: () => apiFetch<ConnectedAccount[]>("/api/accounts"),
  gmailAuthUrl: () =>
    apiFetch<{ auth_url: string; state: string }>("/api/accounts/gmail/auth-url"),
  disconnectAccount: (accountId: string) =>
    fetch(`${BASE}/api/accounts/${encodeURIComponent(accountId)}`, { method: "DELETE" }),

  scanStart: (request?: ScanRequest) => {
    const params = new URLSearchParams();
    if (request?.mode) params.set("mode", request.mode);
    if (request?.scan_range) params.set("scan_range", request.scan_range);
    if (request?.date_from) params.set("date_from", request.date_from);
    if (request?.date_to) params.set("date_to", request.date_to);
    const qs = params.toString();
    return apiFetch<ScanJobStatus>(`/api/scan/start${qs ? `?${qs}` : ""}`, { method: "POST" });
  },
  scanStatus: (scanId: string) =>
    apiFetch<ScanJobStatus>(`/api/scan/status/${encodeURIComponent(scanId)}`),

  paymentEvents: (params?: {
    event_type?: string;
    is_recurring_candidate?: number;
    is_one_time_candidate?: number;
    limit?: number;
  }) => {
    const p = new URLSearchParams();
    if (params?.event_type) p.set("event_type", params.event_type);
    if (params?.is_recurring_candidate != null) p.set("is_recurring_candidate", String(params.is_recurring_candidate));
    if (params?.is_one_time_candidate != null) p.set("is_one_time_candidate", String(params.is_one_time_candidate));
    if (params?.limit != null) p.set("limit", String(params.limit));
    const qs = p.toString();
    return apiFetch<PaymentEvent[]>(`/api/payment-events${qs ? `?${qs}` : ""}`);
  },

  // Phase 3.4: Manual CRUD for subscriptions
  createSubscription: (req: CreateSubscriptionRequest) =>
    apiFetch<Subscription>("/api/subscriptions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req),
    }),
  updateSubscription: (id: string, req: UpdateSubscriptionRequest) =>
    apiFetch<Subscription>(`/api/subscriptions/${encodeURIComponent(id)}/update`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req),
    }),
  deleteSubscription: (id: string) =>
    fetch(`${BASE}/api/subscriptions/${encodeURIComponent(id)}`, { method: "DELETE" }),

  // Phase 3.4: Payment event link/unlink
  linkPaymentEvent: (eventId: string, subscriptionId: string) =>
    apiFetch<{ event_id: string; subscription_id: string }>(
      `/api/payment-events/${encodeURIComponent(eventId)}/link`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ subscription_id: subscriptionId }),
      }
    ),
  unlinkPaymentEvent: (eventId: string) =>
    apiFetch<{ event_id: string; subscription_id: null }>(
      `/api/payment-events/${encodeURIComponent(eventId)}/unlink`,
      { method: "POST" }
    ),
};
