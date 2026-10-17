import pandas as pd
from pybit.unified_trading import HTTP
import time
from datetime import datetime
import numpy as np
import telebot


# ==================== API TOKENS ====================
API_KEY = '2eXDe221sTedNqwSFz'
API_SECRET = 'a8m7XsSTJOu1PXcj1bs4rN41qIWMPuoBmQVs'

TELEGRAM_BOT_TOKEN = '8968569374:AAGW76iTBj-dcA6hmQ3EgkO5pwbExNAuijA'
TELEGRAM_CHAT_ID = '5650732610'

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)

session = HTTP(api_key=API_KEY, api_secret=API_SECRET)


# ==================== STRATEGY PARAMS ====================
symbol = 'DOGEUSDT'
timeframe = 60            # H1 (1 час) — рекомендованный ТФ
qty = 330

# Bollinger Bands
BB_PERIOD = 20
BB_STD = 2.0

# Supertrend
ST_LOOKBACK = 10
ST_MULTIPLIER = 3

# ADX (фильтр силы тренда)
ADX_PERIOD = 14
ADX_THRESHOLD = 25        # Вход только при ADX > 25

position = None
status = None


# ==================== DATA ====================
def get_historical_data():
    resp = session.get_kline(
        category="linear",
        symbol=symbol,
        interval=timeframe,
        limit=200
    )
    if not resp or 'result' not in resp or 'list' not in resp['result']:
        print("Error: No data received from API")
        return None

    df = pd.DataFrame(resp['result']['list'], columns=[
        'timestamp', 'open', 'high', 'low', 'close', 'volume', 'turnover'
    ])
    df = df[::-1]
    df['timestamp'] = pd.to_datetime(df['timestamp'].astype(int), unit='ms')
    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = df[col].astype(float)
    return df


# ==================== POSITION ====================
def get_current_position():
    try:
        response = session.get_positions(category="linear", symbol=symbol)
        positions = response.get('result', {}).get('list', [])
        for pos in positions:
            if float(pos.get('size', 0)) > 0:
                return 'LONG' if pos['side'] == 'Buy' else 'SHORT'
        return None
    except Exception as e:
        print(f"Position check error: {str(e)}")
        return None


def get_unrealized_pnl_percentage():
    try:
        response = session.get_positions(category="linear", symbol=symbol, settleCoin="USDT")
        if response["retCode"] != 0:
            raise Exception(f"API error: {response['retMsg']}")

        positions = response["result"]["list"]
        for pos in positions:
            if float(pos["size"]) == 0:
                continue
            unrealized_pnl = float(pos["unrealisedPnl"])
            position_value = float(pos["positionValue"])
            if position_value > 0:
                return (unrealized_pnl / position_value) * 1000
            return 0.0
        return 0.0
    except Exception as e:
        print(f"PnL error: {e}")
        return 0.0


def execute_trade(signal):
    global position
    try:
        params = {
            "category": "linear",
            "symbol": symbol,
            "orderType": "Market",
            "qty": str(qty),
            "timeInForce": "GTC"
        }
        if signal == 'BUY':
            print(f"{datetime.now()} - BUY {qty}")
            session.place_order(**params, side="Buy")
            position = 'LONG'
        elif signal == 'SELL':
            print(f"{datetime.now()} - SELL {qty}")
            session.place_order(**params, side="Sell")
            position = 'SHORT'
    except Exception as e:
        print(f"Trade error: {str(e)}")


def close_position(signal):
    global position
    try:
        params = {
            "category": "linear",
            "symbol": symbol,
            "orderType": "Market",
            "qty": str(qty),
            "timeInForce": "GTC",
            "reduceOnly": True
        }
        if signal == 'BUY' and position == 'SHORT':
            print(f"{datetime.now()} - CLOSE SHORT {qty}")
            session.place_order(**params, side="Buy")
        elif signal == 'SELL' and position == 'LONG':
            print(f"{datetime.now()} - CLOSE LONG {qty}")
            session.place_order(**params, side="Sell")
    except Exception as e:
        print(f"Close position error: {str(e)}")


def take_profit(amount):
    global position
    try:
        params = {
            "category": "linear",
            "symbol": symbol,
            "orderType": "Market",
            "qty": str(amount),
            "timeInForce": "GTC",
            "reduceOnly": True
        }
        if position == 'LONG':
            print(f"{datetime.now()} - TAKE PROFIT {amount}")
            session.place_order(**params, side="Sell")
        elif position == 'SHORT':
            print(f"{datetime.now()} - TAKE PROFIT {amount}")
            session.place_order(**params, side="Buy")
    except Exception as e:
        print(f"Take profit error: {str(e)}")


# ==================== INDICATORS ====================
def calculate_bollinger_bands(df, period=BB_PERIOD, num_std=BB_STD):
    df['bb_middle'] = df['close'].rolling(window=period).mean()
    df['bb_std'] = df['close'].rolling(window=period).std()
    df['bb_upper'] = df['bb_middle'] + num_std * df['bb_std']
    df['bb_lower'] = df['bb_middle'] - num_std * df['bb_std']
    df['bb_width'] = (df['bb_upper'] - df['bb_lower']) / df['bb_middle']
    return df


def calculate_supertrend(high, low, close, lookback=ST_LOOKBACK, multiplier=ST_MULTIPLIER):
    high = pd.Series(high).astype(float)
    low = pd.Series(low).astype(float)
    close = pd.Series(close).astype(float)

    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.ewm(span=lookback, adjust=False).mean()

    hl_avg = (high + low) / 2
    upper_band = hl_avg + multiplier * atr
    lower_band = hl_avg - multiplier * atr

    final_upper = pd.Series(index=upper_band.index, dtype=float)
    final_lower = pd.Series(index=lower_band.index, dtype=float)

    for i in range(len(final_upper)):
        if i == 0:
            final_upper.iloc[i] = upper_band.iloc[i]
            final_lower.iloc[i] = lower_band.iloc[i]
        else:
            if (upper_band.iloc[i] < final_upper.iloc[i - 1]) or (close.iloc[i - 1] > final_upper.iloc[i - 1]):
                final_upper.iloc[i] = upper_band.iloc[i]
            else:
                final_upper.iloc[i] = final_upper.iloc[i - 1]
            if (lower_band.iloc[i] > final_lower.iloc[i - 1]) or (close.iloc[i - 1] < final_lower.iloc[i - 1]):
                final_lower.iloc[i] = lower_band.iloc[i]
            else:
                final_lower.iloc[i] = final_lower.iloc[i - 1]

    supertrend = pd.Series(index=close.index, dtype=float)
    for i in range(len(supertrend)):
        if i == 0:
            supertrend.iloc[i] = final_upper.iloc[i]
        else:
            if supertrend.iloc[i - 1] == final_upper.iloc[i - 1] and close.iloc[i] < final_upper.iloc[i]:
                supertrend.iloc[i] = final_upper.iloc[i]
            elif supertrend.iloc[i - 1] == final_upper.iloc[i - 1] and close.iloc[i] > final_upper.iloc[i]:
                supertrend.iloc[i] = final_lower.iloc[i]
            elif supertrend.iloc[i - 1] == final_lower.iloc[i - 1] and close.iloc[i] > final_lower.iloc[i]:
                supertrend.iloc[i] = final_lower.iloc[i]
            elif supertrend.iloc[i - 1] == final_lower.iloc[i - 1] and close.iloc[i] < final_lower.iloc[i]:
                supertrend.iloc[i] = final_upper.iloc[i]
            else:
                supertrend.iloc[i] = supertrend.iloc[i - 1]
    return supertrend


def calculate_adx(df, period=ADX_PERIOD):
    data = df.copy()
    num_cols = ['high', 'low', 'close']
    data[num_cols] = data[num_cols].apply(pd.to_numeric, errors='coerce')

    data['high_prev'] = data['high'].shift(1)
    data['low_prev'] = data['low'].shift(1)
    data['close_prev'] = data['close'].shift(1)

    data['tr1'] = data['high'] - data['low']
    data['tr2'] = abs(data['high'] - data['close_prev'])
    data['tr3'] = abs(data['low'] - data['close_prev'])
    data['tr'] = data[['tr1', 'tr2', 'tr3']].max(axis=1)

    data['plus_dm'] = np.where(
        (data['high'] - data['high_prev']) > (data['low_prev'] - data['low']),
        np.maximum(data['high'] - data['high_prev'], 0), 0
    )
    data['minus_dm'] = np.where(
        (data['low_prev'] - data['low']) > (data['high'] - data['high_prev']),
        np.maximum(data['low_prev'] - data['low'], 0), 0
    )

    data['smoothed_tr'] = data['tr'].rolling(window=period, min_periods=period).mean()
    data['smoothed_plus_dm'] = data['plus_dm'].rolling(window=period, min_periods=period).mean()
    data['smoothed_minus_dm'] = data['minus_dm'].rolling(window=period, min_periods=period).mean()

    for i in range(period, len(data)):
        prev_idx = data.index[i - 1]
        curr_idx = data.index[i]
        data.at[curr_idx, 'smoothed_tr'] = (
            data.at[prev_idx, 'smoothed_tr'] * (period - 1) + data.at[curr_idx, 'tr']
        ) / period
        data.at[curr_idx, 'smoothed_plus_dm'] = (
            data.at[prev_idx, 'smoothed_plus_dm'] * (period - 1) + data.at[curr_idx, 'plus_dm']
        ) / period
        data.at[curr_idx, 'smoothed_minus_dm'] = (
            data.at[prev_idx, 'smoothed_minus_dm'] * (period - 1) + data.at[curr_idx, 'minus_dm']
        ) / period

    data['plus_di'] = (data['smoothed_plus_dm'] / data['smoothed_tr']) * 100
    data['minus_di'] = (data['smoothed_minus_dm'] / data['smoothed_tr']) * 100

    di_sum = data['plus_di'] + data['minus_di']
    di_diff = abs(data['plus_di'] - data['minus_di'])
    data['dx'] = (di_diff / di_sum.replace(0, np.nan)) * 100
    data['adx'] = data['dx'].rolling(window=period).mean()

    return data


# ==================== SIGNALS ====================
def check_bb_breakout(df):
    """Свежий пробой полос Боллинджера (текущая свеча закрылась за полосой,
       предыдущая — внутри канала)."""
    if df is None or len(df) < 3:
        return False, False
    if pd.isna(df['bb_upper'].iloc[-1]) or pd.isna(df['bb_upper'].iloc[-2]):
        return False, False

    prev_close = df['close'].iloc[-2]
    curr_close = df['close'].iloc[-1]

    prev_upper = df['bb_upper'].iloc[-2]
    prev_lower = df['bb_lower'].iloc[-2]
    curr_upper = df['bb_upper'].iloc[-1]
    curr_lower = df['bb_lower'].iloc[-1]

    breakout_up = (prev_close <= prev_upper) and (curr_close > curr_upper)
    breakout_down = (prev_close >= prev_lower) and (curr_close < curr_lower)
    return breakout_up, breakout_down


def send_telegram_alert(trend, adx_val, bb_width):
    try:
        message = (
            f"📊 *Trade Update*\n"
            f"Time: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`\n"
            f"Symbol: *{symbol}*\n"
            f"Position: `{position}`\n"
            f"Trend: `{trend}`\n"
            f"ADX: `{adx_val:.2f}`\n"
            f"BB Width: `{bb_width:.5f}`"
        )
        bot.send_message(TELEGRAM_CHAT_ID, message, parse_mode='Markdown')
    except Exception as e:
        print(f"Telegram send error: {e}")


# ==================== MAIN ====================
def main_loop():
    global position, status

    position = get_current_position()
    print(f"Initial position: {position}")

    while True:
        try:
            df = get_historical_data()
            if df is None:
                time.sleep(2)
                continue

            df = calculate_bollinger_bands(df)
            df['supertrend'] = calculate_supertrend(df['high'], df['low'], df['close'])
            adx_df = calculate_adx(df, period=ADX_PERIOD)

            adx_val = adx_df['adx'].iloc[-1]
            plus_di = adx_df['plus_di'].iloc[-1]
            minus_di = adx_df['minus_di'].iloc[-1]
            bb_width = df['bb_width'].iloc[-1]

            last = df.iloc[-1]
            trend = "Long" if last['close'] > last['supertrend'] else "Short"

            breakout_up, breakout_down = check_bb_breakout(df)

            pnl = get_unrealized_pnl_percentage()

            adx_ok = (adx_val is not None) and not pd.isna(adx_val) and (adx_val > ADX_THRESHOLD)

            # ---- LONG entry ----
            if breakout_up and position != 'LONG' and trend == "Long" and adx_ok:
                close_position('BUY')
                execute_trade('BUY')
                send_telegram_alert(trend, adx_val, bb_width)

            # ---- SHORT entry ----
            elif breakout_down and position != 'SHORT' and trend == "Short" and adx_ok:
                close_position('SELL')
                execute_trade('SELL')
                send_telegram_alert(trend, adx_val, bb_width)

            # ---- Supertrend flip => close on opposite side ----
            elif position == 'LONG' and trend == "Short":
                close_position('SELL')
                status = None

            elif position == 'SHORT' and trend == "Long":
                close_position('BUY')
                status = None

            # ---- Tiered take profit ----
            elif position == 'LONG' and status is None and pnl >= 4.0:
                take_profit(220)
                status = 'TP1'
            elif position == 'LONG' and status == 'TP1' and pnl >= 8.0:
                take_profit(50)
                status = 'TP2'
            elif position == 'LONG' and status == 'TP2' and pnl >= 12.0:
                take_profit(40)
                status = 'TP3'
            elif position == 'LONG' and status == 'TP3' and pnl >= 16.0:
                take_profit(20)
                status = None

            elif position == 'SHORT' and status is None and pnl >= 4.0:
                take_profit(220)
                status = 'TP1'
            elif position == 'SHORT' and status == 'TP1' and pnl >= 8.0:
                take_profit(50)
                status = 'TP2'
            elif position == 'SHORT' and status == 'TP2' and pnl >= 12.0:
                take_profit(40)
                status = 'TP3'
            elif position == 'SHORT' and status == 'TP3' and pnl >= 16.0:
                take_profit(20)
                status = None

            # ---- Log ----
            print(f"\n{datetime.now()} | {symbol}")
            print(f"Position: {position} | Trend: {trend}")
            print(f"Close: {last['close']:.5f} | ST: {last['supertrend']:.5f}")
            print(f"BB up: {last['bb_upper']:.5f} | BB low: {last['bb_lower']:.5f} | width: {bb_width:.5f}")
            print(f"ADX: {adx_val:.2f} | +DI: {plus_di:.2f} | -DI: {minus_di:.2f} | PnL: {pnl:.2f}%")
            print(f"Signals: breakUp={breakout_up} breakDown={breakout_down}")

            time.sleep(1)

        except KeyboardInterrupt:
            print("Stopped by user")
            break
        except Exception as e:
            print(f"Main loop error: {str(e)}")
            time.sleep(2)


if __name__ == "__main__":
    try:
        print("Testing connection...")
        balance = session.get_wallet_balance(accountType="UNIFIED")
        print("Balance OK. Available:",
              balance['result']['list'][0]['coin'][0]['availableToWithdraw'])
        main_loop()
    except Exception as e:
        print(f"Init failed: {str(e)}")