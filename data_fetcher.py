"""
Data Fetcher Module for EGX Stocks
Multi-source price fetching:
  1. Investing.com scraping (PRIMARY - more accurate)
  2. Google Finance scraping (backup)
  3. Yahoo Finance (fallback for historical data)
Shows price source and data timestamp for full transparency
"""

import yfinance as yf
import pandas as pd
import requests
import re
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, List, Tuple
from cachetools import TTLCache
import logging
import threading
import json
import time

from config import EGX_TOP_COMPANIES, DATA_CONFIG

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s', datefmt='%H:%M:%S')
logger = logging.getLogger(__name__)

# Egypt timezone (UTC+2)
EGYPT_TZ = timezone(timedelta(hours=2))

# Caches
stock_cache = TTLCache(maxsize=200, ttl=DATA_CONFIG["cache_timeout_minutes"] * 60)
price_cache = TTLCache(maxsize=200, ttl=120)  # 2 min TTL for prices
_fetch_lock = threading.Lock()

# Investing.com slugs for Egyptian stocks 
INVESTING_SLUGS = {
    "COMI.CA": "commercial-international-bank-egypt",
    "HDBK.CA": "housing-and-development-bank",
    "TMGH.CA": "talaat-moustafa-group",
    "PHDC.CA": "palm-hills-developments",
    "SWDY.CA": "elsewedy-electric",
    "ETEL.CA": "telecom-egypt",
    "EAST.CA": "eastern-company",
    "FWRY.CA": "fawry-for-banking-technology",
    "HRHO.CA": "efg-hermes-holding",
    "EFIH.CA": "e-finance",
    "JUFO.CA": "juhayna-food-industries",
    "ABUK.CA": "abu-qir-fertilizers",
    "SKPC.CA": "sidi-kerir-petrochemicals",
    "ORWE.CA": "oriental-weavers-carpet",
    "EMFD.CA": "emaar-misr",
    "OCDI.CA": "orascom-development-egypt",
    "ISPH.CA": "ibnsina-pharma",
    "EFID.CA": "edita-food-industries",
    "AMOC.CA": "alexandria-mineral-oils-co",
    "HELI.CA": "heliopolis-housing",
    "CIEB.CA": "credit-agricole-egypt",
    "ADIB.CA": "abu-dhabi-islamic-bank-misr",
    "EXPA.CA": "export-development-bank-of-egypt",
    "ARCC.CA": "arabian-cement",
    "SVCE.CA": "suez-cement",
}

# Google Finance ticker mappings (ticker without .CA)
GOOGLE_TICKERS = {ticker: ticker.replace('.CA', '') for ticker in EGX_TOP_COMPANIES}


def get_egypt_time():
    """Get current time in Egypt timezone"""
    return datetime.now(EGYPT_TZ)


def is_market_hours():
    """Check if Egyptian Exchange is currently open (Sun-Thu, 10:00-14:30 EET)"""
    now = get_egypt_time()
    # Sunday=6, Monday=0, ..., Thursday=3, Friday=4, Saturday=5
    weekday = now.weekday()
    if weekday in [4, 5]:  # Friday & Saturday = closed
        return False
    hour = now.hour
    minute = now.minute
    time_minutes = hour * 60 + minute
    # Market open: 10:00 to 14:30 (600 to 870 in minutes)
    return 600 <= time_minutes <= 870


# ========================= Investing.com Scraping =========================

def _get_price_investing(ticker: str) -> Optional[Dict]:
    """Scrape current price from Investing.com"""
    slug = INVESTING_SLUGS.get(ticker)
    if not slug:
        return None
    
    try:
        url = f"https://www.investing.com/equities/{slug}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Cache-Control": "max-age=0",
        }
        
        resp = requests.get(url, headers=headers, timeout=12, allow_redirects=True)
        if resp.status_code != 200:
            logger.debug(f"Investing.com HTTP {resp.status_code} for {ticker}")
            return None
        
        text = resp.text
        
        # Try multiple regex patterns to find the price
        price = None
        patterns = [
            r'data-test="instrument-price-last"[^>]*>([0-9,\.]+)<',
            r'"last_numeric"\s*:\s*([0-9\.]+)',
            r'"last"\s*:\s*"([0-9,\.]+)"',
            r'instrument-price-last["\s][^>]*>([0-9,\.]+)',
            r'<span[^>]*class="[^"]*last-price[^"]*"[^>]*>([0-9,\.]+)',
            r'"lastPrice"\s*:\s*"?([0-9,\.]+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                price_str = match.group(1).replace(',', '')
                try:
                    price = float(price_str)
                    if price > 0:
                        break
                except ValueError:
                    continue
        
        if not price or price <= 0:
            return None
        
        # Try to get change data
        change = 0
        change_pct = 0
        change_patterns = [
            r'data-test="instrument-price-change"[^>]*>([+-]?[0-9,\.]+)<',
            r'"change_numeric"\s*:\s*([+-]?[0-9\.]+)',
        ]
        pct_patterns = [
            r'data-test="instrument-price-change-percent"[^>]*>\(?([+-]?[0-9,\.]+)%?\)?<',
            r'"changePercent_numeric"\s*:\s*([+-]?[0-9\.]+)',
        ]
        
        for pattern in change_patterns:
            match = re.search(pattern, text)
            if match:
                try:
                    change = float(match.group(1).replace(',', ''))
                    break
                except:
                    pass
        
        for pattern in pct_patterns:
            match = re.search(pattern, text)
            if match:
                try:
                    change_pct = float(match.group(1).replace(',', ''))
                    break
                except:
                    pass
        
        egypt_now = get_egypt_time()
        
        result = {
            "current_price": round(price, 2),
            "change": round(change, 2),
            "change_percent": round(change_pct, 2),
            "source": "Investing.com",
            "data_time": egypt_now.strftime('%Y-%m-%d %H:%M:%S'),
        }
        
        logger.info(f"Investing.com: {ticker} = {price} EGP")
        return result
        
    except requests.Timeout:
        logger.debug(f"Investing.com timeout for {ticker}")
    except Exception as e:
        logger.debug(f"Investing.com error {ticker}: {e}")
    
    return None


# ========================= Google Finance Scraping =========================

def _get_price_google(ticker: str) -> Optional[Dict]:
    """Scrape current price from Google Finance"""
    try:
        symbol = ticker.replace('.CA', '')
        url = f"https://www.google.com/finance/quote/{symbol}:EGX"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
        }
        
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code != 200:
            return None
        
        text = resp.text
        
        # Google Finance stores the price in specific data attributes
        price = None
        patterns = [
            r'data-last-price="([0-9\.]+)"',
            r'class="YMlKec fxKbKc"[^>]*>([0-9,\.]+)',
            r'class="[^"]*kf1m0[^"]*"[^>]*>([0-9,\.]+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                try:
                    price = float(match.group(1).replace(',', ''))
                    if price > 0:
                        break
                except:
                    continue
        
        if not price or price <= 0:
            return None
        
        # Try to get change
        change = 0
        change_pct = 0
        change_match = re.search(r'data-currency-change="([+-]?[0-9\.]+)"', text)
        pct_match = re.search(r'data-currency-change-percent="([+-]?[0-9\.]+)"', text)
        
        if change_match:
            try: change = float(change_match.group(1))
            except: pass
        if pct_match:
            try: change_pct = float(pct_match.group(1))
            except: pass
        
        egypt_now = get_egypt_time()
        
        result = {
            "current_price": round(price, 2),
            "change": round(change, 2),
            "change_percent": round(change_pct, 2),
            "source": "Google Finance",
            "data_time": egypt_now.strftime('%Y-%m-%d %H:%M:%S'),
        }
        
        logger.info(f"Google Finance: {ticker} = {price} EGP")
        return result
        
    except Exception as e:
        logger.debug(f"Google Finance error {ticker}: {e}")
    
    return None


# ========================= Yahoo Finance =========================

def get_stock_data(ticker: str, period: str = None, interval: str = None, force_refresh: bool = False) -> Optional[pd.DataFrame]:
    """Fetch historical stock data from Yahoo Finance (for charts & analysis)"""
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


def _get_price_yahoo(ticker: str) -> Optional[Dict]:
    """Get latest price from Yahoo Finance (fallback)"""
    try:
        stock = yf.Ticker(ticker)
        # Try fast_info first
        try:
            fi = stock.fast_info
            if hasattr(fi, 'last_price') and fi.last_price and fi.last_price > 0:
                prev = fi.previous_close if hasattr(fi, 'previous_close') and fi.previous_close else fi.last_price
                change = fi.last_price - prev
                egypt_now = get_egypt_time()
                return {
                    "current_price": round(float(fi.last_price), 2),
                    "change": round(float(change), 2),
                    "change_percent": round(float(change / prev * 100), 2) if prev > 0 else 0,
                    "source": "Yahoo Finance",
                    "data_time": egypt_now.strftime('%Y-%m-%d %H:%M:%S'),
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
        egypt_now = get_egypt_time()

        return {
            "current_price": round(float(latest['Close']), 2),
            "open": round(float(latest['Open']), 2),
            "high": round(float(latest['High']), 2),
            "low": round(float(latest['Low']), 2),
            "volume": int(latest['Volume']),
            "change": round(change, 2),
            "change_percent": round(change / prev_close * 100, 2) if prev_close > 0 else 0,
            "source": "Yahoo Finance (EOD)",
            "data_time": str(df.index[-1]),
        }
    except Exception as e:
        logger.error(f"YF price error {ticker}: {e}")
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
    """Fetch data for multiple stocks (for chart analysis)"""
    if tickers is None:
        tickers = list(EGX_TOP_COMPANIES.keys())
    result = {}
    for ticker in tickers:
        data = get_stock_data(ticker, period, interval)
        if data is not None and not data.empty:
            result[ticker] = data
    return result


# ========================= Price Fetching (Multi-Source) =========================

def get_real_time_price(ticker: str) -> Optional[Dict]:
    """
    Get the best available price. Priority:
      1. Investing.com (most accurate for EGX)
      2. Google Finance (backup)
      3. Yahoo Finance (fallback)
      4. Cached data (last resort)
    """
    # Check price cache first
    if ticker in price_cache:
        cached = price_cache[ticker]
        cached['from_cache'] = True
        return cached

    company_info = EGX_TOP_COMPANIES.get(ticker, {})
    result = None
    
    # 1. Try Investing.com first (most accurate)
    result = _get_price_investing(ticker)
    
    # 2. Try Google Finance
    if not result:
        result = _get_price_google(ticker)
    
    # 3. Try Yahoo Finance
    if not result:
        result = _get_price_yahoo(ticker)
    
    # 4. Fallback to cached stock data
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
        "timestamp": get_egypt_time().strftime('%Y-%m-%d %H:%M:%S'),
        "from_cache": False,
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
            # Clear price cache to force fresh data
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
        "timestamp": get_egypt_time().isoformat(),
        "market_open": is_market_hours(),
        "total_stocks": len(prices),
        "gainers_count": len(gainers), "losers_count": len(losers),
        "unchanged_count": len(prices) - len(gainers) - len(losers),
        "top_gainers": gainers[:5], "top_losers": losers[:5],
        "total_volume": sum(p['volume'] for p in prices),
        "average_change_percent": round(sum(p['change_percent'] for p in prices) / len(prices), 2),
    }
