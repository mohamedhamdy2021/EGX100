"""
Data Fetcher Module for EGX Stocks
Handles fetching stock data from Yahoo Finance
Uses cached daily data for price updates (Yahoo Finance doesn't support real-time for EGX)
"""

import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, Optional, List, Tuple
from cachetools import TTLCache
import logging
import threading

from config import EGX_TOP_COMPANIES, DATA_CONFIG

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Cache for stock data - 15 min TTL
stock_cache = TTLCache(maxsize=200, ttl=DATA_CONFIG["cache_timeout_minutes"] * 60)
# Separate cache for latest prices - 2 min TTL for faster updates
price_cache = TTLCache(maxsize=200, ttl=120)
# Lock for thread safety
_fetch_lock = threading.Lock()


def get_stock_data(ticker: str, period: str = None, interval: str = None, force_refresh: bool = False) -> Optional[pd.DataFrame]:
    """Fetch historical stock data from Yahoo Finance"""
    period = period or DATA_CONFIG["default_period"]
    interval = interval or DATA_CONFIG["default_interval"]
    cache_key = f"{ticker}_{period}_{interval}"
    
    if not force_refresh and cache_key in stock_cache:
        return stock_cache[cache_key]
    
    try:
        logger.info(f"Fetching data for {ticker}...")
        stock = yf.Ticker(ticker)
        df = stock.history(period=period, interval=interval)
        
        if df.empty:
            logger.warning(f"No data for {ticker}")
            return None
        
        stock_cache[cache_key] = df
        logger.info(f"Got {len(df)} records for {ticker}")
        return df
    except Exception as e:
        logger.error(f"Error fetching {ticker}: {e}")
        return None


def get_stock_info(ticker: str) -> Optional[Dict]:
    """Get stock information"""
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        if ticker in EGX_TOP_COMPANIES:
            info.update(EGX_TOP_COMPANIES[ticker])
        return info
    except Exception as e:
        logger.error(f"Error info {ticker}: {e}")
        return None


def get_multiple_stocks_data(tickers: List[str] = None, period: str = None, interval: str = None) -> Dict[str, pd.DataFrame]:
    """Fetch data for multiple stocks"""
    if tickers is None:
        tickers = list(EGX_TOP_COMPANIES.keys())
    
    result = {}
    for ticker in tickers:
        data = get_stock_data(ticker, period, interval)
        if data is not None and not data.empty:
            result[ticker] = data
    
    return result


def get_real_time_price(ticker: str) -> Optional[Dict]:
    """
    Get latest price data. Uses daily data since Yahoo Finance
    doesn't support intraday data for Egyptian stocks.
    """
    # Check price cache first
    if ticker in price_cache:
        return price_cache[ticker]
    
    try:
        # Use daily data - more reliable for EGX
        stock = yf.Ticker(ticker)
        df = stock.history(period="5d", interval="1d")
        
        if df.empty or len(df) < 1:
            # Fallback: use cached stock data if available
            cached_key = f"{ticker}_6mo_1d"
            if cached_key in stock_cache:
                df = stock_cache[cached_key]
            if df is None or df.empty:
                return None
        
        latest = df.iloc[-1]
        previous = df.iloc[-2] if len(df) > 1 else latest
        
        price_change = float(latest['Close'] - previous['Close'])
        prev_close = float(previous['Close'])
        price_change_percent = (price_change / prev_close * 100) if prev_close > 0 else 0
        
        result = {
            "ticker": ticker,
            "name": EGX_TOP_COMPANIES.get(ticker, {}).get("name", ticker),
            "arabic_name": EGX_TOP_COMPANIES.get(ticker, {}).get("arabic_name", ""),
            "current_price": round(float(latest['Close']), 2),
            "open": round(float(latest['Open']), 2),
            "high": round(float(latest['High']), 2),
            "low": round(float(latest['Low']), 2),
            "volume": int(latest['Volume']),
            "change": round(price_change, 2),
            "change_percent": round(price_change_percent, 2),
            "timestamp": datetime.now().isoformat(),
        }
        
        price_cache[ticker] = result
        return result
    except Exception as e:
        logger.error(f"Error price {ticker}: {e}")
        return None


def get_latest_price_from_cache(ticker: str) -> Optional[float]:
    """Get latest price from any available cache - fastest possible"""
    # Check price cache
    if ticker in price_cache:
        return price_cache[ticker]['current_price']
    
    # Check stock data cache
    cached_key = f"{ticker}_6mo_1d"
    if cached_key in stock_cache:
        df = stock_cache[cached_key]
        if df is not None and not df.empty:
            return round(float(df['Close'].iloc[-1]), 2)
    
    return None


def get_all_prices() -> List[Dict]:
    """Get current prices for all EGX companies"""
    prices = []
    for ticker in EGX_TOP_COMPANIES.keys():
        price_data = get_real_time_price(ticker)
        if price_data:
            price_data["sector"] = EGX_TOP_COMPANIES[ticker]["sector"]
            prices.append(price_data)
    return prices


def bulk_update_prices(tickers: List[str] = None) -> Dict[str, float]:
    """
    Update prices for multiple tickers efficiently.
    Returns dict of ticker -> current_price
    """
    if tickers is None:
        tickers = list(EGX_TOP_COMPANIES.keys())
    
    updated = {}
    for ticker in tickers:
        try:
            price_info = get_real_time_price(ticker)
            if price_info:
                updated[ticker] = price_info['current_price']
        except Exception as e:
            logger.error(f"Bulk update error {ticker}: {e}")
    
    return updated


def validate_ticker(ticker: str) -> Tuple[bool, str]:
    """Validate if a ticker is valid"""
    if ticker not in EGX_TOP_COMPANIES:
        return False, f"{ticker} not in EGX100 list"
    data = get_stock_data(ticker, period="1mo")
    if data is None or data.empty:
        return False, f"No data for {ticker}"
    return True, f"{ticker} valid ({len(data)} records)"


def get_market_summary() -> Dict:
    """Get market summary"""
    prices = get_all_prices()
    if not prices:
        return {"error": "No market data"}
    
    gainers = sorted([p for p in prices if p['change_percent'] > 0], key=lambda x: x['change_percent'], reverse=True)
    losers = sorted([p for p in prices if p['change_percent'] < 0], key=lambda x: x['change_percent'])
    
    return {
        "timestamp": datetime.now().isoformat(),
        "total_stocks": len(prices),
        "gainers_count": len(gainers),
        "losers_count": len(losers),
        "unchanged_count": len(prices) - len(gainers) - len(losers),
        "top_gainers": gainers[:5],
        "top_losers": losers[:5],
        "total_volume": sum(p['volume'] for p in prices),
        "average_change_percent": round(sum(p['change_percent'] for p in prices) / len(prices), 2),
    }
