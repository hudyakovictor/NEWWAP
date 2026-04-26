/**
 * Lazy-loaded index from photo URL to its dHash perceptual fingerprint.
 *
 * The index lives in `signal-report.json`, written by `npm run signals`.
 * In the browser we fetch the slim copy from `/signal-report.json`.
 * In Node (audit / cli) we read the full report from disk.
 *
 * This is the bridge that lets the algorithmic layer (`api.similarPhotos`,
 * the Pair analysis page, future signal-driven features) operate on real
 * pixel data rather than purely synthetic fields.
 */

let cache: Map<string, string> | null = null;
let loadPromise: Promise<Map<string, string>> | null = null;

function isRealBrowser(): boolean {
  return typeof window !== "undefined" && typeof document !== "undefined";
}

export async function getDhashIndex(): Promise<Map<string, string>> {
  if (cache) return cache;
  if (loadPromise) return loadPromise;
  loadPromise = (async () => {
    const map = new Map<string, string>();
    try {
      if (isRealBrowser()) {
        const r = await fetch("/signal-report.json");
        if (r.ok) {
          const j = await r.json();
          for (const e of j.entries ?? []) {
            if (e.dhash && e.url) map.set(e.url, e.dhash);
          }
        }
      } else {
        const fs: any = await import(/* @vite-ignore */ "node:fs" as any);
        const path: any = await import(/* @vite-ignore */ "node:path" as any);
        const cwd = (globalThis as any).process?.cwd?.() ?? ".";
        for (const c of [
          path.resolve(cwd, "signal-report.json"),
          path.resolve(cwd, "public/signal-report.json"),
          path.resolve(cwd, "ui/signal-report.json"),
        ]) {
          if (fs.existsSync(c)) {
            const j = JSON.parse(fs.readFileSync(c, "utf8"));
            for (const e of j.entries ?? []) {
              if (e.dhash && e.url) map.set(e.url, e.dhash);
            }
            break;
          }
        }
      }
    } catch {
      /* report unavailable — leave map empty, callers fall back gracefully */
    }
    cache = map;
    return map;
  })();
  return loadPromise;
}

/** Hamming distance between two same-length hex strings. Returns Infinity
 *  when either argument is missing so callers can branch cleanly. */
export function dhashDistance(a?: string, b?: string): number {
  if (!a || !b || a.length !== b.length) return Infinity;
  let d = 0;
  for (let i = 0; i < a.length; i += 2) {
    const x = parseInt(a.slice(i, i + 2), 16) ^ parseInt(b.slice(i, i + 2), 16);
    let v = x;
    v = v - ((v >> 1) & 0x55);
    v = (v & 0x33) + ((v >> 2) & 0x33);
    v = (v + (v >> 4)) & 0x0f;
    d += v;
  }
  return d;
}

/** Synchronous lookup; returns undefined until getDhashIndex() resolves. */
export function dhashFor(url: string): string | undefined {
  return cache?.get(url);
}
