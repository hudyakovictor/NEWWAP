import { COL_W, LABEL_W, PHOTO_H_MIN } from "./constants";
import type { YearPoint } from "../../mock/data";
import { SeverityIcon } from "./icons";

export default function PhotoStrip({
  points,
  selectedYear,
  onSelect,
  onOpen,
  grow = 3,
}: {
  points: YearPoint[];
  selectedYear: number;
  onSelect: (y: number) => void;
  onOpen: (y: number) => void;
  grow?: number;
}) {
  return (
    <>
      <div
        className="flex shrink-0"
        style={{ flexGrow: grow, flexBasis: 0, minHeight: PHOTO_H_MIN }}
      >
        <div
          style={{ width: LABEL_W }}
          className="flex flex-col justify-center px-3 border-r border-line/60"
        >
          <div className="text-[11px] text-white font-medium">Subject timeline</div>
          <div className="text-[10px] text-muted">click photo for details</div>
        </div>
        <div className="flex">
          {points.map((p) => {
            const selected = p.year === selectedYear;
            return (
              <button
                key={p.year}
                onClick={() => {
                  onSelect(p.year);
                  onOpen(p.year);
                }}
                style={{ width: COL_W }}
                className={`relative group flex items-stretch justify-center px-1 py-1 h-full transition-colors ${
                  selected ? "bg-white/5" : ""
                }`}
              >
                <div
                  className={`relative w-full h-full rounded-sm overflow-hidden border ${
                    selected
                      ? "border-ok shadow-[0_0_0_1px_rgba(34,197,94,0.5)]"
                      : "border-line/60 group-hover:border-axis"
                  }`}
                >
                  <img
                    src={p.photo}
                    alt={String(p.year)}
                    className="w-full h-full object-cover"
                    loading="lazy"
                    draggable={false}
                  />
                  {p.identity === "B" && (
                    <div className="absolute top-0 right-0 text-[8px] px-1 bg-accent/80 text-white rounded-bl">
                      B
                    </div>
                  )}
                </div>
              </button>
            );
          })}
        </div>
      </div>

      <div className="flex shrink-0" style={{ height: 22 }}>
        <div
          style={{ width: LABEL_W }}
          className="border-r border-line/60 flex items-center px-3 text-[10px] text-muted"
        >
          Anomalies
        </div>
        <div className="flex">
          {points.map((p) => (
            <div
              key={p.year}
              style={{ width: COL_W }}
              className="h-full flex items-start justify-center pt-0.5 relative"
              title={p.note}
            >
              <div className="absolute top-0 w-px h-2 bg-line" />
              {p.anomaly ? <SeverityIcon s={p.anomaly} /> : null}
            </div>
          ))}
        </div>
      </div>
    </>
  );
}
