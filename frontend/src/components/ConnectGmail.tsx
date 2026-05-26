"use client";
import { useState } from "react";
import { api } from "@/lib/api";

interface Props {
  onConnected?: () => void;
}

export function ConnectGmail({ onConnected }: Props) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleConnect = async () => {
    setLoading(true);
    setError(null);
    try {
      const { auth_url } = await api.gmailAuthUrl();
      // Redirect the browser to Google's consent screen.
      // Google will redirect back to the FastAPI callback (/api/oauth/callback),
      // which then redirects to this page with ?connected=true.
      window.location.href = auth_url;
    } catch (e) {
      setError(
        "Could not start Gmail connection. Make sure the API server is running and " +
        "GOOGLE_OAUTH_CLIENT_ID / CLIENT_SECRET are set in .env."
      );
      setLoading(false);
    }
  };

  return (
    <div>
      {error && (
        <div style={{
          background: "#450a0a",
          border: "1px solid var(--red)",
          borderRadius: "8px",
          padding: "12px 16px",
          marginBottom: "16px",
          color: "var(--red)",
          fontSize: "14px",
        }}>
          {error}
        </div>
      )}
      <button
        onClick={handleConnect}
        disabled={loading}
        style={{ opacity: loading ? 0.6 : 1 }}
      >
        {loading ? "Redirecting to Google…" : "Connect Gmail"}
      </button>
      <p style={{ color: "var(--muted)", fontSize: "12px", marginTop: "8px" }}>
        Read-only access · Gmail metadata only · No email bodies stored
      </p>
    </div>
  );
}
