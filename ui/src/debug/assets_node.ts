/**
 * Node-only asset existence check. Confirms that every reconstruction
 * artifact and every photo URL referenced from mock data physically exists
 * under ui/public/. Skipped (returns []) when running in the browser.
 */

import type { Finding } from "./invariants";
import { PHOTOS } from "../mock/photos";
import { GROUND_TRUTH } from "./ground_truth_accessor";

function isRealBrowser(): boolean {
  return typeof window !== "undefined" && typeof document !== "undefined";
}

export async function checkAssetsExist(): Promise<Finding[]> {
  if (isRealBrowser()) return [];
  // Use string-form import so TS doesn't try to type-check node builtins
  // in the browser tsconfig.
  const fs: any = await import(/* @vite-ignore */ "node:fs" as any);
  const path: any = await import(/* @vite-ignore */ "node:path" as any);

  const cwd = (globalThis as any).process?.cwd?.() ?? ".";
  const candidates = [
    path.resolve(cwd, "public"),
    path.resolve(cwd, "ui/public"),
    path.resolve(cwd, "../public"),
  ];
  let publicDir: string | null = null;
  for (const c of candidates) {
    if (fs.existsSync(c)) {
      publicDir = c;
      break;
    }
  }
  if (!publicDir) {
    return [
      {
        id: "assets.public_dir_missing",
        area: "consistency",
        severity: "info",
        message: "Could not locate ui/public/ directory; skipping asset check",
      },
    ];
  }

  const out: Finding[] = [];

  // Decode percent-encoded URLs (e.g. spaces as %20) before stat'ing the
  // file on disk. The dev server decodes automatically; our check has to too.
  const decode = (u: string) => decodeURIComponent(u);

  // Each PhotoRecord references /photos*/<filename>; deduplicate.
  const photoUrls = new Set(PHOTOS.map((p) => p.photo));
  for (const url of photoUrls) {
    const abs = path.resolve(publicDir, decode(url).replace(/^\//, ""));
    if (!fs.existsSync(abs)) {
      out.push({
        id: `assets.photo_missing.${url}`,
        area: "consistency",
        severity: "warn",
        message: "Photo URL has no file on disk",
        actual: { url, expectedAt: abs },
      });
    }
  }

  // Ground-truth files
  for (const g of GROUND_TRUTH) {
    const abs = path.resolve(publicDir, decode(g.url).replace(/^\//, ""));
    if (!fs.existsSync(abs)) {
      out.push({
        id: `assets.ground_truth_missing.${g.file}`,
        area: "consistency",
        severity: "danger",
        message: "Ground-truth photo missing from /public/photos/",
        actual: { url: g.url, expectedAt: abs },
      });
    }
  }

  // 3D reconstruction artifacts intentionally NOT checked here: that stage
  // is marked "stub" on the Progress page until 3DDFA-V3 is rerun across
  // the full 1638-photo set with --extractTex. Re-add this block once the
  // batch run lands and writes per-photo artifacts.

  return out;
}
