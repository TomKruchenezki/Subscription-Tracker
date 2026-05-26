"use client";
import type { EmailRecord } from "@/types/api";

interface Props {
  records: EmailRecord[];
}

export function ReviewQueue({ records }: Props) {
  if (records.length === 0) {
    return <p style={{ color: "var(--muted)" }}>No flagged records — inbox looks clean.</p>;
  }

  return (
    <table>
      <thead>
        <tr>
          <th>Sender</th>
          <th>Subject</th>
          <th>Date</th>
          <th>Amount</th>
          <th>Confidence</th>
        </tr>
      </thead>
      <tbody>
        {records.map((record) => (
          <tr key={record.record_id}>
            <td style={{ color: "var(--muted)", fontSize: "12px" }}>{record.sender_address}</td>
            <td>{record.subject}</td>
            <td style={{ color: "var(--muted)", whiteSpace: "nowrap" }}>
              {new Date(record.email_date).toLocaleDateString()}
            </td>
            <td>
              {record.amount_extracted != null
                ? `${record.currency_extracted ?? ""}$${record.amount_extracted}`
                : "—"}
            </td>
            <td>
              <span style={{
                color: record.confidence_score >= 0.6 ? "var(--yellow)" : "var(--muted)",
                fontVariantNumeric: "tabular-nums",
              }}>
                {(record.confidence_score * 100).toFixed(0)}%
              </span>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
