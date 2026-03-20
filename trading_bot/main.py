import logging
import os
from typing import List, Dict, Any

import pandas as pd
import requests
import yfinance as yf
from finvizfinance.quote import finvizfinance
from finvizfinance.screener.overview import Overview
from finvizfinance.screener.technical import Technical

os.makedirs("logs", exist_ok=True)

LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(logging.INFO)
handler = logging.FileHandler(
    filename=os.path.join("logs", f"trading_bot_{pd.Timestamp.now().strftime('%Y-%m-%d')}.log"),
    mode='a',
)
handler.setFormatter(
    fmt=logging.Formatter(
        datefmt="%b-%d-%Y %I:%M:%S %p",
        fmt="%(asctime)s - %(levelname)s - [%(funcName)s:%(lineno)d] - %(message)s",
    )
)
LOGGER.addHandler(hdlr=handler)

TWELVEDATA_API_KEY = (
        os.environ.get("TWELVEDATA_API_KEY") or os.environ.get("TWELVEDATA_APIKEY") or
        os.environ.get("twelvedata_api_key") or os.environ.get("twelvedata_apikey")
)

filters_dict = {
    'Exchange': 'NASDAQ',
    'Country': 'USA',
    'Average Volume': 'Over 500K',
    'Price': 'Under $50',
    'Relative Volume': 'Over 2',
    'Gap': 'Up',
    'Change': 'Up 5%',
    'RSI (14)': 'Not Overbought (<60)',
}

foverview = Overview()
foverview.set_filter(filters_dict=filters_dict)
scan_df = foverview.screener_view()

ftech = Technical()
ftech.set_filter(filters_dict=filters_dict)
tech_df = ftech.screener_view()


def enrich_ticker(ticker):
    try:
        stock = finvizfinance(ticker)
        news = stock.ticker_news()
        insider = stock.ticker_inside_trader()
        latest_news = news['Title'].iloc[0] if not news.empty else 'No news'
        insider_action = insider['Transaction'].iloc[0] if not insider.empty else 'No insider data'
        return pd.Series({'Latest_News': latest_news, 'Insider_Action': insider_action})
    except Exception as err:
        LOGGER.error(f"Error enriching ticker {ticker}: {err}")
        return pd.Series({'Latest_News': pd.NA, 'Insider_Action': pd.NA})


def get_candle_signal_twelvedata(ticker):
    """Pull last 5 x 5min candles from twelvedata and determine buy/sell signal based on direction."""
    try:
        url = f'https://api.twelvedata.com/time_series'
        params = {
            'symbol': ticker,
            'interval': '5min',
            'outputsize': 5,
            'apikey': TWELVEDATA_API_KEY,
        }
        response = requests.get(url, params=params)
        data = response.json()

        if 'values' not in data:
            return pd.Series({'TD_Signal': 'No data', 'TD_Trend': 'Unknown'})

        candles = pd.DataFrame(data['values'])
        candles = candles.astype({
            'open': float, 'high': float,
            'low': float, 'close': float,
            'volume': float
        })

        # Candle direction: True = bullish, False = bearish
        candles['bullish'] = candles['close'] > candles['open']

        # Count consecutive bullish candles from most recent
        bullish_count = candles['bullish'].sum()
        last_candle = candles.iloc[0]  # most recent
        prev_candle = candles.iloc[1]

        # Higher highs and higher lows = strong uptrend
        higher_high = last_candle['high'] > prev_candle['high']
        higher_low = last_candle['low'] > prev_candle['low']

        if bullish_count >= 4 and higher_high and higher_low:
            signal = 'STRONG BUY'
        elif bullish_count >= 3 and higher_high:
            signal = 'BUY'
        elif bullish_count <= 1:
            signal = 'SELL'
        elif bullish_count == 2:
            signal = 'WEAK - WAIT'
        else:
            signal = 'NEUTRAL'

        trend = 'UPTREND' if higher_high and higher_low else 'DOWNTREND' if not higher_high and not higher_low else 'SIDEWAYS'
        return pd.Series({'TD_Signal': signal, 'TD_Trend': trend})
    except Exception as error:
        LOGGER.error(f"Error fetching twelvedata data for {ticker} : {error}")
        return pd.Series({'TD_Signal': 'Error', 'TD_Trend': 'Error'})


def get_candle_signal_yfinance(ticker):
    try:
        df = yf.download(ticker, period='1d', interval='5m', progress=False)

        if df.empty:
            return pd.Series({'YF_Signal': 'No data', 'EMA_Cross': 'Unknown'})

        # Flatten multi-level columns if present
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        df['EMA9'] = df['Close'].ewm(span=9).mean()
        df['EMA21'] = df['Close'].ewm(span=21).mean()

        # Use .item() to extract scalar values
        last_ema9 = df['EMA9'].iloc[-1].item()
        last_ema21 = df['EMA21'].iloc[-1].item()
        prev_ema9 = df['EMA9'].iloc[-2].item()
        prev_ema21 = df['EMA21'].iloc[-2].item()
        last_volume = df['Volume'].iloc[-1].item()
        avg_volume = df['Volume'].mean().item()

        ema_cross_up = prev_ema9 < prev_ema21 and last_ema9 > last_ema21
        ema_cross_down = prev_ema9 > prev_ema21 and last_ema9 < last_ema21
        ema_above = last_ema9 > last_ema21
        volume_spike = last_volume > avg_volume * 1.5

        if ema_cross_up and volume_spike:
            signal = 'STRONG BUY'
        elif ema_above and volume_spike:
            signal = 'BUY'
        elif ema_cross_down:
            signal = 'SELL'
        elif not ema_above:
            signal = 'WEAK - WAIT'
        else:
            signal = 'NEUTRAL'
        cross = 'CROSS UP' if ema_cross_up else 'CROSS DOWN' if ema_cross_down else 'NO CROSS'
        return pd.Series({'YF_Signal': signal, 'EMA_Cross': cross})
    except Exception as error:
        print(f"Error fetching yfinance data for {ticker} : {error}")
        return pd.Series({'YF_Signal': 'Error', 'EMA_Cross': 'Error'})


def score_stock(row):
    score = 0

    # Volume conviction (max 30 pts)
    if row['Volume'] > 5000000:
        score += 30
    elif row['Volume'] > 2000000:
        score += 20
    elif row['Volume'] > 1000000:
        score += 10

    # Momentum via Change % (max 25 pts)
    if row['Change'] > 20:
        score += 25
    elif row['Change'] > 10:
        score += 15
    elif row['Change'] > 5:
        score += 10

    # RSI sweet spot 50-65 = trending but not exhausted (max 25 pts)
    if 50 <= row['RSI'] <= 65:
        score += 25
    elif 40 <= row['RSI'] < 50:
        score += 15
    elif 65 < row['RSI'] < 70:
        score += 10

    # Insider buying bonus (max 20 pts)
    if 'Buy' in str(row['Insider_Action']):
        score += 20
    elif 'Sale' in str(row['Insider_Action']):
        score -= 10

    # Candle signal bonus (max 20 pts)
    if row['TD_Signal'] == 'STRONG BUY' and row['YF_Signal'] == 'STRONG BUY':
        score += 20  # both agree = high confidence
    elif row['TD_Signal'] == 'BUY' or row['YF_Signal'] == 'BUY':
        score += 10
    elif row['TD_Signal'] == 'SELL' or row['YF_Signal'] == 'SELL':
        score -= 15  # penalize conflicting signals hard

    return score


def builder(filepath: str = None, to_dict: bool = False) -> pd.DataFrame | List[Dict[str, Any]]:
    # Build final dataframe
    final_df = scan_df.merge(tech_df[['Ticker', 'Beta', 'ATR', 'SMA20', 'SMA50', 'RSI', 'Gap']], on='Ticker')
    enriched = final_df['Ticker'].apply(enrich_ticker)
    final_df = pd.concat([final_df, enriched], axis=1)

    # Candle signals
    td_signals = final_df['Ticker'].apply(get_candle_signal_twelvedata)
    yf_signals = final_df['Ticker'].apply(get_candle_signal_yfinance)
    final_df = pd.concat([final_df, td_signals, yf_signals], axis=1)

    # Numeric conversions
    final_df['Volume'] = pd.to_numeric(final_df['Volume'].astype(str).str.replace(',', ''), errors='coerce')
    final_df['ATR'] = pd.to_numeric(final_df['ATR'], errors='coerce')
    final_df['RSI'] = pd.to_numeric(final_df['RSI'], errors='coerce')
    final_df['Change'] = pd.to_numeric(final_df['Change'].astype(str).str.replace('%', ''), errors='coerce')

    final_df = final_df[final_df['RSI'] < 70]
    final_df['Score'] = final_df.apply(score_stock, axis=1)
    final_df = final_df.sort_values('Score', ascending=False)

    filtered_df = final_df[
        ['Ticker', 'Price', 'Change', 'Volume', 'RSI', 'ATR',
         'TD_Signal', 'TD_Trend', 'YF_Signal', 'EMA_Cross',
         'Score', 'Latest_News', 'Insider_Action']
    ]
    if filepath:
        match filepath.split('.')[-1]:
            case "csv":
                filtered_df.to_csv(filepath, index=False)
            case "xlsx":
                filtered_df.to_excel(filepath, index=False)
            case "json":
                filtered_df.to_json(filepath, orient='records', lines=True)
            case "html":
                filtered_df.to_html(filepath, index=False)
            case _:
                raise ValueError("Unsupported file format. Use .csv, .xlsx, .json, or .html")

    if to_dict:
        return filtered_df.to_dict(orient='records')

    return filtered_df


if __name__ == '__main__':
    pd.set_option('display.max_columns', None)
    pd.set_option('display.max_rows', None)
    print(builder(filepath="index.html"))
