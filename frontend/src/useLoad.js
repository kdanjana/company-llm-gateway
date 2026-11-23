import { useEffect, useState } from "react";

/**
 * Loads data when the page opens and whenever `deps` change.
 * While reloading, the previous data stays on screen (shown dimmed) instead of flashing empty.
 * Returns { data, error, loading, reload }.
 */
export function useLoad(load, deps) {
  const [state, setState] = useState({ data: null, error: "", loading: true });
  const [version, setVersion] = useState(0);

  useEffect(() => {
    let cancelled = false; // ignore answers that arrive after the page moved on
    setState((s) => ({ ...s, loading: true, error: "" }));
    load()
      .then((data) => {
        if (!cancelled) setState({ data, error: "", loading: false });
      })
      .catch((err) => {
        if (!cancelled) setState((s) => ({ ...s, error: err.message, loading: false }));
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, version]);

  return { ...state, reload: () => setVersion((v) => v + 1) };
}
