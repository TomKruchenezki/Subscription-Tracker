"use client";
import { useState } from "react";
import type { Subscription, UpdateSubscriptionRequest, CreateSubscriptionRequest } from "@/types/api";
import { formatMonthly } from "@/lib/format";
import { api } from "@/lib/api";

interface Props {
  subscriptions: Subscription[];
  onRefresh: () => void;
}

const CYCLE_LABELS: Record<string, string> = {
  MONTHLY: "Monthly",
  ANNUAL: "Annual",
  QUARTERLY: "Quarterly",
  WEEKLY: "Weekly",
  UNKNOWN: "—",
};

const INPUT_STYLE: React.CSSProperties = {
  background: "var(--surface)",
  border: "1px solid var(--border)",
  borderRadius: "4px",
  color: "var(--text)",
  padding: "2px 6px",
  fontSize: "13px",
  width: "100%",
};

const BTN_STYLE: React.CSSProperties = {
  background: "none",
  border: "none",
  cursor: "pointer",
  padding: "2px 6px",
  borderRadius: "4px",
  fontSize: "12px",
  color: "var(--muted)",
};

function monthlyEquivalent(sub: Subscription): string {
  if (sub.amount == null) return "—";
  const monthly = sub.billing_cycle === "ANNUAL" ? sub.amount / 12 : sub.amount;
  return formatMonthly(monthly, sub.currency);
}

// ─── Inline edit row ─────────────────────────────────────────────────────────

function EditRow({ sub, onSave, onCancel }: {
  sub: Subscription;
  onSave: (req: UpdateSubscriptionRequest) => Promise<void>;
  onCancel: () => void;
}) {
  const [name, setName] = useState(sub.name);
  const [amount, setAmount] = useState(sub.amount?.toString() ?? "");
  const [currency, setCurrency] = useState(sub.currency);
  const [cycle, setCycle] = useState(sub.billing_cycle);
  const [status, setStatus] = useState(sub.status);
  const [category, setCategory] = useState(sub.category);
  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
    setSaving(true);
    try {
      await onSave({
        name: name || undefined,
        amount: amount !== "" ? parseFloat(amount) : null,
        currency: currency || undefined,
        billing_cycle: cycle || undefined,
        status: status || undefined,
        category: category || undefined,
      });
    } finally {
      setSaving(false);
    }
  };

  return (
    <tr style={{ background: "var(--surface-hover, rgba(255,255,255,0.04))" }}>
      <td><input style={INPUT_STYLE} value={name} onChange={e => setName(e.target.value)} /></td>
      <td>
        <div style={{ display: "flex", gap: "4px" }}>
          <input style={{ ...INPUT_STYLE, width: "70px" }} type="number" step="0.01" value={amount} onChange={e => setAmount(e.target.value)} placeholder="0.00" />
          <input style={{ ...INPUT_STYLE, width: "50px" }} value={currency} onChange={e => setCurrency(e.target.value)} placeholder="USD" />
        </div>
      </td>
      <td>
        <select style={INPUT_STYLE} value={cycle} onChange={e => setCycle(e.target.value as Subscription["billing_cycle"])}>
          <option value="MONTHLY">Monthly</option>
          <option value="ANNUAL">Annual</option>
          <option value="QUARTERLY">Quarterly</option>
          <option value="WEEKLY">Weekly</option>
          <option value="UNKNOWN">Unknown</option>
        </select>
      </td>
      <td>
        <select style={INPUT_STYLE} value={category} onChange={e => setCategory(e.target.value as Subscription["category"])}>
          <option value="STREAMING">Streaming</option>
          <option value="SAAS">SaaS</option>
          <option value="NEWS">News</option>
          <option value="CLOUD">Cloud</option>
          <option value="OTHER">Other</option>
        </select>
      </td>
      <td>
        <select style={INPUT_STYLE} value={status} onChange={e => setStatus(e.target.value as Subscription["status"])}>
          <option value="ACTIVE">Active</option>
          <option value="TRIAL">Trial</option>
          <option value="PAUSED">Paused</option>
          <option value="CANCELLED">Cancelled</option>
          <option value="UNKNOWN">Unknown</option>
        </select>
      </td>
      <td colSpan={3}>
        <div style={{ display: "flex", gap: "6px" }}>
          <button className="primary" style={{ fontSize: "12px", padding: "3px 10px" }} onClick={handleSave} disabled={saving}>
            {saving ? "Saving…" : "Save"}
          </button>
          <button style={{ ...BTN_STYLE, color: "var(--text)" }} onClick={onCancel}>Cancel</button>
        </div>
      </td>
    </tr>
  );
}

// ─── Create form ──────────────────────────────────────────────────────────────

function CreateForm({ onSave, onCancel }: {
  onSave: (req: CreateSubscriptionRequest) => Promise<void>;
  onCancel: () => void;
}) {
  const [name, setName] = useState("");
  const [amount, setAmount] = useState("");
  const [currency, setCurrency] = useState("USD");
  const [cycle, setCycle] = useState("MONTHLY");
  const [status, setStatus] = useState("ACTIVE");
  const [category, setCategory] = useState("OTHER");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
        status,
        category,
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create subscription");
      setSaving(false);
    }
  };

  return (
    <tr style={{ background: "var(--surface-hover, rgba(255,255,255,0.04))" }}>
      <td>
        <input style={INPUT_STYLE} value={name} onChange={e => setName(e.target.value)} placeholder="Service name (required)" autoFocus />
        {error && <div style={{ color: "var(--red, #ef4444)", fontSize: "11px", marginTop: "2px" }}>{error}</div>}
      </td>
      <td>
        <div style={{ display: "flex", gap: "4px" }}>
          <input style={{ ...INPUT_STYLE, width: "70px" }} type="number" step="0.01" value={amount} onChange={e => setAmount(e.target.value)} placeholder="0.00" />
          <input style={{ ...INPUT_STYLE, width: "50px" }} value={currency} onChange={e => setCurrency(e.target.value)} />
        </div>
      </td>
      <td>
        <select style={INPUT_STYLE} value={cycle} onChange={e => setCycle(e.target.value)}>
          <option value="MONTHLY">Monthly</option>
          <option value="ANNUAL">Annual</option>
          <option value="QUARTERLY">Quarterly</option>
          <option value="WEEKLY">Weekly</option>
          <option value="UNKNOWN">Unknown</option>
        </select>
      </td>
      <td>
        <select style={INPUT_STYLE} value={category} onChange={e => setCategory(e.target.value)}>
          <option value="STREAMING">Streaming</option>
          <option value="SAAS">SaaS</option>
          <option value="NEWS">News</option>
          <option value="CLOUD">Cloud</option>
          <option value="OTHER">Other</option>
        </select>
      </td>
      <td>
        <select style={INPUT_STYLE} value={status} onChange={e => setStatus(e.target.value)}>
          <option value="ACTIVE">Active</option>
          <option value="TRIAL">Trial</option>
          <option value="UNKNOWN">Unknown</option>
        </select>
      </td>
      <td colSpan={3}>
        <div style={{ display: "flex", gap: "6px" }}>
          <button className="primary" style={{ fontSize: "12px", padding: "3px 10px" }} onClick={handleSave} disabled={saving}>
            {saving ? "Adding…" : "Add"}
          </button>
          <button style={{ ...BTN_STYLE, color: "var(--text)" }} onClick={onCancel}>Cancel</button>
        </div>
      </td>
    </tr>
  );
}

// ─── Subscription row ─────────────────────────────────────────────────────────

function SubRow({ sub, onEdit, onDelete }: {
  sub: Subscription;
  onEdit: () => void;
  onDelete: () => void;
}) {
  return (
    <tr style={{ opacity: sub.status === "CANCELLED" ? 0.4 : 1 }}>
      <td style={{ fontWeight: 500 }}>{sub.name}</td>
      <td>{monthlyEquivalent(sub)}</td>
      <td>{CYCLE_LABELS[sub.billing_cycle] ?? sub.billing_cycle}</td>
      <td style={{ color: "var(--muted)" }}>{sub.category}</td>
      <td>
        <span className={`badge badge-${sub.status.toLowerCase()}`}>{sub.status}</span>
      </td>
      <td>
        <span className={`badge badge-${sub.source_provider.toLowerCase()}`}>{sub.source_provider}</span>
      </td>
      <td style={{ color: "var(--muted)" }}>
        {sub.first_charge_date ? new Date(sub.first_charge_date).toLocaleDateString() : "—"}
      </td>
      <td style={{ color: "var(--muted)" }}>
        {sub.last_charge_date ? new Date(sub.last_charge_date).toLocaleDateString() : "—"}
      </td>
      <td>
        <div style={{ display: "flex", gap: "2px" }}>
          <button style={BTN_STYLE} onClick={onEdit} title="Edit subscription" aria-label="Edit">✏️</button>
          <button style={{ ...BTN_STYLE, color: "var(--red, #ef4444)" }} onClick={onDelete} title="Delete subscription" aria-label="Delete">🗑️</button>
        </div>
      </td>
    </tr>
  );
}

// ─── Section table ────────────────────────────────────────────────────────────

function SectionTable({ rows, editingId, onEdit, onSave, onCancel, onDelete, showCreateForm, onSaveCreate, onCancelCreate }: {
  rows: Subscription[];
  editingId: string | null;
  onEdit: (id: string) => void;
  onSave: (id: string, req: UpdateSubscriptionRequest) => Promise<void>;
  onCancel: () => void;
  onDelete: (id: string) => void;
  showCreateForm?: boolean;
  onSaveCreate?: (req: CreateSubscriptionRequest) => Promise<void>;
  onCancelCreate?: () => void;
}) {
  return (
    <table>
      <thead>
        <tr>
          <th>Service</th>
          <th>Amount/mo</th>
          <th>Cycle</th>
          <th>Category</th>
          <th>Status</th>
          <th>Source</th>
          <th>First charged</th>
          <th>Last charged</th>
          <th style={{ width: "60px" }}></th>
        </tr>
      </thead>
      <tbody>
        {showCreateForm && onSaveCreate && onCancelCreate && (
          <CreateForm onSave={onSaveCreate} onCancel={onCancelCreate} />
        )}
        {rows.map((sub) =>
          editingId === sub.subscription_id ? (
            <EditRow
              key={sub.subscription_id}
              sub={sub}
              onSave={(req) => onSave(sub.subscription_id, req)}
              onCancel={onCancel}
            />
          ) : (
            <SubRow
              key={sub.subscription_id}
              sub={sub}
              onEdit={() => onEdit(sub.subscription_id)}
              onDelete={() => onDelete(sub.subscription_id)}
            />
          )
        )}
      </tbody>
    </table>
  );
}

// ─── Main export ──────────────────────────────────────────────────────────────

export function SubscriptionTable({ subscriptions, onRefresh }: Props) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [showCandidates, setShowCandidates] = useState(true);

  const confirmed = subscriptions.filter(s => s.status === "ACTIVE" || s.status === "TRIAL");
  const candidates = subscriptions.filter(s => s.status === "UNKNOWN" || s.status === "PAUSED");
  const others = subscriptions.filter(s => s.status === "CANCELLED");

  const handleSave = async (id: string, req: UpdateSubscriptionRequest) => {
    await api.updateSubscription(id, req);
    setEditingId(null);
    onRefresh();
  };

  const handleDelete = async (id: string) => {
    const sub = subscriptions.find(s => s.subscription_id === id);
    if (!window.confirm(`Delete "${sub?.name ?? id}"? This cannot be undone.`)) return;
    await api.deleteSubscription(id);
    onRefresh();
  };

  const handleCreate = async (req: CreateSubscriptionRequest) => {
    await api.createSubscription(req);
    setShowCreateForm(false);
    onRefresh();
  };

  if (subscriptions.length === 0 && !showCreateForm) {
    return (
      <div>
        <button className="primary" style={{ marginBottom: "12px" }} onClick={() => setShowCreateForm(true)}>
          + Add subscription
        </button>
        <p style={{ color: "var(--muted)" }}>
          No subscriptions found. Run a scan to detect subscriptions from your email source, or add one manually.
        </p>
        {showCreateForm && (
          <table>
            <thead>
              <tr>
                <th>Service</th><th>Amount/mo</th><th>Cycle</th><th>Category</th><th>Status</th><th colSpan={4}></th>
              </tr>
            </thead>
            <tbody>
              <CreateForm onSave={handleCreate} onCancel={() => setShowCreateForm(false)} />
            </tbody>
          </table>
        )}
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "24px" }}>
      {/* ── Active & Trial ── */}
      <div>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
          <h3 style={{ margin: 0, fontSize: "15px", fontWeight: 600 }}>
            Active subscriptions
            {confirmed.length > 0 && (
              <span style={{ fontSize: "12px", fontWeight: 400, color: "var(--muted)", marginLeft: "8px" }}>
                ({confirmed.length})
              </span>
            )}
          </h3>
          <button
            style={{ ...BTN_STYLE, color: "var(--accent)", fontSize: "13px" }}
            onClick={() => setShowCreateForm(v => !v)}
          >
            {showCreateForm ? "Cancel" : "+ Add subscription"}
          </button>
        </div>

        {confirmed.length === 0 && !showCreateForm ? (
          <p style={{ color: "var(--muted)", fontSize: "13px" }}>
            No confirmed active subscriptions yet.
          </p>
        ) : (
          <SectionTable
            rows={confirmed}
            editingId={editingId}
            onEdit={setEditingId}
            onSave={handleSave}
            onCancel={() => setEditingId(null)}
            onDelete={handleDelete}
            showCreateForm={showCreateForm}
            onSaveCreate={handleCreate}
            onCancelCreate={() => setShowCreateForm(false)}
          />
        )}
      </div>

      {/* ── Candidates / Unconfirmed ── */}
      {candidates.length > 0 && (
        <div>
          <div
            style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "8px", cursor: "pointer" }}
            onClick={() => setShowCandidates(v => !v)}
          >
            <h3 style={{ margin: 0, fontSize: "15px", fontWeight: 600 }}>
              Unconfirmed candidates
              <span style={{ fontSize: "12px", fontWeight: 400, color: "var(--muted)", marginLeft: "8px" }}>
                ({candidates.length})
              </span>
            </h3>
            <span style={{ color: "var(--muted)", fontSize: "12px" }}>{showCandidates ? "▲" : "▼"}</span>
          </div>
          {showCandidates && (
            <>
              <p style={{ fontSize: "12px", color: "var(--muted)", margin: "0 0 8px" }}>
                Detected but amount or cycle is uncertain. Edit to confirm or delete to remove.
              </p>
              <SectionTable
                rows={candidates}
                editingId={editingId}
                onEdit={setEditingId}
                onSave={handleSave}
                onCancel={() => setEditingId(null)}
                onDelete={handleDelete}
              />
            </>
          )}
        </div>
      )}

      {/* ── Cancelled ── */}
      {others.length > 0 && (
        <details style={{ opacity: 0.6 }}>
          <summary style={{ cursor: "pointer", fontSize: "13px", color: "var(--muted)", marginBottom: "8px" }}>
            Cancelled ({others.length})
          </summary>
          <SectionTable
            rows={others}
            editingId={editingId}
            onEdit={setEditingId}
            onSave={handleSave}
            onCancel={() => setEditingId(null)}
            onDelete={handleDelete}
          />
        </details>
      )}
    </div>
  );
}
