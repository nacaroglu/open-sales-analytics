import { afterEach, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { ProductsView } from "./ProductsPage";
import type { ProductsResponse } from "../lib/types";

const { useProducts } = vi.hoisted(() => ({ useProducts: vi.fn() }));
vi.mock("../lib/hooks", async (importOriginal) => ({ ...(await importOriginal<typeof import("../lib/hooks")>()), useProducts }));

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

afterEach(() => vi.clearAllMocks());

test("renders all portfolio regions, encoded product links and switches rankings", () => {
  useProducts.mockReturnValue({ data: products, isPending: false, isError: false, isPlaceholderData: false, refetch: vi.fn() });
  render(<MemoryRouter><ProductsView datasetId="d1" /></MemoryRouter>);
  for (const label of ["Rankings", "Share of gross sales", "Rising and falling products", "Dormant products", "Bought together"]) expect(screen.getByRole("region", { name: label })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Long product <name>" })).toHaveAttribute("href", "/d/d1/products/detail?product_id=a%2Fb");
  fireEvent.change(screen.getByLabelText("Rank by"), { target: { value: "units_sold" } });
  expect(useProducts).toHaveBeenCalledWith("d1", undefined, undefined, "60", "previous_period");
});
