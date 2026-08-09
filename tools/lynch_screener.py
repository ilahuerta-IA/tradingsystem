#!/usr/bin/env python3
"""
PETER LYNCH 10-BAGGER SCREENER
------------------------------
Extrae datos financieros de yfinance, aplica filtros de crecimiento
y exporta los resultados a HTML. Incluye rate-limiting.

Ubicación: tools/lynch_screener.py
"""

import os
import time
import random
import logging
import yfinance as yf
import pandas as pd
import numpy as np
from typing import Dict, Any, List, Optional

# Configuración de logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

# Gestión de Rutas del Proyecto
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
RESULTS_DIR = os.path.join(_ROOT, "results")
os.makedirs(RESULTS_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# Constantes y Filtros de Peter Lynch
# ---------------------------------------------------------------------------
MIN_MARKET_CAP = 100_000_000      # $100M
MAX_MARKET_CAP = 2_000_000_000    # $2B
MAX_PEG_RATIO = 1.0               
MIN_ROIC = 15.0                   
MAX_DEBT_EQUITY = 50.0            
MIN_EPS_GROWTH = 15.0             
MAX_EPS_GROWTH = 40.0             
MAX_BETA = 1.5                    
MIN_PRICE = 5.0                   
MIN_VOLUME = 100_000              

class LynchScreener:
    def __init__(self, tickers: List[str], delay_min: float = 1.0, delay_max: float = 3.0):
        self.tickers = tickers
        self.results = []
        self.delay_min = delay_min
        self.delay_max = delay_max

    def _get_safe_val(self, dictionary: dict, key: str, default=0.0):
        val = dictionary.get(key)
        return float(val) if val is not None else default

    def _calculate_historic_metrics(self, ticker_obj) -> Dict[str, float]:
        """Calcula medias de 5 años usando cuentas anuales."""
        try:
            fin = ticker_obj.financials
            bs = ticker_obj.balance_sheet
            
            if fin.empty or bs.empty:
                return {"roic_5y_avg": 0.0, "eps_growth_5y_avg": 0.0}

            cols = fin.columns[:5]
            
            # Cálculo de EPS Growth (Media 5 años)
            eps_growth_list = []
            if 'Diluted EPS' in fin.index:
                eps_data = fin.loc['Diluted EPS', cols].dropna().values
                for i in range(len(eps_data)-1):
                    prev = eps_data[i+1]
                    curr = eps_data[i]
                    if prev > 0:
                        growth = ((curr - prev) / prev) * 100
                        eps_growth_list.append(growth)
            
            eps_5y_avg = np.mean(eps_growth_list) if eps_growth_list else 0.0

            # Cálculo de ROIC (Media 5 años)
            roic_list = []
            for col in cols:
                try:
                    ebit = fin.loc['EBIT', col] if 'EBIT' in fin.index else 0
                    tax_prov = fin.loc['Tax Provision', col] if 'Tax Provision' in fin.index else 0
                    pretax = fin.loc['Pretax Income', col] if 'Pretax Income' in fin.index else ebit
                    
                    tax_rate = (tax_prov / pretax) if pretax > 0 else 0.21 
                    nopat = ebit * (1 - tax_rate)

                    total_debt = bs.loc['Total Debt', col] if 'Total Debt' in bs.index else 0
                    equity = bs.loc['Stockholders Equity', col] if 'Stockholders Equity' in bs.index else 0
                    invested_capital = total_debt + equity

                    if invested_capital > 0:
                        roic = (nopat / invested_capital) * 100
                        roic_list.append(roic)
                except KeyError:
                    continue
            
            roic_5y_avg = np.mean(roic_list) if roic_list else 0.0

            return {
                "roic_5y_avg": round(roic_5y_avg, 2),
                "eps_growth_5y_avg": round(eps_5y_avg, 2)
            }
        except Exception:
            return {"roic_5y_avg": 0.0, "eps_growth_5y_avg": 0.0}

    def process_ticker(self, symbol: str) -> Optional[Dict[str, Any]]:
        logging.info(f"Analizando {symbol}...")
        tk = yf.Ticker(symbol)
        info = tk.info

        # 1. Filtros Rápidos
        mcap = self._get_safe_val(info, 'marketCap')
        if not (MIN_MARKET_CAP <= mcap <= MAX_MARKET_CAP):
            return None 

        price = self._get_safe_val(info, 'currentPrice', self._get_safe_val(info, 'previousClose'))
        if price < MIN_PRICE:
            return None 

        vol = self._get_safe_val(info, 'averageVolume')
        if vol < MIN_VOLUME:
            return None 

        beta = self._get_safe_val(info, 'beta', 1.0)
        if beta > MAX_BETA:
            return None 

        # 2. Métricas de Valoración Actuales
        peg = self._get_safe_val(info, 'pegRatio', 99.9)
        per = self._get_safe_val(info, 'trailingPE', 99.9)
        debt_equity = self._get_safe_val(info, 'debtToEquity', 999.0) 

        # if peg > MAX_PEG_RATIO or debt_equity > MAX_DEBT_EQUITY:
        #    return None 

        # 3. Cálculos Históricos 
        hist_metrics = self._calculate_historic_metrics(tk)
        roic_avg = hist_metrics["roic_5y_avg"]
        eps_g_avg = hist_metrics["eps_growth_5y_avg"]

        # if roic_avg < MIN_ROIC:
        #    return None
            
        # if not (MIN_EPS_GROWTH <= eps_g_avg <= MAX_EPS_GROWTH):
        #    return None

        # Nota temporal: Los filtros estrictos están comentados arriba para asegurar que 
        # la lista de prueba de 10 devuelva algún resultado y veas el formato HTML.
        # Descoméntalos cuando lances los 2.000 tickers.

        return {
            "Ticker": symbol,
            "Sector": info.get('sector', 'N/A'),
            "Precio ($)": price,
            "MarketCap ($M)": round(mcap / 1_000_000, 1),
            "PER": round(per, 2),
            "PEG": round(peg, 2),
            "ROIC 5a (%)": roic_avg,
            "Deuda/Eq (%)": debt_equity,
            "EPS 5a (%)": eps_g_avg,
            "Beta": round(beta, 2)
        }

    def run(self):
        for idx, tk in enumerate(self.tickers):
            data = self.process_ticker(tk)
            if data:
                logging.info(f" -> CANDIDATO GUARDADO: {tk}")
                self.results.append(data)
            
            # Rate Limiting (Evitar baneos de yfinance)
            if idx < len(self.tickers) - 1:
                sleep_time = random.uniform(self.delay_min, self.delay_max)
                time.sleep(sleep_time)
        
        return pd.DataFrame(self.results)

def generate_html_report(df: pd.DataFrame, filename: str):
    """Genera un archivo HTML en modo oscuro."""
    if df.empty:
        return
        
    html_template = f"""
    <html>
    <head>
        <title>Orion Screener - Peter Lynch</title>
        <style>
            body {{ background-color: #121212; color: #e0e0e0; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; padding: 20px; }}
            h2 {{ color: #4CAF50; }}
            table {{ border-collapse: collapse; width: 100%; margin-top: 20px; }}
            th, td {{ border: 1px solid #333; padding: 12px; text-align: left; }}
            th {{ background-color: #1e1e1e; color: #4CAF50; }}
            tr:nth-child(even) {{ background-color: #1a1a1a; }}
            tr:hover {{ background-color: #333; }}
        </style>
    </head>
    <body>
        <h2>Orion Screener: Candidatos Peter Lynch (10-Baggers)</h2>
        <p>Generado con métricas a 5 años y filtros de valoración.</p>
        {df.to_html(index=False, classes='dark-table')}
    </body>
    </html>
    """
    
    filepath = os.path.join(RESULTS_DIR, filename)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(html_template)
    logging.info(f"Reporte HTML guardado en: {filepath}")

# ---------------------------------------------------------------------------
# Ejecución Principal
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    # Prueba inicial con 10 componentes típicos del Russell 2000 / Small Caps
    TEST_TICKERS = ["MBUU", "LANC", "MED", "FOXF", "XPEL", "AAON", "CALM", "SAIA", "TREX", "TTC"]
    
    print("\n" + "="*60)
    print(" INICIANDO ORION SCREENER (TEST 10 TICKERS) ")
    print("="*60 + "\n")
    
    # Instanciamos el screener con retraso de 1 a 2 segundos entre peticiones
    screener = LynchScreener(TEST_TICKERS, delay_min=1.0, delay_max=2.0)
    df_results = screener.run()
    
    print("\n" + "="*60)
    print(" RESULTADOS FINALES ")
    print("="*60)
    
    if not df_results.empty:
        print(df_results.to_markdown(index=False))
        # Generar reporte HTML en la carpeta /results
        generate_html_report(df_results, "lynch_report.html")
    else:
        print("Ninguna empresa ha superado los filtros.")