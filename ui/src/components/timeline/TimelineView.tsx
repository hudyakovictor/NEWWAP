import { useRef, useEffect, useState } from "react";
import {
  YEARS,
  yearPoints,
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
import StubBanner from "../common/StubBanner";

export default function TimelineView() {
  const [selectedYear, setSelectedYear] = useState(2012);
  const [openYear, setOpenYear] = useState<number | null>(null);
  const [range, setRange] = useState<[number, number]>([1999, 2025]);
  const years = YEARS;

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
  const openPoint = openIdx >= 0 ? yearPoints[openIdx] : null;

  return (
    <div className="flex-1 flex flex-col min-h-0">
      <div className="px-3 pt-2">
        <StubBanner
          fields={["7 top metric rows (skull, neuro, orbital, BMI, synth, LBP, age)", "anomaly markers", "identity clusters", "events"]}
          note="Year anchor photos are REAL (frontal pick from main). Bottom 3 metric rows (Photos/year, Mean |yaw|/year, Frontal ratio/year) are REAL from the head-pose pipeline. Top 7 metric rows are still synthetic until texture/zone pipelines run."
        />
      </div>
      <div ref={scrollRef} className="relative flex-1 overflow-auto bg-bg min-h-0">
        <div
          className="relative flex flex-col h-full"
          style={{ minWidth: 168 + years.length * 54 }}
        >
          <YearsRow years={years} selectedYear={selectedYear} onSelect={setSelectedYear} />

          <PhotoStrip
            points={yearPoints}
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
