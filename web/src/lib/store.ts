/**
 * A tiny guarded localStorage store for useSyncExternalStore.
 *
 * Storage can be missing or throw (private mode, blocked site data), so every
 * read and write is guarded and the app falls back to defaults. Snapshots are
 * cached per raw string so React sees a stable reference until the value
 * actually changes.
 */
export function createStore<T>(key: string, empty: T, parse: (raw: unknown) => T) {
  const listeners = new Set<() => void>();
  let cachedRaw: string | null | undefined;
  let cachedValue: T = empty;

  function snapshot(): T {
    try {
      const raw = window.localStorage.getItem(key);
      if (raw !== cachedRaw) {
        cachedRaw = raw;
        cachedValue = raw ? parse(JSON.parse(raw)) : empty;
      }
    } catch {
      cachedValue = empty;
    }
    return cachedValue;
  }

  function write(value: T | null) {
    try {
      if (value === null) window.localStorage.removeItem(key);
      else window.localStorage.setItem(key, JSON.stringify(value));
    } catch {
      /* storage unavailable: keep working for this visit */
      cachedRaw = undefined;
      cachedValue = value ?? empty;
    }
    listeners.forEach((listener) => listener());
  }

  function subscribe(onChange: () => void) {
    listeners.add(onChange);
    const onStorage = (event: StorageEvent) => {
      if (event.key === null || event.key === key) onChange();
    };
    window.addEventListener("storage", onStorage);
    return () => {
      listeners.delete(onChange);
      window.removeEventListener("storage", onStorage);
    };
  }

  return { snapshot, write, subscribe };
}
