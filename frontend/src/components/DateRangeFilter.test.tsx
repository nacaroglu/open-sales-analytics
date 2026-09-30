import { afterEach, expect, test, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import DateRangeFilter, { isIsoDate, validateRange } from "./DateRangeFilter";

afterEach(cleanup);

const noop = () => {};

test("isIsoDate accepts real calendar dates and nothing else", () => {
  expect(isIsoDate("2025-03-01")).toBe(true);
  expect(isIsoDate("2024-02-29")).toBe(true);
  expect(isIsoDate("2025-02-29")).toBe(false);
  expect(isIsoDate("2025-04-31")).toBe(false);
  expect(isIsoDate("2025-13-01")).toBe(false);
  expect(isIsoDate("2025-00-10")).toBe(false);
  expect(isIsoDate("2025-01-00")).toBe(false);
  expect(isIsoDate("12025-03-01")).toBe(false);
  expect(isIsoDate("")).toBe(false);
  expect(isIsoDate("2025-3-1")).toBe(false);
});

test("validateRange: five-digit years, before the first and after the last date are errors", () => {
  const min = "2025-01-01";
  const max = "2025-12-31";
  expect(validateRange(min, max, "12025-03-01", max).errors.start).toBe(
    "Start date must be between 2025-01-01 and 2025-12-31",
  );
  expect(validateRange(min, max, "2024-12-31", max).errors.start).toMatch(/^Start date must be between/);
  expect(validateRange(min, max, min, "2026-01-01").errors.end).toBe(
    "End date must be between 2025-01-01 and 2025-12-31",
  );
  expect(validateRange(min, max, min, "12025-03-01").valid).toBe(false);
});

test("validateRange: inverted is an error on Start, equal and ordered are valid, empty is neither", () => {
  const min = "2025-01-01";
  const max = "2025-12-31";
  expect(validateRange(min, max, "2025-06-02", "2025-06-01")).toEqual({
    errors: { start: "Start date must be on or before end date", end: null },
    valid: false,
  });
  expect(validateRange(min, max, "2025-06-01", "2025-06-01").valid).toBe(true);
  expect(validateRange(min, max, min, max).valid).toBe(true);
  expect(validateRange(min, max, "", max)).toEqual({ errors: { start: null, end: null }, valid: false });
  expect(validateRange(min, max, min, "")).toEqual({ errors: { start: null, end: null }, valid: false });
});

test("a range error wins over the inverted message on Start", () => {
  const { errors } = validateRange("2025-01-01", "2025-12-31", "2024-01-01", "2023-01-01");
  expect(errors.start).toMatch(/^Start date must be between/);
  expect(errors.end).toMatch(/^End date must be between/);
});

test("without bounds both inputs and Reset are disabled and empty", () => {
  render(
    <DateRangeFilter
      min={undefined}
      max={undefined}
      start=""
      end=""
      onStartChange={noop}
      onEndChange={noop}
      onReset={noop}
      updating={false}
    />,
  );
  expect(screen.getByLabelText("Start date")).toBeDisabled();
  expect(screen.getByLabelText("End date")).toBeDisabled();
  expect(screen.getByRole("button", { name: "Reset" })).toBeDisabled();
  expect(screen.getByLabelText("Start date")).toHaveValue("");
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

test("it only calls its handlers: change, blur on an empty input and Reset", () => {
  const onStart = vi.fn();
  const onEnd = vi.fn();
  const onReset = vi.fn();
  render(
    <DateRangeFilter
      min="2025-03-01"
      max="2025-03-31"
      start=""
      end="2025-03-20"
      onStartChange={onStart}
      onEndChange={onEnd}
      onReset={onReset}
      updating={false}
    />,
  );

  fireEvent.change(screen.getByLabelText("End date"), { target: { value: "2025-03-21" } });
  expect(onEnd).toHaveBeenCalledWith("2025-03-21");
  fireEvent.blur(screen.getByLabelText("Start date"));
  expect(onStart).toHaveBeenCalledWith("2025-03-01");
  fireEvent.blur(screen.getByLabelText("End date"));
  expect(onEnd).toHaveBeenCalledTimes(1);
  fireEvent.click(screen.getByRole("button", { name: "Reset" }));
  expect(onReset).toHaveBeenCalledTimes(1);
});

test("Updating… is a status shown only while updating", () => {
  const props = {
    min: "2025-03-01",
    max: "2025-03-31",
    start: "2025-03-02",
    end: "2025-03-31",
    onStartChange: noop,
    onEndChange: noop,
    onReset: noop,
  };
  const view = render(<DateRangeFilter {...props} updating={false} />);
  expect(screen.queryByText("Updating…")).not.toBeInTheDocument();
  view.rerender(<DateRangeFilter {...props} updating />);
  expect(screen.getByRole("status")).toHaveTextContent("Updating…");
});
