import React, { useState, useEffect } from 'react';
import type { PhotoMeta } from '../../types/api';

interface PhotoPickerProps {
  onSelect: (photoId: string) => void;
  selectedId?: string;
}

export const PhotoPicker: React.FC<PhotoPickerProps> = ({ onSelect, selectedId }) => {
  const [photos, setPhotos] = useState<PhotoMeta[]>([]);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');

  useEffect(() => {
    const fetchPhotos = async () => {
      setLoading(true);
      try {
        const params = new URLSearchParams({
          limit: '30',
          offset: String((page - 1) * 30),
          sortBy: 'date',
        });
        const res = await fetch(`/api/photos/main?${params.toString()}`);
        const data = await res.json();
        setPhotos(data.items || []);
      } catch (err) {
        console.error('Failed to fetch photos:', err);
      } finally {
        setLoading(false);
      }
    };
    fetchPhotos();
  }, [page]);

  const filteredPhotos = photos.filter(p =>
    p.photo_id.toLowerCase().includes(search.toLowerCase()) ||
    (p.filename && p.filename.toLowerCase().includes(search.toLowerCase())) ||
    ((p.date || p.date_str) && String(p.date || p.date_str).includes(search))
  );

  return (
    <div className="photo-picker">
      <input
        type="text"
        placeholder="Search by date or ID..."
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        className="w-full p-2 mb-4 bg-gray-800 text-white border border-gray-600 rounded"
      />
      {loading ? (
        <div className="text-gray-400">Loading...</div>
      ) : (
        <div className="grid grid-cols-4 gap-2 max-h-96 overflow-y-auto">
          {filteredPhotos.map((photo) => (
            <div
              key={photo.photo_id}
              onClick={() => onSelect(photo.photo_id)}
              className={`cursor-pointer p-2 border rounded ${
                selectedId === photo.photo_id ? 'border-blue-500 bg-gray-700' : 'border-gray-600 bg-gray-800'
              }`}
            >
              {photo.source_url || photo.thumbnail_url ? (
                <img src={photo.source_url || photo.thumbnail_url || ''} alt={photo.photo_id} className="w-full h-20 object-cover" />
              ) : (
                <div className="w-full h-20 bg-gray-700 flex items-center justify-center text-xs text-gray-400">
                  No image
                </div>
              )}
              <div className="text-xs text-gray-300 mt-1 truncate">{photo.date || photo.date_str || photo.photo_id}</div>
              <div className="text-[10px] text-gray-500 truncate">{photo.filename || photo.photo_id}</div>
            </div>
          ))}
        </div>
      )}
      <button
        onClick={() => setPage(p => p + 1)}
        className="mt-2 w-full bg-gray-700 hover:bg-gray-600 text-white py-2 rounded"
      >
        Load More
      </button>
    </div>
  );
};
