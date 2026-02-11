"""
EGX100 Trading Bot - Full Auto Trading
- Auto opens ALL qualifying trades on startup
- Updates prices every 60 seconds
- Scans for new signals every 5 minutes
- Real-time WebSocket updates to UI
"""

from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
from flask_socketio import SocketIO, emit
import json
from datetime import datetime
from dataclasses import asdict
import threading
import time
import logging

from config import EGX_TOP_COMPANIES, STRATEGY_CONFIG, SERVER_CONFIG, PLATFORM_RECOMMENDATION
from data_fetcher import get_stock_data, get_multiple_stocks_data, get_real_time_price, get_all_prices, get_market_summary, bulk_update_prices, is_market_hours, INVESTING_SLUGS, INVESTING_DOMAIN, get_investing_url
from technical_analysis import generate_trading_signal, scan_all_stocks, get_buy_signals, get_sell_signals, SignalType
from chart_generator import create_candlestick_chart
from paper_trading import paper_trading
from auto_settings import auto_settings, save_settings, load_settings

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s', datefmt='%H:%M:%S')
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'egx-trading-bot-2024'
CORS(app)

# Auto-detect async mode: gevent for production (Railway), threading for local dev
import os as _os
_async_mode = 'gevent' if _os.environ.get('PORT') or _os.environ.get('RAILWAY_ENVIRONMENT') else 'threading'
try:
    import gevent
    _async_mode = 'gevent'
except ImportError:
    _async_mode = 'threading'
logger.info(f"SocketIO async_mode: {_async_mode}")
socketio = SocketIO(app, cors_allowed_origins="*", async_mode=_async_mode)

# Track last scan results for the UI
last_scan_results = {"signals": [], "timestamp": None}

def signal_to_dict(signal):
    if signal is None: return None
    return {
        "ticker": signal.ticker, "signal_type": signal.signal_type.value, "confidence": signal.confidence,
        "price": signal.price, "entry_price": signal.entry_price, "stop_loss": signal.stop_loss,
        "take_profit": signal.take_profit, "reasons": signal.reasons, "indicators": signal.indicators,
        "timestamp": signal.timestamp,
        "company_name": EGX_TOP_COMPANIES.get(signal.ticker, {}).get("name", signal.ticker),
        "arabic_name": EGX_TOP_COMPANIES.get(signal.ticker, {}).get("arabic_name", ""),
        "sector": EGX_TOP_COMPANIES.get(signal.ticker, {}).get("sector", ""),
    }

def broadcast_update():
    """Push latest data to all connected clients"""
    try:
        socketio.emit('trades_update', {
            'trades': paper_trading.get_open_trades(),
            'portfolio': paper_trading.get_portfolio_stats(),
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Broadcast error: {e}")

# ==================== API Routes ====================
@app.route('/')
def index(): return render_template('index.html')

@app.route('/api/companies')
def get_companies():
    return jsonify({"status": "success", "companies": [{"ticker": t, **info} for t, info in EGX_TOP_COMPANIES.items()]})

@app.route('/api/market/summary')
def market_summary():
    return jsonify({"status": "success", "data": get_market_summary()})

@app.route('/api/stock/<ticker>')
def get_stock(ticker):
    ticker = ticker.upper()
    if not ticker.endswith('.CA'): ticker += '.CA'
    df = get_stock_data(ticker, period=request.args.get('period', '6mo'))
    if df is None: return jsonify({"status": "error", "message": f"No data for {ticker}"}), 404
    signal = generate_trading_signal(ticker, df)
    chart_json = create_candlestick_chart(df, ticker, EGX_TOP_COMPANIES.get(ticker, {}).get("name", ""))
    return jsonify({"status": "success", "ticker": ticker, "signal": signal_to_dict(signal), "chart": json.loads(chart_json)})

@app.route('/api/signals')
def get_all_signals():
    stocks_data = get_multiple_stocks_data()
    all_signals = scan_all_stocks(stocks_data)
    return jsonify({"status": "success", "signals": [signal_to_dict(s) for s in all_signals], "total": len(all_signals)})

@app.route('/api/signals/buy')
def get_buy_recommendations():
    stocks_data = get_multiple_stocks_data()
    buy_signals = get_buy_signals(scan_all_stocks(stocks_data))
    return jsonify({"status": "success", "signals": [signal_to_dict(s) for s in buy_signals], "total": len(buy_signals)})

@app.route('/api/signals/sell')
def get_sell_recommendations():
    stocks_data = get_multiple_stocks_data()
    sell_signals = get_sell_signals(scan_all_stocks(stocks_data))
    return jsonify({"status": "success", "signals": [signal_to_dict(s) for s in sell_signals], "total": len(sell_signals)})

@app.route('/api/test-price/<ticker>')
def test_price(ticker):
    """Debug endpoint to test price fetching"""
    ticker = ticker.upper()
    if not ticker.endswith('.CA'): ticker += '.CA'
    price_info = get_real_time_price(ticker)
    if price_info:
        return jsonify({
            "status": "success",
            "ticker": ticker,
            "price": price_info.get('current_price'),
            "source": price_info.get('source'),
            "method": price_info.get('method', 'unknown'),
            "change": price_info.get('change'),
            "change_percent": price_info.get('change_percent'),
            "data_time": price_info.get('data_time'),
            "from_cache": price_info.get('from_cache', False),
            "source_url": price_info.get('source_url'),
        })
    return jsonify({"status": "error", "message": f"Could not fetch price for {ticker}"}), 404

@app.route('/api/chart/<ticker>')
def get_chart(ticker):
    ticker = ticker.upper()
    if not ticker.endswith('.CA'): ticker += '.CA'
    df = get_stock_data(ticker, period=request.args.get('period', '6mo'))
    if df is None: return jsonify({"status": "error"}), 404
    
    # Get price from Investing.com
    price_info = get_real_time_price(ticker)
    company = EGX_TOP_COMPANIES.get(ticker, {})
    
    # Investing.com URL
    investing_url = get_investing_url(ticker)
    data_time = price_info.get('data_time', 'N/A') if price_info else 'N/A'
    
    stock_info = {
        "ticker": ticker,
        "name": company.get('name', ticker),
        "arabic_name": company.get('arabic_name', ''),
        "sector": company.get('sector', ''),
        "current_price": price_info.get('current_price') if price_info else None,
        "change": price_info.get('change', 0) if price_info else 0,
        "change_percent": price_info.get('change_percent', 0) if price_info else 0,
        "open": price_info.get('open') if price_info else None,
        "high": price_info.get('high') if price_info else None,
        "low": price_info.get('low') if price_info else None,
        "volume": price_info.get('volume', 0) if price_info else 0,
        "source": "Investing.com",
        "source_url": investing_url,
        "method": price_info.get('method', '') if price_info else '',
        "data_time": data_time + ' (توقيت مصر)' if data_time != 'N/A' else 'N/A',
        "timestamp": price_info.get('timestamp', '') if price_info else '',
        "market_open": is_market_hours(),
    }
    
    return jsonify({
        "status": "success", 
        "chart": json.loads(create_candlestick_chart(df, ticker, company.get("name", ""))),
        "stock_info": stock_info
    })

# ==================== Paper Trading API ====================
@app.route('/api/trades')
def get_trades():
    t = request.args.get('type', 'all')
    trades = paper_trading.get_open_trades() if t == 'open' else paper_trading.get_closed_trades() if t == 'closed' else paper_trading.get_all_trades()
    return jsonify({"status": "success", "trades": trades, "total": len(trades)})

@app.route('/api/trades/open')
def get_open_trades():
    return jsonify({"status": "success", "trades": paper_trading.get_open_trades(), "total": len(paper_trading.open_trades)})

@app.route('/api/trades/portfolio')
def get_portfolio():
    return jsonify({"status": "success", "portfolio": paper_trading.get_portfolio_stats()})

@app.route('/api/trades/open', methods=['POST'])
def open_new_trade():
    data = request.json
    ticker = data.get('ticker', '').upper()
    if not ticker.endswith('.CA'): ticker += '.CA'
    entry_price = data.get('entry_price') or (get_real_time_price(ticker) or {}).get('current_price')
    if not entry_price: return jsonify({"status": "error", "message": "No price"}), 400
    company_info = EGX_TOP_COMPANIES.get(ticker, {})
    trade = paper_trading.open_trade(ticker=ticker, company_name=company_info.get('name', ticker),
        arabic_name=company_info.get('arabic_name', ''), entry_price=entry_price,
        stop_loss=data.get('stop_loss', entry_price * 0.95), take_profit=data.get('take_profit', entry_price * 1.10),
        signal_confidence=data.get('confidence', 0), reasons=data.get('reasons', ['يدوي']),
        direction=data.get('direction', 'BUY'), investment_amount=data.get('amount', auto_settings['trade_amount']))
    if trade:
        broadcast_update()
        return jsonify({"status": "success", "trade": asdict(trade)})
    return jsonify({"status": "error", "message": "فشل - قد يكون هناك صفقة مفتوحة بالفعل"}), 400

@app.route('/api/trades/close/<ticker>', methods=['POST'])
def close_trade(ticker):
    ticker = ticker.upper()
    if not ticker.endswith('.CA'): ticker += '.CA'
    # Get exit price from body or from latest data
    body = request.get_json(silent=True) or {}
    exit_price = body.get('exit_price')
    if not exit_price:
        price_info = get_real_time_price(ticker)
        if price_info:
            exit_price = price_info['current_price']
        else:
            # Fallback to current_price stored in trade
            if ticker in paper_trading.open_trades:
                exit_price = paper_trading.open_trades[ticker].current_price
    if not exit_price:
        return jsonify({"status": "error", "message": "لا يمكن الحصول على السعر"}), 400
    trade = paper_trading.close_trade(ticker, exit_price, "MANUAL")
    if trade:
        broadcast_update()
        return jsonify({"status": "success", "trade": asdict(trade)})
    return jsonify({"status": "error", "message": "لا توجد صفقة مفتوحة"}), 404

@app.route('/api/trades/reset', methods=['POST'])
def reset_portfolio():
    body = request.get_json(silent=True) or {}
    
    # Disable auto-trading to prevent immediately reopening trades
    auto_settings['auto_trade_enabled'] = False
    save_settings(auto_settings)
    
    # Clear trade data
    paper_trading.reset_portfolio(body.get('initial_capital', 100000))
    
    # Clear scan results cache
    last_scan_results["signals"] = []
    last_scan_results["timestamp"] = None
    
    broadcast_update()
    logger.info("Portfolio reset! Auto-trading disabled.")
    return jsonify({
        "status": "success", 
        "message": "تم إعادة التعيين - التداول التلقائي معطل. فعّله يدوياً لبدء صفقات جديدة.",
        "portfolio": paper_trading.get_portfolio_stats()
    })

# ==================== Settings API ====================
@app.route('/api/settings')
def get_settings():
    return jsonify({"status": "success", "settings": auto_settings})

@app.route('/api/settings', methods=['POST'])
def update_settings():
    global auto_settings
    data = request.json
    for key in ['min_confidence', 'max_open_trades', 'trade_amount']:
        if key in data: auto_settings[key] = int(data[key])
    if 'auto_trade_enabled' in data: auto_settings['auto_trade_enabled'] = bool(data['auto_trade_enabled'])
    save_settings(auto_settings)
    logger.info(f"Settings updated: conf={auto_settings['min_confidence']}%, max={auto_settings['max_open_trades']}, amt={auto_settings['trade_amount']}")
    return jsonify({"status": "success", "settings": auto_settings})

# ==================== WebSocket ====================
@socketio.on('connect')
def handle_connect():
    emit('connected', {'message': 'متصل', 'settings': auto_settings})
    # Send current state immediately
    emit('trades_update', {
        'trades': paper_trading.get_open_trades(),
        'portfolio': paper_trading.get_portfolio_stats(),
        'timestamp': datetime.now().isoformat()
    })

@socketio.on('get_update')
def handle_get_update():
    emit('trades_update', {
        'trades': paper_trading.get_open_trades(),
        'portfolio': paper_trading.get_portfolio_stats(),
        'timestamp': datetime.now().isoformat()
    })

# ==================== Background Workers ====================

def worker_update_prices():
    """Update prices for all open trades every 60 seconds"""
    while True:
        time.sleep(60)
        try:
            open_tickers = list(paper_trading.open_trades.keys())
            if not open_tickers:
                continue
            
            updated_count = 0
            closed_count = 0
            for ticker in open_tickers:
                price_info = get_real_time_price(ticker)
                if price_info and 'current_price' in price_info:
                    result = paper_trading.update_trade_price(ticker, price_info['current_price'])
                    if result:
                        updated_count += 1
                        src = price_info.get('source', 'Unknown')
                        # Check if trade was auto-closed (SL/TP hit)
                        if result.status != "مفتوحة":
                            closed_count += 1
                            logger.info(f"Trade {ticker} auto-closed: {result.status} | PnL: {result.pnl}")
                        else:
                            logger.debug(f"  {ticker}: {result.current_price} (src: {src})")
            
            if updated_count > 0:
                broadcast_update()
                logger.info(f"Price update: {updated_count} trades updated, {closed_count} auto-closed")
        except Exception as e:
            logger.error(f"Price update error: {e}")


def worker_auto_trade():
    """Scan for signals and open trades automatically"""
    # Wait 30 seconds on startup to let data cache warm up
    time.sleep(30)
    
    while True:
        try:
            if not auto_settings.get('auto_trade_enabled', False):
                logger.info("Auto-trade disabled, skipping scan")
                time.sleep(300)
                continue
            
            # Only trade during EGX market hours (Sun-Thu, 10:00-14:30 Egypt time)
            if not is_market_hours():
                logger.info("Market closed - skipping auto-trade scan")
                time.sleep(300)
                continue
            
            current_open = len(paper_trading.open_trades)
            max_trades = auto_settings.get('max_open_trades', 100)
            
            if current_open >= max_trades:
                logger.info(f"Max trades reached ({current_open}/{max_trades}), skipping")
                time.sleep(300)
                continue
            
            logger.info(f"Scanning for signals... (open: {current_open}/{max_trades})")
            
            # Fetch all stock data
            stocks_data = get_multiple_stocks_data()
            logger.info(f"Fetched data for {len(stocks_data)} stocks")
            
            # Generate signals
            all_signals = scan_all_stocks(stocks_data)
            min_conf = auto_settings.get('min_confidence', 65)
            
            # Get buy signals above threshold
            buy_signals = [s for s in all_signals 
                          if s.signal_type in [SignalType.BUY, SignalType.STRONG_BUY] 
                          and s.confidence >= min_conf]
            
            logger.info(f"Found {len(buy_signals)} buy signals >= {min_conf}% confidence")
            
            # Build cooldown set: tickers closed in last 24 hours
            cooldown_hours = 24
            cooldown_tickers = set()
            now = datetime.now()
            for trade in paper_trading.trades:
                if trade.status != "مفتوحة" and trade.exit_time:
                    try:
                        closed_time = datetime.fromisoformat(trade.exit_time)
                        hours_since = (now - closed_time).total_seconds() / 3600
                        if hours_since < cooldown_hours:
                            cooldown_tickers.add(trade.ticker)
                    except:
                        pass
            
            if cooldown_tickers:
                logger.info(f"Cooldown tickers (closed <{cooldown_hours}h): {cooldown_tickers}")
            
            # Open trades for qualifying signals
            opened = 0
            skipped_existing = 0
            skipped_cooldown = 0
            skipped_max = 0
            
            for signal in buy_signals:
                # Check max trades limit
                if len(paper_trading.open_trades) >= max_trades:
                    skipped_max += len(buy_signals) - opened - skipped_existing - skipped_cooldown
                    break
                
                # Skip if already have this trade open
                if signal.ticker in paper_trading.open_trades:
                    skipped_existing += 1
                    continue
                
                # Skip if ticker is in cooldown (recently closed)
                if signal.ticker in cooldown_tickers:
                    skipped_cooldown += 1
                    continue
                
                company_info = EGX_TOP_COMPANIES.get(signal.ticker, {})
                trade = paper_trading.open_trade(
                    ticker=signal.ticker,
                    company_name=company_info.get('name', signal.ticker),
                    arabic_name=company_info.get('arabic_name', ''),
                    entry_price=signal.price,
                    stop_loss=signal.stop_loss,
                    take_profit=signal.take_profit,
                    signal_confidence=signal.confidence,
                    reasons=signal.reasons,
                    direction="BUY",
                    investment_amount=auto_settings.get('trade_amount', 1000)
                )
                
                if trade:
                    opened += 1
                    logger.info(f"  Opened: {signal.ticker} @ {signal.price} (conf: {signal.confidence}%)")
                    socketio.emit('new_trade', {'trade': asdict(trade)})
            
            logger.info(f"Auto-trade result: opened={opened}, skipped_existing={skipped_existing}, skipped_cooldown={skipped_cooldown}, skipped_max={skipped_max}")
            
            if opened > 0:
                broadcast_update()
            
            # Store last scan results
            last_scan_results["signals"] = [signal_to_dict(s) for s in all_signals]
            last_scan_results["timestamp"] = datetime.now().isoformat()
            
        except Exception as e:
            logger.error(f"Auto-trade error: {e}", exc_info=True)
        
        time.sleep(300)  # Scan every 5 minutes


@app.errorhandler(404)
def not_found(e): return jsonify({"status": "error", "message": "Not found"}), 404

@app.errorhandler(500)
def server_error(e): return jsonify({"status": "error", "message": "Server error"}), 500


# Start background workers (works both with direct run and gunicorn)
import os as _os
_workers_started = False

def start_workers():
    global _workers_started
    if _workers_started:
        return
    _workers_started = True
    threading.Thread(target=worker_update_prices, daemon=True, name="PriceUpdater").start()
    threading.Thread(target=worker_auto_trade, daemon=True, name="AutoTrader").start()
    logger.info("Background workers started")

# Start workers when imported by gunicorn
start_workers()


if __name__ == '__main__':
    port = int(_os.environ.get('PORT', SERVER_CONFIG["port"]))
    
    print(f"""
    ╔═══════════════════════════════════════════════════════════════════╗
    ║           EGX100 Auto Trading Bot 📈🤖                            ║
    ║                                                                   ║
    ║   🌐 http://localhost:{port}                                        ║
    ║   ⚙️  Min Confidence: {auto_settings['min_confidence']}%                                    ║
    ║   📊 Max Trades: {auto_settings['max_open_trades']}                                         ║
    ║   💰 Per Trade: {auto_settings['trade_amount']} EGP                                       ║
    ║   🤖 Auto-Trade: {'ON ✓' if auto_settings['auto_trade_enabled'] else 'OFF ✗'}                                          ║
    ║                                                                   ║
    ║   🔄 Price updates: every 60 sec                                  ║
    ║   🔍 Signal scan: every 5 min                                     ║
    ║   📡 First scan: 10 sec after start                               ║
    ╚═══════════════════════════════════════════════════════════════════╝
    """)
    
    socketio.run(app, host="0.0.0.0", port=port, debug=False)
