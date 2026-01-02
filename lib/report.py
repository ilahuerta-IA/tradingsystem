import backtrader as bt
import numpy as np
import datetime
from collections import defaultdict

def print_trade_analysis(cerebro, results):
    strat = results[0]
    analyzer = strat.analyzers.trades.get_analysis()
    
    # 1. Recuperar lista de trades cerrados para análisis manual (Año por Año)
    # Backtrader guarda los trades en strat._trades[data][0]
    trades_list = []
    if len(strat._trades) > 0:
        # Accedemos al primer dataseed (normalmente el activo principal)
        trades_list = strat._trades[list(strat._trades.keys())[0]][0]

    # Filtrar solo trades cerrados
    closed_trades = [t for t in trades_list if t.status == bt.Trade.Closed]
    total_trades = len(closed_trades)

    if total_trades == 0:
        print("!!! NO TRADES EXECUTED !!!")
        return

    # 2. Cálculos Globales
    won_trades = [t for t in closed_trades if t.pnlcomm > 0]
    lost_trades = [t for t in closed_trades if t.pnlcomm <= 0]
    
    wins = len(won_trades)
    losses = len(lost_trades)
    win_rate = (wins / total_trades) * 100
    
    gross_profit = sum(t.pnlcomm for t in won_trades)
    gross_loss = abs(sum(t.pnlcomm for t in lost_trades))
    net_pnl = gross_profit - gross_loss
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else 0

    # Drawdown & Sharpe (Desde Analyzers)
    dd_analyzer = strat.analyzers.drawdown.get_analysis()
    max_dd = dd_analyzer.get('max', {}).get('drawdown', 0.0)
    
    sharpe_an = strat.analyzers.sharpe.get_analysis()
    sharpe = sharpe_an.get('sharperatio', 0.0)
    if sharpe is None: sharpe = 0.0

    # 3. Desglose Anual (Yearly Breakdown)
    yearly_stats = defaultdict(lambda: {'count': 0, 'won': 0, 'pnl': 0.0})
    
    for t in closed_trades:
        # Usamos la fecha de cierre para atribuir el año
        dt = bt.num2date(t.dtclose)
        year = dt.year
        
        yearly_stats[year]['count'] += 1
        yearly_stats[year]['pnl'] += t.pnlcomm
        if t.pnlcomm > 0:
            yearly_stats[year]['won'] += 1

    # ================= IMPRIMIR REPORTE ESTILO ORIGINAL =================
    print("\n" + "="*70)
    print(f"=== STRATEGY REPORT: {strat.p.asset_name} ===")
    print("="*70)
    
    # Comisión estimada (Darwinex style)
    # Asumiendo size promedio si no podemos acceder exacto, o calculando del trade
    total_comm = sum(t.commission for t in closed_trades)
    
    print(f"Total Trades:      {total_trades}")
    print(f"Wins: {wins} | Losses: {losses}")
    print(f"Win Rate:          {win_rate:.2f}%")
    print(f"Profit Factor:     {profit_factor:.2f}")
    print(f"Gross Profit:      ${gross_profit:,.2f}")
    print(f"Gross Loss:        ${gross_loss:,.2f}")
    print(f"Net P&L:           ${net_pnl:,.2f}")
    print(f"Total Commission:  ${total_comm:,.2f}")
    print(f"Final Value:       ${cerebro.broker.getvalue():,.2f}")
    
    print("\n" + "="*70)
    print("ADVANCED RISK METRICS")
    print("="*70)
    print(f"Sharpe Ratio:      {sharpe:.2f}")
    print(f"Max Drawdown:      {max_dd:.2f}%")
    
    print("\n" + "="*70)
    print("YEARLY STATISTICS")
    print("="*70)
    print(f"{'Year':<6} | {'Trades':<8} | {'WR%':<8} | {'PnL':<12}")
    print("-" * 70)
    
    # Ordenar años
    sorted_years = sorted(yearly_stats.keys())
    for y in sorted_years:
        s = yearly_stats[y]
        wr = (s['won'] / s['count'] * 100) if s['count'] > 0 else 0
        print(f"{y:<6} | {s['count']:<8} | {wr:6.1f}% | ${s['pnl']:,.2f}")
    
    print("="*70 + "\n")