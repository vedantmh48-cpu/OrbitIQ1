// Minimal browser-ish globals shared by the smoke scripts.
const bag = new Map();
globalThis.localStorage = {
  getItem: k => (bag.has(k) ? bag.get(k) : null),
  setItem: (k, v) => void bag.set(k, String(v)),
  removeItem: k => void bag.delete(k),
  clear: () => bag.clear(),
  get length() { return bag.size; },
  key: i => Array.from(bag.keys())[i] ?? null,
};
globalThis.fetch = async () => ({ status: 200, ok: true, json: async () => ({}) });
export { bag };
