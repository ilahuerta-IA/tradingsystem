import pandas as pd
import yfinance as yf
import time
import sys
import io

# Forzar codificacion limpia de la terminal
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# ==============================================================================
# CONFIGURACION DE MERCADO (Cambia el nombre para alternar el indice a descargar)
# ==============================================================================
#INDICE_SELECCIONADO = "CAC_40_Paris"
INDICE_SELECCIONADO = "AEX_Amsterdam"
#INDICE_SELECCIONADO = "BEL_20_Bruselas"
#INDICE_SELECCIONADO = "DAX_40_Franfort"
#INDICE_SELECCIONADO = "IBEX_35_Madrid"
#INDICE_SELECCIONADO = "FTSE_100_Londres"
#INDICE_SELECCIONADO = "FTSE_MIB_Milan"
#INDICE_SELECCIONADO = "EUROPA_MID_SMALL_CAPS"
# ==============================================================================

DICCIONARIO_TICKERS = {
    "EUROPA_MID_SMALL_CAPS": [
        # --- FRANCIA MID & SMALL CAPS (.PA) ---
        "DIM.PA", "AMUN.PA", "SEB.PA", "RUI.PA", "IPS.PA", "NEXI.PA", "BEN.PA", "SK3.PA",
        "ELIOR.PA", "SMCP.PA", "ESI.PA", "ALBIO.PA", "ALGAU.PA", "ALMVD.PA", "KORI.PA", "VIL.PA",
        "FNAC.PA", "DBV.PA", "XIL.PA", "MFG.PA", "NACON.PA", "SOITEC.PA", "POM.PA", "LIN.PA",
        # --- ALEMANIA MID & SMALL CAPS (.DE) ---
        "BOSS.DE", "PUM.DE", "EVK.DE", "FPE.DE", "KGX.DE", "NDX1.DE", "FRA.DE", "HNR1.DE",
        "SDF.DE", "GXI.DE", "WAF.DE", "AIXA.DE", "SMA.DE", "HDD.DE", "JEN.DE", "MOR.DE",
        "HOT.DE", "DUE.DE", "STR.DE", "AFX.DE", "MTE.DE", "BC8.DE", "ENC.DE", "BYW6.DE",
        # --- ESPAÑA MID & SMALL CAPS / CONTINUO (.MC) ---
        "ALM.MC", "IDR.MC", "LOG.MC", "ROVI.MC", "SCYR.MC", "MEL.MC", "FLUID.MC", "GRI.MC",
        "APAM.MC", "BAK.MC", "CAF.MC", "COL.MC", "EAV.MC", "ENC.MC", "FAE.MC", "FCC.MC",
        "GEST.MC", "LRE.MC", "NEO.MC", "ORY.MC", "PHM.MC", "SLR.MC", "TLGO.MC", "TRG.MC",
        # --- PAÍSES BAJOS MID & SMALL CAPS (.AS) ---
        "ASM.AS", "BESI.AS", "IMCD.AS", "RAND.AS", "REN.AS", "JDE.AS", "FLOW.AS", "ALFEN.AS",
        "CORA.AS", "FAST.AS", "FUGR.AS", "POST.AS", "AALB.AS", "BASIC.AS", "CTP.AS", "VPK.AS",
        # --- BÉLGICA MID & SMALL CAPS (.BR) ---
        "EVS.BR", "ACKB.BR", "DIE.BR", "ELI.BR", "GBLB.BR", "SOF.BR", "WDP.BR", "RECT.BR",
        "COFB.BR", "AED.BR", "BEKB.BR", "BEFB.BR", "CPINV.BR", "ECON.BR", "LOTB.BR", "MELE.BR",
        # --- ITALIA MID & SMALL CAPS (.MI) ---
        "AMP.MI", "AZM.MI", "CPR.MI", "DIA.MI", "ERG.MI", "INW.MI", "MONC.MI", "NEXI.MI",
        "PIRC.MI", "PST.MI", "REC.MI", "BFF.MI", "BRE.MI", "DAMI.MI", "FILA.MI", "JUVE.MI"
    ],
    "CAC_40_Paris": [
        "AC.PA", "ACA.PA", "AI.PA", "AIR.PA", "ALO.PA", "MT.PA", "CS.PA", "BNP.PA",
        "EN.PA", "CAP.PA", "CA.PA", "BN.PA", "DSY.PA", "EDEN.PA", "ENGI.PA",
        "EL.PA", "ERF.PA", "RMS.PA", "KER.PA", "LR.PA", "OR.PA", "MC.PA", "ML.PA",
        "ORA.PA", "RI.PA", "PUB.PA", "RNO.PA", "SAF.PA", "SGO.PA", "SAN.PA", "SU.PA",
        "GLE.PA", "STLAP.PA", "TEP.PA", "HO.PA", "TTE.PA", "URW.PA", "VIE.PA", 
        "DG.PA", "VIV.PA"
    ],
    "AEX_Amsterdam": [
        "ADYEN.AS", "AGN.AS", "AKZA.AS", "ASM.AS", "ASML.AS", "BESI.AS", "HEIA.AS",
        "IMCD.AS", "INGA.AS", "KPN.AS", "NN.AS", "PHIA.AS", "PRX.AS", "RAND.AS",
        "REN.AS", "UMG.AS", "UNA.AS", "WKL.AS"
    ],
    "BEL_20_Bruselas": [
        "ABI.BR", "ACKB.BR", "ARGX.BR", "DIE.BR", "ELI.BR", "GBLB.BR", "KBC.BR",
        "SAB.BR", "SOLB.BR", "SOF.BR", "UCB.BR", "UMI.BR", "WDP.BR"
    ],
    "DAX_40_Franfort": [
        "ADS.DE", "ALV.DE", "BAS.DE", "BAYN.DE", "BMW.DE", "CON.DE", "1COV.DE",
        "DTG.DE", "DBK.DE", "DB1.DE", "LHA.DE", "DPW.DE", "DTE.DE", "EOAN.DE",
        "FRE.DE", "FME.DE", "HEI.DE", "HEN3.DE", "HLAG.DE", "IFX.DE", "SDF.DE",
        "MBG.DE", "MRK.DE", "MTX.DE", "MUV2.DE", "PUM.DE", "RWE.DE", "SAP.DE",
        "SIE.DE", "SHL.DE", "SRT3.DE", "SY1.DE", "TKA.DE", "VOW3.DE", "VNA.DE"
    ],
    "IBEX_35_Madrid": [
        "ANA.MC", "AENA.MC", "ACS.MC", "ALM.MC", "AMS.MC", "MTS.MC", "SAB.MC",
        "SAN.MC", "BKT.MC", "BBVA.MC", "CABK.MC", "CLNX.MC", "ENG.MC", "ELE.MC",
        "FER.MC", "FLUID.MC", "GRI.MC", "IAG.MC", "IBE.MC", "ITX.MC", "IDR.MC",
        "COL.MC", "LOG.MC", "MAP.MC", "MEL.MC", "MRL.MC", "NTGY.MC", "REE.MC",
        "REP.MC", "ROVI.MC", "SCYR.MC", "TEF.MC", "UNI.MC"
    ],
    "FTSE_100_Londres": [
        "AAL.L", "ABF.L", "ADM.L", "AHT.L", "ANTO.L", "AV.L", "AZN.L", "BA.L",
        "BARC.L", "BATS.L", "BDEV.L", "BKG.L", "BLND.L", "BP.L", "BRBY.L", "BT-A.L",
        "CCE.L", "CNA.L", "CPG.L", "CRDA.L", "DGE.L", "ENT.L", "EXPN.L", "FLTR.L",
        "FRAS.L", "FRES.L", "GLEN.L", "GSK.L", "HLN.L", "HSBA.L", "IAG.L", "IHG.L",
        "III.L", "IMB.L", "INF.L", "KGF.L", "LAND.L", "LGEN.L", "LLOY.L", "LSEG.L",
        "MNG.L", "MRO.L", "NG.L", "NWG.L", "PSON.L", "PRU.L", "REL.L", "RKT.L",
        "RMV.L", "RIO.L", "RR.L", "RS1.L", "SDR.L", "SGE.L", "SGRO.L", "SHEL.L",
        "SMIN.L", "SN.L", "SPX.L", "SSE.L", "STAN.L", "TW.L", "ULVR.L", "UU.L",
        "VOD.L", "WPP.L", "WTB.L"
    ],
    "FTSE_MIB_Milan": [
        "A2A.MI", "AMP.MI", "AZM.MI", "BAMI.MI", "BCA.MI", "BMED.MI", "BPER.MI",
        "CPR.MI", "DIA.MI", "ENEL.MI", "ENI.MI", "ERG.MI", "RACE.MI", "FBK.MI",
        "G.MI", "INW.MI", "ISP.MI", "LDO.MI", "MB.MI", "MONC.MI", "NEXI.MI",
        "PIRC.MI", "PST.MI", "PRY.MI", "REC.MI", "SPM.MI", "SRG.MI", "STMPA.MI",
        "TEN.MI", "TRN.MI", "UCG.MI", "UNI.MI"
    ]
}

def extraer_datos_seguros(symbol):
    ticker = yf.Ticker(symbol)
    datos = {
        "symbol": symbol,
        "name": "N/A",
        "sector": "N/A",
        "per": "N/A",
        "roe": "N/A",
        "roic": "N/A",
        "deuda_neta_ebitda": "N/A"
    }
    
    try:
        info = ticker.info
        if info and isinstance(info, dict) and len(info) > 10:
            datos["name"] = info.get("longName", "N/A")
            datos["sector"] = info.get("sector", "N/A")
            
            per = info.get("trailingPE")
            datos["per"] = round(per, 2) if isinstance(per, (int, float)) else "N/A"
            
            roe = info.get("returnOnEquity")
            datos["roe"] = round(roe * 100, 2) if isinstance(roe, (int, float)) else "N/A"
    except Exception:
        pass

    # Evitamos procesar ratios de balance complejos en sectores financieros/bancos
    if datos["sector"] not in ["Financial Services", "Financials", "Banks", "N/A"]:
        try:
            financials = ticker.financials
            balance = ticker.balance_sheet
            
            if financials is not None and balance is not None and not financials.empty and not balance.empty:
                financials.index = financials.index.str.upper()
                balance.index = balance.index.str.upper()
                
                ebit = None
                for tag in ['EBIT', 'OPERATING INCOME']:
                    if tag in financials.index:
                        ebit = financials.loc[tag]
                        break
                        
                ebitda = None
                for tag in ['EBITDA', 'NORMALIZED EBITDA']:
                    if tag in financials.index:
                        ebitda = financials.loc[tag]
                        break

                equity = None
                for tag in ['STOCKHOLDERS EQUITY', 'TOTAL EQUITY']:
                    if tag in balance.index:
                        equity = balance.loc[tag]
                        break
                
                debt = balance.loc['TOTAL DEBT'] if 'TOTAL DEBT' in balance.index else 0
                cash = balance.loc['CASH AND CASH EQUIVALENTS'] if 'CASH AND CASH EQUIVALENTS' in balance.index else 0
                
                # Desempaquetar series temporales si Yahoo devuelve historicos en lugar de escalares
                v_ebit = float(ebit.iloc[0] if isinstance(ebit, pd.Series) else ebit)
                v_ebitda = float(ebitda.iloc[0] if isinstance(ebitda, pd.Series) else ebitda) if ebitda is not None else None
                v_equity = float(equity.iloc[0] if isinstance(equity, pd.Series) else equity) if equity is not None else None
                v_debt = float(debt.iloc[0] if isinstance(debt, pd.Series) else debt)
                v_cash = float(cash.iloc[0] if isinstance(cash, pd.Series) else cash)

                # Calculo de ROIC (Ajuste fiscal del 25% estandar europeo)
                if v_equity and v_ebit:
                    capital_invertido = v_equity + v_debt - v_cash
                    if capital_invertido > 0:
                        datos["roic"] = round(((v_ebit * 0.75) / capital_invertido) * 100, 2)
                
                # Calculo de apalancamiento
                if v_ebitda and v_ebitda > 0:
                    datos["deuda_neta_ebitda"] = round((v_debt - v_cash) / v_ebitda, 2)
        except Exception:
            pass
            
    return datos

if __name__ == "__main__":
    print("-" * 80)
    print("PROCESANDO ANALISIS EN MASA: " + INDICE_SELECCIONADO)
    print("-" * 80)
    
    lista_tickers = DICCIONARIO_TICKERS.get(INDICE_SELECCIONADO, [])
    total_activos = len(lista_tickers)
    print("Se van a procesar " + str(total_activos) + " activos totales.")
    
    resultados = []
    
    for i, ticker in enumerate(lista_tickers):
        print("[" + str(i+1) + "/" + str(total_activos) + "] Descargando: " + ticker)
        data = extraer_datos_seguros(ticker)
        resultados.append(data)
        time.sleep(0.6) # Mantener tasa de peticiones controlada para evitar bloqueos
        
    # Guardar matriz final a un JSON plano estructurado
    df_resultado = pd.DataFrame(resultados)
    nombre_archivo = "euronext_" + INDICE_SELECCIONADO + ".json"
    df_resultado.to_json(nombre_archivo, orient="records", indent=4)
    
    print("\n" + "=" * 80)
    print("PROCESO TERMINADO")
    print("Se han guardado con exito " + str(len(resultados)) + " activos en: " + nombre_archivo)
    print("=" * 80)
