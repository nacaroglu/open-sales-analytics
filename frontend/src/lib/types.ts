// Response shapes of the backend API. Keys stay snake_case, as sent.
// Money is a string with 4 decimals, dates are YYYY-MM-DD, timestamps are UTC
// strings like 2026-09-30T12:19:11Z.

export interface Meta {
  id: string;
  currency: string;
  created_at: string;
  expires_at: string;
  row_count: number;
  date_range: { min: string; max: string };
  capabilities?: Capabilities;
}

export type AvailabilityState =
  | "available"
  | "unavailable"
  | "insufficient_data"
  | "low_coverage"
  | "zero_result";

export interface CapabilityAvailability {
  state: AvailabilityState;
  reason: string | null;
}

export interface Capabilities {
  columns: { customer_id: boolean };
  counts: { orders: number; products: number; line_items: number; history_days: number };
  modules: {
    overview: CapabilityAvailability;
    products: CapabilityAvailability;
    customers: CapabilityAvailability;
  };
  comparisons: {
    previous_period: CapabilityAvailability;
    previous_year: CapabilityAvailability;
  };
}

export interface Issue {
  code: string;
  reason: string;
  row_number: number | null;
  field: string | null;
}

export type Granularity = "daily" | "weekly" | "monthly";

export interface Summary {
  range: { start: string; end: string };
  currency: string;
  granularity: Granularity;
  kpis: {
    gross_sales: string;
    orders: number;
    units_sold: number;
    average_order_value: string;
  };
  trend: { bucket_start: string; gross_sales: string }[];
  top_products: {
    product_id: string;
    product_name: string;
    gross_sales: string;
    units_sold: number;
    distinct_orders: number;
  }[];
}
export interface Overview extends Omit<Summary, "kpis" | "trend"> {
  comparison: Comparison;
  kpis: { gross_sales: ComparedMoney; orders: ComparedCount; units_sold: ComparedCount; average_order_value: ComparedMoney };
  trend: { bucket_start: string; gross_sales: string }[];
  comparison_trend: { bucket_start: string; gross_sales: string }[] | null;
}

export interface Availability { state: AvailabilityState; reason: string | null }
export interface ComparisonDates { start: string; end: string }
export interface Comparison { mode: "previous_period" | "previous_year"; current: ComparisonDates; comparison: ComparisonDates; state: AvailabilityState; reason: string | null }
export interface ComparedMoney { value: string; comparison_value: string | null; absolute_change: string | null; percent_change: string | null; change_status: string | null }
export interface ComparedCount { value: number; comparison_value: number | null; absolute_change: number | null; percent_change: string | null; change_status: string | null }
export interface ProductRow { product_id: string; product_name: string; gross_sales: string; units_sold: number; distinct_orders: number }
export interface ProductsResponse {
  range: { start: string; end: string }; currency: string; granularity: Granularity; comparison: Comparison; product_count: number; availability: Availability;
  rankings: { availability: Availability; by_gross_sales: ProductRow[]; by_units_sold: ProductRow[]; by_orders: ProductRow[] };
  share: { products: { product_id: string; product_name: string; gross_sales: string; gross_sales_share: string | null; cumulative_share: string | null }[]; product_count: number; total_gross_sales: string; top_20_percent_product_count: number | null; top_20_percent_share: string | null; products_to_80_percent: number | null; availability: Availability };
  growth: { availability: Availability; products: GrowthProduct[]; rising: GrowthProduct[]; falling: GrowthProduct[] };
  dormant: { window_days: number; anchor_date: string; availability: Availability; products: DormantProduct[] };
  penetration: { all_orders: number; availability: Availability; products: PenetrationProduct[] };
  basket: BasketResponse;
}
export interface GrowthProduct { product_id: string; product_name: string; gross_sales: ComparedMoney; units_sold: ComparedCount; orders: ComparedCount; classification: "new" | "no_current_sales" | "rising" | "falling" | "unchanged" | null }
export interface DormantProduct { product_id: string; product_name: string; last_sale_date: string; days_inactive: number; earlier_gross_sales: string; earlier_orders: number }
export interface PenetrationProduct { product_id: string; product_name: string; orders_containing_product: number; all_orders: number; order_penetration: string | null }
export interface BasketPair { product_a: { product_id: string; product_name: string }; product_b: { product_id: string; product_name: string }; shared_orders: number; support: string; confidence_a_to_b: string; confidence_b_to_a: string; lift: string }
export interface BasketResponse { basket_orders: number; excluded_oversize_orders: number; max_distinct_products_per_order: number; min_shared_orders: number; min_support: string; eligible_pair_count: number; availability: Availability; pairs: BasketPair[] }
export interface ProductDetail { range: { start: string; end: string }; currency: string; granularity: Granularity; comparison: Comparison; product: { product_id: string; product_name: string }; kpis: { gross_sales: ComparedMoney; units_sold: ComparedCount; orders: ComparedCount }; trend: { bucket_start: string; gross_sales: string }[]; price_history: { granularity: Granularity; availability: Availability; buckets: { bucket_start: string; weighted_unit_price: string | null; units_sold: number }[] }; penetration: { orders_containing_product: number; all_orders: number; order_penetration: string | null; availability: Availability }; related_products: { excluded_oversize_orders: number; availability: Availability; related_products: { product: { product_id: string; product_name: string }; shared_orders: number; support: string; confidence_from_x: string; confidence_to_x: string; lift: string }[] }; availability: Availability }

export interface Created {
  dataset_id: string;
  token: string;
  meta: Meta;
  warnings: Issue[];
  initial_summary: Summary;
}

export interface PublicConfig {
  public_demo_mode: boolean;
  max_upload_bytes: number;
  max_rows: number;
}

export interface Health {
  status: string;
}

export interface CustomerCoverageValue {
  tier: "missing" | "suppressed" | "warning" | "normal";
  coverage: number | null;
  identified_orders: number;
  unidentified_orders: number;
  total_orders: number;
}

export interface CustomerResponse {
  module: "customers";
  range: { start: string; end: string };
  comparison: Comparison;
  currency: string;
  availability: Availability & { tier: CustomerCoverageValue["tier"]; warning?: Availability | null };
  coverage: { dataset: CustomerCoverageValue; range: CustomerCoverageValue };
  projected_12_month_customer_value: Projected12MonthCustomerValue;
  sections: Record<string, unknown>;
}

export interface ProjectionEligibilityCondition {
  code: string;
  label: string;
  actual: number | string | null;
  threshold: number | string;
  passed: boolean;
}

export interface ProjectedCustomerValueCohort {
  cohort_month: string;
  customers: number;
  observed_age_months: number;
  mature: boolean;
  observed_per_customer: string;
  projected_per_customer_estimate: string;
  total_per_customer_estimate: string;
}

export interface ProjectedCustomerValue {
  customers: number;
  contributing_mature_cohorts: number;
  observed_per_customer: string;
  projected_per_customer_estimate: string;
  total_per_customer_estimate: string;
  cohorts: ProjectedCustomerValueCohort[];
}

export interface Projected12MonthCustomerValue {
  is_estimate: boolean;
  horizon_months: number;
  data_cutoff: string;
  eligibility: {
    status: "eligible" | "ineligible" | "unavailable";
    data_cutoff: string;
    conditions: ProjectionEligibilityCondition[];
  };
  value: ProjectedCustomerValue | null;
}
