# LYRA Strategy

**Type:** Short-Selling on Index CFDs during VOLATILE_UP regime  
**Assets:** SP500, UK100 (confirmed edge). NDX descartado.  
**Direction:** Short Only  
**Timeframe:** H1 (resampled from 5m)  
**Regime:** VOLATILE_UP (code 1) — complemento bear-market de ALTAIR  
**Broker:** Darwinex Zero CFD indices (margin 5%)

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Prestudy Results](#prestudy-results)
4. [Backtest Results (Full Sample)](#backtest-results-full-sample)
5. [Portfolio Complementarity Analysis](#portfolio-complementarity-analysis)
6. [IS/OOS Plan](#isoos-plan)
7. [Configuration](#configuration)
8. [Tools](#tools)
9. [Changelog](#changelog)

---

## Overview

LYRA es una estrategia **SHORT-only** diseñada para operar índices CFD durante regímenes
de alta volatilidad (VOLATILE_UP). Es el inverso lógico de ALTAIR (LONG stocks en CALM_UP).

La tesis: cuando el mercado está en régimen volátil alcista, los reversals bajistas desde
zonas de sobrecompra (DTOSC) ofrecen oportunidades de short con edge positivo.

**Rol en el portfolio:** Estabilizador de allocation. No es un hedge directo de ALTAIR,
sino una fuente de retorno decorrelacionada durante periodos donde ALTAIR y VEGA pueden
tener menor actividad. Con peso reducido en allocation, aporta diversificación.

---

## Architecture

```
Layer 1 (D1): Regime Filter
  - Mom12M (SMA 252) + ATR_ratio + Mom63d
  - Solo opera en VOLATILE_UP (regime code 1)

Layer 2 (H1): Signal
  - DTOSC bearish reversal from overbought (>75)
  - Fast cruza por debajo de Slow desde zona OB

Layer 3 (Execution):
  - Tr-1BL confirmation (sell stop below trigger bar low)
  - SL: above swing high (or ATR-based fallback)
  - TP: ATR-based below entry
  - Risk-based position sizing (1% equity risk)

State Machine:
  SCANNING -> [DTOSC signal] -> TRIGGERED
  TRIGGERED -> [low < sell_stop] -> IN_POSITION
  IN_POSITION -> [SL/TP/TIME/REGIME] -> SCANNING
```

---

## Prestudy Results

Prestudy con señales DTOSC + régimen VOLATILE_UP sobre 6 índices (2017-2025):

| Index | Trades | WR% | PF | Net Return |
|-------|--------|-----|-----|------------|
| NDX | 135 | 43.0% | 1.18 | +22.94% |
| SP500 | 133 | 42.1% | 1.12 | +10.60% |
| UK100 | 177 | 46.4% | 1.23 | +12.65% |
| NI225 | 73 | 42.5% | 1.08 | +9.77% |
| DJ30 | 147 | 38.8% | 0.95 | -4.46% |
| DAX40 | 166 | 43.4% | 0.96 | -4.09% |

**Conclusión prestudy:** NDX, SP500, UK100 con edge positivo. NI225 marginal. DJ30/DAX40 descartados.

---

## Backtest Results (Full Sample)

Ejecutado con parámetros optimizados (SL 2.0x ATR, TP 3.0x, Tr-1BL, Swing High SL):

### SP500_LYRA
```
Trades: 61 | WR: 39.3% | PF: 1.44
Sharpe: 0.24 | Sortino: 0.04 | CAGR: 1.65%
MaxDD: 10.29% | Calmar: 0.16
MC95 DD: 11.19% | MC99: 13.49%
Net P&L: $15,107 | Commission: $323

Year    Trades  WR%     PF      PnL
2017      8    37.5%   1.04    $154
2018     10    40.0%   1.45  $2,795
2019      6    33.3%   1.56  $1,929
2020      9    44.4%   1.26  $1,251
2021     10    40.0%   1.71  $4,240
2022      1   100.0%    INF  $3,942
2023      2    50.0%   2.21  $1,134
2024      7    28.6%   0.60 -$1,921
2025      8    37.5%   1.36  $1,584
```

### UK100_LYRA
```
Trades: 103 | WR: 40.8% | PF: 1.42
Sharpe: 0.21 | Sortino: 0.04 | CAGR: 1.64%
MaxDD: 11.43% | Calmar: 0.14
MC95 DD: 13.05% | MC99: 15.55%
Net P&L: $22,521 | Commission: $8,003

Year    Trades  WR%     PF      PnL
2017      6     0.0%   0.00 -$3,741
2018      1     0.0%   0.00 -$1,038
2019      7    28.6%   0.44 -$2,082
2020     10    40.0%   0.71 -$1,624
2021     19    42.1%   2.59 $11,695
2022     14    35.7%   1.27  $2,004
2023      4    75.0%   2.97  $4,093
2024     28    42.9%   1.29  $4,752
2025     14    57.1%   2.30  $8,463
```

### NDX_LYRA (DESCARTADO)
```
Trades: 70 | WR: 32.9% | PF: 0.72
Net P&L: -$11,822 | CAGR: -1.80% | MaxDD: 23.31%
```
NDX pierde dinero con los parámetros actuales. Descartado del portfolio.

---

## Portfolio Complementarity Analysis

### LYRA vs ALTAIR+VEGA (yearly PnL, $)

| Year | ALTAIR | VEGA (3 pairs) | LYRA SP500 | LYRA UK100 | A+V | A+V+L(SP+UK) |
|------|--------|----------------|------------|------------|-----|---------------|
| 2017 | — | +13,649 | +154 | -3,741 | +13,649 | +10,062 |
| 2018 | -5,358 | +18,940 | +2,795 | -1,038 | +13,582 | +15,339 |
| 2019 | +17,595 | +26,265 | +1,929 | -2,082 | +43,860 | +43,707 |
| 2020 | +41,285 | +56,702 | +1,251 | -1,624 | +97,987 | +97,614 |
| 2021 | +10,676 | +34,993 | +4,240 | +11,695 | +45,669 | +61,604 |
| 2022 | +15,685 | +19,524 | +3,942 | +2,004 | +35,209 | +41,155 |
| 2023 | +76,702 | +18,845 | +1,134 | +4,093 | +95,547 | +100,774 |
| 2024 | +20,894 | +45,899 | -1,921 | +4,752 | +66,793 | +69,624 |
| 2025 | +21,784 | +64,751 | +1,584 | +8,463 | +86,535 | +96,582 |

### Observaciones clave

1. **LYRA SP500 sola**: 2.4% del PnL combinado A+V — insignificante como hedge.
2. **SP500 + UK100 juntos**: UK100 aporta más trades (103 vs 61) y compensa en años donde SP500 pierde (2024: UK100 +$4.7K vs SP500 -$1.9K).
3. **2021 destaca**: LYRA UK100 +$11.7K — año donde ALTAIR tuvo resultado modesto (+$10.7K).
4. **2017-2020 UK100 es negativo**: necesita warm-up o los parámetros no aplican pre-2021.
5. **Con allocation reducida (ej: 5-10% por índice)** el drawdown se controla y la diversificación aporta.
6. **No es hedge directo**: es fuente de retorno adicional decorrelacionada (SHORT index vs LONG stocks + forex mean-reversion).

### Conclusión allocation

- **VEGA**: backbone del portfolio (~65% allocation) — 3 pares forex, $422K, consistente.
- **ALTAIR**: growth engine (~25% allocation) — 14 stocks, $199K, concentrado en CALM_UP.
- **LYRA**: stabilizer (~10% allocation, split SP500/UK100) — $37.6K combined, decorrelación por dirección (SHORT) y régimen (VOLATILE_UP).

---

## IS/OOS Plan

Validación In-Sample / Out-of-Sample pendiente (siguiente fase):

### Propuesta de split
- **IS (In-Sample):** 2017-01-01 a 2022-12-31 (6 años)
- **OOS (Out-of-Sample):** 2023-01-01 a 2025-12-31 (3 años)

### Criterios de aprobación OOS
- PF > 1.20 en OOS
- WR > 35%
- Max DD < 15%
- MC95 DD < 18%
- Net PnL positivo cada año o 2/3 años positivos

### Assets para IS/OOS
- SP500_LYRA ✅
- UK100_LYRA ✅  
- NDX_LYRA ❌ (descartado — PF 0.72)

---

## Configuration

### SP500_LYRA
```python
Commission: $0.0275/contract
Hours: [14, 15, 16, 17, 18, 19]  # US session
bars_per_day: 7
```

### UK100_LYRA
```python
Commission: $0.98/contract
Hours: [8, 9, 10, 11, 12, 13, 14, 15, 16]  # London session
bars_per_day: 9
```

### Common params
```python
DTOSC: period=8, smooth_k=5, smooth_d=3, signal=3, OB=75, OS=25
Regime: SMA(252), ATR(252), allowed=(1,)  # VOLATILE_UP only
SL: 2.0x ATR (max 2.0x), swing_high fallback
TP: 3.0x ATR
Tr-1BL: ON, timeout=5
Max holding: 35 bars
Risk: 1% equity
```

---

## Tools

- `tools/lyra_optimizer.py` — 6-phase optimizer (sl, tp, entry, holding, regime, confirmation)
- `tools/analyze_lyra.py` — Trade log analyzer (12 sections: config, summary, ATR, hours, days, matrix, year, exit, bars, DTOSC, SL/ATR, holding quality)
- `run_backtest.py SP500_LYRA|UK100_LYRA` — Standard backtest runner

---

## Changelog

- **2026-04-12**: Strategy created. Full prestudy (6 indices), strategy implementation, optimizer, analyzer. SL optimization (max_sl=2.0 best). Entry/exit plot lines on backtrader chart. Complementarity analysis vs ALTAIR+VEGA. NDX descartado (PF 0.72). SP500 + UK100 confirmed for IS/OOS.
