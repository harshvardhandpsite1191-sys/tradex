// lib/hooks.ts — SWR data hooks for all AI-QROS endpoints
import useSWR from 'swr'
import { apiFetch } from './api'
import type {
  RegimeResult, BehaviourSummary, OpeningIntelligence, ExpiryIntelligence,
  TradeSignal, TradeRecommendation, AIPrediction, MarketScenario,
  SimilarityMatch, ResearchFinding, ResearchHypothesis, PipelineLog,
  PerformanceMetrics, TradePerformanceLog, LiveStatus, LearningStatus,
} from './types'

const fetcher = (url: string) => apiFetch<any>(url)

// ─── Market Intelligence ────────────────────────────────────────────────────
export const useRegimes = (symbol = 'NIFTY') =>
  useSWR<RegimeResult[]>(`/regimes/?symbol=${symbol}&limit=5`, fetcher, { refreshInterval: 60000 })

export const useBehaviours = (symbol = 'NIFTY') =>
  useSWR<BehaviourSummary[]>(`/behaviours/?symbol=${symbol}&limit=10`, fetcher, { refreshInterval: 60000 })

export const useOpening = (symbol = 'NIFTY') =>
  useSWR<OpeningIntelligence>(`/opening/latest?symbol=${symbol}`, fetcher, { refreshInterval: 300000 })

export const useExpiry = (symbol = 'NIFTY') =>
  useSWR<ExpiryIntelligence>(`/expiry/latest?symbol=${symbol}`, fetcher, { refreshInterval: 300000 })

// ─── Trade Center ───────────────────────────────────────────────────────────
export const useSignal = (symbol = 'NIFTY') =>
  useSWR<TradeSignal>(`/signals/latest?symbol=${symbol}`, fetcher, { refreshInterval: 60000 })

export const useRecommendations = (symbol = 'NIFTY') =>
  useSWR<TradeRecommendation[]>(`/recommendations/?symbol=${symbol}&limit=5`, fetcher, { refreshInterval: 300000 })

// ─── AI Predictions ─────────────────────────────────────────────────────────
export const usePrediction = (symbol = 'NIFTY') =>
  useSWR<AIPrediction>(`/predictions/latest?symbol=${symbol}`, fetcher, { refreshInterval: 300000 })

// ─── Scenarios ──────────────────────────────────────────────────────────────
export const useScenarios = () =>
  useSWR<MarketScenario[]>(`/scenarios/?limit=20`, fetcher, { refreshInterval: 600000 })

// ─── Historical Similarity ───────────────────────────────────────────────────
export const useSimilarity = (symbol = 'NIFTY') =>
  useSWR<SimilarityMatch[]>(`/similarity/?symbol=${symbol}&limit=5`, fetcher, { refreshInterval: 600000 })

// ─── Research ───────────────────────────────────────────────────────────────
export const useResearchFindings = () =>
  useSWR<ResearchFinding[]>(`/research/findings?limit=30`, fetcher, { refreshInterval: 600000 })

export const useHypotheses = () =>
  useSWR<ResearchHypothesis[]>(`/research/hypotheses?limit=30`, fetcher, { refreshInterval: 600000 })

export const usePipelineLogs = () =>
  useSWR<PipelineLog[]>(`/research/pipeline-logs?limit=10`, fetcher, { refreshInterval: 600000 })

// ─── Performance ────────────────────────────────────────────────────────────
export const usePerformanceMetrics = () =>
  useSWR<PerformanceMetrics>(`/performance/metrics`, fetcher, { refreshInterval: 300000 })

export const usePerformanceTrades = () =>
  useSWR<TradePerformanceLog[]>(`/performance/trades?limit=50`, fetcher, { refreshInterval: 300000 })

// ─── Live ────────────────────────────────────────────────────────────────────
export const useLiveStatus = (symbol = 'NIFTY') =>
  useSWR<LiveStatus>(`/live/status?symbol=${symbol}`, fetcher, { refreshInterval: 5000 })

// ─── Learning ───────────────────────────────────────────────────────────────
export const useLearningStatus = () =>
  useSWR<LearningStatus>(`/learning/status`, fetcher, { refreshInterval: 600000 })
