/**
 * Build transitive near-duplicate clusters from the signal report.
 *
 * Two photos are "the same image" if their dHash Hamming distance is below
 * THRESHOLD. The relation is transitive (union-find), so a chain like
 * A↔B (d=2), B↔C (d=3) collapses A,B,C into one cluster.
 *
 * Output: storage/duplicate-clusters.json
 *   { generatedAt, threshold, clusters: [{ id, files, dHashes, yearSpan, isCrossYear }, ...] }
 *
 * Usage: npx tsx scripts/duplicate_clusters.ts [--threshold 5]
 */

import { readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";

interface Sig {
  file: string;
  url: string;
  dhash?: string;
  sha256: string;
}
interface Report {
  count: number;
  entries: Sig[];
}

function hamming(a: string, b: string): number {
  if (!a || !b || a.length !== b.length) return Infinity;
  let d = 0;
  for (let i = 0; i < a.length; i += 2) {
    let v = parseInt(a.slice(i, i + 2), 16) ^ parseInt(b.slice(i, i + 2), 16);
    v = v - ((v >> 1) & 0x55);
    v = (v & 0x33) + ((v >> 2) & 0x33);
    v = (v + (v >> 4)) & 0x0f;
    d += v;
  }
  return d;
}

function yearOf(file: string): number | null {
  const m = /^(\d{4})_/.exec(file);
  return m ? +m[1] : null;
}

function main() {
  const cwd = process.cwd();
  const reportPath = resolve(cwd, "public/signal-report.json");
  const report = JSON.parse(readFileSync(reportPath, "utf8")) as Report;

  const argThreshold = process.argv.indexOf("--threshold");
  const THRESHOLD = argThreshold > 0 ? +process.argv[argThreshold + 1] || 5 : 5;

  const items = report.entries.filter((e) => e.dhash);
  console.log(`[start] ${items.length} entries with dHash · threshold ${THRESHOLD}`);

  // Union-find
  const parent = new Map<number, number>();
  for (let i = 0; i < items.length; i++) parent.set(i, i);
  const find = (x: number): number => {
    let r = x;
    while (parent.get(r)! !== r) r = parent.get(r)!;
    while (parent.get(x)! !== r) {
      const n = parent.get(x)!;
      parent.set(x, r);
      x = n;
    }
    return r;
  };
  const union = (a: number, b: number) => {
    const ra = find(a);
    const rb = find(b);
    if (ra !== rb) parent.set(ra, rb);
  };

  // O(N^2) pairwise scan — 1837^2 ≈ 3.4M comparisons, ~3 sec.
  let pairCount = 0;
  for (let i = 0; i < items.length; i++) {
    for (let j = i + 1; j < items.length; j++) {
      if (hamming(items[i].dhash!, items[j].dhash!) <= THRESHOLD) {
        union(i, j);
        pairCount++;
      }
    }
    if (i % 200 === 0) console.log(`  scanned ${i}/${items.length} (${pairCount} pairs)`);
  }

  // Group by root
  const groups = new Map<number, number[]>();
  for (let i = 0; i < items.length; i++) {
    const r = find(i);
    if (!groups.has(r)) groups.set(r, []);
    groups.get(r)!.push(i);
  }

  // Keep only clusters of size >= 2
  const clusters = Array.from(groups.values())
    .filter((idxs) => idxs.length >= 2)
    .map((idxs, k) => {
      const members = idxs.map((i) => items[i]);
      const years = members.map((m) => yearOf(m.file)).filter((y): y is number => y !== null);
      const yearSet = new Set(years);
      const yearSpan = years.length > 1 ? Math.max(...years) - Math.min(...years) : 0;
      return {
        id: `cluster-${k.toString().padStart(3, "0")}`,
        size: members.length,
        files: members.map((m) => m.file),
        urls: members.map((m) => m.url),
        years: members.map((m) => yearOf(m.file)),
        distinctYears: Array.from(yearSet).sort(),
        yearSpan,
        isCrossYear: yearSet.size > 1,
        sha256s: Array.from(new Set(members.map((m) => m.sha256))),
        dhashes: Array.from(new Set(members.map((m) => m.dhash!))),
      };
    })
    .sort((a, b) => b.size - a.size || b.yearSpan - a.yearSpan);

  const out = {
    generatedAt: new Date().toISOString(),
    threshold: THRESHOLD,
    totalPhotos: items.length,
    pairCount,
    clusters,
    summary: {
      total: clusters.length,
      crossYear: clusters.filter((c) => c.isCrossYear).length,
      sameYear: clusters.filter((c) => !c.isCrossYear).length,
      maxSize: clusters.length > 0 ? Math.max(...clusters.map((c) => c.size)) : 0,
      maxYearSpan: clusters.length > 0 ? Math.max(...clusters.map((c) => c.yearSpan)) : 0,
      photosInClusters: clusters.reduce((acc, c) => acc + c.size, 0),
    },
  };

  const outPath = resolve(cwd, "../storage/duplicate-clusters.json");
  writeFileSync(outPath, JSON.stringify(out, null, 2));
  // Also bundle into UI public for in-app use
  const publicPath = resolve(cwd, "public/duplicate-clusters.json");
  writeFileSync(publicPath, JSON.stringify(out, null, 2));

  console.log(`\n[done] ${clusters.length} clusters (${out.summary.crossYear} cross-year, ${out.summary.sameYear} same-year)`);
  console.log(`  photos in clusters: ${out.summary.photosInClusters}`);
  console.log(`  max cluster size: ${out.summary.maxSize}`);
  console.log(`  max year span: ${out.summary.maxYearSpan}`);
  console.log(`  written: ${outPath}`);
  console.log(`  bundled: ${publicPath}`);

  console.log(`\nTop 10 clusters by size:`);
  for (const c of clusters.slice(0, 10)) {
    const yearStr = c.distinctYears.length > 0 ? c.distinctYears.join(", ") : "no-date";
    const flag = c.isCrossYear ? " ⚠ cross-year" : "";
    console.log(`  ${c.id} · size ${c.size} · years [${yearStr}] · span ${c.yearSpan}y${flag}`);
    for (const f of c.files.slice(0, 6)) console.log(`      ${f}`);
    if (c.files.length > 6) console.log(`      … +${c.files.length - 6} more`);
  }
}

main();
