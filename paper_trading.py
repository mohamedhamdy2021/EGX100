"""
Paper Trading System - نظام التداول الافتراضي
Tracks virtual trades to evaluate strategy performance
"""

import json
import os
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
from enum import Enum
import threading
import time

# File to persist trades
TRADES_FILE = "trades_history.json"
PORTFOLIO_FILE = "portfolio.json"

class TradeStatus(Enum):
    OPEN = "مفتوحة"
    CLOSED_PROFIT = "مغلقة بربح"
    CLOSED_LOSS = "مغلقة بخسارة"
    CLOSED_MANUAL = "مغلقة يدوياً"

class TradeDirection(Enum):
    BUY = "شراء"
    SELL = "بيع"

@dataclass
class Trade:
    """Represents a virtual trade"""
    id: str
    ticker: str
    company_name: str
    arabic_name: str
    direction: str  # BUY or SELL
    entry_price: float
    current_price: float
    stop_loss: float
    take_profit: float
    quantity: int
    investment_amount: float  # Amount in EGP
    entry_time: str
    exit_time: Optional[str]
    exit_price: Optional[float]
    status: str  # OPEN, CLOSED_PROFIT, CLOSED_LOSS
    pnl: float  # Profit/Loss in EGP
    pnl_percent: float  # Profit/Loss percentage
    signal_confidence: float
    reasons: List[str]


class PaperTradingSystem:
    """Manages virtual trades for strategy evaluation"""
    
    def __init__(self, initial_capital: float = 100000):
        self.initial_capital = initial_capital
        self.current_capital = initial_capital
        self.trades: List[Trade] = []
        self.open_trades: Dict[str, Trade] = {}  # ticker -> Trade
        self.default_trade_amount = 1000  # 1000 EGP per trade
        self._lock = threading.Lock()
        
        # Load existing data
        self._load_data()
    
    def _load_data(self):
        """Load trades and portfolio from files"""
        # Load portfolio
        if os.path.exists(PORTFOLIO_FILE):
            try:
                with open(PORTFOLIO_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.initial_capital = data.get('initial_capital', 100000)
                    self.current_capital = data.get('current_capital', 100000)
            except:
                pass
        
        # Load trades
        if os.path.exists(TRADES_FILE):
            try:
                with open(TRADES_FILE, 'r', encoding='utf-8') as f:
                    trades_data = json.load(f)
                    for t in trades_data:
                        trade = Trade(**t)
                        self.trades.append(trade)
                        if trade.status == TradeStatus.OPEN.value:
                            self.open_trades[trade.ticker] = trade
            except:
                pass
    
    def _save_data(self):
        """Save trades and portfolio to files"""
        with self._lock:
            # Save portfolio
            portfolio_data = {
                'initial_capital': self.initial_capital,
                'current_capital': self.current_capital,
                'last_updated': datetime.now().isoformat()
            }
            with open(PORTFOLIO_FILE, 'w', encoding='utf-8') as f:
                json.dump(portfolio_data, f, ensure_ascii=False, indent=2)
            
            # Save trades
            trades_data = [asdict(t) for t in self.trades]
            with open(TRADES_FILE, 'w', encoding='utf-8') as f:
                json.dump(trades_data, f, ensure_ascii=False, indent=2)
    
    def open_trade(
        self,
        ticker: str,
        company_name: str,
        arabic_name: str,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        signal_confidence: float,
        reasons: List[str],
        direction: str = "BUY",
        investment_amount: float = None
    ) -> Optional[Trade]:
        """Open a new virtual trade"""
        
        # Check if already have an open trade for this ticker
        if ticker in self.open_trades:
            return None
        
        investment = investment_amount or self.default_trade_amount
        
        # Check if enough capital
        if investment > self.current_capital:
            return None
        
        # Calculate quantity
        quantity = int(investment / entry_price)
        if quantity <= 0:
            return None
        
        actual_investment = quantity * entry_price
        
        # Create trade
        trade = Trade(
            id=f"T{len(self.trades)+1:05d}",
            ticker=ticker,
            company_name=company_name,
            arabic_name=arabic_name,
            direction=direction,
            entry_price=round(entry_price, 2),
            current_price=round(entry_price, 2),
            stop_loss=round(stop_loss, 2),
            take_profit=round(take_profit, 2),
            quantity=quantity,
            investment_amount=round(actual_investment, 2),
            entry_time=datetime.now().isoformat(),
            exit_time=None,
            exit_price=None,
            status=TradeStatus.OPEN.value,
            pnl=0,
            pnl_percent=0,
            signal_confidence=signal_confidence,
            reasons=reasons
        )
        
        # Update capital
        self.current_capital -= actual_investment
        
        # Store trade
        self.trades.append(trade)
        self.open_trades[ticker] = trade
        
        # Save to file
        self._save_data()
        
        return trade
    
    def update_trade_price(self, ticker: str, current_price: float) -> Optional[Trade]:
        """Update current price for an open trade"""
        if ticker not in self.open_trades:
            return None
        
        trade = self.open_trades[ticker]
        trade.current_price = round(current_price, 2)
        
        # Calculate P&L
        if trade.direction == "BUY":
            trade.pnl = round((current_price - trade.entry_price) * trade.quantity, 2)
            trade.pnl_percent = round(((current_price - trade.entry_price) / trade.entry_price) * 100, 2)
        else:  # SELL (short)
            trade.pnl = round((trade.entry_price - current_price) * trade.quantity, 2)
            trade.pnl_percent = round(((trade.entry_price - current_price) / trade.entry_price) * 100, 2)
        
        # Check stop loss / take profit
        if trade.direction == "BUY":
            if current_price <= trade.stop_loss:
                return self.close_trade(ticker, current_price, "STOP_LOSS")
            elif current_price >= trade.take_profit:
                return self.close_trade(ticker, current_price, "TAKE_PROFIT")
        else:
            if current_price >= trade.stop_loss:
                return self.close_trade(ticker, current_price, "STOP_LOSS")
            elif current_price <= trade.take_profit:
                return self.close_trade(ticker, current_price, "TAKE_PROFIT")
        
        self._save_data()
        return trade
    
    def close_trade(self, ticker: str, exit_price: float, reason: str = "MANUAL") -> Optional[Trade]:
        """Close an open trade"""
        if ticker not in self.open_trades:
            return None
        
        trade = self.open_trades[ticker]
        trade.exit_price = round(exit_price, 2)
        trade.exit_time = datetime.now().isoformat()
        trade.current_price = round(exit_price, 2)
        
        # Calculate final P&L
        if trade.direction == "BUY":
            trade.pnl = round((exit_price - trade.entry_price) * trade.quantity, 2)
            trade.pnl_percent = round(((exit_price - trade.entry_price) / trade.entry_price) * 100, 2)
        else:
            trade.pnl = round((trade.entry_price - exit_price) * trade.quantity, 2)
            trade.pnl_percent = round(((trade.entry_price - exit_price) / trade.entry_price) * 100, 2)
        
        # Set status
        if reason == "STOP_LOSS" or trade.pnl < 0:
            trade.status = TradeStatus.CLOSED_LOSS.value
        elif reason == "TAKE_PROFIT" or trade.pnl > 0:
            trade.status = TradeStatus.CLOSED_PROFIT.value
        else:
            trade.status = TradeStatus.CLOSED_MANUAL.value
        
        # Return capital + PnL
        self.current_capital += trade.investment_amount + trade.pnl
        
        # Remove from open trades
        del self.open_trades[ticker]
        
        self._save_data()
        return trade
    
    def get_open_trades(self) -> List[Dict]:
        """Get all open trades"""
        return [asdict(t) for t in self.open_trades.values()]
    
    def get_all_trades(self) -> List[Dict]:
        """Get all trades (open and closed)"""
        return [asdict(t) for t in self.trades]
    
    def get_closed_trades(self) -> List[Dict]:
        """Get closed trades only"""
        return [asdict(t) for t in self.trades if t.status != TradeStatus.OPEN.value]
    
    def get_portfolio_stats(self) -> Dict:
        """Get portfolio statistics"""
        total_trades = len(self.trades)
        open_trades = len(self.open_trades)
        closed_trades = [t for t in self.trades if t.status != TradeStatus.OPEN.value]
        
        winning_trades = [t for t in closed_trades if t.pnl > 0]
        losing_trades = [t for t in closed_trades if t.pnl < 0]
        
        total_realized_pnl = sum(t.pnl for t in closed_trades)
        total_unrealized_pnl = sum(t.pnl for t in self.open_trades.values())
        
        win_rate = (len(winning_trades) / len(closed_trades) * 100) if closed_trades else 0
        
        return {
            "initial_capital": self.initial_capital,
            "current_capital": round(self.current_capital, 2),
            "total_equity": round(self.current_capital + sum(t.investment_amount + t.pnl for t in self.open_trades.values()), 2),
            "total_trades": total_trades,
            "open_trades": open_trades,
            "closed_trades": len(closed_trades),
            "winning_trades": len(winning_trades),
            "losing_trades": len(losing_trades),
            "win_rate": round(win_rate, 1),
            "total_realized_pnl": round(total_realized_pnl, 2),
            "total_unrealized_pnl": round(total_unrealized_pnl, 2),
            "total_pnl": round(total_realized_pnl + total_unrealized_pnl, 2),
            "total_return_percent": round(((self.current_capital + sum(t.investment_amount + t.pnl for t in self.open_trades.values()) - self.initial_capital) / self.initial_capital) * 100, 2),
            "last_updated": datetime.now().isoformat()
        }
    
    def reset_portfolio(self, initial_capital: float = 100000):
        """Reset portfolio and clear all trades"""
        self.initial_capital = initial_capital
        self.current_capital = initial_capital
        self.trades = []
        self.open_trades = {}
        
        # Delete files
        if os.path.exists(TRADES_FILE):
            os.remove(TRADES_FILE)
        if os.path.exists(PORTFOLIO_FILE):
            os.remove(PORTFOLIO_FILE)
        
        self._save_data()


# Global instance
paper_trading = PaperTradingSystem(initial_capital=100000)


def auto_trade_from_signals(signals: list, max_open_trades: int = 5):
    """
    Automatically open trades based on signals
    Only opens trades with high confidence
    """
    opened = []
    
    for signal in signals:
        # Skip if already have this trade open
        if signal.ticker in paper_trading.open_trades:
            continue
        
        # Skip if too many open trades
        if len(paper_trading.open_trades) >= max_open_trades:
            break
        
        # Only trade high confidence signals
        if signal.confidence < 65:
            continue
        
        # Open trade
        trade = paper_trading.open_trade(
            ticker=signal.ticker,
            company_name=signal.indicators.get("price", {}).get("name", signal.ticker) if isinstance(signal.indicators, dict) else signal.ticker,
            arabic_name="",
            entry_price=signal.price,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
            signal_confidence=signal.confidence,
            reasons=signal.reasons,
            direction="BUY" if "شراء" in signal.signal_type.value else "SELL",
            investment_amount=1000  # 1000 EGP per trade
        )
        
        if trade:
            opened.append(trade)
    
    return opened
