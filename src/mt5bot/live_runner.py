import csv
import logging
import os
import time
from datetime import datetime
from typing import Any, List, Optional, Sequence, Tuple

import MetaTrader5 as mt5

from .config import AppConfig
from .mt5_client import MT5Client
from .risk_manager import calculate_lot
from .strategy_triple import calculate_triple_signal


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


def setup_logging(text_log_path: str) -> logging.Logger:
    os.makedirs(os.path.dirname(text_log_path), exist_ok=True)

    logger = logging.getLogger("mt5bot_live")
    logger.setLevel(logging.INFO)

    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    if not any(isinstance(h, logging.FileHandler) and h.baseFilename == text_log_path for h in logger.handlers):
        fh = logging.FileHandler(text_log_path, encoding="utf-8")
        fh.setFormatter(formatter)
        fh.setLevel(logging.INFO)
        logger.addHandler(fh)

    if not any(isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler) for h in logger.handlers):
        sh = logging.StreamHandler()
        sh.setFormatter(formatter)
        sh.setLevel(logging.INFO)
        logger.addHandler(sh)

    return logger


def ensure_csv_header(path: str, header: Sequence[str]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path) and os.path.getsize(path) > 0:
        try:
            with open(path, "r", newline="", encoding="utf-8") as f:
                r = csv.reader(f)
                current = next(r, None)
                if current is not None and list(current) == list(header):
                    return
        except Exception:
            return

    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(list(header))


def append_csv_row(path: str, row: Sequence[Any]) -> None:
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(list(row))


def _csv_header() -> List[str]:
    return [
        "ts_local",
        "symbol",
        "timeframe",
        "bar_time_current",
        "bar_time_closed",
        "ema_trend",
        "stoch_k",
        "stoch_d",
        "macd_hist",
        "atr",
        "rsi",
        "filter_reason",
        "signal",
        "bid",
        "ask",
        "spread",
        "position_state",
        "position_ticket",
        "position_volume",
        "action",
        "order_retcode",
        "order_comment",
        "order_ticket",
    ]


def _position_state(position) -> Tuple[str, str, str]:
    if position is None:
        return "NONE", "", ""
    pos_type = int(position.type)
    state = "BUY" if pos_type == mt5.POSITION_TYPE_BUY else "SELL"
    return state, str(int(position.ticket)), str(float(position.volume))


def run_live(cfg: AppConfig) -> None:
    text_log_path = os.fspath(cfg.live.log_dir / cfg.live.text_log_filename)
    csv_log_path = os.fspath(cfg.live.log_dir / cfg.live.decisions_csv_filename)

    logger = setup_logging(text_log_path)
    ensure_csv_header(csv_log_path, _csv_header())

    client = MT5Client()
    symbol = client.connect(cfg.mt5, logger)
    cs = client.contract_size(symbol)
    run_once = (os.getenv("RUN_ONCE") or "").strip().lower() in ("1", "true", "yes", "y", "on")

    last_seen_bar_time: Optional[int] = None
    entry_tf_const, _, entry_tf_label = _timeframe(cfg.strategy.entry_timeframe)
    trend_tf_const, _, trend_tf_label = _timeframe(cfg.strategy.trend_timeframe)
    logger.info(
        "Bot started. mode=%s symbol=%s entry_tf=%s trend_tf=%s magic=%s",
        cfg.mode,
        symbol,
        entry_tf_label,
        trend_tf_label,
        cfg.live.magic,
    )
    start_equity = 0.0
    stop_out_level = 0.0
    if float(cfg.live.stop_out_pct) > 0.0:
        info = mt5.account_info()
        if info is not None:
            start_equity = float(getattr(info, "equity", 0.0))
            stop_out_level = float(start_equity) * float(cfg.live.stop_out_pct)
            logger.info(
                "LIVE_STOP_OUT start_equity=%.2f stop_out_pct=%.4f stop_out_level=%.2f",
                float(start_equity),
                float(cfg.live.stop_out_pct),
                float(stop_out_level),
            )
        else:
            logger.warning("LIVE_STOP_OUT disabled: account_info unavailable")

    try:
        while True:
            try:
                rates = client.copy_rates_from_pos(symbol, entry_tf_const, 0, int(cfg.live.bars))
                current_bar_time = int(rates[-1]["time"])
            except Exception as e:
                logger.error("copy_rates_from_pos error: %s", e)
                if run_once:
                    break
                time.sleep(2)
                continue

            if last_seen_bar_time is None:
                last_seen_bar_time = current_bar_time
                if run_once:
                    break
                time.sleep(cfg.live.poll_interval_seconds)
                continue

            if current_bar_time == last_seen_bar_time:
                if run_once:
                    break
                time.sleep(cfg.live.poll_interval_seconds)
                continue

            last_seen_bar_time = current_bar_time
            ts_local = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            if float(cfg.live.stop_out_pct) > 0.0 and float(start_equity) > 0.0:
                info = mt5.account_info()
                if info is not None:
                    current_equity = float(getattr(info, "equity", 0.0))
                    if float(current_equity) <= float(stop_out_level):
                        position = client.positions_get_bot(symbol, cfg.live.magic)
                        pos_state, pos_ticket, pos_vol = _position_state(position)
                        closed_ok = False
                        if position is not None:
                            closed_ok = client.close_position(
                                logger,
                                position,
                                deviation_points=cfg.strategy.deviation_points,
                                magic=cfg.live.magic,
                                comment="STOP_OUT",
                            )
                        logger.warning(
                            "LIVE_STOP_OUT_TRIGGER equity=%.2f level=%.2f position=%s closed=%s — bot berhenti",
                            float(current_equity),
                            float(stop_out_level),
                            pos_state,
                            str(closed_ok),
                        )
                        append_csv_row(
                            csv_log_path,
                            [
                                ts_local,
                                symbol,
                                entry_tf_label,
                                str(current_bar_time),
                                "",
                                "",
                                "",
                                "",
                                "",
                                "",
                                "",
                                "",
                                "STOP_OUT",
                                "",
                                "",
                                "",
                                pos_state,
                                pos_ticket,
                                pos_vol,
                                "STOP_OUT_CLOSE_AND_STOP",
                                "",
                                f"equity={current_equity:.2f} level={stop_out_level:.2f} closed={closed_ok}",
                                "",
                            ],
                        )
                        break

            try:
                m15_bars = max(int(cfg.strategy.ema_trend) + 10, 200)
                m15_rates = client.copy_rates_from_pos(symbol, trend_tf_const, 0, int(m15_bars))
                sig = calculate_triple_signal(
                    rates,
                    trend_rates_m15=m15_rates,
                    entry_model=cfg.strategy.entry_model,
                    breakout_lookback=cfg.strategy.breakout_lookback,
                    breakout_max_age=cfg.strategy.breakout_max_age,
                    retest_atr_tolerance=cfg.strategy.retest_atr_tolerance,
                    retest_max_distance_atr=cfg.strategy.retest_max_distance_atr,
                    followthrough_range_atr=cfg.strategy.followthrough_range_atr,
                    followthrough_body_ratio=cfg.strategy.followthrough_body_ratio,
                    followthrough_max_distance_atr=cfg.strategy.followthrough_max_distance_atr,
                    ema_trend_period=cfg.strategy.ema_trend,
                    stoch_period=cfg.strategy.stoch_period,
                    stoch_smooth_k=cfg.strategy.stoch_smooth_k,
                    stoch_smooth_d=cfg.strategy.stoch_smooth_d,
                    stoch_oversold=cfg.strategy.stoch_oversold,
                    stoch_overbought=cfg.strategy.stoch_overbought,
                    stoch_min_gap=cfg.strategy.stoch_min_gap,
                    macd_fast=cfg.strategy.macd_fast,
                    macd_slow=cfg.strategy.macd_slow,
                    macd_signal=cfg.strategy.macd_signal,
                    ema_slope_min=cfg.strategy.ema_slope_min,
                    ema_gate1_start_wib=cfg.strategy.ema_gate1_start_wib,
                    ema_gate1_end_wib=cfg.strategy.ema_gate1_end_wib,
                    ema_gate2_start_wib=cfg.strategy.ema_gate2_start_wib,
                    ema_gate2_end_wib=cfg.strategy.ema_gate2_end_wib,
                    rsi_period=cfg.strategy.rsi_period,
                    rsi_buy_max=cfg.strategy.rsi_buy_max,
                    rsi_sell_min=cfg.strategy.rsi_sell_min,
                    atr_period=cfg.strategy.atr_period,
                    atr_entry_multiplier=cfg.strategy.atr_entry_multiplier,
                    candle_body_ratio=cfg.strategy.candle_body_ratio,
                    session_start_london_wib=cfg.strategy.session_start_london_wib,
                    session_end_ny_wib=cfg.strategy.session_end_ny_wib,
                )
            except Exception as e:
                logger.error("calculate_triple_signal error: %s", e)
                append_csv_row(
                    csv_log_path,
                    [
                        ts_local,
                        symbol,
                        entry_tf_label,
                        current_bar_time,
                        "",
                        "",
                        "",
                        "",
                        "",
                        "",
                        "",
                        "",
                        "",
                        "",
                        "",
                        "",
                        "ERROR",
                        "",
                        "",
                        "ERROR_SIGNAL",
                        "",
                        str(e),
                        "",
                    ],
                )
                if run_once:
                    break
                time.sleep(cfg.live.poll_interval_seconds)
                continue

            try:
                bid, ask, spread = client.spread(symbol)
            except Exception as e:
                logger.error("spread check error: %s", e)
                if run_once:
                    break
                time.sleep(cfg.live.poll_interval_seconds)
                continue

            position = client.positions_get_bot(symbol, cfg.live.magic)
            pos_state, pos_ticket, pos_vol = _position_state(position)

            action = "HOLD"
            order_retcode: str = ""
            order_comment: str = ""
            order_ticket: str = ""

            logger.info(
                "NEW_%s bar_time=%s signal=%s ema_trend=%.5f stoch(k=%.2f,d=%.2f) macd_hist=%.5f rsi=%.2f atr=%.5f spread=%.5f pos=%s filter=%s",
                entry_tf_label,
                sig.bar_time_current,
                sig.signal,
                float(sig.ema_trend),
                float(sig.stoch_k),
                float(sig.stoch_d),
                float(sig.macd_hist),
                float(sig.rsi),
                float(sig.atr),
                float(spread),
                pos_state,
                str(sig.filter_reason or ""),
            )

            spread_ok = float(spread) <= float(cfg.strategy.spread_max)

            try:
                if position is None:
                    if sig.signal in ("BUY", "SELL"):
                        if not spread_ok:
                            action = "SKIP_SPREAD"
                            logger.info("Entry dibatalkan karena spread terlalu besar: %.5f", float(spread))
                        else:
                            sl_dist = float(cfg.strategy.atr_sl_multiplier) * float(sig.atr)
                            tp_dist = float(cfg.strategy.atr_tp_multiplier) * float(sig.atr)
                            if sl_dist <= 0.0:
                                if sig.signal == "BUY":
                                    sl_dist = float(cfg.strategy.buy_sl_distance)
                                    tp_dist = float(cfg.strategy.buy_tp_distance)
                                else:
                                    sl_dist = float(cfg.strategy.sell_sl_distance)
                                    tp_dist = float(cfg.strategy.sell_tp_distance)

                            account = mt5.account_info()
                            if account is None:
                                logger.error("account_info unavailable; using balance=0.0 for position sizing")
                                balance = 0.0
                            else:
                                balance = float(getattr(account, "balance", 0.0))

                            lot = calculate_lot(
                                balance=balance,
                                sl_distance=sl_dist,
                                risk_pct=cfg.strategy.risk_per_trade_pct,
                                min_lot=cfg.strategy.min_lot,
                                max_lot=cfg.strategy.max_lot,
                                lot_step=cfg.strategy.lot_step,
                                contract_size=cs,
                            )
                            logger.info(
                                "POSITION_SIZE balance=%.2f sl_dist=%.5f risk_pct=%.1f%% lot=%.2f",
                                balance,
                                sl_dist,
                                cfg.strategy.risk_per_trade_pct,
                                lot,
                            )
                            if sig.signal == "BUY":
                                entry = float(ask)
                                sl = entry - sl_dist
                                tp = entry + tp_dist
                            else:
                                entry = float(bid)
                                sl = entry + sl_dist
                                tp = entry - tp_dist
                            ok, res = client.send_order(
                                logger,
                                symbol,
                                sig.signal,
                                lot=lot,
                                sl=sl,
                                tp=tp,
                                deviation_points=cfg.strategy.deviation_points,
                                magic=cfg.live.magic,
                                comment="TRIPLE",
                            )
                            action = f"OPEN_{sig.signal}"
                            if res is not None:
                                order_retcode = str(getattr(res, "retcode", ""))
                                order_comment = str(getattr(res, "comment", ""))
                                order_ticket = str(getattr(res, "order", ""))
                            if not ok:
                                action = f"OPEN_{sig.signal}_FAILED"
                else:
                    pos_type = int(position.type)
                    if pos_type == mt5.POSITION_TYPE_BUY and sig.signal == "SELL":
                        closed_ok = client.close_position(
                            logger,
                            position,
                            deviation_points=cfg.strategy.deviation_points,
                            magic=cfg.live.magic,
                            comment="TRIPLE_CLOSE",
                        )
                        action = "REVERSE_CLOSE_BUY"
                        if closed_ok and spread_ok:
                            sl_dist = float(cfg.strategy.atr_sl_multiplier) * float(sig.atr)
                            tp_dist = float(cfg.strategy.atr_tp_multiplier) * float(sig.atr)
                            if sl_dist <= 0.0:
                                sl_dist = float(cfg.strategy.sell_sl_distance)
                                tp_dist = float(cfg.strategy.sell_tp_distance)

                            account = mt5.account_info()
                            if account is None:
                                logger.error("account_info unavailable; using balance=0.0 for position sizing")
                                balance = 0.0
                            else:
                                balance = float(getattr(account, "balance", 0.0))

                            lot = calculate_lot(
                                balance=balance,
                                sl_distance=sl_dist,
                                risk_pct=cfg.strategy.risk_per_trade_pct,
                                min_lot=cfg.strategy.min_lot,
                                max_lot=cfg.strategy.max_lot,
                                lot_step=cfg.strategy.lot_step,
                                contract_size=cs,
                            )
                            logger.info(
                                "POSITION_SIZE balance=%.2f sl_dist=%.5f risk_pct=%.1f%% lot=%.2f",
                                balance,
                                sl_dist,
                                cfg.strategy.risk_per_trade_pct,
                                lot,
                            )
                            entry = float(bid)
                            sl = entry + sl_dist
                            tp = entry - tp_dist
                            ok, res = client.send_order(
                                logger,
                                symbol,
                                "SELL",
                                lot=lot,
                                sl=sl,
                                tp=tp,
                                deviation_points=cfg.strategy.deviation_points,
                                magic=cfg.live.magic,
                                comment="TRIPLE",
                            )
                            action = "REVERSE_OPEN_SELL" if ok else "REVERSE_OPEN_SELL_FAILED"
                            if res is not None:
                                order_retcode = str(getattr(res, "retcode", ""))
                                order_comment = str(getattr(res, "comment", ""))
                                order_ticket = str(getattr(res, "order", ""))
                        elif closed_ok and not spread_ok:
                            action = "REVERSE_CLOSE_BUY_SKIP_SPREAD"
                            logger.info("Entry dibatalkan karena spread terlalu besar: %.5f", float(spread))
                    elif pos_type == mt5.POSITION_TYPE_SELL and sig.signal == "BUY":
                        closed_ok = client.close_position(
                            logger,
                            position,
                            deviation_points=cfg.strategy.deviation_points,
                            magic=cfg.live.magic,
                            comment="TRIPLE_CLOSE",
                        )
                        action = "REVERSE_CLOSE_SELL"
                        if closed_ok and spread_ok:
                            sl_dist = float(cfg.strategy.atr_sl_multiplier) * float(sig.atr)
                            tp_dist = float(cfg.strategy.atr_tp_multiplier) * float(sig.atr)
                            if sl_dist <= 0.0:
                                sl_dist = float(cfg.strategy.buy_sl_distance)
                                tp_dist = float(cfg.strategy.buy_tp_distance)

                            account = mt5.account_info()
                            if account is None:
                                logger.error("account_info unavailable; using balance=0.0 for position sizing")
                                balance = 0.0
                            else:
                                balance = float(getattr(account, "balance", 0.0))

                            lot = calculate_lot(
                                balance=balance,
                                sl_distance=sl_dist,
                                risk_pct=cfg.strategy.risk_per_trade_pct,
                                min_lot=cfg.strategy.min_lot,
                                max_lot=cfg.strategy.max_lot,
                                lot_step=cfg.strategy.lot_step,
                                contract_size=cs,
                            )
                            logger.info(
                                "POSITION_SIZE balance=%.2f sl_dist=%.5f risk_pct=%.1f%% lot=%.2f",
                                balance,
                                sl_dist,
                                cfg.strategy.risk_per_trade_pct,
                                lot,
                            )
                            entry = float(ask)
                            sl = entry - sl_dist
                            tp = entry + tp_dist
                            ok, res = client.send_order(
                                logger,
                                symbol,
                                "BUY",
                                lot=lot,
                                sl=sl,
                                tp=tp,
                                deviation_points=cfg.strategy.deviation_points,
                                magic=cfg.live.magic,
                                comment="TRIPLE",
                            )
                            action = "REVERSE_OPEN_BUY" if ok else "REVERSE_OPEN_BUY_FAILED"
                            if res is not None:
                                order_retcode = str(getattr(res, "retcode", ""))
                                order_comment = str(getattr(res, "comment", ""))
                                order_ticket = str(getattr(res, "order", ""))
                        elif closed_ok and not spread_ok:
                            action = "REVERSE_CLOSE_SELL_SKIP_SPREAD"
                            logger.info("Entry dibatalkan karena spread terlalu besar: %.5f", float(spread))
            except Exception as e:
                logger.error("trade logic error: %s", e)
                action = "ERROR_TRADE"
                order_comment = str(e)

            append_csv_row(
                csv_log_path,
                [
                    ts_local,
                    symbol,
                    entry_tf_label,
                    str(sig.bar_time_current),
                    str(sig.bar_time_closed),
                    f"{float(sig.ema_trend):.2f}",
                    f"{float(sig.stoch_k):.2f}",
                    f"{float(sig.stoch_d):.2f}",
                    f"{float(sig.macd_hist):.2f}",
                    f"{float(sig.atr):.2f}",
                    f"{float(sig.rsi):.2f}",
                    str(sig.filter_reason or ""),
                    sig.signal,
                    f"{bid:.2f}",
                    f"{ask:.2f}",
                    f"{float(spread):.2f}",
                    pos_state,
                    pos_ticket,
                    pos_vol,
                    action,
                    order_retcode,
                    order_comment,
                    order_ticket,
                ],
            )

            if run_once:
                break
            time.sleep(cfg.live.poll_interval_seconds)
    except KeyboardInterrupt:
        logger.info("Bot stopped by user.")
    finally:
        client.shutdown()
