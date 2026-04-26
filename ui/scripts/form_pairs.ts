/**
 * Form same-person pairs for calibration from myface photos.
 *
 * Within each person cluster, form pairs where:
 * - Δyaw ≤ 15° (similar pose)
 * - Both have face_stats (for light categorization)
 * - Max 50 pairs per person per pose bucket (performance cap)
 *
 * Output: storage/myface_pairs.json
 *   { generatedAt, totalPairs, pairs: [{ a, b, person, deltaYaw, bucket }, ...] }
 *
 * Usage: npx tsx scripts/form_pairs.ts [--max_yaw 15] [--max_per_bucket 50]
 */

import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { resolve } from "node:path";

interface PoseEntry {
  yaw: number | null;
  pitch: number | null;
  roll: number | null;
  source: "hpe" | "3ddfa" | "none";
  classification: string;
}

interface FaceStats {
  meanLum: number;
  stdLum: number;
  meanR: number;
  meanG: number;
  meanB: number;
  stdR: number;
  stdG: number;
  stdB: number;
  cropW: number;
  cropH: number;
}

interface PersonCluster {
  personId: string;
  files: string[];
  count: number;
}

interface PersonsFile {
  generatedAt: string;
  method: string;
  clusters: PersonCluster[];
}

interface Pair {
  a: string;
  b: string;
  person: string;
  deltaYaw: number;
  poseA: string;
  poseB: string;
  lightCategory: string; // derived from face_stats
  bucketKey: string; // poseA_lightCategory (for calibration)
}

interface Output {
  generatedAt: string;
  maxYawDelta: number;
  maxPerBucket: number;
  totalPairs: number;
  byPerson: Record<string, number>;
  byBucket: Record<string, number>;
  pairs: Pair[];
}

function getLightCategory(stats: FaceStats): string {
  // Simple threshold-based lighting categorization from face_stats
  if (stats.meanLum > 150) return "studio";
  if (stats.meanLum < 80) return "low_light";
  return "daylight";
}

function main() {
  const cwd = process.cwd();

  // Parse args
  const argMaxYaw = process.argv.indexOf("--max_yaw");
  const MAX_YAW_DELTA = argMaxYaw > 0 ? +process.argv[argMaxYaw + 1] || 15 : 15;

  const argMaxPerBucket = process.argv.indexOf("--max_per_bucket");
  const MAX_PER_BUCKET = argMaxPerBucket > 0 ? +process.argv[argMaxPerBucket + 1] || 50 : 50;

  // Load data
  const personsPath = resolve(cwd, "storage/myface_persons.json");
  const persons = JSON.parse(readFileSync(personsPath, "utf8")) as PersonsFile;

  const posesPath = resolve(cwd, "src/data/poses_myface.json");
  const poses = JSON.parse(readFileSync(posesPath, "utf8")) as Record<string, PoseEntry>;

  const faceStatsPath = resolve(cwd, "src/data/face_stats_myface.json");
  const faceStats = JSON.parse(readFileSync(faceStatsPath, "utf8")) as Record<string, FaceStats | null>;

  console.log(`[start] Forming pairs with |Δyaw| ≤ ${MAX_YAW_DELTA}, max ${MAX_PER_BUCKET} per bucket`);

  const allPairs: Pair[] = [];
  const byPerson: Record<string, number> = {};
  const byBucket: Record<string, number> = {};

  for (const cluster of persons.clusters) {
    const personId = cluster.personId;
    const files = cluster.files;

    // Build list of valid photos (have pose and face_stats)
    const validPhotos = files
      .map((f) => ({
        file: f,
        pose: poses[f],
        stats: faceStats[f],
      }))
      .filter((p) => p.pose && p.pose.yaw !== null && p.stats);

    console.log(`[${personId}] ${validPhotos.length}/${files.length} photos with pose + face_stats`);

    const personPairs: Pair[] = [];

    // O(N^2) pairwise within person
    for (let i = 0; i < validPhotos.length; i++) {
      for (let j = i + 1; j < validPhotos.length; j++) {
        const a = validPhotos[i];
        const b = validPhotos[j];

        const deltaYaw = Math.abs(a.pose.yaw! - b.pose.yaw!);
        if (deltaYaw > MAX_YAW_DELTA) continue;

        // Use light category from photo A (they're similar enough)
        const lightCat = getLightCategory(a.stats!);
        const bucketKey = `${a.pose.classification}_${lightCat}`;

        personPairs.push({
          a: a.file,
          b: b.file,
          person: personId,
          deltaYaw: +deltaYaw.toFixed(2),
          poseA: a.pose.classification,
          poseB: b.pose.classification,
          lightCategory: lightCat,
          bucketKey,
        });
      }
    }

    // Cap pairs per bucket
    const bucketCounts = new Map<string, number>();
    const cappedPairs: Pair[] = [];

    for (const pair of personPairs) {
      const count = bucketCounts.get(pair.bucketKey) || 0;
      if (count < MAX_PER_BUCKET) {
        bucketCounts.set(pair.bucketKey, count + 1);
        cappedPairs.push(pair);
      }
    }

    console.log(`[${personId}] ${personPairs.length} raw pairs → ${cappedPairs.length} after capping`);

    allPairs.push(...cappedPairs);
    byPerson[personId] = cappedPairs.length;

    for (const pair of cappedPairs) {
      byBucket[pair.bucketKey] = (byBucket[pair.bucketKey] || 0) + 1;
    }
  }

  // Sort pairs by person then by deltaYaw
  allPairs.sort((a, b) => {
    if (a.person !== b.person) return a.person.localeCompare(b.person);
    return a.deltaYaw - b.deltaYaw;
  });

  console.log(`[total] ${allPairs.length} calibration pairs formed`);
  console.log(`[buckets] ${Object.keys(byBucket).length} unique pose+light buckets:`);
  for (const [bucket, count] of Object.entries(byBucket).sort((a, b) => b[1] - a[1])) {
    console.log(`  ${bucket}: ${count} pairs`);
  }

  // Write output
  const output: Output = {
    generatedAt: new Date().toISOString(),
    maxYawDelta: MAX_YAW_DELTA,
    maxPerBucket: MAX_PER_BUCKET,
    totalPairs: allPairs.length,
    byPerson,
    byBucket,
    pairs: allPairs,
  };

  const outDir = resolve(cwd, "storage");
  mkdirSync(outDir, { recursive: true });
  const outPath = resolve(outDir, "myface_pairs.json");
  writeFileSync(outPath, JSON.stringify(output, null, 2));
  console.log(`[write] ${outPath}`);
}

main();
