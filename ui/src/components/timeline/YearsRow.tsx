
import { COL_W, LABEL_W } from "./constants";

export default function YearsRow({
  years,
  selectedYear,
  onSelect,
}: {
  years: number[];
  selectedYear: number;
  onSelect: (y: number) => void;
}) {
  return (
    <div className="flex h-7 items-end border-b border-line/60 sticky top-0 z-20 bg-bg-panel/90 backdrop-blur">
      <div style={{ width: LABEL_W }} className="h-full border-r border-line/60" />
      <div className="flex">
        {years.map((y) => (
          <button
            key={y}
            onClick={() => onSelect(y)}
            style={{ width: COL_W }}
            className={`text-center text-[10px] font-mono tracking-wider pb-1 transition-colors ${
              y === selectedYear ? "text-white" : "text-muted hover:text-white"
            }`}
          >
            {y}
          </button>
        ))}
      </div>
    </div>
  );
}
