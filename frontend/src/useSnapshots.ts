import { useEffect, useState } from "react";
import { getMetadata, getObservations } from "./api/client";
import { CURATED } from "./catalog";
import { toNumbers } from "./format";
import { today, yearsAgo } from "./dates";

export interface Snapshot {
  id: string;
  title: string;
  units: string;
  dates: string[];
  values: number[];
}

/** id -> snapshot; `null` means that one series failed to load. */
export type SnapshotMap = Record<string, Snapshot | null>;

const CACHE_KEY = "econ.snapshots.v1";
const CACHE_TTL_MS = 6 * 60 * 60 * 1000;

function readCache(): SnapshotMap | null {
  try {
    const raw = localStorage.getItem(CACHE_KEY);
    if (!raw) return null;
    const { t, data } = JSON.parse(raw) as { t: number; data: SnapshotMap };
    return Date.now() - t < CACHE_TTL_MS ? data : null;
  } catch {
    return null;
  }
}

function writeCache(data: SnapshotMap) {
  try {
    localStorage.setItem(CACHE_KEY, JSON.stringify({ t: Date.now(), data }));
  } catch {
    /* storage unavailable — the page works without it */
  }
}

/**
 * Two years of history for each featured series, fetched once and cached in
 * the browser for six hours. The API's token budget is shared per process, so
 * the landing page deliberately avoids re-spending it on every visit.
 */
export function useSnapshots() {
  const [items, setItems] = useState<SnapshotMap>(() => readCache() ?? {});
  const [loading, setLoading] = useState(() => readCache() === null);

  useEffect(() => {
    if (!loading) return;
    let cancelled = false;
    const collected: SnapshotMap = {};

    Promise.all(
      CURATED.map(async (s) => {
        try {
          const [obs, meta] = await Promise.all([
            getObservations(s.id, { start_date: yearsAgo(2), end_date: today(), frequency: s.freq }),
            getMetadata(s.id).catch(() => null),
          ]);
          const values = toNumbers(obs.observations);
          collected[s.id] =
            values.length > 1
              ? {
                  id: s.id,
                  title: meta?.title ?? s.name,
                  units: meta?.units ?? "",
                  dates: obs.observations.map((o) => o.date),
                  values,
                }
              : null;
        } catch {
          collected[s.id] = null;
        }
        if (!cancelled) setItems({ ...collected });
      }),
    ).then(() => {
      if (cancelled) return;
      setLoading(false);
      if (Object.values(collected).some(Boolean)) writeCache(collected);
    });

    return () => {
      cancelled = true;
    };
  }, [loading]);

  return { items, loading };
}
