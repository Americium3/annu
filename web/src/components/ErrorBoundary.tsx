import { Component, type ReactNode } from "react";

/**
 * Catches a rendering error in one part of the page (for example the hospital drawer meeting an unexpected
 * field in a record) and shows `fallback` there instead, so the rest of the page keeps working.
 * `resetKey` clears the error when it changes (another hospital opened).
 */
export class ErrorBoundary extends Component<
  { children: ReactNode; fallback: ReactNode; resetKey?: unknown },
  { failed: boolean; key?: unknown }
> {
  state = { failed: false, key: this.props.resetKey };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  static getDerivedStateFromProps(props: { resetKey?: unknown }, state: { failed: boolean; key?: unknown }) {
    return props.resetKey !== state.key ? { failed: false, key: props.resetKey } : null;
  }

  componentDidCatch(error: unknown) {
    console.error("Part of the page failed to render", error);
  }

  render() {
    return this.state.failed ? this.props.fallback : this.props.children;
  }
}
