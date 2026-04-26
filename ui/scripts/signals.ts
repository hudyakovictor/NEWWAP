/**
 * Real-photo signal extractor.
 *
 * For every JPEG under ui/public/photos/ this computes:
 *   - SHA-256 of the file bytes (uniqueness fingerprint)
 *   - file size in bytes
 *   - JPEG width/height parsed from the SOF0 marker
 *   - first 8 bytes of the file as a hex preview (lets us spot truncated/
 *     non-JPEG files even when the extension lies)
 *
 * Output is written to:
 *   - ./signal-report.json     (full report, AI-friendly)
 *   - public/signal-report.json (smaller subset bundled into the app so
 *                                the browser can fetch it)
 *
 * Run:  npm run signals
 */

import { createHash } from "node:crypto";
import { readdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { resolve, basename } from "node:path";
// @ts-expect-error - jpeg-js ships its own types but we don't need them strictly typed here
import jpeg from "jpeg-js";

interface SignalEntry {
  file: string;
  url: string;
  bytes: number;
  sha256: string;
  width?: number;
  height?: number;
  format: "jpeg" | "png" | "unknown";
  magic: string;
  /** dHash perceptual fingerprint (64-bit) as 16-char hex, or null if it
   *  could not be computed (non-JPEG / decode error). */
  dhash?: string;
  /** average luminance of the 8×8 thumbnail used for dhash, [0..255] */
  avgLuminance?: number;
}

interface SignalReport {
  generatedAt: string;
  rootDir: string;
  count: number;
  entries: SignalEntry[];
  hashIndex: Record<string, string[]>;     // sha256 → [file, file, ...]
  duplicates: Array<{ sha256: string; files: string[] }>;
  filesizeBytesTotal: number;
  /** Pairwise Hamming distances on the dHash, sorted ascending. Limited to
   *  top-N closest pairs to keep the report compact. */
  closestDhashPairs: Array<{ a: string; b: string; distance: number }>;
}

function detectFormat(buf: Buffer): SignalEntry["format"] {
  if (buf[0] === 0xff && buf[1] === 0xd8) return "jpeg";
  if (buf[0] === 0x89 && buf[1] === 0x50 && buf[2] === 0x4e && buf[3] === 0x47) return "png";
  return "unknown";
}

/** Walk JPEG markers until we hit SOFn (0xFFC0..0xFFCF except DHT/DRI). */
function readJpegDimensions(buf: Buffer): { width?: number; height?: number } {
  if (buf[0] !== 0xff || buf[1] !== 0xd8) return {};
  let i = 2;
  while (i < buf.length - 1) {
    if (buf[i] !== 0xff) return {};
    let marker = buf[i + 1];
    // Skip pad bytes
    while (marker === 0xff && i + 2 < buf.length) {
      i++;
      marker = buf[i + 1];
    }
    i += 2;
    // Standalone markers
    if (marker === 0xd8 || marker === 0xd9) continue;
    if (i + 1 >= buf.length) return {};
    const segLen = buf.readUInt16BE(i);
    if (
      (marker >= 0xc0 && marker <= 0xc3) ||
      (marker >= 0xc5 && marker <= 0xc7) ||
      (marker >= 0xc9 && marker <= 0xcb) ||
      (marker >= 0xcd && marker <= 0xcf)
    ) {
      // SOFn: precision(1) + height(2) + width(2) + ...
      const height = buf.readUInt16BE(i + 3);
      const width = buf.readUInt16BE(i + 5);
      return { width, height };
    }
    i += segLen;
  }
  return {};
}

function readPngDimensions(buf: Buffer): { width?: number; height?: number } {
  // PNG signature 8 bytes + IHDR length(4) + "IHDR"(4) + width(4) + height(4)
  if (buf.length < 24) return {};
  if (buf.readUInt32BE(12) !== 0x49484452) return {}; // "IHDR"
  return { width: buf.readUInt32BE(16), height: buf.readUInt32BE(20) };
}

/**
 * Decode JPEG to RGBA, downsample to 9×8 grayscale, then build a 64-bit
 * dHash signature: bit i,j = 1 iff pixel(i,j) > pixel(i,j+1). This is the
 * standard "difference hash" — robust to small re-encodings and crops,
 * sensitive to actual image content changes.
 */
function dhashFromJpeg(buf: Buffer): { dhash: string; avg: number } | null {
  let raw: { width: number; height: number; data: Buffer | Uint8Array };
  try {
    raw = jpeg.decode(buf, { useTArray: true, maxMemoryUsageInMB: 256 });
  } catch {
    return null;
  }
  const { width, height } = raw;
  const data = raw.data as Uint8Array;

  // Convert to grayscale 9×8 via box-average sampling.
  const W = 9;
  const H = 8;
  const gray = new Uint8Array(W * H);
  let sumLum = 0;
  for (let y = 0; y < H; y++) {
    const y0 = Math.floor((y * height) / H);
    const y1 = Math.max(y0 + 1, Math.floor(((y + 1) * height) / H));
    for (let x = 0; x < W; x++) {
      const x0 = Math.floor((x * width) / W);
      const x1 = Math.max(x0 + 1, Math.floor(((x + 1) * width) / W));
      let s = 0;
      let n = 0;
      for (let yy = y0; yy < y1; yy += Math.max(1, Math.floor((y1 - y0) / 4))) {
        for (let xx = x0; xx < x1; xx += Math.max(1, Math.floor((x1 - x0) / 4))) {
          const idx = (yy * width + xx) * 4;
          // Luminance: ITU-R BT.601
          const lum = 0.299 * data[idx] + 0.587 * data[idx + 1] + 0.114 * data[idx + 2];
          s += lum;
          n++;
        }
      }
      const v = n > 0 ? Math.round(s / n) : 0;
      gray[y * W + x] = v;
      sumLum += v;
    }
  }

  // Build 8×8 bit field.
  const bits = new Uint8Array(8); // 64 bits = 8 bytes
  let bit = 0;
  for (let y = 0; y < H; y++) {
    for (let x = 0; x < W - 1; x++) {
      const left = gray[y * W + x];
      const right = gray[y * W + x + 1];
      if (left > right) {
        bits[Math.floor(bit / 8)] |= 1 << (7 - (bit % 8));
      }
      bit++;
    }
  }

  const dhash = Array.from(bits, (b) => b.toString(16).padStart(2, "0")).join("");
  return { dhash, avg: Math.round(sumLum / (W * H)) };
}

function hammingHex(a: string, b: string): number {
  let d = 0;
  for (let i = 0; i < a.length; i += 2) {
    const x = parseInt(a.slice(i, i + 2), 16) ^ parseInt(b.slice(i, i + 2), 16);
    // popcount
    let v = x;
    v = v - ((v >> 1) & 0x55);
    v = (v & 0x33) + ((v >> 2) & 0x33);
    v = (v + (v >> 4)) & 0x0f;
    d += v;
  }
  return d;
}

function processFile(absPath: string, fileName: string): SignalEntry {
  const buf = readFileSync(absPath);
  const format = detectFormat(buf);
  const dim =
    format === "jpeg" ? readJpegDimensions(buf) : format === "png" ? readPngDimensions(buf) : {};
  const sha256 = createHash("sha256").update(buf).digest("hex");
  let dhash: string | undefined;
  let avgLuminance: number | undefined;
  if (format === "jpeg") {
    const r = dhashFromJpeg(buf);
    if (r) {
      dhash = r.dhash;
      avgLuminance = r.avg;
    }
  }
  return {
    file: fileName,
    url: `/photos/${fileName}`,
    bytes: statSync(absPath).size,
    sha256,
    width: dim.width,
    height: dim.height,
    format,
    magic: buf.subarray(0, 8).toString("hex"),
    dhash,
    avgLuminance,
  };
}

function main() {
  const cwd = process.cwd();
  // Two real folders we expose to the UI. main is symlinked into public/,
  // myface holds the 199 portraits we copied (excluding non-portrait files).
  const dirs: { abs: string; urlPrefix: string }[] = [
    { abs: resolve(cwd, "public/photos_main"),   urlPrefix: "/photos_main" },
    { abs: resolve(cwd, "public/photos_myface"), urlPrefix: "/photos_myface" },
  ];
  const entries: SignalEntry[] = [];
  for (const d of dirs) {
    const files = readdirSync(d.abs).filter((f) => /\.(jpe?g|png)$/i.test(f)).sort();
    for (const f of files) {
      const abs = resolve(d.abs, f);
      const e = processFile(abs, basename(f));
      e.url = `${d.urlPrefix}/${encodeURIComponent(basename(f))}`;
      entries.push(e);
    }
  }
  const photosDir = dirs.map((d) => d.abs).join(" + ");

  const hashIndex: Record<string, string[]> = {};
  for (const e of entries) {
    (hashIndex[e.sha256] ??= []).push(e.file);
  }
  const duplicates = Object.entries(hashIndex)
    .filter(([, list]) => list.length > 1)
    .map(([sha256, list]) => ({ sha256, files: list }));

  // Pairwise dHash distances
  const withDhash = entries.filter((e): e is SignalEntry & { dhash: string } => !!e.dhash);
  const pairs: Array<{ a: string; b: string; distance: number }> = [];
  for (let i = 0; i < withDhash.length; i++) {
    for (let j = i + 1; j < withDhash.length; j++) {
      pairs.push({
        a: withDhash[i].file,
        b: withDhash[j].file,
        distance: hammingHex(withDhash[i].dhash, withDhash[j].dhash),
      });
    }
  }
  pairs.sort((a, b) => a.distance - b.distance);
  const closestDhashPairs = pairs.slice(0, 30);

  const report: SignalReport = {
    generatedAt: new Date().toISOString(),
    rootDir: photosDir,
    count: entries.length,
    entries,
    hashIndex,
    duplicates,
    filesizeBytesTotal: entries.reduce((a, e) => a + e.bytes, 0),
    closestDhashPairs,
  };

  writeFileSync(resolve(cwd, "signal-report.json"), JSON.stringify(report, null, 2));

  // Bundle a slim version into public/ so the browser can load it
  const slim = {
    generatedAt: report.generatedAt,
    count: report.count,
    entries: entries.map((e) => ({
      file: e.file,
      url: e.url,
      bytes: e.bytes,
      sha256: e.sha256,
      width: e.width,
      height: e.height,
      format: e.format,
      dhash: e.dhash,
      avgLuminance: e.avgLuminance,
    })),
    duplicates,
    closestDhashPairs,
  };
  writeFileSync(resolve(cwd, "public/signal-report.json"), JSON.stringify(slim, null, 2));

  console.log(`Scanned ${entries.length} photo(s) in ${photosDir}`);
  console.log(`Total size: ${(report.filesizeBytesTotal / 1024).toFixed(1)} KB`);
  console.log(`Unique SHA-256: ${Object.keys(hashIndex).length}`);
  if (duplicates.length) {
    console.log(`Duplicates detected: ${duplicates.length}`);
    for (const d of duplicates) console.log(`  ${d.sha256.slice(0, 12)}…  ${d.files.join(", ")}`);
  }
  for (const e of entries) {
    const dim = e.width && e.height ? `${e.width}×${e.height}` : "?×?";
    const dh = e.dhash ? e.dhash : "no-dhash         ";
    const lum = e.avgLuminance !== undefined ? String(e.avgLuminance).padStart(3) : "  ?";
    console.log(
      `  ${e.file.padEnd(28)} ${e.format.padEnd(7)} ${dim.padEnd(11)} ${(e.bytes / 1024).toFixed(0).padStart(5)} KB  lum=${lum}  dhash=${dh}  ${e.sha256.slice(0, 12)}…`
    );
  }

  console.log(`\nClosest dHash pairs (Hamming distance):`);
  for (const p of closestDhashPairs.slice(0, 10)) {
    const flag = p.distance < 10 ? " ⚠ near-duplicate" : "";
    console.log(`  ${String(p.distance).padStart(2)} :: ${p.a.padEnd(28)} ↔ ${p.b}${flag}`);
  }
}

main();
