import { useRef, useEffect, useState, useMemo } from "react";
import {
  YEARS,
  buildYearPoints,
  metrics,
  identitySegments,
  eventMarkers,
  photoVolume,
} from "../../mock/data";
import YearsRow from "./YearsRow";
import PhotoStrip from "./PhotoStrip";
import MetricRow from "./MetricRow";
import IdentityRow from "./IdentityRow";
import EventsRow from "./EventsRow";
import SelectionOverlay from "./SelectionOverlay";
import Scrubber from "./Scrubber";
import PhotoDetailModal from "../photo/PhotoDetailModal";

export default function TimelineView() {
  const [selectedYear, setSelectedYear] = useState(2012);
  const [openYear, setOpenYear] = useState<number | null>(null);
  const [range, setRange] = useState<[number, number]>([1999, 2025]);
  const [poseFilter, setPoseFilter] = useState<string>("");
  const years = YEARS;
  
  const currentPoints = useMemo(() => buildYearPoints(poseFilter || undefined), [poseFilter]);

  const scrollRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const idx = years.indexOf(selectedYear);
    const LABEL_W = 168;
    const COL_W = 54;
    const xCenter = LABEL_W + idx * COL_W + COL_W / 2;
    el.scrollTo({ left: xCenter - el.clientWidth / 2, behavior: "smooth" });
  }, [selectedYear, years]);

  const openIdx = openYear !== null ? years.indexOf(openYear) : -1;
  const openPoint = openIdx >= 0 ? currentPoints[openIdx] : null;

  return (
    <div className="flex-1 flex flex-col min-h-0">
      <div className="px-3 pt-2 flex justify-between items-center mb-1">
        <div className="text-text-muted text-sm font-medium">Timeline Anchors</div>
        <select 
          value={poseFilter} 
          onChange={e => setPoseFilter(e.target.value)} 
          className="bg-bg-dark border border-border rounded px-2 py-1 text-xs text-text-muted focus:outline-none"
        >
          <option value="">Auto (Frontal preferred)</option>
          <option value="frontal">Frontal</option>
          <option value="three_quarter_left">3/4 Left</option>
          <option value="three_quarter_right">3/4 Right</option>
          <option value="profile_left">Profile Left</option>
          <option value="profile_right">Profile Right</option>
        </select>
      </div>
      <div ref={scrollRef} className="relative flex-1 overflow-auto bg-bg min-h-0">
        <div
          className="relative flex flex-col h-full"
          style={{ minWidth: 168 + years.length * 54 }}
        >
          <YearsRow years={years} selectedYear={selectedYear} onSelect={setSelectedYear} />

          <PhotoStrip
            points={currentPoints}
            selectedYear={selectedYear}
            onSelect={setSelectedYear}
            onOpen={setOpenYear}
            grow={4}
          />

          {metrics.map((m) => (
            <MetricRow
              key={m.id}
              metric={m}
              years={years}
              selectedYear={selectedYear}
              onSelect={setSelectedYear}
              grow={1.2}
            />
          ))}

          <IdentityRow years={years} segments={identitySegments} />
          <EventsRow years={years} events={eventMarkers} />

          <SelectionOverlay years={years} selectedYear={selectedYear} />
        </div>
      </div>

      <Scrubber years={years} volume={photoVolume} range={range} onRangeChange={setRange} />

      {openPoint && (
        <PhotoDetailModal
          point={openPoint}
          onClose={() => setOpenYear(null)}
          onPrev={openIdx > 0 ? () => setOpenYear(years[openIdx - 1]) : undefined}
          onNext={openIdx < years.length - 1 ? () => setOpenYear(years[openIdx + 1]) : undefined}
        />
      )}
    </div>
  );
}
