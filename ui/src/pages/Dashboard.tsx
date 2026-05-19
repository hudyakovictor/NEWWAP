import { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import {
  Camera, AlertTriangle, BarChart3, Shield,
  Activity, Eye, Skull
} from 'lucide-react'

interface OverviewData {
  total_photos: number
  total_main: number
  total_calibration: number
  total_pairs: number
  total_anomalies: number
  total_metrics: number
  buckets: Record<string, number>
  calibration_quality: Record<string, number>
}

export function Dashboard() {
  const [data, setData] = useState<OverviewData | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch('/api/overview')
      .then(r => r.json())
      .then(d => {
        const auditScores = Array.isArray(d.audit_current)
          ? d.audit_current.map((item: any) => Number(item.score) || 0)
          : []
        const avgAuditScore = auditScores.length
          ? Math.round(auditScores.reduce((sum: number, score: number) => sum + score, 0) / auditScores.length)
          : 0
        setData({
          total_photos: d.source_photo_total ?? 0,
          total_main: d.source_photo_total ?? 0,
          total_calibration: d.source_calibration_total ?? 0,
          total_pairs: d.timeline_summary?.transitions ?? 0,
          total_anomalies: (d.timeline_summary?.impossible_changes ?? 0) + (d.timeline_summary?.long_gaps ?? 0),
          total_metrics: d.calibration?.stable_metrics ?? 0,
          buckets: d.timeline_summary?.angle_coverage ?? {},
          calibration_quality: {
            high: d.calibration?.stable_metrics ?? 0,
            medium: d.calibration?.marginal_metrics ?? 0,
            marginal: d.calibration?.replace_metrics ?? 0,
            low: Math.max(0, 100 - avgAuditScore),
          },
        })
        setLoading(false)
      })
      .catch(() => {
        // Fallback to compiled data
        fetch('/storage/master_ui_data.json')
          .then(r => r.json())
          .then(d => {
            setData({
              total_photos: d.summary?.total_photos ?? 1947,
              total_main: d.summary?.main_photos ?? 1723,
              total_calibration: d.summary?.calibration_photos ?? 224,
              total_pairs: d.summary?.total_pairs ?? 1723,
              total_anomalies: d.summary?.total_anomalies ?? 15120,
              total_metrics: d.summary?.total_metrics ?? 41000,
              buckets: d.summary?.buckets ?? {},
              calibration_quality: d.summary?.calibration_quality ?? {},
            })
            setLoading(false)
          })
          .catch(() => setLoading(false))
      })
  }, [])

  if (loading) return <div className="loading-spinner" />

  const stats = [
    { icon: Camera, label: 'Основных фото', value: data?.total_main ?? '—', color: 'blue' },
    { icon: Shield, label: 'Калибровочных', value: data?.total_calibration ?? '—', color: 'cyan' },
    { icon: BarChart3, label: 'Переходов', value: data?.total_pairs ?? '—', color: 'emerald' },
    { icon: AlertTriangle, label: 'Аномалий', value: data?.total_anomalies ?? '—', color: 'red' },
    { icon: Activity, label: 'Метрик', value: data?.total_metrics ?? '—', color: 'purple' },
    { icon: Eye, label: 'Всего фото', value: data?.total_photos ?? '—', color: 'amber' },
  ]

  const buckets = data?.buckets ?? {}
  const bucketEntries = Object.entries(buckets).sort((a, b) => b[1] - a[1])
  const maxBucket = Math.max(...Object.values(buckets), 1)

  const calQuality = data?.calibration_quality ?? {}

  return (
    <div>
      <div className="page-header">
        <h2>Криминалистическая панель</h2>
        <p>Обзор 3D-аудита фотоархива Путина (1999–2025)</p>
      </div>

      <div className="stats-grid">
        {stats.map((s, i) => (
          <motion.div
            key={s.label}
            className="stat-card"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.08, duration: 0.4 }}
          >
            <div className={`stat-icon ${s.color}`}>
              <s.icon size={20} />
            </div>
            <div className="stat-value">
              {typeof s.value === 'number' ? s.value.toLocaleString('ru-RU') : s.value}
            </div>
            <div className="stat-label">{s.label}</div>
          </motion.div>
        ))}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 20 }}>
        {/* Bucket distribution */}
        <motion.div
          className="panel"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.5 }}
        >
          <div className="panel-header">
            <h3>Распределение по ракурсам</h3>
            <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
              {bucketEntries.length} групп
            </span>
          </div>
          <div className="panel-body">
            {bucketEntries.map(([bucket, count]) => (
              <div key={bucket} style={{ marginBottom: 12 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                  <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
                    {formatBucket(bucket)}
                  </span>
                  <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>
                    {count}
                  </span>
                </div>
                <div style={{
                  height: 6,
                  background: 'var(--bg-secondary)',
                  borderRadius: 3,
                  overflow: 'hidden'
                }}>
                  <motion.div
                    style={{
                      height: '100%',
                      background: 'var(--gradient-primary)',
                      borderRadius: 3,
                    }}
                    initial={{ width: 0 }}
                    animate={{ width: `${(count / maxBucket) * 100}%` }}
                    transition={{ duration: 0.8, delay: 0.6 }}
                  />
                </div>
              </div>
            ))}
          </div>
        </motion.div>

        {/* Calibration quality */}
        <motion.div
          className="panel"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.6 }}
        >
          <div className="panel-header">
            <h3>Качество калибровки</h3>
          </div>
          <div className="panel-body">
            {['high', 'medium', 'marginal', 'low'].map((level) => {
              const count = calQuality[level] ?? 0
              const total = Object.values(calQuality).reduce((a, b) => a + b, 0) || 1
              const pct = ((count / total) * 100).toFixed(1)
              const colors: Record<string, string> = {
                high: 'var(--accent-emerald)',
                medium: 'var(--accent-cyan)',
                marginal: 'var(--accent-amber)',
                low: 'var(--accent-red)',
              }
              const labels: Record<string, string> = {
                high: 'Высокое',
                medium: 'Среднее',
                marginal: 'Погранич.',
                low: 'Низкое',
              }
              return (
                <div key={level} style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: '10px 0',
                  borderBottom: '1px solid var(--border-subtle)'
                }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <div style={{
                      width: 10, height: 10, borderRadius: '50%',
                      background: colors[level],
                    }} />
                    <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
                      {labels[level]}
                    </span>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <span style={{ fontSize: 15, fontWeight: 700, color: 'var(--text-primary)' }}>
                      {count}
                    </span>
                    <span style={{ fontSize: 11, color: 'var(--text-muted)', marginLeft: 6 }}>
                      {pct}%
                    </span>
                  </div>
                </div>
              )
            })}

            <div style={{
              marginTop: 20,
              padding: 14,
              background: 'var(--bg-secondary)',
              borderRadius: 'var(--radius-md)',
              textAlign: 'center'
            }}>
              <Skull size={24} style={{ color: 'var(--accent-red)', marginBottom: 8 }} />
              <div style={{ fontSize: 11, color: 'var(--text-muted)', lineHeight: 1.5 }}>
                Статус считается по текущим<br />summary.json и калибровке
              </div>
            </div>
          </div>
        </motion.div>
      </div>
    </div>
  )
}

function formatBucket(bucket: string): string {
  const map: Record<string, string> = {
    frontal: '🎯 Фронтальный',
    left_profile: '◀ Левый профиль',
    right_profile: '▶ Правый профиль',
    left_threequarter_deep: '↖ Лев. 3/4 глубокий',
    left_threequarter_mid: '↖ Лев. 3/4 средний',
    left_threequarter_light: '↖ Лев. 3/4 лёгкий',
    right_threequarter_deep: '↗ Прав. 3/4 глубокий',
    right_threequarter_mid: '↗ Прав. 3/4 средний',
    right_threequarter_light: '↗ Прав. 3/4 лёгкий',
    unclassified: '❓ Неклассифицированный',
  }
  return map[bucket] ?? bucket
}
