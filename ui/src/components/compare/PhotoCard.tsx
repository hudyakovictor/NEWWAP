import React, { useState, useEffect } from 'react';
import { FallbackImage } from '../gallery/FallbackImage';
import type { PhotoMeta } from '../../types/api';

interface PhotoCardProps {
  photoId: string;
  onToggle3D?: () => void;
}

export const PhotoCard: React.FC<PhotoCardProps> = ({ photoId, onToggle3D }) => {
  const [photo, setPhoto] = useState<PhotoMeta | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const fetchPhoto = async () => {
      if (!photoId) return;
      setLoading(true);
      try {
        const res = await fetch(`/api/photo/main/${photoId}`);
        const data = await res.json();
        setPhoto(data.record || data);
      } catch (err) {
        console.error('Failed to fetch photo:', err);
      } finally {
        setLoading(false);
      }
    };
    fetchPhoto();
  }, [photoId]);

  if (loading) {
    return <div className="photo-card border p-4 bg-gray-800">Loading...</div>;
  }

  if (!photo) {
    return <div className="photo-card border p-4 bg-gray-800">No photo data</div>;
  }

  return (
    <div className="photo-card border p-4 bg-gray-800 flex flex-col gap-2">
      {photo.source_url ? (
        <img
          src={photo.source_url}
          alt={photo.photo_id}
          className="w-full h-48 object-cover"
          onError={(e) => {
            e.currentTarget.style.display = 'none';
          }}
        />
      ) : (
        <FallbackImage />
      )}
      <div className="text-sm text-gray-300">
        <p>ID: {photo.photo_id}</p>
        <p>Date: {photo.date || photo.date_str || '—'}</p>
        <p>Bucket: {photo.bucket}</p>
        <p>
          Pose: Y={(photo.pose?.yaw ?? 0).toFixed(1)} P={(photo.pose?.pitch ?? 0).toFixed(1)} R={(photo.pose?.roll ?? 0).toFixed(1)}
        </p>
      </div>
      {onToggle3D && (
        <button
          onClick={onToggle3D}
          className="mt-2 bg-gray-700 hover:bg-gray-600 text-white py-1 px-2 rounded text-sm"
        >
          3D View
        </button>
      )}
    </div>
  );
};
