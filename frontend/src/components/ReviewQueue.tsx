"use client";
import { useState, useEffect } from "react";
import type { EmailRecord, CreateSubscriptionRequest, Attachment } from "@/types/api";
import { formatCurrency, formatDateLocal } from "@/lib/format";
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
          From: {record.sender_address} · {formatDateLocal(record.email_date)}
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

// Phase 3.7: inline PDF/attachment evidence detail (fetched on demand).
function AttachmentDetail({ recordId }: { recordId: string }) {
  const [atts, setAtts] = useState<Attachment[] | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    api.getRecordAttachments(recordId)
      .then(setAtts)
      .catch(() => setError(true));
  }, [recordId]);

  if (error) return <div style={{ fontSize: "11px", color: "var(--muted)" }}>Could not load attachments.</div>;
  if (atts === null) return <div style={{ fontSize: "11px", color: "var(--muted)" }}>Loading attachments…</div>;
  if (atts.length === 0) return <div style={{ fontSize: "11px", color: "var(--muted)" }}>No attachment details.</div>;

  return (
    <div style={{ marginTop: "4px", padding: "6px 8px", background: "var(--bg, rgba(255,255,255,0.03))", borderRadius: "4px", fontSize: "11px" }}>
      {atts.map((a) => {
        const f = a.extracted_fields;
        return (
          <div key={a.attachment_row_id} style={{ marginBottom: "4px" }}>
            <div style={{ color: "var(--text)" }}>
              📎 {a.filename ?? a.detected_attachment_type ?? "attachment"}
              {" · "}
              <span style={{ color: a.processing_status === "PARSED" ? "var(--green, #4ade80)" : "var(--yellow, #facc15)" }}>
                {a.processing_status.replace(/_/g, " ").toLowerCase()}
              </span>
            </div>
            {f && (
              <div style={{ color: "var(--muted)", marginLeft: "16px" }}>
                {f.amount != null && (
                  <span>{formatCurrency(f.amount, f.currency ?? "USD")}
                    {f.inferred_cycle && f.inferred_cycle !== "UNKNOWN" ? ` / ${f.inferred_cycle.toLowerCase()}` : ""} · </span>
                )}
                {f.provider && <span>{f.provider} · </span>}
                {f.evidence_reasons && <span style={{ color: "var(--green, #4ade80)" }}>{f.evidence_reasons.replace(/;/g, ", ")}</span>}
                {f.penalty_reasons && <span style={{ color: "var(--yellow, #facc15)" }}> · {f.penalty_reasons.replace(/;/g, ", ")}</span>}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function RecordRow({ record, dismissed, onConfirm, onDismiss, onMarkOneTime }: {
  record: EmailRecord;
  dismissed: boolean;
  onConfirm: () => void;
  onDismiss: () => void;
  onMarkOneTime: () => void;
}) {
  const [showAttachments, setShowAttachments] = useState(false);
  if (dismissed) return null;

  const BTN_BASE: React.CSSProperties = {
    background: "none", border: "1px solid var(--border)", borderRadius: "4px",
    fontSize: "11px", padding: "2px 7px", cursor: "pointer",
  };

  return (
    <tr>
      <td style={{ color: "var(--muted)", fontSize: "12px" }}>
        {record.sender_address}
        {record.account_alias && (
          <div style={{ fontSize: "10px", color: "var(--muted)", opacity: 0.6 }}>
            acct:{record.account_alias}
          </div>
        )}
      </td>
      <td>
        <div>{record.subject}</div>
        {/* Phase 3.6: Explanation fields */}
        {record.evidence_summary && (
          <div style={{ color: "var(--green, #4ade80)", fontSize: "11px", marginTop: "3px" }}>
            ✓ {record.evidence_summary}
          </div>
        )}
        {record.missing_evidence && (
          <div style={{ color: "var(--yellow, #facc15)", fontSize: "11px", marginTop: "1px" }}>
            ⚠ Missing: {record.missing_evidence}
          </div>
        )}
        {record.suggested_action && (
          <div style={{ color: "var(--muted)", fontSize: "11px", marginTop: "1px" }}>
            → {record.suggested_action}
          </div>
        )}
        {!record.evidence_summary && record.short_evidence && (
          <div style={{ color: "var(--muted)", fontSize: "12px", marginTop: "2px" }}>
            {record.short_evidence}
          </div>
        )}
        {record.has_attachment && (
          <div style={{ marginTop: "3px" }}>
            <button
              onClick={() => setShowAttachments(v => !v)}
              style={{ background: "none", border: "none", cursor: "pointer", color: "var(--accent)", fontSize: "11px", padding: 0 }}
              title="View attachment / PDF evidence"
            >
              📎 {showAttachments ? "Hide attachment details" : "View attachment details"}
            </button>
            {showAttachments && <AttachmentDetail recordId={record.record_id} />}
          </div>
        )}
      </td>
      <td style={{ color: "var(--muted)", fontSize: "12px", whiteSpace: "nowrap" }}>
        {record.detection_state
          ? record.detection_state.replace(/_/g, " ").toLowerCase()
          : (record.event_type ?? "—")}
      </td>
      <td style={{ color: "var(--muted)", whiteSpace: "nowrap" }}>
        {formatDateLocal(record.email_date)}
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
        <div style={{ display: "flex", gap: "4px", whiteSpace: "nowrap", flexWrap: "wrap" }}>
          <button
            style={{ ...BTN_BASE, color: "var(--accent)" }}
            onClick={onConfirm}
            title="Add as subscription"
          >
            ✓ Confirm
          </button>
          <button
            style={{ ...BTN_BASE, color: "var(--muted)" }}
            onClick={onDismiss}
            title="Dismiss from view (persisted)"
          >
            ✕ Dismiss
          </button>
          <button
            style={{ ...BTN_BASE, color: "var(--muted)" }}
            onClick={onMarkOneTime}
            title="Mark as one-time payment — not a subscription"
          >
            1× One-time
          </button>
        </div>
      </td>
    </tr>
  );
}

// ─── Section ───────────────────────────────────────────────────────────────────

function Section({ title, records, dismissed, onConfirm, onDismiss, onMarkOneTime }: {
  title: string;
  records: EmailRecord[];
  dismissed: Set<string>;
  onConfirm: (r: EmailRecord) => void;
  onDismiss: (id: string) => void;
  onMarkOneTime: (id: string) => void;
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
                onMarkOneTime={() => onMarkOneTime(r.record_id)}
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
  // Dismissed set is seeded from DB on mount (Phase 3.5 — persists across refreshes).
  // Initially populated with IDs already dismissed in previous sessions.
  const [dismissed, setDismissed] = useState<Set<string>>(new Set());
  const [loadingDismissed, setLoadingDismissed] = useState(true);
  const [confirmRecord, setConfirmRecord] = useState<EmailRecord | null>(null);

  // On mount: seed dismissed set from DB so previously dismissed
  // records stay hidden after page reload (Phase 3.5 persistence).
  useEffect(() => {
    api.getDismissedEmailIds()
      .then(ids => setDismissed(new Set(ids)))
      .catch(() => {/* graceful degradation: dismissed set stays empty */})
      .finally(() => setLoadingDismissed(false));
  }, []);

  const handleDismiss = async (id: string) => {
    // Persist to DB first (Phase 3.5). Gracefully degrade if API fails.
    try {
      await api.dismissEmailRecord(id);
    } catch (e) {
      // Non-fatal: still dismiss locally even if persist fails
      console.error("Failed to persist dismissal:", e);
    }
    setDismissed(prev => new Set([...prev, id]));
  };

  const handleMarkOneTime = async (id: string) => {
    try {
      await api.markEmailOneTime(id);
    } catch (e) {
      console.error("Failed to mark as one-time:", e);
    }
    // Treat one-time marked items like dismissed — hide from review queue
    setDismissed(prev => new Set([...prev, id]));
  };

  const handleSaveConfirm = async (req: CreateSubscriptionRequest) => {
    await api.createSubscription(req);
    if (confirmRecord) await handleDismiss(confirmRecord.record_id);
    setConfirmRecord(null);
    onRefresh();
  };

  const [selectedAccount, setSelectedAccount] = useState<string>("all");

  // Collect unique account aliases present in the records for the filter dropdown.
  const accountAliases = Array.from(new Set(
    records.map(r => r.account_alias).filter((a): a is string => Boolean(a))
  ));

  const allVisible = records
    .filter(r => !dismissed.has(r.record_id))
    .filter(r => selectedAccount === "all" || r.account_alias === selectedAccount);

  if (loadingDismissed) {
    return <p style={{ color: "var(--muted)", fontSize: "13px" }}>Loading…</p>;
  }

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
          Show all (local view only)
        </button>
      </p>
    );
  }

  const filteredCategorized = categorize(allVisible);

  return (
    <div>
      {confirmRecord && (
        <ConfirmModal
          record={confirmRecord}
          onSave={handleSaveConfirm}
          onClose={() => setConfirmRecord(null)}
        />
      )}

      {accountAliases.length > 1 && (
        <div style={{ marginBottom: "12px", display: "flex", alignItems: "center", gap: "8px" }}>
          <span style={{ fontSize: "12px", color: "var(--muted)" }}>Account:</span>
          <select
            value={selectedAccount}
            onChange={e => setSelectedAccount(e.target.value)}
            style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "6px", color: "var(--text)", padding: "3px 8px", fontSize: "12px", cursor: "pointer" }}
          >
            <option value="all">All accounts</option>
            {accountAliases.map(alias => (
              <option key={alias} value={alias}>acct:{alias}</option>
            ))}
          </select>
        </div>
      )}

      {Object.entries(CATEGORIES).map(([key, cat]) => (
        <Section
          key={key}
          title={cat.label}
          records={filteredCategorized[key] ?? []}
          dismissed={dismissed}
          onConfirm={setConfirmRecord}
          onDismiss={handleDismiss}
          onMarkOneTime={handleMarkOneTime}
        />
      ))}

      {(filteredCategorized.other?.length ?? 0) > 0 && (
        <Section
          title="Other"
          records={filteredCategorized.other}
          dismissed={dismissed}
          onConfirm={setConfirmRecord}
          onDismiss={handleDismiss}
          onMarkOneTime={handleMarkOneTime}
        />
      )}
    </div>
  );
}
