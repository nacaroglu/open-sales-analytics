import "@testing-library/jest-dom/vitest";

// jsdom has no layout and no ResizeObserver, which Recharts' ResponsiveContainer
// needs. This stub reports a fixed 800 x 288 px box (w-full x h-72) as soon as an
// element is observed, so charts render in tests.
class ResizeObserverStub {
  private callback: ResizeObserverCallback;
  constructor(callback: ResizeObserverCallback) {
    this.callback = callback;
  }
  observe(target: Element) {
    const contentRect = { width: 800, height: 288, top: 0, left: 0, right: 800, bottom: 288, x: 0, y: 0 };
    this.callback(
      [{ target, contentRect } as unknown as ResizeObserverEntry],
      this as unknown as ResizeObserver,
    );
  }
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver = ResizeObserverStub;
