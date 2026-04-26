import { useEffect, useRef, useState } from "react";
import type * as THREE_NS from "three";

// Minimal OBJ loader — supports v/vn/vt/f with the common subset produced
// by 3DDFA_v3 exports.
function parseOBJ(THREE: typeof THREE_NS, src: string): THREE_NS.BufferGeometry {
  const positions: number[] = [];
  const vertices: number[][] = [];
  const lines = src.split(/\r?\n/);
  for (const raw of lines) {
    const line = raw.trim();
    if (!line || line.startsWith("#")) continue;
    const parts = line.split(/\s+/);
    const cmd = parts[0];
    if (cmd === "v") {
      vertices.push([+parts[1], +parts[2], +parts[3]]);
    } else if (cmd === "f") {
      const idx = parts.slice(1).map((p) => parseInt(p.split("/")[0], 10) - 1);
      for (let i = 1; i < idx.length - 1; i++) {
        const a = vertices[idx[0]];
        const b = vertices[idx[i]];
        const c = vertices[idx[i + 1]];
        if (!a || !b || !c) continue;
        positions.push(...a, ...b, ...c);
      }
    }
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  geo.computeVertexNormals();
  geo.center();
  return geo;
}

export default function MeshViewer({ objUrl }: { objUrl: string }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    let disposed = false;
    let cleanup: (() => void) | null = null;

    (async () => {
      const THREE = (await import("three")) as typeof THREE_NS;
      if (disposed || !container) return;

      const width = container.clientWidth;
      const height = container.clientHeight;

      const scene = new THREE.Scene();
      scene.background = new THREE.Color(0x061019);

      const camera = new THREE.PerspectiveCamera(35, width / height, 0.01, 1000);
      camera.position.set(0, 0, 3);

      const renderer = new THREE.WebGLRenderer({ antialias: true });
      renderer.setPixelRatio(window.devicePixelRatio);
      renderer.setSize(width, height);
      container.appendChild(renderer.domElement);

      scene.add(new THREE.AmbientLight(0x6688aa, 0.55));
      const key = new THREE.DirectionalLight(0xffffff, 0.9);
      key.position.set(1, 1.5, 2);
      scene.add(key);
      const rim = new THREE.DirectionalLight(0xa855f7, 0.45);
      rim.position.set(-1.5, 0.5, -1);
      scene.add(rim);

      let mesh: THREE_NS.Mesh | null = null;
      let wireframe: THREE_NS.LineSegments | null = null;

      try {
        const resp = await fetch(objUrl);
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const text = await resp.text();
        if (disposed) return;
        const geo = parseOBJ(THREE, text);
        geo.computeBoundingSphere();
        const r = geo.boundingSphere?.radius ?? 1;
        geo.scale(1 / r, 1 / r, 1 / r);

        const material = new THREE.MeshStandardMaterial({
          color: 0xcfd8e6,
          metalness: 0.15,
          roughness: 0.55,
          flatShading: false,
        });
        mesh = new THREE.Mesh(geo, material);
        scene.add(mesh);

        const wire = new THREE.WireframeGeometry(geo);
        const wireMat = new THREE.LineBasicMaterial({
          color: 0x38bdf8,
          transparent: true,
          opacity: 0.15,
        });
        wireframe = new THREE.LineSegments(wire, wireMat);
        scene.add(wireframe);
        setLoading(false);
      } catch (e: any) {
        setError(String(e?.message ?? e));
        return;
      }

      let dragging = false;
      let lastX = 0;
      let lastY = 0;
      let rotY = 0;
      let rotX = 0;

      const onDown = (e: MouseEvent) => {
        dragging = true;
        lastX = e.clientX;
        lastY = e.clientY;
      };
      const onMove = (e: MouseEvent) => {
        if (!dragging) return;
        rotY += (e.clientX - lastX) * 0.01;
        rotX += (e.clientY - lastY) * 0.01;
        rotX = Math.max(-Math.PI / 2.2, Math.min(Math.PI / 2.2, rotX));
        lastX = e.clientX;
        lastY = e.clientY;
      };
      const onUp = () => {
        dragging = false;
      };
      const onWheel = (e: WheelEvent) => {
        e.preventDefault();
        camera.position.z = Math.max(1.3, Math.min(6, camera.position.z + e.deltaY * 0.002));
      };
      renderer.domElement.addEventListener("mousedown", onDown);
      window.addEventListener("mousemove", onMove);
      window.addEventListener("mouseup", onUp);
      renderer.domElement.addEventListener("wheel", onWheel, { passive: false });

      let frame = 0;
      const tick = () => {
        if (disposed) return;
        if (mesh) {
          mesh.rotation.y = rotY;
          mesh.rotation.x = rotX;
        }
        if (wireframe && mesh) wireframe.rotation.copy(mesh.rotation);
        if (!dragging) rotY += 0.003;
        renderer.render(scene, camera);
        frame = requestAnimationFrame(tick);
      };
      tick();

      const onResize = () => {
        if (!container) return;
        const w = container.clientWidth;
        const h = container.clientHeight;
        camera.aspect = w / h;
        camera.updateProjectionMatrix();
        renderer.setSize(w, h);
      };
      const ro = new ResizeObserver(onResize);
      ro.observe(container);

      cleanup = () => {
        cancelAnimationFrame(frame);
        ro.disconnect();
        renderer.domElement.removeEventListener("mousedown", onDown);
        window.removeEventListener("mousemove", onMove);
        window.removeEventListener("mouseup", onUp);
        renderer.domElement.removeEventListener("wheel", onWheel);
        scene.traverse((obj) => {
          const a = obj as any;
          a.geometry?.dispose?.();
          a.material?.dispose?.();
        });
        renderer.dispose();
        if (renderer.domElement.parentNode === container) {
          container.removeChild(renderer.domElement);
        }
      };
    })();

    return () => {
      disposed = true;
      cleanup?.();
    };
  }, [objUrl]);

  return (
    <div className="relative w-full h-full bg-bg-deep rounded">
      <div ref={containerRef} className="absolute inset-0" />
      {loading && !error && (
        <div className="absolute inset-0 grid place-items-center text-[11px] text-muted">
          Loading mesh …
        </div>
      )}
      {error && (
        <div className="absolute inset-0 grid place-items-center text-[11px] text-danger">
          Failed to load mesh: {error}
        </div>
      )}
      <div className="absolute bottom-1 right-1 text-[9px] text-muted bg-bg/60 px-1 rounded">
        drag to rotate · wheel to zoom
      </div>
    </div>
  );
}
