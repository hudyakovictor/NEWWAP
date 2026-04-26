# DEEPUTIN — agent runbook

This is a personal forensic-investigation notebook. The owner is **non-technical**
and relies on the AI assistant to drive verification, not the other way around.
The UI is a working draft (debug-grade); polish will come last, after the math
underneath is provably correct.

If you (the AI) are joining a session in this repo, do this first:

1. Read `about platform.txt` once for the conceptual scope (TZ).
2. Run `cd ui && npm run audit` and read `ui/audit-report.json`. This single
   command exercises every backend endpoint, runs every cross-field invariant,
   produces a TZ-coverage map and writes a machine-readable JSON report.
3. If the report has `findings[]` of severity `danger` or `warn`, address them
   before anything else. The goal of this notebook is correctness; the UI is a
   means to inspect correctness, not the deliverable.

## Project layout (relevant pieces)

- `ui/` — Vite + React + TS + Tailwind frontend (the notebook)
- `backend/` — Python FastAPI scaffold (currently empty `app/`)
- `storage/main/` — real 3DDFA_v3 reconstruction artifacts (mesh.obj, uv_*.png,
  render_*.png) — used by `MeshViewer` via `ui/public/recon/`
- `testphoto/` — 20 real photographs serving as ground-truth calibration anchors
  (`ui/public/photos/`)

## Frontend important paths

- `ui/src/api/types.ts` — single `Backend` interface used by every page
- `ui/src/api/mock.ts` — deterministic mock implementation
- `ui/src/api/logged.ts` — middleware that times + validates every call
- `ui/src/api/index.ts` — exports `api: Backend` (wraps logged backend)
- `ui/src/debug/logger.ts` — central log buffer + console formatting
- `ui/src/debug/expectations.ts` — predicted ranges per data field
- `ui/src/debug/validators.ts` — per-response validators
- `ui/src/debug/invariants.ts` — cross-field invariants (the audit suite)
- `ui/src/debug/audit.ts` — audit runner used by both UI and CLI
- `ui/src/debug/auditLoop.ts` — auto-audit every 60s in the browser
- `ui/scripts/audit.ts` — `npm run audit` entrypoint (writes audit-report.json)
- `ui/src/pages/AuditPage.tsx` — in-app audit dashboard
- `ui/src/pages/LogsPage.tsx` — in-app log inspector

## Workflows

### Verify the project is healthy (AI-only, no user input)
```
cd ui
npm run audit
```
Returns exit code 2 if any `danger` finding exists. Otherwise prints a summary
and writes `audit-report.json` to `ui/`. **Read that file before claiming
anything works.**

For a continuous loop while you iterate:
```
npm run audit -- --watch                  # default 30s interval
npm run audit -- --watch --interval 5000  # 5s interval
```

When the photos in `ui/public/photos/` change, refresh real-photo signals:
```
npm run signals     # writes signal-report.json + public/signal-report.json
npm run audit:full  # signals + audit in one shot
```
The `signals` invariant in the audit cross-checks every ground-truth file
against the report, flags duplicates and stale reports.
The watch mode prints one compact line per tick and notes any change in
`total` / `danger` counts.

The audit covers:
- 23 invariants (cross-field, symmetry, determinism, integrity, real-photo
  signals)
- 15 backend endpoints with per-call timing
- TZ auto-coverage: parses `about platform.txt` and verifies each section
  heading maps to an entry in `tzCoverageMap()` (with cyrillic aliases)
- Asset existence (Node-only): every referenced photo/recon URL must exist
  on disk under `ui/public/`
- Real-photo signals: SHA-256 + JPEG dimensions + size for every file in
  `ui/public/photos/`, with hash-based duplicate detection

## Overnight pose-detection run (2026-04-25)

While the owner was asleep we ran the project's existing head-pose runners
on the two relevant photo folders.

Inputs (do not modify):
- main folder: `~/dutin/rebucketed_photos/all` — 1638 JPEGs (full study set)
- calibration folder: `~/dutin/myface` — 204 JPEGs (confirmed by owner 2026-04-25)

Pipeline used (no new tools, no MediaPipe):
1. `scripts/poses_hpe_safe.py` — wrapper around `core/runner_hpe.py`
   internals (SCRFD + MobileNetV3 on MPS). Adds incremental writes every
   25 photos and a `--resume` flag.
2. For files where HPE found no face, `scripts/poses_3ddfa_safe.py`
   — wrapper around `core/runner_3ddfa_v3.py` internals. Catches the
   `SystemExit` raised by `face_box.detector` on no-face images (the
   stock runner crashes on the first such photo) and also supports
   incremental writes + `--resume`.

Both wrappers leave `core/` untouched. Use `--resume` to continue after
a terminal crash:

    python scripts/poses_hpe_safe.py    --input_dir <dir> --output_json <path> --resume
    python scripts/poses_3ddfa_safe.py  --input_dir <dir> --output_json <path> --resume

The runners write the JSON every 25 photos, so worst-case loss is the
last <25 entries.

Outputs in `newapp/storage/poses/`:
- `poses_main.json`          — raw HPE output (1638 entries)
- `poses_main_3ddfa.json`    — 3DDFA output for the 427 HPE misses
- `poses_main_consolidated.json` — merged, with `source: "hpe"|"3ddfa"|"none"` and `classification`
- `poses_main_summary.json`  — counts per bucket and per estimator
- Same four files for `myface`.

Coverage achieved:
- main: 1211 HPE + 427 3DDFA = **1638 / 1638 (100 %)**
- myface: 176 HPE + 23 3DDFA + 5 not-portraits = **199 / 204 (97.5 %)**

The 5 myface entries that no model could process are not actually faces:
two duplicate wireframe-skull renders + three random screenshots (banking
UI, gosuslugi UI, sberbank UI). The detector behaviour is correct — flag
to the owner that the screenshot `Снимок экрана 2026-04-16 в 22.06.43.png`
contains personal banking details and probably shouldn't sit inside the
calibration folder at all.

Bucket distribution (main, by yaw):
- frontal 419, ¾-left 258, ¾-right 331, profile-left 304, profile-right 326

Pair-formation logic for analysis/calibration was **not** implemented —
the owner has not yet specified the rule (within-bucket pairs? cross-folder
within bucket? deltaYaw window?). Surface this when he wakes.

## Mock removed, real data wired in (2026-04-25)

The 20-testphoto mock layer has been replaced by real data:
- 1638 photos from `~/dutin/rebucketed_photos/all` symlinked at `ui/public/photos_main/`.
- 199 portrait photos from `~/dutin/myface` (filtered, no .mp4/.pdf/banking screenshots) copied to `ui/public/photos_myface/`.
- Pose JSONs (`poses_main.json`, `poses_myface.json`) imported from `src/data/`
  build the photo registry; `mock/photos.ts` is now a thin shim that maps
  registry → legacy `PhotoRecord` shape.
- Stub fields (`syntheticProb`, `bayesH0`, `cluster`, `flags`, `md5`,
  `resolution`, `expression`, `source`) stay — pages relying on them now
  show a `<StubBanner />` to mark synthetic numbers.

Files deleted:
- `ui/audit-report.json`, `ui/signal-report.json`, `ui/public/signal-report.json`
- `ui/public/photos/` (20 testphotos)
- `ui/public/recon/` (single-photo reconstruction)
- `ui/public/about_platform.txt` (TZ check still finds the canonical copy at repo root)
- `newapp/testphoto/`
- `storage/main/main-1999_09_03-2c92ad0b6b/`

What's still synthetic (per Progress page):
perceptual hash, 3D reconstruction, 21-zone scores, texture/synthetic
detector, bayesian, ageing, calibration buckets. These pages display a
`<StubBanner />` until the relevant pipeline run lands.

Audit state after migration: 1 warn (`signals.missing_report` — accurate,
signals stage is stub), 1 info (TZ summary), reproducible across runs.

## Autonomous run (2026-04-25 02:00–06:05)

Phases 1–6 completed without owner input:

1. `npm run signals` on 1837 photos (1638 main + 199 myface) — produced
   `public/signal-report.json` with SHA-256, JPEG dimensions, dHash, and
   pairwise distances. Forensic findings: **17 cross-year near-duplicate
   pairs** (dHash distance < 4) — same image surfaced under multiple
   "different year" filenames. Plus 5 byte-identical duplicates (same-day
   `-N` suffix copies + 3 myface PNG re-uploads).

2. Real timeline anchors: `mock/data.ts::yearPoints` now picks the most
   frontal real photo per year from the main folder (every year 1999..2025
   has at least one anchor). Synthetic metric rows still on the same page,
   marked with `<StubBanner />`.

3. Pose-driven Pair analysis: real Δyaw/Δpitch/Δroll surfaced in a new
   "Pose comparison (real)" panel. Mutual zone visibility now uses real
   yaw thresholds (±55°) instead of the old string-matching mock.

4. Real anomaly registry: `src/data/poseAnomalies.ts` aggregates real
   findings into the `AnomalyRecord[]` returned by `api.listAnomalies()`:
     - `signals.near_dup.*` — perceptual duplicates from signal-report
       (cross-year = danger, same-year = warn)
     - `pose.extreme.*` — |yaw| > 80° (info)
     - `pose.fallback.*` — HPE failed, 3DDFA used (info)
     - `pose.drift.*` — |Δyaw| > 60° between consecutive same-year frames
       within 30 days (warn)
   Synthetic year-based and event-based entries follow afterwards in the
   same list.

5. Photos page filters rewired to real fields only: folder (main/myface),
   pose classification, pose source (hpe/3ddfa/none), max |yaw|, sort by
   date/yaw/id. Per-card overlay shows real yaw + pose source.

6. Audit reproducibility verified — two consecutive `npm run audit` runs
   produce byte-identical findings (modulo timestamps/durationMs).

**Audit state**: RED on purpose — the 17 `signals.near_duplicate` findings
are real evidence of mis-dated photos in the dataset. They are visible
in the Audit page and as anomalies in the Anomalies page.

PhotoRecord shape gained two real fields: `yaw: number | null` and
`poseSource: "hpe" | "3ddfa" | "none"`. Other stub fields (`syntheticProb`,
`bayesH0`, `cluster`, `flags`, `md5`, `resolution`, `expression`,
`source`) remain stubs and are flagged via `<StubBanner />`.

## Iterative real-data run (2026-04-25 06:30–07:00)

Six small batched iterations under the 20/80 rule:

1. **Visual clusters** (cheap, no compute). Built union-find on dHash
   distances → `storage/duplicate-clusters.json` + new in-app page
   `Visual clusters`. **Important correction**: my prior framing of
   dHash near-duplicates as "mis-dated photos" was wrong — visual
   verification of distance-2/3 pairs revealed they are different
   sessions of the same person in the same profile pose. dHash 8×8
   captures composition, not identity. The audit invariant has been
   downgraded to info ("similar composition"), and only SHA-256
   byte duplicates remain promoted to anomalies.

2. **Real per-year pose metrics in the timeline**. Added 3 metric rows
   (Photos/year, Mean |yaw|/year, Frontal ratio/year) computed from the
   pose pipeline output. Synthetic top-7 metrics still present and
   marked stub.

3. **Real Pipeline page**. Replaced synthetic stages with real ingest →
   signals → pose chain (1837 → 1837 → 1832 → 1832), downstream stages
   stay stub.

4. **Real bbox extraction**. New `scripts/bbox_safe.py` (Python, SCRFD
   only, no pose). Output `storage/bbox/bbox_{main,myface}.json` with
   per-file `{x, y, w, h, score, kp5, imgW, imgH}`. Coverage: 1211/1638
   main + 176/199 myface = 1387 of 1837 photos (76%). Same SCRFD miss
   rate as HPE — the 450 missed photos still have pose via 3DDFA but
   no bbox yet.

5. **Real face crop stats**. New `scripts/face_stats.py` over the bbox
   crops, producing per-photo `{meanLum, stdLum, meanR, meanG, meanB,
   stdR, stdG, stdB, cropW, cropH}`. ~110 photos/sec on CPU.

6. **Wired bbox + face_stats into UI**. `RealPhoto.faceStats` is now
   real for 1387 photos. Two new real metric rows on the timeline
   (Face mean luminance/year, Face luminance σ/year). Progress page
   shows new real stages.

Stub banner pages still: Pair analysis (zone scores still stub), Evidence,
Anomalies (synthetic flags), Calibration (lighting axis), N×N matrix,
Report builder, top-7 timeline metric rows.

Audit state: YELLOW · 0 danger · 7 warn · 6 info · reproducible.

The 7 warns are 5 real SHA-256 byte duplicates + 2 dHash collisions
(also re-encoded same-file copies). The 6 info include 5 distance≤2
"similar composition" pairs + 1 TZ coverage summary.

## Determinism

All "random" mock outputs are seeded via `src/debug/prng.ts` (mulberry32 +
FNV-1a). The same input always produces the same output, so `npm run audit`
is fully reproducible — running it twice in a row yields identical
`findings` modulo timestamps and `durationMs`.

If you need to add new mock noise, derive a seed string from stable inputs
(photo id, year, year + photo, etc.) and call `rngFor(...parts)`. Avoid
`Math.random()` anywhere a value will be displayed or used by an invariant.

### Build & typecheck
```
cd ui
npx tsc -b --noEmit       # types only
npm run build             # full vite build
```

### Run the app
```
./run                     # starts backend on :8000 and ui on :5173
# or just frontend:
cd ui && npm run dev
```

In the browser console, the `deeputin` global exposes:
- `deeputin.dump()` — table of all logs
- `deeputin.suspicious()` — only entries flagged by validators
- `deeputin.byCategory('bayes')` / `.byScope('photo')` — filters
- `deeputin.audit()` — manual audit run
- `deeputin.lastAudit` — most recent audit report

## Adding new fields to the pipeline

Any new mock/algorithmic field must end up in three places:
1. `mock/*.ts` — the data itself (deterministic seeding when possible)
2. `debug/expectations.ts` — predicted range/value
3. `debug/validators.ts` and/or `debug/invariants.ts` — at least one check

If you skip step 3, the audit can't notice when the field drifts.

## When the audit goes red

- `danger`: drop everything else and fix it. Almost always a math/contract bug.
- `warn`: fix unless it's an explicit choice (then update expectations/invariants).
- `info`: look at the hint; usually points to a TZ topic that needs follow-up.

Findings include a `hint` field whenever the AI can act on it directly.
