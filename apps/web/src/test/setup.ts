import "@testing-library/jest-dom/vitest";
import "@testing-library/react";

type ResizeHandler = (width: number) => void;

const resizeHandlers = new WeakMap<Element, Set<ResizeHandler>>();

class ResizeObserverStub implements ResizeObserver {
  private readonly callback: ResizeObserverCallback;

  constructor(callback: ResizeObserverCallback) {
    this.callback = callback;
  }

  observe(target: Element): void {
    const set = resizeHandlers.get(target) ?? new Set<ResizeHandler>();
    set.add((width) => {
      const entry = { contentRect: { width } } as unknown as ResizeObserverEntry;
      this.callback([entry], this as unknown as ResizeObserver);
    });
    resizeHandlers.set(target, set);
  }

  unobserve(): void {}

  disconnect(): void {}
}

export function fireResize(target: Element, width: number): void {
  for (const handler of resizeHandlers.get(target) ?? []) handler(width);
}

globalThis.ResizeObserver = ResizeObserverStub as unknown as typeof ResizeObserver;

if (typeof Element !== "undefined") {
  const prototype = Element.prototype as Element & {
    setPointerCapture?: () => void;
    releasePointerCapture?: () => void;
  };
  if (typeof prototype.setPointerCapture !== "function") {
    prototype.setPointerCapture = () => {};
  }
  if (typeof prototype.releasePointerCapture !== "function") {
    prototype.releasePointerCapture = () => {};
  }
}
