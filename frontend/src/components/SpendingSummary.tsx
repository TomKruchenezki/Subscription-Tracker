"use client";
import type { Summary } from "@/types/api";

interface Props {
  summary: Summary;
  onScan: () => void;
  scanning: boolean;
}

export function SpendingSummary({ summary, onScan, scanning }: Props) {
  return (
    <div style={{ display: "flex", gap: "16px", marginBottom: "24px", flexWrap: "wrap" }}>
      <StatCard
        label="Est. monthly cost"
        value={`$${summary.total_monthly_cost.toFixed(2)}`}
        color="var(--accent)"
      />
      <StatCard label="Active subscriptions" value={summary.active_count.toString()} />
      <StatCard label="Emails detected" value={summary.detected_count.toString()} />
      <StatCard label="Flagged for review" value={summary.flagged_count.toString()} color={summary.flagged_count > 0 ? "var(--yellow)" : undefined} />
      <div style={{ marginLeft: "auto", display: "flex", alignItems: "center" }}>
        <button className="primary" onClick={onScan} disabled={scanning}>
          {scanning ? "Scanning…" : "Run scan"}
        </button>
      </div>
    </div>
  );
}

function StatCard({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div style={{
      background: "var(--surface)",
      border: "1px solid var(--border)",
      borderRadius: "8px",
      padding: "16px 20px",
      minWidth: "140px",
    }}>
      <div style={{ fontSize: "11px", color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: "4px" }}>{label}</div>
      <div style={{ fontSize: "22px", fontWeight: 600, color: color ?? "var(--text)" }}>{value}</div>
    </div>
  );
}
