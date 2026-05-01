/**
 * Build transitive near-duplicate clusters from the signal report,
 * **grouped by pose classification** so that clustering reflects
 * visual identity within the same pose rather than just pose similarity.
 *
 * Two photos are "the same image" if their dHash Hamming distance is below
 * THRESHOLD. The relation is transitive (union-find), so a chain like
 * A↔B (d=2), B↔C (d=3) collapses A,B,C into one cluster.
 *
 * Clustering is done **per pose bucket** (frontal, ¾-left, ¾-right,
 * profile-left, profile-right) because dHash captures composition/pose
 * similarity. If we cluster across all poses, the dominant split will
 * be by pose angle rather than by identity.
 *
 * Output: storage/duplicate-clusters.json
 *   { generatedAt, threshold, clusters, poseBuckets }
 *
 * Usage: npx tsx scripts/duplicate_clusters.ts [--threshold 5]
 */

import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { resolve, dirname } from "node:path";

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

// Pose classification from filename-based heuristics + pose JSON
interface PoseEntry {
  yaw: number | null;
  pitch: number | null;
  roll: number | null;
  source: string;
  classification: string;
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

type PoseBucket = "frontal" | "three_quarter_left" | "three_quarter_right" | "profile_left" | "profile_right" | "none";

function classifyPose(yaw: number | null): PoseBucket {
  if (yaw == null) return "none";
  const abs = Math.abs(yaw);
  if (abs < 25) return "frontal";
  if (abs < 55) return yaw > 0 ? "three_quarter_right" : "three_quarter_left";
  return yaw > 0 ? "profile_right" : "profile_left";
}

interface ClusterResult {
  id: string;
  size: number;
  files: string[];
  urls: string[];
  years: (number | null)[];
  distinctYears: number[];
  yearSpan: number;
  isCrossYear: boolean;
  sha256s: string[];
  dhashes: string[];
  poseBucket: PoseBucket;
}

function clusterItems(items: Sig[], threshold: number, poseBucket: PoseBucket, clusterOffset: number): ClusterResult[] {
  if (items.length < 2) return [];

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

  let pairCount = 0;
  for (let i = 0; i < items.length; i++) {
    for (let j = i + 1; j < items.length; j++) {
      if (hamming(items[i].dhash!, items[j].dhash!) <= threshold) {
        union(i, j);
        pairCount++;
      }
    }
  }

  // Group by root
  const groups = new Map<number, number[]>();
  for (let i = 0; i < items.length; i++) {
    const r = find(i);
    if (!groups.has(r)) groups.set(r, []);
    groups.get(r)!.push(i);
  }

  // Keep only clusters of size >= 2
  return Array.from(groups.values())
    .filter((idxs) => idxs.length >= 2)
    .map((idxs, k) => {
      const members = idxs.map((i) => items[i]);
      const years = members.map((m) => yearOf(m.file)).filter((y): y is number => y !== null);
      const yearSet = new Set(years);
      const yearSpan = years.length > 1 ? Math.max(...years) - Math.min(...years) : 0;
      return {
        id: `cluster-${(clusterOffset + k).toString().padStart(3, "0")}`,
        size: members.length,
        files: members.map((m) => m.file),
        urls: members.map((m) => m.url),
        years: members.map((m) => yearOf(m.file)),
        distinctYears: Array.from(yearSet).sort(),
        yearSpan,
        isCrossYear: yearSet.size > 1,
        sha256s: Array.from(new Set(members.map((m) => m.sha256))),
        dhashes: Array.from(new Set(members.map((m) => m.dhash!))),
        poseBucket,
      };
    });
}

function main() {
  const cwd = process.cwd();
  const reportPath = resolve(cwd, "public/signal-report.json");
  const report = JSON.parse(readFileSync(reportPath, "utf8")) as Report;

  // Load pose data for classification
  const mainPosesPath = resolve(cwd, "src/data/poses_main.json");
  const myfacePosesPath = resolve(cwd, "src/data/poses_myface.json");
  let mainPoses: Record<string, PoseEntry> = {};
  let myfacePoses: Record<string, PoseEntry> = {};
  try {
    mainPoses = JSON.parse(readFileSync(mainPosesPath, "utf8"));
  } catch { console.log("[warn] poses_main.json not found, using heuristic classification"); }
  try {
    myfacePoses = JSON.parse(readFileSync(myfacePosesPath, "utf8"));
  } catch { console.log("[warn] poses_myface.json not found, using heuristic classification"); }

  const argThreshold = process.argv.indexOf("--threshold");
  const THRESHOLD = argThreshold > 0 ? +process.argv[argThreshold + 1] || 5 : 5;

  const items = report.entries.filter((e) => e.dhash);
  console.log(`[start] ${items.length} entries with dHash · threshold ${THRESHOLD}`);

  // Classify each item into a pose bucket
  const poseBuckets = new Map<PoseBucket, Sig[]>();
  const BUCKET_NAMES: PoseBucket[] = ["frontal", "three_quarter_left", "three_quarter_right", "profile_left", "profile_right", "none"];
  for (const b of BUCKET_NAMES) poseBuckets.set(b, []);

  for (const item of items) {
    // Try to find pose data by filename
    const filename = item.file;
    const poseEntry = mainPoses[filename] || myfacePoses[filename];
    let bucket: PoseBucket;
    if (poseEntry?.classification && poseEntry.classification !== "none") {
      bucket = poseEntry.classification as PoseBucket;
    } else if (poseEntry?.yaw != null) {
      bucket = classifyPose(poseEntry.yaw);
    } else {
      bucket = "none";
    }
    poseBuckets.get(bucket)!.push(item);
  }

  console.log("[pose distribution]");
  for (const [bucket, bucketItems] of poseBuckets) {
    console.log(`  ${bucket}: ${bucketItems.length} фото`);
  }

  // Cluster within each pose bucket
  const allClusters: ClusterResult[] = [];
  let clusterOffset = 0;
  for (const [bucket, bucketItems] of poseBuckets) {
    if (bucketItems.length < 2) continue;
    console.log(`\n[clustering] ${bucket}: ${bucketItems.length} фото`);
    const clusters = clusterItems(bucketItems, THRESHOLD, bucket, clusterOffset);
    console.log(`  → ${clusters.length} кластеров`);
    allClusters.push(...clusters);
    clusterOffset += clusters.length;
  }

  // Sort by size descending
  allClusters.sort((a, b) => b.size - a.size || b.yearSpan - a.yearSpan);

  // Re-index after sort
  allClusters.forEach((c, i) => {
    c.id = `cluster-${(i + 1).toString().padStart(3, "0")}`;
  });

  const poseBucketSummary: Record<string, { count: number; clusters: number; photosInClusters: number }> = {};
  for (const [bucket, bucketItems] of poseBuckets) {
    const bucketClusters = allClusters.filter((c) => c.poseBucket === bucket);
    poseBucketSummary[bucket] = {
      count: bucketItems.length,
      clusters: bucketClusters.length,
      photosInClusters: bucketClusters.reduce((a, c) => a + c.size, 0),
    };
  }

  const out = {
    generatedAt: new Date().toISOString(),
    threshold: THRESHOLD,
    totalPhotos: items.length,
    clusterMode: "per_pose_bucket",
    poseBucketSummary,
    clusters: allClusters,
    summary: {
      total: allClusters.length,
      crossYear: allClusters.filter((c) => c.isCrossYear).length,
      sameYear: allClusters.filter((c) => !c.isCrossYear).length,
      maxSize: allClusters.length > 0 ? Math.max(...allClusters.map((c) => c.size)) : 0,
      maxYearSpan: allClusters.length > 0 ? Math.max(...allClusters.map((c) => c.yearSpan)) : 0,
      photosInClusters: allClusters.reduce((acc, c) => acc + c.size, 0),
    },
  };

  const storagePath = resolve(cwd, "../storage/duplicate-clusters.json");
  try { mkdirSync(dirname(storagePath), { recursive: true }); } catch {}
  writeFileSync(storagePath, JSON.stringify(out, null, 2));
  // Also bundle into UI public for in-app use
  const publicPath = resolve(cwd, "public/duplicate-clusters.json");
  writeFileSync(publicPath, JSON.stringify(out, null, 2));

  console.log(`\n[done] ${allClusters.length} кластеров (${out.summary.crossYear} межгодовых, ${out.summary.sameYear} внутригодовых)`);
  console.log(`  фото в кластерах: ${out.summary.photosInClusters}`);
  console.log(`  макс. размер кластера: ${out.summary.maxSize}`);
  console.log(`  макс. размах лет: ${out.summary.maxYearSpan}`);

  console.log(`\nПо бакетам ракурса:`);
  for (const [bucket, info] of Object.entries(poseBucketSummary)) {
    console.log(`  ${bucket}: ${info.count} фото → ${info.clusters} кластеров (${info.photosInClusters} фото в кластерах)`);
  }

  console.log(`\nТоп-10 кластеров:`);
  for (const c of allClusters.slice(0, 10)) {
    const yearStr = c.distinctYears.length > 0 ? c.distinctYears.join(", ") : "без даты";
    const flag = c.isCrossYear ? " ⚠ межгодовой" : "";
    console.log(`  ${c.id} · ${c.poseBucket} · размер ${c.size} · годы [${yearStr}] · размах ${c.yearSpan}г${flag}`);
    for (const f of c.files.slice(0, 4)) console.log(`      ${f}`);
    if (c.files.length > 4) console.log(`      … +${c.files.length - 4} ещё`);
  }

  console.log(`\nЗаписано: ${storagePath}`);
  console.log(`Скопировано: ${publicPath}`);
}

main();
