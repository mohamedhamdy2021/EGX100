"""
Technical Analysis Module
Implements various technical indicators for trading signals
"""

import pandas as pd
import numpy as np
from ta import trend, momentum, volatility, volume
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from enum import Enum
from config import STRATEGY_CONFIG

class SignalType(Enum):
    STRONG_BUY = "شراء قوي"
    BUY = "شراء"
    HOLD = "احتفظ"
    SELL = "بيع"
    STRONG_SELL = "بيع قوي"


@dataclass
class TradingSignal:
    """Represents a trading signal with all relevant information"""
    ticker: str
    signal_type: SignalType
    confidence: float  # 0-100
    price: float
    entry_price: float
    stop_loss: float
    take_profit: float
    reasons: List[str]  # Arabic explanations
    indicators: Dict  # All indicator values
    timestamp: str


def calculate_rsi(df: pd.DataFrame, period: int = None) -> pd.Series:
    """Calculate Relative Strength Index"""
    period = period or STRATEGY_CONFIG["rsi_period"]
    return momentum.RSIIndicator(df['Close'], window=period).rsi()


def calculate_macd(df: pd.DataFrame) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """Calculate MACD, Signal Line, and Histogram"""
    macd_indicator = trend.MACD(
        df['Close'],
        window_slow=STRATEGY_CONFIG["macd_slow"],
        window_fast=STRATEGY_CONFIG["macd_fast"],
        window_sign=STRATEGY_CONFIG["macd_signal"]
    )
    return (
        macd_indicator.macd(),
        macd_indicator.macd_signal(),
        macd_indicator.macd_diff()
    )


def calculate_bollinger_bands(df: pd.DataFrame) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """Calculate Bollinger Bands (upper, middle, lower)"""
    bb = volatility.BollingerBands(
        df['Close'],
        window=STRATEGY_CONFIG["bb_period"],
        window_dev=STRATEGY_CONFIG["bb_std"]
    )
    return bb.bollinger_hband(), bb.bollinger_mavg(), bb.bollinger_lband()


def calculate_sma(df: pd.DataFrame, short: int = None, long: int = None) -> Tuple[pd.Series, pd.Series]:
    """Calculate Simple Moving Averages"""
    short = short or STRATEGY_CONFIG["sma_short"]
    long = long or STRATEGY_CONFIG["sma_long"]
    return df['Close'].rolling(window=short).mean(), df['Close'].rolling(window=long).mean()


def calculate_ema(df: pd.DataFrame, short: int = None, long: int = None) -> Tuple[pd.Series, pd.Series]:
    """Calculate Exponential Moving Averages"""
    short = short or STRATEGY_CONFIG["ema_short"]
    long = long or STRATEGY_CONFIG["ema_long"]
    return df['Close'].ewm(span=short).mean(), df['Close'].ewm(span=long).mean()


def calculate_volume_analysis(df: pd.DataFrame) -> Dict:
    """Analyze volume patterns"""
    volume_ma = df['Volume'].rolling(window=STRATEGY_CONFIG["volume_ma_period"]).mean()
    current_volume = df['Volume'].iloc[-1]
    avg_volume = volume_ma.iloc[-1]
    
    volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1
    is_volume_spike = volume_ratio > STRATEGY_CONFIG["volume_spike_threshold"]
    
    return {
        "current_volume": int(current_volume),
        "average_volume": int(avg_volume),
        "volume_ratio": round(volume_ratio, 2),
        "is_volume_spike": bool(is_volume_spike),
    }


def calculate_all_indicators(df: pd.DataFrame) -> Dict:
    """
    Calculate all technical indicators for a stock
    
    Args:
        df: DataFrame with OHLCV data
        
    Returns:
        Dictionary with all indicator values
    """
    if df is None or len(df) < STRATEGY_CONFIG["sma_long"]:
        return None
    
    # RSI
    rsi = calculate_rsi(df)
    
    # MACD
    macd, macd_signal, macd_histogram = calculate_macd(df)
    
    # Bollinger Bands
    bb_upper, bb_middle, bb_lower = calculate_bollinger_bands(df)
    
    # Moving Averages
    sma_short, sma_long = calculate_sma(df)
    ema_short, ema_long = calculate_ema(df)
    
    # Volume
    volume_data = calculate_volume_analysis(df)
    
    # Get latest values
    current_price = df['Close'].iloc[-1]
    
    return {
        "price": {
            "current": round(current_price, 2),
            "open": round(df['Open'].iloc[-1], 2),
            "high": round(df['High'].iloc[-1], 2),
            "low": round(df['Low'].iloc[-1], 2),
            "previous_close": round(df['Close'].iloc[-2], 2) if len(df) > 1 else current_price,
        },
        "rsi": {
            "value": round(rsi.iloc[-1], 2) if not pd.isna(rsi.iloc[-1]) else 50,
            "overbought": STRATEGY_CONFIG["rsi_overbought"],
            "oversold": STRATEGY_CONFIG["rsi_oversold"],
            "status": "ذروة شراء" if rsi.iloc[-1] > STRATEGY_CONFIG["rsi_overbought"] 
                     else "ذروة بيع" if rsi.iloc[-1] < STRATEGY_CONFIG["rsi_oversold"]
                     else "محايد"
        },
        "macd": {
            "macd": round(macd.iloc[-1], 4) if not pd.isna(macd.iloc[-1]) else 0,
            "signal": round(macd_signal.iloc[-1], 4) if not pd.isna(macd_signal.iloc[-1]) else 0,
            "histogram": round(macd_histogram.iloc[-1], 4) if not pd.isna(macd_histogram.iloc[-1]) else 0,
            "trend": "صاعد" if macd.iloc[-1] > macd_signal.iloc[-1] else "هابط"
        },
        "bollinger_bands": {
            "upper": round(bb_upper.iloc[-1], 2) if not pd.isna(bb_upper.iloc[-1]) else current_price * 1.02,
            "middle": round(bb_middle.iloc[-1], 2) if not pd.isna(bb_middle.iloc[-1]) else current_price,
            "lower": round(bb_lower.iloc[-1], 2) if not pd.isna(bb_lower.iloc[-1]) else current_price * 0.98,
            "position": "فوق" if current_price > bb_upper.iloc[-1] 
                       else "تحت" if current_price < bb_lower.iloc[-1]
                       else "وسط"
        },
        "moving_averages": {
            "sma_short": round(sma_short.iloc[-1], 2) if not pd.isna(sma_short.iloc[-1]) else current_price,
            "sma_long": round(sma_long.iloc[-1], 2) if not pd.isna(sma_long.iloc[-1]) else current_price,
            "ema_short": round(ema_short.iloc[-1], 2) if not pd.isna(ema_short.iloc[-1]) else current_price,
            "ema_long": round(ema_long.iloc[-1], 2) if not pd.isna(ema_long.iloc[-1]) else current_price,
            "sma_trend": "صاعد" if sma_short.iloc[-1] > sma_long.iloc[-1] else "هابط",
            "ema_trend": "صاعد" if ema_short.iloc[-1] > ema_long.iloc[-1] else "هابط",
            "price_above_sma20": bool(current_price > sma_short.iloc[-1]),
            "price_above_sma50": bool(current_price > sma_long.iloc[-1]),
        },
        "volume": volume_data,
    }


def generate_trading_signal(ticker: str, df: pd.DataFrame, company_info: Dict = None) -> Optional[TradingSignal]:
    """
    Generate a trading signal based on technical analysis
    
    Args:
        ticker: Stock ticker
        df: DataFrame with OHLCV data
        company_info: Additional company information
        
    Returns:
        TradingSignal object with recommendation
    """
    indicators = calculate_all_indicators(df)
    
    if indicators is None:
        return None
    
    # Scoring system
    buy_score = 0
    sell_score = 0
    reasons = []
    
    current_price = indicators["price"]["current"]
    
    # RSI Analysis (weight: 20%)
    rsi_value = indicators["rsi"]["value"]
    if rsi_value < STRATEGY_CONFIG["rsi_oversold"]:
        buy_score += 20
        reasons.append(f"📊 RSI ({rsi_value:.1f}) في منطقة ذروة البيع - فرصة شراء")
    elif rsi_value > STRATEGY_CONFIG["rsi_overbought"]:
        sell_score += 20
        reasons.append(f"📊 RSI ({rsi_value:.1f}) في منطقة ذروة الشراء - فرصة بيع")
    elif rsi_value < 45:
        buy_score += 10
        reasons.append(f"📊 RSI ({rsi_value:.1f}) يميل للانخفاض")
    elif rsi_value > 55:
        sell_score += 10
        reasons.append(f"📊 RSI ({rsi_value:.1f}) يميل للارتفاع")
    
    # MACD Analysis (weight: 25%)
    macd_trend = indicators["macd"]["trend"]
    histogram = indicators["macd"]["histogram"]
    if macd_trend == "صاعد":
        buy_score += 15
        reasons.append("📈 MACD يعطي إشارة صاعدة")
        if histogram > 0:
            buy_score += 10
            reasons.append("📈 الهيستوجرام موجب - تأكيد للاتجاه الصاعد")
    else:
        sell_score += 15
        reasons.append("📉 MACD يعطي إشارة هابطة")
        if histogram < 0:
            sell_score += 10
            reasons.append("📉 الهيستوجرام سالب - تأكيد للاتجاه الهابط")
    
    # Bollinger Bands Analysis (weight: 15%)
    bb_position = indicators["bollinger_bands"]["position"]
    bb_lower = indicators["bollinger_bands"]["lower"]
    bb_upper = indicators["bollinger_bands"]["upper"]
    if bb_position == "تحت":
        buy_score += 15
        reasons.append(f"📉 السعر ({current_price:.2f}) تحت الحد السفلي للبولينجر ({bb_lower:.2f}) - فرصة ارتداد")
    elif bb_position == "فوق":
        sell_score += 15
        reasons.append(f"📈 السعر ({current_price:.2f}) فوق الحد العلوي للبولينجر ({bb_upper:.2f}) - احتمال تصحيح")
    
    # Moving Averages Analysis (weight: 25%)
    sma_trend = indicators["moving_averages"]["sma_trend"]
    ema_trend = indicators["moving_averages"]["ema_trend"]
    price_above_sma20 = indicators["moving_averages"]["price_above_sma20"]
    price_above_sma50 = indicators["moving_averages"]["price_above_sma50"]
    
    if sma_trend == "صاعد" and ema_trend == "صاعد":
        buy_score += 15
        reasons.append("📈 المتوسطات المتحركة تشير لاتجاه صاعد قوي")
    elif sma_trend == "هابط" and ema_trend == "هابط":
        sell_score += 15
        reasons.append("📉 المتوسطات المتحركة تشير لاتجاه هابط قوي")
    
    if price_above_sma20 and price_above_sma50:
        buy_score += 10
        reasons.append("📈 السعر فوق المتوسطات المتحركة 20 و 50")
    elif not price_above_sma20 and not price_above_sma50:
        sell_score += 10
        reasons.append("📉 السعر تحت المتوسطات المتحركة 20 و 50")
    
    # Volume Analysis (weight: 15%)
    volume_data = indicators["volume"]
    if volume_data["is_volume_spike"]:
        if buy_score > sell_score:
            buy_score += 15
            reasons.append(f"📊 حجم تداول مرتفع ({volume_data['volume_ratio']:.1f}x) - تأكيد للشراء")
        else:
            sell_score += 15
            reasons.append(f"📊 حجم تداول مرتفع ({volume_data['volume_ratio']:.1f}x) - تأكيد للبيع")
    
    # Calculate confidence and signal
    total_score = buy_score + sell_score
    if total_score == 0:
        confidence = 50
        signal_type = SignalType.HOLD
        reasons.append("⚖️ لا توجد إشارة واضحة - ننصح بالانتظار")
    else:
        if buy_score > sell_score:
            confidence = (buy_score / total_score) * 100
            if confidence >= 75:
                signal_type = SignalType.STRONG_BUY
            elif confidence >= 55:
                signal_type = SignalType.BUY
            else:
                signal_type = SignalType.HOLD
        else:
            confidence = (sell_score / total_score) * 100
            if confidence >= 75:
                signal_type = SignalType.STRONG_SELL
            elif confidence >= 55:
                signal_type = SignalType.SELL
            else:
                signal_type = SignalType.HOLD
    
    # Calculate entry, stop loss, and take profit
    stop_loss_percent = STRATEGY_CONFIG["stop_loss_percent"] / 100
    take_profit_percent = STRATEGY_CONFIG["take_profit_percent"] / 100
    
    if signal_type in [SignalType.BUY, SignalType.STRONG_BUY]:
        entry_price = current_price
        stop_loss = current_price * (1 - stop_loss_percent)
        take_profit = current_price * (1 + take_profit_percent)
    elif signal_type in [SignalType.SELL, SignalType.STRONG_SELL]:
        entry_price = current_price
        stop_loss = current_price * (1 + stop_loss_percent)
        take_profit = current_price * (1 - take_profit_percent)
    else:
        entry_price = current_price
        stop_loss = current_price * (1 - stop_loss_percent)
        take_profit = current_price * (1 + take_profit_percent)
    
    from datetime import datetime
    
    return TradingSignal(
        ticker=ticker,
        signal_type=signal_type,
        confidence=round(confidence, 1),
        price=current_price,
        entry_price=round(entry_price, 2),
        stop_loss=round(stop_loss, 2),
        take_profit=round(take_profit, 2),
        reasons=reasons,
        indicators=indicators,
        timestamp=datetime.now().isoformat()
    )


def scan_all_stocks(stocks_data: Dict[str, pd.DataFrame]) -> List[TradingSignal]:
    """
    Scan all stocks and generate signals
    
    Args:
        stocks_data: Dictionary mapping tickers to DataFrames
        
    Returns:
        List of TradingSignal objects sorted by confidence
    """
    signals = []
    
    for ticker, df in stocks_data.items():
        signal = generate_trading_signal(ticker, df)
        if signal:
            signals.append(signal)
    
    # Sort by confidence (highest first)
    signals.sort(key=lambda x: x.confidence, reverse=True)
    
    return signals


def get_buy_signals(signals: List[TradingSignal], min_confidence: float = None) -> List[TradingSignal]:
    """Get only buy signals above minimum confidence"""
    min_conf = min_confidence or STRATEGY_CONFIG["min_confidence_buy"]
    return [
        s for s in signals 
        if s.signal_type in [SignalType.BUY, SignalType.STRONG_BUY] 
        and s.confidence >= min_conf
    ]


def get_sell_signals(signals: List[TradingSignal], min_confidence: float = None) -> List[TradingSignal]:
    """Get only sell signals above minimum confidence"""
    min_conf = min_confidence or STRATEGY_CONFIG["min_confidence_sell"]
    return [
        s for s in signals 
        if s.signal_type in [SignalType.SELL, SignalType.STRONG_SELL] 
        and s.confidence >= min_conf
    ]
