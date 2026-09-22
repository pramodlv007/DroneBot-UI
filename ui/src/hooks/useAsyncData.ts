import { useCallback, useEffect, useState } from "react";

// A changed selection invalidates older requests, so a slow response cannot
// overwrite the currently selected experiment. Callers memoize their loader.
export function useAsyncData<T>(load: (() => Promise<T>) | null) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(!!load);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const retry = useCallback(() => setAttempt(value => value + 1), []);
  useEffect(() => {
    let current = true;
    setData(null);
    setError(null);
    setLoading(!!load);
    if (load) {
      load().then(result => { if (current) setData(result); })
        .catch(reason => { if (current) setError(reason instanceof Error ? reason.message : "Could not load data."); })
        .finally(() => { if (current) setLoading(false); });
    }
    return () => { current = false; };
  }, [load, attempt]);
  return { data, loading, error, retry };
}
