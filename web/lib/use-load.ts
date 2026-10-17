"use client";

import { useCallback, useEffect, useState } from "react";
import type { Sourced } from "./api";
import type { DataSource } from "./types";

export interface LoadState<T> {
  data: T | undefined;
  source: DataSource | undefined;
  placeholder: boolean;
  error: string | undefined;
  loading: boolean;
  reload: () => void;
}

export function useLoad<T>(fn: () => Promise<Sourced<T>>, key: string = ""): LoadState<T> {
  const [state, setState] = useState<Omit<LoadState<T>, "reload">>({
    data: undefined,
    source: undefined,
    placeholder: false,
    error: undefined,
    loading: true,
  });
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    let alive = true;
    fn().then(
      (r) => alive && setState({ data: r.data, source: r.source, placeholder: r.placeholder, error: undefined, loading: false }),
      (e: unknown) => alive && setState((s) => ({ ...s, error: String(e), loading: false })),
    );
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, nonce]);

  const reload = useCallback(() => setNonce((n) => n + 1), []);
  return { ...state, reload };
}
