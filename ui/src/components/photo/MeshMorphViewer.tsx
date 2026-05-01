import { useEffect, useRef, useState } from "react";
import type * as THREE_NS from "three";

interface MeshData {
  vertices: number[][];
  uv_coords: number[][];
  triangles: number[][];
  normals: number[][];
  vertex_count: number;
  triangle_count: number;
  texture_url: string;
}

async function loadMeshData(dataset: string, photoId: string): Promise<MeshData> {
  const resp = await fetch(`/api/mesh/${dataset}/${photoId}`);
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();
}

function interpolateMesh(
  meshA: MeshData,
  meshB: MeshData,
  t: number,
): { positions: number[]; normals: number[] } {
  if (meshA.vertex_count !== meshB.vertex_count) {
    throw new Error("Meshes have different vertex counts — cannot morph");
  }

  const positions: number[] = [];
  const normals: number[] = [];

  for (let i = 0; i < meshA.vertex_count; i++) {
    const va = meshA.vertices[i];
    const vb = meshB.vertices[i];
    const na = meshA.normals[i] || [0, 0, 1];
    const nb = meshB.normals[i] || [0, 0, 1];

    // Linear interpolation
    positions.push(
      va[0] + (vb[0] - va[0]) * t,
      va[1] + (vb[1] - va[1]) * t,
      va[2] + (vb[2] - va[2]) * t,
    );

    normals.push(
      na[0] + (nb[0] - na[0]) * t,
      na[1] + (nb[1] - na[1]) * t,
      na[2] + (nb[2] - na[2]) * t,
    );
  }

  return { positions, normals };
}

export default function MeshMorphViewer({
  datasetA,
  photoIdA,
  datasetB,
  photoIdB,
}: {
  datasetA: string;
  photoIdA: string;
  datasetB: string;
  photoIdB: string;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [morphT, setMorphT] = useState(0.5);
  const [meshA, setMeshA] = useState<MeshData | null>(null);
  const [meshB, setMeshB] = useState<MeshData | null>(null);

  useEffect(() => {
    (async () => {
      try {
        setLoading(true);
        const [ma, mb] = await Promise.all([
          loadMeshData(datasetA, photoIdA),
          loadMeshData(datasetB, photoIdB),
        ]);
        setMeshA(ma);
        setMeshB(mb);
        setLoading(false);
      } catch (e: any) {
        setError(String(e?.message ?? e));
        setLoading(false);
      }
    })();
  }, [datasetA, photoIdA, datasetB, photoIdB]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container || !meshA || !meshB) return;

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
      let texture: THREE_NS.Texture | null = null;

      // Load texture from meshA (or meshB)
      const texLoader = new THREE.TextureLoader();
      const texUrl = meshA.texture_url || meshB.texture_url;
      if (texUrl) {
        texture = texLoader.load(texUrl);
        texture.colorSpace = THREE.SRGBColorSpace;
        texture.flipY = false;
      }

      // Build triangle index array
      const indices: number[] = [];
      for (const tri of meshA.triangles) {
        indices.push(...tri);
      }

      const updateGeometry = (t: number): THREE_NS.BufferGeometry => {
        if (!meshA || !meshB) return new THREE.BufferGeometry();
        const { positions, normals } = interpolateMesh(meshA, meshB, t);

        const geo = new THREE.BufferGeometry();
        geo.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
        geo.setAttribute("normal", new THREE.Float32BufferAttribute(normals, 3));

        if (meshA.uv_coords && meshA.uv_coords.length > 0) {
          const uvs: number[] = [];
          for (const uv of meshA.uv_coords) {
            uvs.push(uv[0], uv[1]);
          }
          geo.setAttribute("uv", new THREE.Float32BufferAttribute(uvs, 2));
        }

        geo.setIndex(indices);
        geo.computeBoundingSphere();
        const r = geo.boundingSphere?.radius ?? 1;
        geo.scale(1 / r, 1 / r, 1 / r);

        return geo;
      };

      const material = new THREE.MeshStandardMaterial({
        color: texture ? 0xffffff : 0xcfd8e6,
        map: texture,
        metalness: 0.15,
        roughness: 0.55,
        flatShading: false,
      });

      const geo = updateGeometry(morphT);
      mesh = new THREE.Mesh(geo, material);
      scene.add(mesh);

      const wire = new THREE.WireframeGeometry(geo);
      const wireMat = new THREE.LineBasicMaterial({
        color: 0x38bdf8,
        transparent: true,
        opacity: 0.15,
      });
      wireframe = new THREE.LineSegments(wire, wireMat);
      if (wireframe) scene.add(wireframe);

      // Store reference to update on morphT change
      (container as any).__updateMorph = (t: number) => {
        const newGeo = updateGeometry(t);
        mesh!.geometry.dispose();
        mesh!.geometry = newGeo;
        if (wireframe) {
          wireframe.geometry.dispose();
          const newWire = new THREE.WireframeGeometry(newGeo);
          if (newWire) wireframe.geometry = newWire;
        }
      };

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
        texture?.dispose?.();
        if (renderer.domElement.parentNode === container) {
          container.removeChild(renderer.domElement);
        }
        delete (container as any).__updateMorph;
      };
    })();

    return () => {
      disposed = true;
      cleanup?.();
    };
  }, [meshA, meshB]); // Rebuild when meshes load

  // Update morph when slider changes
  useEffect(() => {
    const container = containerRef.current;
    const updateFn = container && (container as any).__updateMorph;
    if (updateFn) {
      updateFn(morphT);
    }
  }, [morphT]);

  return (
    <div className="relative w-full h-full bg-bg-deep rounded">
      <div ref={containerRef} className="absolute inset-0" />
      {loading && !error && (
        <div className="absolute inset-0 grid place-items-center text-[11px] text-muted">
          Loading mesh data …
        </div>
      )}
      {error && (
        <div className="absolute inset-0 grid place-items-center text-[11px] text-danger">
          Failed to load mesh: {error}
        </div>
      )}
      <div className="absolute bottom-1 left-1 right-1 flex items-center gap-2 bg-bg/80 px-2 py-1 rounded">
        <span className="text-[9px] text-muted">{photoIdA}</span>
        <input
          type="range"
          min={0}
          max={1}
          step={0.01}
          value={morphT}
          onChange={(e) => setMorphT(parseFloat(e.target.value))}
          className="flex-1 h-1 bg-line rounded appearance-none cursor-pointer"
        />
        <span className="text-[9px] text-muted">{photoIdB}</span>
      </div>
      <div className="absolute top-1 right-1 text-[9px] text-muted bg-bg/60 px-1 rounded">
        drag to rotate · wheel to zoom
      </div>
    </div>
  );
}
