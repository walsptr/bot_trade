import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


def _env_str(name: str) -> Optional[str]:
    v = os.getenv(name)
    if v is None:
        return None
    v = v.strip()
    return v or None


def _env_int(name: str) -> Optional[int]:
    v = _env_str(name)
    if v is None:
        return None
    try:
        return int(v)
    except ValueError:
        return None


def _env_float(name: str) -> Optional[float]:
    v = _env_str(name)
    if v is None:
        return None
    try:
        return float(v)
    except ValueError:
        return None


@dataclass(frozen=True)
class MT5Config:
    login: Optional[int]
    password: Optional[str]
    server: Optional[str]
    path: Optional[str]
    symbol: str


@dataclass(frozen=True)
class StrategyConfig:
    entry_timeframe: str = "M5"
    trend_timeframe: str = "M15"
    ema_trend: int = 50
    stoch_period: int = 5
    stoch_smooth_k: int = 3
    stoch_smooth_d: int = 3
    stoch_oversold: float = 20.0
    stoch_overbought: float = 80.0
    stoch_min_gap: float = 2.0
    macd_fast: int = 5
    macd_slow: int = 13
    macd_signal: int = 9
    ema_slope_min: float = 0.0
    ema_gate1_start_wib: int = 7
    ema_gate1_end_wib: int = 15
    ema_gate2_start_wib: int = 19
    ema_gate2_end_wib: int = 24
    risk_per_trade_pct: float = 1.5
    min_lot: float = 0.01
    max_lot: float = 0.05
    lot_step: float = 0.01
    spread_max: float = 0.40
    deviation_points: int = 30
    buy_sl_distance: float = 1.5
    buy_tp_distance: float = 3.0
    sell_sl_distance: float = 1.5
    sell_tp_distance: float = 3.0
    rsi_period: int = 14
    rsi_buy_max: float = 60.0
    rsi_sell_min: float = 40.0
    atr_period: int = 14
    atr_sl_multiplier: float = 1.5
    atr_tp_multiplier: float = 3.0
    atr_entry_multiplier: float = 1.0
    candle_body_ratio: float = 0.3
    session_start_london_wib: int = 15
    session_end_ny_wib: int = 23


@dataclass(frozen=True)
class LiveConfig:
    magic: int = 20260602
    bars: int = 200
    poll_interval_seconds: float = 1.0
    log_dir: Path = Path("logs")
    text_log_filename: str = "bot.log"
    decisions_csv_filename: str = "decisions.csv"


@dataclass(frozen=True)
class BacktestConfig:
    start_date: str = "2026-05-01"
    end_date: str = "2026-06-01"
    initial_balance: float = 50.0
    leverage: int = 2000
    log_dir: Path = Path("logs")


@dataclass(frozen=True)
class AppConfig:
    mode: str
    project_root: Path
    mt5: MT5Config
    strategy: StrategyConfig
    live: LiveConfig
    backtest: BacktestConfig


def load_config(project_root: Path, mode: str) -> AppConfig:
    symbol = _env_str("MT5_SYMBOL") or "XAUUSDm"
    mt5 = MT5Config(
        login=_env_int("MT5_LOGIN"),
        password=_env_str("MT5_PASSWORD"),
        server=_env_str("MT5_SERVER"),
        path=_env_str("MT5_PATH"),
        symbol=symbol,
    )

    spread_max = _env_float("SPREAD_MAX")
    entry_timeframe = _env_str("ENTRY_TIMEFRAME")
    trend_timeframe = _env_str("TREND_TIMEFRAME")
    ema_trend = _env_int("EMA_TREND")
    stoch_period = _env_int("STOCH_PERIOD")
    stoch_smooth_k = _env_int("STOCH_SMOOTH_K")
    stoch_smooth_d = _env_int("STOCH_SMOOTH_D")
    stoch_oversold = _env_float("STOCH_OVERSOLD")
    stoch_overbought = _env_float("STOCH_OVERBOUGHT")
    stoch_min_gap = _env_float("STOCH_MIN_GAP")
    macd_fast = _env_int("MACD_FAST")
    macd_slow = _env_int("MACD_SLOW")
    macd_signal = _env_int("MACD_SIGNAL")
    ema_slope_min = _env_float("EMA_SLOPE_MIN")
    ema_gate1_start_wib = _env_int("EMA_GATE1_START_WIB")
    ema_gate1_end_wib = _env_int("EMA_GATE1_END_WIB")
    ema_gate2_start_wib = _env_int("EMA_GATE2_START_WIB")
    ema_gate2_end_wib = _env_int("EMA_GATE2_END_WIB")
    risk_per_trade_pct = _env_float("RISK_PER_TRADE_PCT")
    min_lot = _env_float("MIN_LOT")
    max_lot = _env_float("MAX_LOT")
    lot_step = _env_float("LOT_STEP")
    rsi_period = _env_int("RSI_PERIOD")
    rsi_buy_max = _env_float("RSI_BUY_MAX")
    rsi_sell_min = _env_float("RSI_SELL_MIN")
    atr_period = _env_int("ATR_PERIOD")
    atr_sl_multiplier = _env_float("ATR_SL_MULTIPLIER")
    atr_tp_multiplier = _env_float("ATR_TP_MULTIPLIER")
    atr_entry_multiplier = _env_float("ATR_ENTRY_MULTIPLIER")
    candle_body_ratio = _env_float("CANDLE_BODY_RATIO")
    session_start_london_wib = _env_int("SESSION_START_LONDON_WIB")
    session_end_ny_wib = _env_int("SESSION_END_NY_WIB")
    strategy = StrategyConfig(
        entry_timeframe=str(entry_timeframe) if entry_timeframe is not None else StrategyConfig.entry_timeframe,
        trend_timeframe=str(trend_timeframe) if trend_timeframe is not None else StrategyConfig.trend_timeframe,
        ema_trend=int(ema_trend) if ema_trend is not None else StrategyConfig.ema_trend,
        stoch_period=int(stoch_period) if stoch_period is not None else StrategyConfig.stoch_period,
        stoch_smooth_k=int(stoch_smooth_k) if stoch_smooth_k is not None else StrategyConfig.stoch_smooth_k,
        stoch_smooth_d=int(stoch_smooth_d) if stoch_smooth_d is not None else StrategyConfig.stoch_smooth_d,
        stoch_oversold=float(stoch_oversold) if stoch_oversold is not None else StrategyConfig.stoch_oversold,
        stoch_overbought=float(stoch_overbought) if stoch_overbought is not None else StrategyConfig.stoch_overbought,
        stoch_min_gap=float(stoch_min_gap) if stoch_min_gap is not None else StrategyConfig.stoch_min_gap,
        macd_fast=int(macd_fast) if macd_fast is not None else StrategyConfig.macd_fast,
        macd_slow=int(macd_slow) if macd_slow is not None else StrategyConfig.macd_slow,
        macd_signal=int(macd_signal) if macd_signal is not None else StrategyConfig.macd_signal,
        ema_slope_min=float(ema_slope_min) if ema_slope_min is not None else StrategyConfig.ema_slope_min,
        ema_gate1_start_wib=int(ema_gate1_start_wib) if ema_gate1_start_wib is not None else StrategyConfig.ema_gate1_start_wib,
        ema_gate1_end_wib=int(ema_gate1_end_wib) if ema_gate1_end_wib is not None else StrategyConfig.ema_gate1_end_wib,
        ema_gate2_start_wib=int(ema_gate2_start_wib) if ema_gate2_start_wib is not None else StrategyConfig.ema_gate2_start_wib,
        ema_gate2_end_wib=int(ema_gate2_end_wib) if ema_gate2_end_wib is not None else StrategyConfig.ema_gate2_end_wib,
        risk_per_trade_pct=float(risk_per_trade_pct) if risk_per_trade_pct is not None else StrategyConfig.risk_per_trade_pct,
        min_lot=float(min_lot) if min_lot is not None else StrategyConfig.min_lot,
        max_lot=float(max_lot) if max_lot is not None else StrategyConfig.max_lot,
        lot_step=float(lot_step) if lot_step is not None else StrategyConfig.lot_step,
        spread_max=float(spread_max) if spread_max is not None else StrategyConfig.spread_max,
        rsi_period=int(rsi_period) if rsi_period is not None else StrategyConfig.rsi_period,
        rsi_buy_max=float(rsi_buy_max) if rsi_buy_max is not None else StrategyConfig.rsi_buy_max,
        rsi_sell_min=float(rsi_sell_min) if rsi_sell_min is not None else StrategyConfig.rsi_sell_min,
        atr_period=int(atr_period) if atr_period is not None else StrategyConfig.atr_period,
        atr_sl_multiplier=float(atr_sl_multiplier) if atr_sl_multiplier is not None else StrategyConfig.atr_sl_multiplier,
        atr_tp_multiplier=float(atr_tp_multiplier) if atr_tp_multiplier is not None else StrategyConfig.atr_tp_multiplier,
        atr_entry_multiplier=float(atr_entry_multiplier) if atr_entry_multiplier is not None else StrategyConfig.atr_entry_multiplier,
        candle_body_ratio=float(candle_body_ratio) if candle_body_ratio is not None else StrategyConfig.candle_body_ratio,
        session_start_london_wib=int(session_start_london_wib) if session_start_london_wib is not None else StrategyConfig.session_start_london_wib,
        session_end_ny_wib=int(session_end_ny_wib) if session_end_ny_wib is not None else StrategyConfig.session_end_ny_wib,
    )

    magic = _env_int("MAGIC")
    bars = _env_int("BARS")
    poll = _env_float("POLL_INTERVAL_SECONDS")
    live = LiveConfig(
        magic=int(magic) if magic is not None else LiveConfig.magic,
        bars=int(bars) if bars is not None else LiveConfig.bars,
        poll_interval_seconds=float(poll) if poll is not None else LiveConfig.poll_interval_seconds,
        log_dir=project_root / "logs",
        text_log_filename=LiveConfig.text_log_filename,
        decisions_csv_filename=LiveConfig.decisions_csv_filename,
    )

    bt_start = _env_str("BACKTEST_START")
    bt_end = _env_str("BACKTEST_END")
    bt_balance = _env_float("BACKTEST_INITIAL_BALANCE")
    bt_leverage = _env_int("BACKTEST_LEVERAGE")
    backtest = BacktestConfig(
        start_date=bt_start or BacktestConfig.start_date,
        end_date=bt_end or BacktestConfig.end_date,
        initial_balance=float(bt_balance) if bt_balance is not None else BacktestConfig.initial_balance,
        leverage=int(bt_leverage) if bt_leverage is not None else BacktestConfig.leverage,
        log_dir=project_root / "logs",
    )

    return AppConfig(
        mode=mode,
        project_root=project_root,
        mt5=mt5,
        strategy=strategy,
        live=live,
        backtest=backtest,
    )
