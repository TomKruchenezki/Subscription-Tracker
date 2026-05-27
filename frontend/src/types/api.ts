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
}

export interface ConnectedAccount {
  account_id: string;
  source_provider: SourceProvider;
  account_email: string;
  display_name: string | null;
  is_active: boolean;
}

export type ScanMode = "quick" | "deep" | "forensic";
export type ScanRange = "1m" | "3m" | "6m" | "1y" | "2y" | "5y";

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
  has_mock_data?: boolean;  // present in Gmail mode; true when MOCK rows exist but are excluded
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
