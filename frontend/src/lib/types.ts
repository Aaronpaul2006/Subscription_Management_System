export type Role = "ADMIN" | "STAFF" | "CUSTOMER";
export type Money = string;

export interface User {
  id: number;
  email: string;
  name: string;
  role: Role;
  phone: string;
  is_active: boolean;
  date_joined: string;
  customer_id: number | null;
}

export interface Choice {
  value: string;
  label: string;
}

export interface Meta {
  company: { name: string; address: string; email: string; tax_id: string; currency: string; currency_symbol: string };
  password_rules: string;
  choices: Record<string, Choice[]>;
}

export interface Customer {
  id: number;
  name: string;
  company: string;
  email: string;
  phone: string;
  address: string;
  city: string;
  state: string;
  country: string;
  tax_id: string;
  notes: string;
  has_portal_access: boolean;
  created_at: string;
  active_subscriptions?: number;
  outstanding?: Money;
}

export interface Tax {
  id: number;
  name: string;
  computation: "PERCENT" | "FIXED";
  amount: string;
  description: string;
  is_active: boolean;
}

export interface Variant {
  id?: number;
  attribute: string;
  value: string;
  extra_price: Money;
  price?: Money;
}

export interface Product {
  id: number;
  name: string;
  product_type: string;
  product_type_label: string;
  sales_price: Money;
  cost_price: Money;
  margin_percent: string | null;
  notes: string;
  taxes: number[];
  tax_names: string[];
  variants: Variant[];
  is_active: boolean;
}

export interface Plan {
  id: number;
  name: string;
  description: string;
  price: Money;
  billing_period: string;
  billing_period_label: string;
  billing_interval: number;
  billing_label: string;
  min_quantity: string;
  start_date: string;
  end_date: string | null;
  auto_close: boolean;
  closable: boolean;
  pausable: boolean;
  renewable: boolean;
  taxes: number[];
  is_active: boolean;
  is_available: boolean;
  active_subscriptions: number;
}

export interface PaymentTerm {
  id: number;
  name: string;
  due_days: number;
  is_active: boolean;
}

export interface TemplateLine {
  id?: number;
  product: number;
  product_name?: string;
  variant: number | null;
  variant_label?: string | null;
  quantity: string;
  description: string;
}

export interface QuotationTemplate {
  id: number;
  name: string;
  validity_days: number;
  plan: number;
  plan_name: string;
  payment_term: number | null;
  payment_term_name: string | null;
  duration_months: number | null;
  notes: string;
  is_active: boolean;
  lines: TemplateLine[];
}

export type SubStatus = "DRAFT" | "QUOTATION" | "CONFIRMED" | "ACTIVE" | "PAUSED" | "CLOSED";

export interface SubscriptionLine {
  id?: number;
  product: number | null;
  product_name?: string | null;
  variant: number | null;
  variant_label?: string | null;
  description: string;
  quantity: string;
  unit_price: Money | null;
  taxes?: number[];
  tax_names?: string[];
  subtotal?: Money;
  tax_amount?: Money;
  total?: Money;
}

export interface Subscription {
  id: number;
  number: string;
  customer: number;
  customer_name: string;
  plan: number;
  plan_name: string;
  billing_label: string;
  status: SubStatus;
  status_label: string;
  start_date: string;
  expiry_date: string | null;
  next_invoice_date: string | null;
  quotation_valid_until: string | null;
  quotation_expired: boolean;
  is_expired: boolean;
  untaxed_amount: Money;
  tax_amount: Money;
  total: Money;
  mrr: Money;
  created_at: string;
}

export interface SubscriptionDetail extends Subscription {
  customer_detail: { id: number; name: string; company: string; email: string };
  plan_detail: Pick<Plan, "id" | "name" | "price" | "billing_period" | "billing_interval" | "billing_label" | "min_quantity" | "auto_close" | "closable" | "pausable" | "renewable">;
  lines: SubscriptionLine[];
  payment_term: number | null;
  payment_term_name: string | null;
  template: number | null;
  template_name: string | null;
  salesperson: number | null;
  salesperson_name: string | null;
  notes?: string;
  terms: string;
  quotation_sent_at: string | null;
  confirmed_at: string | null;
  accepted_by_name: string;
  accepted_at: string | null;
  activated_at: string | null;
  paused_at: string | null;
  closed_at: string | null;
  close_reason: string;
  renewal_count: number;
  allowed_actions: string[];
}

export interface Discount {
  id: number;
  name: string;
  code: string;
  kind: "PERCENT" | "FIXED";
  value: Money;
  scope: "PRODUCTS" | "SUBSCRIPTION";
  products: number[];
  product_names: string[];
  subscriptions: number[];
  subscription_numbers: string[];
  min_purchase: Money | null;
  min_quantity: string | null;
  start_date: string | null;
  end_date: string | null;
  usage_limit: number | null;
  times_used: number;
  total_discounted: Money;
  is_active: boolean;
  state: "active" | "scheduled" | "expired" | "exhausted" | "inactive";
}

export type InvoiceStatus = "DRAFT" | "CONFIRMED" | "PAID" | "CANCELLED";

export interface Invoice {
  id: number;
  number: string | null;
  display_number: string;
  customer: number;
  customer_name: string;
  subscription: number | null;
  subscription_number: string | null;
  status: InvoiceStatus;
  status_label: string;
  invoice_date: string;
  due_date: string;
  period_start: string | null;
  period_end: string | null;
  untaxed_amount: Money;
  discount_amount: Money;
  tax_amount: Money;
  total: Money;
  amount_paid: Money;
  amount_due: Money;
  is_overdue: boolean;
  days_overdue: number;
  sent_at: string | null;
  reminder_count: number;
}

export interface InvoiceLine {
  id: number;
  product: number | null;
  description: string;
  quantity: string;
  unit_price: Money;
  gross_amount: Money;
  discount_amount: Money;
  subtotal: Money;
  tax_amount: Money;
  total: Money;
  taxes: { name: string; rate: string; computation: string; amount: Money }[];
}

export interface Payment {
  id: number;
  invoice: number;
  invoice_number: string;
  customer: number;
  customer_name: string;
  method: string;
  method_label: string;
  amount: Money;
  payment_date: string;
  reference: string;
  note: string;
  source: "MANUAL" | "PORTAL";
  recorded_by_name: string | null;
  created_at: string;
}

export interface InvoiceDetail extends Invoice {
  bill_to: Record<string, string>;
  payment_term: string;
  notes: string;
  lines: InvoiceLine[];
  applied_discounts: { id: number; discount: number; name: string; amount: Money }[];
  payments: Payment[];
  confirmed_at: string | null;
  paid_at: string | null;
  cancelled_at: string | null;
  cancel_reason: string;
  sent_count: number;
  last_reminder_at: string | null;
  billing_run: number | null;
  created_at: string;
  allowed_actions: string[];
}

export interface Activity {
  id: number;
  entity: string;
  entity_id: number;
  verb: string;
  message: string;
  actor_name: string | null;
  created_at: string;
}

export interface BillingRun {
  id: number;
  as_of: string;
  trigger: "MANUAL" | "SCHEDULED";
  triggered_by_name: string | null;
  auto_confirm: boolean;
  auto_send: boolean;
  subscriptions_processed: number;
  invoices_created: number;
  total_amount: Money;
  errors: { subscription_id?: number; invoice_id?: number; error: string }[];
  started_at: string;
  duration_ms: number;
}

export interface OutboundEmail {
  id: number;
  to: string;
  subject: string;
  body: string;
  html: string;
  attachments: string[];
  category: string;
  status: string;
  error: string;
  created_at: string;
}
