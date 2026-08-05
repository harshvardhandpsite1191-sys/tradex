'use client'
import Link from 'next/link'
import { usePathname } from 'next/navigation'

const NAV_ITEMS = [
  { label: 'Market Intelligence', href: '/dashboard/market-intelligence', icon: '◈', section: 'Intelligence' },
  { label: 'Trade Center',        href: '/dashboard/trade-center',        icon: '⟳', section: 'Intelligence' },
  { label: 'Forecast Center',     href: '/dashboard/forecast-center',     icon: '◎', section: 'Intelligence' },
  { label: 'Liquidity Map',       href: '/dashboard/liquidity-intelligence', icon: '≋', section: 'Intelligence' },
  { label: 'Options Intelligence',href: '/dashboard/options-intelligence', icon: '⬡', section: 'Intelligence' },
  { label: 'Research Laboratory', href: '/dashboard/research-laboratory', icon: '⚗', section: 'Research' },
  { label: 'Historical Replay',   href: '/dashboard/historical-replay',   icon: '▷', section: 'Research' },
  { label: 'Performance Center',  href: '/dashboard/performance-center',  icon: '⬛', section: 'Analytics' },
]

export default function Sidebar() {
  const pathname = usePathname()
  const sections = [...new Set(NAV_ITEMS.map(i => i.section))]

  return (
    <aside className="sidebar">
      {/* Logo */}
      <div className="sidebar-logo">
        <div className="logo-title">AI-QROS</div>
        <div className="logo-sub">Quant Research & Options Intelligence</div>
      </div>

      {/* Navigation */}
      <nav style={{ flex: 1, paddingBottom: 16 }}>
        {sections.map(section => (
          <div key={section}>
            <div className="sidebar-section-label">{section}</div>
            {NAV_ITEMS.filter(i => i.section === section).map(item => (
              <Link
                key={item.href}
                href={item.href}
                className={`nav-item ${pathname === item.href ? 'active' : ''}`}
              >
                <span style={{ fontSize: 15, width: 18, textAlign: 'center' }}>{item.icon}</span>
                <span>{item.label}</span>
              </Link>
            ))}
          </div>
        ))}
      </nav>

      {/* Bottom status */}
      <div style={{ padding: '12px 16px', borderTop: '1px solid var(--border-subtle)' }}>
        <div className="flex items-center gap-2" style={{ fontSize: 11, color: 'var(--text-muted)' }}>
          <span className="status-dot live"></span>
          <span>Phase 22 — Auto-Retraining Active</span>
        </div>
      </div>
    </aside>
  )
}
