import React, { useEffect, useState } from 'react';

export const SimilarPhotosSidebar: React.FC<{ targetPhotoId: string }> = ({ targetPhotoId }) => {
  const [similars, setSimilars] = useState<any[]>([]);

  useEffect(() => {
    fetch(`/api/similar-photos/${targetPhotoId}?limit=5`)
      .then(r => r.json())
      .then(setSimilars)
      .catch(console.error);
  }, [targetPhotoId]);

  if (!similars.length) return <div className="text-gray-500">Поиск совпадений...</div>;

  return (
    <div className="similar-photos mt-6 border-t border-gray-700 pt-4">
      <h3 className="text-lg text-white mb-4">Наиболее похожие (H0 Score)</h3>
      <div className="flex flex-col gap-3">
        {similars.map((photo) => (
          <div key={photo.photo_id} className="flex items-center gap-3 bg-gray-800 p-2 rounded">
            <img src={`/storage/main/${photo.photo_id}/${photo.filename}`} className="w-12 h-12 object-cover rounded" />
            <div className="flex-1">
              <p className="text-sm text-gray-300 truncate w-32">{photo.photo_id}</p>
              {/* Показываем скор сходства */}
              <p className="text-xs font-bold text-green-400">Match: {(photo.h0_score * 100).toFixed(1)}%</p>
            </div>
            <button className="bg-blue-600 text-xs px-2 py-1 rounded text-white">Сравнить</button>
          </div>
        ))}
      </div>
    </div>
  );
};
