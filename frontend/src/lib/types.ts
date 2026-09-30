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
