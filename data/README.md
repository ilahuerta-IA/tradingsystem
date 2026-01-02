# Data Directory

Place your CSV price data files here.

## Expected Format (Darwinex 5-minute)

```csv
Date,Time,Open,High,Low,Close,Volume
20240701,00:00:00,171.234,171.250,171.200,171.210,1234
20240701,00:05:00,171.210,171.235,171.195,171.220,1156
20240701,00:10:00,171.220,171.240,171.210,171.235,987
```

## Column Mapping

| Column | Index | Description |
|--------|-------|-------------|
| Date | 0 | Format: YYYYMMDD |
| Time | 1 | Format: HH:MM:SS |
| Open | 2 | Opening price |
| High | 3 | Highest price |
| Low | 4 | Lowest price |
| Close | 5 | Closing price |
| Volume | 6 | Tick volume |

## Data Sources

You can obtain forex data from:
- [Darwinex](https://www.darwinex.com/) - Free historical data
- [Dukascopy](https://www.dukascopy.com/swiss/english/marketwatch/historical/) - Free tick data
- [HistData](https://www.histdata.com/) - Free forex data

## Important Notes

1. **Timezone**: Data should be in UTC
2. **Timeframe**: 5-minute candles
3. **File naming**: `EURJPY_5m_5Yea.csv` (or update path in `config/settings.py`)

## Sample File

For testing, you can create a minimal CSV with the format above. The strategy requires at least 100 bars for indicator warmup.
