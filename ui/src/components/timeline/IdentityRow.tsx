import { Fragment } from "react";
import { COL_W, LABEL_W } from "./constants";
import type { IdentitySegment } from "../../mock/data";

const H = 32;

export default function IdentityRow({
  years,
  segments,
}: {
  years: number[];
  segments: IdentitySegment[];
}) {
  const yearIndex = (y: number) => years.indexOf(y);
  return (
    <div className="flex border-b border-line/40">
      <div
        style={{ width: LABEL_W, height: H }}
        className="flex flex-col justify-center px-3 border-r border-line/60"
      >
        <div className="text-[11px] text-white">Identity clusters</div>
        <div className="text-[10px] text-muted">bayesian H0 / H1</div>
      </div>
      <div className="relative" style={{ width: years.length * COL_W, height: H }}>
        {/* baseline */}
        <div className="absolute left-0 right-0 top-1/2 h-px bg-accent/40" />
        {segments.map((s, i) => {
          const startIdx = yearIndex(s.from);
          const endIdx = yearIndex(s.to);
          if (startIdx < 0 || endIdx < 0) return null;
          const x = startIdx * COL_W + COL_W / 2;
          const w = (endIdx - startIdx) * COL_W;
          return (
            <Fragment key={i}>
              <div
                className="absolute top-1/2 -translate-y-1/2 h-1 rounded-full"
                style={{ left: x, width: w, background: s.id === "A" ? "#a855f7" : "#ef4444" }}
              />
              <div
                className="absolute top-1/2 -translate-y-1/2 w-5 h-5 rounded-full grid place-items-center text-[10px] font-bold text-white border"
                style={{
                  left: x - 10,
                  background: s.id === "A" ? "#7e22ce" : "#991b1b",
                  borderColor: s.id === "A" ? "#c084fc" : "#fca5a5",
                }}
              >
                {s.id}
              </div>
              <div
                className="absolute top-1/2 -translate-y-1/2 w-5 h-5 rounded-full grid place-items-center text-[10px] font-bold text-white border"
                style={{
                  left: x + w - 10,
                  background: s.id === "A" ? "#7e22ce" : "#991b1b",
                  borderColor: s.id === "A" ? "#c084fc" : "#fca5a5",
                }}
              >
                {s.id}
              </div>
            </Fragment>
          );
        })}
      </div>
    </div>
  );
}
