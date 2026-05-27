"use client";
import { useEffect, useState, useCallback, useRef } from "react";
import { api } from "@/lib/api";
import { SpendingSummary } from "@/components/SpendingSummary";
import { SubscriptionTable } from "@/components/SubscriptionTable";
import type { Subscription, Summary, ScanMode, ScanRange, ScanResult, ScanJobStatus } from "@/types/api";

interface LastScan extends ScanResult {
  mode: ScanMode;
  scan_range: ScanRange;
}

export default function DashboardPage() {
  const [subscriptions, setSubscriptions] = useState<Subscription[]>([]);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [scanning, setScanning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<string>("…");

  // Scan controls — default to smallest/safest range
  const [scanMode, setScanMode] = useState<ScanMode>("quick");
  const [scanRange, setScanRange] = useState<ScanRange>("1m");
  const [lastScan, setLastScan] = useState<LastScan | null>(null);

  // Background scan progress (forensic mode only)
  const [scanProgress, setScanProgress] = useState<ScanJobStatus | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const loadData = useCallback(async () => {
    try {
      const [subs, sum, health] = await Promise.all([
        api.subscriptions(),
        api.summary(),
        api.health(),
      ]);
      setSubscriptions(subs);
      setSummary(sum);
      setMode(health.mode);
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
      if (scanMode === "forensic") {
        // ── Background scan: start + poll ──────────────────────────────────
        const job = await api.scanStart({ mode: scanMode, scan_range: scanRange });
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
                  scan_range: scanRange,
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
        const result = await api.scan({ mode: scanMode, scan_range: scanRange });
        setLastScan({ ...result, mode: scanMode, scan_range: scanRange });
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

  // Detect mixed MOCK + GMAIL data
  const hasMock = subscriptions.some((s) => s.source_provider === "MOCK");
  const hasGmail = subscriptions.some((s) => s.source_provider === "GMAIL");
  const mixedSources = hasMock && hasGmail;

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

      {mixedSources && (
        <div style={{ background: "#422006", border: "1px solid var(--yellow)", borderRadius: "8px", padding: "12px 16px", marginBottom: "16px", color: "var(--yellow)", fontSize: "14px" }}>
          Showing mixed <strong>MOCK</strong> + <strong>GMAIL</strong> data. Run a scan in Gmail mode to replace mock rows, or restart with <code>USE_MOCK=false</code> and clear the database.
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

      <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "8px", overflow: "hidden" }}>
        <SubscriptionTable subscriptions={subscriptions} />
      </div>
    </>
  );
}
