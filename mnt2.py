import os
import time
import logging
from decimal import Decimal, ROUND_DOWN

import pandas as pd
from pybit.unified_trading import HTTP
from ta.momentum import StochRSIIndicator
from ta.volatility import AverageTrueRange
from ta.trend import EMAIndicator

# =========================
# 1. НАСТРОЙКИ
# =========================
CATEGORY = "linear"                 # USDT-перпетуалы Bybit
SYMBOL = "BTCUSDT"
INTERVAL = "15"                     # 15 минут (Bybit: "1","3","5","15","30",...)
KLINES_LIMIT = 200

STOCH_RSI_PERIOD = 14
STOCH_PERIOD = 14
STOCH_SMOOTH_K = 3
STOCH_SMOOTH_D = 3
ATR_PERIOD = 14
ATR_SMA_PERIOD = 20
EMA_PERIOD = 200

RISK_PER_TRADE = 0.1               # 1% от баланса
ATR_STOP_MULT = 1.5
TAKE_PROFIT_R = 2.0
LEVERAGE = 3                        # не выше 3x для mean-reversion логики

# Инициализация клиента pybit v5
API_KEY = "zXhDcOWNVq26WchFyX"
API_SECRET = "6G0junTz5PbXtkZik68nmlfzVDiCAJp1oBvj"

session = HTTP(
    testnet=False,                   # testnet=False для реальной торговли
    api_key=API_KEY,
    api_secret=API_SECRET,
)

# Устанавливаем плечо (one-way mode: buyLeverage == sellLeverage)
session.set_leverage(
    category=CATEGORY,
    symbol=SYMBOL,
    buyLeverage=str(LEVERAGE),
    sellLeverage=str(LEVERAGE),
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")


# =========================
# 2. ЗАГРУЗКА ДАННЫХ И РАСЧЁТ ИНДИКАТОРОВ
# =========================
def fetch_klines() -> pd.DataFrame:
    """
    Загружает свечи с Bybit.
    В pybit v5 используется session.get_kline(category="linear", ...).
    """
    resp = session.get_kline(
        category=CATEGORY,
        symbol=SYMBOL,
        interval=INTERVAL,
        limit=KLINES_LIMIT,
    )

    if resp.get("retCode") != 0:
        raise RuntimeError(f"Bybit get_kline error: {resp}")

    raw = resp["result"]["list"]
    # Bybit возвращает список в порядке: [start, open, high, low, close, volume, turnover]
    df = pd.DataFrame(raw, columns=[
        "start", "open", "high", "low", "close", "volume", "turnover"
    ])
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = df[col].astype(float)

    # Bybit отдаёт свечи от новых к старым — разворачиваем
    df = df.iloc[::-1].reset_index(drop=True)
    return df


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df["ema200"] = EMAIndicator(close=df["close"], window=EMA_PERIOD).ema_indicator()

    df["atr"] = AverageTrueRange(
        high=df["high"], low=df["low"], close=df["close"], window=ATR_PERIOD
    ).average_true_range()
    df["atr_sma"] = df["atr"].rolling(ATR_SMA_PERIOD).mean()

    stoch = StochRSIIndicator(
        close=df["close"],
        window=STOCH_RSI_PERIOD,
        smooth1=STOCH_SMOOTH_K,
        smooth2=STOCH_SMOOTH_D,
    )
    df["stoch_k"] = stoch.stochrsi_k() * 100
    df["stoch_d"] = stoch.stochrsi_d() * 100

    return df


# =========================
# 3. ЛОГИКА СИГНАЛОВ
# =========================
def get_signal(df: pd.DataFrame):
    if len(df) < max(EMA_PERIOD, ATR_SMA_PERIOD, STOCH_RSI_PERIOD + 10):
        return None

    prev = df.iloc[-2]      # последний закрытый бар
    before = df.iloc[-3]    # предыдущий закрытый бар

    # Фильтр волатильности
    if not (prev["atr"] > prev["atr_sma"]):
        return None

    cross_up = (before["stoch_k"] <= before["stoch_d"]) and (prev["stoch_k"] > prev["stoch_d"])
    cross_down = (before["stoch_k"] >= before["stoch_d"]) and (prev["stoch_k"] < prev["stoch_d"])

    # LONG: пересечение вверх в зоне <20 + цена выше EMA200
    if cross_up and prev["stoch_k"] < 20 and prev["stoch_d"] < 20 and prev["close"] > prev["ema200"]:
        return "LONG"

    # SHORT: пересечение вниз в зоне >80 + цена ниже EMA200
    if cross_down and prev["stoch_k"] > 80 and prev["stoch_d"] > 80 and prev["close"] < prev["ema200"]:
        return "SHORT"

    return None


# =========================
# 4. РАЗМЕР ПОЗИЦИИ И ОКРУГЛЕНИЕ
# =========================
def get_qty_step() -> Decimal:
    """Шаг количества из lotSizeFilter (Bybit v5: qtyStep)."""
    resp = session.get_instruments_info(category=CATEGORY, symbol=SYMBOL)
    if resp.get("retCode") != 0:
        raise RuntimeError(f"get_instruments_info error: {resp}")
    item = resp["result"]["list"][0]
    return Decimal(item["lotSizeFilter"]["qtyStep"])


def get_available_balance() -> float:
    """Доступный баланс USDT на Unified Trading Account."""
    resp = session.get_wallet_balance(accountType="UNIFIED", coin="USDT")
    if resp.get("retCode") != 0:
        raise RuntimeError(f"get_wallet_balance error: {resp}")
    # Структура ответа v5: result.list[0].coin[0].availableToWithdraw / walletBalance
    account = resp["result"]["list"][0]
    for c in account.get("coin", []):
        if c.get("coin") == "USDT":
            return float(c.get("availableToWithdraw") or c.get("walletBalance") or 0)
    return 0.0


def safe_qty(qty: float, step: Decimal) -> str:
    return str(Decimal(str(qty)).quantize(step, rounding=ROUND_DOWN))


def calc_position_size(entry_price: float, stop_price: float) -> str:
    balance = get_available_balance()
    risk_usdt = balance * RISK_PER_TRADE
    risk_per_unit = abs(entry_price - stop_price)
    if risk_per_unit <= 0:
        raise ValueError("Нулевое расстояние до стопа")
    raw_qty = risk_usdt / risk_per_unit
    return safe_qty(raw_qty, get_qty_step())


# =========================
# 5. ИСПОЛНЕНИЕ ОРДЕРА (Bybit: SL/TP прямо в ордере)
# =========================
def execute_signal(signal: str, df: pd.DataFrame):
    last = df.iloc[-2]
    price = last["close"]
    atr = last["atr"]

    if signal == "LONG":
        side = "Buy"
        stop_price = price - ATR_STOP_MULT * atr
        tp_price = price + TAKE_PROFIT_R * (price - stop_price)
    elif signal == "SHORT":
        side = "Sell"
        stop_price = price + ATR_STOP_MULT * atr
        tp_price = price - TAKE_PROFIT_R * (stop_price - price)
    else:
        return

    qty = calc_position_size(price, stop_price)

    # Округление цен до tickSize (для BTCUSDT на Bybit — 0.1 или 0.01; уточняйте через instruments-info)
    stop_price = round(stop_price, 1)
    tp_price = round(tp_price, 1)

    logging.info(f"Сигнал: {signal} | price={price} | qty={qty} | SL={stop_price} | TP={tp_price}")

    resp = session.place_order(
        category=CATEGORY,
        symbol=SYMBOL,
        side=side,
        orderType="Market",
        qty=qty,
        stopLoss=str(stop_price),
        takeProfit=str(tp_price),
        tpslMode="Full",            # Full = закрыть всю позицию по TP/SL
        slTriggerBy="MarkPrice",    # триггер по Mark Price (аналог workingType="MARK_PRICE")
        tpTriggerBy="MarkPrice",
        positionIdx=0,              # 0 = one-way mode
    )

    if resp.get("retCode") != 0:
        logging.error(f"place_order error: {resp}")
    else:
        logging.info(f"Ордер размещён: {resp['result']}")


# =========================
# 6. ОСНОВНОЙ ЦИКЛ
# =========================
def run():
    logging.info("Стратегия Bybit запущена.")
    while True:
        try:
            df = fetch_klines()
            df = add_indicators(df)
            signal = get_signal(df)

            if signal:
                execute_signal(signal, df)
            else:
                logging.info("Сигнала нет. Ожидание следующей свечи.")

        except Exception as e:
            logging.error(f"Ошибка: {e}", exc_info=True)

        # 15m = 900 секунд; спим до следующей свечи
        time.sleep(900)


if __name__ == "__main__":
    run()