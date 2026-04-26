
import { COL_W, LABEL_W } from "./constants";

export default function SelectionOverlay({
  years,
  selectedYear,
}: {
  years: number[];
  selectedYear: number;
}) {
  const idx = years.indexOf(selectedYear);
  if (idx < 0) return null;
  return (
    <div
      className="absolute top-0 bottom-0 pointer-events-none border-l border-r border-danger/60"
      style={{
        left: LABEL_W + idx * COL_W,
        width: COL_W,
        background: "linear-gradient(180deg, rgba(239,68,68,0.08), rgba(239,68,68,0.02))",
      }}
    />
  );
}
