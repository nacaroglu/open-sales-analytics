import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import ErrorBlock from "./ErrorBlock";
import FullPageCard from "./FullPageCard";
import SectionBoundary from "./SectionBoundary";

afterEach(cleanup);

test("the error block is an alert with icon, the word Error, the message as text and its actions", () => {
  render(
    <ErrorBlock message="<b>Oops</b>">
      <button>Retry</button>
    </ErrorBlock>,
  );

  const block = screen.getByRole("alert");
  expect(block).toHaveTextContent("Error <b>Oops</b>");
  expect(block.querySelector("b")).toBeNull();
  expect(block.querySelector("strong")).toHaveTextContent("Error");
  expect(block.querySelector("[aria-hidden]")).toHaveTextContent("✕");
  expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  expect(block).toHaveClass("border-red-700", "bg-red-50", "text-red-900");
});

test("the full-page card is an alert with an h2, one sentence and its action", () => {
  render(
    <FullPageCard title="Title" sentence="One sentence.">
      <a href="/">Go</a>
    </FullPageCard>,
  );

  const card = screen.getByRole("alert");
  expect(card).toContainElement(screen.getByRole("heading", { level: 2, name: "Title" }));
  expect(card).toHaveTextContent("One sentence.");
  expect(card).toContainElement(screen.getByRole("link", { name: "Go" }));
  expect(card).toHaveClass("mx-auto", "max-w-md", "text-center");
});

function Boom({ fail }: { fail: boolean }) {
  if (fail) throw new Error("secret stack detail");
  return <p>fine</p>;
}

beforeEach(() => {
  vi.spyOn(console, "error").mockImplementation(() => {});
});

afterEach(() => {
  vi.restoreAllMocks();
});

test("a section boundary shows the fallback instead of a blank page and hides the error text", () => {
  render(
    <div>
      <SectionBoundary>
        <Boom fail />
      </SectionBoundary>
      <p>other section</p>
    </div>,
  );

  expect(screen.getByRole("alert")).toHaveTextContent("Something went wrong showing this section");
  expect(document.body.textContent).not.toContain("secret stack detail");
  expect(screen.getByText("other section")).toBeInTheDocument();
});

test("a section boundary renders its children when nothing fails", () => {
  render(
    <SectionBoundary>
      <Boom fail={false} />
    </SectionBoundary>,
  );
  expect(screen.getByText("fine")).toBeInTheDocument();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

test("a new resetKey gives the section another try, the same key keeps the fallback", () => {
  const { rerender } = render(
    <SectionBoundary resetKey={1}>
      <Boom fail />
    </SectionBoundary>,
  );
  expect(screen.getByRole("alert")).toBeInTheDocument();

  rerender(
    <SectionBoundary resetKey={1}>
      <Boom fail={false} />
    </SectionBoundary>,
  );
  expect(screen.getByRole("alert")).toBeInTheDocument();

  rerender(
    <SectionBoundary resetKey={2}>
      <Boom fail={false} />
    </SectionBoundary>,
  );
  expect(screen.getByText("fine")).toBeInTheDocument();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});
