/**
 * Cluster myface photos into persons using dHash similarity.
 *
 * Since myface contains 2 confirmed people, this script uses union-find
 * on perceptual hash distances to separate them. Photos of the same person
 * will have similar composition (face position, background) while photos
 * of different people will have different dHash values.
 *
 * Output: storage/myface_persons.json
 *   { generatedAt, threshold, clusters: [{ personId, files, count }, ...] }
 *
 * Usage: npx tsx scripts/person_cluster.ts [--threshold 10]
 */

import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { resolve, dirname } from "node:path";

interface Sig {
  file: string;
  url: string;
  dhash?: string;
  sha256: string;
  width: number;
  height: number;
}

interface Report {
  count: number;
  entries: Sig[];
}

interface PersonCluster {
  personId: string;
  files: string[];
  count: number;
  sampleDhashes: string[];
}

interface Output {
  generatedAt: string;
  threshold: number;
  totalPhotos: number;
  clusters: PersonCluster[];
  unclustered: string[];
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

function main() {
  const cwd = process.cwd();
  const reportPath = resolve(cwd, "public/signal-report.json");
  const report = JSON.parse(readFileSync(reportPath, "utf8")) as Report;

  const argThreshold = process.argv.indexOf("--threshold");
  const THRESHOLD = argThreshold > 0 ? +process.argv[argThreshold + 1] || 10 : 10;

  // Filter for myface photos only
  const myfaceItems = report.entries.filter(
    (e) => e.dhash && e.url && e.url.includes("photos_myface")
  );
  console.log(`[start] ${myfaceItems.length} myface photos with dHash · threshold ${THRESHOLD}`);

  if (myfaceItems.length === 0) {
    console.error("[error] No myface photos found in signal-report.json");
    process.exit(1);
  }

  // Union-find
  const parent = new Map<number, number>();
  for (let i = 0; i < myfaceItems.length; i++) parent.set(i, i);
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

  // O(N^2) pairwise scan
  let pairCount = 0;
  for (let i = 0; i < myfaceItems.length; i++) {
    for (let j = i + 1; j < myfaceItems.length; j++) {
      if (hamming(myfaceItems[i].dhash!, myfaceItems[j].dhash!) <= THRESHOLD) {
        union(i, j);
        pairCount++;
      }
    }
  }
  console.log(`[pairs] ${pairCount} similar pairs found (d ≤ ${THRESHOLD})`);

  // Build clusters
  const clusterMap = new Map<number, number[]>();
  for (let i = 0; i < myfaceItems.length; i++) {
    const root = find(i);
    if (!clusterMap.has(root)) clusterMap.set(root, []);
    clusterMap.get(root)!.push(i);
  }

  // Sort clusters by size (largest first)
  const clusters = Array.from(clusterMap.entries())
    .map(([root, indices]) => ({
      root,
      indices,
      files: indices.map((i) => myfaceItems[i].file),
      dhashes: indices.map((i) => myfaceItems[i].dhash!),
    }))
    .sort((a, b) => b.indices.length - a.indices.length);

  console.log(`[clusters] ${clusters.length} total clusters`);
  clusters.forEach((c, i) => {
    console.log(`  cluster ${i + 1}: ${c.indices.length} photos`);
  });

  // Expect 2 main clusters (the 2 people), rest are noise/small
  const MIN_CLUSTER_SIZE = 10;
  const mainClusters = clusters.filter((c) => c.indices.length >= MIN_CLUSTER_SIZE);
  const smallClusters = clusters.filter((c) => c.indices.length < MIN_CLUSTER_SIZE);

  console.log(`[main] ${mainClusters.length} clusters with ≥${MIN_CLUSTER_SIZE} photos`);

  // Build output
  const output: Output = {
    generatedAt: new Date().toISOString(),
    threshold: THRESHOLD,
    totalPhotos: myfaceItems.length,
    clusters: mainClusters.map((c, idx) => ({
      personId: `person${String.fromCharCode(65 + idx)}`, // personA, personB, ...
      files: c.files,
      count: c.files.length,
      sampleDhashes: c.dhashes.slice(0, 5), // First 5 for reference
    })),
    unclustered: smallClusters.flatMap((c) => c.files),
  };

  // Write output
  const outDir = resolve(cwd, "storage");
  mkdirSync(outDir, { recursive: true });
  const outPath = resolve(outDir, "myface_persons.json");
  writeFileSync(outPath, JSON.stringify(output, null, 2));
  console.log(`[write] ${outPath}`);
  console.log(`[done] Assigned ${output.clusters.reduce((sum, c) => sum + c.count, 0)} photos to ${output.clusters.length} persons`);

  if (output.unclustered.length > 0) {
    console.log(`[warn] ${output.unclustered.length} photos remain unclustered (small clusters)`);
  }
}

main();
