"use client";
import { useState } from "react";
import type { PaymentEvent } from "@/types/api";
import { formatCurrency } from "@/lib/format";
import { api } from "@/lib/api";

/**
 * PaymentEventsTable — renders the payment_events financial event log.
 *
 * Privacy: displays only safe structured fields. No raw email content
 * (subject, sender address, snippet, body text) is stored in payment_events
 * and therefore cannot appear here.
 *
 * Columns: Date | Type | Merchant | Amount | Recurring | One-time | Linked | Conf.
 * Phase 3.4 additions: 📎 attachment indicator, Link/Unlink actions
 */

const EVENT_TYPE_LABELS: Record<string, string> = {
  subscription_charge: "Subscription charge",
  renewal_charge:      "Renewal",
  one_time_charge:     "One-time",
  refund:              "Refund",
  cancellation:        "Cancellation",
  trial_started:       "Trial started",
  trial_ended:         "Trial ended",
  failed_payment:      "Failed payment",
  price_change:        "Price change",
  unknown_payment:     "Unknown payment",
};

const EVENT_TYPE_COLORS: Record<string, string> = {
  subscription_charge: "var(--green)",
  renewal_charge:      "var(--green)",
  refund:              "var(--yellow)",
  cancellation:        "var(--red)",
  trial_started:       "var(--accent)",
  trial_ended:         "var(--muted)",
  failed_payment:      "var(--red)",
  price_change:        "var(--yellow)",
  one_time_charge:     "var(--text)",
  unknown_payment:     "var(--muted)",
};

interface Props {
  events: PaymentEvent[];
  onRefresh: () => void;
}

// ─── Relabel modal ─────────────────────────────────────────────────────────────

function RelabelModal({ event, onSave, onClose }: {
  event: PaymentEvent;
  onSave: (newName: string) => Promise<void>;
  onClose: () => void;
}) {
  const [name, setName] = useState(event.merchant_name);
  const [saving, setSaving] = useState(false);
  const INPUT_S: React.CSSProperties = {
    background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "4px",
    color: "var(--text)", padding: "4px 8px", fontSize: "13px", width: "100%", boxSizing: "border-box",
  };
  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.6)", zIndex: 100, display: "flex", alignItems: "center", justifyContent: "center" }}>
      <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "10px", padding: "24px", width: "360px", maxWidth: "90vw", display: "flex", flexDirection: "column", gap: "12px" }}>
        <h3 style={{ margin: 0, fontSize: "15px", fontWeight: 600 }}>Relabel provider</h3>
        <p style={{ margin: 0, fontSize: "12px", color: "var(--muted)" }}>Current: {event.merchant_name}</p>
        <label style={{ fontSize: "12px", color: "var(--muted)" }}>
          New name
          <input style={INPUT_S} value={name} onChange={e => setName(e.target.value)} autoFocus />
        </label>
        <div style={{ display: "flex", gap: "8px", justifyContent: "flex-end" }}>
          <button style={{ background: "none", border: "1px solid var(--border)", borderRadius: "6px", padding: "6px 14px", cursor: "pointer", color: "var(--text)", fontSize: "13px" }} onClick={onClose}>Cancel</button>
          <button className="primary" style={{ fontSize: "13px" }} disabled={saving}
            onClick={async () => { setSaving(true); await onSave(name); onClose(); }}>
            {saving ? "Saving…" : "Relabel"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Link modal ────────────────────────────────────────────────────────────────

function LinkModal({ event, onSave, onClose }: {
  event: PaymentEvent;
  onSave: (subscriptionId: string) => Promise<void>;
  onClose: () => void;
}) {
  const [subscriptionId, setSubscriptionId] = useState("");
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
    if (!subscriptionId.trim()) { setError("Subscription ID is required"); return; }
    setSaving(true);
    setError(null);
    try {
      await onSave(subscriptionId.trim());
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to link event");
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
        borderRadius: "10px", padding: "24px", width: "380px", maxWidth: "90vw",
        display: "flex", flexDirection: "column", gap: "12px",
      }}>
        <h3 style={{ margin: 0, fontSize: "15px", fontWeight: 600 }}>Link payment event</h3>
        <p style={{ margin: 0, fontSize: "12px", color: "var(--muted)" }}>
          {event.merchant_name} · {event.event_date.slice(0, 10)}
          {event.amount != null && ` · ${formatCurrency(event.amount, event.currency)}`}
        </p>
        <label style={{ fontSize: "12px", color: "var(--muted)" }}>
          Subscription ID
          <input
            style={INPUT_STYLE}
            value={subscriptionId}
            onChange={e => setSubscriptionId(e.target.value)}
            placeholder="sub_…"
            autoFocus
          />
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
            {saving ? "Linking…" : "Link"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Event row ────────────────────────────────────────────────────────────────

function EventRow({ ev, onLink, onUnlink, onMarkOneTime, onRelabel }: {
  ev: PaymentEvent;
  onLink: () => void;
  onUnlink: () => void;
  onMarkOneTime: () => void;
  onRelabel: () => void;
}) {
  const BTN: React.CSSProperties = {
    background: "none", border: "1px solid var(--border)", borderRadius: "4px",
    fontSize: "11px", padding: "2px 6px", cursor: "pointer", color: "var(--muted)",
  };

  const isOneTime = ev.user_marked_one_time === 1 || ev.is_one_time_candidate === 1;

  return (
    <tr style={{ opacity: ev.user_marked_one_time === 1 ? 0.6 : 1 }}>
      <td style={{ color: "var(--muted)", whiteSpace: "nowrap" }}>
        {ev.event_date.slice(0, 10)}
        {ev.account_alias && (
          <div style={{ fontSize: "10px", color: "var(--muted)", opacity: 0.6 }}>
            acct:{ev.account_alias}
          </div>
        )}
      </td>
      <td>
        <span style={{ color: EVENT_TYPE_COLORS[ev.event_type] ?? "var(--text)", fontSize: "13px" }}>
          {EVENT_TYPE_LABELS[ev.event_type] ?? ev.event_type}
        </span>
        {ev.user_marked_one_time === 1 && (
          <span style={{ fontSize: "10px", color: "var(--muted)", marginLeft: "6px" }}>1× one-time</span>
        )}
      </td>
      <td style={{ fontWeight: 500 }}>
        {ev.merchant_name}
        {ev.decision_reason && (
          <div style={{ fontSize: "10px", color: "var(--muted)", marginTop: "2px", maxWidth: "200px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
               title={ev.decision_reason}>
            {ev.decision_reason}
          </div>
        )}
      </td>
      <td style={{ whiteSpace: "nowrap" }}>
        {ev.amount != null
          ? formatCurrency(ev.amount, ev.currency)
          : ev.needs_attachment_review
            ? <span title="Amount is in an attachment (PDF) — not yet extracted" style={{ color: "var(--muted)" }}>📎 —</span>
            : <span style={{ color: "var(--muted)" }}>—</span>}
      </td>
      <td style={{ textAlign: "center" }}>
        {ev.is_recurring_candidate ? "✓" : <span style={{ color: "var(--muted)" }}>—</span>}
      </td>
      <td style={{ textAlign: "center" }}>
        {isOneTime ? "✓" : <span style={{ color: "var(--muted)" }}>—</span>}
      </td>
      <td style={{ textAlign: "center" }}>
        {ev.subscription_id
          ? <span style={{ color: "var(--green)" }} title={ev.subscription_id}>✓</span>
          : <span style={{ color: "var(--muted)" }}>—</span>}
      </td>
      <td style={{ color: "var(--muted)", fontSize: "12px" }}>
        {Math.round(ev.confidence_score * 100)}%
      </td>
      <td>
        <div style={{ display: "flex", gap: "3px", whiteSpace: "nowrap", flexWrap: "wrap" }}>
          {ev.subscription_id ? (
            <button style={BTN} onClick={onUnlink} title="Remove subscription link">Unlink</button>
          ) : (
            <button style={{ ...BTN, color: "var(--accent)" }} onClick={onLink} title="Link to subscription">Link</button>
          )}
          {ev.user_marked_one_time !== 1 && (
            <button style={BTN} onClick={onMarkOneTime} title="Mark as one-time payment">1×</button>
          )}
          <button style={BTN} onClick={onRelabel} title="Relabel provider name">✎</button>
        </div>
      </td>
    </tr>
  );
}

// ─── Main export ──────────────────────────────────────────────────────────────

export function PaymentEventsTable({ events, onRefresh }: Props) {
  const [linkEvent, setLinkEvent] = useState<PaymentEvent | null>(null);
  const [relabelEvent, setRelabelEvent] = useState<PaymentEvent | null>(null);

  const handleLink = async (eventId: string, subscriptionId: string) => {
    await api.linkPaymentEvent(eventId, subscriptionId);
    onRefresh();
  };

  const handleUnlink = async (eventId: string) => {
    await api.unlinkPaymentEvent(eventId);
    onRefresh();
  };

  const handleMarkOneTime = async (eventId: string) => {
    try {
      await api.markPaymentEventOneTime(eventId);
      onRefresh();
    } catch (e) {
      console.error("Failed to mark as one-time:", e);
    }
  };

  const handleRelabel = async (eventId: string, newName: string) => {
    await api.relabelPaymentEvent(eventId, newName);
    onRefresh();
  };

  if (events.length === 0) {
    return (
      <p style={{ color: "var(--muted)", padding: "16px 0" }}>
        No payment events recorded. Run a scan to detect financial events from your emails.
      </p>
    );
  }

  const attachmentCount = events.filter(e => e.needs_attachment_review).length;

  return (
    <div>
      {linkEvent && (
        <LinkModal
          event={linkEvent}
          onSave={(subId) => handleLink(linkEvent.event_id, subId)}
          onClose={() => setLinkEvent(null)}
        />
      )}
      {relabelEvent && (
        <RelabelModal
          event={relabelEvent}
          onSave={(newName) => handleRelabel(relabelEvent.event_id, newName)}
          onClose={() => setRelabelEvent(null)}
        />
      )}

      {attachmentCount > 0 && (
        <p style={{ fontSize: "12px", color: "var(--muted)", marginBottom: "8px" }}>
          📎 {attachmentCount} event{attachmentCount !== 1 ? "s" : ""} have amount in an attachment (PDF) — not yet extracted.
        </p>
      )}

      <div style={{ overflowX: "auto" }}>
        <table>
          <thead>
            <tr>
              <th>Date</th>
              <th>Type</th>
              <th>Merchant</th>
              <th>Amount</th>
              <th title="Confirmed recurring subscription evidence">Recurring</th>
              <th title="One-time payment evidence">One-time</th>
              <th title="Linked to a subscription record">Linked</th>
              <th title="Detection confidence">Conf.</th>
              <th style={{ width: "60px" }}></th>
            </tr>
          </thead>
          <tbody>
            {events.map((ev) => (
              <EventRow
                key={ev.event_id}
                ev={ev}
                onLink={() => setLinkEvent(ev)}
                onUnlink={() => handleUnlink(ev.event_id)}
                onMarkOneTime={() => handleMarkOneTime(ev.event_id)}
                onRelabel={() => setRelabelEvent(ev)}
              />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
