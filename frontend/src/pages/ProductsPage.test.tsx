import { afterEach, expect, test, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { ProductDetailView, ProductsView } from "./ProductsPage";
import type { ProductDetail, ProductsResponse } from "../lib/types";

const { useProducts, useProductDetail } = vi.hoisted(() => ({ useProducts: vi.fn(), useProductDetail: vi.fn() }));
vi.mock("../lib/hooks", async (importOriginal) => ({ ...(await importOriginal<typeof import("../lib/hooks")>()), useProducts, useProductDetail }));

const available = { state: "available" as const, reason: null };
const products: ProductsResponse = {
  range: { start: "2025-01-01", end: "2025-03-31" }, currency: "USD", granularity: "daily",
  comparison: { mode: "previous_period", current: { start: "2025-01-01", end: "2025-03-31" }, comparison: { start: "2024-10-03", end: "2024-12-31" }, state: "available", reason: null },
  product_count: 1, availability: available,
  rankings: { availability: available, by_gross_sales: [{ product_id: "a/b", product_name: "Long product <name>", gross_sales: "25.0000", units_sold: 2, distinct_orders: 1 }], by_units_sold: [{ product_id: "a/b", product_name: "Long product <name>", gross_sales: "25.0000", units_sold: 2, distinct_orders: 1 }], by_orders: [{ product_id: "a/b", product_name: "Long product <name>", gross_sales: "25.0000", units_sold: 2, distinct_orders: 1 }] },
  share: { products: [{ product_id: "a/b", product_name: "Long product <name>", gross_sales: "25.0000", gross_sales_share: "1.000000", cumulative_share: "1.000000" }], product_count: 1, total_gross_sales: "25.0000", top_20_percent_product_count: 1, top_20_percent_share: "1.000000", products_to_80_percent: 1, availability: available },
  growth: { availability: available, products: [], rising: [], falling: [] },
  dormant: { window_days: 60, anchor_date: "2025-03-31", availability: available, products: [] },
  penetration: { all_orders: 1, availability: available, products: [] },
  basket: { basket_orders: 1, excluded_oversize_orders: 0, max_distinct_products_per_order: 100, min_shared_orders: 10, min_support: "0.001000", eligible_pair_count: 0, availability: { state: "zero_result", reason: "No product pair meets the thresholds in this range" }, pairs: [] },
};

afterEach(() => { cleanup(); vi.clearAllMocks(); });

test("renders all portfolio regions, encoded product links and switches rankings", () => {
  useProducts.mockReturnValue({ data: products, isPending: false, isError: false, isPlaceholderData: false, refetch: vi.fn() });
  render(<MemoryRouter><ProductsView datasetId="d1" /></MemoryRouter>);
  for (const label of ["Rankings", "Share of gross sales", "Rising and falling products", "Dormant products", "Bought together"]) expect(screen.getByRole("region", { name: label })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Long product <name>" })).toHaveAttribute("href", "/d/d1/products/detail?product_id=a%2Fb");
  fireEvent.change(screen.getByLabelText("Rank by"), { target: { value: "units_sold" } });
  expect(useProducts).toHaveBeenCalledWith("d1", undefined, undefined, "60", "previous_period");
});

test("the share section draws the cumulative Pareto chart instead of a placeholder", () => {
  useProducts.mockReturnValue({ data: products, isPending: false, isError: false, isPlaceholderData: false, refetch: vi.fn() });
  render(<MemoryRouter><ProductsView datasetId="d1" /></MemoryRouter>);
  const share = screen.getByRole("region", { name: "Share of gross sales" });
  expect(within(share).getByRole("img", { name: /^Cumulative share of gross sales over 1 products/ })).toBeInTheDocument();
  expect(share.querySelector(".recharts-reference-line")).not.toBeNull();
  expect(within(share).queryByText("80% reference line")).toBeNull();
});

const detail: ProductDetail = {
  range: { start: "2025-01-01", end: "2025-01-02" }, currency: "USD", granularity: "daily",
  comparison: products.comparison, product: { product_id: "a/b", product_name: "Mug" },
  kpis: {
    gross_sales: { value: "7.0000", comparison_value: null, absolute_change: null, percent_change: null, change_status: "unavailable" },
    units_sold: { value: 3, comparison_value: null, absolute_change: null, percent_change: null, change_status: "unavailable" },
    orders: { value: 2, comparison_value: null, absolute_change: null, percent_change: null, change_status: "unavailable" },
  },
  trend: [{ bucket_start: "2025-01-01", gross_sales: "2.0000" }, { bucket_start: "2025-01-02", gross_sales: "5.0000" }],
  price_history: { granularity: "daily", availability: available, buckets: [{ bucket_start: "2025-01-01", weighted_unit_price: "2.0000", units_sold: 1 }, { bucket_start: "2025-01-02", weighted_unit_price: "2.5000", units_sold: 2 }] },
  penetration: { orders_containing_product: 2, all_orders: 4, order_penetration: "0.500000", availability: available },
  related_products: { excluded_oversize_orders: 0, availability: { state: "zero_result", reason: null }, related_products: [] },
  availability: available,
};

test("product detail draws the gross sales trend and the price history as charts", () => {
  useProductDetail.mockReturnValue({ data: detail, isPending: false, isError: false, refetch: vi.fn() });
  const { container } = render(<MemoryRouter initialEntries={["/d/d1/products/detail?product_id=a%2Fb"]}><ProductDetailView datasetId="d1" /></MemoryRouter>);
  const trend = screen.getByRole("region", { name: "Gross sales trend" });
  expect(within(trend).getByRole("img", { name: "Gross sales per day from 2025-01-01 to 2025-01-02" })).toBeInTheDocument();
  expect(within(trend).getByRole("cell", { name: "$5.00" })).toBeInTheDocument();
  const price = screen.getByRole("region", { name: "Average price paid per unit" });
  expect(within(price).getByRole("img", { name: "Weighted unit price per day from 2025-01-01 to 2025-01-02" })).toBeInTheDocument();
  expect(within(price).getByRole("cell", { name: "$2.50" })).toBeInTheDocument();
  expect(container.querySelectorAll(".recharts-line")).toHaveLength(2);
  expect(container.querySelector("ul")).toBeNull();
});

test("product detail shows the price history state instead of an empty chart", () => {
  useProductDetail.mockReturnValue({ data: { ...detail, price_history: { granularity: "daily", availability: { state: "zero_result", reason: null }, buckets: [] } }, isPending: false, isError: false, refetch: vi.fn() });
  render(<MemoryRouter initialEntries={["/d/d1/products/detail?product_id=a%2Fb"]}><ProductDetailView datasetId="d1" /></MemoryRouter>);
  const price = screen.getByRole("region", { name: "Average price paid per unit" });
  expect(within(price).getByText("No units of this product sold in this range")).toBeInTheDocument();
  expect(within(price).queryByRole("img")).toBeNull();
});
