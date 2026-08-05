'use client'
import { useState } from 'react'
import StatCard from '@/components/ui/StatCard'
import ConfidenceBar from '@/components/ui/ConfidenceBar'
import { useSimilarity } from '@/lib/hooks'
import { RegimeBadge } from '@/components/ui/SignalBadge'

const SYMBOLS = ['NIFTY', 'BANKNIFTY', 'SENSEX']

export default function HistoricalReplayPage() {
  const [symbol, setSymbol] = useState('NIFTY')
  const { data: similar, isLoading } = useSimilarity(symbol)

  const avgReturn = similar && similar.length > 0
    ? similar.reduce((sum, s) => sum + s.next_day_return, 0) / similar.length
    : null
  const bullishCount = similar?.filter(s => s.next_day_return > 0).length || 0
  const bearishCount = similar?.filter(s => s.next_day_return < 0).length || 0

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Historical Replay</h1>
          <p className="page-subtitle">Find the most structurally similar historical trading days using KNN feature matching</p>
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
        {/* Summary stats */}
        <div className="stats-grid-4">
          <StatCard label="Matches Found" value={similar?.length ?? 0} loading={isLoading} accent="blue" />
          <StatCard label="Avg Next-Day Return" value={avgReturn !== null ? `${(avgReturn * 100).toFixed(2)}%` : '—'} loading={isLoading}
            accent={avgReturn !== null ? (avgReturn >= 0 ? 'green' : 'red') : 'blue'} mono />
          <StatCard label="Bullish Outcomes" value={bullishCount} loading={isLoading} accent="green" />
          <StatCard label="Bearish Outcomes" value={bearishCount} loading={isLoading} accent="red" />
        </div>

        {/* Analog Cards */}
        {isLoading ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {[...Array(5)].map((_, i) => (
              <div key={i} className="card">
                <div className="skeleton" style={{ height: 80, borderRadius: 8 }} />
              </div>
            ))}
          </div>
        ) : similar && similar.length > 0 ? (
          <div>
            <div className="section-title">Top Historical Analogues</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              {similar.map((s, i) => (
                <div key={`${s.similar_date}-${i}`} className="card" style={{
                  borderLeft: `3px solid ${s.next_day_return >= 0 ? 'var(--bullish)' : 'var(--bearish)'}`,
                }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 14 }}>
                    <div>
                      <div style={{ fontWeight: 700, fontSize: 15, fontFamily: 'var(--font-mono)', color: 'var(--text-primary)', marginBottom: 4 }}>
                        {s.similar_date}
                      </div>
                      <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                        <RegimeBadge regime={s.regime} />
                        <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>Rank #{i + 1} closest match</span>
                      </div>
                    </div>
                    <div style={{ textAlign: 'right' }}>
                      <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 4 }}>Next Day Return</div>
                      <div style={{
                        fontSize: 24, fontWeight: 800, fontFamily: 'var(--font-mono)',
                        color: s.next_day_return >= 0 ? 'var(--bullish)' : 'var(--bearish)',
                      }}>
                        {s.next_day_return >= 0 ? '+' : ''}{(s.next_day_return * 100).toFixed(2)}%
                      </div>
                    </div>
                  </div>

                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                    <ConfidenceBar label="Cosine Similarity" value={s.cosine_similarity} color="var(--accent-primary)" />
                    <div>
                      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6, fontSize: 12 }}>
                        <span style={{ color: 'var(--text-secondary)' }}>Euclidean Distance</span>
                        <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 600, color: 'var(--accent-teal)' }}>{s.euclidean_distance.toFixed(4)}</span>
                      </div>
                      <div className="meter-bar">
                        <div className="meter-fill" style={{
                          width: `${Math.min(100, (1 / (1 + s.euclidean_distance)) * 100)}%`,
                          background: 'var(--accent-teal)',
                        }} />
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ) : (
          <div className="card" style={{ textAlign: 'center', padding: '60px 40px' }}>
            <div style={{ fontSize: 40, marginBottom: 16, opacity: 0.3 }}>▷</div>
            <h2 style={{ color: 'var(--text-secondary)', fontWeight: 600, marginBottom: 8 }}>Historical Replay</h2>
            <p style={{ color: 'var(--text-muted)', fontSize: 13, maxWidth: 480, margin: '0 auto', lineHeight: 1.6 }}>
              KNN similarity matching runs nightly after feature engineering completes. Compares today's 290+ feature vector against all historical trading days to find the closest structural matches.
            </p>
          </div>
        )}
      </div>
    </div>
  )
}
