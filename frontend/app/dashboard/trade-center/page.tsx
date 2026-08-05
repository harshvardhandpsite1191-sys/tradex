'use client'
import { useState } from 'react'
import StatCard from '@/components/ui/StatCard'
import { SignalBadge, OutcomeBadge } from '@/components/ui/SignalBadge'
import ConfidenceBar from '@/components/ui/ConfidenceBar'
import { useSignal, useRecommendations, usePrediction } from '@/lib/hooks'

const SYMBOLS = ['NIFTY', 'BANKNIFTY', 'SENSEX']

export default function TradeCenterPage() {
  const [symbol, setSymbol] = useState('NIFTY')
  const { data: signal, isLoading: sLoad } = useSignal(symbol)
  const { data: recos, isLoading: rLoad } = useRecommendations(symbol)
  const { data: pred, isLoading: pLoad } = usePrediction(symbol)

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Trade Center</h1>
          <p className="page-subtitle">AI consensus signal, directional options strategies, and executable trade recommendations</p>
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
        {/* Signal Overview */}
        <div>
          <div className="section-title">Today's Consensus Signal</div>
          <div className="stats-grid-4">
            <div className="card" style={{ gridColumn: 'span 2', display: 'flex', alignItems: 'center', gap: 16, padding: '20px 24px' }}>
              {sLoad ? (
                <div className="skeleton" style={{ height: 40, width: '100%', borderRadius: 8 }} />
              ) : signal ? (
                <>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 10 }}>Active Signal</div>
                    <SignalBadge signal={signal.signal as any} />
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 4 }}>Confidence</div>
                    <div style={{ fontSize: 28, fontWeight: 800, fontFamily: 'var(--font-mono)', color: signal.confidence > 0.7 ? 'var(--bullish)' : signal.confidence > 0.5 ? 'var(--neutral)' : 'var(--text-secondary)' }}>
                      {(signal.confidence * 100).toFixed(0)}%
                    </div>
                  </div>
                </>
              ) : <div style={{ color: 'var(--text-muted)', fontSize: 13 }}>No signal for today</div>}
            </div>
            <StatCard label="Regime Score" value={signal ? `${(signal.regime_score * 100).toFixed(0)}%` : '—'} loading={sLoad} accent="blue" mono />
            <StatCard label="Behaviour Score" value={signal ? `${(signal.behaviour_score * 100).toFixed(0)}%` : '—'} loading={sLoad} accent="purple" mono />
          </div>
        </div>

        {/* AI Prediction */}
        {!pLoad && pred && (
          <div className="content-grid-2">
            <div className="card">
              <div className="card-title">AI Model Prediction</div>
              <div style={{ marginBottom: 16 }}>
                <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 8, textTransform: 'uppercase', letterSpacing: '0.07em' }}>Directional Probability</div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                  <ConfidenceBar label="Bullish" value={pred.bullish_prob} color="var(--bullish)" />
                  <ConfidenceBar label="Neutral" value={pred.neutral_prob} color="var(--neutral)" />
                  <ConfidenceBar label="Bearish" value={pred.bearish_prob} color="var(--bearish)" />
                </div>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, color: 'var(--text-muted)', marginTop: 8 }}>
                <span>Model: {pred.model_version}</span>
                <span>{pred.feature_count} features</span>
              </div>
            </div>

            {/* Signal sub-scores */}
            {signal && (
              <div className="card">
                <div className="card-title">Signal Components</div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                  <ConfidenceBar label="Overall Confidence" value={signal.confidence} color="var(--accent-primary)" />
                  <ConfidenceBar label="Regime Alignment" value={signal.regime_score} color="var(--accent-secondary)" />
                  <ConfidenceBar label="Behaviour Score" value={signal.behaviour_score} color="var(--accent-teal)" />
                  <ConfidenceBar label="AI Model Probability" value={signal.ai_probability} color="var(--bullish)" />
                </div>
              </div>
            )}
          </div>
        )}

        {/* Trade Recommendations */}
        <div>
          <div className="section-title">Executable Trade Recommendations</div>
          {rLoad ? (
            <div className="card" style={{ padding: 0 }}>
              {[...Array(3)].map((_, i) => (
                <div key={i} style={{ padding: '16px 20px', borderBottom: '1px solid var(--border-subtle)' }}>
                  <div className="skeleton" style={{ height: 14, width: '70%', marginBottom: 10, borderRadius: 4 }} />
                  <div className="skeleton" style={{ height: 12, width: '50%', borderRadius: 4 }} />
                </div>
              ))}
            </div>
          ) : recos && recos.length > 0 ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              {recos.map(reco => (
                <div key={reco.id} className="card" style={{
                  borderLeft: `3px solid ${reco.status === 'active' ? 'var(--bullish)' : reco.status === 'closed' ? 'var(--bearish)' : 'var(--accent-primary)'}`,
                }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 }}>
                    <div>
                      <div style={{ fontWeight: 700, fontSize: 14, color: 'var(--text-primary)', marginBottom: 4 }}>{reco.strategy}</div>
                      <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>Expiry: {reco.expiry_date} · {reco.symbol}</div>
                    </div>
                    <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                      {reco.outcome && <OutcomeBadge outcome={reco.outcome} />}
                      <span style={{
                        padding: '3px 10px', borderRadius: 8, fontSize: 11, fontWeight: 600,
                        background: reco.status === 'active' ? 'rgba(34,197,94,0.12)' : 'var(--bg-elevated)',
                        color: reco.status === 'active' ? 'var(--bullish)' : 'var(--text-muted)',
                      }}>{reco.status.toUpperCase()}</span>
                    </div>
                  </div>

                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 12 }}>
                    {[
                      { label: 'Leg 1 Strike', val: `${reco.leg1_strike} ${reco.leg1_type} ${reco.leg1_action}` },
                      reco.leg2_strike ? { label: 'Leg 2 Strike', val: `${reco.leg2_strike} ${reco.leg2_type} ${reco.leg2_action}` } : null,
                      { label: 'Est. Premium', val: `₹${reco.estimated_premium}` },
                      { label: 'Stop Loss', val: `₹${reco.stop_loss}` },
                      { label: 'Target', val: `₹${reco.target}` },
                    ].filter(Boolean).map(item => (
                      <div key={item!.label}>
                        <div style={{ fontSize: 10, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 4 }}>{item!.label}</div>
                        <div style={{ fontSize: 13, fontWeight: 700, fontFamily: 'var(--font-mono)', color: 'var(--text-primary)' }}>{item!.val}</div>
                      </div>
                    ))}
                  </div>

                  {reco.pnl !== null && (
                    <div style={{ marginTop: 12, paddingTop: 12, borderTop: '1px solid var(--border-subtle)', display: 'flex', gap: 20 }}>
                      <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>Final P&L: <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, color: reco.pnl >= 0 ? 'var(--bullish)' : 'var(--bearish)' }}>{reco.pnl >= 0 ? '+' : ''}₹{reco.pnl}</span></div>
                      <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>Max Loss: <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>₹{reco.max_loss}</span></div>
                      <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>Max Profit: <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>₹{reco.max_profit}</span></div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <div className="card" style={{ textAlign: 'center', padding: '40px' }}>
              <div style={{ fontSize: 32, marginBottom: 12, opacity: 0.3 }}>⟳</div>
              <p style={{ color: 'var(--text-muted)', fontSize: 13 }}>No recommendations generated yet. Runs nightly at 9:30 PM IST.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
