/**
 * Test-only zustand replacement: lets the harness control the snapshot React
 * reads during an SSR render (zustand v5 normally freezes it at the boot state).
 */
import { createStore } from "zustand/vanilla";
import { useStore } from "zustand/react";

let override = null;

export function setStateOverride(fn) {
  override = fn;
}

export function create(createState) {
  const api = createStore(createState);
  const base = api.getInitialState;
  api.getInitialState = () => {
    const initial = base();
    return override ? { ...initial, ...override(initial) } : initial;
  };
  const useBoundStore = (selector) => useStore(api, selector);
  Object.assign(useBoundStore, api);
  return useBoundStore;
}

export { useStore };

export default { create, useStore };
