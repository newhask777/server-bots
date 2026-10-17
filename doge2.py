import pandas as pd
from pybit.unified_trading import HTTP
import time
from datetime import datetime
import numpy as np
import telebot
import os
import signal as trigger
import sys
import os

# Bybit api tokens
API_KEY = 'zXhDcOWNVq26WchFyX'
API_SECRET = '6G0junTz5PbXtkZik68nmlfzVDiCAJp1oBvj'

# Telegram api tokens
TELEGRAM_BOT_TOKEN = '8968569374:AAGW76iTBj-dcA6hmQ3EgkO5pwbExNAuijA'
TELEGRAM_CHAT_ID = '5650732610'

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)

# Start HTTP session
session = HTTP(
    api_key=API_KEY,
    api_secret=API_SECRET
)

# Possition settings params
symbol = 'DOGEUSDT'
timeframe = 60
qty = 400
min_macd_dif = 0.0005
position = None
status = None

def get_historical_data():
    """Получение и обработка исторических данных"""
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
    df['close'] = df['close'].astype(float)
    return df

def get_historical_data_4h():
    """Получение и обработка исторических данных"""
    resp = session.get_kline(
        category="linear",
        symbol=symbol,
        interval=240,
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
    df['close'] = df['close'].astype(float)
    return df

def get_current_position():
    """Получение текущей позиции с биржи"""
    try:
        response = session.get_positions(
            category="linear",
            symbol=symbol,
        )
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
            print("Нет открытых позиций.")
            return
        
        for pos in positions:
            size = float(pos["size"])
            if size == 0:
                continue
            
            unrealized_pnl = float(pos["unrealisedPnl"])
            avg_entry_price = float(pos["avgPrice"])
            position_value = float(pos["positionValue"])
            
            if position_value > 0:
                pnl_percent = (unrealized_pnl / position_value) * 1000
            else:
                pnl_percent = 0.0
            
            print(f"Символ: {symbol}")
            print(f"  Нереализованный PnL: {unrealized_pnl:.6f} USDT")
            print(f"  PnL в процентах: {pnl_percent:.2f}%")
            print("-" * 40)

            return pnl_percent
            
    except Exception as e:
        print(f"Ошибка: {e}")

def execute_trade(signal):
    global position, last_trade_time
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
    global position, last_trade_time
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

def take_profit(qty):
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

        if position == 'LONG':
            print(f"{datetime.now()} - TAKE PROFIT {qty} USDT")
            session.place_order(**params, side="Sell")

        elif position == 'SHORT':
            print(f"{datetime.now()} - TAKE PROFIT {qty} USDT")
            session.place_order(**params, side="Buy")

    except Exception as e:
        print(f"Close position error: {str(e)}")

def stop_loss():
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

        if position == 'LONG':
            print(f"{datetime.now()} - STOP LOSS {qty} USDT")
            session.place_order(**params, side="Sell")
            position = None

        elif position == 'SHORT':
            print(f"{datetime.now()} - STOP LOSS {qty} USDT")
            session.place_order(**params, side="Buy")
            position = None

    except Exception as e:
        print(f"Stop loss error: {str(e)}")

"""
MACD
"""
def calculate_macd(df):
    if df is None or len(df) < 50:
        print("Not enough data for MACD calculation")
        return None
    
    df['EMA12'] = df['close'].ewm(span=12, adjust=False).mean()
    df['EMA26'] = df['close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = df['EMA12'] - df['EMA26']
    df['Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    return df

def check_crossover(df):
    global min_macd_dif
    if df is None or len(df) < 3:
        return False, False
    
    prev_macd = df['MACD'].iloc[-3]
    prev_signal = df['Signal'].iloc[-3]   
    mid_macd = df['MACD'].iloc[-2]
    mid_signal = df['Signal'].iloc[-2]   
    current_macd = df['MACD'].iloc[-1]
    current_signal = df['Signal'].iloc[-1]

    hist = current_macd - current_signal
    hist_above_zero = hist >= 0
    hist_under_zero = hist <= 0

    above_zero = current_macd > 0 and current_signal > 0
    under_zero = current_macd < 0 and current_signal < 0
    print(above_zero)
    print(under_zero)
    
    if above_zero:
        crossover = (
            #prev_macd < prev_signal and 
            current_macd > current_signal and
            (current_macd - current_signal) >= min_macd_dif
        )
        crossunder = (
            #prev_macd > prev_signal and 
            current_macd < current_signal and
            (current_signal - current_macd) >= min_macd_dif
        )
        print('above')
    elif under_zero:
        min_macd_dif = -min_macd_dif
        crossover = (
            #prev_macd < prev_signal and 
            current_macd > current_signal and
            (current_macd - current_signal) >= min_macd_dif
        )
        crossunder = (
            #prev_macd > prev_signal and 
            current_macd < current_signal and
            (current_signal - current_macd) >= min_macd_dif
        )
        print('under')
    else:
        crossover = None
        crossunder = None

    return crossover, crossunder

"""
RSI
"""
def calculate_rsi_2(prices, period=14):
    deltas = np.diff(prices)
    seed = deltas[:period]
    
    up = seed[seed >= 0].sum() / period
    down = -seed[seed < 0].sum() / period
    rs = up / down if down != 0 else 0
    rsi = np.zeros_like(prices)
    rsi[:period] = 100. - 100. / (1. + rs)
    
    for i in range(period, len(prices)):
        delta = deltas[i-1]
        if delta > 0:
            upval = delta
            downval = 0.
        else:
            upval = 0.
            downval = -delta
            
        up = (up * (period - 1) + upval) / period
        down = (down * (period - 1) + downval) / period
        rs = up / down if down != 0 else 0
        rsi[i] = 100. - 100. / (1. + rs)
    
    return rsi

"""
Stoch RSI
"""
def calculate_stoch_rsi(rsi, k_period=3, d_period=3, stoch_period=14):
    stoch_rsi = np.zeros_like(rsi)
    stoch_k = np.zeros_like(rsi)
    stoch_d = np.zeros_like(rsi)
    
    for i in range(stoch_period, len(rsi)):
        rsi_window = rsi[i-stoch_period+1:i+1]
        current_rsi = rsi[i]
        lowest_low = np.min(rsi_window)
        highest_high = np.max(rsi_window)
        
        if highest_high - lowest_low != 0:
            stoch_rsi[i] = (current_rsi - lowest_low) / (highest_high - lowest_low) * 100
        else:
            stoch_rsi[i] = 50
    
    for i in range(k_period-1, len(stoch_rsi)):
        stoch_k[i] = np.mean(stoch_rsi[i-k_period+1:i+1])
    
    for i in range(k_period + d_period - 2, len(stoch_k)):
        stoch_d[i] = np.mean(stoch_k[i-d_period+1:i+1])
    
    return stoch_rsi, stoch_k, stoch_d

"""
Supertrend
"""
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

"""
Новые функции для определения боковика
"""
def is_supertrend_flat(supertrend_series, lookback=10, tolerance=0.0):
    """Проверяет, был ли Supertrend неизменным последние lookback свечей."""
    if len(supertrend_series) < lookback:
        return False
    window = supertrend_series.iloc[-lookback:]
    if tolerance == 0.0:
        return window.nunique() == 1
    return (window.max() - window.min()) <= tolerance

def is_atr_low(df, atr_period=14, ma_period=20, threshold=0.7):
    """Проверяет, находится ли ATR ниже своего скользящего среднего на threshold."""
    high = df['high'].astype(float)
    low = df['low'].astype(float)
    close = df['close'].astype(float)
    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.ewm(span=atr_period, adjust=False).mean()
    atr_ma = atr.rolling(window=ma_period).mean()
    if len(atr) < ma_period:
        return False
    current_atr = atr.iloc[-1]
    current_ma = atr_ma.iloc[-1]
    if pd.isna(current_ma) or current_ma == 0:
        return False
    return current_atr < current_ma * threshold

def is_sideways(df, supertrend_series, supertrend_lookback=10, supertrend_tolerance=0.0,
                atr_period=14, atr_ma_period=20, atr_threshold=0.7,
                use_supertrend=True, use_atr=True):
    """Определяет боковик по Supertrend и/или ATR."""
    flat_st = False
    low_atr = False
    if use_supertrend:
        flat_st = is_supertrend_flat(supertrend_series, supertrend_lookback, supertrend_tolerance)
    if use_atr:
        low_atr = is_atr_low(df, atr_period, atr_ma_period, atr_threshold)
    
    if use_supertrend and use_atr:
        return flat_st or low_atr  # если любой из признаков указывает на боковик
    elif use_supertrend:
        return flat_st
    elif use_atr:
        return low_atr
    else:
        return False

"""
ADX
"""
def calculate_adx(df, period=14):
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
        np.maximum(data['high'] - data['high_prev'], 0),
        0
    )
    data['minus_dm'] = np.where(
        (data['low_prev'] - data['low']) > (data['high'] - data['high_prev']),
        np.maximum(data['low_prev'] - data['low'], 0),
        0
    )
    
    data['smoothed_tr'] = data['tr'].rolling(window=period, min_periods=period).mean()
    data['smoothed_plus_dm'] = data['plus_dm'].rolling(window=period, min_periods=period).mean()
    data['smoothed_minus_dm'] = data['minus_dm'].rolling(window=period, min_periods=period).mean()
    
    for i in range(period, len(data)):
        prev_idx = data.index[i-1]
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

    return data.drop([
        'high_prev', 'low_prev', 'close_prev',
        'tr1', 'tr2', 'tr3', 'tr',
        'plus_dm', 'minus_dm',
        'smoothed_tr', 'smoothed_plus_dm', 'smoothed_minus_dm', 'dx'
    ], axis=1)

"""
Telegram message
"""
def send_telegram_alert(rsi):
    try:
        message = (
            f"📊 *Trade Update*\n"
            f"Time: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`\n"
            f"Symbol: *{symbol}*\n"
            f"Position: `{position}`\n"
            f"MACD Diff: `{min_macd_dif:.6f}`\n"
            f"RSI: `{rsi[-1]}`"
        )
        bot.send_message(TELEGRAM_CHAT_ID, message, parse_mode='Markdown')
    except Exception as e:
        print(f"Telegram send error: {e}")

def main_loop():
    global min_macd_dif
    global position
    global status
    
    position = get_current_position()
    print(f"Initial position: {position}")
    
    while True:
        try:
            start_time = time.time()
            df = get_historical_data()
            df_4 = get_historical_data_4h()
            
            if df is not None:
                df_4h = calculate_macd(df_4)
                
                if df is not None:
                    crossover, crossunder = check_crossover(df_4h)

                    pnl = get_unrealized_pnl_percentage()
                    if pnl == None:
                        pnl = 0.0

                    rsi_2 = calculate_rsi_2(df['close'].values, period=14)
                    stoch_rsi, stoch_k, stoch_d = calculate_stoch_rsi(rsi_2)
                    print(stoch_k[-1])

                    lookback = 10
                    multiplier = 3
                    trend = None

                    df['supertrend'], df['uptrend'], df['downtrend'] = calculate_supertrend(
                        df['high'], df['low'], df['close'], lookback, multiplier
                    )

                    # Определяем текущий тренд
                    last_row = df.iloc[-1]
                    if last_row['close'] > last_row['supertrend']:
                        print(f"\nТекущий тренд: ВОСХОДЯЩИЙ (цена {last_row['close']} > SuperTrend {last_row['supertrend']})")
                        trend = "Long"
                    else:
                        print(f"\nТекущий тренд: НИСХОДЯЩИЙ (цена {last_row['close']} < SuperTrend {last_row['supertrend']})")
                        trend = "Short"

                    # ====== ПРОВЕРКА НА БОКОВИК ======
                    sideways = is_sideways(
                        df, df['supertrend'],
                        supertrend_lookback=10,
                        supertrend_tolerance=0.0,
                        atr_period=14,
                        atr_ma_period=20,
                        atr_threshold=0.7,
                        use_supertrend=True,
                        use_atr=True
                    )
                    print(f"Sideways: {sideways}")
                    # =================================

                    # ====== STOP LOSS 4% ======
                    if position == 'LONG' and pnl <= -50.0:
                        stop_loss()
                        send_telegram_alert(rsi_2)
                    elif position == 'SHORT' and pnl <= -50.0:
                        stop_loss()
                        send_telegram_alert(rsi_2)
                    # ==========================

                    # LONG position logic
                    if crossover and position != 'LONG' and trend == "Long" and stoch_k[-1] > 80 and not sideways:
                        close_position('BUY')
                        execute_trade('BUY')
                        send_telegram_alert(rsi_2)
                            
                    elif position == 'LONG' and status == None and pnl >= 4.0:
                        take_profit(qty=300)
                        status = 'FIRST_TAKE_PROFIT'

                    elif position == 'LONG' and status == 'FIRST_TAKE_PROFIT' and pnl >= 8.0:
                        take_profit(qty=70)
                        status = 'SECOND_TAKE_PROFIT'

                    elif position == 'LONG' and status == 'SECOND_TAKE_PROFIT' and pnl >= 12.0:
                        take_profit(qty=20)
                        status = 'THIRD_TAKE_PROFIT'

                    elif position == 'LONG' and status == 'THIRD_TAKE_PROFIT' and pnl >= 16.0:
                        take_profit(qty=10)
                        status = None

                    # SHORT position logic
                    elif crossunder and position != 'SHORT' and trend == "Short" and stoch_k[-1] < 20 and not sideways:
                        close_position('SELL')
                        execute_trade('SELL')
                        send_telegram_alert(rsi_2)
                            
                    elif position == 'SHORT' and status == None and pnl >= 4.0:
                        take_profit(qty=300)
                        status = 'FIRST_TAKE_PROFIT'

                    elif position == 'SHORT' and status == 'FIRST_TAKE_PROFIT' and pnl >= 8.0:
                        take_profit(qty=70)
                        status = 'SECOND_TAKE_PROFIT'

                    elif position == 'SHORT' and status == 'SECOND_TAKE_PROFIT' and pnl >= 12.0:
                        take_profit(qty=20)
                        status = 'THIRD_TAKE_PROFIT'

                    elif position == 'SHORT' and status == 'THIRD_TAKE_PROFIT' and pnl >= 16.0:
                        take_profit(qty=10)
                        status = None

                    # Вывод информации о состоянии
                    print(f"\n{datetime.now()}")
                    print(f"Symbol: {symbol}")
                    print(f"Position: {position}")
                    print(f"Diff: {min_macd_dif}")
                    print(f"Cупер тренд: {trend}")
                    print(f"UpperTrend: {df['uptrend'].values[-1]}")
                    print(f"DownTrend: {df['downtrend'].values[-1]}")
                    print(f"Stochastick RSI fast: {stoch_k[1]}")
                    print(f"Stochastick RSI slow: {stoch_d[-1]}")
                    
                    if len(df) > 0:
                        print(f"Last close: {df['close'].iloc[-1]:.5f}")
                        print(f"MACD: {df_4h['MACD'].iloc[-1]:.5f} | Signal: {df_4h['Signal'].iloc[-1]:.5f}")
                        print(f"Middle MACD: {df_4h['MACD'].iloc[-2]:.5f} | Middle Signal: {df_4h['Signal'].iloc[-2]:5f}")
            
            time.sleep(1)
            
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