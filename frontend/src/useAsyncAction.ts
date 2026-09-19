import { useCallback, useRef, useState } from "react";

interface State<T> {
  data: T | null;
  error: unknown;
  loading: boolean;
}

/** Request-state helper: `run(...args)` calls `fn`, tracking loading / data /
 * error. Only the latest call may update state, so a slow earlier request
 * can't overwrite a newer one. `fn` should be a stable reference. */
export function useAsyncAction<A extends unknown[], T>(fn: (...args: A) => Promise<T>) {
  const [state, setState] = useState<State<T>>({ data: null, error: null, loading: false });
  const latest = useRef(0);

  const run = useCallback(
    async (...args: A) => {
      const ticket = ++latest.current;
      setState({ data: null, error: null, loading: true });
      try {
        const data = await fn(...args);
        if (ticket === latest.current) setState({ data, error: null, loading: false });
      } catch (error) {
        if (ticket === latest.current) setState({ data: null, error, loading: false });
      }
    },
    [fn],
  );

  return { ...state, run };
}
