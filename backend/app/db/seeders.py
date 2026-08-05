"""
AI-QROS — Phase 0 Default Rules Seeder
Seeds the Rule Registry with all initial operational rules and thresholds
Runs on application startup if rules are not already present
"""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.governance import RuleRegistry, RuleVersion
import structlog

logger = structlog.get_logger("aiqros.seeder")

# ─────────────────────────────────────────────
# Default Rules — Phase 0 (Project Foundation)
# These thresholds are updated by Phase 22 (Continuous Learning)
# ─────────────────────────────────────────────
DEFAULT_RULES = [

    # ── Phase 17: Trade Quality Thresholds ──────────────────────
    # Initial values below are placeholder defaults.
    # Phase 17 (Trade Quality Engine) will calibrate these from historical data.
    # Phase 22 (Continuous Learning) will update these daily.
    {
        "rule_name": "TRADE_MIN_CONFIDENCE",
        "description": "Minimum confidence score required for a trade recommendation to pass Phase 18 filter.",
        "category": "TRADE_QUALITY",
        "parameters": {"threshold": None, "unit": "probability_0_to_1", "note": "Set by Phase 17"},
    },
    {
        "rule_name": "TRADE_MIN_PROBABILITY",
        "description": "Minimum directional probability (bullish or bearish) from Phase 16 Decision Engine.",
        "category": "TRADE_QUALITY",
        "parameters": {"threshold": None, "unit": "probability_0_to_1", "note": "Set by Phase 17"},
    },
    {
        "rule_name": "TRADE_MIN_WIN_RATE",
        "description": "Minimum historical win rate for the matched scenario from Phase 8 verification.",
        "category": "TRADE_QUALITY",
        "parameters": {"threshold": None, "unit": "fraction_0_to_1", "note": "Set by Phase 17"},
    },
    {
        "rule_name": "TRADE_MIN_OCCURRENCES",
        "description": "Minimum number of historical occurrences a scenario must have to be trusted.",
        "category": "TRADE_QUALITY",
        "parameters": {"threshold": None, "unit": "count", "note": "Set by Phase 17"},
    },
    {
        "rule_name": "TRADE_MIN_EXPECTED_VALUE",
        "description": "Minimum expected value (EV) of a trade. EV = (win_rate x avg_win) - (loss_rate x avg_loss).",
        "category": "TRADE_QUALITY",
        "parameters": {"threshold": None, "unit": "ratio_positive", "note": "Set by Phase 17"},
    },
    {
        "rule_name": "TRADE_MIN_RISK_REWARD",
        "description": "Minimum Risk:Reward ratio required before a recommendation is generated.",
        "category": "TRADE_QUALITY",
        "parameters": {"threshold": None, "unit": "ratio", "note": "Set by Phase 17"},
    },
    {
        "rule_name": "TRADE_MIN_LIQUIDITY",
        "description": "Minimum option volume (lots) for a strike to be considered liquid enough to trade.",
        "category": "TRADE_QUALITY",
        "parameters": {"threshold": None, "unit": "lots", "note": "Set by Phase 17"},
    },
    {
        "rule_name": "TRADE_MAX_SPREAD",
        "description": "Maximum bid-ask spread (as % of premium) for an option to be tradeable.",
        "category": "TRADE_QUALITY",
        "parameters": {"threshold": None, "unit": "fraction_of_premium", "note": "Set by Phase 17"},
    },

    # ── Phase 8: Hypothesis Rejection Gate ──────────────────────
    {
        "rule_name": "HYPOTHESIS_MIN_OCCURRENCES",
        "description": "Minimum historical occurrences for a hypothesis to pass Phase 8 verification.",
        "category": "HYPOTHESIS_REJECTION",
        "parameters": {"threshold": None, "unit": "count", "note": "Set by Phase 8"},
    },
    {
        "rule_name": "HYPOTHESIS_MIN_WIN_RATE",
        "description": "Minimum win rate for a hypothesis to be validated (not rejected).",
        "category": "HYPOTHESIS_REJECTION",
        "parameters": {"threshold": None, "unit": "fraction_0_to_1", "note": "Set by Phase 8"},
    },
    {
        "rule_name": "HYPOTHESIS_MIN_STABILITY",
        "description": "Minimum stability score (consistency of win rate across rolling windows).",
        "category": "HYPOTHESIS_REJECTION",
        "parameters": {"threshold": None, "unit": "score_0_to_1", "note": "Set by Phase 8"},
    },

    # ── Phase 9: Knowledge Ranking ───────────────────────────────
    {
        "rule_name": "KNOWLEDGE_HIGH_RANK_THRESHOLD",
        "description": "Minimum rank score for a concept to be 'high ranking' and influence Phase 16 decisions.",
        "category": "RANKING",
        "parameters": {"threshold": None, "unit": "score_0_to_1", "note": "Set by Phase 9"},
    },

    # ── Phase 22: Learning Validation Gate ──────────────────────
    {
        "rule_name": "LEARNING_MIN_VALIDATION_PASS_RATE",
        "description": "Minimum fraction of new hypotheses that must pass Phase 8 before promoting to production.",
        "category": "LEARNING",
        "parameters": {"threshold": None, "unit": "fraction_0_to_1", "note": "Set by Phase 22"},
    },

    # ── System Rules ─────────────────────────────────────────────
    {
        "rule_name": "SYSTEM_HISTORICAL_YEARS",
        "description": "Number of years of historical data to use for backtesting and research.",
        "category": "SYSTEM",
        "parameters": {"value": 5, "unit": "years"},
    },
    {
        "rule_name": "SYSTEM_LIVE_UPDATE_INTERVAL_SECONDS",
        "description": "How often (in seconds) the Live Market Engine (Phase 20) updates all intelligence.",
        "category": "SYSTEM",
        "parameters": {"value": None, "unit": "seconds", "note": "Set by Phase 20"},
    },
]



async def seed_default_rules(db: AsyncSession):
    """
    Seeds default rules into Rule Registry on startup.
    Only inserts rules that do not already exist.
    """
    seeded_count = 0
    for rule_data in DEFAULT_RULES:
        existing = await db.execute(
            select(RuleRegistry).where(RuleRegistry.rule_name == rule_data["rule_name"])
        )
        if existing.scalar_one_or_none():
            continue  # Already exists — skip

        db_rule = RuleRegistry(
            rule_name=rule_data["rule_name"],
            description=rule_data["description"],
            category=rule_data["category"],
            parameters=rule_data["parameters"],
            version=1,
            is_active=True,
            created_by="system_seed",
        )
        db.add(db_rule)
        await db.flush()

        version_record = RuleVersion(
            rule_id=db_rule.id,
            version=1,
            parameters_snapshot=rule_data["parameters"],
            change_reason="System default — seeded on startup",
            created_by="system_seed",
            is_current=True,
        )
        db.add(version_record)
        seeded_count += 1

    await db.commit()
    if seeded_count > 0:
        logger.info("rules_seeded", count=seeded_count)
    else:
        logger.info("rules_already_seeded", message="All default rules already present.")
