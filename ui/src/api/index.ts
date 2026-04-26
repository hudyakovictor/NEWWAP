import { loggedBackend } from "./logged";
import type { Backend } from "./types";

// Swap the inner backend (mock → http) in src/api/logged.ts when ready.
// Every call passes through logging + validation middleware by design.
export const api: Backend = loggedBackend;
export type { Backend };
export * from "./types";
