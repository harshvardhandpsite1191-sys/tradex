// lib/types.ts — TypeScript interfaces matching all backend response schemas

// ─── Regime ────────────────────────────────────────────────────────────────
export interface RegimeResult {
  date: string
  symbol: string
  regime: 'Trending' | 'Ranging' | 'Volatile' | 'Breakout' | 'Reversal'
  regime_score: number
  adx: number
  atr_pct: number
  method: 'gmm' | 'heuristic'
}

// ─── Behaviours ────────────────────────────────────────────────────────────
export interface BehaviourSummary {
  date: string
  symbol: string
  choch_detected: boolean
  bos_detected: boolean
  stop_hunt_up: boolean
  stop_hunt_down: boolean
  equal_highs: boolean
  equal_lows: boolean
  iv_spike: boolean
  oi_buildup: boolean
  institutional_activity_score: number
}

// ─── Opening Intelligence ───────────────────────────────────────────────────
export interface OpeningIntelligence {
  date: string
  symbol: string
  expected_gap_pct: number
  opening_bias: 'Bullish' | 'Bearish' | 'Neutral'
  gift_nifty: number
  predicted_ib_high: number
  predicted_ib_low: number
  global_sentiment_score: number
}

// ─── Expiry Intelligence ────────────────────────────────────────────────────
export interface ExpiryIntelligence {
  date: string
  symbol: string
  expiry_date: string
  max_pain_strike: number
  net_gex: number
  pcr: number
  pin_probability: number
  days_to_expiry: number
}

// ─── Trade Signal ───────────────────────────────────────────────────────────
export interface TradeSignal {
  date: string
  symbol: string
  signal: 'BUY_CALL' | 'BUY_PUT' | 'SHORT_STRADDLE' | 'IRON_CONDOR' | 'NEUTRAL'
  direction: 'Bullish' | 'Bearish' | 'Neutral'
  confidence: number
  regime_score: number
  behaviour_score: number
  ai_probability: number
}

// ─── Trade Recommendation ───────────────────────────────────────────────────
export interface TradeRecommendation {
  id: number
  date: string
  symbol: string
  strategy: string
  leg1_strike: number
  leg1_type: string
  leg1_action: string
  leg2_strike: number | null
  leg2_type: string | null
  leg2_action: string | null
  estimated_premium: number
  stop_loss: number
  target: number
  max_loss: number
  max_profit: number
  expiry_date: string
  status: 'pending' | 'active' | 'closed'
  outcome: 'Win' | 'Loss' | 'Scratch' | null
  pnl: number | null
}

// ─── AI Prediction ──────────────────────────────────────────────────────────
export interface AIPrediction {
  date: string
  symbol: string
  predicted_direction: 'Bullish' | 'Bearish' | 'Neutral'
  bullish_prob: number
  bearish_prob: number
  neutral_prob: number
  model_version: string
  feature_count: number
}

// ─── Market Scenario ────────────────────────────────────────────────────────
export interface MarketScenario {
  id: number
  name: string
  category: string
  regime: string
  win_rate: number
  avg_return_pct: number
  sample_size: number
  description: string
}

// ─── Historical Similarity ──────────────────────────────────────────────────
export interface SimilarityMatch {
  date: string
  similar_date: string
  symbol: string
  euclidean_distance: number
  cosine_similarity: number
  next_day_return: number
  regime: string
}

// ─── Research Findings ──────────────────────────────────────────────────────
export interface ResearchFinding {
  id: number
  hypothesis: string
  regime: string
  win_rate: number
  edge_ratio: number
  sample_size: number
  status: 'active' | 'deprecated'
  created_at: string
}

export interface ResearchHypothesis {
  id: number
  statement: string
  status: 'pending' | 'confirmed' | 'rejected'
  p_value: number | null
  win_rate: number | null
  created_at: string
}

export interface PipelineLog {
  id: number
  run_date: string
  hypotheses_generated: number
  hypotheses_confirmed: number
  findings_deprecated: number
  duration_seconds: number
}

// ─── Performance Metrics ────────────────────────────────────────────────────
export interface PerformanceMetrics {
  total_trades: number
  winning_trades: number
  losing_trades: number
  win_rate: number
  total_pnl: number
  avg_pnl_per_trade: number
  profit_factor: number
  max_drawdown: number
  sharpe_ratio: number
}

export interface TradePerformanceLog {
  id: number
  date: string
  symbol: string
  strategy: string
  pnl: number
  outcome: 'Win' | 'Loss' | 'Scratch'
  roi_pct: number
}

// ─── Live Engine ────────────────────────────────────────────────────────────
export interface LiveStatus {
  symbol: string
  last_price: number
  vwap: number
  volume: number
  vwap_deviation_pct: number
  volume_spike: boolean
  timestamp: string
}

// ─── Continuous Learning ────────────────────────────────────────────────────
export interface LearningStatus {
  date: string
  psi_score: number
  drift_detected: boolean
  retrain_triggered: boolean
  model_version: string
}
