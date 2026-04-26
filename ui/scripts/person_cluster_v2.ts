/**
 * Cluster myface photos into 2 persons using face stats (luminance + color).
 *
 * Different people have different skin tones and face positions in selfies.
 * Uses k-means clustering on [meanLum, meanR, meanG, meanB, cropW, cropH].
 *
 * Output: storage/myface_persons.json
 *   { generatedAt, method, clusters: [{ personId, files, count, centroid }, ...] }
 *
 * Usage: npx tsx scripts/person_cluster_v2.ts
 */

import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { resolve } from "node:path";

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
  centroid: number[];
}

interface Output {
  generatedAt: string;
  method: "kmeans_face_stats";
  k: number;
  totalPhotos: number;
  clusters: PersonCluster[];
}

function kmeans(
  data: number[][],
  k: number,
  maxIter = 100
): { assignments: number[]; centroids: number[][] } {
  const n = data.length;
  const dims = data[0].length;

  // Initialize centroids randomly
  const centroids: number[][] = [];
  const used = new Set<number>();
  while (centroids.length < k) {
    const idx = Math.floor(Math.random() * n);
    if (!used.has(idx)) {
      used.add(idx);
      centroids.push([...data[idx]]);
    }
  }

  const assignments = new Array(n).fill(0);

  for (let iter = 0; iter < maxIter; iter++) {
    // Assign points to nearest centroid
    let changed = false;
    for (let i = 0; i < n; i++) {
      let best = 0;
      let bestDist = Infinity;
      for (let c = 0; c < k; c++) {
        let dist = 0;
        for (let d = 0; d < dims; d++) {
          const diff = data[i][d] - centroids[c][d];
          dist += diff * diff;
        }
        if (dist < bestDist) {
          bestDist = dist;
          best = c;
        }
      }
      if (assignments[i] !== best) {
        assignments[i] = best;
        changed = true;
      }
    }

    if (!changed) break;

    // Recompute centroids
    const counts = new Array(k).fill(0);
    const sums = Array.from({ length: k }, () => new Array(dims).fill(0));

    for (let i = 0; i < n; i++) {
      const c = assignments[i];
      counts[c]++;
      for (let d = 0; d < dims; d++) {
        sums[c][d] += data[i][d];
      }
    }

    for (let c = 0; c < k; c++) {
      if (counts[c] > 0) {
        for (let d = 0; d < dims; d++) {
          centroids[c][d] = sums[c][d] / counts[c];
        }
      }
    }
  }

  return { assignments, centroids };
}

function main() {
  const cwd = process.cwd();

  // Load face stats
  const faceStatsPath = resolve(cwd, "src/data/face_stats_myface.json");
  const faceStats = JSON.parse(readFileSync(faceStatsPath, "utf8")) as Record<string, FaceStats>;

  // Build feature vectors: [meanLum, meanR, meanG, meanB, cropW, cropH]
  const files: string[] = [];
  const vectors: number[][] = [];

  for (const [file, stats] of Object.entries(faceStats)) {
    if (!stats) continue; // Skip photos without face_stats (SCRFD missed)
    files.push(file);
    vectors.push([
      stats.meanLum,
      stats.meanR,
      stats.meanG,
      stats.meanB,
      stats.cropW,
      stats.cropH,
    ]);
  }

  console.log(`[start] ${vectors.length} myface photos with face_stats`);

  if (vectors.length < 2) {
    console.error("[error] Need at least 2 photos with face_stats");
    process.exit(1);
  }

  // Normalize features (z-score)
  const dims = vectors[0].length;
  const means = new Array(dims).fill(0);
  const stds = new Array(dims).fill(0);

  for (let d = 0; d < dims; d++) {
    means[d] = vectors.reduce((sum, v) => sum + v[d], 0) / vectors.length;
    const variance = vectors.reduce((sum, v) => sum + Math.pow(v[d] - means[d], 2), 0) / vectors.length;
    stds[d] = Math.sqrt(variance) || 1; // Avoid div by zero
  }

  const normalized = vectors.map((v) => v.map((x, d) => (x - means[d]) / stds[d]));

  // K-means with k=2 (2 people)
  const K = 2;
  const { assignments, centroids } = kmeans(normalized, K);

  // Build clusters
  const clusters: PersonCluster[] = [];
  for (let c = 0; c < K; c++) {
    const clusterFiles = files.filter((_, i) => assignments[i] === c);
    clusters.push({
      personId: `person${String.fromCharCode(65 + c)}`, // personA, personB
      files: clusterFiles,
      count: clusterFiles.length,
      centroid: centroids[c].map((x, d) => x * stds[d] + means[d]), // Denormalize
    });
  }

  // Sort by size (largest first)
  clusters.sort((a, b) => b.count - a.count);

  console.log(`[clusters] ${K} persons identified:`);
  clusters.forEach((c) => {
    console.log(`  ${c.personId}: ${c.count} photos`);
    console.log(`    centroid: lum=${c.centroid[0].toFixed(1)}, R=${c.centroid[1].toFixed(1)}, G=${c.centroid[2].toFixed(1)}, B=${c.centroid[3].toFixed(1)}`);
  });

  // Write output
  const output: Output = {
    generatedAt: new Date().toISOString(),
    method: "kmeans_face_stats",
    k: K,
    totalPhotos: files.length,
    clusters,
  };

  const outDir = resolve(cwd, "storage");
  mkdirSync(outDir, { recursive: true });
  const outPath = resolve(outDir, "myface_persons.json");
  writeFileSync(outPath, JSON.stringify(output, null, 2));
  console.log(`[write] ${outPath}`);
}

main();
