import { afterEach, expect, test } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import KpiCards from "./KpiCards";

afterEach(cleanup);

const LABELS = ["Gross sales", "Orders", "Units sold", "Average order value"];

function valueOf(label: string): string {
  const term = screen.getByText(label);
  return term.nextElementSibling?.textContent ?? "";
}

test("four cards in order with money and counts formatted", () => {
  render(
    <KpiCards
      kpis={{ gross_sales: "1234.5678", orders: 10482, units_sold: 1234567, average_order_value: "1234.5000" }}
      currency="USD"
    />,
  );

  const terms = screen.getAllByRole("term").map((el) => el.textContent);
  expect(terms).toEqual(LABELS);
  expect(valueOf("Gross sales")).toBe("$1,234.57");
  expect(valueOf("Orders")).toBe("10,482");
  expect(valueOf("Units sold")).toBe("1,234,567");
  expect(valueOf("Average order value")).toBe("$1,234.50");
});

test("all zeros show formatted zeros, not blanks", () => {
  render(
    <KpiCards
      kpis={{ gross_sales: "0.0000", orders: 0, units_sold: 0, average_order_value: "0.0000" }}
      currency="USD"
    />,
  );

  expect(LABELS.map(valueOf)).toEqual(["$0.00", "0", "0", "$0.00"]);
  expect(document.body).not.toHaveTextContent(/NaN|—/);
});

test("a currency without minor units has no decimals", () => {
  render(
    <KpiCards
      kpis={{ gross_sales: "1234.0000", orders: 1, units_sold: 1, average_order_value: "1234.0000" }}
      currency="JPY"
    />,
  );

  expect(valueOf("Gross sales")).toBe("¥1,234");
  expect(valueOf("Average order value")).toBe("¥1,234");
});

test("a very long value is shown in full and wraps rather than overflowing", () => {
  render(
    <KpiCards
      kpis={{ gross_sales: "1234567890.1200", orders: 1, units_sold: 1, average_order_value: "1.0000" }}
      currency="USD"
    />,
  );

  const value = screen.getByText("$1,234,567,890.12");
  expect(value.tagName).toBe("DD");
  expect(value).toHaveClass("wrap-anywhere", "text-2xl", "lg:text-xl");
});

test("while loading, every card shows a placeholder instead of a number", () => {
  render(<KpiCards kpis={undefined} currency={undefined} />);

  const status = screen.getByRole("status");
  expect(status).toHaveAttribute("aria-busy", "true");
  expect(screen.getAllByRole("term").map((el) => el.textContent)).toEqual(LABELS);
  for (const label of LABELS) expect(valueOf(label)).toBe("");
  expect(status.querySelectorAll(".animate-pulse")).toHaveLength(4);
  expect(status.querySelectorAll(".motion-reduce\\:animate-none")).toHaveLength(4);
});

test("each label and its value are a term/definition pair, read together", () => {
  render(
    <KpiCards
      kpis={{ gross_sales: "5.0000", orders: 2, units_sold: 3, average_order_value: "2.5000" }}
      currency="USD"
    />,
  );

  for (const term of screen.getAllByRole("term")) {
    expect(term.nextElementSibling?.tagName).toBe("DD");
    expect(term.parentElement?.tagName).toBe("DIV");
    expect(within(term.parentElement as HTMLElement).getAllByRole("definition")).toHaveLength(1);
  }
});

test("the word revenue appears nowhere", () => {
  render(<KpiCards kpis={undefined} currency={undefined} />);
  expect(document.body).not.toHaveTextContent(/revenue/i);
});
