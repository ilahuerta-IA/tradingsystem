"""
HELIX Strategy - HTF Structure + Pullback + Breakout (using Spectral Entropy)

Based on SEDNA with key difference:
- Uses Spectral Entropy (SE) instead of Efficiency Ratio (ER) as HTF filter

HYPOTHESIS:
- SEDNA works well on JPY pairs (USDJPY, EURJPY) using ER
- SEDNA fails on EUR/CHF pairs (EURUSD, USDCHF) 
- SE might detect "structure" faster than ER on these pairs
- SE LOW = structured (vs ER HIGH = trending) - inverted logic

ENTRY SYSTEM (3 PHASES):
1. HTF STRUCTURE: SE <= threshold AND Close > KAMA (15m equiv)
2. PULLBACK: N bars without new HH, price respects KAMA
3. BREAKOUT: High > pullback HH + offset within N candles

EXIT SYSTEM:
- Stop Loss: Entry - (ATR x SL multiplier)
- Take Profit: Entry + (ATR x TP multiplier)

TARGET PAIRS: EURUSD, USDCHF (where SEDNA doesn't work)
"""
from __future__ import annotations
import math
from pathlib import Path
from datetime import datetime
from collections import defaultdict

import backtrader as bt
import numpy as np

from lib.filters import (
    check_time_filter,
    check_day_filter,
    check_atr_filter,
    check_sl_pips_filter,
    check_spectral_entropy_filter,
    detect_pullback,
    check_pullback_breakout,
)
from lib.indicators import SpectralEntropy, KAMA, SEStdDev
from lib.position_sizing import calculate_position_size


class EntryExitLines(bt.Indicator):
    """
    Indicator to plot entry/exit price levels as horizontal dashed lines.
    """
    lines = ('entry', 'stop_loss', 'take_profit')
    
    plotinfo = dict(
        subplot=False,
        plotlinelabels=True,
    )
    plotlines = dict(
        entry=dict(color='green', linestyle='--', linewidth=1.0),
        stop_loss=dict(color='red', linestyle='--', linewidth=1.0),
        take_profit=dict(color='blue', linestyle='--', linewidth=1.0),
    )
    
    def __init__(self):
        pass
    
    def next(self):
        pass


class HELIXStrategy(bt.Strategy):
    """
    HELIX Strategy implementation.
    
    Based on SEDNA with:
    - Spectral Entropy (SE) instead of Efficiency Ratio (ER)
    - SE LOW = structured (inverted from ER HIGH = trending)
    """
    
    params = dict(
        # KAMA settings (same as SEDNA)
        kama_period=10,
        kama_fast=2,
        kama_slow=30,
        
        # HL2 EMA for KAMA comparison (period=1 means raw HL2)
        hl2_ema_period=1,
        
        # CCI settings (optional momentum filter)
        use_cci_filter=False,
        cci_period=20,
        cci_threshold=100,
        cci_max_threshold=999,
        
        # ATR for SL/TP
        atr_length=14,
        atr_sl_multiplier=3.0,
        atr_tp_multiplier=8.0,
        
        # Breakout Window
        use_breakout_window=True,
        breakout_window_candles=5,
        breakout_level_offset_pips=1.0,
        
        # === FILTERS ===
        
        # Time Filter
        use_time_filter=False,
        allowed_hours=[],
        
        # Day Filter (0=Monday, 6=Sunday)
        use_day_filter=False,
        allowed_days=[0, 1, 2, 3, 4],
        
        # SL Pips Filter
        use_sl_pips_filter=False,
        sl_pips_min=5.0,
        sl_pips_max=50.0,
        
        # ATR Filter (uses average ATR)
        use_atr_filter=False,
        atr_min=0.0,
        atr_max=1.0,
        atr_avg_period=20,
        
        # === HTF FILTER (Spectral Entropy - KEY DIFFERENCE FROM SEDNA) ===
        # STABILITY filter: SE with low variance = consistent market regime
        # High SE variance = market changing regime = avoid
        use_htf_filter=True,
        htf_timeframe_minutes=60,  # 60m for smoother SE
        htf_se_period=20,  # SE period on HTF equivalent
        
        # SE Stability filter (NEW - replaces se_min/se_max range)
        use_se_stability=True,  # Use StdDev(SE) instead of SE range
        se_stability_period=5,  # Lookback for StdDev calculation
        se_stability_min=0.005,  # Min StdDev (too stable = dead market)
        se_stability_max=0.03,  # Max StdDev allowed (too volatile = regime change)
        
        # SE Range filter (DEPRECATED - use se_stability instead)
        htf_se_min=0.0,  # Min SE (0 = disabled)
        htf_se_max=1.0,  # Max SE (1 = disabled)
        
        # === PULLBACK DETECTION ===
        use_pullback_filter=True,
        pullback_min_bars=1,
        pullback_max_bars=4,
        
        # === EXIT CONDITIONS ===
        use_kama_exit=False,
        
        # === ASSET CONFIG ===
        pip_value=0.0001,  # Default for EUR pairs
        is_jpy_pair=False,
        jpy_rate=150.0,
        lot_size=100000,
        is_etf=False,
        margin_pct=3.33,
        
        # Risk
        risk_percent=0.01,
        
        # Debug & Reporting
        print_signals=False,
        export_reports=True,
        
        # Plot options
        plot_entry_exit_lines=True,
    )

    def __init__(self):
        d = self.data
        
        # HL2 = (High + Low) / 2
        self.hl2 = (d.high + d.low) / 2.0
        
        # KAMA on HL2
        self.kama = KAMA(
            self.hl2,
            period=self.p.kama_period,
            fast=self.p.kama_fast,
            slow=self.p.kama_slow
        )
        
        # EMA on HL2 for KAMA comparison
        self.hl2_ema = bt.ind.EMA(self.hl2, period=self.p.hl2_ema_period)
        self.hl2_ema.plotinfo.subplot = False
        self.hl2_ema.plotinfo.plotname = 'HL2 EMA'
        
        # CCI on HL2 (only show if filter is active)
        self.cci_sma = bt.ind.SMA(self.hl2, period=self.p.cci_period)
        self.cci_sma.plotinfo.plot = False
        self.cci = bt.ind.CCI(d, period=self.p.cci_period)
        if not self.p.use_cci_filter:
            self.cci.plotinfo.plot = False  # Hide if not used
        
        # ATR
        self.atr = bt.ind.ATR(d, period=self.p.atr_length)
        
        # HTF Spectral Entropy (KEY DIFFERENCE: SE instead of ER)
        # Uses internal aggregation for TRUE HTF calculation
        self.htf_se = None
        self.se_stddev_indicator = None
        if self.p.use_htf_filter:
            # Calculate HTF multiplier (30m from 5m = 6, 60m from 5m = 12)
            base_tf_minutes = 5  # Base timeframe
            htf_mult = self.p.htf_timeframe_minutes // base_tf_minutes
            
            if htf_mult > 1:
                # Use internal HTF aggregation (TRUE HTF calculation)
                self.htf_se = SpectralEntropy(
                    d, 
                    period=self.p.htf_se_period,
                    htf_mult=htf_mult
                )
                self.htf_se.plotinfo.plotname = f'SE({self.p.htf_timeframe_minutes}m) ({self.p.htf_se_period}, {htf_mult})'
                self.htf_se.plotinfo.subplot = True
                print(f'[HELIX] Using internal HTF aggregation: {base_tf_minutes}m x {htf_mult} = {self.p.htf_timeframe_minutes}m')
            else:
                # Same timeframe
                self.htf_se = SpectralEntropy(d.close, period=self.p.htf_se_period)
                self.htf_se.plotinfo.plotname = f'SE({base_tf_minutes}m)'
            
            # SE StdDev indicator (visual)
            if self.p.use_se_stability:
                self.se_stddev_indicator = SEStdDev(
                    self.htf_se.lines.se, 
                    period=self.p.se_stability_period
                )
                self.se_stddev_indicator.plotinfo.plotname = f'SE StdDev({self.p.se_stability_period})'
        
        # Entry/Exit plot lines
        if self.p.plot_entry_exit_lines:
            self.entry_exit_lines = EntryExitLines(d)
        else:
            self.entry_exit_lines = None
        
        # Orders
        self.order = None
        self.stop_order = None
        self.limit_order = None
        
        # Levels
        self.stop_level = None
        self.take_level = None
        self.last_entry_price = None
        self.last_entry_bar = None
        self.last_exit_reason = None
        
        # Breakout state machine
        self.state = "SCANNING"
        self.pattern_detected_bar = None
        self.breakout_level = None
        self.pattern_atr = None
        self.pattern_cci = None
        
        # ATR history for averaging
        self.atr_history = []
        
        # SE history for stability calculation
        self.se_history = []
        self.last_se_stddev = 0.0  # Cache for logging
        
        # Price history for pullback detection
        self.price_history = {
            'highs': [],
            'lows': [],
            'closes': [],
            'kama': []
        }
        self.pullback_data = None
        
        # Stats
        self.trades = 0
        self.wins = 0
        self.losses = 0
        self.gross_profit = 0.0
        self.gross_loss = 0.0
        self._portfolio_values = []
        self._trade_pnls = []
        self._starting_cash = self.broker.get_cash()
        
        # Trade reporting
        self.trade_reports = []
        self.trade_report_file = None
        self._init_trade_reporting()

    # =========================================================================
    # CCI ON HL2 CALCULATION
    # =========================================================================
    
    def _calculate_cci_hl2(self) -> float:
        """Calculate CCI using HL2 instead of typical price (HLC3)."""
        try:
            hl2_values = []
            for i in range(self.p.cci_period):
                h = float(self.data.high[-i])
                l = float(self.data.low[-i])
                hl2_values.append((h + l) / 2.0)
            
            current_hl2 = (float(self.data.high[0]) + float(self.data.low[0])) / 2.0
            sma_hl2 = sum(hl2_values) / len(hl2_values)
            mean_dev = sum(abs(v - sma_hl2) for v in hl2_values) / len(hl2_values)
            
            if mean_dev == 0:
                return 0.0
            
            cci = (current_hl2 - sma_hl2) / (0.015 * mean_dev)
            return cci
        except:
            return 0.0
    
    def _get_average_atr(self) -> float:
        """Get average ATR over the specified period."""
        if len(self.atr_history) < self.p.atr_avg_period:
            return float(self.atr[0]) if not math.isnan(float(self.atr[0])) else 0
        
        recent_atr = self.atr_history[-self.p.atr_avg_period:]
        return sum(recent_atr) / len(recent_atr)

    # =========================================================================
    # TRADE REPORTING
    # =========================================================================
    
    def _init_trade_reporting(self):
        """Initialize trade report file."""
        if not self.p.export_reports:
            return
        try:
            report_dir = Path("logs")
            report_dir.mkdir(exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            report_path = report_dir / f"HELIX_trades_{timestamp}.txt"
            self.trade_report_file = open(report_path, 'w', encoding='utf-8')
            self.trade_report_file.write("=== HELIX STRATEGY TRADE REPORT ===\n")
            self.trade_report_file.write(f"Generated: {datetime.now()}\n")
            self.trade_report_file.write(f"KAMA: period={self.p.kama_period}, fast={self.p.kama_fast}, slow={self.p.kama_slow}\n")
            if self.p.use_cci_filter:
                self.trade_report_file.write(f"CCI (HL2): {self.p.cci_period}/{self.p.cci_threshold}\n")
            else:
                self.trade_report_file.write("CCI: DISABLED\n")
            self.trade_report_file.write(f"Breakout: {self.p.breakout_level_offset_pips}pips, {self.p.breakout_window_candles}bars\n")
            self.trade_report_file.write(f"SL: {self.p.atr_sl_multiplier}x ATR | TP: {self.p.atr_tp_multiplier}x ATR\n")
            if self.p.use_sl_pips_filter:
                self.trade_report_file.write(f"SL Filter: {self.p.sl_pips_min}-{self.p.sl_pips_max} pips\n")
            if self.p.use_atr_filter:
                self.trade_report_file.write(f"ATR Filter: {self.p.atr_min}-{self.p.atr_max} (avg {self.p.atr_avg_period})\n")
            if self.p.use_time_filter:
                self.trade_report_file.write(f"Time Filter: {list(self.p.allowed_hours)}\n")
            if self.p.use_htf_filter:
                self.trade_report_file.write(f"HTF Filter: SE(period={self.p.htf_se_period}, TF={self.p.htf_timeframe_minutes}m) in [{self.p.htf_se_min}, {self.p.htf_se_max}]\n")
            self.trade_report_file.write("\n")
            print(f"Trade report: {report_path}")
        except Exception as e:
            print(f"Trade reporting init failed: {e}")

    def _record_trade_entry(self, dt, entry_price, size, atr, cci, sl_pips, se_value, se_stddev=0.0):
        """Record entry to trade report file."""
        if not self.trade_report_file:
            return
        try:
            entry = {
                'entry_time': dt,
                'entry_price': entry_price,
                'size': size,
                'atr': atr,
                'cci': cci,
                'se': se_value,
                'se_stddev': se_stddev,
                'sl_pips': sl_pips,
                'stop_level': self.stop_level,
                'take_level': self.take_level,
            }
            self.trade_reports.append(entry)
            self.trade_report_file.write(f"ENTRY #{len(self.trade_reports)}\n")
            self.trade_report_file.write(f"Time: {dt.strftime('%Y-%m-%d %H:%M:%S')}\n")
            self.trade_report_file.write(f"Entry Price: {entry_price:.5f}\n")
            self.trade_report_file.write(f"Stop Loss: {self.stop_level:.5f}\n")
            self.trade_report_file.write(f"Take Profit: {self.take_level:.5f}\n")
            self.trade_report_file.write(f"SL Pips: {sl_pips:.1f}\n")
            self.trade_report_file.write(f"ATR (avg): {atr:.6f}\n")
            self.trade_report_file.write(f"SE: {se_value:.3f}\n")
            self.trade_report_file.write(f"SE StdDev: {se_stddev:.4f}\n")
            if self.p.use_cci_filter:
                self.trade_report_file.write(f"CCI (HL2): {cci:.2f}\n")
            self.trade_report_file.write("-" * 50 + "\n\n")
            self.trade_report_file.flush()
        except Exception as e:
            pass

    def _record_trade_exit(self, dt, pnl, reason):
        """Record exit to trade report file."""
        if not self.trade_report_file or not self.trade_reports:
            return
        try:
            self.trade_reports[-1]['pnl'] = pnl
            self.trade_reports[-1]['exit_reason'] = reason
            self.trade_reports[-1]['exit_time'] = dt
            self.trade_report_file.write(f"EXIT #{len(self.trade_reports)}\n")
            self.trade_report_file.write(f"Time: {dt.strftime('%Y-%m-%d %H:%M:%S')}\n")
            self.trade_report_file.write(f"Exit Reason: {reason}\n")
            self.trade_report_file.write(f"P&L: ${pnl:.2f}\n")
            self.trade_report_file.write("=" * 80 + "\n\n")
            self.trade_report_file.flush()
        except:
            pass

    # =========================================================================
    # PLOT LINES UPDATE
    # =========================================================================
    
    def _update_plot_lines(self, entry_price=None, stop_level=None, take_level=None):
        """Update entry/exit plot lines on chart."""
        if not self.entry_exit_lines:
            return
        
        nan = float('nan')
        self.entry_exit_lines.lines.entry[0] = entry_price if entry_price else nan
        self.entry_exit_lines.lines.stop_loss[0] = stop_level if stop_level else nan
        self.entry_exit_lines.lines.take_profit[0] = take_level if take_level else nan

    # =========================================================================
    # DATETIME HELPER
    # =========================================================================
    
    def _get_datetime(self, offset=0) -> datetime:
        """Get correct datetime combining date and time."""
        try:
            dt_date = self.data.datetime.date(offset)
            dt_time = self.data.datetime.time(offset)
            return datetime.combine(dt_date, dt_time)
        except Exception:
            return self.data.datetime.datetime(offset)

    # =========================================================================
    # CONDITION CHECKS
    # =========================================================================
    
    def _check_kama_condition(self) -> bool:
        """Check if EMA(HL2) is above KAMA."""
        try:
            hl2_ema_value = float(self.hl2_ema[0])
            kama_value = float(self.kama[0])
            return hl2_ema_value > kama_value
        except:
            return False

    def _check_kama_exit_condition(self) -> bool:
        """Check if KAMA > EMA (trend reversal = exit signal)."""
        try:
            hl2_ema_value = float(self.hl2_ema[0])
            kama_value = float(self.kama[0])
            return kama_value > hl2_ema_value
        except:
            return False

    def _check_cci_condition(self) -> bool:
        """Check if CCI(HL2) > threshold and < max_threshold."""
        if not self.p.use_cci_filter:
            return True
        
        try:
            cci_val = self._calculate_cci_hl2()
            if cci_val <= self.p.cci_threshold:
                return False
            if cci_val >= self.p.cci_max_threshold:
                return False
            return True
        except:
            return False

    def _check_htf_filter(self) -> tuple:
        """
        Check Higher Timeframe structure filter (MAIN TRIGGER).
        
        Two conditions required:
        1. SE STABILITY: StdDev(SE) < threshold (consistent market regime)
           OR SE in range [se_min, se_max] (legacy mode)
        2. Close > KAMA (bullish direction)
        
        NEW INSIGHT (2026-02-05):
        - What matters is NOT the SE value, but its STABILITY
        - Stable SE (any level) = market in consistent regime = predictable
        - Volatile SE (spikes) = market changing regime = avoid
        
        Returns: (passed: bool, se_value: float, se_stddev: float)
        """
        if not self.p.use_htf_filter:
            return True, 1.0, 0.0
        
        try:
            se_value = 1.0
            se_stddev = 0.0
            
            if self.htf_se is not None:
                se_value = float(self.htf_se[0])
                
                # Update SE history
                self.se_history.append(se_value)
                max_history = self.p.se_stability_period + 5
                if len(self.se_history) > max_history:
                    self.se_history = self.se_history[-max_history:]
                
                # Condition 1A: SE Stability filter (NEW - preferred)
                # Insight: ni muy estable (mercado muerto) ni muy volátil (régimen cambiando)
                if self.p.use_se_stability:
                    if len(self.se_history) >= self.p.se_stability_period:
                        import numpy as np
                        recent_se = self.se_history[-self.p.se_stability_period:]
                        se_stddev = float(np.std(recent_se))
                        self.last_se_stddev = se_stddev  # Cache for logging
                        
                        # Too volatile = regime changing = avoid
                        if se_stddev > self.p.se_stability_max:
                            return False, se_value, se_stddev
                        # Too stable = dead market = avoid (optional)
                        if self.p.se_stability_min > 0 and se_stddev < self.p.se_stability_min:
                            return False, se_value, se_stddev
                
                # Condition 1B: SE Range filter (legacy - optional)
                if self.p.htf_se_min > 0.0 or self.p.htf_se_max < 1.0:
                    if not check_spectral_entropy_filter(
                        se_value=se_value,
                        se_min=self.p.htf_se_min,
                        se_max=self.p.htf_se_max,
                        enabled=True
                    ):
                        return False, se_value, se_stddev
            
            # Cache stddev for logging
            self.last_se_stddev = se_stddev
            
            # Condition 2: Close > KAMA (bullish direction)
            close_price = float(self.data.close[0])
            kama_value = float(self.kama[0])
            if close_price <= kama_value:
                return False, se_value, se_stddev
            
            return True, se_value, se_stddev
        except:
            return True, 1.0, 0.0

    def _check_pullback_condition(self) -> bool:
        """Check pullback condition using standard reusable filter."""
        if not self.p.use_pullback_filter:
            return True
        
        required_len = self.p.pullback_max_bars + 2
        if len(self.price_history['highs']) < required_len:
            return False
        
        result = detect_pullback(
            highs=self.price_history['highs'],
            lows=self.price_history['lows'],
            closes=self.price_history['closes'],
            kama_values=self.price_history['kama'],
            min_bars=self.p.pullback_min_bars,
            max_bars=self.p.pullback_max_bars,
            enabled=True
        )
        
        if result['valid']:
            self.pullback_data = result
            return True
        
        return False

    def _check_entry_conditions(self, dt: datetime) -> tuple:
        """
        Check all entry conditions (3-phase system).
        
        Returns: (passed: bool, se_value: float)
        """
        # Time filter
        if self.p.use_time_filter:
            if not check_time_filter(dt, self.p.allowed_hours, True):
                return False, 1.0
        
        # Day filter
        if self.p.use_day_filter:
            if not check_day_filter(dt, self.p.allowed_days, True):
                return False, 1.0
        
        # Phase 1: HTF Filter (SE stability AND Close > KAMA)
        htf_passed, se_value, se_stddev = self._check_htf_filter()
        if not htf_passed:
            return False, se_value
        
        # Phase 2: KAMA condition (HL2_EMA > KAMA)
        if not self._check_kama_condition():
            return False, se_value
        
        # Phase 3: Pullback detection
        if not self._check_pullback_condition():
            return False, se_value
        
        return True, se_value

    # =========================================================================
    # ENTRY SETUP
    # =========================================================================
    
    def _setup_entry(self, dt: datetime, avg_atr: float, se_value: float):
        """Setup entry levels after conditions are met."""
        
        current_high = float(self.data.high[0])
        
        # Determine breakout level
        if self.p.use_pullback_filter and self.pullback_data:
            breakout_level = self.pullback_data['breakout_level']
        else:
            breakout_level = current_high
        
        # Add offset
        self.breakout_level = breakout_level + (self.p.breakout_level_offset_pips * self.p.pip_value)
        
        # Store pattern info
        self.pattern_detected_bar = len(self.data)
        self.pattern_atr = avg_atr
        self.pattern_cci = self._calculate_cci_hl2() if self.p.use_cci_filter else 0
        
        if self.p.use_breakout_window:
            # Wait for breakout confirmation
            self.state = "WAITING_BREAKOUT"
            if self.p.print_signals:
                print(f"[HELIX] {dt} WAITING_BREAKOUT | Level: {self.breakout_level:.5f} | SE: {se_value:.3f}")
        else:
            # Immediate entry
            self._execute_entry(dt, se_value)

    def _execute_entry(self, dt: datetime, se_value: float):
        """Execute market entry."""
        
        entry_price = self.breakout_level
        avg_atr = self.pattern_atr if self.pattern_atr else self._get_average_atr()
        
        # ATR Filter
        if self.p.use_atr_filter:
            if not check_atr_filter(avg_atr, self.p.atr_min, self.p.atr_max, True):
                self.state = "SCANNING"
                return
        
        # Calculate SL/TP
        self.stop_level = entry_price - (avg_atr * self.p.atr_sl_multiplier)
        self.take_level = entry_price + (avg_atr * self.p.atr_tp_multiplier)
        
        # SL Pips Filter
        sl_pips = abs(entry_price - self.stop_level) / self.p.pip_value
        if self.p.use_sl_pips_filter:
            if not check_sl_pips_filter(sl_pips, self.p.sl_pips_min, self.p.sl_pips_max, True):
                self.state = "SCANNING"
                return
        
        # Position sizing (same as SEDNA)
        if self.p.is_etf:
            pair_type = 'ETF'
        elif self.p.is_jpy_pair:
            pair_type = 'JPY'
        else:
            pair_type = 'STANDARD'
        
        bt_size = calculate_position_size(
            entry_price=entry_price,
            stop_loss=self.stop_level,
            equity=self.broker.get_value(),
            risk_percent=self.p.risk_percent,
            pair_type=pair_type,
            lot_size=self.p.lot_size,
            jpy_rate=self.p.jpy_rate,
            pip_value=self.p.pip_value,
            margin_pct=self.p.margin_pct,
        )
        
        if bt_size <= 0:
            self.state = "SCANNING"
            return
        
        # Execute order
        self.order = self.buy(size=bt_size, exectype=bt.Order.Market)
        self.last_entry_price = entry_price
        self.last_entry_bar = len(self.data)
        
        # Record entry
        cci_val = self._calculate_cci_hl2() if self.p.use_cci_filter else 0
        self._record_trade_entry(dt, entry_price, bt_size, avg_atr, cci_val, sl_pips, se_value, self.last_se_stddev)
        
        if self.p.print_signals:
            print(f"[HELIX] {dt} ENTRY | Price: {entry_price:.5f} | SL: {self.stop_level:.5f} | TP: {self.take_level:.5f} | SE: {se_value:.3f} | StdDev: {self.last_se_stddev:.4f}")
        
        self.state = "SCANNING"

    # =========================================================================
    # MAIN NEXT
    # =========================================================================
    
    def next(self):
        dt = self._get_datetime()
        
        # Update price history
        try:
            self.price_history['highs'].append(float(self.data.high[0]))
            self.price_history['lows'].append(float(self.data.low[0]))
            self.price_history['closes'].append(float(self.data.close[0]))
            self.price_history['kama'].append(float(self.kama[0]))
            
            # Keep last 50 bars
            max_history = 50
            for key in self.price_history:
                if len(self.price_history[key]) > max_history:
                    self.price_history[key] = self.price_history[key][-max_history:]
        except:
            pass
        
        # Update ATR history
        try:
            atr_val = float(self.atr[0])
            if not math.isnan(atr_val):
                self.atr_history.append(atr_val)
                if len(self.atr_history) > self.p.atr_avg_period * 2:
                    self.atr_history = self.atr_history[-self.p.atr_avg_period * 2:]
        except:
            pass
        
        # Record portfolio value
        self._portfolio_values.append(self.broker.getvalue())
        
        # Update plot lines if in position
        if self.position:
            self._update_plot_lines(self.last_entry_price, self.stop_level, self.take_level)
        else:
            self._update_plot_lines(None, None, None)
        
        # Skip if pending orders
        if self.order:
            return
        
        # =====================================================================
        # POSITION MANAGEMENT
        # =====================================================================
        
        if self.position:
            current_high = float(self.data.high[0])
            current_low = float(self.data.low[0])
            
            # Check stop loss
            if current_low <= self.stop_level:
                self.order = self.close()
                self.last_exit_reason = "SL"
                return
            
            # Check take profit
            if current_high >= self.take_level:
                self.order = self.close()
                self.last_exit_reason = "TP"
                return
            
            # KAMA exit (optional)
            if self.p.use_kama_exit and self._check_kama_exit_condition():
                self.order = self.close()
                self.last_exit_reason = "KAMA_EXIT"
                return
            
            return
        
        # =====================================================================
        # STATE MACHINE (ENTRY LOGIC)
        # =====================================================================
        
        if self.state == "SCANNING":
            # Check all entry conditions
            conditions_met, se_value = self._check_entry_conditions(dt)
            
            if conditions_met:
                avg_atr = self._get_average_atr()
                self._setup_entry(dt, avg_atr, se_value)
        
        elif self.state == "WAITING_BREAKOUT":
            # Check timeout
            bars_since = len(self.data) - self.pattern_detected_bar
            
            if bars_since > self.p.breakout_window_candles:
                self.state = "SCANNING"
                if self.p.print_signals:
                    print(f"[HELIX] {dt} TIMEOUT | Bars waited: {bars_since}")
                return
            
            # Check breakout
            current_high = float(self.data.high[0])
            if check_pullback_breakout(current_high, self.breakout_level, buffer_pips=0, pip_value=self.p.pip_value):
                se_value = float(self.htf_se[0]) if self.htf_se else 1.0
                self._execute_entry(dt, se_value)

    # =========================================================================
    # TRADE NOTIFICATIONS
    # =========================================================================
    
    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            return
        
        if order.status == order.Completed:
            if order.isbuy():
                pass
            elif order.issell():
                pass
        
        self.order = None

    def notify_trade(self, trade):
        if not trade.isclosed:
            return
        
        dt = self._get_datetime()
        pnl = trade.pnl
        
        self.trades += 1
        self._trade_pnls.append(pnl)
        
        if pnl > 0:
            self.wins += 1
            self.gross_profit += pnl
        else:
            self.losses += 1
            self.gross_loss += abs(pnl)
        
        reason = self.last_exit_reason or "UNKNOWN"
        self._record_trade_exit(dt, pnl, reason)
        
        if self.p.print_signals:
            print(f"[HELIX] {dt} EXIT ({reason}) | P&L: ${pnl:.2f}")
        
        self.last_exit_reason = None

    # =========================================================================
    # STOP - COMPLETE METRICS REPORT
    # =========================================================================
    
    def stop(self):
        """Strategy end - print comprehensive summary with advanced metrics."""
        import numpy as np
        from collections import defaultdict
        
        # Calculate basic metrics
        total_trades = self.wins + self.losses
        win_rate = (self.wins / total_trades * 100) if total_trades > 0 else 0
        profit_factor = (self.gross_profit / self.gross_loss) if self.gross_loss > 0 else float('inf')
        
        final_value = self.broker.get_value()
        initial_cash = self._starting_cash if self._starting_cash else 100000.0
        total_pnl = final_value - initial_cash
        
        # =================================================================
        # ADVANCED METRICS: Drawdown, Sharpe Ratio
        # =================================================================
        max_drawdown_pct = 0.0
        sharpe_ratio = 0.0
        
        if len(self._portfolio_values) > 1:
            peak = self._portfolio_values[0]
            for value in self._portfolio_values:
                if value > peak:
                    peak = value
                drawdown = (peak - value) / peak * 100.0
                if drawdown > max_drawdown_pct:
                    max_drawdown_pct = drawdown
        
        if len(self._portfolio_values) > 10:
            returns = []
            for i in range(1, len(self._portfolio_values)):
                ret = (self._portfolio_values[i] - self._portfolio_values[i-1]) / self._portfolio_values[i-1]
                returns.append(ret)
            
            if len(returns) > 0:
                returns_array = np.array(returns)
                mean_return = np.mean(returns_array)
                std_return = np.std(returns_array)
                periods_per_year = 252 * 24 * 12  # 5-minute periods per year
                if std_return > 0:
                    sharpe_ratio = (mean_return * periods_per_year) / (std_return * np.sqrt(periods_per_year))
        
        # =================================================================
        # ADVANCED METRICS: CAGR, Sortino, Calmar, Monte Carlo
        # =================================================================
        cagr = 0.0
        sortino_ratio = 0.0
        calmar_ratio = 0.0
        monte_carlo_dd_95 = 0.0
        monte_carlo_dd_99 = 0.0
        
        # Calculate CAGR
        if len(self._portfolio_values) > 1 and initial_cash > 0:
            total_return = final_value / initial_cash
            # Estimate years from data length
            years = len(self._portfolio_values) / (252 * 24 * 12)
            years = max(years, 0.1)
            
            if total_return > 0:
                cagr = (pow(total_return, 1.0 / years) - 1.0) * 100.0
        
        # Calculate Sortino Ratio
        if len(self._portfolio_values) > 10:
            returns = []
            for i in range(1, len(self._portfolio_values)):
                ret = (self._portfolio_values[i] - self._portfolio_values[i-1]) / self._portfolio_values[i-1]
                returns.append(ret)
            
            if len(returns) > 0:
                returns_array = np.array(returns)
                mean_return = np.mean(returns_array)
                negative_returns = returns_array[returns_array < 0]
                if len(negative_returns) > 0:
                    downside_dev = np.std(negative_returns)
                    periods_per_year = 252 * 24 * 12
                    if downside_dev > 0:
                        sortino_ratio = (mean_return * periods_per_year) / (downside_dev * np.sqrt(periods_per_year))
        
        # Calculate Calmar Ratio
        if max_drawdown_pct > 0:
            calmar_ratio = cagr / max_drawdown_pct
        
        # Monte Carlo Simulation
        if len(self._trade_pnls) >= 20:
            n_simulations = 10000
            pnl_list = self._trade_pnls.copy()
            mc_max_drawdowns = []
            
            for _ in range(n_simulations):
                shuffled_pnl = np.random.permutation(pnl_list)
                equity = initial_cash
                peak = equity
                max_dd = 0.0
                
                for pnl in shuffled_pnl:
                    equity += pnl
                    if equity > peak:
                        peak = equity
                    dd = (peak - equity) / peak * 100.0 if peak > 0 else 0.0
                    if dd > max_dd:
                        max_dd = dd
                
                mc_max_drawdowns.append(max_dd)
            
            mc_max_drawdowns = np.array(mc_max_drawdowns)
            monte_carlo_dd_95 = np.percentile(mc_max_drawdowns, 95)
            monte_carlo_dd_99 = np.percentile(mc_max_drawdowns, 99)
        
        # =================================================================
        # YEARLY STATISTICS
        # =================================================================
        yearly_stats = defaultdict(lambda: {
            'trades': 0, 'wins': 0, 'losses': 0, 'pnl': 0.0,
            'gross_profit': 0.0, 'gross_loss': 0.0, 'pnls': []
        })
        
        # Build yearly stats from trade reports
        for report in self.trade_reports:
            if 'entry_time' in report and 'pnl' in report:
                dt = report['entry_time']
                year = dt.year if hasattr(dt, 'year') else 2024
                pnl = report.get('pnl', 0.0)
                
                yearly_stats[year]['trades'] += 1
                yearly_stats[year]['pnl'] += pnl
                yearly_stats[year]['pnls'].append(pnl)
                
                if pnl > 0:
                    yearly_stats[year]['wins'] += 1
                    yearly_stats[year]['gross_profit'] += pnl
                else:
                    yearly_stats[year]['losses'] += 1
                    yearly_stats[year]['gross_loss'] += abs(pnl)
        
        # Calculate yearly Sharpe and Sortino
        for year in yearly_stats:
            pnls = yearly_stats[year]['pnls']
            if len(pnls) > 1:
                pnl_array = np.array(pnls)
                mean_pnl = np.mean(pnl_array)
                std_pnl = np.std(pnl_array)
                
                if std_pnl > 0:
                    yearly_stats[year]['sharpe'] = (mean_pnl / std_pnl) * np.sqrt(len(pnls))
                else:
                    yearly_stats[year]['sharpe'] = 0.0
                
                neg_pnls = pnl_array[pnl_array < 0]
                if len(neg_pnls) > 0:
                    downside_std = np.std(neg_pnls)
                    if downside_std > 0:
                        yearly_stats[year]['sortino'] = (mean_pnl / downside_std) * np.sqrt(len(pnls))
                    else:
                        yearly_stats[year]['sortino'] = 0.0
                else:
                    yearly_stats[year]['sortino'] = float('inf') if mean_pnl > 0 else 0.0
            else:
                yearly_stats[year]['sharpe'] = 0.0
                yearly_stats[year]['sortino'] = 0.0
        
        # =================================================================
        # PRINT SUMMARY
        # =================================================================
        print('\n' + '=' * 70)
        print('=== HELIX STRATEGY SUMMARY ===')
        print('=' * 70)
        
        print(f'Total Trades: {total_trades}')
        print(f'Wins: {self.wins} | Losses: {self.losses}')
        print(f'Win Rate: {win_rate:.1f}%')
        print(f'Profit Factor: {profit_factor:.2f}')
        print(f'Gross Profit: ${self.gross_profit:,.2f}')
        print(f'Gross Loss: ${self.gross_loss:,.2f}')
        print(f'Net P&L: ${total_pnl:,.2f}')
        print(f'Final Value: ${final_value:,.2f}')
        
        # Advanced Metrics with quality indicators
        print(f"\n{'='*70}")
        print('ADVANCED RISK METRICS')
        print(f"{'='*70}")
        
        sharpe_status = "Poor" if sharpe_ratio < 0.5 else "Marginal" if sharpe_ratio < 1.0 else "Good" if sharpe_ratio < 2.0 else "Excellent"
        print(f'Sharpe Ratio:    {sharpe_ratio:>8.2f}  [{sharpe_status}]')
        
        sortino_status = "Poor" if sortino_ratio < 0.5 else "Marginal" if sortino_ratio < 1.0 else "Good" if sortino_ratio < 2.0 else "Excellent"
        print(f'Sortino Ratio:   {sortino_ratio:>8.2f}  [{sortino_status}]')
        
        cagr_status = "Below Market" if cagr < 8 else "Market-level" if cagr < 12 else "Good" if cagr < 20 else "Exceptional"
        print(f'CAGR:            {cagr:>7.2f}%  [{cagr_status}]')
        
        dd_status = "Excellent" if max_drawdown_pct < 10 else "Acceptable" if max_drawdown_pct < 20 else "High" if max_drawdown_pct < 30 else "Dangerous"
        print(f'Max Drawdown:    {max_drawdown_pct:>7.2f}%  [{dd_status}]')
        
        calmar_status = "Poor" if calmar_ratio < 0.5 else "Acceptable" if calmar_ratio < 1.0 else "Good" if calmar_ratio < 2.0 else "Excellent"
        print(f'Calmar Ratio:    {calmar_ratio:>8.2f}  [{calmar_status}]')
        
        if monte_carlo_dd_95 > 0:
            mc_ratio = monte_carlo_dd_95 / max_drawdown_pct if max_drawdown_pct > 0 else 0
            mc_status = "Good" if mc_ratio < 1.5 else "Caution" if mc_ratio < 2.0 else "Warning"
            print(f'\nMonte Carlo Analysis (10,000 simulations):')
            print(f'  95th Percentile DD: {monte_carlo_dd_95:>6.2f}%  [{mc_status}]')
            print(f'  99th Percentile DD: {monte_carlo_dd_99:>6.2f}%')
            print(f'  Historical vs MC95: {mc_ratio:.2f}x')
        
        print(f"{'='*70}")
        
        # Yearly Statistics
        if yearly_stats:
            print(f"\n{'='*70}")
            print('YEARLY STATISTICS')
            print(f"{'='*70}")
            print(f"{'Year':<6} {'Trades':>7} {'WR%':>7} {'PF':>7} {'PnL':>12} {'Sharpe':>8} {'Sortino':>8}")
            print(f"{'-'*70}")
            
            for year in sorted(yearly_stats.keys()):
                stats = yearly_stats[year]
                wr = (stats['wins'] / stats['trades'] * 100) if stats['trades'] > 0 else 0
                year_pf = (stats['gross_profit'] / stats['gross_loss']) if stats['gross_loss'] > 0 else float('inf')
                year_sharpe = stats.get('sharpe', 0.0)
                year_sortino = stats.get('sortino', 0.0)
                
                pf_str = f"{year_pf:>7.2f}" if year_pf != float('inf') else "    inf"
                sortino_str = f"{year_sortino:>7.2f}" if year_sortino != float('inf') else "    inf"
                
                print(f"{year:<6} {stats['trades']:>7} {wr:>6.1f}% {pf_str} ${stats['pnl']:>10,.0f} {year_sharpe:>8.2f} {sortino_str}")
            
            print(f"{'='*70}")
        
        # Close trade report file
        if self.trade_report_file:
            try:
                self.trade_report_file.write("\n=== SUMMARY ===\n")
                self.trade_report_file.write(f"Total Trades: {total_trades}\n")
                self.trade_report_file.write(f"Wins: {self.wins} | Losses: {self.losses}\n")
                self.trade_report_file.write(f"Win Rate: {win_rate:.1f}%\n")
                self.trade_report_file.write(f"Profit Factor: {profit_factor:.2f}\n")
                self.trade_report_file.write(f"Sharpe Ratio: {sharpe_ratio:.2f}\n")
                self.trade_report_file.write(f"Sortino Ratio: {sortino_ratio:.2f}\n")
                self.trade_report_file.write(f"Max Drawdown: {max_drawdown_pct:.2f}%\n")
                self.trade_report_file.write(f"CAGR: {cagr:.2f}%\n")
                self.trade_report_file.write(f"Net P&L: ${total_pnl:,.2f}\n")
                self.trade_report_file.close()
            except:
                pass
