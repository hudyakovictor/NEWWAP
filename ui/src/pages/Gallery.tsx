import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Search, ChevronLeft, ChevronRight,
  ShieldAlert, Smile
} from 'lucide-react'

interface PhotoItem {
  photo_id: string
  dataset_type: 'main' | 'calibration'
  date_str: string
  date: string
  pose: {
    yaw: number
    pitch: number
    roll: number
    bucket: string
    pose_source: string
  }
  expression_flags: {
    smile: boolean
    jaw_open: boolean
  }
  syntheticProb?: number
  bayesH0?: number
  filename: string
  relative_path: string
}

export function Gallery() {
  const [photos, setPhotos] = useState<PhotoItem[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [pose, setPose] = useState('')
  const [dataset, setDataset] = useState<'main' | 'calibration'>('main')
  const [sortBy, setSortBy] = useState('date')
  const [page, setPage] = useState(1)
  const [selectedPhoto, setSelectedPhoto] = useState<string | null>(null)
  const [selectedDetail, setSelectedDetail] = useState<any>(null)
  const [detailLoading, setDetailLoading] = useState(false)

  // Calibration Override & Manual Extraction states
  const [showOverridePanel, setShowOverridePanel] = useState(false)
  const [calibrationCandidates, setCalibrationCandidates] = useState<any[]>([])
  const [loadingCandidates, setLoadingCandidates] = useState(false)
  const [selectedCandidateId, setSelectedCandidateId] = useState('')
  const [overrideReason, setOverrideReason] = useState('Подбор оптимального ракурса вручную')
  const [submittingOverride, setSubmittingOverride] = useState(false)
  const [uploadingCal, setUploadingCal] = useState(false)
  const [extractingJob, setExtractingJob] = useState(false)
  const [extractingProgress, setExtractingProgress] = useState('')

  const limit = 24
  const offset = (page - 1) * limit

  useEffect(() => {
    setLoading(true)
    const params = new URLSearchParams({
      sortBy,
      limit: String(limit),
      offset: String(offset),
    })
    if (search) params.append('search', search)
    if (pose) params.append('pose', pose)

    fetch(`/api/photos/${dataset}?${params.toString()}`)
      .then((r) => r.json())
      .then((d) => {
        setPhotos(d.items || [])
        setTotal(d.total || 0)
        setLoading(false)
      })
      .catch(() => {
        setLoading(false)
      })
  }, [dataset, search, pose, sortBy, page])

  useEffect(() => {
    if (!selectedPhoto) {
      setSelectedDetail(null)
      return
    }
    setDetailLoading(true)
    fetch(`/api/photo/${dataset}/${selectedPhoto}`)
      .then((r) => r.json())
      .then((d) => {
        setSelectedDetail(d)
        setDetailLoading(false)
      })
      .catch(() => setDetailLoading(false))
  }, [selectedPhoto, dataset])

  const fetchCandidates = (bucket: string) => {
    setLoadingCandidates(true)
    fetch(`/api/photos/calibration?pose=${bucket}&limit=100`)
      .then((r) => r.json())
      .then((d) => {
        setCalibrationCandidates(d.items || [])
        setLoadingCandidates(false)
      })
      .catch(() => setLoadingCandidates(false))
  }

  const submitOverride = (photoId: string, calibrationPhotoId: string) => {
    if (!calibrationPhotoId) return
    setSubmittingOverride(true)
    fetch('/api/calibration/override', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        photo_id: photoId,
        calibration_photo_id: calibrationPhotoId,
        reason: overrideReason,
        author: 'Аналитик (Интерфейс)'
      })
    })
      .then((r) => r.json())
      .then(() => {
        setSubmittingOverride(false)
        setShowOverridePanel(false)
        // Reload photo detail
        setDetailLoading(true)
        fetch(`/api/photo/${dataset}/${photoId}`)
          .then((r) => r.json())
          .then((d) => {
            setSelectedDetail(d)
            setDetailLoading(false)
          })
      })
      .catch(() => setSubmittingOverride(false))
  }

  const handleUploadCalibration = (e: React.ChangeEvent<HTMLInputElement>, photoId: string) => {
    const file = e.target.files?.[0]
    if (!file) return
    setUploadingCal(true)
    const formData = new FormData()
    formData.append('file', file)

    fetch('/api/upload-calibration', {
      method: 'POST',
      body: formData,
    })
      .then((r) => r.json())
      .then((data) => {
        submitOverride(photoId, data.photo_id)
        setUploadingCal(false)
      })
      .catch(() => setUploadingCal(false))
  }

  const triggerJob = (onlyIds?: string[], force: boolean = true) => {
    setExtractingJob(true)
    setExtractingProgress('Запуск фоновой задачи...')
    fetch('/api/jobs/extract', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        dataset: dataset,
        only_ids: onlyIds,
        force: force
      })
    })
      .then((r) => r.json())
      .then((data) => {
        const jobId = data.job_id
        const interval = setInterval(() => {
          fetch(`/api/jobs/${jobId}`)
            .then((r) => r.json())
            .then((job) => {
              if (job.status === 'done') {
                clearInterval(interval)
                setExtractingJob(false)
                setExtractingProgress('')
                setPage(1)
                if (selectedPhoto) {
                  setDetailLoading(true)
                  fetch(`/api/photo/${dataset}/${selectedPhoto}`)
                    .then((r) => r.json())
                    .then((d) => {
                      setSelectedDetail(d)
                      setDetailLoading(false)
                    })
                }
              } else if (job.status === 'failed') {
                clearInterval(interval)
                setExtractingJob(false)
                setExtractingProgress('Ошибка: ' + job.error)
              } else {
                setExtractingProgress(`В процессе... ${job.progress?.completed || 0} из ${job.progress?.total || 0}`)
              }
            })
            .catch(() => {
              clearInterval(interval)
              setExtractingJob(false)
            })
        }, 1000)
      })
      .catch(() => {
        setExtractingJob(false)
        setExtractingProgress('Не удалось запустить')
      })
  }

  const totalPages = Math.ceil(total / limit) || 1

  return (
    <div>
      <div className="page-header">
        <h2>База фотоизображений</h2>
        <p>Архив лиц и параметров 3D-реконструкции</p>
      </div>

      {/* Filters Panel */}
      <div className="panel" style={{ marginBottom: 20 }}>
        <div className="panel-body" style={{ display: 'flex', flexWrap: 'wrap', gap: 12, alignItems: 'center' }}>
          {/* Dataset select */}
          <div style={{ display: 'flex', background: 'var(--bg-secondary)', borderRadius: 'var(--radius-md)', padding: 4 }}>
            <button
              className={`nav-item ${dataset === 'main' ? 'active' : ''}`}
              style={{ padding: '6px 12px', margin: 0, fontSize: 12 }}
              onClick={() => { setDataset('main'); setPage(1) }}
            >
              Основной архив
            </button>
            <button
              className={`nav-item ${dataset === 'calibration' ? 'active' : ''}`}
              style={{ padding: '6px 12px', margin: 0, fontSize: 12 }}
              onClick={() => { setDataset('calibration'); setPage(1) }}
            >
              Калибровка
            </button>
          </div>

          {/* Search bar */}
          <div style={{ position: 'relative', flex: 1, minWidth: 200 }}>
            <Search size={16} style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }} />
            <input
              type="text"
              placeholder="Поиск по ID или имени файла..."
              value={search}
              onChange={(e) => { setSearch(e.target.value); setPage(1) }}
              style={{
                width: '100%',
                background: 'var(--bg-secondary)',
                border: '1px solid var(--border-subtle)',
                borderRadius: 'var(--radius-md)',
                padding: '8px 12px 8px 36px',
                color: 'var(--text-primary)',
                outline: 'none',
                fontSize: 13,
              }}
            />
          </div>

          {/* Pose filter */}
          <div style={{ position: 'relative' }}>
            <select
              value={pose}
              onChange={(e) => { setPose(e.target.value); setPage(1) }}
              style={{
                background: 'var(--bg-secondary)',
                border: '1px solid var(--border-subtle)',
                borderRadius: 'var(--radius-md)',
                padding: '8px 12px 8px 12px',
                color: 'var(--text-primary)',
                outline: 'none',
                fontSize: 13,
                cursor: 'pointer',
              }}
            >
              <option value="">Все ракурсы</option>
              <option value="frontal">🎯 Фронтальный</option>
              <option value="left_profile">◀ Левый профиль</option>
              <option value="right_profile">▶ Правый профиль</option>
              <option value="left_threequarter_deep">↖ Лев. 3/4 глубокий</option>
              <option value="left_threequarter_mid">↖ Лев. 3/4 средний</option>
              <option value="left_threequarter_light">↖ Лев. 3/4 лёгкий</option>
              <option value="right_threequarter_deep">↗ Прав. 3/4 глубокий</option>
              <option value="right_threequarter_mid">↗ Прав. 3/4 средний</option>
              <option value="right_threequarter_light">↗ Прав. 3/4 лёгкий</option>
            </select>
          </div>

          {/* Sorting */}
          <div style={{ position: 'relative' }}>
            <select
              value={sortBy}
              onChange={(e) => { setSortBy(e.target.value); setPage(1) }}
              style={{
                background: 'var(--bg-secondary)',
                border: '1px solid var(--border-subtle)',
                borderRadius: 'var(--radius-md)',
                padding: '8px 12px 8px 12px',
                color: 'var(--text-primary)',
                outline: 'none',
                fontSize: 13,
                cursor: 'pointer',
              }}
            >
              <option value="date">📅 По дате</option>
              <option value="synthetic">🧬 Синтетическая кожа</option>
              <option value="bayes">🔍 Вероятность H0 (Байес)</option>
            </select>
          </div>
        </div>
      </div>

      {/* Main Grid & Results */}
      {loading ? (
        <div className="loading-spinner" />
      ) : (
        <>
          <div className="photo-grid">
            {photos.map((photo) => {
              // Construct image URL
              const imgUrl = `/source/${dataset}/${photo.relative_path || photo.filename}`
              return (
                <div
                  key={photo.photo_id}
                  className="photo-card"
                  onClick={() => setSelectedPhoto(photo.photo_id)}
                >
                  <img src={imgUrl} alt={photo.photo_id} onError={(e) => {
                    (e.target as HTMLImageElement).src = 'https://images.unsplash.com/photo-1544005313-94ddf0286df2?w=150&auto=format&fit=crop&q=60'
                  }} />
                  <div className="photo-meta">
                    <div className="photo-date">{new Date(photo.date).toLocaleDateString('ru-RU')}</div>
                    <div style={{ display: 'flex', gap: 4, marginTop: 4, flexWrap: 'wrap' }}>
                      <span className="badge info" style={{ fontSize: 9, padding: '1px 4px' }}>
                        Y:{Math.round(photo.pose.yaw)}°
                      </span>
                      {photo.syntheticProb !== undefined && photo.syntheticProb > 0.5 && (
                        <span className="badge danger" style={{ fontSize: 9, padding: '1px 4px' }}>
                          Синт.
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              )
            })}
          </div>

          {photos.length === 0 && (
            <div style={{ textAlign: 'center', padding: '40px', color: 'var(--text-muted)' }}>
              Нет результатов по вашему запросу
            </div>
          )}

          {/* Pagination */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 24 }}>
            <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>
              Показано {photos.length} из {total.toLocaleString('ru-RU')} фото
            </span>
            <div style={{ display: 'flex', gap: 8 }}>
              <button
                className="nav-item"
                style={{ padding: 6, width: 32, height: 32, justifyContent: 'center' }}
                disabled={page === 1}
                onClick={() => setPage(p => Math.max(p - 1, 1))}
              >
                <ChevronLeft size={16} />
              </button>
              <span style={{ display: 'flex', alignItems: 'center', fontSize: 13, padding: '0 8px' }}>
                Страница {page} из {totalPages}
              </span>
              <button
                className="nav-item"
                style={{ padding: 6, width: 32, height: 32, justifyContent: 'center' }}
                disabled={page === totalPages}
                onClick={() => setPage(p => Math.min(p + 1, totalPages))}
              >
                <ChevronRight size={16} />
              </button>
            </div>
          </div>
        </>
      )}

      {/* Detail Modal */}
      <AnimatePresence>
        {selectedPhoto && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            style={{
              position: 'fixed',
              top: 0,
              left: 0,
              right: 0,
              bottom: 0,
              background: 'rgba(0,0,0,0.85)',
              zIndex: 1000,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              padding: 24,
            }}
            onClick={() => setSelectedPhoto(null)}
          >
            <motion.div
              initial={{ scale: 0.9, y: 20 }}
              animate={{ scale: 1, y: 0 }}
              exit={{ scale: 0.9, y: 20 }}
              style={{
                width: '100%',
                maxWidth: 960,
                maxHeight: '90vh',
                background: 'var(--bg-card)',
                border: '1px solid var(--border-active)',
                borderRadius: 'var(--radius-lg)',
                boxShadow: 'var(--shadow-card)',
                overflow: 'hidden',
                display: 'flex',
                flexDirection: 'column',
              }}
              onClick={(e) => e.stopPropagation()}
            >
              <div className="panel-header">
                <h3>Подробный криминалистический анализ: {selectedPhoto}</h3>
                <button
                  onClick={() => setSelectedPhoto(null)}
                  style={{
                    background: 'none',
                    border: 'none',
                    color: 'var(--text-muted)',
                    cursor: 'pointer',
                    fontSize: 16,
                  }}
                >
                  ✕
                </button>
              </div>

              <div style={{ overflowY: 'auto', flex: 1, padding: 24 }}>
                {detailLoading ? (
                  <div className="loading-spinner" />
                ) : selectedDetail ? (
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24 }}>
                    {/* Left Column: Images & Calibration */}
                    <div>
                      {/* Side-by-Side Images */}
                      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 16 }}>
                        {/* Main Photo */}
                        <div className="panel" style={{ overflow: 'hidden', background: '#000', textAlign: 'center', margin: 0 }}>
                          <div style={{ fontSize: 11, padding: '4px 8px', background: 'rgba(0,0,0,0.6)', color: '#fff', textAlign: 'left', borderBottom: '1px solid var(--border-subtle)' }}>
                            Исследуемый кадр
                          </div>
                          <img
                            src={selectedDetail.record?.source_url || `/source/${dataset}/${selectedDetail.record?.relative_path || selectedDetail.record?.filename}`}
                            style={{ width: '100%', height: 200, objectFit: 'contain' }}
                            onError={(e) => {
                              (e.target as HTMLImageElement).src = 'https://images.unsplash.com/photo-1544005313-94ddf0286df2?w=500&auto=format&fit=crop&q=60'
                            }}
                          />
                          <div style={{ padding: 8, fontSize: 11, color: 'var(--text-secondary)' }}>
                            {selectedDetail.record?.filename}
                          </div>
                        </div>

                        {/* Matched Calibration Photo */}
                        <div className="panel" style={{ overflow: 'hidden', background: '#000', textAlign: 'center', margin: 0 }}>
                          <div style={{ fontSize: 11, padding: '4px 8px', background: 'rgba(0,0,0,0.6)', color: '#fff', textAlign: 'left', borderBottom: '1px solid var(--border-subtle)', display: 'flex', justifyContent: 'space-between' }}>
                            <span>Калибровочный эталон</span>
                            {selectedDetail.record?.calibration_match && (
                              <span style={{
                                color: selectedDetail.record.calibration_match.score > 0.9 ? 'var(--accent-emerald)' :
                                       selectedDetail.record.calibration_match.score > 0.75 ? 'var(--accent-amber)' : 'var(--accent-red)',
                                fontWeight: 700
                              }}>
                                {(selectedDetail.record.calibration_match.score * 100).toFixed(1)}%
                              </span>
                            )}
                          </div>
                          {selectedDetail.record?.calibration_match ? (
                            <>
                              <img
                                src={selectedDetail.record.calibration_match.source_url || `/source/calibration/${selectedDetail.record.calibration_match.filename}`}
                                style={{ width: '100%', height: 200, objectFit: 'contain' }}
                                onError={(e) => {
                                  (e.target as HTMLImageElement).src = 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=500&auto=format&fit=crop&q=60'
                                }}
                              />
                              <div style={{ padding: 8, fontSize: 11, color: 'var(--text-secondary)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: '60%' }}>
                                  {selectedDetail.record.calibration_match.filename}
                                </span>
                                {selectedDetail.record.calibration_match.manually_overridden && (
                                  <span className="badge info" style={{ fontSize: 9, padding: '2px 4px' }}>Ручной</span>
                                )}
                              </div>
                            </>
                          ) : (
                            <div style={{ height: 200, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)', fontSize: 13, padding: 16 }}>
                              Нет подходящего эталона в ракурсе
                            </div>
                          )}
                        </div>
                      </div>

                      {/* Side-by-Side Poses */}
                      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 16 }}>
                        {/* Main Pose */}
                        <div className="panel" style={{ padding: 12, margin: 0 }}>
                          <h5 style={{ fontSize: 12, marginBottom: 6, color: 'var(--text-muted)' }}>Поза кадра (3DDFA)</h5>
                          <div style={{ display: 'flex', gap: 4, justifyContent: 'space-between', fontSize: 11 }}>
                            <span>Yaw: <b>{selectedDetail.record?.pose?.yaw?.toFixed(1)}°</b></span>
                            <span>Pitch: <b>{selectedDetail.record?.pose?.pitch?.toFixed(1)}°</b></span>
                            <span>Roll: <b>{selectedDetail.record?.pose?.roll?.toFixed(1)}°</b></span>
                          </div>
                          <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 4 }}>
                            Источник: {selectedDetail.record?.pose?.pose_source || 'неизвестно'}
                          </div>
                        </div>

                        {/* Calibration Pose */}
                        <div className="panel" style={{ padding: 12, margin: 0 }}>
                          <h5 style={{ fontSize: 12, marginBottom: 6, color: 'var(--text-muted)' }}>Поза эталона</h5>
                          {selectedDetail.record?.calibration_match ? (
                            <>
                              <div style={{ display: 'flex', gap: 4, justifyContent: 'space-between', fontSize: 11 }}>
                                <span>Yaw: <b>{selectedDetail.record.calibration_match.angles?.[1]?.toFixed(1)}°</b></span>
                                <span>Pitch: <b>{selectedDetail.record.calibration_match.angles?.[0]?.toFixed(1)}°</b></span>
                                <span>Roll: <b>{selectedDetail.record.calibration_match.angles?.[2]?.toFixed(1)}°</b></span>
                              </div>
                              <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 4 }}>
                                Источник: {selectedDetail.record.calibration_match.source || 'автоматически'}
                              </div>
                            </>
                          ) : (
                            <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>Ракурс не определён</div>
                          )}
                        </div>
                      </div>

                      {/* Calibration Controls */}
                      {dataset === 'main' && (
                        <div className="panel" style={{ padding: 14, marginBottom: 16 }}>
                          <h4 style={{ fontSize: 13, marginBottom: 10, color: 'var(--text-secondary)' }}>Управление калибровкой</h4>
                          <div style={{ display: 'flex', gap: 10 }}>
                            <button
                              className="btn btn-secondary"
                              style={{ flex: 1, padding: '8px 12px', fontSize: 12 }}
                              onClick={() => {
                                setShowOverridePanel(!showOverridePanel)
                                if (!showOverridePanel && selectedDetail.record?.pose?.bucket) {
                                  fetchCandidates(selectedDetail.record.pose.bucket)
                                }
                              }}
                            >
                              Изменить калибровочное фото
                            </button>
                            <label
                              className="btn btn-secondary"
                              style={{ flex: 1, padding: '8px 12px', fontSize: 12, cursor: 'pointer', textAlign: 'center', display: 'flex', alignItems: 'center', justifyContent: 'center' }}
                            >
                              <span>{uploadingCal ? 'Загрузка...' : 'Загрузить новое фото'}</span>
                              <input
                                type="file"
                                accept="image/*"
                                onChange={(e) => handleUploadCalibration(e, selectedDetail.record.photo_id)}
                                style={{ display: 'none' }}
                                disabled={uploadingCal}
                              />
                            </label>
                          </div>

                          {/* Override Candidates Sub-panel */}
                          {showOverridePanel && (
                            <div style={{ marginTop: 14, borderTop: '1px solid var(--border-subtle)', paddingTop: 14 }}>
                              <h5 style={{ fontSize: 12, marginBottom: 8, color: 'var(--text-secondary)' }}>Доступные эталоны ({selectedDetail.record?.pose?.bucket}):</h5>
                              {loadingCandidates ? (
                                <div style={{ fontSize: 12, color: 'var(--text-muted)', textAlign: 'center', padding: 8 }}>Загрузка эталонов...</div>
                              ) : calibrationCandidates.length === 0 ? (
                                <div style={{ fontSize: 12, color: 'var(--text-muted)', textAlign: 'center', padding: 8 }}>Нет калибровочных кадров в этом ракурсе</div>
                              ) : (
                                <>
                                  <div style={{ display: 'flex', gap: 8, overflowX: 'auto', paddingBottom: 10, marginBottom: 10 }}>
                                    {calibrationCandidates.map((c) => (
                                      <div
                                        key={c.photo_id}
                                        onClick={() => setSelectedCandidateId(c.photo_id)}
                                        style={{
                                          flexShrink: 0,
                                          width: 90,
                                          border: selectedCandidateId === c.photo_id ? '2px solid var(--accent-blue)' : '1px solid var(--border-subtle)',
                                          borderRadius: 'var(--radius-sm)',
                                          overflow: 'hidden',
                                          cursor: 'pointer',
                                          background: 'var(--bg-secondary)',
                                          padding: 4,
                                          textAlign: 'center'
                                        }}
                                      >
                                        <img
                                          src={c.source_url || `/source/calibration/${c.filename}`}
                                          style={{ width: '100%', height: 60, objectFit: 'contain', background: '#000' }}
                                        />
                                        <div style={{ fontSize: 9, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', marginTop: 4, color: 'var(--text-muted)' }}>
                                          {c.filename}
                                        </div>
                                      </div>
                                    ))}
                                  </div>

                                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                                    <input
                                      type="text"
                                      value={overrideReason}
                                      onChange={(e) => setOverrideReason(e.target.value)}
                                      placeholder="Обоснование ручной привязки..."
                                      style={{
                                        width: '100%',
                                        background: 'var(--bg-secondary)',
                                        border: '1px solid var(--border-subtle)',
                                        borderRadius: 'var(--radius-sm)',
                                        padding: '6px 10px',
                                        fontSize: 12,
                                        color: 'var(--text-primary)'
                                      }}
                                    />
                                    <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
                                      <button
                                        className="btn btn-secondary"
                                        style={{ padding: '4px 10px', fontSize: 11 }}
                                        onClick={() => setShowOverridePanel(false)}
                                      >
                                        Отмена
                                      </button>
                                      <button
                                        className="btn"
                                        style={{ background: 'var(--accent-blue)', color: '#fff', padding: '4px 10px', fontSize: 11 }}
                                        onClick={() => submitOverride(selectedDetail.record.photo_id, selectedCandidateId)}
                                        disabled={submittingOverride || !selectedCandidateId}
                                      >
                                        {submittingOverride ? 'Применение...' : 'Принять привязку'}
                                      </button>
                                    </div>
                                  </div>
                                </>
                              )}
                            </div>
                          )}
                        </div>
                      )}

                      {/* Expression flags */}
                      <div style={{ display: 'flex', gap: 12 }}>
                        {selectedDetail.record?.expression_flags?.smile && (
                          <div className="badge warn" style={{ flex: 1, padding: 8, justifyContent: 'center' }}>
                            <Smile size={14} style={{ marginRight: 6 }} /> Обнаружена улыбка
                          </div>
                        )}
                        {selectedDetail.record?.expression_flags?.jaw_open && (
                          <div className="badge danger" style={{ flex: 1, padding: 8, justifyContent: 'center' }}>
                            <ShieldAlert size={14} style={{ marginRight: 6 }} /> Открытый рот (исключен)
                          </div>
                        )}
                      </div>
                    </div>

                    {/* Right Column: Metrics, Verdicts & Job Extraction */}
                    <div>
                      {/* Bayesian Verdict */}
                      {selectedDetail.record?.bayesH0 !== undefined && (
                        <div className="panel" style={{ padding: 14, marginBottom: 16, borderLeft: '4px solid var(--accent-blue)' }}>
                          <h4 style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 4 }}>Байесовский анализ идентичности</h4>
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <span style={{ fontSize: 14, fontWeight: 600 }}>Вероятность H0 (Оригинал):</span>
                            <span style={{ fontSize: 18, fontWeight: 800, color: 'var(--accent-blue)' }}>
                              {(selectedDetail.record.bayesH0 * 100).toFixed(1)}%
                            </span>
                          </div>
                        </div>
                      )}

                      {/* Synthetic skin probability */}
                      {selectedDetail.record?.syntheticProb !== undefined && (
                        <div className="panel" style={{ padding: 14, marginBottom: 16, borderLeft: '4px solid var(--accent-red)' }}>
                          <h4 style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 4 }}>Спектральный анализ текстуры кожи</h4>
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <span style={{ fontSize: 14, fontWeight: 600 }}>Силикон / Грим (Синтетика):</span>
                            <span style={{ fontSize: 18, fontWeight: 800, color: 'var(--accent-red)' }}>
                              {(selectedDetail.record.syntheticProb * 100).toFixed(1)}%
                            </span>
                          </div>
                        </div>
                      )}

                      {/* Anatomical metrics list */}
                      <h4 style={{ fontSize: 13, marginBottom: 10, color: 'var(--text-secondary)' }}>Абсолютные анатомические метрики</h4>
                      <div className="panel" style={{ maxHeight: 200, overflowY: 'auto', marginBottom: 16 }}>
                        {selectedDetail.record?.metrics ? (
                          Object.entries(selectedDetail.record.metrics).map(([key, val]: [string, any]) => {
                            if (typeof val !== 'number') return null
                            return (
                              <div key={key} style={{
                                display: 'flex',
                                justifyContent: 'space-between',
                                padding: '8px 12px',
                                borderBottom: '1px solid var(--border-subtle)',
                                fontSize: 12
                              }}>
                                <span style={{ color: 'var(--text-secondary)' }}>{formatMetricName(key)}</span>
                                <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{val.toFixed(4)}</span>
                              </div>
                            )
                          })
                        ) : (
                          <div style={{ padding: 20, textAlign: 'center', color: 'var(--text-muted)' }}>
                            Метрики не вычислены для этого кадра
                          </div>
                        )}
                      </div>

                      {/* On-Demand Extraction Jobs */}
                      <div className="panel" style={{ padding: 14 }}>
                        <h4 style={{ fontSize: 13, marginBottom: 10, color: 'var(--text-secondary)' }}>Экстракция и перерасчет данных</h4>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                          <div style={{ display: 'flex', gap: 8 }}>
                            <button
                              className="btn btn-secondary"
                              style={{ flex: 1, padding: '6px 10px', fontSize: 11, background: 'var(--bg-secondary)' }}
                              onClick={() => triggerJob([selectedDetail.record.photo_id], true)}
                              disabled={extractingJob}
                            >
                              Пересчитать этот кадр
                            </button>
                            <button
                              className="btn btn-secondary"
                              style={{ flex: 1, padding: '6px 10px', fontSize: 11, background: 'var(--bg-secondary)' }}
                              onClick={() => {
                                // Find all photos in current bucket and trigger
                                const inBucketIds = photos.filter(p => p.pose?.bucket === selectedDetail.record?.pose?.bucket).map(p => p.photo_id)
                                triggerJob(inBucketIds, true)
                              }}
                              disabled={extractingJob}
                            >
                              Пересчитать ракурс
                            </button>
                          </div>
                          <button
                            className="btn btn-secondary"
                            style={{ width: '100%', padding: '6px 10px', fontSize: 11, background: 'var(--bg-secondary)', color: 'var(--accent-red)', borderColor: 'var(--accent-red)' }}
                            onClick={() => triggerJob(undefined, true)}
                            disabled={extractingJob}
                          >
                            Пересчитать весь архив
                          </button>

                          {extractingJob && (
                            <div style={{ marginTop: 8 }}>
                              <div style={{ fontSize: 11, color: 'var(--text-primary)', marginBottom: 4, fontWeight: 600 }}>
                                {extractingProgress}
                              </div>
                              <div style={{ height: 6, background: 'var(--bg-secondary)', borderRadius: 3, overflow: 'hidden' }}>
                                <motion.div
                                  style={{ height: '100%', background: 'var(--gradient-primary)' }}
                                  animate={{ width: ['0%', '100%'] }}
                                  transition={{ repeat: Infinity, duration: 1.5, ease: 'easeInOut' }}
                                />
                              </div>
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  </div>
                ) : (
                  <div style={{ textAlign: 'center', padding: 40 }}>Не удалось загрузить детали фотографии</div>
                )}
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

function formatMetricName(name: string): string {
  const map: Record<string, string> = {
    eyebrow_distance: '↔️ Межбровное расстояние',
    eyebrow_height_left: '↕️ Высота брови (Л)',
    eyebrow_height_right: '↕️ Высота брови (П)',
    eye_aperture_left: '👁 Раскрытие глаза (Л)',
    eye_aperture_right: '👁 Раскрытие глаза (П)',
    nose_width: '👃 Ширина носа',
    nose_bridge_width: '👃 Ширина переносицы',
    nose_length: '📏 Длина носа',
    lip_thickness_upper: '👄 Толщина верхней губы',
    lip_thickness_lower: '👄 Толщина нижней губы',
    mouth_width: '👄 Ширина рта',
    jaw_width: '📐 Ширина челюсти',
    forehead_height: '🦲 Высота лба',
    cheekbone_width: '📐 Ширина скул',
    orbital_asymmetry_index: '🚨 Асимметрия орбит (периметр)',
    orbital_height_signed: '🚨 Асимметрия орбит по высоте (signed)',
    cranial_face_index: '💀 Краниальный индекс',
  }
  return map[name] ?? name
}
