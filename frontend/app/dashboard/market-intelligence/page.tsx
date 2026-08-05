'use client'
import type { Metadata } from 'next'
import StatCard from '@/components/ui/StatCard'
import { RegimeBadge, DirectionBadge } from '@/components/ui/SignalBadge'
import ConfidenceBar from '@/components/ui/ConfidenceBar'
import { useRegimes, useBehaviours, useOpening, useExpiry } from '@/lib/hooks'
import { useState } from 'react'

const SYMBOLS = ['NIFTY', 'BANKNIFTY', 'SENSEX']

function BehaviourTag({ active, label }: { active: boolean; label: string }) {
  return (
    <div style={{
      padding: '6px 12px', borderRadius: 8, fontSize: 12, fontWeight: 600,
      background: active ? 'rgba(59,130,246,0.15)' : 'var(--bg-elevated)',
      color: active ? 'var(--accent-primary)' : 'var(--text-muted)',
      border: `1px solid ${active ? 'rgba(59,130,246,0.3)' : 'var(--border-subtle)'}`,
      transition: 'all 0.2s ease',
    }}>
      {active ? '◉' : '○'} {label}
    </div>
  )
}

export default function MarketIntelligencePage() {
  const [symbol, setSymbol] = useState('NIFTY')
  const { data: regimes, isLoading: rLoading } = useRegimes(symbol)
  const { data: behaviours, isLoading: bLoading } = useBehaviours(symbol)
  const { data: opening, isLoading: oLoading } = useOpening(symbol)
  const { data: expiry, isLoading: eLoading } = useExpiry(symbol)

  const latest = regimes?.[0]
  const beh = behaviours?.[0]

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Market Intelligence</h1>
          <p className="page-subtitle">Regime classification, opening bias, expiry analytics & institutional behaviour</p>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          {SYMBOLS.map(s => (
            <button key={s} onClick={() => setSymbol(s)} style={{
              padding: '6px 14px', borderRadius: 8, fontSize: 12, fontWeight: 600,
              background: symbol === s ? 'var(--accent-primary)' : 'var(--bg-elevated)',
              color: symbol === s ? '#fff' : 'var(--text-secondary)',
              border: `1px solid ${symbol === s ? 'var(--accent-primary)' : 'var(--border-default)'}`,
              cursor: 'pointer', transition: 'all 0.2s',
            }}>{s}</button>
          ))}
        </div>
      </div>

      <div className="page-body">
        {/* Regime Row */}
        <div>
          <div className="section-title">Market Regime — {symbol}</div>
          <div className="stats-grid-4">
            <StatCard label="Current Regime" value={latest?.regime ?? '—'} loading={rLoading} accent="blue" />
            <StatCard label="Regime Score" value={latest ? `${(latest.regime_score * 100).toFixed(1)}%` : '—'} loading={rLoading} accent="purple" mono />
            <StatCard label="ADX" value={latest ? latest.adx.toFixed(1) : '—'} loading={rLoading} accent={latest && latest.adx > 25 ? 'green' : 'amber'} mono />
            <StatCard label="ATR %" value={latest ? `${latest.atr_pct.toFixed(2)}%` : '—'} loading={rLoading} accent="teal" mono />
          </div>
        </div>

        {/* Opening Intelligence */}
        <div className="content-grid-2">
          <div className="card">
            <div className="card-title">Opening Intelligence</div>
            {oLoading ? (
              <div className="skeleton" style={{ height: 120, borderRadius: 8 }} />
            ) : opening ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ color: 'var(--text-secondary)', fontSize: 13 }}>Opening Bias</span>
                  <DirectionBadge direction={opening.opening_bias as any} />
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: 'var(--text-secondary)', fontSize: 13 }}>Expected Gap</span>
                  <span style={{ fontFamily: 'var(--font-mono)', color: Math.abs(opening.expected_gap_pct) > 0.5 ? 'var(--bearish)' : 'var(--text-primary)', fontWeight: 700 }}>
                    {opening.expected_gap_pct > 0 ? '+' : ''}{opening.expected_gap_pct.toFixed(2)}%
                  </span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: 'var(--text-secondary)', fontSize: 13 }}>GIFT Nifty</span>
                  <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-primary)', fontWeight: 600 }}>
                    {opening.gift_nifty?.toFixed(2) ?? '—'}
                  </span>
                </div>
                <hr className="divider" />
                <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>Predicted Initial Balance</div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: 'var(--bullish)', fontFamily: 'var(--font-mono)', fontWeight: 700 }}>IB High: {opening.predicted_ib_high?.toFixed(0)}</span>
                  <span style={{ color: 'var(--bearish)', fontFamily: 'var(--font-mono)', fontWeight: 700 }}>IB Low: {opening.predicted_ib_low?.toFixed(0)}</span>
                </div>
                <ConfidenceBar label="Global Sentiment" value={opening.global_sentiment_score} color="var(--accent-primary)" />
              </div>
            ) : (
              <div style={{ color: 'var(--text-muted)', fontSize: 13, textAlign: 'center', padding: '40px 0' }}>No opening data for today</div>
            )}
          </div>

          {/* Expiry Intelligence */}
          <div className="card">
            <div className="card-title">Expiry Intelligence</div>
            {eLoading ? (
              <div className="skeleton" style={{ height: 120, borderRadius: 8 }} />
            ) : expiry ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: 'var(--text-secondary)', fontSize: 13 }}>Max Pain Strike</span>
                  <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--accent-primary)', fontWeight: 700, fontSize: 18 }}>{expiry.max_pain_strike}</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: 'var(--text-secondary)', fontSize: 13 }}>PCR (Put/Call Ratio)</span>
                  <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, color: expiry.pcr < 0.8 ? 'var(--bearish)' : expiry.pcr > 1.2 ? 'var(--bullish)' : 'var(--neutral)' }}>
                    {expiry.pcr?.toFixed(2)}
                  </span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: 'var(--text-secondary)', fontSize: 13 }}>Net GEX</span>
                  <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 600, color: expiry.net_gex >= 0 ? 'var(--bullish)' : 'var(--bearish)' }}>
                    {expiry.net_gex >= 0 ? '+' : ''}{(expiry.net_gex / 1e6).toFixed(2)}M
                  </span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: 'var(--text-secondary)', fontSize: 13 }}>Days to Expiry</span>
                  <span style={{ fontFamily: 'var(--font-mono)', color: expiry.days_to_expiry <= 2 ? 'var(--bearish)' : 'var(--text-primary)', fontWeight: 700 }}>
                    {expiry.days_to_expiry}d
                  </span>
                </div>
                <hr className="divider" />
                <ConfidenceBar label="Pin Probability" value={expiry.pin_probability} color="var(--accent-secondary)" />
              </div>
            ) : (
              <div style={{ color: 'var(--text-muted)', fontSize: 13, textAlign: 'center', padding: '40px 0' }}>No expiry data available</div>
            )}
          </div>
        </div>

        {/* Behaviour Detection */}
        <div className="card">
          <div className="card-title">Institutional Behaviour Detection</div>
          {bLoading ? (
            <div className="skeleton" style={{ height: 80, borderRadius: 8 }} />
          ) : beh ? (
            <div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 16 }}>
                <BehaviourTag active={beh.choch_detected}     label="CHoCH" />
                <BehaviourTag active={beh.bos_detected}       label="BOS" />
                <BehaviourTag active={beh.stop_hunt_up}       label="Stop Hunt ↑" />
                <BehaviourTag active={beh.stop_hunt_down}     label="Stop Hunt ↓" />
                <BehaviourTag active={beh.equal_highs}        label="Equal Highs" />
                <BehaviourTag active={beh.equal_lows}         label="Equal Lows" />
                <BehaviourTag active={beh.iv_spike}           label="IV Spike" />
                <BehaviourTag active={beh.oi_buildup}         label="OI Buildup" />
              </div>
              <ConfidenceBar
                label="Institutional Activity Score"
                value={beh.institutional_activity_score}
                color="var(--accent-secondary)"
              />
            </div>
          ) : (
            <div style={{ color: 'var(--text-muted)', fontSize: 13 }}>No behaviour data available</div>
          )}
        </div>

        {/* Recent Regimes History */}
        {regimes && regimes.length > 1 && (
          <div className="card">
            <div className="card-title">Recent Regime History</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
              {regimes.map((r, i) => (
                <div key={r.date} style={{
                  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                  padding: '10px 0',
                  borderBottom: i < regimes.length - 1 ? '1px solid var(--border-subtle)' : 'none',
                }}>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-muted)' }}>{r.date}</span>
                  <RegimeBadge regime={r.regime} />
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-secondary)' }}>ADX {r.adx.toFixed(1)}</span>
                  <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>{r.method}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
