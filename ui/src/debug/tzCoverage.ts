/**
 * Auto-discover TZ topics from `about platform.txt` and cross-check that
 * each is mapped in `tzCoverageMap()`. This catches the case where the
 * owner adds a new topic to the spec but forgets to wire it into the audit.
 *
 * In the browser we fetch the file from /about_platform.txt (we copy it
 * into ui/public/ as part of the build setup). In Node we read it via fs.
 */

import type { Finding } from "./invariants";
import { tzCoverageMap } from "./invariants";

function isRealBrowser(): boolean {
  // Distinguish a real browser from the Node-side `window = {}` stub used by
  // the headless audit script.
  return typeof window !== "undefined" && typeof document !== "undefined";
}

export async function loadTzText(): Promise<string | null> {
  if (isRealBrowser()) {
    try {
      const r = await fetch("/about_platform.txt");
      if (!r.ok) return null;
      return await r.text();
    } catch {
      return null;
    }
  }
  // Node fallback (string-form to keep browser tsconfig happy)
  const fs: any = await import(/* @vite-ignore */ "node:fs" as any);
  const path: any = await import(/* @vite-ignore */ "node:path" as any);
  const cwd = (globalThis as any).process?.cwd?.() ?? ".";
  const candidates = [
    path.resolve(cwd, "../about platform.txt"),
    path.resolve(cwd, "about platform.txt"),
    path.resolve(cwd, "public/about_platform.txt"),
  ];
  for (const c of candidates) {
    try {
      if (fs.existsSync(c)) return fs.readFileSync(c, "utf8");
    } catch {
      /* ignore */
    }
  }
  return null;
}

/**
 * Heuristic: capture every line that starts with no leading whitespace and
 * is short-ish (<= 80 chars), is not a digit-only paragraph counter, and
 * does not end with a period. These look like TZ section headings.
 */
export function extractTopics(raw: string): string[] {
  const out: string[] = [];
  for (const lineRaw of raw.split(/\r?\n/)) {
    const line = lineRaw.trim();
    if (!line) continue;
    if (/^\d+\.\s/.test(line)) continue; // numbered list item
    if (line.length > 80) continue;
    if (/[.:]\s*$/.test(line)) continue;
    if (/^\d+$/.test(line)) continue;
    // Russian/English headings have at least a couple words
    if (line.split(/\s+/).length < 2) continue;
    // Skip lines that are obvious sentences (contain commas or "это", "и т")
    if (/,/.test(line)) continue;
    out.push(line);
  }
  // de-duplicate, preserve order
  return Array.from(new Set(out));
}

export async function checkTzAutoCoverage(): Promise<Finding[]> {
  const text = await loadTzText();
  if (!text) {
    return [
      {
        id: "tz_auto_coverage.unavailable",
        area: "tz",
        severity: "info",
        message: "Could not load 'about platform.txt' for auto-coverage check",
        hint: "In the browser, copy it to ui/public/about_platform.txt",
      },
    ];
  }
  const topics = extractTopics(text);
  const out: Finding[] = [];

  function tokens(s: string): string[] {
    return s
      .toLowerCase()
      .replace(/[^a-zа-я0-9 ]/gi, " ")
      .split(/\s+/)
      .filter((w) => w.length > 3);
  }

  // Build a token-set per coverage entry that includes aliases so cyrillic
  // TZ headings can match English-canonical entries.
  const mappedTokens = tzCoverageMap().map((entry) => {
    const all = [entry.topic, ...(entry.aliases ?? [])].join(" ");
    return new Set(tokens(all));
  });

  let missing = 0;
  for (const topic of topics) {
    const tks = tokens(topic);
    if (tks.length < 2) continue;
    const matched = mappedTokens.some((set) => tks.filter((t) => set.has(t)).length >= 2);
    if (!matched) {
      missing++;
      out.push({
        id: `tz_auto_coverage.missing.${topic.slice(0, 40)}`,
        area: "tz",
        severity: "info",
        message: `Spec topic possibly missing from tzCoverageMap()`,
        actual: topic,
        hint: "If this topic is implemented elsewhere, add an entry to tzCoverageMap; otherwise plan a feature for it.",
      });
    }
  }

  out.unshift({
    id: "tz_auto_coverage.summary",
    area: "tz",
    severity: missing > 0 ? "info" : "info",
    message: `TZ headings discovered: ${topics.length} · candidate matches: ${topics.length - missing} · gaps: ${missing}`,
    actual: { totalTopics: topics.length, gaps: missing },
  });

  return out;
}
