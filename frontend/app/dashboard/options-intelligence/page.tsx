'use client'
import { useState } from 'react'
import StatCard from '@/components/ui/StatCard'
import ConfidenceBar from '@/components/ui/ConfidenceBar'
import { useExpiry, useSimilarity, usePrediction } from '@/lib/hooks'
import { TriProbBar } from '@/components/ui/ConfidenceBar'

const SYMBOLS = ['NIFTY', 'BANKNIFTY', 'SENSEX']

export default function OptionsIntelligencePage() {
  const [symbol, setSymbol] = useState('NIFTY')
  const { data: expiry, isLoading: eLoad } = useExpiry(symbol)
  const { data: similar, isLoading: sLoad } = useSimilarity(symbol)
  const { data: pred, isLoading: pLoad } = usePrediction(symbol)

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Options Intelligence</h1>
          <p className="page-subtitle">Max Pain, GEX, PCR, Greeks, pin analysis and historical analogs</p>
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
        {/* Key Options Stats */}
        <div>
          <div className="section-title">Options Market Metrics</div>
          <div className="stats-grid-4">
            <StatCard label="Max Pain Strike" value={expiry?.max_pain_strike ?? '—'} loading={eLoad} accent="blue" mono />
            <StatCard label="PCR" value={expiry ? expiry.pcr.toFixed(2) : '—'} loading={eLoad}
              accent={expiry ? (expiry.pcr < 0.8 ? 'red' : expiry.pcr > 1.2 ? 'green' : 'amber') : 'amber'} mono />
            <StatCard label="Net GEX" value={expiry ? `${(expiry.net_gex / 1e6).toFixed(2)}M` : '—'} loading={eLoad}
              accent={expiry ? (expiry.net_gex >= 0 ? 'green' : 'red') : 'blue'} mono />
            <StatCard label="Days to Expiry" value={expiry ? `${expiry.days_to_expiry}d` : '—'} loading={eLoad}
              accent={expiry ? (expiry.days_to_expiry <= 2 ? 'red' : 'teal') : 'teal'} mono />
          </div>
        </div>

        <div className="content-grid-2">
          {/* Pin Analysis */}
          <div className="card">
            <div className="card-title">Expiry Pin Analysis</div>
            {eLoad ? (
              <div className="skeleton" style={{ height: 140, borderRadius: 8 }} />
            ) : expiry ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
                <div style={{ textAlign: 'center', padding: '16px 0', borderRadius: 12, background: 'var(--bg-elevated)' }}>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.07em' }}>Max Pain Level</div>
                  <div style={{ fontSize: 36, fontWeight: 800, fontFamily: 'var(--font-mono)', color: 'var(--accent-primary)' }}>{expiry.max_pain_strike}</div>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 4 }}>Expiry: {expiry.expiry_date}</div>
                </div>
                <ConfidenceBar label="Pin Probability" value={expiry.pin_probability} color="var(--accent-secondary)" height={8} />
                <div style={{ display: 'flex', gap: 12 }}>
                  <div style={{ flex: 1, padding: '12px', borderRadius: 8, background: 'var(--bg-elevated)', textAlign: 'center' }}>
                    <div style={{ fontSize: 10, color: 'var(--text-muted)', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.07em' }}>GEX Regime</div>
                    <div style={{ fontSize: 14, fontWeight: 700, color: expiry.net_gex >= 0 ? 'var(--bullish)' : 'var(--bearish)' }}>
                      {expiry.net_gex >= 0 ? 'Long Gamma' : 'Short Gamma'}
                    </div>
                  </div>
                  <div style={{ flex: 1, padding: '12px', borderRadius: 8, background: 'var(--bg-elevated)', textAlign: 'center' }}>
                    <div style={{ fontSize: 10, color: 'var(--text-muted)', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.07em' }}>PCR Signal</div>
                    <div style={{ fontSize: 14, fontWeight: 700, color: expiry.pcr > 1.2 ? 'var(--bullish)' : expiry.pcr < 0.8 ? 'var(--bearish)' : 'var(--neutral)' }}>
                      {expiry.pcr > 1.2 ? 'Contrarian Bull' : expiry.pcr < 0.8 ? 'Contrarian Bear' : 'Neutral'}
                    </div>
                  </div>
                </div>
              </div>
            ) : (
              <div style={{ color: 'var(--text-muted)', fontSize: 13, textAlign: 'center', padding: '40px 0' }}>No expiry data available</div>
            )}
          </div>

          {/* AI Prediction Probabilities */}
          <div className="card">
            <div className="card-title">Next-Day Direction Probability</div>
            {pLoad ? (
              <div className="skeleton" style={{ height: 140, borderRadius: 8 }} />
            ) : pred ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
                <TriProbBar bullish={pred.bullish_prob} neutral={pred.neutral_prob} bearish={pred.bearish_prob} />
                <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                  <ConfidenceBar label="Bullish Probability" value={pred.bullish_prob} color="var(--bullish)" />
                  <ConfidenceBar label="Neutral Probability" value={pred.neutral_prob} color="var(--neutral)" />
                  <ConfidenceBar label="Bearish Probability" value={pred.bearish_prob} color="var(--bearish)" />
                </div>
                <div style={{ fontSize: 11, color: 'var(--text-muted)', textAlign: 'right' }}>
                  LightGBM v{pred.model_version} · {pred.feature_count} features
                </div>
              </div>
            ) : (
              <div style={{ color: 'var(--text-muted)', fontSize: 13, textAlign: 'center', padding: '40px 0' }}>No prediction available</div>
            )}
          </div>
        </div>

        {/* Historical Similarity */}
        <div className="card">
          <div className="card-title">Historical Day Analogs (KNN Similarity)</div>
          {sLoad ? (
            <div className="skeleton" style={{ height: 120, borderRadius: 8 }} />
          ) : similar && similar.length > 0 ? (
            <div>
              <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 16 }}>
                Days most structurally similar to today based on Euclidean + Cosine distance on 290+ features
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
                {similar.map((s, i) => (
                  <div key={`${s.similar_date}-${i}`} style={{
                    display: 'grid', gridTemplateColumns: '120px 1fr 1fr 1fr 1fr',
                    alignItems: 'center', gap: 12,
                    padding: '12px 0',
                    borderBottom: i < similar.length - 1 ? '1px solid var(--border-subtle)' : 'none',
                    fontSize: 13,
                  }}>
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-muted)' }}>{s.similar_date}</span>
                    <div>
                      <div style={{ fontSize: 10, color: 'var(--text-muted)', marginBottom: 2, textTransform: 'uppercase', letterSpacing: '0.06em' }}>Cosine Sim</div>
                      <div style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, color: 'var(--accent-primary)', fontSize: 12 }}>{(s.cosine_similarity * 100).toFixed(1)}%</div>
                    </div>
                    <div>
                      <div style={{ fontSize: 10, color: 'var(--text-muted)', marginBottom: 2, textTransform: 'uppercase', letterSpacing: '0.06em' }}>Distance</div>
                      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-secondary)' }}>{s.euclidean_distance.toFixed(3)}</div>
                    </div>
                    <div>
                      <div style={{ fontSize: 10, color: 'var(--text-muted)', marginBottom: 2, textTransform: 'uppercase', letterSpacing: '0.06em' }}>Regime</div>
                      <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{s.regime}</div>
                    </div>
                    <div style={{ textAlign: 'right' }}>
                      <div style={{ fontSize: 10, color: 'var(--text-muted)', marginBottom: 2, textTransform: 'uppercase', letterSpacing: '0.06em' }}>Next Day Ret</div>
                      <div style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: 12, color: s.next_day_return >= 0 ? 'var(--bullish)' : 'var(--bearish)' }}>
                        {s.next_day_return >= 0 ? '+' : ''}{(s.next_day_return * 100).toFixed(2)}%
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div style={{ color: 'var(--text-muted)', fontSize: 13, textAlign: 'center', padding: '40px 0' }}>
              Historical similarity runs nightly after feature engineering.
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
