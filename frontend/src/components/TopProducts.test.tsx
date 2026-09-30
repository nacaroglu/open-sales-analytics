import { afterEach, expect, test } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import TopProducts, { shortenName, topProductsSentence } from "./TopProducts";
import type { Summary } from "../lib/types";

afterEach(cleanup);

type Product = Summary["top_products"][number];

const range = { start: "2025-03-01", end: "2025-03-31" };

function product(id: string, name: string, sales: string, units = 1, orders = 1): Product {
  return { product_id: id, product_name: name, gross_sales: sales, units_sold: units, distinct_orders: orders };
}

function renderProducts(products: Product[] | undefined, currency: string | undefined = "USD") {
  return render(<TopProducts topProducts={products} currency={currency} range={range} />);
}

// Y-axis tick texts, top to bottom (Recharts also leaves a hidden measuring span).
function labels(container: HTMLElement): string[] {
  return Array.from(container.querySelectorAll(".recharts-yAxis-tick-labels .recharts-cartesian-axis-tick-value")).map(
    (el) => el.textContent ?? "",
  );
}

function bars(container: HTMLElement): SVGElement[] {
  return Array.from(container.querySelectorAll(".recharts-bar-rectangle")).flatMap((el) =>
    Array.from(el.querySelectorAll("path, rect")),
  ) as SVGElement[];
}

function tableNames(): string[] {
  const rows = screen.getAllByRole("row").slice(1);
  return rows.map((row) => within(row).getAllByRole("cell")[0].textContent ?? "");
}

test("10 products: 10 bars and 10 rows, in the order received, with the range in the text alternative", () => {
  const products = Array.from({ length: 10 }, (_, i) =>
    product(`p${i + 1}`, `Product ${i + 1}`, `${(10 - i) * 100}.0000`, 5, 2),
  );
  const { container } = renderProducts(products);

  expect(screen.getByRole("heading", { level: 2, name: "Top products" })).toBeInTheDocument();
  expect(
    screen.getByRole("img", { name: "Top 10 products by gross sales from 2025-03-01 to 2025-03-31" }),
  ).toBeInTheDocument();
  expect(bars(container)).toHaveLength(10);
  expect(screen.getAllByRole("row")).toHaveLength(11);
  expect(labels(container)).toEqual(products.map((p) => p.product_name));
  expect(tableNames()).toEqual(products.map((p) => p.product_name));
});

test("an order that is not by name or by sales is kept as received", () => {
  const { container } = renderProducts([
    product("p10", "Zebra", "5.0000"),
    product("p2", "Apple", "50.0000"),
  ]);

  expect(labels(container)).toEqual(["Zebra", "Apple"]);
  expect(tableNames()).toEqual(["Zebra", "Apple"]);
});

test("3 products: 3 bars, 3 rows, no empty rows, count in the label", () => {
  const { container } = renderProducts([
    product("a", "A", "30.0000"),
    product("b", "B", "20.0000"),
    product("c", "C", "10.0000"),
  ]);

  expect(bars(container)).toHaveLength(3);
  expect(screen.getAllByRole("row")).toHaveLength(4);
  expect(screen.getByRole("img")).toHaveAttribute(
    "aria-label",
    "Top 3 products by gross sales from 2025-03-01 to 2025-03-31",
  );
});

test("a single product reads as singular", () => {
  expect(topProductsSentence(1, range)).toBe("Top 1 product by gross sales from 2025-03-01 to 2025-03-31");
});

test("a tie keeps the server's order and draws bars of equal length", () => {
  const { container } = renderProducts([
    product("p10", "Ten", "100.0000"),
    product("p2", "Two", "100.0000"),
    product("p3", "Three", "40.0000"),
  ]);

  expect(labels(container)).toEqual(["Ten", "Two", "Three"]);
  expect(tableNames()).toEqual(["Ten", "Two", "Three"]);
  const widths = bars(container).map((bar) => Number(bar.getAttribute("width")));
  expect(widths[0]).toBe(widths[1]);
  expect(widths[0]).toBeGreaterThan(widths[2]);
});

test("two products with the same name and different ids are two bars and two rows", () => {
  const { container } = renderProducts([
    product("p1", "Widget", "100.0000", 4, 2),
    product("p2", "Widget", "60.0000", 3, 1),
  ]);

  expect(bars(container)).toHaveLength(2);
  expect(labels(container)).toEqual(["Widget", "Widget"]);
  const rows = screen.getAllByRole("row").slice(1);
  expect(rows).toHaveLength(2);
  expect(within(rows[0]).getByText("$100.00")).toBeInTheDocument();
  expect(within(rows[1]).getByText("$60.00")).toBeInTheDocument();
});

test("a long name is shortened with an ellipsis in the chart and complete in the table", () => {
  const name = "An extraordinarily long product name that cannot fit the label area";
  const { container } = renderProducts([product("p1", name, "10.0000")]);

  const [label] = labels(container);
  expect(label.endsWith("…")).toBe(true);
  expect(Array.from(label).length).toBeLessThan(name.length);
  expect(name.startsWith(label.slice(0, -1))).toBe(true);
  expect(tableNames()).toEqual([name]);
  expect(shortenName("short")).toBe("short");
  expect(shortenName("x".repeat(22))).toBe("x".repeat(22));
  expect(shortenName("x".repeat(23))).toBe(`${"x".repeat(21)}…`);
});

test("HTML-like names are literal text in the chart and in the table", () => {
  const { container } = renderProducts([product("p1", "<b>x</b>", "10.0000")]);

  expect(labels(container)).toEqual(["<b>x</b>"]);
  expect(tableNames()).toEqual(["<b>x</b>"]);
  expect(container.querySelector("b")).toBeNull();
});

test("the table has the four columns, money in the currency and grouped counts, numbers right-aligned", () => {
  renderProducts([product("p1", "Desk", "1234567.8900", 12345, 6789)], "EUR");

  const headers = screen.getAllByRole("columnheader");
  expect(headers.map((h) => h.textContent)).toEqual(["Product", "Gross sales", "Units sold", "Orders"]);
  expect(headers[0]).not.toHaveClass("text-right");
  for (const header of headers.slice(1)) expect(header).toHaveClass("text-right");
  const cells = within(screen.getAllByRole("row")[1]).getAllByRole("cell");
  expect(cells.map((c) => c.textContent)).toEqual(["Desk", "€1,234,567.89", "12,345", "6,789"]);
  for (const cell of cells.slice(1)) expect(cell).toHaveClass("text-right");
  expect(screen.getByRole("table").parentElement).toHaveClass("overflow-x-auto");
});

test("a product with zero gross sales keeps its bar slot and its row", () => {
  const { container } = renderProducts([product("p1", "Desk", "10.0000"), product("p2", "Free", "0.0000")]);

  expect(labels(container)).toEqual(["Desk", "Free"]);
  expect(tableNames()).toEqual(["Desk", "Free"]);
  expect(within(screen.getAllByRole("row")[2]).getByText("$0.00")).toBeInTheDocument();
});

test("an empty list shows the message in an h-72 box and neither chart nor table", () => {
  const { container } = renderProducts([]);

  expect(screen.getByRole("heading", { level: 2, name: "Top products" })).toBeInTheDocument();
  const message = screen.getByText("No products sold in this range");
  expect(message).toHaveClass("h-72");
  expect(screen.queryByRole("img")).toBeNull();
  expect(screen.queryByRole("table")).toBeNull();
  expect(container.querySelector("svg")).toBeNull();
});

test("while loading: a busy status with Loading… and a pulse block, no chart and no table", () => {
  const { container } = renderProducts(undefined, undefined);

  const status = screen.getByRole("status");
  expect(status).toHaveAttribute("aria-busy", "true");
  expect(within(status).getByText("Loading…")).toBeInTheDocument();
  expect(container.querySelector(".h-72.animate-pulse.motion-reduce\\:animate-none")).not.toBeNull();
  expect(screen.queryByRole("img")).toBeNull();
  expect(screen.queryByRole("table")).toBeNull();
});

test("the tooltip shows the full name and the gross sales in full currency format", () => {
  const { container } = renderProducts([
    product("p1", "An extraordinarily long product name that cannot fit", "1234.5000"),
    product("p2", "Desk", "20.0000"),
  ]);

  // jsdom has no layout, so hover cannot hit a bar: focusing the chart shows the
  // first entry in the same tooltip (hover itself is checked in a real browser).
  fireEvent.focus(container.querySelector(".recharts-surface") as SVGElement);

  const tooltip = container.querySelector(".recharts-tooltip-wrapper") as HTMLElement;
  expect(tooltip).toHaveTextContent("An extraordinarily long product name that cannot fit");
  expect(tooltip).toHaveTextContent("Gross sales : $1,234.50");
  expect(document.body.textContent).not.toMatch(/revenue/i);
});
