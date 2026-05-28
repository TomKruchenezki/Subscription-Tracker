"use client";
import { useEffect, useState, useCallback, useRef } from "react";
import { api } from "@/lib/api";
import { SpendingSummary } from "@/components/SpendingSummary";
import { SubscriptionTable } from "@/components/SubscriptionTable";
import { PaymentEventsTable } from "@/components/PaymentEventsTable";
import type { Subscription, Summary, ScanMode, ScanRange, ScanResult, ScanJobStatus, PaymentEvent } from "@/types/api";

interface LastScan extends ScanResult {
  mode: ScanMode;
  scan_range: ScanRange | string;
}

export default function DashboardPage() {
  const [subscriptions, setSubscriptions] = useState<Subscription[]>([]);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [paymentEvents, setPaymentEvents] = useState<PaymentEvent[]>([]);
  const [scanning, setScanning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<string>("…");

  // Scan controls — default to smallest/safest range
  const [scanMode, setScanMode] = useState<ScanMode>("quick");
  const [scanRange, setScanRange] = useState<ScanRange>("1m");
  const [lastScan, setLastScan] = useState<LastScan | null>(null);

  // Phase 3.4: custom date range
  const today = new Date().toISOString().slice(0, 10);
  const [customDateFrom, setCustomDateFrom] = useState<string>(() => {
    const d = new Date();
    d.setFullYear(d.getFullYear() - 1);
    return d.toISOString().slice(0, 10);
  });
  const [customDateTo, setCustomDateTo] = useState<string>(today);

  // Background scan progress (forensic mode only)
  const [scanProgress, setScanProgress] = useState<ScanJobStatus | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const loadData = useCallback(async () => {
    try {
      const [subs, sum, health, events] = await Promise.all([
        api.subscriptions(),
        api.summary(),
        api.health(),
        api.paymentEvents(),
      ]);
      setSubscriptions(subs);
      setSummary(sum);
      setMode(health.mode);
      setPaymentEvents(events);
      setError(null);
    } catch {
      setError("Cannot reach the API server. Make sure `python main.py` is running.");
    }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  // Clean up polling on unmount
  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  const stopPolling = () => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  };

  const handleScan = async () => {
    setScanning(true);
    setScanProgress(null);
    setError(null);

    try {
      const scanRequest = scanRange === "custom"
        ? { mode: scanMode, date_from: customDateFrom, date_to: customDateTo }
        : { mode: scanMode, scan_range: scanRange };

      if (scanMode === "forensic") {
        // ── Background scan: start + poll ──────────────────────────────────
        const job = await api.scanStart(scanRequest);
        setScanProgress(job);

        pollRef.current = setInterval(async () => {
          try {
            const status = await api.scanStatus(job.scan_id);
            setScanProgress(status);

            if (["completed", "failed", "interrupted"].includes(status.status)) {
              stopPolling();
              setScanning(false);

              if (status.status === "completed") {
                setLastScan({
                  scanned: status.processed_count,
                  detected: status.detected_count,
                  flagged: status.flagged_count,
                  ignored: status.ignored_count,
                  mode: scanMode,
                  scan_range: scanRange === "custom" ? "custom" : scanRange,
                });
                await loadData();
              } else {
                setError(
                  status.error_message
                    ? `Scan ${status.status}: ${status.error_message}`
                    : `Scan ${status.status}. Safe to re-run.`
                );
              }
            }
          } catch {
            // Polling error — don't stop, will retry next interval
          }
        }, 3000);

      } else {
        // ── Synchronous scan: quick / deep ─────────────────────────────────
        const result = await api.scan(scanRequest);
        setLastScan({ ...result, mode: scanMode, scan_range: scanRange === "custom" ? "custom" : scanRange });
        await loadData();
        setScanning(false);
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : "";
      if (msg.includes("409")) {
        setError(
          "No Gmail account connected. Visit the Accounts page to connect Gmail first."
        );
      } else if (msg.includes("400")) {
        setError("Background scan requires Gmail mode (USE_MOCK=false).");
      } else {
        setError("Scan failed. Check that the API server is running.");
      }
      setScanning(false);
    }
  };

  // Gmail mode: endpoints auto-filter to GMAIL rows; has_mock_data=true means MOCK rows exist
  // but are hidden (not mixed). Mock mode: show warning if GMAIL rows are present.
  const isGmailMode = mode === "GMAIL";
  const hasMockRows = isGmailMode && (summary?.has_mock_data ?? false);
  const hasMockInMockMode = !isGmailMode && subscriptions.some((s) => s.source_provider === "GMAIL");

  return (
    <>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
        <h1 style={{ margin: 0, fontSize: "20px" }}>Subscriptions</h1>
        <span className={`badge badge-${mode.toLowerCase()}`}>{mode} mode</span>
      </div>

      {error && (
        <div style={{ background: "#450a0a", border: "1px solid var(--red)", borderRadius: "8px", padding: "12px 16px", marginBottom: "16px", color: "var(--red)" }}>
          {error}
        </div>
      )}

      {hasMockRows && (
        <div style={{ background: "#422006", border: "1px solid var(--yellow)", borderRadius: "8px", padding: "12px 16px", marginBottom: "16px", color: "var(--yellow)", fontSize: "14px" }}>
          MOCK rows exist in the local DB but are <strong>excluded</strong> from Gmail mode results.
          Run <code>python scripts/cleanup_mock_rows.py</code> to remove them permanently.
        </div>
      )}

      {hasMockInMockMode && (
        <div style={{ background: "#422006", border: "1px solid var(--yellow)", borderRadius: "8px", padding: "12px 16px", marginBottom: "16px", color: "var(--yellow)", fontSize: "14px" }}>
          GMAIL rows exist in the DB but you are in <strong>MOCK mode</strong> (<code>USE_MOCK=true</code>). Set <code>USE_MOCK=false</code> to see Gmail data.
        </div>
      )}

      {summary && (
        <SpendingSummary
          summary={summary}
          onScan={handleScan}
          scanning={scanning}
          scanMode={scanMode}
          onScanModeChange={setScanMode}
          scanRange={scanRange}
          onScanRangeChange={setScanRange}
          customDateFrom={customDateFrom}
          customDateTo={customDateTo}
          onCustomDateFromChange={setCustomDateFrom}
          onCustomDateToChange={setCustomDateTo}
          scanProgress={scanProgress}
        />
      )}

      {lastScan && (
        <div style={{
          background: "var(--surface)",
          border: "1px solid var(--border)",
          borderRadius: "8px",
          padding: "10px 16px",
          marginBottom: "16px",
          fontSize: "13px",
          color: "var(--muted)",
          display: "flex",
          gap: "8px",
          alignItems: "center",
          flexWrap: "wrap",
        }}>
          <span style={{ color: "var(--text)", fontWeight: 500 }}>Last scan:</span>
          <span className={`badge badge-${lastScan.mode}`}>{lastScan.mode}</span>
          <span>{lastScan.scan_range}</span>
          <span>·</span>
          <span>{lastScan.scanned} scanned</span>
          <span>·</span>
          <span style={{ color: "var(--green)" }}>{lastScan.detected} detected</span>
          <span>·</span>
          <span style={{ color: lastScan.flagged > 0 ? "var(--yellow)" : "var(--muted)" }}>
            {lastScan.flagged} flagged for review
          </span>
          <span>·</span>
          <span>{lastScan.ignored} ignored</span>
        </div>
      )}

      <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "8px", padding: "16px", overflow: "hidden" }}>
        <SubscriptionTable subscriptions={subscriptions} onRefresh={loadData} />
      </div>

      {/* Payment Events — financial event log (Phase 3.3B) */}
      <div style={{ marginTop: "24px" }}>
        <h2 style={{ fontSize: "16px", fontWeight: 600, marginBottom: "12px", color: "var(--text)" }}>
          Payment Events
          {paymentEvents.length > 0 && (
            <span style={{ marginLeft: "8px", fontSize: "13px", fontWeight: 400, color: "var(--muted)" }}>
              ({paymentEvents.length})
            </span>
          )}
        </h2>
        <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "8px", overflow: "hidden", padding: "16px" }}>
          <PaymentEventsTable events={paymentEvents} onRefresh={loadData} />
        </div>
      </div>
    </>
  );
}
