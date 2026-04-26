/**
 * Central logging + validation system for the DEEPUTIN investigation notebook.
 *
 * Goals (as stated by the owner of the notebook):
 * 1. Log every piece of data that flows through the pipeline.
 * 2. Automatically cross-check values against predicted ranges and flag any
 *    unexpected deviations as "suspicious" even when they don't blow up.
 * 3. Make the full log stream available both in the browser console (for
 *    classical DevTools inspection) and inside the app (Logs page) with
 *    filtering, search and JSON drill-down.
 *
 * Runtime shape:
 *   window.deeputin = {
 *     logs: LogEntry[]             // append-only ring buffer
 *     dump(): void                 // console.table of all entries
 *     byCategory(cat): LogEntry[]  // filter helper
 *     suspicious(): LogEntry[]     // only entries flagged by validator
 *     clear(): void
 *     selfTest(): Promise<void>
 *   }
 */

export type LogLevel = "trace" | "debug" | "info" | "warn" | "error";

export type LogCategory =
  | "boot"
  | "api"
  | "nav"
  | "ui"
  | "pipeline"
  | "bayes"
  | "calibration"
  | "cache"
  | "ageing"
  | "pair"
  | "photo"
  | "validation"
  | "self_test";

export interface Violation {
  field: string;
  expected: string;  // human-readable expected range
  actual: unknown;
  severity: "info" | "warn" | "danger";
  note?: string;
}

export interface LogEntry {
  id: number;
  ts: number;              // epoch ms
  level: LogLevel;
  category: LogCategory;
  scope: string;           // e.g. "api:getPhotoDetail", "ui:open_modal"
  message: string;
  data?: unknown;
  durationMs?: number;
  violations?: Violation[]; // if validator flagged something
  suspicious?: boolean;     // convenience: violations.length > 0
}

const MAX_LOGS = 5000;
const buffer: LogEntry[] = [];
let idCounter = 0;

const subscribers = new Set<(e: LogEntry) => void>();

const LEVEL_STYLES: Record<LogLevel, string> = {
  trace: "color:#6b7a90",
  debug: "color:#38bdf8",
  info:  "color:#22c55e",
  warn:  "color:#f59e0b;font-weight:bold",
  error: "color:#ef4444;font-weight:bold",
};

const CATEGORY_STYLES: Record<LogCategory, string> = {
  boot:         "background:#0b3d91;color:#fff;padding:1px 4px;border-radius:2px",
  api:          "background:#063a2b;color:#a7f3d0;padding:1px 4px;border-radius:2px",
  nav:          "background:#3a1d6b;color:#ddd6fe;padding:1px 4px;border-radius:2px",
  ui:           "background:#1a2b44;color:#cfd8e6;padding:1px 4px;border-radius:2px",
  pipeline:     "background:#4a3208;color:#fde68a;padding:1px 4px;border-radius:2px",
  bayes:        "background:#4a0808;color:#fecaca;padding:1px 4px;border-radius:2px",
  calibration:  "background:#08434a;color:#bae6fd;padding:1px 4px;border-radius:2px",
  cache:        "background:#3b0764;color:#e9d5ff;padding:1px 4px;border-radius:2px",
  ageing:       "background:#4a2108;color:#fed7aa;padding:1px 4px;border-radius:2px",
  pair:         "background:#2c0950;color:#ddd6fe;padding:1px 4px;border-radius:2px",
  photo:        "background:#0c2e4a;color:#bfdbfe;padding:1px 4px;border-radius:2px",
  validation:   "background:#7f1d1d;color:#fecaca;padding:1px 4px;border-radius:2px;font-weight:bold",
  self_test:    "background:#166534;color:#bbf7d0;padding:1px 4px;border-radius:2px",
};

function push(entry: Omit<LogEntry, "id" | "ts" | "suspicious"> & { ts?: number }) {
  const e: LogEntry = {
    id: ++idCounter,
    ts: entry.ts ?? Date.now(),
    suspicious: (entry.violations?.length ?? 0) > 0,
    ...entry,
  };
  buffer.push(e);
  if (buffer.length > MAX_LOGS) buffer.splice(0, buffer.length - MAX_LOGS);

  // Console output
  const time = new Date(e.ts).toISOString().slice(11, 23);
  const prefix = `%c${time}%c %c${e.category}%c %c${e.level.toUpperCase()}`;
  const styles = [
    "color:#6b7a90", "",
    CATEGORY_STYLES[e.category] ?? "", "",
    LEVEL_STYLES[e.level],
  ];
  const dur = e.durationMs !== undefined ? ` (${e.durationMs}ms)` : "";
  if (e.suspicious) {
    // eslint-disable-next-line no-console
    console.groupCollapsed(`${prefix}%c %c⚠ ${e.scope}%c ${e.message}${dur}`, ...styles, "", "color:#ef4444;font-weight:bold", "");
    // eslint-disable-next-line no-console
    console.log("data:", e.data);
    // eslint-disable-next-line no-console
    console.warn("violations:", e.violations);
    // eslint-disable-next-line no-console
    console.groupEnd();
  } else if (e.data !== undefined) {
    // eslint-disable-next-line no-console
    console.groupCollapsed(`${prefix}%c %c${e.scope}%c ${e.message}${dur}`, ...styles, "", "color:#cfd8e6", "");
    // eslint-disable-next-line no-console
    console.log(e.data);
    // eslint-disable-next-line no-console
    console.groupEnd();
  } else {
    // eslint-disable-next-line no-console
    console.log(`${prefix}%c %c${e.scope}%c ${e.message}${dur}`, ...styles, "", "color:#cfd8e6", "");
  }

  subscribers.forEach((fn) => fn(e));
  return e;
}

/** Subscribe to new log entries (used by Logs page for live updates). */
export function subscribe(fn: (e: LogEntry) => void) {
  subscribers.add(fn);
  return () => subscribers.delete(fn);
}

export function getAllLogs(): LogEntry[] {
  return buffer.slice();
}

export function clearLogs() {
  buffer.length = 0;
  idCounter = 0;
  // eslint-disable-next-line no-console
  console.log("%cdeeputin logs cleared", "color:#6b7a90");
}

/* -------------------- Public logging API ------------------------------- */

export const log = {
  trace(category: LogCategory, scope: string, message: string, data?: unknown) {
    return push({ level: "trace", category, scope, message, data });
  },
  debug(category: LogCategory, scope: string, message: string, data?: unknown) {
    return push({ level: "debug", category, scope, message, data });
  },
  info(category: LogCategory, scope: string, message: string, data?: unknown) {
    return push({ level: "info", category, scope, message, data });
  },
  warn(category: LogCategory, scope: string, message: string, data?: unknown, violations?: Violation[]) {
    return push({ level: "warn", category, scope, message, data, violations });
  },
  error(category: LogCategory, scope: string, message: string, data?: unknown) {
    return push({ level: "error", category, scope, message, data });
  },
  /**
   * Report the result of a validation pass. If any violations are present,
   * the entry is automatically flagged as suspicious and visually stands out
   * in both console and Logs page.
   */
  validation(scope: string, message: string, data: unknown, violations: Violation[]) {
    const level: LogLevel =
      violations.some((v) => v.severity === "danger")
        ? "error"
        : violations.some((v) => v.severity === "warn")
        ? "warn"
        : violations.length
        ? "info"
        : "debug";
    return push({ level, category: "validation", scope, message, data, violations });
  },
  /** Time a function call and log its duration + result. */
  async time<T>(category: LogCategory, scope: string, message: string, fn: () => Promise<T>): Promise<T> {
    const t0 = performance.now();
    try {
      const result = await fn();
      const durationMs = +(performance.now() - t0).toFixed(1);
      push({ level: "debug", category, scope, message, data: result, durationMs });
      return result;
    } catch (err) {
      const durationMs = +(performance.now() - t0).toFixed(1);
      push({ level: "error", category, scope, message: `${message} FAILED`, data: err, durationMs });
      throw err;
    }
  },
};

/* -------------------- window.deeputin --------------------------------- */

if (typeof window !== "undefined") {
  const w = window as unknown as { deeputin?: Record<string, unknown> };
  w.deeputin = {
    logs: buffer,
    dump() {
      // eslint-disable-next-line no-console
      console.table(buffer.map((e) => ({
        id: e.id,
        ts: new Date(e.ts).toISOString().slice(11, 23),
        cat: e.category,
        level: e.level,
        scope: e.scope,
        msg: e.message,
        dur: e.durationMs,
        susp: e.suspicious ? "⚠" : "",
      })));
    },
    byCategory(cat: LogCategory) {
      return buffer.filter((e) => e.category === cat);
    },
    byScope(scope: string) {
      return buffer.filter((e) => e.scope.includes(scope));
    },
    suspicious() {
      return buffer.filter((e) => e.suspicious);
    },
    clear: clearLogs,
    help() {
      // eslint-disable-next-line no-console
      console.log(
        `%cdeeputin notebook — console helpers
%cdeeputin.dump()           full log table
deeputin.byCategory('api') filter by category
deeputin.byScope('photo')  filter by scope substring
deeputin.suspicious()      only entries with validation flags
deeputin.clear()           clear buffer
deeputin.selfTest()        run api self-test (populated after boot)`,
        "color:#38bdf8;font-weight:bold",
        "color:#cfd8e6"
      );
    },
  };
}
