import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import MetaTrader5 as mt5

from .config import MT5Config


class MT5Client:
    def __init__(self) -> None:
        self._connected = False
        self._filling_mode_by_symbol: Dict[str, int] = {}

    def connect(self, cfg: MT5Config, logger) -> str:
        if cfg.login is None or cfg.password is None or cfg.server is None:
            raise RuntimeError("MT5_LOGIN/MT5_PASSWORD/MT5_SERVER belum di-set atau invalid")

        init_ok = mt5.initialize(path=cfg.path) if cfg.path else mt5.initialize()
        if not init_ok:
            raise RuntimeError(f"mt5.initialize gagal: {mt5.last_error()}")

        if not mt5.login(login=int(cfg.login), password=str(cfg.password), server=str(cfg.server)):
            err = mt5.last_error()
            mt5.shutdown()
            raise RuntimeError(f"mt5.login gagal: {err}")

        symbol = self._select_symbol(cfg.symbol, logger)
        self._connected = True

        info = mt5.account_info()
        if info:
            logger.info(
                "Connected. login=%s balance=%.2f equity=%.2f currency=%s symbol=%s",
                getattr(info, "login", None),
                getattr(info, "balance", 0.0),
                getattr(info, "equity", 0.0),
                getattr(info, "currency", ""),
                symbol,
            )
        else:
            logger.info("Connected. account_info unavailable symbol=%s", symbol)

        return symbol

    def shutdown(self) -> None:
        if self._connected:
            mt5.shutdown()
        self._connected = False

    def _select_symbol(self, symbol: str, logger) -> str:
        symbol = str(symbol)
        selected = False
        last_err = None
        for _ in range(20):
            if mt5.symbol_select(symbol, True):
                selected = True
                break
            last_err = mt5.last_error()
            time.sleep(0.5)

        if selected:
            return symbol

        candidates = mt5.symbols_get(f"{symbol}*")
        if candidates:
            found = None
            for s in candidates:
                name = str(getattr(s, "name", ""))
                if name == symbol:
                    found = name
                    break
            if found is None:
                found = str(getattr(candidates[0], "name", ""))
            if found:
                logger.info("Symbol %s tidak ditemukan. Pakai alternatif: %s", symbol, found)
                symbol = found
                for _ in range(10):
                    if mt5.symbol_select(symbol, True):
                        return symbol
                    last_err = mt5.last_error()
                    time.sleep(0.5)

        sample = ""
        try:
            c2 = mt5.symbols_get("XAUUSD*")
            if c2:
                sample = ", contoh tersedia: " + ", ".join(str(getattr(s, "name", "")) for s in c2[:5])
        except Exception:
            sample = ""
        err = last_err if last_err is not None else mt5.last_error()
        mt5.shutdown()
        raise RuntimeError(f"symbol_select gagal untuk {symbol}: {err}{sample}. Jika broker pakai suffix, set MT5_SYMBOL")

    def symbol_info(self, symbol: str):
        info = mt5.symbol_info(symbol)
        if info is None:
            raise RuntimeError(f"symbol_info None untuk {symbol}")
        return info

    def symbol_tick(self, symbol: str):
        t = mt5.symbol_info_tick(symbol)
        if t is None:
            raise RuntimeError(f"symbol_info_tick None untuk {symbol}")
        return t

    def spread(self, symbol: str) -> Tuple[float, float, float]:
        t = self.symbol_tick(symbol)
        bid = float(t.bid)
        ask = float(t.ask)
        return bid, ask, ask - bid

    def normalize_price(self, symbol: str, price: float) -> float:
        digits = int(self.symbol_info(symbol).digits)
        return round(float(price), digits)

    def positions_get_bot(self, symbol: str, magic: int):
        positions = mt5.positions_get(symbol=symbol)
        if positions is None:
            return None
        for p in positions:
            if int(getattr(p, "magic", 0)) == int(magic):
                return p
        return None

    def _invalid_fill_retcode(self) -> int:
        return int(getattr(mt5, "TRADE_RETCODE_INVALID_FILL", 10030))

    def _candidate_filling_modes(self, symbol: str) -> List[int]:
        info = mt5.symbol_info(symbol)
        modes: List[int] = []
        if info is not None:
            fm = getattr(info, "filling_mode", None)
            if fm is not None:
                try:
                    modes.append(int(fm))
                except Exception:
                    pass

        for m in (mt5.ORDER_FILLING_RETURN, mt5.ORDER_FILLING_IOC, mt5.ORDER_FILLING_FOK):
            if int(m) not in modes:
                modes.append(int(m))
        return modes

    def _resolve_filling_mode(self, symbol: str) -> int:
        cached = self._filling_mode_by_symbol.get(str(symbol))
        if cached is not None:
            return int(cached)
        modes = self._candidate_filling_modes(symbol)
        return int(modes[0]) if modes else int(mt5.ORDER_FILLING_IOC)

    def _order_send_with_filling_fallback(self, logger, request: Dict[str, Any]) -> Optional[Any]:
        symbol = str(request.get("symbol", ""))
        if not symbol:
            result = mt5.order_send(request)
            if result is None:
                logger.error("order_send None: %s", mt5.last_error())
            return result

        candidates = self._candidate_filling_modes(symbol)
        cached = self._filling_mode_by_symbol.get(symbol)
        if cached is not None and int(cached) in candidates:
            candidates = [int(cached)] + [m for m in candidates if int(m) != int(cached)]

        invalid_fill = self._invalid_fill_retcode()
        last_result = None
        for fill in candidates:
            req = dict(request)
            req["type_filling"] = int(fill)
            result = mt5.order_send(req)
            last_result = result
            if result is None:
                logger.error("order_send None: %s", mt5.last_error())
                return None

            ret = int(getattr(result, "retcode", -1))
            if ret == mt5.TRADE_RETCODE_DONE:
                self._filling_mode_by_symbol[symbol] = int(fill)
                return result
            if ret == int(invalid_fill):
                continue
            return result

        return last_result

    def close_position(self, logger, position, *, deviation_points: int, magic: int, comment: str) -> bool:
        symbol = str(position.symbol)
        volume = float(position.volume)
        ticket = int(position.ticket)
        pos_type = int(position.type)

        tick = self.symbol_tick(symbol)
        if pos_type == mt5.POSITION_TYPE_BUY:
            order_type = mt5.ORDER_TYPE_SELL
            price = float(tick.bid)
        else:
            order_type = mt5.ORDER_TYPE_BUY
            price = float(tick.ask)

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": order_type,
            "position": ticket,
            "price": self.normalize_price(symbol, price),
            "deviation": int(deviation_points),
            "magic": int(magic),
            "comment": str(comment),
            "type_time": mt5.ORDER_TIME_GTC,
        }

        result = self._order_send_with_filling_fallback(logger, request)
        if result is None:
            return False

        ok = int(getattr(result, "retcode", -1)) == mt5.TRADE_RETCODE_DONE
        logger.info(
            "CLOSE ticket=%s type=%s vol=%.2f retcode=%s comment=%s filling=%s",
            ticket,
            "BUY" if pos_type == mt5.POSITION_TYPE_BUY else "SELL",
            volume,
            getattr(result, "retcode", None),
            getattr(result, "comment", ""),
            self._filling_mode_by_symbol.get(symbol),
        )
        return ok

    def send_order(
        self,
        logger,
        symbol: str,
        direction: str,
        *,
        lot: float,
        sl: float,
        tp: float,
        deviation_points: int,
        magic: int,
        comment: str,
    ) -> Tuple[bool, Optional[Any]]:
        tick = self.symbol_tick(symbol)

        direction = direction.upper().strip()
        if direction == "BUY":
            order_type = mt5.ORDER_TYPE_BUY
            price = float(tick.ask)
        elif direction == "SELL":
            order_type = mt5.ORDER_TYPE_SELL
            price = float(tick.bid)
        else:
            raise ValueError("direction must be BUY or SELL")

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": float(lot),
            "type": order_type,
            "price": self.normalize_price(symbol, price),
            "sl": self.normalize_price(symbol, sl),
            "tp": self.normalize_price(symbol, tp),
            "deviation": int(deviation_points),
            "magic": int(magic),
            "comment": str(comment),
            "type_time": mt5.ORDER_TIME_GTC,
        }

        result = self._order_send_with_filling_fallback(logger, request)
        if result is None:
            return False, None

        ok = int(getattr(result, "retcode", -1)) == mt5.TRADE_RETCODE_DONE
        logger.info(
            "OPEN %s lot=%.2f price=%.5f sl=%.5f tp=%.5f retcode=%s comment=%s filling=%s",
            direction,
            float(lot),
            float(request["price"]),
            float(request["sl"]),
            float(request["tp"]),
            getattr(result, "retcode", None),
            getattr(result, "comment", ""),
            self._filling_mode_by_symbol.get(symbol),
        )
        return ok, result

    def copy_rates_from_pos(self, symbol: str, timeframe: int, start_pos: int, bars: int) -> List[Dict[str, Any]]:
        rates = mt5.copy_rates_from_pos(symbol, timeframe, start_pos, bars)
        if rates is None:
            raise RuntimeError(f"copy_rates_from_pos returned None: {mt5.last_error()}")
        if len(rates) == 0:
            raise RuntimeError("copy_rates_from_pos returned 0 bars")

        out: List[Dict[str, Any]] = []
        for r in rates:
            out.append(
                {
                    "time": int(r["time"]),
                    "open": float(r["open"]),
                    "high": float(r["high"]),
                    "low": float(r["low"]),
                    "close": float(r["close"]),
                    "tick_volume": int(r["tick_volume"]),
                }
            )
        out.sort(key=lambda x: x["time"])
        return out

    def copy_rates_range(self, symbol: str, timeframe: int, start_dt: datetime, end_dt: datetime) -> List[Dict[str, Any]]:
        rates = mt5.copy_rates_range(symbol, timeframe, start_dt, end_dt)
        if rates is None:
            raise RuntimeError(f"copy_rates_range returned None: {mt5.last_error()}")
        if len(rates) == 0:
            raise RuntimeError("copy_rates_range returned 0 bars")

        out: List[Dict[str, Any]] = []
        for r in rates:
            out.append(
                {
                    "time": int(r["time"]),
                    "open": float(r["open"]),
                    "high": float(r["high"]),
                    "low": float(r["low"]),
                    "close": float(r["close"]),
                }
            )
        out.sort(key=lambda x: x["time"])
        return out

    def copy_ticks_range(self, symbol: str, start_dt: datetime, end_dt: datetime, flags: int) -> List[Dict[str, Any]]:
        chunk = mt5.copy_ticks_range(symbol, start_dt, end_dt, flags)
        if chunk is None:
            raise RuntimeError(f"copy_ticks_range returned None: {mt5.last_error()}")
        out: List[Dict[str, Any]] = []
        for t in chunk:
            out.append(
                {
                    "time_msc": int(t["time_msc"]),
                    "bid": float(t["bid"]),
                    "ask": float(t["ask"]),
                }
            )
        out.sort(key=lambda x: x["time_msc"])
        return out

    def contract_size(self, symbol: str) -> float:
        info = mt5.symbol_info(symbol)
        if info is None:
            return 1.0
        v = float(getattr(info, "trade_contract_size", 1.0) or 1.0)
        return v if v > 0 else 1.0
