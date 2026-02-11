"""
Chart Generator Module
Creates interactive charts using Plotly
"""

import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
from typing import Dict, Optional
from technical_analysis import calculate_all_indicators
from config import STRATEGY_CONFIG


def create_candlestick_chart(
    df: pd.DataFrame,
    ticker: str,
    company_name: str = "",
    show_indicators: bool = True
) -> str:
    """
    Create an interactive candlestick chart with indicators
    
    Args:
        df: DataFrame with OHLCV data
        ticker: Stock ticker
        company_name: Company name for title
        show_indicators: Whether to show technical indicators
        
    Returns:
        Plotly chart as JSON string
    """
    # Calculate indicators
    indicators = calculate_all_indicators(df) if show_indicators else None
    
    # Create subplot with volume
    fig = make_subplots(
        rows=4, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.02,
        row_heights=[0.5, 0.15, 0.2, 0.15],
        subplot_titles=(
            f'{company_name} ({ticker})' if company_name else ticker,
            'Volume / حجم التداول',
            'MACD',
            'RSI'
        )
    )
    
    # Candlestick
    fig.add_trace(
        go.Candlestick(
            x=df.index,
            open=df['Open'],
            high=df['High'],
            low=df['Low'],
            close=df['Close'],
            name='السعر',
            increasing_line_color='#00C853',
            decreasing_line_color='#FF1744'
        ),
        row=1, col=1
    )
    
    if show_indicators and indicators:
        # Add Bollinger Bands
        bb_upper = df['Close'].rolling(window=STRATEGY_CONFIG["bb_period"]).mean() + \
                   STRATEGY_CONFIG["bb_std"] * df['Close'].rolling(window=STRATEGY_CONFIG["bb_period"]).std()
        bb_lower = df['Close'].rolling(window=STRATEGY_CONFIG["bb_period"]).mean() - \
                   STRATEGY_CONFIG["bb_std"] * df['Close'].rolling(window=STRATEGY_CONFIG["bb_period"]).std()
        bb_middle = df['Close'].rolling(window=STRATEGY_CONFIG["bb_period"]).mean()
        
        fig.add_trace(
            go.Scatter(
                x=df.index, y=bb_upper,
                name='Bollinger Upper',
                line=dict(color='rgba(156, 39, 176, 0.3)', width=1),
                showlegend=False
            ),
            row=1, col=1
        )
        
        fig.add_trace(
            go.Scatter(
                x=df.index, y=bb_lower,
                name='Bollinger Lower',
                line=dict(color='rgba(156, 39, 176, 0.3)', width=1),
                fill='tonexty',
                fillcolor='rgba(156, 39, 176, 0.1)',
                showlegend=False
            ),
            row=1, col=1
        )
        
        fig.add_trace(
            go.Scatter(
                x=df.index, y=bb_middle,
                name='BB Middle',
                line=dict(color='rgba(156, 39, 176, 0.5)', width=1, dash='dash'),
                showlegend=False
            ),
            row=1, col=1
        )
        
        # Add SMA
        sma_short = df['Close'].rolling(window=STRATEGY_CONFIG["sma_short"]).mean()
        sma_long = df['Close'].rolling(window=STRATEGY_CONFIG["sma_long"]).mean()
        
        fig.add_trace(
            go.Scatter(
                x=df.index, y=sma_short,
                name=f'SMA {STRATEGY_CONFIG["sma_short"]}',
                line=dict(color='#2196F3', width=1.5)
            ),
            row=1, col=1
        )
        
        fig.add_trace(
            go.Scatter(
                x=df.index, y=sma_long,
                name=f'SMA {STRATEGY_CONFIG["sma_long"]}',
                line=dict(color='#FF9800', width=1.5)
            ),
            row=1, col=1
        )
    
    # Volume
    colors = ['#00C853' if close >= open else '#FF1744' 
              for close, open in zip(df['Close'], df['Open'])]
    
    fig.add_trace(
        go.Bar(
            x=df.index,
            y=df['Volume'],
            name='حجم التداول',
            marker_color=colors,
            showlegend=False
        ),
        row=2, col=1
    )
    
    if show_indicators:
        # MACD
        from ta import trend
        macd_indicator = trend.MACD(
            df['Close'],
            window_slow=STRATEGY_CONFIG["macd_slow"],
            window_fast=STRATEGY_CONFIG["macd_fast"],
            window_sign=STRATEGY_CONFIG["macd_signal"]
        )
        
        fig.add_trace(
            go.Scatter(
                x=df.index,
                y=macd_indicator.macd(),
                name='MACD',
                line=dict(color='#2196F3', width=1.5)
            ),
            row=3, col=1
        )
        
        fig.add_trace(
            go.Scatter(
                x=df.index,
                y=macd_indicator.macd_signal(),
                name='Signal',
                line=dict(color='#FF9800', width=1.5)
            ),
            row=3, col=1
        )
        
        macd_hist = macd_indicator.macd_diff()
        hist_colors = ['#00C853' if v >= 0 else '#FF1744' for v in macd_hist]
        
        fig.add_trace(
            go.Bar(
                x=df.index,
                y=macd_hist,
                name='Histogram',
                marker_color=hist_colors,
                showlegend=False
            ),
            row=3, col=1
        )
        
        # RSI
        from ta import momentum
        rsi = momentum.RSIIndicator(df['Close'], window=STRATEGY_CONFIG["rsi_period"]).rsi()
        
        fig.add_trace(
            go.Scatter(
                x=df.index,
                y=rsi,
                name='RSI',
                line=dict(color='#9C27B0', width=1.5)
            ),
            row=4, col=1
        )
        
        # RSI overbought/oversold lines
        fig.add_hline(
            y=STRATEGY_CONFIG["rsi_overbought"],
            line_dash="dash",
            line_color="red",
            annotation_text="ذروة شراء",
            row=4, col=1
        )
        
        fig.add_hline(
            y=STRATEGY_CONFIG["rsi_oversold"],
            line_dash="dash",
            line_color="green",
            annotation_text="ذروة بيع",
            row=4, col=1
        )
        
        fig.add_hline(
            y=50,
            line_dash="dot",
            line_color="gray",
            row=4, col=1
        )
    
    # Update layout
    fig.update_layout(
        title=dict(
            text=f'<b>{company_name}</b> ({ticker})' if company_name else f'<b>{ticker}</b>',
            x=0.5,
            font=dict(size=20)
        ),
        xaxis_rangeslider_visible=False,
        template='plotly_dark',
        paper_bgcolor='#1a1a2e',
        plot_bgcolor='#16213e',
        font=dict(family='Cairo, Arial', color='#eee'),
        height=900,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        ),
        margin=dict(l=50, r=50, t=80, b=50)
    )
    
    # Update axes
    fig.update_xaxes(
        gridcolor='rgba(255,255,255,0.1)',
        showgrid=True
    )
    
    fig.update_yaxes(
        gridcolor='rgba(255,255,255,0.1)',
        showgrid=True
    )
    
    return fig.to_json()


def create_mini_chart(df: pd.DataFrame, ticker: str) -> str:
    """
    Create a small chart for quick overview
    
    Args:
        df: DataFrame with OHLCV data
        ticker: Stock ticker
        
    Returns:
        Plotly chart as JSON string
    """
    # Last 30 days
    df_mini = df.tail(30)
    
    # Determine color based on trend
    is_positive = df_mini['Close'].iloc[-1] >= df_mini['Close'].iloc[0]
    color = '#00C853' if is_positive else '#FF1744'
    
    fig = go.Figure()
    
    fig.add_trace(
        go.Scatter(
            x=df_mini.index,
            y=df_mini['Close'],
            mode='lines',
            fill='tozeroy',
            line=dict(color=color, width=2),
            fillcolor=f'{color}20'
        )
    )
    
    fig.update_layout(
        template='plotly_dark',
        paper_bgcolor='transparent',
        plot_bgcolor='transparent',
        showlegend=False,
        margin=dict(l=0, r=0, t=0, b=0),
        height=80,
        xaxis=dict(visible=False),
        yaxis=dict(visible=False)
    )
    
    return fig.to_json()


def create_sector_heatmap(stocks_data: Dict[str, Dict]) -> str:
    """
    Create a heatmap of sectors performance
    
    Args:
        stocks_data: Dictionary with stock performance data
        
    Returns:
        Plotly chart as JSON string
    """
    from config import EGX_TOP_COMPANIES
    
    # Organize by sector
    sectors = {}
    for ticker, data in stocks_data.items():
        if ticker in EGX_TOP_COMPANIES:
            sector = EGX_TOP_COMPANIES[ticker]["sector"]
            if sector not in sectors:
                sectors[sector] = []
            sectors[sector].append({
                "ticker": ticker,
                "name": EGX_TOP_COMPANIES[ticker]["name"],
                "change": data.get("change_percent", 0)
            })
    
    # Calculate average by sector
    sector_names = []
    sector_changes = []
    
    for sector, stocks in sectors.items():
        avg_change = sum(s["change"] for s in stocks) / len(stocks)
        sector_names.append(sector)
        sector_changes.append(round(avg_change, 2))
    
    # Create heatmap
    fig = go.Figure()
    
    fig.add_trace(
        go.Bar(
            y=sector_names,
            x=sector_changes,
            orientation='h',
            marker=dict(
                color=sector_changes,
                colorscale=[
                    [0, '#FF1744'],
                    [0.5, '#FFC107'],
                    [1, '#00C853']
                ],
                cmin=-5,
                cmax=5
            ),
            text=[f'{c:+.2f}%' for c in sector_changes],
            textposition='auto'
        )
    )
    
    fig.update_layout(
        title='أداء القطاعات / Sector Performance',
        template='plotly_dark',
        paper_bgcolor='#1a1a2e',
        plot_bgcolor='#16213e',
        font=dict(family='Cairo, Arial', color='#eee'),
        height=400,
        margin=dict(l=150, r=50, t=80, b=50),
        xaxis_title='نسبة التغير %',
        yaxis_title=''
    )
    
    return fig.to_json()
