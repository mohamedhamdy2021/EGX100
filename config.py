"""
Configuration for EGX100 Trading Bot
Updated with correct Yahoo Finance tickers
"""

# Top EGX100 Companies with their Yahoo Finance tickers
# Note: Egyptian stocks on Yahoo Finance use .CA suffix
EGX_TOP_COMPANIES = {
    # Banking & Financial Services
    "COMI.CA": {"name": "Commercial International Bank (CIB)", "sector": "Banking", "arabic_name": "البنك التجاري الدولي"},
    "HDBK.CA": {"name": "Housing & Development Bank", "sector": "Banking", "arabic_name": "بنك التعمير والإسكان"},
    "CIEB.CA": {"name": "Credit Agricole Egypt", "sector": "Banking", "arabic_name": "كريدي أجريكول مصر"},
    "ADIB.CA": {"name": "Abu Dhabi Islamic Bank Egypt", "sector": "Banking", "arabic_name": "مصرف أبوظبي الإسلامي مصر"},
    "EXPA.CA": {"name": "Export Development Bank", "sector": "Banking", "arabic_name": "البنك المصري لتنمية الصادرات"},
    "EFIH.CA": {"name": "E-Finance", "sector": "FinTech", "arabic_name": "إي فاينانس"},
    "HRHO.CA": {"name": "EFG Holding", "sector": "Financial Services", "arabic_name": "إي إف جي القابضة"},
    "FWRY.CA": {"name": "Fawry", "sector": "FinTech", "arabic_name": "فوري"},
    
    # Real Estate & Construction
    "TMGH.CA": {"name": "Talaat Moustafa Group", "sector": "Real Estate", "arabic_name": "طلعت مصطفى القابضة"},
    "PHDC.CA": {"name": "Palm Hills Development", "sector": "Real Estate", "arabic_name": "بالم هيلز للتعمير"},
    "EMFD.CA": {"name": "Emaar Misr", "sector": "Real Estate", "arabic_name": "إعمار مصر"},
    "OCDI.CA": {"name": "Orascom Development", "sector": "Real Estate", "arabic_name": "أوراسكوم للتنمية"},
    "HELI.CA": {"name": "Heliopolis Housing", "sector": "Real Estate", "arabic_name": "مصر الجديدة للإسكان"},
    
    # Industrial & Manufacturing
    "SWDY.CA": {"name": "Elsewedy Electric", "sector": "Industrial", "arabic_name": "السويدي إليكتريك"},
    "ORWE.CA": {"name": "Oriental Weavers", "sector": "Textiles", "arabic_name": "السجاد الشرقية"},
    
    # Food & Beverages
    "JUFO.CA": {"name": "Juhayna Food Industries", "sector": "Food & Beverages", "arabic_name": "جهينة للصناعات الغذائية"},
    "EAST.CA": {"name": "Eastern Company", "sector": "Tobacco", "arabic_name": "الشرقية للدخان"},
    "EFID.CA": {"name": "Edita Food Industries", "sector": "Food & Beverages", "arabic_name": "إيديتا للصناعات الغذائية"},
    
    # Telecommunications
    "ETEL.CA": {"name": "Telecom Egypt", "sector": "Telecommunications", "arabic_name": "المصرية للاتصالات"},
    
    # Petrochemicals & Chemicals
    "SKPC.CA": {"name": "Sidi Kerir Petrochemicals", "sector": "Petrochemicals", "arabic_name": "سيدي كرير للبتروكيماويات"},
    "ABUK.CA": {"name": "Abu Qir Fertilizers", "sector": "Fertilizers", "arabic_name": "أبوقير للأسمدة"},
    "AMOC.CA": {"name": "Alexandria Mineral Oils", "sector": "Petrochemicals", "arabic_name": "زيوت الإسكندرية المعدنية"},
    
    # Pharmaceuticals & Healthcare
    "ISPH.CA": {"name": "Ibnsina Pharma", "sector": "Pharmaceuticals", "arabic_name": "ابن سينا فارما"},
    
    # Building Materials
    "ARCC.CA": {"name": "Arabian Cement", "sector": "Cement", "arabic_name": "العربية للأسمنت"},
    "SVCE.CA": {"name": "South Valley Cement", "sector": "Cement", "arabic_name": "جنوب الوادى للأسمنت"},
}

# Trading Strategy Parameters
STRATEGY_CONFIG = {
    # Technical Indicators Settings
    "rsi_period": 14,
    "rsi_overbought": 70,
    "rsi_oversold": 30,
    
    "macd_fast": 12,
    "macd_slow": 26,
    "macd_signal": 9,
    
    "bb_period": 20,
    "bb_std": 2,
    
    "sma_short": 20,
    "sma_long": 50,
    
    "ema_short": 12,
    "ema_long": 26,
    
    # Volume Analysis
    "volume_ma_period": 20,
    "volume_spike_threshold": 1.5,  # 150% of average volume
    
    # Signal Confidence Thresholds
    "min_confidence_buy": 60,  # Minimum confidence % for buy signal
    "min_confidence_sell": 60,  # Minimum confidence % for sell signal
    
    # Risk Management
    "stop_loss_percent": 5,  # 5% stop loss
    "take_profit_percent": 10,  # 10% take profit
    "max_position_size_percent": 10,  # Maximum 10% of portfolio per position
}

# Data Fetching Settings
DATA_CONFIG = {
    "default_period": "6mo",  # Default historical data period
    "default_interval": "1d",  # Daily data
    "cache_timeout_minutes": 15,  # Cache stock data for 15 minutes
}

# Server Configuration
SERVER_CONFIG = {
    "host": "0.0.0.0",
    "port": 5000,
    "debug": True,
}

# Trading Platform Recommendation
PLATFORM_RECOMMENDATION = {
    "recommended": "Thndr",
    "reasons": [
        "رسوم تداول أقل",
        "واجهة مستخدم سهلة ومناسبة للمبتدئين",
        "تطبيق موبايل ممتاز",
        "دعم طرق إيداع متعددة (انستاباي، فودافون كاش، فوري)",
        "فتح حساب سريع في نفس اليوم",
    ],
    "alternatives": ["EFG Hermes ONE", "EFG Hermes Pro"],
}
