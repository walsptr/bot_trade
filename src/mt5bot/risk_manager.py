import logging
import math
from typing import Final


_EPS: Final[float] = 1e-12


def round_lot(lot: float, lot_step: float) -> float:
    """Bulatkan lot ke bawah ke kelipatan lot_step."""
    lot = float(lot)
    lot_step = float(lot_step)
    if lot_step <= 0.0:
        raise ValueError("lot_step must be > 0")
    if lot <= 0.0:
        return 0.0
    steps = math.floor((lot / lot_step) + _EPS)
    return float(steps) * lot_step


def calculate_lot(
    balance: float,
    sl_distance: float,
    risk_pct: float,
    min_lot: float,
    max_lot: float,
    lot_step: float,
    contract_size: float = 100.0,
) -> float:
    """Hitung lot berbasis risk_per_trade_pct terhadap balance."""
    logger = logging.getLogger(__name__)

    balance = float(balance)
    sl_distance = float(sl_distance)
    risk_pct = float(risk_pct)
    min_lot = float(min_lot)
    max_lot = float(max_lot)
    lot_step = float(lot_step)
    contract_size = float(contract_size)

    if min_lot <= 0.0:
        raise ValueError("min_lot must be > 0")
    if max_lot < min_lot:
        raise ValueError("max_lot must be >= min_lot")
    if lot_step <= 0.0:
        raise ValueError("lot_step must be > 0")
    if contract_size <= 0.0:
        contract_size = 100.0

    if balance <= 0.0 or risk_pct <= 0.0 or sl_distance <= 0.0:
        logger.warning("Balance terlalu kecil, pakai min_lot=%.2f", min_lot)
        return float(min_lot)

    risk_amount = balance * (risk_pct / 100.0)
    denom = sl_distance * contract_size
    if denom <= 0.0:
        logger.warning("Balance terlalu kecil, pakai min_lot=%.2f", min_lot)
        return float(min_lot)

    lot_raw = risk_amount / denom
    lot_rounded = round_lot(lot_raw, lot_step)

    if lot_rounded < min_lot:
        logger.warning("Balance terlalu kecil, pakai min_lot=%.2f", min_lot)
        return float(min_lot)

    if lot_rounded > max_lot:
        return float(max_lot)
    return float(lot_rounded)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    assert round_lot(0.019, 0.01) == 0.01
    assert round_lot(0.02, 0.01) == 0.02
    assert round_lot(0.0, 0.01) == 0.0

    lot1 = calculate_lot(
        balance=1000.0,
        sl_distance=10.0,
        risk_pct=1.0,
        min_lot=0.01,
        max_lot=0.05,
        lot_step=0.01,
        contract_size=100.0,
    )
    assert lot1 == 0.01

    lot2 = calculate_lot(
        balance=1000.0,
        sl_distance=1.0,
        risk_pct=5.0,
        min_lot=0.01,
        max_lot=0.05,
        lot_step=0.01,
        contract_size=100.0,
    )
    assert lot2 == 0.05

    lot3 = calculate_lot(
        balance=1.0,
        sl_distance=10.0,
        risk_pct=1.0,
        min_lot=0.01,
        max_lot=0.05,
        lot_step=0.01,
        contract_size=100.0,
    )
    assert lot3 == 0.01
