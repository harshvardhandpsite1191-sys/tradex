import type { Metadata } from 'next'
import '../styles/globals.css'

export const metadata: Metadata = {
  title: 'AI-QROS — Quantitative Research & Options Intelligence System',
  description: 'Autonomous Quantitative Research & Decision Intelligence Platform for NIFTY & SENSEX Options',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  )
}
