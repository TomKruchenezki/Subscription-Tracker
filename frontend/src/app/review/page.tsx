"use client";
import { useEffect, useState, useCallback } from "react";
import { api } from "@/lib/api";
import { ReviewQueue } from "@/components/ReviewQueue";
import type { EmailRecord } from "@/types/api";

export default function ReviewPage() {
  const [records, setRecords] = useState<EmailRecord[]>([]);
  const [error, setError] = useState<string | null>(null);

  const loadRecords = useCallback(() => {
    api.emailRecords("FLAGGED")
      .then(setRecords)
      .catch(() => setError("Cannot reach the API server. Make sure `python main.py --mock` is running."));
  }, []);

  useEffect(() => { loadRecords(); }, [loadRecords]);

  return (
    <>
      <div style={{ marginBottom: "16px" }}>
        <h1 style={{ margin: "0 0 4px", fontSize: "20px" }}>Review Queue</h1>
        <p style={{ margin: 0, color: "var(--muted)" }}>
          Emails the detector flagged as possible subscriptions but couldn&#39;t confirm automatically.
          Use ✓ Confirm to add as a subscription, or ✕ Dismiss to hide from view.
        </p>
      </div>

      {error && (
        <div style={{ background: "#450a0a", border: "1px solid var(--red)", borderRadius: "8px", padding: "12px 16px", marginBottom: "16px", color: "var(--red)" }}>
          {error}
        </div>
      )}

      <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "8px", padding: "16px", overflow: "hidden" }}>
        <ReviewQueue records={records} onRefresh={loadRecords} />
      </div>
    </>
  );
}
