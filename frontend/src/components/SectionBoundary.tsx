import { Component } from "react";
import type { ReactNode } from "react";
import ErrorBlock from "./ErrorBlock";
import { SECTION_FAILED } from "../lib/errors";

// Catches a render error in one dashboard section so the others keep working.
// A new `resetKey` (new data arrived) gives the section another try.
export default class SectionBoundary extends Component<
  { children: ReactNode; resetKey?: unknown },
  { failed: boolean }
> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidUpdate(previous: { resetKey?: unknown }) {
    if (this.state.failed && previous.resetKey !== this.props.resetKey) {
      this.setState({ failed: false });
    }
  }

  render() {
    return this.state.failed ? <ErrorBlock message={SECTION_FAILED} /> : this.props.children;
  }
}
