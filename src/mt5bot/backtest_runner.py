import csv
import json
import logging
import os
import statistics
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence, Tuple

import MetaTrader5 as mt5

from .config import AppConfig
from .mt5_client import MT5Client
from .risk_manager import calculate_lot
from .strategy_triple import (
    atr_wilder,
    calculate_triple_signal_at_index,
    ema_series,
    macd,
    min_bars_required,
    rsi_wilder,
    stochastic,
)


STOP_OUT_PCT: float = 0.50


def _timeframe(tf: str) -> Tuple[int, int, str]:
    v = (tf or "").strip().upper()
    m = {
        "M1": (mt5.TIMEFRAME_M1, 60),
        "M2": (mt5.TIMEFRAME_M2, 2 * 60),
        "M3": (mt5.TIMEFRAME_M3, 3 * 60),
        "M4": (mt5.TIMEFRAME_M4, 4 * 60),
        "M5": (mt5.TIMEFRAME_M5, 5 * 60),
        "M6": (mt5.TIMEFRAME_M6, 6 * 60),
        "M10": (mt5.TIMEFRAME_M10, 10 * 60),
        "M12": (mt5.TIMEFRAME_M12, 12 * 60),
        "M15": (mt5.TIMEFRAME_M15, 15 * 60),
        "M20": (mt5.TIMEFRAME_M20, 20 * 60),
        "M30": (mt5.TIMEFRAME_M30, 30 * 60),
        "H1": (mt5.TIMEFRAME_H1, 60 * 60),
        "H2": (mt5.TIMEFRAME_H2, 2 * 60 * 60),
        "H3": (mt5.TIMEFRAME_H3, 3 * 60 * 60),
        "H4": (mt5.TIMEFRAME_H4, 4 * 60 * 60),
        "H6": (mt5.TIMEFRAME_H6, 6 * 60 * 60),
        "H8": (mt5.TIMEFRAME_H8, 8 * 60 * 60),
        "H12": (mt5.TIMEFRAME_H12, 12 * 60 * 60),
        "D1": (mt5.TIMEFRAME_D1, 24 * 60 * 60),
    }
    if v not in m:
        raise ValueError(f"Unsupported timeframe: {tf}")
    const, seconds = m[v]
    return int(const), int(seconds), v


@dataclass
class Position:
    side: str
    open_time: int
    entry: float
    lot: float
    spread_open: float
    sl: float
    tp: float
    atr: float
    ema_trend: float
    stoch_k: float
    stoch_d: float
    macd_hist: float
    rsi: float


def setup_logging(log_path: str) -> logging.Logger:
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    logger = logging.getLogger("mt5bot_backtest")
    logger.setLevel(logging.INFO)

    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    if not any(isinstance(h, logging.FileHandler) and h.baseFilename == log_path for h in logger.handlers):
        fh = logging.FileHandler(log_path, encoding="utf-8")
        fh.setFormatter(formatter)
        fh.setLevel(logging.INFO)
        logger.addHandler(fh)

    if not any(isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler) for h in logger.handlers):
        sh = logging.StreamHandler()
        sh.setFormatter(formatter)
        sh.setLevel(logging.INFO)
        logger.addHandler(sh)

    return logger


def write_csv(path: str, header: Sequence[str], rows: Sequence[Sequence[Any]]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(list(header))
        for r in rows:
            w.writerow(list(r))


def parse_date(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d")


def max_drawdown(equity_points: Sequence[float]) -> float:
    peak = None
    worst = 0.0
    for x in equity_points:
        if peak is None or x > peak:
            peak = x
        if peak:
            dd = peak - x
            if dd > worst:
                worst = dd
    return float(worst)


def get_ticks_range_per_day(
    client: MT5Client,
    symbol: str,
    start_dt: datetime,
    end_dt: datetime,
    logger: logging.Logger,
) -> List[Dict[str, Any]]:
    day_start = start_dt.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = end_dt.replace(hour=0, minute=0, second=0, microsecond=0)

    ticks: List[Dict[str, Any]] = []
    d = day_start
    while d <= day_end:
        d2 = d + timedelta(days=1)
        chunk = client.copy_ticks_range(symbol, d, d2, mt5.COPY_TICKS_ALL)
        ticks.extend(chunk)
        logger.info("ticks %s: %s", d.strftime("%Y-%m-%d"), len(chunk))
        d = d2

    ticks.sort(key=lambda x: x["time_msc"])
    return ticks


def build_candle_tick_map(
    rates: Sequence[Dict[str, Any]],
    ticks: Sequence[Dict[str, Any]],
    timeframe_seconds: int,
) -> Tuple[Dict[int, Tuple[float, float, float]], int, List[float]]:
    out: Dict[int, Tuple[float, float, float]] = {}
    tick_idx = 0
    last_tick: Optional[Dict[str, Any]] = None
    fallback_count = 0
    spreads: List[float] = []

    for bar in rates:
        open_ts = int(bar["time"])
        open_msc = open_ts * 1000
        end_msc = open_msc + (timeframe_seconds * 1000)

        while tick_idx < len(ticks) and int(ticks[tick_idx]["time_msc"]) < open_msc:
            last_tick = ticks[tick_idx]
            tick_idx += 1

        mapped: Optional[Dict[str, Any]] = None
        if tick_idx < len(ticks):
            t = ticks[tick_idx]
            if open_msc <= int(t["time_msc"]) < end_msc:
                mapped = t

        if mapped is None:
            if last_tick is not None:
                mapped = last_tick
                fallback_count += 1
            elif tick_idx < len(ticks):
                mapped = ticks[tick_idx]
                fallback_count += 1

        if mapped is None:
            raise RuntimeError("Tidak ada tick data untuk mapping candle (ticks kosong?)")

        bid = float(mapped["bid"])
        ask = float(mapped["ask"])
        spread = ask - bid
        out[open_ts] = (bid, ask, spread)
        spreads.append(spread)

    return out, fallback_count, spreads


def run_backtest(cfg: AppConfig) -> Dict[str, Any]:
    start_dt = parse_date(cfg.backtest.start_date)
    end_dt = parse_date(cfg.backtest.end_date).replace(hour=23, minute=59, second=59)

    log_path = os.fspath(cfg.backtest.log_dir / f"backtest_{cfg.backtest.start_date}_{cfg.backtest.end_date}.log")
    logger = setup_logging(log_path)

    client = MT5Client()
    symbol = client.connect(cfg.mt5, logger)

    try:
        entry_tf_const, entry_tf_seconds, entry_tf_label = _timeframe(cfg.strategy.entry_timeframe)
        trend_tf_const, trend_tf_seconds, trend_tf_label = _timeframe(cfg.strategy.trend_timeframe)

        rates = client.copy_rates_range(symbol, entry_tf_const, start_dt, end_dt)
        min_bars = min_bars_required(
            ema_trend_period=int(cfg.strategy.ema_trend),
            stoch_period=int(cfg.strategy.stoch_period),
            stoch_smooth_k=int(cfg.strategy.stoch_smooth_k),
            stoch_smooth_d=int(cfg.strategy.stoch_smooth_d),
            macd_slow=int(cfg.strategy.macd_slow),
            macd_signal=int(cfg.strategy.macd_signal),
            rsi_period=int(cfg.strategy.rsi_period),
            atr_period=int(cfg.strategy.atr_period),
            extra=10,
        )
        if len(rates) < int(min_bars):
            raise RuntimeError(f"Bars tidak cukup: butuh >= {int(min_bars)}, dapat {len(rates)}")

        ticks = get_ticks_range_per_day(client, symbol, start_dt, end_dt, logger)
        candle_tick_map, ticks_fallback_count, candle_spreads = build_candle_tick_map(rates, ticks, int(entry_tf_seconds))
        cs = client.contract_size(symbol)

        spread_min = min(candle_spreads) if candle_spreads else None
        spread_max = max(candle_spreads) if candle_spreads else None
        spread_avg = (sum(candle_spreads) / len(candle_spreads)) if candle_spreads else None

        logger.info(
            "Backtest params mode=%s symbol=%s entry_tf=%s trend_tf=%s start=%s end=%s leverage=1:%s contract_size=%.2f ticks=%s candle_spread_min=%.8f candle_spread_avg=%.8f candle_spread_max=%.8f",
            cfg.mode,
            symbol,
            entry_tf_label,
            trend_tf_label,
            cfg.backtest.start_date,
            cfg.backtest.end_date,
            cfg.backtest.leverage,
            float(cs),
            len(ticks),
            float(spread_min or 0.0),
            float(spread_avg or 0.0),
            float(spread_max or 0.0),
        )

        closes = [float(r["close"]) for r in rates]
        highs = [float(r["high"]) for r in rates]
        lows = [float(r["low"]) for r in rates]
        ema_trend = ema_series(closes, cfg.strategy.ema_trend)
        stoch_k, stoch_d = stochastic(
            highs,
            lows,
            closes,
            cfg.strategy.stoch_period,
            cfg.strategy.stoch_smooth_k,
            cfg.strategy.stoch_smooth_d,
        )
        _, _, macd_hist = macd(closes, cfg.strategy.macd_fast, cfg.strategy.macd_slow, cfg.strategy.macd_signal)
        rsi = rsi_wilder(closes, cfg.strategy.rsi_period)
        atr = atr_wilder(highs, lows, closes, cfg.strategy.atr_period)

        trend_bars = max(int(cfg.strategy.ema_trend) + 10, 200)
        trend_start_dt = start_dt - timedelta(seconds=int(trend_bars) * int(trend_tf_seconds))
        trend_rates = client.copy_rates_range(symbol, trend_tf_const, trend_start_dt, end_dt)
        trend_times = [int(r["time"]) for r in trend_rates]
        trend_closes = [float(r["close"]) for r in trend_rates]
        trend_ema = ema_series(trend_closes, cfg.strategy.ema_trend)

        trend_m15_close: List[float] = []
        trend_m15_ema: List[float] = []
        j = -1
        for bar in rates:
            entry_close_time = int(bar["time"]) + int(entry_tf_seconds)
            while (j + 1) < len(trend_times) and (int(trend_times[j + 1]) + int(trend_tf_seconds)) <= int(entry_close_time):
                j += 1
            if j >= 0:
                trend_m15_close.append(float(trend_closes[j]))
                trend_m15_ema.append(float(trend_ema[j]))
            else:
                trend_m15_close.append(float(trend_closes[0]))
                trend_m15_ema.append(float(trend_ema[0]))

        balance = float(cfg.backtest.initial_balance)
        equity_curve: List[float] = [balance]
        trades: List[List[Any]] = []
        pos: Optional[Position] = None
        entries_skipped_spread = 0
        entries_skipped_margin: int = 0
        stop_out_triggered: bool = False
        filter_counts: Dict[str, int] = {}

        warmup = max(int(min_bars), 3)

        logger.info("=== DIAGNOSTIC SERIES ===")
        logger.info("EMA50 sample (last 5): %s", [round(x, 2) for x in ema_trend[-5:]])

        stoch_k_sample = stoch_k[-100:] if len(stoch_k) >= 100 else stoch_k
        stoch_k_sample = stoch_k_sample if stoch_k_sample else [0.0]
        stoch_d_sample = stoch_d[-100:] if len(stoch_d) >= 100 else stoch_d
        stoch_d_sample = stoch_d_sample if stoch_d_sample else [0.0]
        macd_hist_sample = macd_hist[-100:] if len(macd_hist) >= 100 else macd_hist
        macd_hist_sample = macd_hist_sample if macd_hist_sample else [0.0]
        rsi_sample = rsi[-100:] if len(rsi) >= 100 else rsi
        rsi_sample = rsi_sample if rsi_sample else [0.0]

        logger.info(
            "Stoch_K sample (last 20): min=%.2f max=%.2f mean=%.2f",
            min(stoch_k_sample),
            max(stoch_k_sample),
            statistics.mean(stoch_k_sample),
        )
        logger.info("Stoch_D sample (last 20): min=%.2f max=%.2f", min(stoch_d_sample), max(stoch_d_sample))
        logger.info(
            "MACD hist sample (last 100): min=%.4f max=%.4f",
            min(macd_hist_sample),
            max(macd_hist_sample),
        )
        logger.info("RSI sample (last 100): min=%.2f max=%.2f", min(rsi_sample), max(rsi_sample))

        stoch_below_20 = sum(1 for x in stoch_k if x < 20)
        stoch_above_80 = sum(1 for x in stoch_k if x > 80)
        logger.info(
            "Stoch cross zones: below_20=%s bars, above_80=%s bars (dari %s total)",
            stoch_below_20,
            stoch_above_80,
            len(stoch_k),
        )

        raw_buy_signals = 0
        raw_sell_signals = 0
        for j in range(2, len(stoch_k)):
            if stoch_k[j - 2] < 20 and stoch_k[j - 1] >= 20:
                raw_buy_signals += 1
            if stoch_k[j - 2] > 80 and stoch_k[j - 1] <= 80:
                raw_sell_signals += 1

        logger.info("Raw stoch crossovers (no filter): BUY=%s SELL=%s", raw_buy_signals, raw_sell_signals)
        logger.info("=== END DIAGNOSTIC ===")

        for i in range(warmup, len(rates)):
            bar = rates[i]
            ts = int(bar["time"])
            bid_open, ask_open, spread_open = candle_tick_map[ts]
            spread_ok = spread_open <= cfg.strategy.spread_max
            high = float(bar["high"])
            low = float(bar["low"])

            if pos is not None:
                if pos.side == "BUY":
                    unrealized = (bid_open - pos.entry) * float(pos.lot) * cs
                else:
                    unrealized = (pos.entry - ask_open) * float(pos.lot) * cs
                current_equity = balance + float(unrealized)
            else:
                current_equity = balance

            stop_out_level = float(cfg.backtest.initial_balance) * float(STOP_OUT_PCT)
            if float(current_equity) <= float(stop_out_level):
                atr_value = float(atr[i - 1]) if 0 <= (i - 1) < len(atr) else (float(pos.atr) if pos is not None else 0.0)
                if pos is not None:
                    if pos.side == "BUY":
                        exit_price = bid_open
                        pnl = (exit_price - pos.entry) * float(pos.lot) * cs
                    else:
                        exit_price = ask_open
                        pnl = (pos.entry - exit_price) * float(pos.lot) * cs

                    balance += pnl
                    trades.append(
                        [
                            datetime.fromtimestamp(pos.open_time).strftime("%Y-%m-%d %H:%M:%S"),
                            datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S"),
                            pos.side,
                            f"{pos.entry:.2f}",
                            f"{pos.sl:.2f}",
                            f"{pos.tp:.2f}",
                            f"{exit_price:.2f}",
                            "STOP_OUT",
                            f"{pnl:.2f}",
                            f"{balance:.2f}",
                            f"{pos.spread_open:.2f}",
                            f"{spread_open:.2f}",
                            f"{pos.atr:.2f}",
                            f"{atr_value:.2f}",
                            f"{pos.ema_trend:.2f}",
                            f"{pos.stoch_k:.2f}",
                            f"{pos.stoch_d:.2f}",
                            f"{pos.macd_hist:.2f}",
                            f"{pos.rsi:.2f}",
                            f"{float(pos.lot):.2f}",
                        ]
                    )
                    equity_curve.append(balance)
                    pos = None

                stop_out_triggered = True
                logger.warning(
                    "STOP_OUT equity=%.2f stop_out_level=%.2f balance=%.2f — bot berhenti",
                    float(current_equity),
                    float(stop_out_level),
                    float(balance),
                )
                break

            sig = calculate_triple_signal_at_index(
                rates,
                i,
                stoch_k=stoch_k,
                stoch_d=stoch_d,
                macd_hist=macd_hist,
                rsi=rsi,
                atr=atr,
                trend_m15_close=trend_m15_close,
                trend_m15_ema=trend_m15_ema,
                atr_entry_multiplier=cfg.strategy.atr_entry_multiplier,
                rsi_buy_max=cfg.strategy.rsi_buy_max,
                rsi_sell_min=cfg.strategy.rsi_sell_min,
                candle_body_ratio=cfg.strategy.candle_body_ratio,
                session_start_london_wib=cfg.strategy.session_start_london_wib,
                session_end_ny_wib=cfg.strategy.session_end_ny_wib,
                ema_slope_min=cfg.strategy.ema_slope_min,
                ema_gate1_start_wib=cfg.strategy.ema_gate1_start_wib,
                ema_gate1_end_wib=cfg.strategy.ema_gate1_end_wib,
                ema_gate2_start_wib=cfg.strategy.ema_gate2_start_wib,
                ema_gate2_end_wib=cfg.strategy.ema_gate2_end_wib,
            )

            if sig.signal == "NONE" and sig.filter_reason:
                filter_counts[sig.filter_reason] = filter_counts.get(sig.filter_reason, 0) + 1

            signal = sig.signal
            ema_trend_value = float(sig.ema_trend)
            stoch_k_value = float(sig.stoch_k)
            stoch_d_value = float(sig.stoch_d)
            macd_hist_value = float(sig.macd_hist)
            rsi_value = float(sig.rsi)
            atr_value = float(sig.atr)
            sl_dist = float(cfg.strategy.atr_sl_multiplier) * atr_value
            tp_dist = float(cfg.strategy.atr_tp_multiplier) * atr_value

            if pos is not None:
                if pos.side == "BUY" and signal == "SELL":
                    exit_price = bid_open
                    pnl = (exit_price - pos.entry) * float(pos.lot) * cs
                    balance += pnl
                    trades.append(
                        [
                            datetime.fromtimestamp(pos.open_time).strftime("%Y-%m-%d %H:%M:%S"),
                            datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S"),
                            pos.side,
                            f"{pos.entry:.2f}",
                            f"{pos.sl:.2f}",
                            f"{pos.tp:.2f}",
                            f"{exit_price:.2f}",
                            "REVERSAL",
                            f"{pnl:.2f}",
                            f"{balance:.2f}",
                            f"{pos.spread_open:.2f}",
                            f"{spread_open:.2f}",
                            f"{pos.atr:.2f}",
                            f"{atr_value:.2f}",
                            f"{pos.ema_trend:.2f}",
                            f"{pos.stoch_k:.2f}",
                            f"{pos.stoch_d:.2f}",
                            f"{pos.macd_hist:.2f}",
                            f"{pos.rsi:.2f}",
                            f"{float(pos.lot):.2f}",
                        ]
                    )
                    equity_curve.append(balance)
                    pos = None

                    if spread_ok:
                        entry = bid_open
                        lot = calculate_lot(
                            balance=balance,
                            sl_distance=sl_dist,
                            risk_pct=cfg.strategy.risk_per_trade_pct,
                            min_lot=cfg.strategy.min_lot,
                            max_lot=cfg.strategy.max_lot,
                            lot_step=cfg.strategy.lot_step,
                            contract_size=cs,
                        )
                        leverage = int(cfg.backtest.leverage) if int(cfg.backtest.leverage) > 0 else 1
                        required_margin = (float(entry) * float(cfg.strategy.min_lot) * float(cs)) / float(leverage)
                        if float(balance) < float(required_margin):
                            logger.warning("SKIP_NO_MARGIN balance=%.2f required=%.2f", float(balance), float(required_margin))
                            entries_skipped_margin += 1
                            pos = None
                            continue
                        pos = Position(
                            side="SELL",
                            open_time=ts,
                            entry=entry,
                            lot=lot,
                            spread_open=spread_open,
                            sl=entry + sl_dist,
                            tp=entry - tp_dist,
                            atr=atr_value,
                            ema_trend=ema_trend_value,
                            stoch_k=stoch_k_value,
                            stoch_d=stoch_d_value,
                            macd_hist=macd_hist_value,
                            rsi=rsi_value,
                        )
                    else:
                        entries_skipped_spread += 1
                elif pos.side == "SELL" and signal == "BUY":
                    exit_price = ask_open
                    pnl = (pos.entry - exit_price) * float(pos.lot) * cs
                    balance += pnl
                    trades.append(
                        [
                            datetime.fromtimestamp(pos.open_time).strftime("%Y-%m-%d %H:%M:%S"),
                            datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S"),
                            pos.side,
                            f"{pos.entry:.2f}",
                            f"{pos.sl:.2f}",
                            f"{pos.tp:.2f}",
                            f"{exit_price:.2f}",
                            "REVERSAL",
                            f"{pnl:.2f}",
                            f"{balance:.2f}",
                            f"{pos.spread_open:.2f}",
                            f"{spread_open:.2f}",
                            f"{pos.atr:.2f}",
                            f"{atr_value:.2f}",
                            f"{pos.ema_trend:.2f}",
                            f"{pos.stoch_k:.2f}",
                            f"{pos.stoch_d:.2f}",
                            f"{pos.macd_hist:.2f}",
                            f"{pos.rsi:.2f}",
                            f"{float(pos.lot):.2f}",
                        ]
                    )
                    equity_curve.append(balance)
                    pos = None

                    if spread_ok:
                        entry = ask_open
                        lot = calculate_lot(
                            balance=balance,
                            sl_distance=sl_dist,
                            risk_pct=cfg.strategy.risk_per_trade_pct,
                            min_lot=cfg.strategy.min_lot,
                            max_lot=cfg.strategy.max_lot,
                            lot_step=cfg.strategy.lot_step,
                            contract_size=cs,
                        )
                        leverage = int(cfg.backtest.leverage) if int(cfg.backtest.leverage) > 0 else 1
                        required_margin = (float(entry) * float(cfg.strategy.min_lot) * float(cs)) / float(leverage)
                        if float(balance) < float(required_margin):
                            logger.warning("SKIP_NO_MARGIN balance=%.2f required=%.2f", float(balance), float(required_margin))
                            entries_skipped_margin += 1
                            pos = None
                            continue
                        pos = Position(
                            side="BUY",
                            open_time=ts,
                            entry=entry,
                            lot=lot,
                            spread_open=spread_open,
                            sl=entry - sl_dist,
                            tp=entry + tp_dist,
                            atr=atr_value,
                            ema_trend=ema_trend_value,
                            stoch_k=stoch_k_value,
                            stoch_d=stoch_d_value,
                            macd_hist=macd_hist_value,
                            rsi=rsi_value,
                        )
                    else:
                        entries_skipped_spread += 1

            if pos is None and signal in ("BUY", "SELL"):
                if spread_ok:
                    if signal == "BUY":
                        entry = ask_open
                        lot = calculate_lot(
                            balance=balance,
                            sl_distance=sl_dist,
                            risk_pct=cfg.strategy.risk_per_trade_pct,
                            min_lot=cfg.strategy.min_lot,
                            max_lot=cfg.strategy.max_lot,
                            lot_step=cfg.strategy.lot_step,
                            contract_size=cs,
                        )
                        leverage = int(cfg.backtest.leverage) if int(cfg.backtest.leverage) > 0 else 1
                        required_margin = (float(entry) * float(cfg.strategy.min_lot) * float(cs)) / float(leverage)
                        if float(balance) < float(required_margin):
                            logger.warning("SKIP_NO_MARGIN balance=%.2f required=%.2f", float(balance), float(required_margin))
                            entries_skipped_margin += 1
                            pos = None
                            continue
                        pos = Position(
                            side="BUY",
                            open_time=ts,
                            entry=entry,
                            lot=lot,
                            spread_open=spread_open,
                            sl=entry - sl_dist,
                            tp=entry + tp_dist,
                            atr=atr_value,
                            ema_trend=ema_trend_value,
                            stoch_k=stoch_k_value,
                            stoch_d=stoch_d_value,
                            macd_hist=macd_hist_value,
                            rsi=rsi_value,
                        )
                    else:
                        entry = bid_open
                        lot = calculate_lot(
                            balance=balance,
                            sl_distance=sl_dist,
                            risk_pct=cfg.strategy.risk_per_trade_pct,
                            min_lot=cfg.strategy.min_lot,
                            max_lot=cfg.strategy.max_lot,
                            lot_step=cfg.strategy.lot_step,
                            contract_size=cs,
                        )
                        leverage = int(cfg.backtest.leverage) if int(cfg.backtest.leverage) > 0 else 1
                        required_margin = (float(entry) * float(cfg.strategy.min_lot) * float(cs)) / float(leverage)
                        if float(balance) < float(required_margin):
                            logger.warning("SKIP_NO_MARGIN balance=%.2f required=%.2f", float(balance), float(required_margin))
                            entries_skipped_margin += 1
                            pos = None
                            continue
                        pos = Position(
                            side="SELL",
                            open_time=ts,
                            entry=entry,
                            lot=lot,
                            spread_open=spread_open,
                            sl=entry + sl_dist,
                            tp=entry - tp_dist,
                            atr=atr_value,
                            ema_trend=ema_trend_value,
                            stoch_k=stoch_k_value,
                            stoch_d=stoch_d_value,
                            macd_hist=macd_hist_value,
                            rsi=rsi_value,
                        )
                else:
                    entries_skipped_spread += 1

            if pos is not None:
                hit_sl = False
                hit_tp = False
                if pos.side == "BUY":
                    hit_tp = high >= pos.tp
                    hit_sl = low <= pos.sl
                    if hit_sl and hit_tp:
                        exit_reason = "SL"
                        exit_price = pos.sl
                    elif hit_sl:
                        exit_reason = "SL"
                        exit_price = pos.sl
                    elif hit_tp:
                        exit_reason = "TP"
                        exit_price = pos.tp
                    else:
                        exit_reason = ""
                        exit_price = 0.0

                    if exit_reason:
                        pnl = (exit_price - pos.entry) * float(pos.lot) * cs
                        balance += pnl
                        trades.append(
                            [
                                datetime.fromtimestamp(pos.open_time).strftime("%Y-%m-%d %H:%M:%S"),
                                datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S"),
                                pos.side,
                                f"{pos.entry:.2f}",
                                f"{pos.sl:.2f}",
                                f"{pos.tp:.2f}",
                                f"{exit_price:.2f}",
                                exit_reason,
                                f"{pnl:.2f}",
                                f"{balance:.2f}",
                                f"{pos.spread_open:.2f}",
                                f"{spread_open:.2f}",
                                f"{pos.atr:.2f}",
                                f"{atr_value:.2f}",
                                f"{pos.ema_trend:.2f}",
                                f"{pos.stoch_k:.2f}",
                                f"{pos.stoch_d:.2f}",
                                f"{pos.macd_hist:.2f}",
                                f"{pos.rsi:.2f}",
                                f"{float(pos.lot):.2f}",
                            ]
                        )
                        equity_curve.append(balance)
                        pos = None
                else:
                    hit_tp = low <= pos.tp
                    hit_sl = high >= pos.sl
                    if hit_sl and hit_tp:
                        exit_reason = "SL"
                        exit_price = pos.sl
                    elif hit_sl:
                        exit_reason = "SL"
                        exit_price = pos.sl
                    elif hit_tp:
                        exit_reason = "TP"
                        exit_price = pos.tp
                    else:
                        exit_reason = ""
                        exit_price = 0.0

                    if exit_reason:
                        pnl = (pos.entry - exit_price) * float(pos.lot) * cs
                        balance += pnl
                        trades.append(
                            [
                                datetime.fromtimestamp(pos.open_time).strftime("%Y-%m-%d %H:%M:%S"),
                                datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S"),
                                pos.side,
                                f"{pos.entry:.2f}",
                                f"{pos.sl:.2f}",
                                f"{pos.tp:.2f}",
                                f"{exit_price:.2f}",
                                exit_reason,
                                f"{pnl:.2f}",
                                f"{balance:.2f}",
                                f"{pos.spread_open:.2f}",
                                f"{spread_open:.2f}",
                                f"{pos.atr:.2f}",
                                f"{atr_value:.2f}",
                                f"{pos.ema_trend:.2f}",
                                f"{pos.stoch_k:.2f}",
                                f"{pos.stoch_d:.2f}",
                                f"{pos.macd_hist:.2f}",
                                f"{pos.rsi:.2f}",
                                f"{float(pos.lot):.2f}",
                            ]
                        )
                        equity_curve.append(balance)
                        pos = None

        wins = 0
        losses = 0
        gross_profit = 0.0
        gross_loss = 0.0
        pnl_list: List[float] = []
        for t in trades:
            pnl = float(t[8])
            pnl_list.append(pnl)
            if pnl >= 0:
                wins += 1
                gross_profit += pnl
            else:
                losses += 1
                gross_loss += abs(pnl)

        total = len(trades)
        win_rate = (wins / total) * 100.0 if total else 0.0
        net_profit = gross_profit - gross_loss
        pf = (gross_profit / gross_loss) if gross_loss > 0 else None

        summary: Dict[str, Any] = {
            "mode": cfg.mode,
            "symbol": symbol,
            "timeframe": "M5",
            "start_date": cfg.backtest.start_date,
            "end_date": cfg.backtest.end_date,
            "bars": len(rates),
            "ticks": len(ticks),
            "initial_balance": cfg.backtest.initial_balance,
            "leverage": cfg.backtest.leverage,
            "final_balance": round(balance, 2),
            "spread_threshold": cfg.strategy.spread_max,
            "ticks_fallback_count": ticks_fallback_count,
            "entries_skipped_spread": entries_skipped_spread,
            "entries_skipped_margin": entries_skipped_margin,
            "filter_rejection_counts": filter_counts,
            "stop_out_triggered": stop_out_triggered,
            "stop_out_level": round(float(cfg.backtest.initial_balance) * float(STOP_OUT_PCT), 2),
            "spread_min": float(f"{spread_min:.8f}") if spread_min is not None else None,
            "spread_avg": float(f"{spread_avg:.8f}") if spread_avg is not None else None,
            "spread_max": float(f"{spread_max:.8f}") if spread_max is not None else None,
            "total_trades": total,
            "wins": wins,
            "losses": losses,
            "win_rate": round(win_rate, 2),
            "gross_profit": round(gross_profit, 2),
            "gross_loss": round(gross_loss, 2),
            "net_profit": round(net_profit, 2),
            "profit_factor": round(pf, 4) if pf is not None else None,
            "max_drawdown": round(max_drawdown(equity_curve), 2),
            "largest_win": round(max(pnl_list), 2) if pnl_list else 0.0,
            "largest_loss": round(min(pnl_list), 2) if pnl_list else 0.0,
            "avg_trade": round((sum(pnl_list) / total), 2) if total else 0.0,
        }

        for reason, count in sorted(filter_counts.items(), key=lambda x: -x[1]):
            logger.info("FILTER_REJECT %s: %s bars", reason, count)

        trades_path = os.fspath(cfg.backtest.log_dir / f"backtest_trades_{cfg.backtest.start_date}_{cfg.backtest.end_date}.csv")
        summary_path = os.fspath(cfg.backtest.log_dir / f"backtest_summary_{cfg.backtest.start_date}_{cfg.backtest.end_date}.json")

        header = [
            "open_time",
            "close_time",
            "side",
            "entry",
            "sl",
            "tp",
            "exit",
            "reason",
            "pnl",
            "balance_after",
            "spread_open",
            "spread_close",
            "atr_open",
            "atr_close",
            "ema_trend",
            "stoch_k",
            "stoch_d",
            "macd_hist",
            "rsi",
            "lot",
        ]
        write_csv(trades_path, header, trades)

        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)

        logger.info("Backtest done. trades=%s final_balance=%.2f", total, balance)
        logger.info("Output trades=%s", trades_path)
        logger.info("Output summary=%s", summary_path)
        return summary
    finally:
        client.shutdown()
