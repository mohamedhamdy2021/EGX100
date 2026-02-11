"""
Quick Start Script for EGX Trading Bot
Run this to start the trading bot server
"""

import subprocess
import sys
import os

def install_requirements():
    """Install required packages"""
    print("📦 جاري تثبيت المتطلبات...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt", "-q"])
    print("✅ تم تثبيت المتطلبات بنجاح!")

def run_server():
    """Run the Flask server"""
    print("""
    ╔═══════════════════════════════════════════════════════════════╗
    ║           EGX100 Trading Advisory Bot 📈                      ║
    ║                                                               ║
    ║   بوت نصائح التداول للبورصة المصرية                           ║
    ║   يقدم توصيات بناءً على التحليل الفني                         ║
    ║                                                               ║
    ║   🌐 افتح المتصفح على: http://localhost:5000                  ║
    ║                                                               ║
    ║   ⚠️ تحذير: هذا البوت تعليمي فقط وليس نصيحة مالية            ║
    ╚═══════════════════════════════════════════════════════════════╝
    """)
    
    from app import app, socketio
    from config import SERVER_CONFIG
    
    socketio.run(
        app,
        host=SERVER_CONFIG["host"],
        port=SERVER_CONFIG["port"],
        debug=SERVER_CONFIG["debug"]
    )

if __name__ == "__main__":
    # Change to script directory
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    
    # Check if requirements are installed
    try:
        import flask
        import yfinance
        import ta
        import plotly
    except ImportError:
        install_requirements()
    
    # Run server
    run_server()
