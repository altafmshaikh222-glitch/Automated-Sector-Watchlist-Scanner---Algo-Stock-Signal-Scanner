from flask import Flask, render_template
import yfinance as yf
import pandas as pd
import requests
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from strategies.indicators import apply_technical_indicators

app = Flask(__name__)

# Configure a custom session with a User-Agent to prevent Yahoo Finance 401 blocking
session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
})

# Categorized Sector Watchlist (NSE Tickers)
SECTOR_WATCHLIST = {
    "Original Blue-Chips": ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS", "ITC.NS", "LT.NS"],
    "Banking & Financial Services": ["SBIN.NS", "AXISBANK.NS", "KOTAKBANK.NS", "BAJFINANCE.NS"],
    "Auto & Manufacturing": ["TATAMOTORS.NS", "MARUTI.NS", "M&M.NS", "BAJAJ-AUTO.NS"],
    "Tech & Communications": ["HCLTECH.NS", "TECHM.NS", "BHARTIARTL.NS", "WIPRO.NS"],
    "Metals, Energy & Infrastructure": ["TATASTEEL.NS", "NTPC.NS", "POWERGRID.NS", "ONGC.NS", "SUNPHARMA.NS"]
}

def fetch_and_scan(ticker):
    """Fetches data safely using a custom session and handles any API errors gracefully."""
    try:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=365)
        
        # Pass the custom session to avoid 401 unauthorized blocks
        df = yf.download(ticker, start=start_date, end=end_date, progress=False, session=session)
        if df is None or df.empty:
            return None
            
        # Robust MultiIndex and DataFrame extraction fix
        if isinstance(df.columns, pd.MultiIndex):
            close_col = [col for col in df.columns if 'Close' in str(col)]
            if not close_col:
                return None
            df = pd.DataFrame({'Close': df[close_col[0]]})
        else:
            if 'Close' in df.columns:
                close_data = df['Close']
                if isinstance(close_data, pd.DataFrame):
                    df = pd.DataFrame({'Close': close_data.iloc[:, 0]})
                else:
                    df = pd.DataFrame({'Close': close_data})
            else:
                df = pd.DataFrame({'Close': df.iloc[:, 0]})
            
        df = apply_technical_indicators(df)
        if len(df) < 2:
            return None
            
        latest = df.iloc[-1]
        prev = df.iloc[-2]
        
        close_price = float(latest['Close'])
        rsi = float(latest['RSI_14'])
        sma_50 = float(latest['SMA_50'])
        sma_200 = float(latest['SMA_200'])
        
        signal = "Neutral"
        if rsi < 35:
            signal = "Oversold (Potential Buy 🟢)"
        elif rsi > 70:
            signal = "Overbought (Potential Sell 🔴)"
        elif prev['SMA_50'] < prev['SMA_200'] and latest['SMA_50'] > latest['SMA_200']:
            signal = "Golden Cross Breakout 🚀"
        
        return {
            "ticker": ticker,
            "price": round(close_price, 2),
            "rsi": round(rsi, 2),
            "sma_50": round(sma_50, 2),
            "sma_200": round(sma_200, 2),
            "signal": signal
        }
    except Exception as e:
        print(f"Skipped {ticker} due to network/data error: {e}")
        return None

def scan_watchlist():
    """Scans all sectors concurrently with safe thread management."""
    categorized_results = {}
    all_tickers = []
    for tickers in SECTOR_WATCHLIST.values():
        all_tickers.extend(tickers)
        
    ticker_results = {}
    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_ticker = {executor.submit(fetch_and_scan, ticker): ticker for ticker in all_tickers}
        for future in as_completed(future_to_ticker):
            res = future.result()
            if res:
                ticker_results[res['ticker']] = res
                
    for sector, tickers in SECTOR_WATCHLIST.items():
        sector_list = []
        for ticker in tickers:
            if ticker in ticker_results:
                sector_list.append(ticker_results[ticker])
        categorized_results[sector] = sector_list
        
    return categorized_results

@app.route("/")
def index():
    results = scan_watchlist()
    return render_template("index.html", results=results)

if __name__ == "__main__":
    app.run(debug=True, port=5000)