"use client";
import { useEffect, useState, useCallback, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import { ConnectGmail } from "@/components/ConnectGmail";
import type { ConnectedAccount } from "@/types/api";

function AccountsContent() {
  const searchParams = useSearchParams();
  const connected = searchParams.get("connected");
  const oauthError = searchParams.get("oauth_error");

  const [accounts, setAccounts] = useState<ConnectedAccount[]>([]);
  const [loading, setLoading] = useState(true);
  const [disconnecting, setDisconnecting] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadAccounts = useCallback(async () => {
    try {
      const data = await api.accounts();
      setAccounts(data.filter((a) => a.source_provider !== "MOCK"));
      setError(null);
    } catch {
      setError("Could not load accounts. Make sure the API server is running.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadAccounts(); }, [loadAccounts]);

  const handleDisconnect = async (accountId: string) => {
    if (!confirm(`Disconnect ${accountId}? This will remove the stored Gmail token.`)) return;
    setDisconnecting(accountId);
    try {
      await api.disconnectAccount(accountId);
      await loadAccounts();
    } catch {
      setError("Failed to disconnect account.");
    } finally {
      setDisconnecting(null);
    }
  };

  const gmailAccounts = accounts.filter((a) => a.source_provider === "GMAIL" && a.is_active);

  return (
    <>
      <div style={{ marginBottom: "24px" }}>
        <h1 style={{ margin: 0, fontSize: "20px" }}>Connected Accounts</h1>
        <p style={{ color: "var(--muted)", fontSize: "14px", marginTop: "4px" }}>
          Gmail is connected read-only. Only sender, subject, and date are read — never email bodies.
        </p>
      </div>

      {connected === "true" && (
        <div style={{
          background: "#052e16",
          border: "1px solid var(--green)",
          borderRadius: "8px",
          padding: "12px 16px",
          marginBottom: "16px",
          color: "var(--green)",
        }}>
          Gmail connected successfully. Run a scan from the dashboard to detect subscriptions.
        </div>
      )}

      {oauthError && (
        <div style={{
          background: "#450a0a",
          border: "1px solid var(--red)",
          borderRadius: "8px",
          padding: "12px 16px",
          marginBottom: "16px",
          color: "var(--red)",
        }}>
          OAuth error: {oauthError.replace(/_/g, " ")}. Please try connecting again.
        </div>
      )}

      {error && (
        <div style={{
          background: "#450a0a",
          border: "1px solid var(--red)",
          borderRadius: "8px",
          padding: "12px 16px",
          marginBottom: "16px",
          color: "var(--red)",
        }}>
          {error}
        </div>
      )}

      {/* Connected accounts list */}
      {!loading && gmailAccounts.length > 0 && (
        <div style={{
          background: "var(--surface)",
          border: "1px solid var(--border)",
          borderRadius: "8px",
          marginBottom: "24px",
          overflow: "hidden",
        }}>
          <table>
            <thead>
              <tr>
                <th>Email</th>
                <th>Provider</th>
                <th>Status</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {gmailAccounts.map((account) => (
                <tr key={account.account_id}>
                  <td style={{ fontWeight: 500 }}>{account.account_email}</td>
                  <td>
                    <span className={`badge badge-${account.source_provider.toLowerCase()}`}>
                      {account.source_provider}
                    </span>
                  </td>
                  <td>
                    <span className={`badge badge-${account.is_active ? "active" : "cancelled"}`}>
                      {account.is_active ? "Connected" : "Disconnected"}
                    </span>
                  </td>
                  <td>
                    <button
                      onClick={() => handleDisconnect(account.account_id)}
                      disabled={disconnecting === account.account_id}
                      style={{
                        background: "transparent",
                        border: "1px solid var(--red)",
                        color: "var(--red)",
                        padding: "4px 10px",
                        fontSize: "12px",
                        opacity: disconnecting === account.account_id ? 0.5 : 1,
                      }}
                    >
                      {disconnecting === account.account_id ? "Disconnecting…" : "Disconnect"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Connect new account */}
      {!loading && gmailAccounts.length === 0 && (
        <div style={{
          background: "var(--surface)",
          border: "1px solid var(--border)",
          borderRadius: "8px",
          padding: "24px",
          marginBottom: "24px",
        }}>
          <h2 style={{ fontSize: "16px", margin: "0 0 8px" }}>Connect Gmail</h2>
          <p style={{ color: "var(--muted)", fontSize: "14px", margin: "0 0 16px" }}>
            Connect your Gmail account to automatically detect subscription emails.
            Phase 2.1 supports one Gmail account.
          </p>
          <ConnectGmail onConnected={loadAccounts} />
        </div>
      )}

      {/* Already connected — offer to add another (Phase 2.2) */}
      {!loading && gmailAccounts.length > 0 && (
        <div style={{
          background: "var(--surface)",
          border: "1px solid var(--border)",
          borderRadius: "8px",
          padding: "24px",
        }}>
          <h2 style={{ fontSize: "16px", margin: "0 0 8px" }}>Connect another account</h2>
          <p style={{ color: "var(--muted)", fontSize: "14px", margin: "0 0 16px" }}>
            Multiple account support is planned for Phase 2.2.
          </p>
          <ConnectGmail onConnected={loadAccounts} />
        </div>
      )}
    </>
  );
}

export default function AccountsPage() {
  return (
    <Suspense fallback={<p style={{ color: "var(--muted)" }}>Loading…</p>}>
      <AccountsContent />
    </Suspense>
  );
}
