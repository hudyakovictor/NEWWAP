import { useState } from "react";
import { LABEL_W } from "./constants";
import type { PhotoPoint } from "../../mock/data";
import { SeverityIcon } from "./icons";
import PhotoDetailModal from "../photo/PhotoDetailModal";

const THUMB_SIZE = 50; // Fixed 50x50 thumbnails

export default function PhotoStrip({
  points,
  selectedIndex,
  onSelect,
  zoom = 1,
}: {
  points: PhotoPoint[];
  selectedIndex: number;
  onSelect: (index: number) => void;
  zoom?: number;
}) {
  const [openPhotoIdx, setOpenPhotoIdx] = useState<number | null>(null);
  
  // Fixed thumbnail size 50x50, zoom scales the gap
  const photoSize = THUMB_SIZE;
  const gapSize = Math.max(2, 4 * zoom);
  
  return (
    <>
      <div className="flex items-center" style={{ height: photoSize + 16 }}>
        <div
          style={{ width: LABEL_W }}
          className="flex flex-col justify-center px-3 border-r border-line/60"
        >
          <div className="text-[11px] text-white font-medium">Subject timeline</div>
          <div className="text-[10px] text-muted">{points.length} photos</div>
        </div>
        <div className="flex items-center pr-4">
          {points.map((p, idx) => {
            const selected = idx === selectedIndex;
            
            return (
              <button
                key={p.photoId}
                onClick={() => {
                  onSelect(idx);
                  setOpenPhotoIdx(idx);
                }}
                style={{ 
                  width: photoSize, 
                  height: photoSize,
                  marginRight: gapSize,
                }}
                className={`relative shrink-0 rounded-sm overflow-hidden border transition-all ${
                  selected
                    ? "border-ok ring-2 ring-ok/50"
                    : "border-[#1a2b44]/60 hover:border-ok"
                }`}
                title={`${p.year} · ${p.pose.classification} · yaw:${p.pose.yaw?.toFixed(1) ?? '?'}`}
              >
                <img
                  src={p.photo}
                  alt={`${p.year}-${p.photoId}`}
                  className="w-full h-full object-cover"
                  loading="lazy"
                  draggable={false}
                />
                {/* Identity badge */}
                {p.identity === "B" && (
                  <div className="absolute top-0 right-0 text-[7px] px-0.5 bg-accent/80 text-white rounded-bl">
                    B
                  </div>
                )}
                {/* Anomaly indicator */}
                {p.anomaly && (
                  <div className="absolute bottom-0 left-0 right-0 h-1 bg-danger/60" />
                )}
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
        <div className="flex items-center">
          {points.map((p) => (
            <div
              key={`${p.photoId}-anomaly`}
              style={{ width: photoSize, marginRight: gapSize }}
              className="h-full flex items-start justify-center pt-0.5 relative"
              title={p.note}
            >
              {p.anomaly ? <SeverityIcon s={p.anomaly} /> : null}
            </div>
          ))}
        </div>
      </div>
      
      {/* Photo detail modal */}
      {openPhotoIdx !== null && (
        <PhotoDetailModal
          photoUrl={points[openPhotoIdx]?.photo || ""}
          year={points[openPhotoIdx]?.year || 0}
          onClose={() => setOpenPhotoIdx(null)}
        />
      )}
    </>
  );
}
