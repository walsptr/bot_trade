# Catatan Jam (Metode CANDLE_ATR)

Sumber data: [backtest_trades_2026-01-01_2026-06-2.csv](file:///c:/Users/alsgm/AppData/Roaming/MetaQuotes/Terminal/D0E8209F77C8CF37AD8BF550E51FF075/MQL5/Scripts/python/logs/backtest_trades_2026-01-01_2026-06-2.csv)  
Metode: `ENTRY_MODEL=CANDLE_ATR`  
Basis jam: WIB, dihitung dari `open_time` trade.  
Jumlah trade pada CSV: 50.

## Jam Rawan (Net PnL negatif, sample >= 2 trade)

- 21 WIB: net -47.79 (n=4, PF=0.404)
- 04 WIB: net -42.02 (n=2, PF=0.000)
- 19 WIB: net -39.23 (n=2, PF=0.000)
- 17 WIB: net -15.40 (n=2, PF=0.000)

## Jam Bagus (Net PnL positif, sample >= 2 trade)

- 22 WIB: net +167.13 (n=2)
- 07 WIB: net +91.82 (n=3)
- 08 WIB: net +46.30 (n=4)
- 11 WIB: net +35.25 (n=3)
- 14 WIB: net +30.58 (n=4)

## Catatan

- Sample trade per jam masih kecil, jadi daftar ini bersifat indikasi awal dan perlu divalidasi lagi kalau trade count sudah lebih besar.
