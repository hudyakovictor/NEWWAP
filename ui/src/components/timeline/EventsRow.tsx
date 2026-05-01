
import { LABEL_W } from "./constants";
import type { EventMarker } from "../../mock/data";
import { EventIcon } from "./icons";

const H = 28;

export default function EventsRow({
  years,
  events,
  zoom = 1,
}: {
  years: number[];
  events: EventMarker[];
  zoom?: number;
}) {
  const COL_W = Math.max(80, 120 * zoom);
  const map = new Map<number, EventMarker>();
  events.forEach((e) => map.set(e.year, e));
  return (
    <div className="flex border-b border-line/40">
      <div
        style={{ width: LABEL_W, height: H }}
        className="flex items-center px-3 border-r border-line/60 text-[11px] text-white"
      >
        Events & health
      </div>
      <div className="flex" style={{ width: years.length * COL_W, height: H }}>
        {years.map((y) => {
          const ev = map.get(y);
          return (
            <div
              key={y}
              style={{ width: COL_W }}
              className={`h-full flex items-center justify-center border-r border-line/30`}
              title={ev?.title}
            >
              {ev ? <EventIcon kind={ev.kind} /> : null}
            </div>
          );
        })}
      </div>
    </div>
  );
}
