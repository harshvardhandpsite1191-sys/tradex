'use client'
import StatCard from '@/components/ui/StatCard'
import ConfidenceBar from '@/components/ui/ConfidenceBar'
import DataTable from '@/components/ui/DataTable'
import { useResearchFindings, useHypotheses, usePipelineLogs } from '@/lib/hooks'
import type { ResearchFinding, ResearchHypothesis, PipelineLog } from '@/lib/types'

export default function ResearchLaboratoryPage() {
  const { data: findings, isLoading: fLoad } = useResearchFindings()
  const { data: hypotheses, isLoading: hLoad } = useHypotheses()
  const { data: logs, isLoading: lLoad } = usePipelineLogs()

  const active = findings?.filter(f => f.status === 'active') || []
  const confirmed = hypotheses?.filter(h => h.status === 'confirmed') || []
  const pending = hypotheses?.filter(h => h.status === 'pending') || []

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Research Laboratory</h1>
          <p className="page-subtitle">Autonomous hypothesis generation, statistical validation, and market edge discovery</p>
        </div>
        <div style={{ padding: '6px 14px', borderRadius: 8, background: 'rgba(139,92,246,0.15)', border: '1px solid rgba(139,92,246,0.3)', fontSize: 12, color: 'var(--accent-secondary)', fontWeight: 600 }}>
          ⚗ AI Research Pipeline
        </div>
      </div>

      <div className="page-body">
        {/* Metrics */}
        <div className="stats-grid-4">
          <StatCard label="Active Findings" value={active.length} loading={fLoad} accent="green" />
          <StatCard label="Confirmed Hypotheses" value={confirmed.length} loading={hLoad} accent="blue" />
          <StatCard label="Pending Test" value={pending.length} loading={hLoad} accent="amber" />
          <StatCard label="Pipeline Runs" value={logs?.length ?? 0} loading={lLoad} accent="purple" />
        </div>

        {/* Active Market Findings */}
        <div>
          <div className="section-title">Active Market Findings ({active.length})</div>
          <DataTable<ResearchFinding>
            loading={fLoad}
            data={active.slice(0, 15)}
            rowKey="id"
            maxHeight={400}
            emptyMessage="Research pipeline has not run yet. Runs nightly at 8:30 PM IST."
            columns={[
              { key: 'hypothesis', label: 'Finding / Hypothesis', render: (v) => (
                <span style={{ fontSize: 12, lineHeight: 1.5, color: 'var(--text-primary)' }}>{String(v)}</span>
              )},
              { key: 'regime', label: 'Regime', render: (v) => (
                <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--accent-secondary)' }}>{String(v)}</span>
              )},
              { key: 'win_rate', label: 'Win Rate', align: 'right', render: (v) => (
                <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, color: Number(v) >= 0.6 ? 'var(--bullish)' : Number(v) >= 0.5 ? 'var(--neutral)' : 'var(--bearish)' }}>
                  {(Number(v) * 100).toFixed(1)}%
                </span>
              )},
              { key: 'edge_ratio', label: 'Edge', align: 'right', mono: true, render: (v) => (
                <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 600, color: 'var(--accent-teal)' }}>{Number(v).toFixed(2)}x</span>
              )},
              { key: 'sample_size', label: 'n', align: 'right', mono: true },
              { key: 'created_at', label: 'Created', render: (v) => (
                <span style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>{String(v).split('T')[0]}</span>
              )},
            ]}
          />
        </div>

        {/* Hypotheses table */}
        <div className="content-grid-2">
          <div>
            <div className="section-title">Pending Hypotheses ({pending.length})</div>
            <DataTable<ResearchHypothesis>
              loading={hLoad}
              data={pending.slice(0, 10)}
              rowKey="id"
              maxHeight={320}
              emptyMessage="No pending hypotheses"
              columns={[
                { key: 'statement', label: 'Hypothesis', render: (v) => (
                  <span style={{ fontSize: 12, lineHeight: 1.5 }}>{String(v)}</span>
                )},
                { key: 'created_at', label: 'Date', render: (v) => (
                  <span style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>{String(v).split('T')[0]}</span>
                )},
              ]}
            />
          </div>

          <div>
            <div className="section-title">Confirmed Hypotheses ({confirmed.length})</div>
            <DataTable<ResearchHypothesis>
              loading={hLoad}
              data={confirmed.slice(0, 10)}
              rowKey="id"
              maxHeight={320}
              emptyMessage="None confirmed yet"
              columns={[
                { key: 'statement', label: 'Statement', render: (v) => (
                  <span style={{ fontSize: 12 }}>{String(v)}</span>
                )},
                { key: 'win_rate', label: 'Win Rate', align: 'right', render: (v) => v !== null ? (
                  <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, color: 'var(--bullish)' }}>{(Number(v) * 100).toFixed(0)}%</span>
                ) : '—'},
                { key: 'p_value', label: 'p-val', align: 'right', render: (v) => v !== null ? (
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: Number(v) < 0.05 ? 'var(--bullish)' : 'var(--neutral)' }}>{Number(v).toFixed(3)}</span>
                ) : '—'},
              ]}
            />
          </div>
        </div>

        {/* Pipeline Run Logs */}
        <div>
          <div className="section-title">Pipeline Run History</div>
          <DataTable<PipelineLog>
            loading={lLoad}
            data={logs || []}
            rowKey="id"
            emptyMessage="No pipeline runs recorded"
            columns={[
              { key: 'run_date', label: 'Run Date', render: (v) => (
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-muted)' }}>{String(v).split('T')[0]}</span>
              )},
              { key: 'hypotheses_generated', label: 'Generated', align: 'right', mono: true },
              { key: 'hypotheses_confirmed', label: 'Confirmed', align: 'right', render: (v) => (
                <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, color: Number(v) > 0 ? 'var(--bullish)' : 'var(--text-muted)' }}>{String(v)}</span>
              )},
              { key: 'findings_deprecated', label: 'Deprecated', align: 'right', render: (v) => (
                <span style={{ fontFamily: 'var(--font-mono)', color: Number(v) > 0 ? 'var(--bearish)' : 'var(--text-muted)' }}>{String(v)}</span>
              )},
              { key: 'duration_seconds', label: 'Duration', align: 'right', render: (v) => (
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-secondary)' }}>{Number(v).toFixed(1)}s</span>
              )},
            ]}
          />
        </div>
      </div>
    </div>
  )
}
