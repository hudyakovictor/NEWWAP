import React, { useMemo, useState, useEffect } from 'react';
import { Canvas } from '@react-three/fiber';
import { OrbitControls } from '@react-three/drei';
import * as THREE from 'three';
import type { MeshData } from '../../types/api';

interface MeshViewerProps {
  dataset?: string;
  photoId?: string;
  vertices?: number[][];
  triangles?: number[][];
  uvCoords?: number[][];
  textureUrl?: string;
  vertexColors?: Float32Array;
  wireframe?: boolean;
}

export const MeshViewer: React.FC<MeshViewerProps> = ({ dataset, photoId, vertices, triangles, uvCoords, vertexColors, wireframe = false }) => {
  const [meshData, setMeshData] = useState<MeshData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (vertices && triangles) {
      setMeshData({ vertices, triangles });
      return;
    }

    if (!dataset || !photoId) return;

    const fetchMesh = async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await fetch(`/api/mesh/${dataset}/${photoId}`);
        if (!res.ok) throw new Error('Mesh not found');
        const data = await res.json();
        setMeshData(data);
      } catch (err) {
        setError('3D-сетка недоступна');
        console.error('Failed to load mesh:', err);
      } finally {
        setLoading(false);
      }
    };
    fetchMesh();
  }, [dataset, photoId, vertices, triangles]);

  if (loading) {
    return <div className="flex items-center justify-center h-48 text-gray-400">Loading 3D mesh...</div>;
  }

  if (error || !meshData) {
    return <div className="flex items-center justify-center h-48 text-gray-500">{error || 'No mesh data'}</div>;
  }

  const geometry = useMemo(() => {
    if (!meshData) return null;

    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.Float32BufferAttribute(new Float32Array(meshData.vertices.flat()), 3));
    const meshUv = uvCoords || meshData.uv_coords;
    if (meshUv?.length) {
      geo.setAttribute('uv', new THREE.Float32BufferAttribute(new Float32Array(meshUv.flat()), 2));
    }
    if (vertexColors) {
      geo.setAttribute('color', new THREE.Float32BufferAttribute(vertexColors, 3));
    }
    geo.setIndex(meshData.triangles.flat());
    geo.computeVertexNormals();
    return geo;
  }, [meshData, uvCoords, vertexColors]);

  return (
    <Canvas camera={{ position: [0, 0, 300], fov: 45 }}>
      <ambientLight intensity={0.6} />
      <directionalLight position={[10, 10, 5]} intensity={1} />
      <OrbitControls enablePan={true} enableZoom={true} />
      <mesh>
        {geometry && <primitive object={geometry} attach="geometry" />}
        <meshStandardMaterial
          attach="material"
          vertexColors={!!vertexColors}
          wireframe={wireframe}
          side={THREE.DoubleSide}
        />
      </mesh>
    </Canvas>
  );
};
