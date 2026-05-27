"use client";
import type { Summary, ScanMode, ScanRange } from "@/types/api";

interface Props {
  summary: Summary;
  onScan: () => void;
  scanning: boolean;
  scanMode: ScanMode;
  onScanModeChange: (m: ScanMode) => void;
  scanRange: ScanRange;
  onScanRangeChange: (r: ScanRange) => void;
}

const SELECT_STYLE: React.CSSProperties = {
  background: "var(--surface)",
  border: "1px solid var(--border)",
  borderRadius: "6px",
  color: "var(--text)",
  padding: "5px 8px",
  fontSize: "13px",
  cursor: "pointer",
};

export function SpendingSummary({
  summary,
  onScan,
  scanning,
  scanMode,
  onScanModeChange,
  scanRange,
  onScanRangeChange,
}: Props) {
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

      <div style={{ marginLeft: "auto", display: "flex", flexDirection: "column", alignItems: "flex-end", gap: "8px" }}>
        <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
          <select
            value={scanMode}
            onChange={(e) => onScanModeChange(e.target.value as ScanMode)}
            disabled={scanning}
            style={SELECT_STYLE}
            aria-label="Scan depth"
          >
            <option value="quick">quick</option>
            <option value="deep">deep</option>
            <option value="forensic">forensic</option>
          </select>
          <select
            value={scanRange}
            onChange={(e) => onScanRangeChange(e.target.value as ScanRange)}
            disabled={scanning}
            style={SELECT_STYLE}
            aria-label="Scan range"
          >
            <option value="1m">1 month</option>
            <option value="3m">3 months</option>
            <option value="6m">6 months</option>
            <option value="1y">1 year</option>
            <option value="2y">2 years</option>
            <option value="5y">5 years</option>
          </select>
          <button className="primary" onClick={onScan} disabled={scanning}>
            {scanning ? "Scanning…" : "Run scan"}
          </button>
        </div>
        <p style={{ fontSize: "11px", color: "var(--muted)", margin: 0, textAlign: "right" }}>
          Start with quick + 1m before scanning larger ranges.
        </p>
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
