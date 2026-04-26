import { useEffect, useMemo, useState } from "react";
import { Page, PanelCard } from "../components/common/Page";
import { GROUND_TRUTH, type GroundTruth } from "../mock/groundTruth";
import { buildPhotoDetail } from "../mock/photoDetail";
import { log } from "../debug/logger";

const LS_KEY = "deeputin.ground_truth.overrides";

interface Override {
  expectedPose?: GroundTruth["expectedPose"];
  expectedExpression?: GroundTruth["expectedExpression"];
  expectedCluster?: GroundTruth["expectedCluster"];
  note?: string;
}

function loadOverrides(): Record<string, Override> {
  try {
    const raw = localStorage.getItem(LS_KEY);
    return raw ? JSON.parse(raw) : {};
  } catch {
    return {};
  }
}

function saveOverrides(overrides: Record<string, Override>) {
  try {
    localStorage.setItem(LS_KEY, JSON.stringify(overrides));
  } catch {
    /* ignore quota errors */
  }
}

interface GTRow extends GroundTruth {
  /** Mock-pipeline output we compare against the expected values. */
  predicted: {
    pose: string;
    expression: string;
    cluster: "A" | "B";
    syntheticProb: number;
    age: number;
  };
  matches: {
    pose: boolean;
    expression: boolean;
    cluster: boolean;
  };
}

function build(overrides: Record<string, Override>): GTRow[] {
  const baseYear = GROUND_TRUTH[0].year;
  return GROUND_TRUTH.map((g) => {
    const o = overrides[g.file] ?? {};
    const merged: GroundTruth = {
      ...g,
      expectedPose: o.expectedPose ?? g.expectedPose,
      expectedExpression: o.expectedExpression ?? g.expectedExpression,
      expectedCluster: o.expectedCluster ?? g.expectedCluster,
      note: o.note ?? g.note,
    };
    const detail = buildPhotoDetail(merged.year, merged.url);
    const predicted = {
      pose: detail.pose.classification,
      expression: detail.expression.neutral
        ? "neutral"
        : detail.expression.smile > 0.3
        ? "smile"
        : detail.expression.jawOpen > 0.25
        ? "speech"
        : "serious",
      cluster: (merged.year >= 2015 && merged.year <= 2020 ? "B" : "A") as "A" | "B",
      syntheticProb: detail.texture.syntheticProb,
      age: 46 + (merged.year - baseYear),
    };
    const matches = {
      pose: !merged.expectedPose || predicted.pose === merged.expectedPose,
      expression: !merged.expectedExpression || predicted.expression === merged.expectedExpression,
      cluster: !merged.expectedCluster || predicted.cluster === merged.expectedCluster,
    };
    return { ...merged, predicted, matches };
  });
}

export default function GroundTruthPage() {
  const [overrides, setOverrides] = useState<Record<string, Override>>(() => loadOverrides());
  const [rows, setRows] = useState<GTRow[]>(() => build(loadOverrides()));
  const [selected, setSelected] = useState<GTRow | null>(rows[0] ?? null);

  // Re-derive rows whenever overrides change so saves are reflected immediately.
  useEffect(() => {
    const next = build(overrides);
    setRows(next);
    if (selected) {
      const fresh = next.find((r) => r.file === selected.file) ?? null;
      setSelected(fresh);
    }
    saveOverrides(overrides);
  }, [overrides]);

  useEffect(() => {
    const mismatches = rows.filter((r) => !r.matches.pose || !r.matches.expression || !r.matches.cluster);
    log.info(
      "calibration",
      "ground_truth:compare",
      `Ground-truth calibration: ${rows.length} anchors, ${mismatches.length} mismatch(es)`,
      {
        rows: rows.map((r) => ({
          file: r.file,
          expected: { pose: r.expectedPose, expression: r.expectedExpression, cluster: r.expectedCluster },
          predicted: r.predicted,
          matches: r.matches,
        })),
      }
    );
    if (mismatches.length) {
      log.warn(
        "validation",
        "ground_truth:mismatches",
        `${mismatches.length} ground-truth anchor(s) mismatch mock pipeline output`,
        mismatches.map((m) => ({
          file: m.file,
          predicted: m.predicted,
          expected: {
            pose: m.expectedPose,
            expression: m.expectedExpression,
            cluster: m.expectedCluster,
          },
        }))
      );
    }
  }, [rows]);

  const stats = useMemo(() => {
    const posMatch = rows.filter((r) => r.matches.pose).length;
    const exprMatch = rows.filter((r) => r.matches.expression).length;
    const clusterMatch = rows.filter((r) => r.matches.cluster).length;
    return {
      total: rows.length,
      posMatch,
      exprMatch,
      clusterMatch,
      posPct:     (posMatch / rows.length) * 100,
      exprPct:    (exprMatch / rows.length) * 100,
      clusterPct: (clusterMatch / rows.length) * 100,
    };
  }, [rows]);

  function updateRow(i: number, patch: Partial<GroundTruth>) {
    const file = rows[i].file;
    setOverrides((prev) => ({
      ...prev,
      [file]: {
        ...prev[file],
        ...patch,
      },
    }));
  }

  function resetOverrides() {
    setOverrides({});
  }

  function exportJson() {
    const payload = rows.map((r) => ({
      file: r.file,
      capturedAt: r.capturedAt,
      expected: { pose: r.expectedPose, expression: r.expectedExpression, cluster: r.expectedCluster },
      predicted: r.predicted,
      matches: r.matches,
      note: r.note,
    }));
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `deeputin-ground-truth-${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <Page
      title="Ground truth (calibration)"
      subtitle="20 real testphoto anchors · manual expected values cross-checked with mock pipeline"
      actions={
        <>
          <button
            onClick={resetOverrides}
            className="px-3 h-8 rounded bg-line hover:bg-line/80 text-[11px] text-white"
            title="Drop all manual edits and revert to file-default expected values"
          >
            Reset overrides ({Object.keys(overrides).length})
          </button>
          <button
            onClick={exportJson}
            className="px-3 h-8 rounded bg-accent/70 hover:bg-accent text-[11px] text-white"
          >
            Export ground truth
          </button>
        </>
      }
    >
      <div className="grid grid-cols-4 gap-3 mb-3">
        <Stat label="total anchors"      value={stats.total}                                            color="#cfd8e6" />
        <Stat label="pose match"         value={`${stats.posMatch}/${stats.total}`}                     color={stats.posPct < 80 ? "#f59e0b" : "#22c55e"} />
        <Stat label="expression match"   value={`${stats.exprMatch}/${stats.total}`}                    color={stats.exprPct < 80 ? "#f59e0b" : "#22c55e"} />
        <Stat label="cluster match"      value={`${stats.clusterMatch}/${stats.total}`}                 color={stats.clusterPct < 80 ? "#f59e0b" : "#22c55e"} />
      </div>

      <div className="grid grid-cols-12 gap-3">
        <PanelCard title="Anchors" className="col-span-7">
          <table className="w-full text-[11px]">
            <thead className="text-muted border-b border-line">
              <tr>
                <th className="text-left p-1">file</th>
                <th className="text-left p-1">date</th>
                <th className="text-left p-1">pose</th>
                <th className="text-left p-1">expr</th>
                <th className="text-left p-1">cluster</th>
                <th className="text-left p-1">synthP</th>
                <th className="text-left p-1">age</th>
                <th className="text-left p-1">ok</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => {
                const allOk = r.matches.pose && r.matches.expression && r.matches.cluster;
                return (
                  <tr
                    key={r.file}
                    onClick={() => setSelected(r)}
                    className={`border-b border-line/30 cursor-pointer hover:bg-line/40 ${
                      selected?.file === r.file ? "bg-line/60" : ""
                    } ${!allOk ? "bg-warn/10" : ""}`}
                  >
                    <td className="p-1 font-mono text-white">{r.file}</td>
                    <td className="p-1 text-muted">{r.capturedAt}</td>
                    <td className={`p-1 ${r.matches.pose ? "text-ok" : "text-warn"}`}>
                      {r.predicted.pose}
                      <span className="text-muted"> / {r.expectedPose ?? "—"}</span>
                    </td>
                    <td className={`p-1 ${r.matches.expression ? "text-ok" : "text-warn"}`}>
                      {r.predicted.expression}
                      <span className="text-muted"> / {r.expectedExpression ?? "—"}</span>
                    </td>
                    <td className={`p-1 ${r.matches.cluster ? "text-ok" : "text-danger"}`}>
                      {r.predicted.cluster}
                      <span className="text-muted"> / {r.expectedCluster ?? "—"}</span>
                    </td>
                    <td className="p-1 font-mono text-muted">{r.predicted.syntheticProb.toFixed(2)}</td>
                    <td className="p-1 font-mono text-muted">{r.predicted.age}</td>
                    <td className="p-1">
                      {allOk ? <span className="text-ok">✓</span> : <span className="text-warn">⚠</span>}
                    </td>
                    <td className="hidden">{i}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </PanelCard>

        <PanelCard title="Anchor editor" className="col-span-5">
          {!selected ? (
            <div className="text-[11px] text-muted">Select an anchor.</div>
          ) : (
            <Editor
              row={selected}
              onChange={(patch) => {
                const i = rows.findIndex((r) => r.file === selected.file);
                if (i >= 0) updateRow(i, patch);
              }}
            />
          )}
        </PanelCard>
      </div>
    </Page>
  );
}

function Editor({ row, onChange }: { row: GTRow; onChange: (p: Partial<GroundTruth>) => void }) {
  return (
    <div className="flex gap-3">
      <img
        src={row.url}
        alt=""
        className="w-48 h-48 object-cover rounded border border-line"
      />
      <div className="flex-1 text-[11px] space-y-2">
        <div className="grid grid-cols-2 gap-2">
          <KV k="file"        v={row.file} />
          <KV k="captured"    v={row.capturedAt} />
          <KV k="year/month"  v={`${row.year}-${row.month}`} />
          <KV k="predicted age" v={row.predicted.age} />
        </div>
        <Field label="Expected pose">
          <select
            value={row.expectedPose ?? ""}
            onChange={(e) => onChange({ expectedPose: (e.target.value || undefined) as any })}
            className="w-full h-7 px-2 rounded bg-bg-deep border border-line text-white"
          >
            <option value="">—</option>
            <option value="frontal">frontal</option>
            <option value="three_quarter_left">three_quarter_left</option>
            <option value="three_quarter_right">three_quarter_right</option>
            <option value="profile_left">profile_left</option>
            <option value="profile_right">profile_right</option>
          </select>
        </Field>
        <Field label="Expected expression">
          <select
            value={row.expectedExpression ?? ""}
            onChange={(e) => onChange({ expectedExpression: (e.target.value || undefined) as any })}
            className="w-full h-7 px-2 rounded bg-bg-deep border border-line text-white"
          >
            <option value="">—</option>
            <option value="neutral">neutral</option>
            <option value="smile">smile</option>
            <option value="speech">speech</option>
            <option value="serious">serious</option>
          </select>
        </Field>
        <Field label="Expected cluster">
          <select
            value={row.expectedCluster ?? ""}
            onChange={(e) => onChange({ expectedCluster: (e.target.value || undefined) as any })}
            className="w-full h-7 px-2 rounded bg-bg-deep border border-line text-white"
          >
            <option value="">—</option>
            <option value="A">A (real)</option>
            <option value="B">B (double / suspected)</option>
          </select>
        </Field>
        <Field label="Investigator note">
          <textarea
            rows={3}
            value={row.note ?? ""}
            onChange={(e) => onChange({ note: e.target.value })}
            className="w-full px-2 py-1 rounded bg-bg-deep border border-line text-white"
          />
        </Field>

        <div className="mt-2 border-t border-line/40 pt-2">
          <div className="text-muted uppercase tracking-widest text-[10px] mb-1">match vs pipeline</div>
          <div className="grid grid-cols-3 gap-1 text-[10px]">
            <MatchBadge ok={row.matches.pose} label="pose" />
            <MatchBadge ok={row.matches.expression} label="expression" />
            <MatchBadge ok={row.matches.cluster} label="cluster" />
          </div>
        </div>
      </div>
    </div>
  );
}

function MatchBadge({ ok, label }: { ok: boolean; label: string }) {
  return (
    <div
      className={`px-2 py-1 rounded ${
        ok ? "bg-ok/20 text-ok" : "bg-warn/20 text-warn"
      } text-center`}
    >
      {label} {ok ? "✓" : "⚠"}
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1 my-1">
      <span className="text-muted">{label}</span>
      {children}
    </label>
  );
}

function Stat({ label, value, color }: { label: string; value: React.ReactNode; color: string }) {
  return (
    <div className="bg-bg-panel border border-line rounded p-2">
      <div className="text-xl font-semibold" style={{ color }}>{value}</div>
      <div className="text-[11px] text-muted">{label}</div>
    </div>
  );
}

function KV({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="flex justify-between border-b border-line/40 py-0.5">
      <span className="text-muted">{k}</span>
      <span className="font-mono text-white truncate max-w-[60%] text-right">{v}</span>
    </div>
  );
}
