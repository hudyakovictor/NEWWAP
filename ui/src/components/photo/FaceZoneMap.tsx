import type { FaceZone } from "../../mock/photoDetail";

export default function FaceZoneMap({
  photo,
  zones,
  hovered,
  onHover,
}: {
  photo: string;
  zones: FaceZone[];
  hovered?: string;
  onHover: (id?: string) => void;
}) {
  const colorFor = (z: FaceZone) => {
    if (z.excluded) return "#6b7a90";
    if (!z.visible) return "#233657";
    if (z.score > 0.8) return "#22c55e";
    if (z.score > 0.6) return "#eab308";
    if (z.score > 0.4) return "#f59e0b";
    return "#ef4444";
  };
  return (
    <div className="relative w-full aspect-[3/4] bg-bg-deep rounded-md overflow-hidden border border-line">
      <img src={photo} alt="subject" className="w-full h-full object-cover opacity-80" />
      <svg className="absolute inset-0 w-full h-full" viewBox="0 0 100 100" preserveAspectRatio="none">
        {zones.map((z) => {
          const isHovered = hovered === z.id;
          return (
            <g key={z.id} onMouseEnter={() => onHover(z.id)} onMouseLeave={() => onHover(undefined)}>
              <circle
                cx={z.x}
                cy={z.y}
                r={isHovered ? 2.6 : 1.8}
                fill={colorFor(z)}
                stroke={isHovered ? "#fff" : "#0a1523"}
                strokeWidth={0.3}
                vectorEffect="non-scaling-stroke"
                opacity={z.excluded ? 0.45 : 0.9}
              />
            </g>
          );
        })}
      </svg>
      <div className="absolute bottom-1 left-1 right-1 flex gap-1 text-[9px]">
        <span className="px-1 rounded bg-ok/30 text-ok">bone</span>
        <span className="px-1 rounded bg-accent/30 text-accent">ligament</span>
        <span className="px-1 rounded bg-info/30 text-info">mixed</span>
        <span className="px-1 rounded bg-muted/30 text-muted">excluded</span>
      </div>
    </div>
  );
}
