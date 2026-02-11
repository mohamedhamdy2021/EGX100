"""
Data Fetcher Module for EGX Stocks
Multi-source price fetching:
  1. Yahoo Finance (primary) - daily close prices
  2. Investing.com scraping (fallback) - more accurate prices
Displays price source and data timestamp for transparency
"""

import yfinance as yf
import pandas as pd
import requests
from datetime import datetime, timedelta
from typing import Dict, Optional, List, Tuple
from cachetools import TTLCache
import logging
import threading
import json
import time

from config import EGX_TOP_COMPANIES, DATA_CONFIG

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s', datefmt='%H:%M:%S')
logger = logging.getLogger(__name__)

# Caches
stock_cache = TTLCache(maxsize=200, ttl=DATA_CONFIG["cache_timeout_minutes"] * 60)
price_cache = TTLCache(maxsize=200, ttl=90)  # 90 sec TTL for prices
_fetch_lock = threading.Lock()

# Mapping: Yahoo ticker -> Investing.com pair ID (for scraping)
# These are the pair IDs from investing.com for Egyptian stocks
INVESTING_IDS = {
    "COMI.CA": "cib-egypt",
    "HDBK.CA": "housing-development-bank",
    "TMGH.CA": "talaat-moustafa",
    "PHDC.CA": "palm-hills-development",
    "SWDY.CA": "el-sewedy-electric",
    "ETEL.CA": "telecom-egypt",
    "EAST.CA": "eastern-co",
    "FWRY.CA": "fawry",
    "HRHO.CA": "efg-hermes",
    "EFIH.CA": "e-finance",
    "JUFO.CA": "juhayna",
    "ABUK.CA": "abu-qir-fertilizers",
    "SKPC.CA": "sidi-kerir-petrochemicals",
    "ORWE.CA": "oriental-weavers",
    "EMFD.CA": "emaar-misr",
    "OCDI.CA": "orascom-development",
    "ISPH.CA": "ibnsina-pharma",
    "EFID.CA": "edita-food-industries",
    "AMOC.CA": "alexandria-mineral-oils",
    "HELI.CA": "heliopolis-housing",
    "CIEB.CA": "credit-agricole-egypt",
    "ADIB.CA": "abu-dhabi-islamic-bank-egypt",
    "EXPA.CA": "export-development-bank",
    "ARCC.CA": "arabian-cement",
    "SVCE.CA": "south-valley-cement",
}


# ========================= Yahoo Finance =========================

def get_stock_data(ticker: str, period: str = None, interval: str = None, force_refresh: bool = False) -> Optional[pd.DataFrame]:
    """Fetch historical stock data from Yahoo Finance"""
    period = period or DATA_CONFIG["default_period"]
    interval = interval or DATA_CONFIG["default_interval"]
    cache_key = f"{ticker}_{period}_{interval}"

    if not force_refresh and cache_key in stock_cache:
        return stock_cache[cache_key]

    try:
        stock = yf.Ticker(ticker)
        df = stock.history(period=period, interval=interval)
        if df.empty:
            logger.warning(f"No YF data for {ticker}")
            return None
        stock_cache[cache_key] = df
        logger.info(f"YF: {ticker} -> {len(df)} records")
        return df
    except Exception as e:
        logger.error(f"YF error {ticker}: {e}")
        return None


def get_stock_info(ticker: str) -> Optional[Dict]:
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        if ticker in EGX_TOP_COMPANIES:
            info.update(EGX_TOP_COMPANIES[ticker])
        return info
    except Exception as e:
        logger.error(f"Info error {ticker}: {e}")
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


# ========================= Price Fetching (Multi-Source) =========================

def _get_price_yahoo(ticker: str) -> Optional[Dict]:
    """Get latest price from Yahoo Finance"""
    try:
        stock = yf.Ticker(ticker)
        # Use fast_info for quick price (if available)
        try:
            fi = stock.fast_info
            if hasattr(fi, 'last_price') and fi.last_price and fi.last_price > 0:
                prev = fi.previous_close if hasattr(fi, 'previous_close') and fi.previous_close else fi.last_price
                change = fi.last_price - prev
                return {
                    "current_price": round(float(fi.last_price), 2),
                    "change": round(float(change), 2),
                    "change_percent": round(float(change / prev * 100), 2) if prev > 0 else 0,
                    "source": "Yahoo (fast)",
                    "data_time": datetime.now().isoformat(),
                }
        except:
            pass

        # Fallback to history
        df = stock.history(period="5d", interval="1d")
        if df.empty or len(df) < 1:
            return None

        latest = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else latest
        change = float(latest['Close'] - prev['Close'])
        prev_close = float(prev['Close'])

        return {
            "current_price": round(float(latest['Close']), 2),
            "open": round(float(latest['Open']), 2),
            "high": round(float(latest['High']), 2),
            "low": round(float(latest['Low']), 2),
            "volume": int(latest['Volume']),
            "change": round(change, 2),
            "change_percent": round(change / prev_close * 100, 2) if prev_close > 0 else 0,
            "source": "Yahoo Finance",
            "data_time": str(df.index[-1]),
        }
    except Exception as e:
        logger.error(f"YF price error {ticker}: {e}")
        return None


def _get_price_scrape(ticker: str) -> Optional[Dict]:
    """Scrape price from mubasher.info (Arabic financial portal for EGX)"""
    try:
        # Use mubasher.info - reliable source for EGX data
        symbol = ticker.replace('.CA', '')
        url = f"https://www.mubasher.info/api/1/correcteddata/getsecuritydailychart?securityId={symbol}&marketId=EGX"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
        }
        
        resp = requests.get(url, headers=headers, timeout=8)
        if resp.status_code == 200:
            data = resp.json()
            if data and isinstance(data, list) and len(data) > 0:
                last = data[-1]
                price = last.get('close') or last.get('last')
                if price and price > 0:
                    return {
                        "current_price": round(float(price), 2),
                        "source": "Mubasher",
                        "data_time": datetime.now().isoformat(),
                    }
    except Exception as e:
        logger.debug(f"Scrape error {ticker}: {e}")
    
    return None


def get_real_time_price(ticker: str) -> Optional[Dict]:
    """
    Get the best available price from multiple sources.
    Priority: 1. Yahoo Finance fast_info  2. Yahoo Finance history  3. Cached data
    """
    # Check price cache first
    if ticker in price_cache:
        return price_cache[ticker]

    company_info = EGX_TOP_COMPANIES.get(ticker, {})
    
    # Try Yahoo Finance (most reliable free source)
    result = _get_price_yahoo(ticker)
    
    # If Yahoo failed, try using cached stock data
    if not result:
        cached_key = f"{ticker}_6mo_1d"
        if cached_key in stock_cache:
            df = stock_cache[cached_key]
            if df is not None and not df.empty:
                latest = df.iloc[-1]
                prev = df.iloc[-2] if len(df) > 1 else latest
                change = float(latest['Close'] - prev['Close'])
                result = {
                    "current_price": round(float(latest['Close']), 2),
                    "open": round(float(latest['Open']), 2),
                    "high": round(float(latest['High']), 2),
                    "low": round(float(latest['Low']), 2),
                    "volume": int(latest['Volume']),
                    "change": round(change, 2),
                    "change_percent": round(change / float(prev['Close']) * 100, 2) if float(prev['Close']) > 0 else 0,
                    "source": "Cached Data",
                    "data_time": str(df.index[-1]),
                }
    
    if not result:
        return None
    
    # Add company info
    result.update({
        "ticker": ticker,
        "name": company_info.get("name", ticker),
        "arabic_name": company_info.get("arabic_name", ""),
        "timestamp": datetime.now().isoformat(),
    })
    
    # Fill missing fields
    result.setdefault("open", result["current_price"])
    result.setdefault("high", result["current_price"])
    result.setdefault("low", result["current_price"])
    result.setdefault("volume", 0)
    result.setdefault("change", 0)
    result.setdefault("change_percent", 0)
    
    # Cache it
    price_cache[ticker] = result
    return result


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
    """Update prices for multiple tickers, returns ticker->price dict"""
    if tickers is None:
        tickers = list(EGX_TOP_COMPANIES.keys())
    updated = {}
    for ticker in tickers:
        try:
            # Force fresh data by clearing price cache for this ticker
            if ticker in price_cache:
                del price_cache[ticker]
            info = get_real_time_price(ticker)
            if info:
                updated[ticker] = info['current_price']
        except Exception as e:
            logger.error(f"Bulk update error {ticker}: {e}")
    return updated


def validate_ticker(ticker: str) -> Tuple[bool, str]:
    if ticker not in EGX_TOP_COMPANIES:
        return False, f"{ticker} not in EGX100"
    data = get_stock_data(ticker, period="1mo")
    if data is None or data.empty:
        return False, f"No data for {ticker}"
    return True, f"{ticker} valid ({len(data)} records)"


def get_market_summary() -> Dict:
    prices = get_all_prices()
    if not prices:
        return {"error": "No data"}
    gainers = sorted([p for p in prices if p['change_percent'] > 0], key=lambda x: x['change_percent'], reverse=True)
    losers = sorted([p for p in prices if p['change_percent'] < 0], key=lambda x: x['change_percent'])
    return {
        "timestamp": datetime.now().isoformat(),
        "total_stocks": len(prices),
        "gainers_count": len(gainers), "losers_count": len(losers),
        "unchanged_count": len(prices) - len(gainers) - len(losers),
        "top_gainers": gainers[:5], "top_losers": losers[:5],
        "total_volume": sum(p['volume'] for p in prices),
        "average_change_percent": round(sum(p['change_percent'] for p in prices) / len(prices), 2),
    }
