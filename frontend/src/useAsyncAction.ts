import { useCallback, useState } from "react";

interface State<T> {
  data: T | null;
  error: unknown;
  loading: boolean;
}

/** Minimal request-state helper: run an async fn, track loading/data/error. */
export function useAsyncAction<T>(fn: () => Promise<T>) {
  const [state, setState] = useState<State<T>>({ data: null, error: null, loading: false });

  const run = useCallback(async () => {
    setState({ data: null, error: null, loading: true });
    try {
      setState({ data: await fn(), error: null, loading: false });
    } catch (error) {
      setState({ data: null, error, loading: false });
    }
  }, [fn]);

  return { ...state, run };
}
