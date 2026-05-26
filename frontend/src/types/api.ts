export type BillingCycle = "MONTHLY" | "ANNUAL" | "WEEKLY" | "UNKNOWN";
export type Category = "STREAMING" | "SAAS" | "NEWS" | "CLOUD" | "OTHER";
export type SubscriptionStatus = "ACTIVE" | "CANCELLED" | "PAUSED";
export type Disposition = "DETECTED" | "FLAGGED" | "IGNORED";
export type Source = "MOCK" | "GMAIL";

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
  source: Source;
}

export interface EmailRecord {
  record_id: string;
  subscription_id: string | null;
  sender_address: string;
  sender_name: string | null;
  subject: string;
  email_date: string;
  amount_extracted: number | null;
  currency_extracted: string | null;
  confidence_score: number;
  disposition: Disposition;
}

export interface ScanResult {
  scanned: number;
  detected: number;
  flagged: number;
  ignored: number;
}

export interface Summary {
  total_monthly_cost: number;
  currency: string;
  active_count: number;
  detected_count: number;
  flagged_count: number;
}
