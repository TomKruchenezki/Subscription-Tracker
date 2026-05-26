"use client";
import { useEffect, useState, useCallback } from "react";
import { api } from "@/lib/api";
import { SpendingSummary } from "@/components/SpendingSummary";
import { SubscriptionTable } from "@/components/SubscriptionTable";
import type { Subscription, Summary } from "@/types/api";

export default function DashboardPage() {
  const [subscriptions, setSubscriptions] = useState<Subscription[]>([]);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [scanning, setScanning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<string>("…");

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
    } catch (e) {
      setError("Cannot reach the API server. Make sure `python main.py --mock` is running.");
    }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  const handleScan = async () => {
    setScanning(true);
    try {
      await api.scan();
      await loadData();
    } catch (e) {
      setError("Scan failed. Check that the API server is running.");
    } finally {
      setScanning(false);
    }
  };

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

      {summary && (
        <SpendingSummary summary={summary} onScan={handleScan} scanning={scanning} />
      )}

      <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "8px", overflow: "hidden" }}>
        <SubscriptionTable subscriptions={subscriptions} />
      </div>
    </>
  );
}
