from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Deque, Dict, List, Sequence, Tuple


@dataclass(frozen=True)
class TripleSignal:
    signal: str
    ema_trend: float
    stoch_k: float
    stoch_d: float
    macd_hist: float
    atr: float
    rsi: float
    bar_time_current: int
    bar_time_closed: int
    filter_reason: str


def ema_series(prices: Sequence[float], period: int) -> List[float]:
    """Hitung Exponential Moving Average (EMA) untuk seluruh seri."""
    if period <= 0:
        raise ValueError("period must be > 0")
    if not prices:
        return []
    alpha = 2.0 / (float(period) + 1.0)
    ema: List[float] = [float(prices[0])]
    for i in range(1, len(prices)):
        ema.append(alpha * float(prices[i]) + (1.0 - alpha) * ema[-1])
    return ema


def sma_series(values: Sequence[float], period: int) -> List[float]:
    """Hitung Simple Moving Average (SMA) untuk seluruh seri (window berjalan)."""
    n = int(period)
    if n <= 0:
        raise ValueError("period must be > 0")
    if not values:
        return []

    out: List[float] = []
    q: Deque[float] = deque()
    s = 0.0
    for v in values:
        fv = float(v)
        q.append(fv)
        s += fv
        if len(q) > n:
            s -= float(q.popleft())
        out.append(float(s / float(len(q))))
    return out


def stochastic(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    period: int,
    smooth_k: int,
    smooth_d: int,
) -> Tuple[List[float], List[float]]:
    """Hitung Stochastic Oscillator %K dan %D (dengan smoothing SMA)."""
    n = int(period)
    sk = int(smooth_k)
    sd = int(smooth_d)
    if n <= 0 or sk <= 0 or sd <= 0:
        raise ValueError("period/smooth_k/smooth_d must be > 0")
    if not highs or not lows or not closes:
        return [], []
    if not (len(highs) == len(lows) == len(closes)):
        raise ValueError("highs/lows/closes length mismatch")

    raw_k: List[float] = []
    for i in range(len(closes)):
        if i < n - 1:
            raw_k.append(50.0)
            continue

        start = i - n + 1
        window_high = max(float(x) for x in highs[start : i + 1])
        window_low = min(float(x) for x in lows[start : i + 1])
        if window_high == window_low:
            raw_k.append(50.0)
            continue

        c = float(closes[i])
        k = ((c - window_low) / (window_high - window_low)) * 100.0
        if k < 0.0:
            k = 0.0
        elif k > 100.0:
            k = 100.0
        raw_k.append(float(k))

    k_smooth = sma_series(raw_k, sk)
    d_smooth = sma_series(k_smooth, sd)
    return k_smooth, d_smooth


def macd(
    prices: Sequence[float],
    fast: int,
    slow: int,
    signal_period: int,
) -> Tuple[List[float], List[float], List[float]]:
    """
    Hitung MACD line, signal line, dan histogram.

    Returns:
        (macd_line, signal_line, histogram) — semua panjangnya sama dengan prices
    """
    if len(prices) == 0:
        return [], [], []

    ema_fast_vals = ema_series(prices, fast)
    ema_slow_vals = ema_series(prices, slow)

    macd_line = [float(ema_fast_vals[i]) - float(ema_slow_vals[i]) for i in range(len(prices))]

    signal_line = ema_series(macd_line, signal_period)

    histogram = [float(macd_line[i]) - float(signal_line[i]) for i in range(len(macd_line))]

    return macd_line, signal_line, histogram


def rsi_wilder(closes: Sequence[float], period: int) -> List[float]:
    """Hitung RSI menggunakan Wilder smoothing (RMA)."""
    n = int(period)
    if n <= 0:
        raise ValueError("period must be > 0")
    if len(closes) == 0:
        return []
    if len(closes) == 1:
        return [50.0]

    deltas = [float(closes[i]) - float(closes[i - 1]) for i in range(1, len(closes))]
    gains = [max(d, 0.0) for d in deltas]
    losses = [max(-d, 0.0) for d in deltas]

    rsi: List[float] = [50.0]
    avg_gain = 0.0
    avg_loss = 0.0

    if len(deltas) < n:
        for _ in range(1, len(closes)):
            rsi.append(50.0)
        return rsi

    avg_gain = sum(gains[:n]) / float(n)
    avg_loss = sum(losses[:n]) / float(n)

    for _ in range(1, n + 1):
        rsi.append(50.0)

    def _rsi_value(g: float, l: float) -> float:
        if l == 0.0:
            return 100.0 if g > 0.0 else 50.0
        rs = g / l
        return 100.0 - (100.0 / (1.0 + rs))

    rsi[n] = _rsi_value(avg_gain, avg_loss)

    for i in range(n, len(deltas)):
        avg_gain = ((avg_gain * float(n - 1)) + gains[i]) / float(n)
        avg_loss = ((avg_loss * float(n - 1)) + losses[i]) / float(n)
        rsi.append(_rsi_value(avg_gain, avg_loss))

    if len(rsi) != len(closes):
        if len(rsi) > len(closes):
            rsi = rsi[: len(closes)]
        else:
            rsi.extend([rsi[-1]] * (len(closes) - len(rsi)))
    return rsi


def atr_wilder(highs: Sequence[float], lows: Sequence[float], closes: Sequence[float], period: int) -> List[float]:
    """Hitung ATR menggunakan Wilder smoothing."""
    n = int(period)
    if n <= 0:
        raise ValueError("period must be > 0")
    if not highs or not lows or not closes:
        return []
    if not (len(highs) == len(lows) == len(closes)):
        raise ValueError("highs/lows/closes length mismatch")

    trs: List[float] = []
    for i in range(len(closes)):
        h = float(highs[i])
        l = float(lows[i])
        if i == 0:
            tr = h - l
        else:
            pc = float(closes[i - 1])
            tr = max(h - l, abs(h - pc), abs(l - pc))
        trs.append(float(tr))

    atr: List[float] = [float(trs[0])]
    if len(trs) == 1:
        return atr
    if len(trs) <= n:
        for _ in range(1, len(trs)):
            atr.append(float(atr[-1]))
        return atr

    first_atr = sum(trs[1 : n + 1]) / float(n)
    while len(atr) < n:
        atr.append(float(atr[-1]))
    atr.append(float(first_atr))

    prev = float(first_atr)
    for i in range(n + 1, len(trs)):
        prev = ((prev * float(n - 1)) + trs[i]) / float(n)
        atr.append(float(prev))

    if len(atr) != len(trs):
        if len(atr) > len(trs):
            atr = atr[: len(trs)]
        else:
            atr.extend([atr[-1]] * (len(trs) - len(atr)))
    return atr


def is_in_session_wib(unix_ts: int, start_london: int, end_ny: int) -> bool:
    """Cek apakah timestamp berada dalam session yang diizinkan (WIB/UTC+7)."""
    dt_wib = datetime.fromtimestamp(int(unix_ts), tz=timezone.utc) + timedelta(hours=7)
    h = int(dt_wib.hour)
    start = int(start_london)
    end = int(end_ny)
    return start <= h < end


def _hour_wib(unix_ts: int) -> int:
    dt_wib = datetime.fromtimestamp(int(unix_ts), tz=timezone.utc) + timedelta(hours=7)
    return int(dt_wib.hour)


def _hour_in_range(h: int, start: int, end: int) -> bool:
    start = int(start)
    end = int(end)
    h = int(h)
    if start == end:
        return False
    if start < end:
        return start <= h < end
    return h >= start or h < end


def is_in_any_session_wib(unix_ts: int, start1: int, end1: int, start2: int, end2: int) -> bool:
    h = _hour_wib(unix_ts)
    return _hour_in_range(h, start1, end1) or _hour_in_range(h, start2, end2)


def candle_body_ok(bar: Dict[str, Any], ratio: float) -> bool:
    """Validasi candle body: |close-open| >= ratio*(high-low)."""
    o = float(bar["open"])
    c = float(bar["close"])
    h = float(bar["high"])
    l = float(bar["low"])
    rng = h - l
    if rng <= 0.0:
        return False
    body = abs(c - o)
    return body >= float(ratio) * rng


def min_bars_required(
    *,
    entry_model: str,
    breakout_lookback: int,
    breakout_max_age: int,
    ema_trend_period: int,
    stoch_period: int,
    stoch_smooth_k: int,
    stoch_smooth_d: int,
    macd_slow: int,
    macd_signal: int,
    rsi_period: int,
    atr_period: int,
    extra: int = 10,
) -> int:
    """Hitung kebutuhan minimum bars untuk sinyal dan filter (plus buffer)."""
    entry_model = (entry_model or "").strip().upper()
    breakout_need = 0
    if entry_model == "BREAKOUT_RETEST":
        breakout_need = int(breakout_lookback) + int(breakout_max_age) + 3
    elif entry_model == "BREAKOUT_FOLLOWTHROUGH":
        breakout_need = int(breakout_lookback) + 3
    base = max(
        int(breakout_need),
        int(ema_trend_period),
        int(stoch_period) + int(stoch_smooth_k) + int(stoch_smooth_d),
        int(macd_slow) + int(macd_signal),
        int(rsi_period) + 1,
        int(atr_period) + 1,
        5,
    )
    return int(base) + int(extra)


def _entry_breakout_retest(
    *,
    rates: Sequence[Dict[str, Any]],
    idx_curr: int,
    trend: str,
    atr_value: float,
    breakout_lookback: int,
    breakout_max_age: int,
    retest_atr_tolerance: float,
    retest_max_distance_atr: float,
) -> str:
    if trend not in ("BUY", "SELL"):
        return "NONE"
    lb = int(breakout_lookback)
    age = int(breakout_max_age)
    if lb <= 1 or age <= 0:
        return "NONE"
    if idx_curr < (lb + 2):
        return "NONE"
    tol = max(float(retest_atr_tolerance), 0.0) * float(atr_value)
    max_dist = max(float(retest_max_distance_atr), 0.0) * float(atr_value)

    highs = [float(r["high"]) for r in rates]
    lows = [float(r["low"]) for r in rates]
    closes = [float(r["close"]) for r in rates]
    opens = [float(r["open"]) for r in rates]

    start_j = max(lb, idx_curr - int(age))
    breakout_idx = -1
    level = 0.0
    for j in range(idx_curr - 1, start_j - 1, -1):
        if trend == "BUY":
            prev_high = max(highs[j - lb : j])
            if closes[j] > float(prev_high) and closes[j] > opens[j]:
                breakout_idx = j
                level = float(prev_high)
                break
        else:
            prev_low = min(lows[j - lb : j])
            if closes[j] < float(prev_low) and closes[j] < opens[j]:
                breakout_idx = j
                level = float(prev_low)
                break

    if breakout_idx < 0:
        return "NONE"

    o = float(opens[idx_curr])
    c = float(closes[idx_curr])
    h = float(highs[idx_curr])
    l = float(lows[idx_curr])

    if trend == "BUY":
        if c <= float(level):
            return "NONE"
        if l > float(level) + float(tol):
            return "NONE"
        if float(max_dist) > 0.0 and c > float(level) + float(max_dist):
            return "NONE"
        if c <= o:
            return "NONE"
        return "BUY"

    if c >= float(level):
        return "NONE"
    if h < float(level) - float(tol):
        return "NONE"
    if float(max_dist) > 0.0 and c < float(level) - float(max_dist):
        return "NONE"
    if c >= o:
        return "NONE"
    return "SELL"


def _entry_breakout_followthrough(
    *,
    rates: Sequence[Dict[str, Any]],
    idx_curr: int,
    trend: str,
    atr_value: float,
    breakout_lookback: int,
    followthrough_range_atr: float,
    followthrough_body_ratio: float,
    followthrough_max_distance_atr: float,
) -> str:
    if trend not in ("BUY", "SELL"):
        return "NONE"
    lb = int(breakout_lookback)
    if lb <= 1:
        return "NONE"
    if idx_curr < (lb + 2):
        return "NONE"

    highs = [float(r["high"]) for r in rates]
    lows = [float(r["low"]) for r in rates]
    closes = [float(r["close"]) for r in rates]
    opens = [float(r["open"]) for r in rates]

    idx_break = int(idx_curr) - 1
    if idx_break < lb:
        return "NONE"

    level = 0.0
    if trend == "BUY":
        prev_high = max(highs[idx_break - lb : idx_break])
        if not (float(closes[idx_break]) > float(prev_high) and float(closes[idx_break]) > float(opens[idx_break])):
            return "NONE"
        level = float(prev_high)
    else:
        prev_low = min(lows[idx_break - lb : idx_break])
        if not (float(closes[idx_break]) < float(prev_low) and float(closes[idx_break]) < float(opens[idx_break])):
            return "NONE"
        level = float(prev_low)

    o = float(opens[idx_curr])
    c = float(closes[idx_curr])
    h = float(highs[idx_curr])
    l = float(lows[idx_curr])
    rng = float(h) - float(l)
    if rng <= 0.0:
        return "NONE"

    body_ratio = float(abs(c - o) / rng)
    if body_ratio < float(followthrough_body_ratio):
        return "NONE"

    if float(atr_value) > 0.0 and float(rng) < float(followthrough_range_atr) * float(atr_value):
        return "NONE"

    max_dist = max(float(followthrough_max_distance_atr), 0.0) * float(atr_value)

    if trend == "BUY":
        if c <= o:
            return "NONE"
        if c <= float(level):
            return "NONE"
        if float(max_dist) > 0.0 and c > float(level) + float(max_dist):
            return "NONE"
        if c <= float(closes[idx_break]):
            return "NONE"
        return "BUY"

    if c >= o:
        return "NONE"
    if c >= float(level):
        return "NONE"
    if float(max_dist) > 0.0 and c < float(level) - float(max_dist):
        return "NONE"
    if c >= float(closes[idx_break]):
        return "NONE"
    return "SELL"


def _apply_filters(
    *,
    signal: str,
    rsi_value: float,
    ema_slope_value: float,
    bar_time_current: int,
    closed_bar: Dict[str, Any],
    rsi_buy_max: float,
    rsi_sell_min: float,
    candle_body_ratio: float,
    session_start_london_wib: int,
    session_end_ny_wib: int,
    ema_slope_min: float,
    ema_gate1_start_wib: int,
    ema_gate1_end_wib: int,
    ema_gate2_start_wib: int,
    ema_gate2_end_wib: int,
) -> Tuple[str, str]:
    if signal not in ("BUY", "SELL"):
        return "NONE", ""

    if not is_in_session_wib(bar_time_current, session_start_london_wib, session_end_ny_wib):
        return "NONE", "OUT_OF_SESSION"

    if not candle_body_ok(closed_bar, candle_body_ratio):
        return "NONE", "DOJI_CANDLE"

    if signal == "BUY":
        if not (float(rsi_value) < float(rsi_buy_max)):
            return "NONE", "RSI_TOO_HIGH"
    else:
        if not (float(rsi_value) > float(rsi_sell_min)):
            return "NONE", "RSI_TOO_LOW"

    if is_in_any_session_wib(
        int(bar_time_current),
        int(ema_gate1_start_wib),
        int(ema_gate1_end_wib),
        int(ema_gate2_start_wib),
        int(ema_gate2_end_wib),
    ):
        smin = float(ema_slope_min)
        if smin < 0.0:
            smin = 0.0
        if signal == "BUY":
            if float(ema_slope_value) <= float(smin):
                return "NONE", "EMA_SLOPE_GATE_BUY"
        else:
            if float(ema_slope_value) >= -float(smin):
                return "NONE", "EMA_SLOPE_GATE_SELL"

    return signal, ""


def calculate_triple_signal(
    rates: Sequence[Dict[str, Any]],
    *,
    trend_rates_m15: Sequence[Dict[str, Any]],
    entry_model: str,
    breakout_lookback: int,
    breakout_max_age: int,
    retest_atr_tolerance: float,
    retest_max_distance_atr: float,
    followthrough_range_atr: float,
    followthrough_body_ratio: float,
    followthrough_max_distance_atr: float,
    ema_trend_period: int,
    stoch_period: int,
    stoch_smooth_k: int,
    stoch_smooth_d: int,
    stoch_oversold: float,
    stoch_overbought: float,
    stoch_min_gap: float,
    macd_fast: int,
    macd_slow: int,
    macd_signal: int,
    ema_slope_min: float,
    ema_gate1_start_wib: int,
    ema_gate1_end_wib: int,
    ema_gate2_start_wib: int,
    ema_gate2_end_wib: int,
    rsi_period: int,
    rsi_buy_max: float,
    rsi_sell_min: float,
    atr_period: int,
    atr_entry_multiplier: float,
    candle_body_ratio: float,
    session_start_london_wib: int,
    session_end_ny_wib: int,
) -> TripleSignal:
    """Hitung sinyal Triple Confirmation pada event candle baru (mengacu candle closed terakhir)."""
    min_bars = min_bars_required(
        entry_model=str(entry_model),
        breakout_lookback=int(breakout_lookback),
        breakout_max_age=int(breakout_max_age),
        ema_trend_period=int(ema_trend_period),
        stoch_period=int(stoch_period),
        stoch_smooth_k=int(stoch_smooth_k),
        stoch_smooth_d=int(stoch_smooth_d),
        macd_slow=int(macd_slow),
        macd_signal=int(macd_signal),
        rsi_period=int(rsi_period),
        atr_period=int(atr_period),
        extra=10,
    )
    if len(rates) < min_bars:
        raise RuntimeError(f"Bars tidak cukup: butuh >= {min_bars}, dapat {len(rates)}")
    if len(trend_rates_m15) < max(int(ema_trend_period) + 2, 3):
        raise RuntimeError("Bars M15 tidak cukup untuk trend filter")

    closes = [float(r["close"]) for r in rates]
    highs = [float(r["high"]) for r in rates]
    lows = [float(r["low"]) for r in rates]

    ema_trend = ema_series(closes, int(ema_trend_period))
    stoch_k, stoch_d = stochastic(
        highs,
        lows,
        closes,
        int(stoch_period),
        int(stoch_smooth_k),
        int(stoch_smooth_d),
    )
    _, _, macd_hist = macd(closes, int(macd_fast), int(macd_slow), int(macd_signal))
    rsi_series = rsi_wilder(closes, int(rsi_period))
    atr_series = atr_wilder(highs, lows, closes, int(atr_period))

    idx_curr = -2

    k_curr = float(stoch_k[idx_curr])
    d_curr = float(stoch_d[idx_curr])
    hist_curr = float(macd_hist[idx_curr])
    rsi_value = float(rsi_series[idx_curr])
    atr_value = float(atr_series[idx_curr])

    m15_closes = [float(r["close"]) for r in trend_rates_m15]
    m15_ema = ema_series(m15_closes, int(ema_trend_period))
    m15_close_curr = float(m15_closes[-2])
    m15_ema_curr = float(m15_ema[-2])
    m15_ema_prev = float(m15_ema[-3])
    ema_slope_value = float(m15_ema_curr) - float(m15_ema_prev)

    trend = "NONE"
    if m15_close_curr > m15_ema_curr:
        trend = "BUY"
    elif m15_close_curr < m15_ema_curr:
        trend = "SELL"

    signal = "NONE"
    closed_bar = dict(rates[-2])
    entry_model_u = (str(entry_model) or "").strip().upper()
    if entry_model_u == "BREAKOUT_RETEST":
        signal = _entry_breakout_retest(
            rates=rates,
            idx_curr=idx_curr,
            trend=str(trend),
            atr_value=float(atr_value),
            breakout_lookback=int(breakout_lookback),
            breakout_max_age=int(breakout_max_age),
            retest_atr_tolerance=float(retest_atr_tolerance),
            retest_max_distance_atr=float(retest_max_distance_atr),
        )
    elif entry_model_u == "BREAKOUT_FOLLOWTHROUGH":
        signal = _entry_breakout_followthrough(
            rates=rates,
            idx_curr=idx_curr,
            trend=str(trend),
            atr_value=float(atr_value),
            breakout_lookback=int(breakout_lookback),
            followthrough_range_atr=float(followthrough_range_atr),
            followthrough_body_ratio=float(followthrough_body_ratio),
            followthrough_max_distance_atr=float(followthrough_max_distance_atr),
        )
    else:
        rng = float(closed_bar["high"]) - float(closed_bar["low"])
        range_ok = float(atr_value) > 0.0 and rng >= float(atr_entry_multiplier) * float(atr_value)
        candle_dir = "NONE"
        if float(closed_bar["close"]) > float(closed_bar["open"]):
            candle_dir = "BUY"
        elif float(closed_bar["close"]) < float(closed_bar["open"]):
            candle_dir = "SELL"

        if trend in ("BUY", "SELL") and candle_dir == trend and range_ok:
            signal = trend

    bar_time_current = int(rates[-1]["time"])
    bar_time_closed = int(rates[-2]["time"])

    signal, filter_reason = _apply_filters(
        signal=signal,
        rsi_value=float(rsi_value),
        ema_slope_value=float(ema_slope_value),
        bar_time_current=int(bar_time_current),
        closed_bar=closed_bar,
        rsi_buy_max=float(rsi_buy_max),
        rsi_sell_min=float(rsi_sell_min),
        candle_body_ratio=float(candle_body_ratio),
        session_start_london_wib=int(session_start_london_wib),
        session_end_ny_wib=int(session_end_ny_wib),
        ema_slope_min=float(ema_slope_min),
        ema_gate1_start_wib=int(ema_gate1_start_wib),
        ema_gate1_end_wib=int(ema_gate1_end_wib),
        ema_gate2_start_wib=int(ema_gate2_start_wib),
        ema_gate2_end_wib=int(ema_gate2_end_wib),
    )

    return TripleSignal(
        signal=signal,
        ema_trend=float(m15_ema_curr),
        stoch_k=float(k_curr),
        stoch_d=float(d_curr),
        macd_hist=float(hist_curr),
        atr=float(atr_value),
        rsi=float(rsi_value),
        bar_time_current=int(bar_time_current),
        bar_time_closed=int(bar_time_closed),
        filter_reason=filter_reason,
    )


def calculate_triple_signal_at_index(
    rates: Sequence[Dict[str, Any]],
    i: int,
    *,
    stoch_k: Sequence[float],
    stoch_d: Sequence[float],
    macd_hist: Sequence[float],
    rsi: Sequence[float],
    atr: Sequence[float],
    trend_m15_close: Sequence[float],
    trend_m15_ema: Sequence[float],
    entry_model: str,
    breakout_lookback: int,
    breakout_max_age: int,
    retest_atr_tolerance: float,
    retest_max_distance_atr: float,
    followthrough_range_atr: float,
    followthrough_body_ratio: float,
    followthrough_max_distance_atr: float,
    atr_entry_multiplier: float,
    rsi_buy_max: float,
    rsi_sell_min: float,
    candle_body_ratio: float,
    session_start_london_wib: int,
    session_end_ny_wib: int,
    ema_slope_min: float,
    ema_gate1_start_wib: int,
    ema_gate1_end_wib: int,
    ema_gate2_start_wib: int,
    ema_gate2_end_wib: int,
) -> TripleSignal:
    """Hitung sinyal+filter pada event candle baru (index i) untuk kebutuhan backtest."""
    if i < 2:
        raise RuntimeError("Index i terlalu kecil untuk menghitung signal (butuh >= 2)")

    idx_curr = i - 1

    k_curr = float(stoch_k[idx_curr])
    d_curr = float(stoch_d[idx_curr])
    hist_curr = float(macd_hist[idx_curr])
    rsi_value = float(rsi[idx_curr])
    atr_value = float(atr[idx_curr])

    m15_close_curr = float(trend_m15_close[idx_curr])
    m15_ema_curr = float(trend_m15_ema[idx_curr])
    m15_ema_prev = float(trend_m15_ema[idx_curr - 1]) if idx_curr - 1 >= 0 else float(m15_ema_curr)
    ema_slope_value = float(m15_ema_curr) - float(m15_ema_prev)

    trend = "NONE"
    if m15_close_curr > m15_ema_curr:
        trend = "BUY"
    elif m15_close_curr < m15_ema_curr:
        trend = "SELL"

    signal = "NONE"
    closed_bar = dict(rates[i - 1])
    entry_model_u = (str(entry_model) or "").strip().upper()
    if entry_model_u == "BREAKOUT_RETEST":
        signal = _entry_breakout_retest(
            rates=rates,
            idx_curr=int(idx_curr),
            trend=str(trend),
            atr_value=float(atr_value),
            breakout_lookback=int(breakout_lookback),
            breakout_max_age=int(breakout_max_age),
            retest_atr_tolerance=float(retest_atr_tolerance),
            retest_max_distance_atr=float(retest_max_distance_atr),
        )
    elif entry_model_u == "BREAKOUT_FOLLOWTHROUGH":
        signal = _entry_breakout_followthrough(
            rates=rates,
            idx_curr=int(idx_curr),
            trend=str(trend),
            atr_value=float(atr_value),
            breakout_lookback=int(breakout_lookback),
            followthrough_range_atr=float(followthrough_range_atr),
            followthrough_body_ratio=float(followthrough_body_ratio),
            followthrough_max_distance_atr=float(followthrough_max_distance_atr),
        )
    else:
        rng = float(closed_bar["high"]) - float(closed_bar["low"])
        range_ok = float(atr_value) > 0.0 and rng >= float(atr_entry_multiplier) * float(atr_value)
        candle_dir = "NONE"
        if float(closed_bar["close"]) > float(closed_bar["open"]):
            candle_dir = "BUY"
        elif float(closed_bar["close"]) < float(closed_bar["open"]):
            candle_dir = "SELL"

        if trend in ("BUY", "SELL") and candle_dir == trend and range_ok:
            signal = trend

    bar_time_current = int(rates[i]["time"])
    bar_time_closed = int(rates[i - 1]["time"])

    signal, filter_reason = _apply_filters(
        signal=signal,
        rsi_value=float(rsi_value),
        ema_slope_value=float(ema_slope_value),
        bar_time_current=int(bar_time_current),
        closed_bar=closed_bar,
        rsi_buy_max=float(rsi_buy_max),
        rsi_sell_min=float(rsi_sell_min),
        candle_body_ratio=float(candle_body_ratio),
        session_start_london_wib=int(session_start_london_wib),
        session_end_ny_wib=int(session_end_ny_wib),
        ema_slope_min=float(ema_slope_min),
        ema_gate1_start_wib=int(ema_gate1_start_wib),
        ema_gate1_end_wib=int(ema_gate1_end_wib),
        ema_gate2_start_wib=int(ema_gate2_start_wib),
        ema_gate2_end_wib=int(ema_gate2_end_wib),
    )

    return TripleSignal(
        signal=signal,
        ema_trend=float(m15_ema_curr),
        stoch_k=float(k_curr),
        stoch_d=float(d_curr),
        macd_hist=float(hist_curr),
        atr=float(atr_value),
        rsi=float(rsi_value),
        bar_time_current=int(bar_time_current),
        bar_time_closed=int(bar_time_closed),
        filter_reason=filter_reason,
    )
