"use client";
import { useState } from "react";
import type { EmailRecord, CreateSubscriptionRequest } from "@/types/api";
import { formatCurrency } from "@/lib/format";
import { api } from "@/lib/api";

interface Props {
  records: EmailRecord[];
  onRefresh: () => void;
}

// ─── Category definitions ─────────────────────────────────────────────────────

const CATEGORIES: Record<string, { label: string; eventTypes: string[] }> = {
  candidates: {
    label: "Subscription candidates",
    eventTypes: ["subscription_started", "renewal_charge", "subscription_candidate"],
  },
  unknown_payments: {
    label: "Unknown payments",
    eventTypes: ["unknown_payment"],
  },
  refunds: {
    label: "Refunds",
    eventTypes: ["refund"],
  },
  cancellations: {
    label: "Cancellations",
    eventTypes: ["cancellation"],
  },
  trials: {
    label: "Trials",
    eventTypes: ["trial_started", "trial_ending"],
  },
};

function categorize(records: EmailRecord[]): Record<string, EmailRecord[]> {
  const result: Record<string, EmailRecord[]> = {};
  const categorized = new Set<string>();

  for (const [key, cat] of Object.entries(CATEGORIES)) {
    result[key] = records.filter(r => cat.eventTypes.includes(r.event_type ?? ""));
    result[key].forEach(r => categorized.add(r.record_id));
  }
  // Anything not matched → "other"
  result.other = records.filter(r => !categorized.has(r.record_id));

  return result;
}

// ─── Confirm modal (pre-filled from email record) ─────────────────────────────

function ConfirmModal({ record, onSave, onClose }: {
  record: EmailRecord;
  onSave: (req: CreateSubscriptionRequest) => Promise<void>;
  onClose: () => void;
}) {
  const [name, setName] = useState(record.sender_name ?? "");
  const [amount, setAmount] = useState(record.amount_extracted?.toString() ?? "");
  const [currency, setCurrency] = useState(record.currency_extracted ?? "USD");
  const [cycle, setCycle] = useState("MONTHLY");
  const [category, setCategory] = useState("OTHER");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const INPUT_STYLE: React.CSSProperties = {
    background: "var(--surface)",
    border: "1px solid var(--border)",
    borderRadius: "4px",
    color: "var(--text)",
    padding: "4px 8px",
    fontSize: "13px",
    width: "100%",
    boxSizing: "border-box",
  };

  const handleSave = async () => {
    if (!name.trim()) { setError("Name is required"); return; }
    setSaving(true);
    setError(null);
    try {
      await onSave({
        name: name.trim(),
        amount: amount !== "" ? parseFloat(amount) : undefined,
        currency,
        billing_cycle: cycle,
        status: "ACTIVE",
        category,
      });
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create subscription");
      setSaving(false);
    }
  };

  return (
    <div style={{
      position: "fixed", inset: 0, background: "rgba(0,0,0,0.6)", zIndex: 100,
      display: "flex", alignItems: "center", justifyContent: "center",
    }}>
      <div style={{
        background: "var(--surface)", border: "1px solid var(--border)",
        borderRadius: "10px", padding: "24px", width: "420px", maxWidth: "90vw",
        display: "flex", flexDirection: "column", gap: "12px",
      }}>
        <h3 style={{ margin: 0, fontSize: "15px", fontWeight: 600 }}>Confirm as subscription</h3>
        <p style={{ margin: 0, fontSize: "12px", color: "var(--muted)" }}>
          From: {record.sender_address} · {new Date(record.email_date).toLocaleDateString()}
        </p>

        <label style={{ fontSize: "12px", color: "var(--muted)" }}>
          Service name
          <input style={INPUT_STYLE} value={name} onChange={e => setName(e.target.value)} autoFocus />
        </label>
        <div style={{ display: "flex", gap: "8px" }}>
          <label style={{ fontSize: "12px", color: "var(--muted)", flex: 2 }}>
            Amount
            <input style={INPUT_STYLE} type="number" step="0.01" value={amount} onChange={e => setAmount(e.target.value)} placeholder="0.00" />
          </label>
          <label style={{ fontSize: "12px", color: "var(--muted)", flex: 1 }}>
            Currency
            <input style={INPUT_STYLE} value={currency} onChange={e => setCurrency(e.target.value)} />
          </label>
        </div>
        <label style={{ fontSize: "12px", color: "var(--muted)" }}>
          Billing cycle
          <select style={INPUT_STYLE} value={cycle} onChange={e => setCycle(e.target.value)}>
            <option value="MONTHLY">Monthly</option>
            <option value="ANNUAL">Annual</option>
            <option value="QUARTERLY">Quarterly</option>
            <option value="WEEKLY">Weekly</option>
            <option value="UNKNOWN">Unknown</option>
          </select>
        </label>
        <label style={{ fontSize: "12px", color: "var(--muted)" }}>
          Category
          <select style={INPUT_STYLE} value={category} onChange={e => setCategory(e.target.value)}>
            <option value="STREAMING">Streaming</option>
            <option value="SAAS">SaaS</option>
            <option value="NEWS">News</option>
            <option value="CLOUD">Cloud</option>
            <option value="OTHER">Other</option>
          </select>
        </label>

        {error && <p style={{ margin: 0, fontSize: "12px", color: "var(--red, #ef4444)" }}>{error}</p>}

        <div style={{ display: "flex", gap: "8px", justifyContent: "flex-end" }}>
          <button
            style={{ background: "none", border: "1px solid var(--border)", borderRadius: "6px", padding: "6px 14px", cursor: "pointer", color: "var(--text)", fontSize: "13px" }}
            onClick={onClose}
          >
            Cancel
          </button>
          <button className="primary" style={{ fontSize: "13px" }} onClick={handleSave} disabled={saving}>
            {saving ? "Adding…" : "Add subscription"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Record row ────────────────────────────────────────────────────────────────

function RecordRow({ record, dismissed, onConfirm, onDismiss }: {
  record: EmailRecord;
  dismissed: boolean;
  onConfirm: () => void;
  onDismiss: () => void;
}) {
  if (dismissed) return null;

  return (
    <tr>
      <td style={{ color: "var(--muted)", fontSize: "12px" }}>{record.sender_address}</td>
      <td>
        <div>{record.subject}</div>
        {record.short_evidence && (
          <div style={{ color: "var(--muted)", fontSize: "12px", marginTop: "2px" }}>
            {record.short_evidence}
          </div>
        )}
      </td>
      <td style={{ color: "var(--muted)", fontSize: "12px", whiteSpace: "nowrap" }}>
        {record.event_type ?? "—"}
      </td>
      <td style={{ color: "var(--muted)", whiteSpace: "nowrap" }}>
        {new Date(record.email_date).toLocaleDateString()}
      </td>
      <td>
        {record.amount_extracted != null
          ? formatCurrency(record.amount_extracted, record.currency_extracted ?? "USD")
          : "—"}
      </td>
      <td>
        <span style={{
          color: record.confidence_score >= 0.6 ? "var(--yellow)" : "var(--muted)",
          fontVariantNumeric: "tabular-nums",
        }}>
          {(record.confidence_score * 100).toFixed(0)}%
        </span>
      </td>
      <td>
        <span className={`badge badge-${record.source_provider.toLowerCase()}`}>
          {record.source_provider}
        </span>
      </td>
      <td>
        <div style={{ display: "flex", gap: "4px", whiteSpace: "nowrap" }}>
          <button
            style={{ background: "none", border: "1px solid var(--border)", borderRadius: "4px", fontSize: "11px", padding: "2px 7px", cursor: "pointer", color: "var(--accent)" }}
            onClick={onConfirm}
            title="Add as subscription"
          >
            ✓ Confirm
          </button>
          <button
            style={{ background: "none", border: "1px solid var(--border)", borderRadius: "4px", fontSize: "11px", padding: "2px 7px", cursor: "pointer", color: "var(--muted)" }}
            onClick={onDismiss}
            title="Dismiss from view"
          >
            ✕ Dismiss
          </button>
        </div>
      </td>
    </tr>
  );
}

// ─── Section ───────────────────────────────────────────────────────────────────

function Section({ title, records, dismissed, onConfirm, onDismiss }: {
  title: string;
  records: EmailRecord[];
  dismissed: Set<string>;
  onConfirm: (r: EmailRecord) => void;
  onDismiss: (id: string) => void;
}) {
  const [open, setOpen] = useState(true);
  const visible = records.filter(r => !dismissed.has(r.record_id));
  if (visible.length === 0) return null;

  return (
    <div style={{ marginBottom: "16px" }}>
      <div
        style={{ display: "flex", alignItems: "center", gap: "8px", cursor: "pointer", marginBottom: "8px" }}
        onClick={() => setOpen(v => !v)}
      >
        <span style={{ fontSize: "13px", fontWeight: 600 }}>{title}</span>
        <span style={{
          background: "var(--border)",
          borderRadius: "10px",
          fontSize: "11px",
          padding: "1px 7px",
          color: "var(--muted)",
        }}>{visible.length}</span>
        <span style={{ color: "var(--muted)", fontSize: "11px", marginLeft: "auto" }}>{open ? "▲" : "▼"}</span>
      </div>
      {open && (
        <table>
          <thead>
            <tr>
              <th>Sender</th>
              <th>Subject</th>
              <th>Type</th>
              <th>Date</th>
              <th>Amount</th>
              <th>Confidence</th>
              <th>Source</th>
              <th style={{ width: "130px" }}></th>
            </tr>
          </thead>
          <tbody>
            {records.map(r => (
              <RecordRow
                key={r.record_id}
                record={r}
                dismissed={dismissed.has(r.record_id)}
                onConfirm={() => onConfirm(r)}
                onDismiss={() => onDismiss(r.record_id)}
              />
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

// ─── Main export ──────────────────────────────────────────────────────────────

export function ReviewQueue({ records, onRefresh }: Props) {
  const [dismissed, setDismissed] = useState<Set<string>>(new Set());
  const [confirmRecord, setConfirmRecord] = useState<EmailRecord | null>(null);

  const categorized = categorize(records);

  const handleDismiss = (id: string) => {
    setDismissed(prev => new Set([...prev, id]));
  };

  const handleSaveConfirm = async (req: CreateSubscriptionRequest) => {
    await api.createSubscription(req);
    if (confirmRecord) handleDismiss(confirmRecord.record_id);
    setConfirmRecord(null);
    onRefresh();
  };

  const allVisible = records.filter(r => !dismissed.has(r.record_id));

  if (allVisible.length === 0 && records.length === 0) {
    return <p style={{ color: "var(--muted)" }}>No flagged records — inbox looks clean.</p>;
  }

  if (allVisible.length === 0 && dismissed.size > 0) {
    return (
      <p style={{ color: "var(--muted)" }}>
        All flagged records dismissed.{" "}
        <button
          style={{ background: "none", border: "none", cursor: "pointer", color: "var(--accent)", textDecoration: "underline", padding: 0, fontSize: "inherit" }}
          onClick={() => setDismissed(new Set())}
        >
          Show all
        </button>
      </p>
    );
  }

  return (
    <div>
      {confirmRecord && (
        <ConfirmModal
          record={confirmRecord}
          onSave={handleSaveConfirm}
          onClose={() => setConfirmRecord(null)}
        />
      )}

      {Object.entries(CATEGORIES).map(([key, cat]) => (
        <Section
          key={key}
          title={cat.label}
          records={categorized[key] ?? []}
          dismissed={dismissed}
          onConfirm={setConfirmRecord}
          onDismiss={handleDismiss}
        />
      ))}

      {(categorized.other?.length ?? 0) > 0 && (
        <Section
          title="Other"
          records={categorized.other}
          dismissed={dismissed}
          onConfirm={setConfirmRecord}
          onDismiss={handleDismiss}
        />
      )}
    </div>
  );
}
