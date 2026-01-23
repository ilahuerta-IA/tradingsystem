# 🚀 Modular Algorithmic Trading System

> **Production-grade backtesting & live trading framework.**  
> Designed for multi-strategy portfolios with proper risk management.

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Backtrader](https://img.shields.io/badge/backtrader-1.9.78-green.svg)](https://www.backtrader.com/)
[![MetaTrader5](https://img.shields.io/badge/MT5-Live%20Trading-orange.svg)](https://www.metatrader5.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

This repository implements a **clean, scalable architecture** for backtesting and live trading. It features centralized configuration, multi-asset support, and professional reporting.

**Current Version:** v0.3.0  
**Strategies:** Sunset Ogle (4-phase breakout) + KOI (Engulfing + EMA momentum)  
**Live Trading:** MT5 integration with multi-symbol monitoring

---

## 📂 Project Structure

```text
TradingSystem/
├── config/
│   ├── settings.py              # ⚙️ Central configuration for all strategies
│   ├── bot_settings.py          # 🤖 Live trading settings (broker, timezone)
│   └── credentials/             # 🔐 MT5 login credentials
├── lib/
│   ├── commission.py            # 💰 Forex commission with JPY P&L correction
│   └── filters.py               # 🎯 Reusable filter functions (time, ATR, angle, SL pips)
├── strategies/
│   ├── sunset_ogle.py           # 🌅 4-Phase State Machine strategy
│   └── koi_strategy.py          # 🐟 Engulfing + 5 EMAs + CCI strategy
├── live/
│   ├── connector.py             # 🔌 MT5 connection management
│   ├── executor.py              # 📤 Order execution with position sizing
│   ├── timezone.py              # 🌍 Broker timezone handling
│   └── checkers/                # 🔍 Live signal checkers
│       ├── sunset_ogle_checker.py
│       └── koi_checker.py
├── docs/                        # 📖 Strategy documentation
├── data/                        # 📊 CSV price data (not tracked in git)
├── logs/                        # 📝 Trade logs output
├── run_backtest.py              # 🧪 Backtest entry point
├── run_multi_live.py            # 🚀 Live trading entry point
└── requirements.txt
```

---

## ⚡ Key Features

### 🔧 Clean Architecture
- **SOLID Principles**: Single responsibility per module
- **Centralized Config**: Change parameters without touching strategy code
- **Scalable Design**: Easy to add new strategies and assets

### 🤖 Live Trading (MT5)
- **Multi-symbol monitoring**: Run 10+ configs simultaneously
- **Broker-aware position sizing**: Uses tick_value for accurate lot calculation
- **Auto-reconnection**: Handles MT5 disconnections gracefully
- **Timezone handling**: Converts broker time (UTC+2) to UTC for filters

### 💱 JPY Pair Handling (ERIS Logic)
Backtrader has known issues with JPY pairs due to different pip values. This system implements:
- **Position Size Normalization**: Divides by JPY rate (~150) for margin calculation
- **P&L Reconstruction**: Multiplies back for accurate profit/loss reporting
- **Commission Correction**: Calculates real lot size for proper fees

### 📊 Professional Reporting
- **Detailed Trade Reports**: Entry/Exit with ATR, Angle, Pips, Duration
- **Live Logging**: JSON trade logs + detailed monitor logs
- **Performance Metrics**: Win Rate, Profit Factor, Gross P/L

---

## 🚀 Quick Start

### 1. Clone & Setup
```bash
git clone https://github.com/yourusername/TradingSystem.git
cd TradingSystem
python -m venv venv
venv\Scripts\activate  # Windows
pip install -r requirements.txt
```

### 2. Add Your Data
Place your CSV file in the `data/` folder. Expected format (Darwinex 5m):
```csv
Date,Time,Open,High,Low,Close,Volume
20240701,00:00:00,171.234,171.250,171.200,171.210,1234
```

### 3. Configure
Edit `config/settings.py` to set your data path and parameters.

### 4. Run
```bash
python run_backtest.py
```

---

## 📈 Sample Output

```
============================================================
STRATEGY SUMMARY
============================================================
Total Trades: 38
Wins: 12 | Losses: 26
Win Rate: 31.6%
Profit Factor: 1.55
Gross Profit: $12,744.20
Gross Loss: $8,243.33
Total P&L: $4,500.01
Final Value: $104,500.01
============================================================
```

---

## 📖 Strategy Documentation

Detailed documentation for each implemented strategy:

| Strategy | Assets | Type | Description |
|----------|--------|------|-------------|
| Sunset Ogle | EURUSD, EURJPY, USDCAD, USDCHF, USDJPY | Trend / Breakout | 4-phase state machine with pullback entry |
| KOI | EURUSD, EURJPY, USDCAD, USDCHF, USDJPY | Momentum | Bullish engulfing + 5 EMAs ascending + CCI |

---

## 🚀 Quick Start

### Backtesting
```bash
python run_backtest.py
```

### Live Trading (Demo)
```bash
python run_multi_live.py
```

**Note:** Configure your MT5 credentials in `config/credentials/` before running live.

---

## 📋 Changelog

### v0.3.0 (2026-01-23)
- **Critical fix**: Added missing ATR filter to KOI live checker (matches backtest)
- Added version tracking to all log events (MONITOR_START, SIGNAL, TRADE)
- Logs now show version in startup header for traceability

### v0.2.9 (2026-01-21)
- Improved logging clarity: logs now show config_name (e.g., "EURJPY_KOI") instead of just strategy_name ("KOI")

### v0.2.8 (2026-01-21)
- Enhanced logging: shows which EMA failed, ATR in signals, SL pips

### v0.2.7 (2026-01-21)
- **Critical fix**: Added SL Pips Filter to KOI live checker (was missing)

### v0.2.6 (2026-01-21)
- **Critical fix**: Position sizing now uses broker tick_value correctly

### v0.2.5 (2026-01-20)
- Multi-symbol live monitoring with 10 concurrent configs
- Broker timezone handling (UTC+2 → UTC conversion)

---

## 🧪 Testing & Validation

This system was validated against the original monolithic implementation:

| Metric | Original | Modular System | Match |
|--------|----------|----------------|-------|
| Total Trades | 38 | 38 | ✅ |
| Win Rate | 31.58% | 31.58% | ✅ |
| Total P&L | $4,500.87 | $4,500.01 | ✅ |

---

## 📚 Learning Resources

If you're learning algorithmic trading, this codebase demonstrates:

1. **State Machine Design**: How to implement complex entry logic
2. **Risk Management**: Position sizing based on ATR and account equity
3. **Forex Specifics**: Handling JPY pairs, pip values, lot sizes
4. **Clean Code**: Separation of concerns, configuration management

---

## ⚠️ Disclaimer

**This software is for educational purposes only.**

- Past performance does not guarantee future results
- Always paper trade before using real capital
- The authors are not responsible for any financial losses

---

## 📄 License

MIT License - Feel free to use, modify, and distribute.

---

## 🤝 Contributing

Contributions are welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Submit a pull request with clear description