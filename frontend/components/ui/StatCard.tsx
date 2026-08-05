'use client'
// components/ui/StatCard.tsx — Metric display with delta indicator
interface StatCardProps {
  label: string
  value: string | number
  delta?: number        // positive = good, negative = bad
  deltaLabel?: string
  accent?: 'blue' | 'green' | 'red' | 'amber' | 'purple' | 'teal'
  loading?: boolean
  mono?: boolean
}

const ACCENT_MAP: Record<string, string> = {
  blue:   'var(--accent-primary)',
  green:  'var(--bullish)',
  red:    'var(--bearish)',
  amber:  'var(--neutral)',
  purple: 'var(--accent-secondary)',
  teal:   'var(--accent-teal)',
}

export default function StatCard({ label, value, delta, deltaLabel, accent = 'blue', loading, mono }: StatCardProps) {
  const color = ACCENT_MAP[accent]

  if (loading) {
    return (
      <div className="card" style={{ padding: '18px 20px', minHeight: 88 }}>
        <div className="skeleton" style={{ height: 12, width: '60%', marginBottom: 12, borderRadius: 4 }} />
        <div className="skeleton" style={{ height: 28, width: '80%', borderRadius: 4 }} />
      </div>
    )
  }

  return (
    <div className="card" style={{ padding: '18px 20px', borderLeft: `3px solid ${color}` }}>
      <div style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 8 }}>
        {label}
      </div>
      <div style={{
        fontSize: 24, fontWeight: 700, color: 'var(--text-primary)',
        fontFamily: mono ? 'var(--font-mono)' : 'var(--font-sans)',
        letterSpacing: mono ? '-0.02em' : undefined,
      }}>
        {value}
      </div>
      {delta !== undefined && (
        <div style={{
          marginTop: 6, fontSize: 12,
          color: delta >= 0 ? 'var(--bullish)' : 'var(--bearish)',
          display: 'flex', alignItems: 'center', gap: 4,
        }}>
          <span>{delta >= 0 ? '▲' : '▼'}</span>
          <span>{Math.abs(delta).toFixed(2)}{deltaLabel || ''}</span>
        </div>
      )}
    </div>
  )
}
