'use client'
// components/ui/SignalBadge.tsx — Directional signal pill with glow

type Signal = 'BUY_CALL' | 'BUY_PUT' | 'SHORT_STRADDLE' | 'IRON_CONDOR' | 'NEUTRAL'
type Direction = 'Bullish' | 'Bearish' | 'Neutral'
type Regime = 'Trending' | 'Ranging' | 'Volatile' | 'Breakout' | 'Reversal'

const SIGNAL_CONFIG: Record<Signal, { label: string; color: string; bg: string }> = {
  BUY_CALL:      { label: 'BUY CALL ▲',   color: '#22c55e', bg: 'rgba(34,197,94,0.12)' },
  BUY_PUT:       { label: 'BUY PUT ▼',    color: '#ef4444', bg: 'rgba(239,68,68,0.12)' },
  SHORT_STRADDLE:{ label: 'SHORT STRADDLE ⊘', color: '#f59e0b', bg: 'rgba(245,158,11,0.12)' },
  IRON_CONDOR:   { label: 'IRON CONDOR ⊡', color: '#8b5cf6', bg: 'rgba(139,92,246,0.12)' },
  NEUTRAL:       { label: 'NEUTRAL —',     color: '#64748b', bg: 'rgba(100,116,139,0.12)' },
}

const DIR_CONFIG: Record<Direction, { color: string }> = {
  Bullish: { color: '#22c55e' },
  Bearish: { color: '#ef4444' },
  Neutral: { color: '#64748b' },
}

const REGIME_CONFIG: Record<Regime, { color: string; bg: string }> = {
  Trending:  { color: '#3b82f6', bg: 'rgba(59,130,246,0.12)' },
  Ranging:   { color: '#f59e0b', bg: 'rgba(245,158,11,0.12)' },
  Volatile:  { color: '#ef4444', bg: 'rgba(239,68,68,0.12)' },
  Breakout:  { color: '#22c55e', bg: 'rgba(34,197,94,0.12)' },
  Reversal:  { color: '#8b5cf6', bg: 'rgba(139,92,246,0.12)' },
}

export function SignalBadge({ signal }: { signal: Signal }) {
  const cfg = SIGNAL_CONFIG[signal] || SIGNAL_CONFIG.NEUTRAL
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 6,
      padding: '5px 12px', borderRadius: 20,
      background: cfg.bg, color: cfg.color,
      fontWeight: 700, fontSize: 12, letterSpacing: '0.05em',
      border: `1px solid ${cfg.color}33`,
    }}>
      {cfg.label}
    </span>
  )
}

export function DirectionBadge({ direction }: { direction: Direction }) {
  const cfg = DIR_CONFIG[direction]
  const icon = direction === 'Bullish' ? '▲' : direction === 'Bearish' ? '▼' : '—'
  return (
    <span style={{ color: cfg.color, fontWeight: 700, fontSize: 13 }}>
      {icon} {direction}
    </span>
  )
}

export function RegimeBadge({ regime }: { regime: Regime | string }) {
  const cfg = REGIME_CONFIG[regime as Regime] || { color: '#64748b', bg: 'rgba(100,116,139,0.12)' }
  return (
    <span style={{
      display: 'inline-block',
      padding: '3px 10px', borderRadius: 12,
      background: cfg.bg, color: cfg.color,
      fontWeight: 600, fontSize: 11, letterSpacing: '0.06em',
      border: `1px solid ${cfg.color}33`,
    }}>
      {regime}
    </span>
  )
}

export function OutcomeBadge({ outcome }: { outcome: 'Win' | 'Loss' | 'Scratch' | null }) {
  const config = {
    Win:     { color: '#22c55e', bg: 'rgba(34,197,94,0.12)',     label: '✓ Win' },
    Loss:    { color: '#ef4444', bg: 'rgba(239,68,68,0.12)',     label: '✕ Loss' },
    Scratch: { color: '#64748b', bg: 'rgba(100,116,139,0.12)',   label: '— Scratch' },
  }
  const cfg = outcome ? config[outcome] : config.Scratch
  return (
    <span style={{
      display: 'inline-block', padding: '2px 8px', borderRadius: 8,
      background: cfg.bg, color: cfg.color,
      fontWeight: 600, fontSize: 11,
    }}>
      {cfg.label}
    </span>
  )
}
