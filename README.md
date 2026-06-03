# MT5 Python Bot (Live + Backtest)

Project ini adalah bot trading untuk MetaTrader 5 (MT5) berbasis Python yang bisa jalan di 2 mode:

- `live`: jalan realtime, membaca data M5, generate signal, lalu eksekusi order.
- `backtest`: simulasi trading di periode tertentu dan menghasilkan log + summary + trade list.

Semua konfigurasi utama diatur lewat file `.env`. Template lengkap tersedia di `.env.example`.

## Quick Start

1) Install dependency

```bash
py -m pip install -r requirements.txt
```

2) Copy env

```bash
copy .env.example .env
```

3) Isi `.env`

- Untuk `live`, isi kredensial MT5 (`MT5_LOGIN/MT5_PASSWORD/MT5_SERVER`) dan path terminal (`MT5_PATH`).
- Untuk `backtest`, set `MODE=backtest` dan isi parameter backtest.

4) Run

```bash
py main.py
```

## ENV Variables

Catatan:

- Semua env var di bawah benar-benar dibaca oleh aplikasi via [main.py](file:///c:/Users/alsgm/AppData/Roaming/MetaQuotes/Terminal/D0E8209F77C8CF37AD8BF550E51FF075/MQL5/Scripts/python/main.py) dan [config.py](file:///c:/Users/alsgm/AppData/Roaming/MetaQuotes/Terminal/D0E8209F77C8CF37AD8BF550E51FF075/MQL5/Scripts/python/src/mt5bot/config.py).
- Default value diambil dari `StrategyConfig`, `LiveConfig`, `BacktestConfig`.

### App

| Variable | Tipe | Default | Fungsi |
|---|---:|---:|---|
| `MODE` | str | `live` | Mode aplikasi: `live` atau `backtest`. |
| `RUN_ONCE` | bool-ish | `0` | Jika `1/true/yes/on`, loop `live` akan berhenti setelah 1 iterasi (berguna untuk debug). |

### MT5 Connection

| Variable | Tipe | Default | Fungsi |
|---|---:|---:|---|
| `MT5_LOGIN` | int | (none) | Login akun MT5. Wajib untuk `live` (dan untuk `backtest` jika butuh akses history dari terminal). |
| `MT5_PASSWORD` | str | (none) | Password akun MT5. |
| `MT5_SERVER` | str | (none) | Nama server broker (contoh: `Exness-MT5Trial...`). |
| `MT5_PATH` | str | (none) | Path ke `terminal64.exe` MT5. |
| `MT5_SYMBOL` | str | `XAUUSDm` | Symbol yang ditradingkan/backtest. Kalau broker pakai suffix, set di sini. |

### Execution & Money Management

| Variable | Tipe | Default | Fungsi |
|---|---:|---:|---|
| `SPREAD_MAX` | float | `0.40` | Maks spread (dalam “price units” sesuai yang dihitung bot). Kalau spread lebih besar, signal akan ditolak. |
| `RISK_PER_TRADE_PCT` | float | `1.5` | Risk per trade dalam persen dari balance (dipakai untuk hitung lot). Contoh: `1.0` berarti 1% balance per trade. |
| `MIN_LOT` | float | `0.01` | Lot minimum yang diizinkan bot. |
| `MAX_LOT` | float | `0.05` | Lot maksimum yang diizinkan bot. |
| `LOT_STEP` | float | `0.01` | Kelipatan lot (pembulatan volume). |

### Strategy – Trend, Momentum, Volatility

#### Timeframes

| Variable | Tipe | Default | Fungsi |
|---|---:|---:|---|
| `ENTRY_TIMEFRAME` | str | `M5` | Timeframe utama untuk entry/eksekusi signal (rates utama yang diproses strategi). Contoh: `M5`, `M15`, `H1`. |
| `TREND_TIMEFRAME` | str | `M15` | Timeframe untuk trend filter (EMA + slope gate). Contoh: `M15`, `H1`. |

#### EMA Trend

| Variable | Tipe | Default | Fungsi |
|---|---:|---:|---|
| `EMA_TREND` | int | `50` | Period EMA untuk trend filter. Dipakai sebagai “arah utama” (trend). |

#### Stochastic (tetap tersedia untuk tuning/filter)

| Variable | Tipe | Default | Fungsi |
|---|---:|---:|---|
| `STOCH_PERIOD` | int | `5` | Period Stochastic. |
| `STOCH_SMOOTH_K` | int | `3` | Smoothing %K. |
| `STOCH_SMOOTH_D` | int | `3` | Smoothing %D. |
| `STOCH_OVERSOLD` | float | `20.0` | Threshold oversold. |
| `STOCH_OVERBOUGHT` | float | `80.0` | Threshold overbought. |
| `STOCH_MIN_GAP` | float | `2.0` | Minimal jarak K–D supaya signal dianggap “cukup tegas”. |

#### MACD

| Variable | Tipe | Default | Fungsi |
|---|---:|---:|---|
| `MACD_FAST` | int | `5` | Fast EMA period untuk MACD. |
| `MACD_SLOW` | int | `13` | Slow EMA period untuk MACD. |
| `MACD_SIGNAL` | int | `9` | Signal EMA period untuk MACD. Jika `1`, histogram akan selalu `0.0` (karena signal line = macd line). |
| `EMA_SLOPE_MIN` | float | `0.0` | Threshold minimum untuk EMA slope gate di jam rawan. `0.0` berarti cukup cek arah: BUY perlu slope positif, SELL perlu slope negatif. |
| `EMA_GATE1_START_WIB` | int | `7` | Jam mulai EMA slope gate (WIB) untuk window 1. |
| `EMA_GATE1_END_WIB` | int | `15` | Jam akhir EMA slope gate (WIB) untuk window 1 (exclusive). Default mencakup 07–14 WIB. |
| `EMA_GATE2_START_WIB` | int | `19` | Jam mulai EMA slope gate (WIB) untuk window 2. |
| `EMA_GATE2_END_WIB` | int | `24` | Jam akhir EMA slope gate (WIB) untuk window 2 (exclusive). Default mencakup 19–23 WIB. |

#### RSI Gate

| Variable | Tipe | Default | Fungsi |
|---|---:|---:|---|
| `RSI_PERIOD` | int | `14` | Period RSI. |
| `RSI_BUY_MAX` | float | `60.0` | Gate untuk BUY: jika RSI terlalu tinggi (di atas ini), BUY bisa ditolak (menghindari buy di kondisi terlalu overbought). |
| `RSI_SELL_MIN` | float | `40.0` | Gate untuk SELL: jika RSI terlalu rendah (di bawah ini), SELL bisa ditolak (menghindari sell di kondisi terlalu oversold). |

#### ATR-based SL/TP + Entry Selectivity

| Variable | Tipe | Default | Fungsi |
|---|---:|---:|---|
| `ATR_PERIOD` | int | `14` | Period ATR. |
| `ATR_SL_MULTIPLIER` | float | `1.5` | Jarak SL = `ATR * multiplier`. |
| `ATR_TP_MULTIPLIER` | float | `3.0` | Jarak TP = `ATR * multiplier`. |
| `ATR_ENTRY_MULTIPLIER` | float | `1.0` | Gate entry berbasis range candle: butuh range yang cukup besar relatif terhadap ATR (semakin besar → semakin selektif). |

#### Candle Filter

| Variable | Tipe | Default | Fungsi |
|---|---:|---:|---|
| `CANDLE_BODY_RATIO` | float | `0.3` | Minimal rasio body candle terhadap range candle untuk menganggap candle “tegas” (filter candle doji/small body). |

### Session Filter (WIB)

| Variable | Tipe | Default | Fungsi |
|---|---:|---:|---|
| `SESSION_START_LONDON_WIB` | int | `15` | Jam mulai trading (WIB, 0–24). |
| `SESSION_END_NY_WIB` | int | `23` | Jam selesai trading (WIB, 0–24). |

### Live Runner

| Variable | Tipe | Default | Fungsi |
|---|---:|---:|---|
| `MAGIC` | int | `20260602` | Magic number untuk membedakan posisi bot vs manual/EA lain. |
| `BARS` | int | `200` | Jumlah bar yang diambil untuk hitung indikator pada `ENTRY_TIMEFRAME`. |
| `POLL_INTERVAL_SECONDS` | float | `1.0` | Interval polling (deteksi candle baru). |

### Backtest

| Variable | Tipe | Default | Fungsi |
|---|---:|---:|---|
| `BACKTEST_START` | str | `2026-05-01` | Tanggal mulai backtest (`YYYY-MM-DD`). |
| `BACKTEST_END` | str | `2026-06-01` | Tanggal akhir backtest (`YYYY-MM-DD`). |
| `BACKTEST_INITIAL_BALANCE` | float | `50.0` | Balance awal untuk simulasi. |
| `BACKTEST_LEVERAGE` | int | `2000` | Leverage yang dipakai di simulasi margin. |

## Output Files

Semua output ada di folder `logs/`, contoh:

- `backtest_YYYY-MM-DD_YYYY-MM-DD.log`
- `backtest_summary_YYYY-MM-DD_YYYY-MM-DD.json`
- `backtest_trades_YYYY-MM-DD_YYYY-MM-DD.csv`
- Live decision journal: `logs/decisions.csv`
