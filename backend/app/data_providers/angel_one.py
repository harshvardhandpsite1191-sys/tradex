"""
AI-QROS — Angel One SmartAPI Connector
Phase 2: Data Infrastructure

Provides historical OHLC candle data for NIFTY option contracts.
Angel One SmartAPI is FREE — requires Angel One trading account.
Supplements NSE Bhavcopy with intraday candle data for specific contracts.

Data coverage:
- OHLC candles at 1min, 5min, 15min, 30min, 60min, 1day intervals
- Up to 8,000 candles per request
- Any NSE F&O instrument via symboltoken

Authentication:
- Uses TOTP (Time-based OTP) for 2FA
- Auto-session refresh on expiry
"""

import asyncio
from datetime import datetime, date, timedelta
from typing import Optional
import pandas as pd
import structlog
from app.config import settings

logger = structlog.get_logger("aiqros.data.angel_one")

# Interval mapping to Angel One API format
INTERVAL_MAP = {
    "1min":  "ONE_MINUTE",
    "5min":  "FIVE_MINUTE",
    "15min": "FIFTEEN_MINUTE",
    "30min": "THIRTY_MINUTE",
    "60min": "ONE_HOUR",
    "1day":  "ONE_DAY",
}

NIFTY_INDEX_TOKEN  = "26000"   # NIFTY 50 index symboltoken
SENSEX_INDEX_TOKEN = "1"       # BSE SENSEX symboltoken
BANKNIFTY_TOKEN    = "26009"   # NIFTY Bank index token


class AngelOneConnector:
    """
    Async wrapper around Angel One SmartAPI.
    Handles authentication, session management, and data fetching.
    """

    def __init__(self):
        self._obj = None
        self._session_data = None
        self._last_login = None

    def _is_session_valid(self) -> bool:
        """Check if current session is still valid (sessions expire ~8 hours)."""
        if self._last_login is None:
            return False
        hours_since_login = (datetime.utcnow() - self._last_login).total_seconds() / 3600
        return hours_since_login < 7.5

    def login(self) -> bool:
        """
        Authenticate with Angel One SmartAPI using TOTP.
        Requires env vars: ANGEL_ONE_API_KEY, ANGEL_ONE_CLIENT_ID,
                           ANGEL_ONE_PASSWORD, ANGEL_ONE_TOTP_SECRET
        """
        if self._is_session_valid():
            return True

        try:
            import pyotp
            from SmartApi import SmartConnect

            if not all([
                settings.ANGEL_ONE_API_KEY,
                settings.ANGEL_ONE_CLIENT_ID,
                settings.ANGEL_ONE_PASSWORD,
                settings.ANGEL_ONE_TOTP_SECRET,
            ]):
                logger.warning(
                    "angel_one_credentials_missing",
                    message="Set ANGEL_ONE_API_KEY, ANGEL_ONE_CLIENT_ID, ANGEL_ONE_PASSWORD, ANGEL_ONE_TOTP_SECRET in .env"
                )
                return False

            self._obj = SmartConnect(api_key=settings.ANGEL_ONE_API_KEY)
            totp = pyotp.TOTP(settings.ANGEL_ONE_TOTP_SECRET).now()
            data = self._obj.generateSession(
                settings.ANGEL_ONE_CLIENT_ID,
                settings.ANGEL_ONE_PASSWORD,
                totp
            )

            if data.get("status"):
                self._session_data = data["data"]
                self._last_login = datetime.utcnow()
                logger.info("angel_one_login_success", client=settings.ANGEL_ONE_CLIENT_ID)
                return True
            else:
                logger.error("angel_one_login_failed", response=data)
                return False

        except ImportError:
            logger.error("angel_one_not_installed", message="pip install SmartApi pyotp")
            return False
        except Exception as e:
            logger.error("angel_one_login_error", error=str(e))
            return False

    def get_candles(
        self,
        symbol_token: str,
        exchange: str,
        interval: str,
        from_date: datetime,
        to_date: datetime,
    ) -> Optional[pd.DataFrame]:
        """
        Fetch OHLC candle data for a specific option token.
        exchange: "NFO" for NIFTY options, "NSE" for index
        interval: one of "1min", "5min", "15min", "30min", "60min", "1day"
        """
        if not self._is_session_valid():
            if not self.login():
                return None

        api_interval = INTERVAL_MAP.get(interval, "ONE_DAY")

        try:
            historic_param = {
                "exchange": exchange,
                "symboltoken": symbol_token,
                "interval": api_interval,
                "fromdate": from_date.strftime("%Y-%m-%d %H:%M"),
                "todate": to_date.strftime("%Y-%m-%d %H:%M"),
            }

            resp = self._obj.getCandleData(historic_param)

            if not resp.get("status") or not resp.get("data"):
                logger.warning("angel_one_no_data", token=symbol_token, interval=interval)
                return None

            df = pd.DataFrame(
                resp["data"],
                columns=["timestamp", "open", "high", "low", "close", "volume"]
            )
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            df["symbol_token"] = symbol_token
            df["exchange"] = exchange
            df["interval"] = interval
            df["data_source"] = "ANGEL_ONE"

            logger.info(
                "angel_one_candles_fetched",
                token=symbol_token,
                interval=interval,
                rows=len(df),
            )
            return df

        except Exception as e:
            logger.error("angel_one_candle_error", error=str(e), token=symbol_token)
            return None

    def get_nifty_candles(
        self,
        interval: str = "1day",
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
    ) -> Optional[pd.DataFrame]:
        """Get NIFTY index OHLC candles (5 years daily)."""
        from_date = from_date or (datetime.utcnow() - timedelta(days=365 * 5))
        to_date = to_date or datetime.utcnow()
        return self.get_candles(NIFTY_INDEX_TOKEN, "NSE", interval, from_date, to_date)

    def get_scrip_master(self) -> Optional[pd.DataFrame]:
        """
        Download Angel One Scrip Master — maps option symbols to tokensTokens.
        NIFTY option naming: NIFTY24DEC2400CE → token 12345
        Used to find symboltoken for any option contract.
        """
        import requests
        try:
            url = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
            resp = requests.get(url, timeout=30)
            data = resp.json()
            df = pd.DataFrame(data)
            # Filter to NIFTY/BANKNIFTY F&O only
            df = df[df["name"].str.startswith(("NIFTY", "BANKNIFTY", "SENSEX"), na=False)]
            df = df[df["exch_seg"] == "NFO"]
            logger.info("scrip_master_downloaded", rows=len(df))
            return df
        except Exception as e:
            logger.error("scrip_master_error", error=str(e))
            return None


# Singleton instance — shared across the application
angel_one = AngelOneConnector()
