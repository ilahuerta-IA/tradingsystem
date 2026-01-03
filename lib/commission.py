"""
Commission schemes for different brokers and instrument types.
Supports both JPY and Standard pairs with proper P&L calculation.
"""
import backtrader as bt


class DarwinexZeroCommission(bt.CommInfoBase):
    """
    Commission scheme for Darwinex Zero.
    
    For JPY pairs:
    - Position size is divided by jpy_rate (~150) for margin management
    - P&L must be multiplied back by jpy_rate to compensate
    - This matches the original sunrise_ogle_eurjpy_pro.py implementation
    
    Darwinex Zero specs:
    - Commission: $2.50 per lot per order
    - Spread: Variable per instrument (in price)
    - Margin: 3.33% (30:1 leverage)
    """
    params = (
        ('stocklike', False),
        ('commtype', bt.CommInfoBase.COMM_FIXED),
        ('percabs', True),
        ('leverage', 500.0),
        ('automargin', True),
        ('commission', 2.50),
        ('lot_size', 100000),
        ('is_jpy_pair', False),
        ('jpy_rate', 150.0),
    )
    
    # Debug counters (class-level)
    commission_calls = 0
    total_commission = 0.0
    total_lots = 0.0

    def _getcommission(self, size, price, pseudoexec):
        """
        Return commission based on lot size.
        
        JPY PAIRS: size was divided by jpy_rate (~150) for P&L calculation,
        but commission must be based on ACTUAL lot size, so we restore it.
        """
        # For JPY pairs: restore actual size before calculating lots
        actual_size = abs(size)
        if self.p.is_jpy_pair:
            actual_size = actual_size * self.p.jpy_rate  # Restore real size
        
        lots = actual_size / self.p.lot_size
        comm = lots * self.p.commission
        
        if not pseudoexec:
            DarwinexZeroCommission.commission_calls += 1
            DarwinexZeroCommission.total_commission += comm
            DarwinexZeroCommission.total_lots += lots
        
        return comm

    def profitandloss(self, size, price, newprice):
        """
        Calculate P&L in USD from JPY-denominated gains/losses.
        
        CRITICAL: Since bt_size is divided by ~150 for margin management,
        we multiply P&L by 150 to compensate and get correct USD P&L.
        
        This is an EXACT replica of the original ForexCommission class
        from sunrise_ogle_eurjpy_pro.py (lines 235-248).
        """
        if self.p.is_jpy_pair:
            # JPY pairs: compensate for size division
            pnl_jpy = size * self.p.jpy_rate * (newprice - price)
            if newprice > 0:
                pnl_usd = pnl_jpy / newprice
                return pnl_usd
            return pnl_jpy
        else:
            # Standard pairs: direct USD P&L
            return size * (newprice - price)

    def cashadjust(self, size, price, newprice):
        """Adjust cash for non-stocklike instruments (forex)."""
        if not self._stocklike:
            if self.p.is_jpy_pair:
                # Same compensation for cash adjustment
                pnl_jpy = size * self.p.jpy_rate * (newprice - price)
                if newprice > 0:
                    return pnl_jpy / newprice
                return pnl_jpy
            else:
                return size * (newprice - price)
        return 0.0

# Alias for backward compatibility
ForexCommission = DarwinexZeroCommission