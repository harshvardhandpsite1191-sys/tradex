'use client'
import { useState } from 'react'
import StatCard from '@/components/ui/StatCard'
import ConfidenceBar from '@/components/ui/ConfidenceBar'
import { useBehaviours, useLiveStatus } from '@/lib/hooks'

const SYMBOLS = ['NIFTY', 'BANKNIFTY', 'SENSEX']

export default function LiquidityIntelligencePage() {
  const [symbol, setSymbol] = useState('NIFTY')
  const { data: behaviours, isLoading: bLoad } = useBehaviours(symbol)
  const { data: live, isLoading: lLoad } = useLiveStatus(symbol)

  const beh = behaviours?.[0]

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Liquidity Intelligence</h1>
          <p className="page-subtitle">Institutional order flow, stop sweeps, OI buildup, and live VWAP tracking</p>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          {live && <div className="live-indicator">LIVE</div>}
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
        {/* Live Price VWAP */}
        {live && (
          <div>
            <div className="section-title">Live Market Feed</div>
            <div className="stats-grid-4">
              <StatCard label="Last Price" value={live.last_price.toFixed(2)} loading={lLoad} accent="teal" mono />
              <StatCard label="VWAP" value={live.vwap.toFixed(2)} loading={lLoad} accent="blue" mono />
              <StatCard label="VWAP Deviation" value={`${live.vwap_deviation_pct.toFixed(2)}%`} loading={lLoad}
                accent={Math.abs(live.vwap_deviation_pct) > 0.5 ? 'red' : 'green'} mono
                delta={live.vwap_deviation_pct} deltaLabel="%" />
              <div className="card" style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <div style={{
                  width: 40, height: 40, borderRadius: '50%',
                  background: live.volume_spike ? 'rgba(239,68,68,0.15)' : 'var(--bg-elevated)',
                  border: `2px solid ${live.volume_spike ? 'var(--bearish)' : 'var(--border-default)'}`,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: 18, flexShrink: 0,
                }}>
                  {live.volume_spike ? '⚡' : '≈'}
                </div>
                <div>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 2 }}>Volume</div>
                  <div style={{ fontWeight: 700, color: live.volume_spike ? 'var(--bearish)' : 'var(--text-primary)', fontFamily: 'var(--font-mono)', fontSize: 14 }}>
                    {live.volume_spike ? 'SPIKE' : 'Normal'}
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Institutional Behaviour */}
        <div className="content-grid-2">
          <div className="card">
            <div className="card-title">Stop Hunt Detection</div>
            {bLoad ? (
              <div className="skeleton" style={{ height: 140, borderRadius: 8 }} />
            ) : beh ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                  {[
                    { label: 'Stop Hunt ↑', active: beh.stop_hunt_up, desc: 'Upside liquidity sweep' },
                    { label: 'Stop Hunt ↓', active: beh.stop_hunt_down, desc: 'Downside liquidity sweep' },
                    { label: 'Equal Highs', active: beh.equal_highs, desc: 'Liquidity at equal highs' },
                    { label: 'Equal Lows', active: beh.equal_lows, desc: 'Liquidity at equal lows' },
                  ].map(item => (
                    <div key={item.label} style={{
                      padding: '14px', borderRadius: 10,
                      background: item.active ? 'rgba(239,68,68,0.08)' : 'var(--bg-elevated)',
                      border: `1px solid ${item.active ? 'rgba(239,68,68,0.25)' : 'var(--border-subtle)'}`,
                    }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                        <span style={{ fontSize: 12, color: item.active ? 'var(--bearish)' : 'var(--text-muted)', fontWeight: 700 }}>
                          {item.active ? '◉' : '○'} {item.label}
                        </span>
                      </div>
                      <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>{item.desc}</div>
                    </div>
                  ))}
                </div>
                <ConfidenceBar label="Institutional Activity" value={beh.institutional_activity_score} color="var(--accent-secondary)" />
              </div>
            ) : (
              <div style={{ color: 'var(--text-muted)', fontSize: 13, textAlign: 'center', padding: '40px 0' }}>No behaviour data</div>
            )}
          </div>

          <div className="card">
            <div className="card-title">Market Structure</div>
            {bLoad ? (
              <div className="skeleton" style={{ height: 140, borderRadius: 8 }} />
            ) : beh ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                {[
                  { label: 'Change of Character (CHoCH)', active: beh.choch_detected, color: '#8b5cf6', desc: 'Trend reversal signal' },
                  { label: 'Break of Structure (BOS)', active: beh.bos_detected, color: '#3b82f6', desc: 'Trend continuation' },
                  { label: 'IV Spike Detected', active: beh.iv_spike, color: '#f59e0b', desc: 'Options volatility expansion' },
                  { label: 'OI Buildup', active: beh.oi_buildup, color: '#14b8a6', desc: 'Institutional positioning' },
                ].map(item => (
                  <div key={item.label} style={{
                    display: 'flex', alignItems: 'center', gap: 14,
                    padding: '12px 14px', borderRadius: 10,
                    background: item.active ? `${item.color}10` : 'var(--bg-elevated)',
                    border: `1px solid ${item.active ? `${item.color}30` : 'var(--border-subtle)'}`,
                  }}>
                    <div style={{
                      width: 10, height: 10, borderRadius: '50%',
                      background: item.active ? item.color : 'var(--border-strong)',
                      boxShadow: item.active ? `0 0 8px ${item.color}` : 'none',
                      flexShrink: 0,
                    }} />
                    <div style={{ flex: 1 }}>
                      <div style={{ fontSize: 12, fontWeight: 600, color: item.active ? 'var(--text-primary)' : 'var(--text-muted)' }}>{item.label}</div>
                      <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>{item.desc}</div>
                    </div>
                    <span style={{ fontSize: 12, color: item.active ? item.color : 'var(--text-muted)', fontWeight: 700 }}>
                      {item.active ? 'ACTIVE' : 'NONE'}
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <div style={{ color: 'var(--text-muted)', fontSize: 13, textAlign: 'center', padding: '40px 0' }}>No structure data</div>
            )}
          </div>
        </div>

        {/* Recent Behaviour History */}
        {behaviours && behaviours.length > 1 && (
          <div className="card">
            <div className="card-title">Behaviour Log (Recent Days)</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
              {behaviours.slice(0, 7).map((b, i) => (
                <div key={b.date} style={{
                  display: 'flex', gap: 12, alignItems: 'center',
                  padding: '10px 0',
                  borderBottom: i < 6 ? '1px solid var(--border-subtle)' : 'none',
                }}>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-muted)', width: 80, flexShrink: 0 }}>{b.date}</span>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, flex: 1 }}>
                    {b.choch_detected && <span style={{ fontSize: 10, padding: '2px 8px', borderRadius: 6, background: 'rgba(139,92,246,0.15)', color: '#8b5cf6' }}>CHoCH</span>}
                    {b.bos_detected && <span style={{ fontSize: 10, padding: '2px 8px', borderRadius: 6, background: 'rgba(59,130,246,0.15)', color: '#3b82f6' }}>BOS</span>}
                    {b.stop_hunt_up && <span style={{ fontSize: 10, padding: '2px 8px', borderRadius: 6, background: 'rgba(239,68,68,0.15)', color: 'var(--bearish)' }}>Hunt↑</span>}
                    {b.stop_hunt_down && <span style={{ fontSize: 10, padding: '2px 8px', borderRadius: 6, background: 'rgba(239,68,68,0.15)', color: 'var(--bearish)' }}>Hunt↓</span>}
                    {b.iv_spike && <span style={{ fontSize: 10, padding: '2px 8px', borderRadius: 6, background: 'rgba(245,158,11,0.15)', color: 'var(--neutral)' }}>IV Spike</span>}
                    {!b.choch_detected && !b.bos_detected && !b.stop_hunt_up && !b.stop_hunt_down && !b.iv_spike && (
                      <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>No signals</span>
                    )}
                  </div>
                  <div style={{ width: 80 }}>
                    <ConfidenceBar value={b.institutional_activity_score} showPct={false} height={4} color="var(--accent-secondary)" />
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
