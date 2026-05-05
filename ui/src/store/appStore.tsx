import { createContext, useContext, useState, useCallback, useRef } from "react";
import type { ReactNode } from "react";
import type { PageId } from "../components/TopBar";
import type { PhotoRecord } from "../api/types";
import { log } from "../debug/logger";

interface AppStore {
  page: PageId;
  setPage: (p: PageId) => void;
  pairA: string;
  pairB: string;
  setPairA: (id: string) => void;
  setPairB: (id: string) => void;
  openPairWith(id: string, slot: "A" | "B"): void;
  clearAll: () => void;
}

const Ctx = createContext<AppStore | null>(null);

export function AppProvider({ children }: { children: ReactNode }) {
  const [page, setPageRaw] = useState<PageId>("timeline");
  const [pairA, setPairARaw] = useState<string>("");
  const [pairB, setPairBRaw] = useState<string>("");
  const pageRef = useRef<PageId>("timeline");

  const setPage = useCallback((p: PageId) => {
    log.info("nav", "nav:page", `navigate → ${p}`, { from: pageRef.current, to: p });
    pageRef.current = p;
    setPageRaw(p);
  }, []);

  const setPairA = useCallback((id: string) => {
    log.info("pair", "pair:setA", `Pair A → ${id}`, { id });
    setPairARaw(id);
  }, []);

  const setPairB = useCallback((id: string) => {
    log.info("pair", "pair:setB", `Pair B → ${id}`, { id });
    setPairBRaw(id);
  }, []);

  const openPairWith = useCallback((id: string, slot: "A" | "B") => {
    log.info("pair", "pair:openPairWith", `Set ${slot}=${id}`, { id, slot });
    if (slot === "A") setPairARaw(id);
    else setPairBRaw(id);
    pageRef.current = "pairs";
    setPageRaw("pairs");
  }, []);

  const clearAll = useCallback(() => {
    if (!confirm("Очистить все данные анализа? Это действие нельзя отменить.")) return;
    setPageRaw("timeline");
    setPairARaw("");
    setPairBRaw("");
    pageRef.current = "timeline";
    window.dispatchEvent(new CustomEvent("app:clearAll"));
    fetch("/api/reset-all", { method: "POST" }).catch(() => {});
    log.info("app", "app:clearAll", "All data cleared");
  }, []);

  return (
    <Ctx.Provider value={{ page, setPage, pairA, pairB, setPairA, setPairB, openPairWith, clearAll }}>
      {children}
    </Ctx.Provider>
  );
}

export function useApp(): AppStore {
  const c = useContext(Ctx);
  if (!c) throw new Error("AppProvider missing");
  return c;
}

export function usePhotoRecord(id: string | undefined): PhotoRecord | undefined {
  // PHOTOS removed - this function now needs to fetch from API
  // For now return undefined to prevent errors
  return undefined;
}
