import pandas as pd
from pybit.unified_trading import HTTP
import time
from datetime import datetime
import numpy as np
import telebot
import os
import signal as trigger
import sys


# Bybit api tokens
API_KEY = '4I3fwVkcfK61OAxuWZ'
API_SECRET = 'BMO7aNrKXOjTRsgEnBNFIiKEcG9xpeAcwlVD'

# Telegram api tokens
TELEGRAM_BOT_TOKEN = '8968569374:AAGW76iTBj-dcA6hmQ3EgkO5pwbExNAuijA'
TELEGRAM_CHAT_ID = '5650732610'

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)

session = HTTP(api_key=API_KEY, api_secret=API_SECRET)

# Position settings
symbol = 'MNTUSDT'
timeframe = 60
qty = 40

# EMA params (1H)
ema_fast = 25
ema_slow = 50

# MACD params (4H)
macd_fast = 12
macd_slow = 26
macd_signal = 9

# Supertrend params (1H)
st_lookback = 10
st_multiplier = 3

# Stop loss %
stop_loss_pct = -40.0

position = None
status = None


# ---------- Данные ----------
def get_historical_data():
    resp = session.get_kline(category="linear", symbol=symbol, interval=timeframe, limit=200)
    if not resp or 'result' not in resp or 'list' not in resp['result']:
        print("Error: No data received from API")
        return None
    df = pd.DataFrame(resp['result']['list'], columns=[
        'timestamp', 'open', 'high', 'low', 'close', 'volume', 'turnover'
    ])
    df = df[::-1]
    df['timestamp'] = pd.to_datetime(df['timestamp'].astype(int), unit='ms')
    for c in ['open', 'high', 'low', 'close', 'volume']:
        df[c] = df[c].astype(float)
    return df


def get_historical_data_4h():
    resp = session.get_kline(category="linear", symbol=symbol, interval=240, limit=200)
    if not resp or 'result' not in resp or 'list' not in resp['result']:
        print("Error: No data received from API")
        return None
    df = pd.DataFrame(resp['result']['list'], columns=[
        'timestamp', 'open', 'high', 'low', 'close', 'volume', 'turnover'
    ])
    df = df[::-1]
    df['timestamp'] = pd.to_datetime(df['timestamp'].astype(int), unit='ms')
    for c in ['open', 'high', 'low', 'close', 'volume']:
        df[c] = df[c].astype(float)
    return df


# ---------- Позиции / PnL ----------
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
            raise Exception(f"Ошибка API: {response['retMsg']}")
        positions = response["result"]["list"]
        if not positions:
            return 0.0
        for pos in positions:
            size = float(pos["size"])
            if size == 0:
                continue
            unrealized_pnl = float(pos["unrealisedPnl"])
            position_value = float(pos["positionValue"])
            if position_value > 0:
                return (unrealized_pnl / position_value) * 1000
        return 0.0
    except Exception as e:
        print(f"Ошибка: {e}")
        return 0.0


# ---------- Торговля ----------
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
            print(f"{datetime.now()} - BUY {qty} USDT")
            session.place_order(**params, side="Buy")
            position = 'LONG'
        elif signal == 'SELL':
            print(f"{datetime.now()} - SELL {qty} USDT")
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
            print(f"{datetime.now()} - CLOSE SHORT {qty} USDT")
            session.place_order(**params, side="Buy")
        elif signal == 'SELL' and position == 'LONG':
            print(f"{datetime.now()} - CLOSE LONG {qty} USDT")
            session.place_order(**params, side="Sell")
    except Exception as e:
        print(f"Close position error: {str(e)}")


def take_profit(qty_tp):
    global position
    try:
        params = {
            "category": "linear",
            "symbol": symbol,
            "orderType": "Market",
            "qty": str(qty_tp),
            "timeInForce": "GTC",
            "reduceOnly": True
        }
        if position == 'LONG':
            print(f"{datetime.now()} - TAKE PROFIT {qty_tp} USDT")
            session.place_order(**params, side="Sell")
        elif position == 'SHORT':
            print(f"{datetime.now()} - TAKE PROFIT {qty_tp} USDT")
            session.place_order(**params, side="Buy")
    except Exception as e:
        print(f"Take profit error: {str(e)}")


def stop_loss():
    global position, status
    try:
        params = {
            "category": "linear",
            "symbol": symbol,
            "orderType": "Market",
            "qty": str(qty),
            "timeInForce": "GTC",
            "reduceOnly": True
        }
        if position == 'LONG':
            print(f"{datetime.now()} - STOP LOSS {qty} USDT")
            session.place_order(**params, side="Sell")
        elif position == 'SHORT':
            print(f"{datetime.now()} - STOP LOSS {qty} USDT")
            session.place_order(**params, side="Buy")
        position = None
        status = None
    except Exception as e:
        print(f"Stop loss error: {str(e)}")


# ---------- EMA (1H) ----------
def add_ema(df, fast=ema_fast, slow=ema_slow):
    df['ema_fast'] = df['close'].ewm(span=fast, adjust=False).mean()
    df['ema_slow'] = df['close'].ewm(span=slow, adjust=False).mean()
    return df


def check_ema_cross(df):
    """Свежее пересечение EMA на последнем баре 1H"""
    if df is None or len(df) < 3:
        return False, False
    prev_fast = df['ema_fast'].iloc[-2]
    prev_slow = df['ema_slow'].iloc[-2]
    curr_fast = df['ema_fast'].iloc[-1]
    curr_slow = df['ema_slow'].iloc[-1]

    cross_up = prev_fast <= prev_slow and curr_fast > curr_slow
    cross_down = prev_fast >= prev_slow and curr_fast < curr_slow
    return cross_up, cross_down


# ---------- MACD (4H) ----------
def calculate_macd(df, fast=macd_fast, slow=macd_slow, signal=macd_signal):
    df['EMA12'] = df['close'].ewm(span=fast, adjust=False).mean()
    df['EMA26'] = df['close'].ewm(span=slow, adjust=False).mean()
    df['MACD'] = df['EMA12'] - df['EMA26']
    df['Signal'] = df['MACD'].ewm(span=signal, adjust=False).mean()
    df['Hist'] = df['MACD'] - df['Signal']
    return df


def get_macd_state(df):
    """BULL если MACD > Signal (бычье), иначе BEAR"""
    if df is None or len(df) < 2:
        return None
    return 'BULL' if df['MACD'].iloc[-1] > df['Signal'].iloc[-1] else 'BEAR'


def check_macd_cross(df):
    """Свежее пересечение MACD на последнем баре 4H (если нужен строгий крест)"""
    if df is None or len(df) < 3:
        return False, False
    prev_macd = df['MACD'].iloc[-2]
    prev_signal = df['Signal'].iloc[-2]
    curr_macd = df['MACD'].iloc[-1]
    curr_signal = df['Signal'].iloc[-1]

    cross_up = prev_macd <= prev_signal and curr_macd > curr_signal
    cross_down = prev_macd >= prev_signal and curr_macd < curr_signal
    return cross_up, cross_down


# ---------- SuperTrend (1H) ----------
def calculate_supertrend(high, low, close, lookback=10, multiplier=3):
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
            if (upper_band.iloc[i] < final_upper.iloc[i-1]) or (close.iloc[i-1] > final_upper.iloc[i-1]):
                final_upper.iloc[i] = upper_band.iloc[i]
            else:
                final_upper.iloc[i] = final_upper.iloc[i-1]
            if (lower_band.iloc[i] > final_lower.iloc[i-1]) or (close.iloc[i-1] < final_lower.iloc[i-1]):
                final_lower.iloc[i] = lower_band.iloc[i]
            else:
                final_lower.iloc[i] = final_lower.iloc[i-1]

    supertrend = pd.Series(index=close.index, dtype=float)
    for i in range(len(supertrend)):
        if i == 0:
            supertrend.iloc[i] = final_upper.iloc[i]
        else:
            if supertrend.iloc[i-1] == final_upper.iloc[i-1] and close.iloc[i] < final_upper.iloc[i]:
                supertrend.iloc[i] = final_upper.iloc[i]
            elif supertrend.iloc[i-1] == final_upper.iloc[i-1] and close.iloc[i] > final_upper.iloc[i]:
                supertrend.iloc[i] = final_lower.iloc[i]
            elif supertrend.iloc[i-1] == final_lower.iloc[i-1] and close.iloc[i] > final_lower.iloc[i]:
                supertrend.iloc[i] = final_lower.iloc[i]
            elif supertrend.iloc[i-1] == final_lower.iloc[i-1] and close.iloc[i] < final_lower.iloc[i]:
                supertrend.iloc[i] = final_upper.iloc[i]
            else:
                supertrend.iloc[i] = supertrend.iloc[i-1]

    uptrend = pd.Series(index=supertrend.index, dtype=float)
    downtrend = pd.Series(index=supertrend.index, dtype=float)
    for i in range(len(supertrend)):
        if close.iloc[i] > supertrend.iloc[i]:
            uptrend.iloc[i] = supertrend.iloc[i]
            downtrend.iloc[i] = np.nan
        else:
            uptrend.iloc[i] = np.nan
            downtrend.iloc[i] = supertrend.iloc[i]

    return supertrend, uptrend, downtrend


def get_supertrend_direction(df):
    return 'GREEN' if df['close'].iloc[-1] > df['supertrend'].iloc[-1] else 'RED'


# ---------- Telegram ----------
def send_telegram_alert(df_1h, df_4h, st_1h, macd_state):
    try:
        message = (
            f"📊 *Trade Signal*\n"
            f"Time: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`\n"
            f"Symbol: *{symbol}*\n"
            f"Position: `{position}`\n"
            f"Price: `{df_1h['close'].iloc[-1]:.5f}`\n"
            f"1H EMA{ema_fast}: `{df_1h['ema_fast'].iloc[-1]:.5f}`\n"
            f"1H EMA{ema_slow}: `{df_1h['ema_slow'].iloc[-1]:.5f}`\n"
            f"1H SuperTrend: `{st_1h}`\n"
            f"4H MACD: `{df_4h['MACD'].iloc[-1]:.5f}`\n"
            f"4H Signal: `{df_4h['Signal'].iloc[-1]:.5f}`\n"
            f"4H MACD state: `{macd_state}`\n"
        )
        bot.send_message(TELEGRAM_CHAT_ID, message, parse_mode='Markdown')
    except Exception as e:
        print(f"Telegram send error: {e}")


# ---------- Основной цикл ----------
def main_loop():
    global position, status

    position = get_current_position()
    print(f"Initial position: {position}")

    while True:
        try:
            df_1h = get_historical_data()
            df_4h = get_historical_data_4h()

            if df_1h is None or df_4h is None:
                time.sleep(5)
                continue

            # --- 1H: EMA + SuperTrend ---
            df_1h = add_ema(df_1h, ema_fast, ema_slow)
            cross_up_1h, cross_down_1h = check_ema_cross(df_1h)

            df_1h['supertrend'], df_1h['uptrend'], df_1h['downtrend'] = calculate_supertrend(
                df_1h['high'], df_1h['low'], df_1h['close'], st_lookback, st_multiplier
            )
            st_1h = get_supertrend_direction(df_1h)

            # --- 4H: MACD ---
            df_4h = calculate_macd(df_4h)
            macd_state = get_macd_state(df_4h)  # BULL / BEAR

            # Если нужен именно свежий крест MACD на 4H — раскомментируйте:
            # macd_cross_up_4h, macd_cross_down_4h = check_macd_cross(df_4h)
            # и в условиях ниже замените macd_state == 'BULL' на macd_cross_up_4h,
            # macd_state == 'BEAR' на macd_cross_down_4h

            pnl = get_unrealized_pnl_percentage() or 0.0

            # ====== STOP LOSS ======
            if position == 'LONG' and pnl <= stop_loss_pct:
                stop_loss()
                send_telegram_alert(df_1h, df_4h, st_1h, macd_state)
            elif position == 'SHORT' and pnl <= stop_loss_pct:
                stop_loss()
                send_telegram_alert(df_1h, df_4h, st_1h, macd_state)

            # ====== LONG ======
            elif (position != 'LONG'
                  and cross_up_1h
                  and st_1h == 'GREEN'
                  and macd_state == 'BULL'):
                close_position('SELL')
                execute_trade('BUY')
                status = None
                send_telegram_alert(df_1h, df_4h, st_1h, macd_state)

            elif position == 'LONG' and status is None and pnl >= 4.0:
                take_profit(30)
                status = 'FIRST_TAKE_PROFIT'
            elif position == 'LONG' and status == 'FIRST_TAKE_PROFIT' and pnl >= 8.0:
                take_profit(5)
                status = 'SECOND_TAKE_PROFIT'
            elif position == 'LONG' and status == 'SECOND_TAKE_PROFIT' and pnl >= 12.0:
                take_profit(3)
                status = 'THIRD_TAKE_PROFIT'
            elif position == 'LONG' and status == 'THIRD_TAKE_PROFIT' and pnl >= 16.0:
                take_profit(2)
                status = None
                position = None

            # ====== SHORT ======
            elif (position != 'SHORT'
                  and cross_down_1h
                  and st_1h == 'RED'
                  and macd_state == 'BEAR'):
                close_position('BUY')
                execute_trade('SELL')
                status = None
                send_telegram_alert(df_1h, df_4h, st_1h, macd_state)

            elif position == 'SHORT' and status is None and pnl >= 4.0:
                take_profit(30)
                status = 'FIRST_TAKE_PROFIT'
            elif position == 'SHORT' and status == 'FIRST_TAKE_PROFIT' and pnl >= 8.0:
                take_profit(5)
                status = 'SECOND_TAKE_PROFIT'
            elif position == 'SHORT' and status == 'SECOND_TAKE_PROFIT' and pnl >= 12.0:
                take_profit(3)
                status = 'THIRD_TAKE_PROFIT'
            elif position == 'SHORT' and status == 'THIRD_TAKE_PROFIT' and pnl >= 16.0:
                take_profit(2)
                status = None
                position = None

            # ====== Вывод состояния ======
            print(f"\n{datetime.now()}")
            print(f"Symbol: {symbol}")
            print(f"Position: {position}")
            print(f"PnL %: {pnl:.2f}")
            print(f"1H cross_up: {cross_up_1h} | cross_down: {cross_down_1h}")
            print(f"1H EMA{ema_fast}: {df_1h['ema_fast'].iloc[-1]:.5f} | EMA{ema_slow}: {df_1h['ema_slow'].iloc[-1]:.5f}")
            print(f"1H SuperTrend: {st_1h}")
            print(f"4H MACD: {df_4h['MACD'].iloc[-1]:.5f} | Signal: {df_4h['Signal'].iloc[-1]:.5f}")
            print(f"4H MACD state: {macd_state}")
            print(f"Last close: {df_1h['close'].iloc[-1]:.5f}")

            time.sleep(5)

        except KeyboardInterrupt:
            print("Strategy stopped by user")
            break
        except Exception as e:
            print(f"Main loop error: {str(e)}")
            time.sleep(1)


if __name__ == "__main__":
    try:
        print("Testing connection...")
        balance = session.get_wallet_balance(accountType="UNIFIED")
        print("Balance check successful!")
        print("Available balance:", balance['result']['list'][0]['coin'][0]['availableToWithdraw'])
        main_loop()
    except Exception as e:
        print(f"Init failed: {str(e)}")