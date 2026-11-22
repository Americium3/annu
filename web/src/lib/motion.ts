import { flushSync } from "react-dom";

/**
 * Fluid state changes via the View Transitions API.
 *
 * `withTransition(update)` runs a React state update inside
 * document.startViewTransition, so the browser morphs the old screen into the
 * new one: result rows glide to their new order, steps slide, the theme
 * spreads from the toggle. Where the API is missing, or the person asked for
 * reduced motion, the update simply happens.
 */
type TransitionDocument = Document & {
  startViewTransition?: (callback: () => void) => { finished: Promise<void>; ready: Promise<void> };
};

export function prefersReducedMotion() {
  return typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
}

export function withTransition(update: () => void, kind?: string) {
  const doc = document as TransitionDocument;
  if (!doc.startViewTransition || prefersReducedMotion()) {
    update();
    return null;
  }
  if (kind) document.documentElement.dataset.transition = kind;
  const transition = doc.startViewTransition(() => {
    flushSync(update);
  });
  transition.finished.finally(() => {
    delete document.documentElement.dataset.transition;
  });
  return transition;
}

/** A CSS-safe view-transition-name for an arbitrary id. */
export function transitionName(prefix: string, id: string) {
  return `${prefix}-${id.replace(/[^a-zA-Z0-9_-]/g, "_")}`;
}
