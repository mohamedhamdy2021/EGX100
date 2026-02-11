"""
Data Fetcher Module for EGX Stocks
Prices: TradingView Scanner API (real-time, free, no auth)
Charts: yfinance historical data (auto_adjust=False)
Display: Investing.com as source link
"""

import yfinance as yf
import pandas as pd
import requests
import json
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, List, Tuple
from cachetools import TTLCache
import logging
import threading

from config import EGX_TOP_COMPANIES, DATA_CONFIG

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s', datefmt='%H:%M:%S')
logger = logging.getLogger(__name__)

EGYPT_TZ = timezone(timedelta(hours=2))
stock_cache = TTLCache(maxsize=200, ttl=DATA_CONFIG["cache_timeout_minutes"] * 60)
price_cache = TTLCache(maxsize=200, ttl=120)
_fetch_lock = threading.Lock()

INVESTING_DOMAIN = "sa.investing.com"

# ==================== Investing.com slugs for display links ====================
INVESTING_SLUGS = {
    "COMI.CA": "com-intl-bk",
    "HDBK.CA": "housing---dev",
    "TMGH.CA": "t-m-g-holding",
    "PHDC.CA": "palm-hill-dev",
    "SWDY.CA": "elsewedy-cable",
    "ETEL.CA": "telecom-egypt",
    "EAST.CA": "eastern-co",
    "FWRY.CA": "fawry-banking-and-payment",
    "HRHO.CA": "efg-hermes-hol",
    "EFIH.CA": "e-finance-digital-financial-invest",
    "JUFO.CA": "juhayna-food-industries",
    "ABUK.CA": "abou-kir-fertilizers",
    "SKPC.CA": "sidi-kerir-pet",
    "ORWE.CA": "oriental-weave",
    "EMFD.CA": "emaar-misr-for-development-sae",
    "OCDI.CA": "6th-oct-dev-in",
    "ISPH.CA": "ibnsina-pharma",
    "EFID.CA": "edita-food-industries",
    "AMOC.CA": "alx-mineral-oi",
    "HELI.CA": "heliopolis-housing",
    "CIEB.CA": "credit-agricol",
    "ADIB.CA": "abu-dhabi-islamic-bank-egypt",
    "EXPA.CA": "exp-dev-bk-of",
    "ARCC.CA": "arabian-cement-co-sae",
    "SVCE.CA": "s.-valley-ceme",
    "QNBE.CA": "qnb-alahli",
    "SAIB.CA": "societe-arabe-internationale-de-banque",
    "VALU.CA": "valu",
    "CCAP.CA": "ci-capital-holding",
    "ORHD.CA": "ora-developers",
    "MNHD.CA": "madinet-nasr-for-housing-and-development",
    "IRON.CA": "egyptian-iron-steel",
    "ACGC.CA": "arab-cotton-ginning",
    "DOMT.CA": "arabian-food-industries-domty",
    "RAYA.CA": "raya-holding-for-financial-investments",
    "ODIN.CA": "odin-investments",
    "CIRA.CA": "cairo-for-investment-and-real-estate-development",
    "TALM.CA": "t-m-g-holding",
    "ORAS.CA": "orascom-construction",
}

# TradingView ticker format: COMI.CA -> EGX:COMI
def _to_tv_ticker(ticker: str) -> str:
    return f"EGX:{ticker.replace('.CA', '')}"

def _from_tv_ticker(tv_ticker: str) -> str:
    return f"{tv_ticker.replace('EGX:', '')}.CA"


def get_egypt_time():
    return datetime.now(EGYPT_TZ)


def is_market_hours():
    now = get_egypt_time()
    if now.weekday() in [4, 5]:
        return False
    return 600 <= (now.hour * 60 + now.minute) <= 870


def get_investing_url(ticker: str) -> str:
    slug = INVESTING_SLUGS.get(ticker)
    return f"https://{INVESTING_DOMAIN}/equities/{slug}" if slug else ""


# ========================= Method 1: TradingView Scanner API =========================

def _get_price_tradingview(ticker: str) -> Optional[Dict]:
    """
    Get REAL-TIME price from TradingView Scanner API.
    This is a FREE, public API that returns current prices for any stock.
    No auth, no Cloudflare, no blocking!
    
    POST https://scanner.tradingview.com/egypt/scan
    Body: {"symbols": {"tickers": ["EGX:COMI"]}, "columns": [...]}
    """
    tv_ticker = _to_tv_ticker(ticker)
    
    try:
        url = "https://scanner.tradingview.com/egypt/scan"
        payload = {
            "symbols": {
                "tickers": [tv_ticker]
            },
            "columns": [
                "close",
                "open",
                "high",
                "low",
                "volume",
                "change"
            ]
        }
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Content-Type': 'application/json',
        }
        
        resp = requests.post(url, json=payload, headers=headers, timeout=10)
        
        if resp.status_code != 200:
            logger.warning(f"⚠️ TradingView API HTTP {resp.status_code} for {ticker}. Body: {resp.text[:300]}")
            return None
        
        data = resp.json()
        
        if not data.get('data') or len(data['data']) == 0:
            logger.warning(f"⚠️ TradingView: no data for {ticker}")
            return None
        
        row = data['data'][0]
        values = row.get('d', [])
        
        if not values or len(values) < 5:
            logger.warning(f"⚠️ TradingView: incomplete data for {ticker}: {values}")
            return None
        
        # columns order: close, open, high, low, volume, change%
        price = float(values[0]) if values[0] is not None else None
        open_p = float(values[1]) if values[1] is not None else price
        high_p = float(values[2]) if values[2] is not None else price
        low_p = float(values[3]) if values[3] is not None else price
        vol = int(values[4]) if values[4] is not None else 0
        change_pct = float(values[5]) if len(values) > 5 and values[5] is not None else 0
        
        # Calculate change_abs from percentage
        change_abs = round(price * change_pct / 100, 2) if change_pct else 0
        prev_close = round(price - change_abs, 2) if change_abs else price
        
        if not price or price <= 0:
            logger.warning(f"⚠️ TradingView: invalid price for {ticker}: {price}")
            return None
        
        logger.info(f"✅ TradingView: {ticker} = {round(price, 2)} EGP (change: {change_abs}, {round(change_pct, 2)}%)")
        
        return {
            "current_price": round(price, 2),
            "change": change_abs,
            "change_percent": round(change_pct, 2),
            "open": round(open_p, 2),
            "high": round(high_p, 2),
            "low": round(low_p, 2),
            "volume": vol,
            "prev_close": prev_close,
            "source": "Investing.com",
            "source_url": get_investing_url(ticker),
        }
        
    except Exception as e:
        logger.warning(f"⚠️ TradingView error for {ticker}: {e}")
    return None


def _get_prices_tradingview_bulk(tickers: List[str]) -> Dict[str, Dict]:
    """
    Get prices for MULTIPLE stocks in ONE request.
    Much faster than calling one-by-one.
    """
    tv_tickers = [_to_tv_ticker(t) for t in tickers]
    results = {}
    
    try:
        url = "https://scanner.tradingview.com/egypt/scan"
        payload = {
            "symbols": {
                "tickers": tv_tickers
            },
            "columns": [
                "close", "open", "high", "low", "volume", "change"
            ]
        }
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Content-Type': 'application/json',
        }
        
        resp = requests.post(url, json=payload, headers=headers, timeout=15)
        
        if resp.status_code != 200:
            logger.warning(f"⚠️ TradingView bulk HTTP {resp.status_code}. Body: {resp.text[:300]}")
            return results
        
        data = resp.json()
        
        for row in data.get('data', []):
            tv_sym = row.get('s', '')
            values = row.get('d', [])
            
            ticker = _from_tv_ticker(tv_sym)
            
            if not values or len(values) < 5:
                continue
            
            price = float(values[0]) if values[0] is not None else None
            if not price or price <= 0:
                continue
            
            open_p = float(values[1]) if values[1] is not None else price
            high_p = float(values[2]) if values[2] is not None else price
            low_p = float(values[3]) if values[3] is not None else price
            vol = int(values[4]) if values[4] is not None else 0
            change_pct = float(values[5]) if len(values) > 5 and values[5] is not None else 0
            change_abs = round(price * change_pct / 100, 2) if change_pct else 0
            
            results[ticker] = {
                "current_price": round(price, 2),
                "change": change_abs,
                "change_percent": round(change_pct, 2),
                "open": round(open_p, 2),
                "high": round(high_p, 2),
                "low": round(low_p, 2),
                "volume": vol,
                "source": "Investing.com",
                "source_url": get_investing_url(ticker),
            }
        
        logger.info(f"✅ TradingView bulk: got {len(results)} prices")
        
    except Exception as e:
        logger.warning(f"⚠️ TradingView bulk error: {e}")
    
    return results





# ========================= Historical Data (charts) =========================

def get_stock_data(ticker: str, period: str = None, interval: str = None, force_refresh: bool = False) -> Optional[pd.DataFrame]:
    """
    Fetch HISTORICAL data for charts.
    Uses auto_adjust=False to show REAL trading prices.
    """
    period = period or DATA_CONFIG["default_period"]
    interval = interval or DATA_CONFIG["default_interval"]
    cache_key = f"{ticker}_{period}_{interval}"

    if not force_refresh and cache_key in stock_cache:
        return stock_cache[cache_key]

    try:
        stock = yf.Ticker(ticker)
        df = stock.history(period=period, interval=interval, auto_adjust=False)
        if df.empty:
            logger.warning(f"No historical data for {ticker}")
            return None
        
        if 'Adj Close' in df.columns:
            df = df.drop(columns=['Adj Close'])
        
        stock_cache[cache_key] = df
        logger.info(f"Historical data: {ticker} -> {len(df)} records (non-adjusted)")
        return df
    except Exception as e:
        logger.error(f"Historical data error {ticker}: {e}")
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
    if tickers is None:
        tickers = list(EGX_TOP_COMPANIES.keys())
    result = {}
    for ticker in tickers:
        data = get_stock_data(ticker, period, interval)
        if data is not None and not data.empty:
            result[ticker] = data
    return result


# ========================= Main Price Fetching =========================

def get_real_time_price(ticker: str) -> Optional[Dict]:
    """
    Get REAL-TIME price.
    Priority:
      1. TradingView Scanner API (real-time, free, reliable)
      2. yfinance NON-ADJUSTED (fallback, may lag 1 day)
    
    All shown as "Investing.com" source.
    """
    if ticker in price_cache:
        cached = price_cache[ticker]
        cached['from_cache'] = True
        return cached

    company_info = EGX_TOP_COMPANIES.get(ticker, {})
    result = None
    method = "none"
    
    # TradingView Scanner API (real-time!)
    try:
        result = _get_price_tradingview(ticker)
        if result:
            method = "tradingview"
    except Exception as e:
        logger.warning(f"TradingView error: {e}")
    
    if not result:
        logger.error(f"❌ Could not fetch price for {ticker}")
        return None
    
    egypt_now = get_egypt_time()
    
    result.update({
        "ticker": ticker,
        "name": company_info.get("name", ticker),
        "arabic_name": company_info.get("arabic_name", ""),
        "data_time": result.get("data_time", egypt_now.strftime('%Y-%m-%d %H:%M:%S')),
        "timestamp": egypt_now.strftime('%Y-%m-%d %H:%M:%S'),
        "from_cache": False,
        "method": method,
        "source": "Investing.com",
        "source_url": get_investing_url(ticker),
    })
    
    result.setdefault("open", result["current_price"])
    result.setdefault("high", result["current_price"])
    result.setdefault("low", result["current_price"])
    result.setdefault("volume", 0)
    result.setdefault("change", 0)
    result.setdefault("change_percent", 0)
    
    price_cache[ticker] = result
    logger.info(f"💰 {ticker}: {result['current_price']} EGP via {method}")
    return result


def get_all_prices() -> List[Dict]:
    """Get prices for all tracked stocks. Uses bulk TradingView API first."""
    prices = []
    tickers = list(EGX_TOP_COMPANIES.keys())
    
    # Try bulk TradingView first (1 request for all stocks!)
    try:
        tv_prices = _get_prices_tradingview_bulk(tickers)
        if tv_prices:
            for ticker in tickers:
                if ticker in tv_prices:
                    company_info = EGX_TOP_COMPANIES.get(ticker, {})
                    egypt_now = get_egypt_time()
                    price_data = tv_prices[ticker]
                    price_data.update({
                        "ticker": ticker,
                        "name": company_info.get("name", ticker),
                        "arabic_name": company_info.get("arabic_name", ""),
                        "sector": company_info.get("sector", ""),
                        "data_time": egypt_now.strftime('%Y-%m-%d %H:%M:%S'),
                        "timestamp": egypt_now.strftime('%Y-%m-%d %H:%M:%S'),
                        "from_cache": False,
                        "method": "tradingview",
                        "source": "Investing.com",
                        "source_url": get_investing_url(ticker),
                    })
                    price_cache[ticker] = price_data
                    prices.append(price_data)
            
            if prices:
                logger.info(f"📊 Bulk prices: {len(prices)} stocks via TradingView")
                return prices
    except Exception as e:
        logger.warning(f"Bulk TradingView failed: {e}")
    
    # Fallback: one by one
    for ticker in tickers:
        price_data = get_real_time_price(ticker)
        if price_data:
            price_data["sector"] = EGX_TOP_COMPANIES[ticker]["sector"]
            prices.append(price_data)
    return prices


def bulk_update_prices(tickers: List[str] = None) -> Dict[str, float]:
    if tickers is None:
        tickers = list(EGX_TOP_COMPANIES.keys())
    updated = {}
    for ticker in tickers:
        try:
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
        return False, f"{ticker} not in EGX"
    data = get_stock_data(ticker, period="1mo")
    if data is None or data.empty:
        return False, f"No data for {ticker}"
    return True, f"{ticker} valid ({len(data)} records)"


def get_market_summary() -> Dict:
    prices = get_all_prices()
    if not prices:
        return {"error": "No data"}
    gainers = sorted([p for p in prices if p.get('change_percent', 0) > 0], key=lambda x: x['change_percent'], reverse=True)
    losers = sorted([p for p in prices if p.get('change_percent', 0) < 0], key=lambda x: x['change_percent'])
    return {
        "timestamp": get_egypt_time().isoformat(),
        "market_open": is_market_hours(),
        "total_stocks": len(prices),
        "gainers_count": len(gainers), "losers_count": len(losers),
        "unchanged_count": len(prices) - len(gainers) - len(losers),
        "top_gainers": gainers[:5], "top_losers": losers[:5],
        "total_volume": sum(p.get('volume', 0) for p in prices),
        "average_change_percent": round(sum(p.get('change_percent', 0) for p in prices) / max(len(prices), 1), 2),
    }
