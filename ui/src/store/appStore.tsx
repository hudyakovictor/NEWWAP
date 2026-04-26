import { createContext, useContext, useState, useCallback, useEffect } from "react";
import type { ReactNode } from "react";
import type { PageId } from "../components/TopBar";
import { PHOTOS, type PhotoRecord } from "../mock/photos";
import { log } from "../debug/logger";

interface AppStore {
  page: PageId;
  setPage: (p: PageId) => void;
  pairA: string;
  pairB: string;
  setPairA: (id: string) => void;
  setPairB: (id: string) => void;
  openPairWith(id: string, slot: "A" | "B"): void;
}

const Ctx = createContext<AppStore | null>(null);

export function AppProvider({ children }: { children: ReactNode }) {
  const [page, setPageRaw] = useState<PageId>("timeline");
  const [pairA, setPairARaw] = useState<string>(PHOTOS[30].id);
  const [pairB, setPairBRaw] = useState<string>(PHOTOS[PHOTOS.length - 40].id);

  const setPage = useCallback((p: PageId) => {
    log.info("nav", "nav:page", `navigate → ${p}`, { from: pageRef.current, to: p });
    pageRef.current = p;
    setPageRaw(p);
  }, []);
  const pageRef = usePersistentRef<PageId>("timeline");

  const setPairA = useCallback((id: string) => {
    log.info("pair", "pair:setA", `Pair A → ${id}`, { id });
    setPairARaw(id);
  }, []);
  const setPairB = useCallback((id: string) => {
    log.info("pair", "pair:setB", `Pair B → ${id}`, { id });
    setPairBRaw(id);
  }, []);

  const openPairWith = useCallback((id: string, slot: "A" | "B") => {
    log.info("pair", "pair:openPairWith", `Set ${slot}=${id} and switch to Pair analysis`, { id, slot });
    if (slot === "A") setPairARaw(id);
    else setPairBRaw(id);
    pageRef.current = "pairs";
    setPageRaw("pairs");
  }, []);

  // Track pair transitions for console audit trail
  useEffect(() => {
    log.debug("pair", "pair:state", "Pair state update", { A: pairA, B: pairB });
  }, [pairA, pairB]);

  return (
    <Ctx.Provider value={{ page, setPage, pairA, pairB, setPairA, setPairB, openPairWith }}>
      {children}
    </Ctx.Provider>
  );
}

// Lightweight ref helper so we can reference previous page inside setters.
function usePersistentRef<T>(initial: T) {
  const r = useState<{ current: T }>({ current: initial })[0];
  return r;
}

export function useApp(): AppStore {
  const c = useContext(Ctx);
  if (!c) throw new Error("AppProvider missing");
  return c;
}

export function usePhotoRecord(id: string | undefined): PhotoRecord | undefined {
  return id ? PHOTOS.find((p) => p.id === id) : undefined;
}
