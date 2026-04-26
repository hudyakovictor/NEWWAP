import { useEffect, useMemo, useState } from "react";
import { Page, PanelCard } from "../components/common/Page";
import { api } from "../api";
import { PHOTOS, type PhotoRecord } from "../mock/photos";
import { useApp } from "../store/appStore";
import { rngFor } from "../debug/prng";
import StubBanner from "../components/common/StubBanner";

// Debug N×N comparison matrix. Pick any subset of photos, see pairwise
// similarity heatmap. Clicking a cell sends the pair to PairAnalysis.

export default function MatrixPage() {
  const { setPairA, setPairB, setPage } = useApp();
  const defaults = useMemo(() => {
    // take a spread across years to make the heatmap meaningful
    const spread: PhotoRecord[] = [];
    const years = Array.from(new Set(PHOTOS.map((p) => p.year)));
    years.forEach((y) => {
      const first = PHOTOS.find((p) => p.year === y);
      if (first) spread.push(first);
    });
    return spread.filter((_, i) => i % 2 === 0).slice(0, 10);
  }, []);

  const [selected, setSelected] = useState<PhotoRecord[]>(defaults);
  const [matrix, setMatrix] = useState<number[][]>([]);
  const [loading, setLoading] = useState(false);
  const [picker, setPicker] = useState(false);

  useEffect(() => {
    if (!selected.length) {
      setMatrix([]);
      return;
    }
    setLoading(true);
    api.comparisonMatrix(selected.map((p) => p.id)).then((m) => {
      setMatrix(m);
      setLoading(false);
    });
  }, [selected]);

  const color = (v: number) => {
    // green → yellow → red (v high = green)
    const t = Math.max(0, Math.min(1, v));
    const r = Math.round(255 * (1 - t));
    const g = Math.round(200 * t);
    return `rgb(${r},${g},60)`;
  };

  return (
    <Page
      title="N×N comparison matrix (debug)"
      subtitle="Pairwise similarity heatmap across a selected subset of photos"
      actions={
        <>
          <button
            onClick={() => setPicker(true)}
            className="px-3 h-8 rounded bg-line/70 hover:bg-line text-[11px] text-white"
          >
            Pick photos ({selected.length})
          </button>
          <button
            onClick={() => {
              // Seeded "shuffle" so it's reproducible inside one session;
              // each click bumps the seed for variety.
              const seedSrc = `matrix-shuffle-${Date.now()}`;
              const r = rngFor(seedSrc);
              const decorated = PHOTOS.map((p) => ({ p, k: r() }));
              decorated.sort((x, y) => x.k - y.k);
              const sorted = decorated.map((d) => d.p);
              setSelected(sorted.slice(0, 10));
            }}
            className="px-3 h-8 rounded bg-accent/70 hover:bg-accent text-[11px] text-white"
          >
            Shuffle
          </button>
        </>
      }
    >
      <StubBanner
        fields={["similarity score"]}
        note="Pose is real; similarity is currently derived from stub synthetic / bayes fields."
      />
      {loading ? (
        <div className="text-[11px] text-muted">Computing matrix…</div>
      ) : !matrix.length ? (
        <div className="text-[11px] text-muted">Pick at least two photos to compute matrix.</div>
      ) : (
        <PanelCard title={`Similarity matrix ${matrix.length}×${matrix.length}`}>
          <div className="overflow-auto">
            <table className="text-[10px]">
              <thead>
                <tr>
                  <th className="p-1"></th>
                  {selected.map((p) => (
                    <th key={p.id} className="p-1 align-bottom">
                      <div className="flex flex-col items-center gap-0.5">
                        <img src={p.photo} alt="" className="w-10 h-10 rounded object-cover border border-line" />
                        <div className="text-muted font-mono">{p.year}</div>
                      </div>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {selected.map((row, i) => (
                  <tr key={row.id}>
                    <th className="p-1 text-right align-middle">
                      <div className="flex items-center gap-1 justify-end">
                        <span className="text-muted font-mono">{row.year}</span>
                        <img src={row.photo} alt="" className="w-8 h-8 rounded object-cover border border-line" />
                      </div>
                    </th>
                    {selected.map((col, j) => {
                      const v = matrix[i][j];
                      return (
                        <td key={col.id} className="p-0.5">
                          <button
                            onClick={() => {
                              setPairA(row.id);
                              setPairB(col.id);
                              setPage("pairs");
                            }}
                            className="w-10 h-10 rounded text-[10px] font-mono text-black font-semibold border border-black/20 hover:ring-2 hover:ring-info"
                            style={{ background: color(v) }}
                            title={`${row.id} × ${col.id} = ${v.toFixed(3)}`}
                          >
                            {v.toFixed(2)}
                          </button>
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="text-[11px] text-muted mt-2">
            Green = high mutual similarity (likely same cluster). Red = low similarity.
            Click any cell to open the pair in Pair analysis.
          </div>
        </PanelCard>
      )}

      {picker && (
        <PhotoPicker
          selected={selected}
          onClose={() => setPicker(false)}
          onChange={setSelected}
        />
      )}
    </Page>
  );
}

function PhotoPicker({
  selected,
  onClose,
  onChange,
}: {
  selected: PhotoRecord[];
  onClose: () => void;
  onChange: (s: PhotoRecord[]) => void;
}) {
  const [query, setQuery] = useState("");
  const selectedIds = new Set(selected.map((s) => s.id));
  const candidates = PHOTOS.filter(
    (p) => !query || p.date.includes(query) || p.id.includes(query)
  ).slice(0, 120);

  function toggle(p: PhotoRecord) {
    if (selectedIds.has(p.id)) {
      onChange(selected.filter((x) => x.id !== p.id));
    } else if (selected.length < 20) {
      onChange([...selected, p]);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-5xl max-h-[85vh] bg-bg-panel border border-line rounded-lg flex flex-col overflow-hidden"
      >
        <div className="flex items-center justify-between h-10 px-3 border-b border-line">
          <div className="text-sm font-semibold text-white">
            Pick photos ({selected.length}/20)
          </div>
          <button onClick={onClose} className="px-2 h-7 rounded bg-line text-[11px] text-white">Done</button>
        </div>
        <div className="p-3 border-b border-line">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="filter id / date"
            className="w-full h-8 px-2 rounded bg-bg-deep border border-line text-[11px] text-white"
          />
        </div>
        <div className="flex-1 overflow-auto p-3">
          <div className="grid grid-cols-10 gap-2">
            {candidates.map((p) => {
              const sel = selectedIds.has(p.id);
              return (
                <button
                  key={p.id}
                  onClick={() => toggle(p)}
                  className={`relative rounded overflow-hidden border ${
                    sel ? "border-ok ring-2 ring-ok/50" : "border-line hover:border-info"
                  }`}
                  title={p.id}
                >
                  <img src={p.photo} alt="" className="w-full aspect-square object-cover" />
                  <div className="absolute bottom-0 inset-x-0 bg-gradient-to-t from-black/90 to-transparent px-1 py-0.5 text-[9px] font-mono text-white">
                    {p.date}
                  </div>
                  {sel && (
                    <div className="absolute top-1 right-1 bg-ok text-black text-[9px] px-1 rounded">✓</div>
                  )}
                </button>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
