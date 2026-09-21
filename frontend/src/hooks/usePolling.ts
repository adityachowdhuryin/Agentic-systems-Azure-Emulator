import { useCallback, useEffect, useRef, useState } from "react";

export function usePolling<T>(
  fetchFn: () => Promise<T>,
  deps: unknown[],
  intervalMs = 3000,
  enabled = true
) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const fetchFnRef = useRef(fetchFn);
  fetchFnRef.current = fetchFn;
  const hadDataRef = useRef(false);

  const refresh = useCallback(async () => {
    if (!enabled) return;
    setIsRefreshing(true);
    if (!hadDataRef.current) setIsLoading(true);
    try {
      const result = await fetchFnRef.current();
      setData(result);
      hadDataRef.current = true;
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error");
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, ...deps]);

  useEffect(() => {
    if (!enabled) return;
    refresh();
    const id = setInterval(refresh, intervalMs);
    return () => clearInterval(id);
  }, [refresh, enabled, intervalMs]);

  return { data, error, isLoading, isRefreshing, refresh };
}

const ACTIVE_RUN_STATES = new Set([
  "RECEIVED",
  "ADMITTED",
  "DISPATCHED",
  "QUEUED",
  "SUSPENDED",
  "REVIEWING",
]);

export function isRunInProgress(state: string | undefined): boolean {
  return !!state && ACTIVE_RUN_STATES.has(state);
}

export function getPollingInterval(runState: string | undefined): number {
  return isRunInProgress(runState) ? 500 : 3000;
}
