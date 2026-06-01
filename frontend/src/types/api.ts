export type BillingCycle = "MONTHLY" | "ANNUAL" | "QUARTERLY" | "WEEKLY" | "UNKNOWN";
export type Category = "STREAMING" | "SAAS" | "NEWS" | "CLOUD" | "OTHER";
export type SubscriptionStatus = "ACTIVE" | "CANCELLED" | "PAUSED" | "TRIAL" | "UNKNOWN";
export type Disposition = "DETECTED" | "FLAGGED" | "IGNORED";
export type SourceProvider = "MOCK" | "GMAIL" | "MICROSOFT" | "IMAP" | "UNKNOWN";

export interface Subscription {
  subscription_id: string;
  name: string;
  service_url: string | null;
  amount: number | null;
  currency: string;
  billing_cycle: BillingCycle;
  next_renewal: string | null;
  category: Category;
  status: SubscriptionStatus;
  first_seen: string;
  last_seen: string;
  source_provider: SourceProvider;
  first_charge_date: string | null;
  last_charge_date: string | null;
  cancelled_at: string | null;
  trial_ends_at: string | null;
  // Phase 3.6: detection quality + account visibility
  detection_state: string | null;
  account_alias: string | null;
  // Phase 3.8: multi-account — all contributing account aliases
  account_aliases?: string[];
}

export interface EmailRecord {
  record_id: string;
  subscription_id: string | null;
  source_provider: SourceProvider;
  source_account_id: string;
  source_account_email: string;
  sender_address: string;
  sender_name: string | null;
  subject: string;
  email_date: string;
  amount_extracted: number | null;
  currency_extracted: string | null;
  confidence_score: number;
  disposition: Disposition;
  event_type: string | null;
  billing_period_start: string | null;
  billing_period_end: string | null;
  short_evidence: string | null;
  user_dismissed: 0 | 1;          // Phase 3.5: 1 if user dismissed from Review Queue
  // Phase 3.6: explanation fields (structured summaries, no raw email content)
  decision_reason: string | null;
  evidence_summary: string | null;
  missing_evidence: string | null;
  suggested_action: string | null;
  detection_state: string | null;
  account_alias: string | null;   // 8-char SHA-256 prefix — privacy-safe account identifier
  has_attachment?: boolean;       // Phase 3.7: record has ≥1 attachment (see /attachments)
  // Phase 3.8: processor/merchant separation + cycle confidence
  sender_domain: string | null;
  payment_processor: string | null;       // canonical processor name, e.g. "Cardcom"
  merchant_name_candidate: string | null; // structured candidate — never raw body text
  is_processor_email: 0 | 1;             // 1 if sender is a known payment processor
  gmail_account_id: string | null;
  cycle_source: string | null;
  cycle_confidence: string | null;        // STRONG | WEAK | NONE
}

// Phase 3.7: structured PDF-derived evidence (no raw PDF text — never stored)
export interface AttachmentFields {
  provider: string | null;
  product_name: string | null;
  amount: number | null;
  currency: string | null;
  invoice_date: string | null;
  payment_date: string | null;
  billing_period_start: string | null;
  billing_period_end: string | null;
  inferred_cycle: string | null;
  tax_amount: number | null;
  invoice_number: string | null;
  subscription_indicators: string | null;
  evidence_reasons: string | null;
  missing_evidence: string | null;
  penalty_reasons: string | null;
  confidence_score: number;
  extraction_status: string | null;
}

export interface Attachment {
  attachment_row_id: string;
  filename: string | null;
  mime_type: string | null;
  size_bytes: number | null;
  detected_attachment_type: string | null;
  processing_status: string;       // PENDING | PARSED | PARSE_FAILED | UNSUPPORTED | SKIPPED
  extracted_fields: AttachmentFields | null;
}

// Phase 3.5: User corrections audit trail
export interface UserCorrection {
  correction_id: string;
  email_record_id: string | null;
  subscription_id: string | null;
  correction_type: "DISMISSED_EMAIL" | "CONFIRMED_SUB" | "REJECTED_SUB" | "RELABELED";
  new_value: string | null;
  created_at: string;
}

export interface ConnectedAccount {
  account_id: string;
  source_provider: SourceProvider;
  account_email: string;
  display_name: string | null;
  is_active: boolean;
}

export type ScanMode = "quick" | "deep" | "forensic";
export type ScanRange = "1m" | "3m" | "6m" | "1y" | "2y" | "5y" | "custom";

export interface ScanRequest {
  mode?: ScanMode;
  scan_range?: ScanRange;
  date_from?: string;
  date_to?: string;
}

export interface ScanResult {
  scanned: number;
  detected: number;
  flagged: number;
  ignored: number;
  content_access_level?: string;
}

export interface Summary {
  total_monthly_cost: number;
  currency: string;
  active_count: number;
  detected_count: number;
  flagged_count: number;
  unconfirmed_count: number;  // Phase 3.4: count of UNKNOWN-status subscriptions
  has_mock_data?: boolean;  // present in Gmail mode; true when MOCK rows exist but are excluded
  monthly_costs_by_currency?: Record<string, number>;  // Phase 3.3: per-currency monthly totals
}

export interface PaymentEvent {
  event_id: string;
  event_type: string;
  merchant_name: string;
  amount: number | null;
  currency: string | null;
  event_date: string;
  is_recurring_candidate: 0 | 1;
  is_one_time_candidate: 0 | 1;
  needs_attachment_review: 0 | 1;   // Phase 3.4: amount is in an attachment (PDF)
  subscription_id: string | null;
  confidence_score: number;
  source_provider: string;
  source_message_id: string;
  created_at: string;
  // Phase 3.6: explanation + correction flags
  decision_reason: string | null;
  user_marked_one_time: 0 | 1;
  account_alias: string | null;
}

// Phase 3.4: Manual CRUD request bodies
export interface CreateSubscriptionRequest {
  name: string;
  amount?: number | null;
  currency?: string;
  billing_cycle?: string;
  category?: string;
  status?: string;
  service_url?: string | null;
}

export interface UpdateSubscriptionRequest {
  name?: string | null;
  amount?: number | null;
  currency?: string | null;
  billing_cycle?: string | null;
  status?: string | null;
  category?: string | null;
  service_url?: string | null;
}

export interface ScanJobStatus {
  scan_id: string;
  mode: string;
  scan_range: string | null;
  content_access_level: string;
  status: "pending" | "collecting" | "processing" | "completed" | "failed" | "interrupted";
  total_ids: number;
  processed_count: number;
  detected_count: number;
  flagged_count: number;
  ignored_count: number;
  body_fetched_count: number;
  body_skipped_count: number;
  body_failed_count: number;
  error_message: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  last_activity_at: string | null;
}
