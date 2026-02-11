"""
Auto Trading Configuration - Saved on server
"""
import json
import os

SETTINGS_FILE = "auto_settings.json"

DEFAULT_SETTINGS = {
    "auto_trade_enabled": True,
    "min_confidence": 65,
    "max_open_trades": 100,
    "trade_amount": 1000,
    "update_interval_seconds": 60,  # Update prices every minute
    "scan_interval_seconds": 300,   # Scan for new signals every 5 minutes
}

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, 'r') as f:
                return {**DEFAULT_SETTINGS, **json.load(f)}
        except:
            pass
    return DEFAULT_SETTINGS.copy()

def save_settings(settings):
    with open(SETTINGS_FILE, 'w') as f:
        json.dump(settings, f, indent=2)
    return settings

# Global settings instance
auto_settings = load_settings()
