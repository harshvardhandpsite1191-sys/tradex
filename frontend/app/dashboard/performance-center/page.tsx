'use client'
import StatCard from '@/components/ui/StatCard'
import ConfidenceBar from '@/components/ui/ConfidenceBar'
import DataTable from '@/components/ui/DataTable'
import { OutcomeBadge } from '@/components/ui/SignalBadge'
import { usePerformanceMetrics, usePerformanceTrades, useLearningStatus } from '@/lib/hooks'
import type { TradePerformanceLog } from '@/lib/types'

export default function PerformanceCenterPage() {
  const { data: metrics, isLoading: mLoad } = usePerformanceMetrics()
  const { data: trades, isLoading: tLoad } = usePerformanceTrades()
  const { data: learning, isLoading: lLoad } = useLearningStatus()

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Performance Center</h1>
          <p className="page-subtitle">Track trade outcomes, portfolio P&L, win rates, and AI model drift status</p>
        </div>
        {learning && (
          <div style={{
            padding: '6px 14px', borderRadius: 8, fontSize: 12,
            background: learning.drift_detected ? 'rgba(239,68,68,0.12)' : 'rgba(34,197,94,0.12)',
            color: learning.drift_detected ? 'var(--bearish)' : 'var(--bullish)',
            border: `1px solid ${learning.drift_detected ? 'rgba(239,68,68,0.3)' : 'rgba(34,197,94,0.3)'}`,
            fontWeight: 600,
          }}>
            {learning.drift_detected ? '⚠ Drift Detected' : '✓ Model Stable'}
          </div>
        )}
      </div>

      <div className="page-body">
        {/* Portfolio Metrics */}
        <div>
          <div className="section-title">Portfolio Metrics</div>
          <div className="stats-grid-4">
            <StatCard label="Total Trades" value={metrics?.total_trades ?? '—'} loading={mLoad} accent="blue" />
            <StatCard label="Win Rate" value={metrics ? `${(metrics.win_rate * 100).toFixed(1)}%` : '—'} loading={mLoad}
              accent={metrics ? (metrics.win_rate >= 0.55 ? 'green' : metrics.win_rate >= 0.45 ? 'amber' : 'red') : 'blue'} mono />
            <StatCard label="Total P&L" value={metrics ? `₹${metrics.total_pnl.toFixed(0)}` : '—'} loading={mLoad}
              accent={metrics ? (metrics.total_pnl >= 0 ? 'green' : 'red') : 'blue'}
              delta={metrics?.total_pnl} mono />
            <StatCard label="Profit Factor" value={metrics ? metrics.profit_factor.toFixed(2) : '—'} loading={mLoad}
              accent={metrics ? (metrics.profit_factor >= 1.5 ? 'green' : metrics.profit_factor >= 1 ? 'amber' : 'red') : 'blue'} mono />
          </div>
        </div>

        {/* Secondary Metrics */}
        <div className="stats-grid-4">
          <StatCard label="Sharpe Ratio" value={metrics ? metrics.sharpe_ratio.toFixed(2) : '—'} loading={mLoad}
            accent={metrics ? (metrics.sharpe_ratio >= 1 ? 'green' : 'amber') : 'blue'} mono />
          <StatCard label="Max Drawdown" value={metrics ? `${(metrics.max_drawdown * 100).toFixed(2)}%` : '—'} loading={mLoad} accent="red" mono />
          <StatCard label="Avg P&L/Trade" value={metrics ? `₹${metrics.avg_pnl_per_trade.toFixed(0)}` : '—'} loading={mLoad}
            accent={metrics ? (metrics.avg_pnl_per_trade >= 0 ? 'green' : 'red') : 'blue'} mono />
          <StatCard label="Wins / Losses" value={metrics ? `${metrics.winning_trades} / ${metrics.losing_trades}` : '—'} loading={mLoad} accent="purple" mono />
        </div>

        <div className="content-grid-2">
          {/* Win Rate Visual */}
          {metrics && (
            <div className="card">
              <div className="card-title">Portfolio Overview</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
                <ConfidenceBar label="Win Rate" value={metrics.win_rate} color={metrics.win_rate >= 0.55 ? 'var(--bullish)' : metrics.win_rate >= 0.45 ? 'var(--neutral)' : 'var(--bearish)'} height={10} />
                <div style={{ display: 'flex', gap: 4, height: 20, borderRadius: 6, overflow: 'hidden' }}>
                  <div style={{ width: `${metrics.win_rate * 100}%`, background: 'var(--bullish)' }} />
                  <div style={{ flex: 1, background: 'var(--bearish)' }} />
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12 }}>
                  <span style={{ color: 'var(--bullish)' }}>✓ {metrics.winning_trades} wins</span>
                  <span style={{ color: 'var(--bearish)' }}>✕ {metrics.losing_trades} losses</span>
                </div>
                <hr className="divider" />
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13 }}>
                  <span style={{ color: 'var(--text-secondary)' }}>Total P&L</span>
                  <span style={{
                    fontFamily: 'var(--font-mono)', fontWeight: 800, fontSize: 18,
                    color: metrics.total_pnl >= 0 ? 'var(--bullish)' : 'var(--bearish)',
                  }}>
                    {metrics.total_pnl >= 0 ? '+' : ''}₹{metrics.total_pnl.toFixed(0)}
                  </span>
                </div>
              </div>
            </div>
          )}

          {/* Model Learning Status */}
          {!lLoad && learning && (
            <div className="card">
              <div className="card-title">Continuous Learning Status</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
                <div style={{
                  padding: '16px', borderRadius: 12,
                  background: learning.drift_detected ? 'rgba(239,68,68,0.08)' : 'rgba(34,197,94,0.08)',
                  border: `1px solid ${learning.drift_detected ? 'rgba(239,68,68,0.2)' : 'rgba(34,197,94,0.2)'}`,
                  textAlign: 'center',
                }}>
                  <div style={{ fontSize: 28, marginBottom: 6 }}>{learning.drift_detected ? '⚠' : '✓'}</div>
                  <div style={{ fontWeight: 700, color: learning.drift_detected ? 'var(--bearish)' : 'var(--bullish)' }}>
                    {learning.drift_detected ? 'Feature Drift Detected' : 'Model Stable'}
                  </div>
                  <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>
                    {learning.retrain_triggered ? 'Retraining triggered automatically' : 'No retraining needed'}
                  </div>
                </div>
                <ConfidenceBar label="PSI Drift Score" value={Math.min(1, learning.psi_score / 0.5)} color={learning.psi_score > 0.25 ? 'var(--bearish)' : 'var(--bullish)'} />
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12 }}>
                  <span style={{ color: 'var(--text-muted)' }}>PSI Score</span>
                  <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, color: learning.psi_score > 0.25 ? 'var(--bearish)' : 'var(--bullish)' }}>{learning.psi_score.toFixed(4)}</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12 }}>
                  <span style={{ color: 'var(--text-muted)' }}>Model Version</span>
                  <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>{learning.model_version}</span>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Trade Log */}
        <div>
          <div className="section-title">Trade History</div>
          <DataTable<TradePerformanceLog>
            loading={tLoad}
            data={trades || []}
            rowKey="id"
            maxHeight={480}
            emptyMessage="No closed trades yet"
            columns={[
              { key: 'date', label: 'Date', render: (v) => (
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-muted)' }}>{String(v)}</span>
              )},
              { key: 'symbol', label: 'Symbol', render: (v) => (
                <span style={{ fontWeight: 700, fontSize: 12, color: 'var(--accent-primary)' }}>{String(v)}</span>
              )},
              { key: 'strategy', label: 'Strategy', render: (v) => (
                <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{String(v)}</span>
              )},
              { key: 'outcome', label: 'Outcome', render: (v) => <OutcomeBadge outcome={v as any} /> },
              { key: 'pnl', label: 'P&L', align: 'right', render: (v) => (
                <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, color: Number(v) >= 0 ? 'var(--bullish)' : 'var(--bearish)' }}>
                  {Number(v) >= 0 ? '+' : ''}₹{Number(v).toFixed(0)}
                </span>
              )},
              { key: 'roi_pct', label: 'ROI %', align: 'right', render: (v) => (
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: Number(v) >= 0 ? 'var(--bullish)' : 'var(--bearish)' }}>
                  {Number(v) >= 0 ? '+' : ''}{Number(v).toFixed(2)}%
                </span>
              )},
            ]}
          />
        </div>
      </div>
    </div>
  )
}
