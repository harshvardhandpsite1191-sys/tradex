'use client'
// components/ui/DataTable.tsx — Sortable data table with styled rows

interface Column<T> {
  key: keyof T
  label: string
  render?: (val: T[keyof T], row: T) => React.ReactNode
  align?: 'left' | 'right' | 'center'
  mono?: boolean
}

interface DataTableProps<T> {
  columns: Column<T>[]
  data: T[]
  rowKey: keyof T
  loading?: boolean
  emptyMessage?: string
  maxHeight?: number
}

export default function DataTable<T>({ columns, data, rowKey, loading, emptyMessage = 'No data', maxHeight }: DataTableProps<T>) {
  if (loading) {
    return (
      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        {[...Array(5)].map((_, i) => (
          <div key={i} style={{ padding: '14px 20px', borderBottom: '1px solid var(--border-subtle)', display: 'flex', gap: 16 }}>
            {columns.map((_, j) => (
              <div key={j} className="skeleton" style={{ height: 14, flex: 1, borderRadius: 4 }} />
            ))}
          </div>
        ))}
      </div>
    )
  }

  return (
    <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
      <div style={{ overflowX: 'auto', maxHeight: maxHeight, overflowY: maxHeight ? 'auto' : undefined }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr style={{ background: 'var(--bg-elevated)', borderBottom: '1px solid var(--border-default)' }}>
              {columns.map(col => (
                <th key={String(col.key)} style={{
                  padding: '10px 16px', textAlign: col.align || 'left',
                  color: 'var(--text-muted)', fontWeight: 600,
                  fontSize: 11, letterSpacing: '0.07em', textTransform: 'uppercase',
                  whiteSpace: 'nowrap',
                }}>
                  {col.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.length === 0 ? (
              <tr>
                <td colSpan={columns.length} style={{
                  padding: '40px 20px', textAlign: 'center',
                  color: 'var(--text-muted)', fontSize: 13,
                }}>
                  {emptyMessage}
                </td>
              </tr>
            ) : data.map((row, i) => (
              <tr key={String(row[rowKey])} style={{
                borderBottom: '1px solid var(--border-subtle)',
                transition: 'background var(--transition-fast)',
                cursor: 'default',
              }}
                onMouseEnter={e => (e.currentTarget.style.background = 'var(--bg-card-hover)')}
                onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
              >
                {columns.map(col => (
                  <td key={String(col.key)} style={{
                    padding: '12px 16px',
                    textAlign: col.align || 'left',
                    color: 'var(--text-primary)',
                    fontFamily: col.mono ? 'var(--font-mono)' : undefined,
                    fontSize: col.mono ? 12 : 13,
                  }}>
                    {col.render ? col.render(row[col.key], row) : String(row[col.key] ?? '—')}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
