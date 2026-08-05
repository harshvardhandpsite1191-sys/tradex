'use client'
// components/ui/ConfidenceBar.tsx — Horizontal probability/confidence bar

interface ConfidenceBarProps {
  label?: string
  value: number        // 0-1
  color?: string
  showPct?: boolean
  height?: number
}

export default function ConfidenceBar({ label, value, color = 'var(--accent-primary)', showPct = true, height = 6 }: ConfidenceBarProps) {
  const pct = Math.max(0, Math.min(1, value)) * 100
  return (
    <div style={{ width: '100%' }}>
      {(label || showPct) && (
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6, fontSize: 12 }}>
          {label && <span style={{ color: 'var(--text-secondary)' }}>{label}</span>}
          {showPct && <span style={{ color, fontWeight: 600, fontFamily: 'var(--font-mono)' }}>{pct.toFixed(1)}%</span>}
        </div>
      )}
      <div style={{
        width: '100%', height, borderRadius: height,
        background: 'var(--bg-elevated)',
        overflow: 'hidden',
      }}>
        <div style={{
          width: `${pct}%`, height: '100%',
          background: color,
          borderRadius: height,
          transition: 'width 0.6s ease',
          boxShadow: `0 0 8px ${color}66`,
        }} />
      </div>
    </div>
  )
}

// Three-way probability display (Bullish / Neutral / Bearish)
interface TriProbProps {
  bullish: number
  neutral: number
  bearish: number
}

export function TriProbBar({ bullish, neutral, bearish }: TriProbProps) {
  const total = bullish + neutral + bearish || 1
  const bPct = (bullish / total) * 100
  const nPct = (neutral / total) * 100
  const rPct = (bearish / total) * 100

  return (
    <div>
      <div style={{ display: 'flex', gap: 2, height: 10, borderRadius: 6, overflow: 'hidden', marginBottom: 8 }}>
        <div style={{ width: `${bPct}%`, background: 'var(--bullish)', transition: 'width 0.6s ease' }} />
        <div style={{ width: `${nPct}%`, background: 'var(--neutral)', transition: 'width 0.6s ease' }} />
        <div style={{ width: `${rPct}%`, background: 'var(--bearish)', transition: 'width 0.6s ease' }} />
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11 }}>
        <span style={{ color: 'var(--bullish)', fontWeight: 600 }}>Bull {bPct.toFixed(0)}%</span>
        <span style={{ color: 'var(--neutral)'  }}>Neutral {nPct.toFixed(0)}%</span>
        <span style={{ color: 'var(--bearish)', fontWeight: 600 }}>Bear {rPct.toFixed(0)}%</span>
      </div>
    </div>
  )
}
