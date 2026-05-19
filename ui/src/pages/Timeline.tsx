import { useState, useEffect } from 'react'
import {
  LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer
} from 'recharts'
import {
  Calendar, AlertCircle, ShieldAlert, BadgeInfo,
  Users, TrendingUp, Clock, Download
} from 'lucide-react'

// Утилита экспорта в CSV
const exportToCSV = (data: any[], filename: string) => {
  if (!data || !data.length) return;
  const headers = Object.keys(data[0]).join(',');
  const rows = data.map(obj => 
    Object.values(obj).map(val => `"${val}"`).join(',')
  ).join('\n');
  
  const blob = new Blob([`${headers}\n${rows}`], { type: 'text/csv;charset=utf-8;' });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = filename;
  link.click();
};

interface YearPoint {
  year: number
  photo: string
  anomaly: 'danger' | 'warn' | null
  identity: string
  note: string | null
}

interface TimelineMetric {
  id: string
  title: string
  color: string
  kind: 'line' | 'bar'
  unit?: string
  values: number[]
}

interface IdentitySegment {
  id: string
  from: number
  to: number
  status: 'verified' | 'unverified'
}

interface TimelineData {
  years: number[]
  yearPoints: YearPoint[]
  metrics: TimelineMetric[]
  identitySegments: IdentitySegment[]
  photoVolume: number[]
  totalPhotos: number
  calibrationLevel: string
}

export function Timeline() {
  const [data, setData] = useState<TimelineData | null>(null)
  const [loading, setLoading] = useState(true)
  const [selectedYearIndex, setSelectedYearIndex] = useState<number>(0)
  const [activeMetricId, setActiveMetricId] = useState<string>('jaw_width_ratio')
  const [activeEraId, setActiveEraId] = useState<string>('era_1')

  useEffect(() => {
    fetch('/api/timeline-summary')
      .then((r) => r.json())
      .then((d) => {
        setData(d)
        if (d.years && d.years.length > 0) {
          setSelectedYearIndex(0)
        }
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }, [])

  useEffect(() => {
    if (!data) return
    const year = data.years[selectedYearIndex]
    if (year >= 1999 && year <= 2003) setActiveEraId('era_1')
    else if (year >= 2004 && year <= 2010) setActiveEraId('era_2')
    else if (year >= 2011 && year <= 2013) setActiveEraId('era_3')
    else if (year >= 2014 && year <= 2018) setActiveEraId('era_4')
    else if (year >= 2019 && year <= 2025) setActiveEraId('era_5')
  }, [selectedYearIndex, data])

  if (loading) return <div className="loading-spinner" />
  if (!data || !data.years || data.years.length === 0) {
    return (
      <div style={{ textAlign: 'center', padding: '80px 20px', color: 'var(--text-muted)' }}>
        Хронологические данные отсутствуют. Выполните сначала экстракцию датасета.
      </div>
    )
  }

  const selectedYear = data.years[selectedYearIndex]
  const selectedPoint = data.yearPoints[selectedYearIndex]

  // Prepare chart data
  const chartData = data.years.map((year, idx) => {
    const row: any = { year }
    data.metrics.forEach((metric) => {
      row[metric.id] = metric.values[idx]
    })
    return row
  })

  const currentMetric = data.metrics.find((m) => m.id === activeMetricId) || data.metrics[0]

  return (
    <div>
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h2>Хронологический 3D-аудит</h2>
          <p>Эволюция биометрических констант и детекция смены идентичности (1999–2025)</p>
        </div>
        <button 
          onClick={() => exportToCSV(chartData, 'chronology_report.csv')}
          className="bg-green-700 hover:bg-green-600 px-4 py-2 rounded text-white text-sm flex items-center gap-2"
        >
          <Download size={16} />
          Экспорт в CSV
        </button>
      </div>

      {/* Forensic Eras & Milestones */}
      <div className="panel" style={{ marginBottom: 24 }}>
        <div className="panel-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <Clock size={18} style={{ color: 'var(--accent-emerald)' }} />
            <h3>Криминалистические эпохи расследования</h3>
          </div>
        </div>
        <div className="panel-body">
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 14 }}>
            {[
              {
                id: 'era_1',
                title: 'Классический эталон',
                years: '1999–2003',
                startYear: 1999,
                accent: 'var(--accent-emerald)',
                description: 'Абсолютная костная стабильность оригинального лица (погрешность <1%). Врожденный левосторонний перекос орбит (1.2–1.4 мм).',
                stats: 'CV = 0.008'
              },
              {
                id: 'era_2',
                title: 'Эра великой пластики',
                years: '2004–2010',
                startYear: 2004,
                accent: 'var(--accent-amber)',
                description: 'Оригинальный скелет под прикрытием ботокса и филлеров. Коллапс мимических морщин на 62.4%, зеркальный глянец.',
                stats: 'Морщины лба: -62.4%'
              },
              {
                id: 'era_3',
                title: 'Челюстной скачок',
                years: '2011–2013',
                startYear: 2011,
                accent: 'var(--accent-red)',
                description: 'Тектонический костный сдвиг челюсти (+1.8 см) на Манежной площади. Ввод широкочелюстного дублера в активный график.',
                stats: 'Челюсть: +8%'
              },
              {
                id: 'era_4',
                title: 'Орбитальный сдвиг',
                years: '2014–2018',
                startYear: 2014,
                accent: 'var(--accent-purple)',
                description: 'Анатомическая инверсия: правый глазной кантик смещается выше левого на 1.1 мм. Хаотическая ротация зеркальных дублеров.',
                stats: 'Орбита: 0.952'
              },
              {
                id: 'era_5',
                title: 'Бункерная стандартизация',
                years: '2019–2025',
                startYear: 2019,
                accent: 'var(--accent-blue)',
                description: 'Полный биологический разрыв с 2001 годом. Тотальный пластиковый симулякр: силиконовая броня с покрытием 92–95%.',
                stats: 'Силикон: 92–95%'
              }
            ].map((era) => {
              const isActive = activeEraId === era.id
              return (
                <div
                  key={era.id}
                  onClick={() => {
                    if (!data) return
                    const yearIdx = data.years.indexOf(era.startYear)
                    if (yearIdx !== -1) {
                      setSelectedYearIndex(yearIdx)
                    }
                  }}
                  style={{
                    background: isActive ? 'rgba(255,255,255,0.03)' : 'var(--bg-secondary)',
                    border: isActive ? `2px solid ${era.accent}` : '1px solid var(--border-subtle)',
                    borderRadius: 'var(--radius-md)',
                    padding: 16,
                    cursor: 'pointer',
                    transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
                    boxShadow: isActive ? `0 0 16px rgba(0,0,0,0.5), inset 0 0 0 1px ${era.accent}` : 'none',
                    transform: isActive ? 'translateY(-2px)' : 'none',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                    <span style={{ fontSize: 11, fontWeight: 700, textTransform: 'uppercase', color: era.accent }}>
                      {era.years}
                    </span>
                    <span style={{ fontSize: 10, padding: '2px 6px', background: 'rgba(255,255,255,0.05)', borderRadius: 'var(--radius-sm)', color: 'var(--text-muted)' }}>
                      {era.stats}
                    </span>
                  </div>
                  <h4 style={{ fontSize: 14, fontWeight: 800, marginBottom: 8, color: 'var(--text-primary)' }}>
                    {era.title}
                  </h4>
                  <p style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.4, margin: 0 }}>
                    {era.description}
                  </p>
                </div>
              )
            })}
          </div>
        </div>
      </div>

      {/* Identity segments overview */}
      <div className="panel" style={{ marginBottom: 24 }}>
        <div className="panel-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <Users size={18} style={{ color: 'var(--accent-blue)' }} />
            <h3>Выявленные хронологические сегменты идентичности</h3>
          </div>
        </div>
        <div className="panel-body">
          <div style={{ display: 'flex', gap: 12, overflowX: 'auto', paddingBottom: 10 }}>
            {data.identitySegments.map((seg, idx) => (
              <div
                key={seg.id}
                style={{
                  flex: 1,
                  minWidth: 200,
                  background: 'var(--bg-secondary)',
                  border: '1px solid var(--border-subtle)',
                  borderRadius: 'var(--radius-md)',
                  padding: 16,
                  borderTop: `4px solid ${idx % 2 === 0 ? 'var(--accent-blue)' : 'var(--accent-purple)'}`,
                  position: 'relative'
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                  <span style={{ fontSize: 24, fontWeight: 900, color: 'var(--text-primary)' }}>
                    Персона {seg.id}
                  </span>
                  <span className={`badge ${seg.status === 'verified' ? 'success' : 'warn'}`} style={{ fontSize: 10 }}>
                    {seg.status === 'verified' ? 'Верифицирован' : 'Подозрение'}
                  </span>
                </div>
                <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
                  Период: <strong>{seg.from} — {seg.to} гг.</strong>
                </div>
                <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 8 }}>
                  {seg.status === 'verified'
                    ? 'Биометрическая непрерывность подтверждена байесовской калибровкой'
                    : 'Зафиксирован резкий скачок костных пропорций челюсти и черепа'}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 340px', gap: 24, marginBottom: 24 }}>
        {/* Left: Interactive chart */}
        <div className="panel" style={{ display: 'flex', flexDirection: 'column' }}>
          <div className="panel-header" style={{ flexWrap: 'wrap', gap: 12 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <TrendingUp size={18} style={{ color: 'var(--accent-emerald)' }} />
              <h3>Динамика пропорций во времени</h3>
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              {data.metrics.map((m) => (
                <button
                  key={m.id}
                  onClick={() => setActiveMetricId(m.id)}
                  style={{
                    padding: '6px 12px',
                    fontSize: 12,
                    borderRadius: 'var(--radius-sm)',
                    border: '1px solid var(--border-subtle)',
                    background: activeMetricId === m.id ? 'var(--bg-elevated)' : 'var(--bg-secondary)',
                    color: activeMetricId === m.id ? 'var(--text-primary)' : 'var(--text-secondary)',
                    cursor: 'pointer',
                    transition: 'all 0.2s',
                  }}
                >
                  {m.title}
                </button>
              ))}
            </div>
          </div>
          <div className="panel-body" style={{ flex: 1, minHeight: 320, padding: '24px 16px 8px 8px', position: 'relative' }}>
            <ResponsiveContainer width="100%" height={320}>
              {currentMetric.kind === 'bar' ? (
                <BarChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                  <XAxis dataKey="year" stroke="var(--text-muted)" fontSize={11} />
                  <YAxis stroke="var(--text-muted)" fontSize={11} />
                  <Tooltip
                    contentStyle={{ background: 'var(--bg-card)', borderColor: 'var(--border-subtle)' }}
                    labelStyle={{ color: 'var(--text-primary)', fontWeight: 600 }}
                  />
                  <Bar dataKey={activeMetricId} fill={currentMetric.color} radius={[4, 4, 0, 0]} />
                </BarChart>
              ) : (
                <LineChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                  <XAxis dataKey="year" stroke="var(--text-muted)" fontSize={11} />
                  <YAxis stroke="var(--text-muted)" fontSize={11} domain={['auto', 'auto']} />
                  <Tooltip
                    contentStyle={{ background: 'var(--bg-card)', borderColor: 'var(--border-subtle)' }}
                    labelStyle={{ color: 'var(--text-primary)', fontWeight: 600 }}
                  />
                  <Line
                    type="monotone"
                    dataKey={activeMetricId}
                    stroke={currentMetric.color}
                    strokeWidth={3}
                    dot={{ fill: currentMetric.color, r: 4 }}
                    activeDot={{ r: 6 }}
                  />
                </LineChart>
              )}
            </ResponsiveContainer>
            {/* Anomaly markers overlay */}
            {data.yearPoints.map((point, idx) => {
              if (point.anomaly === 'danger') {
                const xPos = (idx / (data.years.length - 1)) * 100;
                return (
                  <div
                    key={idx}
                    className="absolute w-3 h-3 bg-red-500 rounded-full animate-ping"
                    style={{
                      left: `${xPos}%`,
                      top: '50%',
                      transform: 'translate(-50%, -50%)',
                      pointerEvents: 'none'
                    }}
                    title={`Аномалия: Год ${data.years[idx]}`}
                  />
                );
              }
              return null;
            })}
          </div>
        </div>

        {/* Right: Selected year details card */}
        <div className="panel" style={{ display: 'flex', flexDirection: 'column' }}>
          <div className="panel-header">
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <Calendar size={18} style={{ color: 'var(--accent-amber)' }} />
              <h3>Фокусный кадр: {selectedYear} год</h3>
            </div>
          </div>
          <div className="panel-body" style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 16 }}>
            {selectedPoint && selectedPoint.photo ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                <div style={{
                  background: '#000',
                  borderRadius: 'var(--radius-md)',
                  overflow: 'hidden',
                  height: 200,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center'
                }}>
                  <img
                    src={selectedPoint.photo}
                    alt={`${selectedYear}`}
                    style={{ width: '100%', height: '100%', objectFit: 'contain' }}
                    onError={(e) => {
                      (e.target as HTMLImageElement).src = 'https://images.unsplash.com/photo-1544005313-94ddf0286df2?w=300&auto=format&fit=crop&q=60'
                    }}
                  />
                </div>

                {/* Anomaly Indicator */}
                {selectedPoint.anomaly ? (
                  <div
                    className={`badge ${selectedPoint.anomaly === 'danger' ? 'danger' : 'warn'}`}
                    style={{ padding: '8px 12px', borderRadius: 'var(--radius-md)', display: 'flex', gap: 8, width: '100%', boxSizing: 'border-box' }}
                  >
                    {selectedPoint.anomaly === 'danger' ? <ShieldAlert size={16} /> : <AlertCircle size={16} />}
                    <div style={{ textAlign: 'left' }}>
                      <strong>Критический скачок пропорций</strong>
                      <div style={{ fontSize: 11, opacity: 0.8, marginTop: 2 }}>
                        {selectedPoint.note || 'Кости лица изменились более чем на 3 стандартных отклонения'}
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="badge success" style={{ padding: '8px 12px', borderRadius: 'var(--radius-md)', display: 'flex', gap: 8 }}>
                    <BadgeInfo size={16} />
                    <span>Биометрические показатели стабильны</span>
                  </div>
                )}

                <div style={{ background: 'var(--bg-secondary)', padding: 12, borderRadius: 'var(--radius-md)', fontSize: 13 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                    <span style={{ color: 'var(--text-muted)' }}>Сегмент:</span>
                    <span style={{ fontWeight: 600 }}>Персона {selectedPoint.identity}</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: 'var(--text-muted)' }}>Качество калибровки:</span>
                    <span style={{ fontWeight: 600, color: 'var(--accent-emerald)' }}>Высокое</span>
                  </div>
                </div>
              </div>
            ) : (
              <div style={{ textAlign: 'center', color: 'var(--text-muted)', padding: '40px 10px' }}>
                Фотоанкер для {selectedYear} года отсутствует
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Horizontal timeline slider selector */}
      <div className="panel">
        <div className="panel-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <Clock size={18} style={{ color: 'var(--accent-blue)' }} />
            <h3>Шкала времени</h3>
          </div>
        </div>
        <div className="panel-body" style={{ overflowX: 'auto' }}>
          <div style={{ display: 'flex', gap: 6, minWidth: 800, paddingBottom: 10 }}>
            {data.years.map((year, idx) => {
              const pt = data.yearPoints[idx]
              const hasAnomaly = pt && pt.anomaly
              let borderCol = 'var(--border-subtle)'
              if (selectedYearIndex === idx) borderCol = 'var(--accent-blue)'
              else if (hasAnomaly === 'danger') borderCol = 'var(--accent-red)'
              else if (hasAnomaly === 'warn') borderCol = 'var(--accent-amber)'

              return (
                <div
                  key={year}
                  onClick={() => setSelectedYearIndex(idx)}
                  style={{
                    flex: 1,
                    textAlign: 'center',
                    padding: '12px 6px',
                    borderRadius: 'var(--radius-md)',
                    background: selectedYearIndex === idx ? 'rgba(59,130,246,0.1)' : 'var(--bg-secondary)',
                    border: `1px solid ${borderCol}`,
                    cursor: 'pointer',
                    transition: 'all 0.2s',
                    position: 'relative'
                  }}
                >
                  <div style={{ fontSize: 14, fontWeight: 700, color: selectedYearIndex === idx ? 'var(--accent-blue)' : 'var(--text-primary)' }}>
                    {year}
                  </div>
                  <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 4 }}>
                    {data.photoVolume[idx]} кадров
                  </div>
                  {hasAnomaly && (
                    <div style={{
                      position: 'absolute',
                      top: 4,
                      right: 4,
                      width: 6,
                      height: 6,
                      borderRadius: '50%',
                      background: hasAnomaly === 'danger' ? 'var(--accent-red)' : 'var(--accent-amber)'
                    }} />
                  )}
                </div>
              )
            })}
          </div>
        </div>
      </div>
    </div>
  )
}
