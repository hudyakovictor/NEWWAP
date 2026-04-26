import { useCallback, useEffect, useRef, useState } from "react";

export default function Scrubber({
  years,
  volume,
  range,
  onRangeChange,
}: {
  years: number[];
  volume: number[];
  range: [number, number];
  onRangeChange: (r: [number, number]) => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [drag, setDrag] = useState<null | "start" | "end" | "move">(null);
  const [moveOffset, setMoveOffset] = useState(0);

  const pctFromYear = (y: number) => ((y - years[0]) / (years.length - 1)) * 100;
  const yearFromPct = (p: number) =>
    years[Math.max(0, Math.min(years.length - 1, Math.round((p / 100) * (years.length - 1))))];

  const onMove = useCallback(
    (e: MouseEvent) => {
      if (!ref.current || !drag) return;
      const rect = ref.current.getBoundingClientRect();
      const p = ((e.clientX - rect.left) / rect.width) * 100;
      if (drag === "start") {
        const newY = Math.min(range[1] - 1, yearFromPct(p));
        onRangeChange([newY, range[1]]);
      } else if (drag === "end") {
        const newY = Math.max(range[0] + 1, yearFromPct(p));
        onRangeChange([range[0], newY]);
      } else if (drag === "move") {
        const centerY = yearFromPct(p - moveOffset);
        const span = range[1] - range[0];
        let from = centerY;
        let to = from + span;
        if (from < years[0]) {
          from = years[0];
          to = from + span;
        }
        if (to > years[years.length - 1]) {
          to = years[years.length - 1];
          from = to - span;
        }
        onRangeChange([from, to]);
      }
    },
    [drag, moveOffset, onRangeChange, range, years]
  );

  useEffect(() => {
    if (!drag) return;
    const up = () => setDrag(null);
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", up);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", up);
    };
  }, [drag, onMove]);

  const vmax = Math.max(...volume);

  return (
    <div className="h-16 bg-bg-deep border-t border-line/60 px-3 py-2 flex items-center">
      <div className="text-[10px] text-muted w-40">
        Navigator · {range[0]}–{range[1]}
      </div>
      <div
        ref={ref}
        className="relative flex-1 h-full rounded border border-line/60 bg-bg-panel/60 overflow-hidden"
      >
        {/* histogram */}
        <div className="absolute inset-0 flex items-end">
          {volume.map((v, i) => (
            <div
              key={i}
              className="flex-1 mx-[1px] bg-info/40"
              style={{ height: `${(v / vmax) * 85 + 10}%` }}
            />
          ))}
        </div>
        {/* year ticks */}
        <div className="absolute inset-x-0 top-0 h-3 flex items-center">
          {years
            .filter((_, i) => i % 2 === 0)
            .map((y) => (
              <div
                key={y}
                className="absolute text-[9px] text-muted -translate-x-1/2"
                style={{ left: `${pctFromYear(y)}%` }}
              >
                {y}
              </div>
            ))}
        </div>
        {/* selection */}
        <div
          className="absolute top-0 bottom-0 border-l-2 border-r-2 border-info bg-info/10"
          style={{
            left: `${pctFromYear(range[0])}%`,
            right: `${100 - pctFromYear(range[1])}%`,
          }}
          onMouseDown={(e) => {
            if (!ref.current) return;
            const rect = ref.current.getBoundingClientRect();
            const p = ((e.clientX - rect.left) / rect.width) * 100;
            setMoveOffset(p - pctFromYear(range[0]));
            setDrag("move");
          }}
        />
        {/* handles */}
        <div
          className="absolute top-0 bottom-0 w-2 -ml-1 cursor-ew-resize bg-info/80 rounded-sm"
          style={{ left: `${pctFromYear(range[0])}%` }}
          onMouseDown={() => setDrag("start")}
        />
        <div
          className="absolute top-0 bottom-0 w-2 -ml-1 cursor-ew-resize bg-info/80 rounded-sm"
          style={{ left: `${pctFromYear(range[1])}%` }}
          onMouseDown={() => setDrag("end")}
        />
      </div>
    </div>
  );
}
