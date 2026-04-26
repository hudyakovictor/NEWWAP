/**
 * Tiny seeded PRNG (mulberry32). All "random" pipeline outputs go through
 * this so audits stay reproducible.
 *
 * The seed is derived from a stable string id (photo id, year, etc.) via
 * cheap FNV-1a so the same input always yields the same output.
 */

export function fnv1a(s: string): number {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = (h + ((h << 1) + (h << 4) + (h << 7) + (h << 8) + (h << 24))) >>> 0;
  }
  return h >>> 0;
}

export function mulberry32(seed: number): () => number {
  let s = seed >>> 0;
  return () => {
    s = (s + 0x6d2b79f5) >>> 0;
    let t = s;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function rngFor(...parts: Array<string | number>): () => number {
  return mulberry32(fnv1a(parts.join("|")));
}
