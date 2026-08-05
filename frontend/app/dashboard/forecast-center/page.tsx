'use client'
import { useState } from 'react'
import StatCard from '@/components/ui/StatCard'
import { SignalBadge, RegimeBadge } from '@/components/ui/SignalBadge'
import ConfidenceBar, { TriProbBar } from '@/components/ui/ConfidenceBar'
import { usePrediction, useSignal, useScenarios, useRegimes } from '@/lib/hooks'

const SYMBOLS = ['NIFTY', 'BANKNIFTY', 'SENSEX']

export default function ForecastCenterPage() {
  const [symbol, setSymbol] = useState('NIFTY')
  const { data: pred, isLoading: pLoad } = usePrediction(symbol)
  const { data: signal, isLoading: sLoad } = useSignal(symbol)
  const { data: scenarios, isLoading: scLoad } = useScenarios()
  const { data: regimes } = useRegimes(symbol)

  const topScenarios = scenarios?.slice(0, 8) || []
  const currentRegime = regimes?.[0]?.regime

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Forecast Center</h1>
          <p className="page-subtitle">AI directional forecast, scenario matching & top institutional setups</p>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
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
        <div className="stats-grid-4">
          <StatCard label="Predicted Direction" value={pred?.predicted_direction ?? '—'} loading={pLoad} accent={pred?.predicted_direction === 'Bullish' ? 'green' : pred?.predicted_direction === 'Bearish' ? 'red' : 'amber'} />
          <StatCard label="Bull Probability" value={pred ? `${(pred.bullish_prob * 100).toFixed(1)}%` : '—'} loading={pLoad} accent="green" mono />
          <StatCard label="Bear Probability" value={pred ? `${(pred.bearish_prob * 100).toFixed(1)}%` : '—'} loading={pLoad} accent="red" mono />
          <StatCard label="AI Confidence" value={signal ? `${(signal.confidence * 100).toFixed(0)}%` : '—'} loading={sLoad} accent="purple" mono />
        </div>

        <div className="content-grid-2">
          <div className="card">
            <div className="card-title">Next-Day Direction Forecast</div>
            {pLoad ? (
              <div className="skeleton" style={{ height: 140, borderRadius: 8 }} />
            ) : pred ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
                <div style={{ textAlign: 'center', padding: '20px', borderRadius: 12, background: 'var(--bg-elevated)' }}>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 8, textTransform: 'uppercase', letterSpacing: '0.08em' }}>AI Forecast</div>
                  <div style={{ fontSize: 32, fontWeight: 800, color: pred.predicted_direction === 'Bullish' ? 'var(--bullish)' : pred.predicted_direction === 'Bearish' ? 'var(--bearish)' : 'var(--neutral)' }}>
                    {pred.predicted_direction === 'Bullish' ? '▲' : pred.predicted_direction === 'Bearish' ? '▼' : '—'} {pred.predicted_direction}
                  </div>
                </div>
                <TriProbBar bullish={pred.bullish_prob} neutral={pred.neutral_prob} bearish={pred.bearish_prob} />
              </div>
            ) : (
              <div style={{ color: 'var(--text-muted)', fontSize: 13, textAlign: 'center', padding: '40px 0' }}>No prediction available</div>
            )}
          </div>

          <div className="card">
            <div className="card-title">Today's Signal Summary</div>
            {sLoad ? (
              <div className="skeleton" style={{ height: 140, borderRadius: 8 }} />
            ) : signal ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>Signal</span>
                  <SignalBadge signal={signal.signal as any} />
                </div>
                <ConfidenceBar label="Signal Confidence" value={signal.confidence} color="var(--accent-primary)" />
                <ConfidenceBar label="AI Probability" value={signal.ai_probability} color="var(--accent-secondary)" />
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12 }}>
                  <span style={{ color: 'var(--text-muted)' }}>Date</span>
                  <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>{signal.date}</span>
                </div>
              </div>
            ) : (
              <div style={{ color: 'var(--text-muted)', fontSize: 13, textAlign: 'center', padding: '40px 0' }}>No signal data</div>
            )}
          </div>
        </div>

        {/* Scenario Library */}
        <div>
          <div className="section-title">Top Market Scenarios — {currentRegime || 'All Regimes'}</div>
          {scLoad ? (
            <div className="skeleton" style={{ height: 200, borderRadius: 12 }} />
          ) : topScenarios.length > 0 ? (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 12 }}>
              {topScenarios.map(sc => (
                <div key={sc.id} className="card" style={{ padding: '16px 18px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 10 }}>
                    <div style={{ fontWeight: 700, fontSize: 13, color: 'var(--text-primary)', flex: 1 }}>{sc.name}</div>
                    <RegimeBadge regime={sc.regime} />
                  </div>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 12, lineHeight: 1.5 }}>{sc.description}</div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12 }}>
                    <div>
                      <span style={{ color: 'var(--text-muted)' }}>Win Rate </span>
                      <span style={{ fontWeight: 700, fontFamily: 'var(--font-mono)', color: sc.win_rate >= 0.6 ? 'var(--bullish)' : sc.win_rate >= 0.5 ? 'var(--neutral)' : 'var(--bearish)' }}>
                        {(sc.win_rate * 100).toFixed(0)}%
                      </span>
                    </div>
                    <div>
                      <span style={{ color: 'var(--text-muted)' }}>Avg Ret </span>
                      <span style={{ fontWeight: 700, fontFamily: 'var(--font-mono)', color: sc.avg_return_pct >= 0 ? 'var(--bullish)' : 'var(--bearish)' }}>
                        {sc.avg_return_pct >= 0 ? '+' : ''}{sc.avg_return_pct.toFixed(2)}%
                      </span>
                    </div>
                    <div style={{ color: 'var(--text-muted)' }}>n={sc.sample_size}</div>
                  </div>
                  <div style={{ marginTop: 10 }}>
                    <ConfidenceBar value={sc.win_rate} color={sc.win_rate >= 0.6 ? 'var(--bullish)' : 'var(--neutral)'} showPct={false} height={4} />
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="card" style={{ textAlign: 'center', padding: '40px' }}>
              <p style={{ color: 'var(--text-muted)', fontSize: 13 }}>Scenario library seeds on first run. Check back after nightly pipeline.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
