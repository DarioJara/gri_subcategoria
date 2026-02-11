"""
SISTEMA DE DESCARGA AUTOMATICA DE VARIABLES MACRO Y DE MERCADO
================================================================

Objetivo:
    Descargar y actualizar automaticamente series historicas de variables macroeconomicas
    y de mercado desde fuentes publicas (FRED, ECB, Eurostat, OECD) para alimentar el
    calculo del GRI (Global Risk Indicator), Interprete y ACRI.

Estructura:
    - GRI = Ciclo de Mercado + Ciclo Economico
    - Interprete = Momentum + Tendencia + Seasonality

Autor: Sistema Automatizado GRI
Fecha: 2025-01-19
Version: 2.0 (Parametrizado para GitHub)
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import logging
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import warnings
warnings.filterwarnings('ignore')

# Importar configuracion global
from config import config, validar_archivo_catalogo, mostrar_formato_esperado, COLUMNAS_REQUERIDAS_CATALOGO

# ============================================================================
# CONFIGURACION GLOBAL (usando modulo config.py)
# ============================================================================

# Propiedades accesibles para compatibilidad con codigo existente
# Estas se obtienen dinamicamente de la configuracion
def _get_base_dir():
    return config.base_dir

def _get_data_dir():
    return config.data_dir

def _get_logs_dir():
    return config.logs_dir

# Aliases para compatibilidad con imports externos
BASE_DIR = property(lambda self: config.base_dir)
DATA_DIR = property(lambda self: config.data_dir)
LOGS_DIR = property(lambda self: config.logs_dir)

# Variables que seran usadas por otros modulos
def get_data_dir():
    """Obtiene el directorio de datos configurado."""
    return config.data_dir

def get_logs_dir():
    """Obtiene el directorio de logs configurado."""
    return config.logs_dir

def get_fecha_inicio_objetivo():
    """Obtiene la fecha de inicio objetivo configurada."""
    return config.fecha_inicio_objetivo

# Configurar logging de forma diferida (para evitar crear archivos antes de configurar rutas)
logger = logging.getLogger(__name__)

def configurar_logging():
    """Configura el logging una vez que las rutas estan definidas."""
    config.inicializar_directorios()

    # Limpiar handlers existentes
    logger.handlers.clear()

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(config.logs_dir / f'descarga_macro_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'),
            logging.StreamHandler()
        ],
        force=True
    )

# Horizonte historico objetivo (25 anos para seasonality)
HORIZONTE_HISTORICO_ANOS = config.horizonte_historico_anos
FECHA_INICIO_OBJETIVO = config.fecha_inicio_objetivo

# ============================================================================
# CATÁLOGO MAESTRO DE VARIABLES - DEFINICIONES
# ============================================================================

class CatalogVariablesMacro:
    """
    Catálogo maestro de todas las variables macroeconómicas y de mercado necesarias
    para el cálculo del GRI e Intérprete.

    Organización:
        - CICLO DE MERCADO: Índices, volatilidad, spreads de crédito
        - CICLO ECONÓMICO: PIB, empleo, inflación, política monetaria
        - FACTORES ADICIONALES: FX, commodities
    """

    def __init__(self):
        """Inicializa el catálogo de variables."""
        self.variables_mercado = self._definir_variables_mercado()
        self.variables_macro = self._definir_variables_macro()
        self.variables_fx = self._definir_variables_fx()

        # Diccionario maestro completo
        self.catalogo_completo = {
            **self.variables_mercado,
            **self.variables_macro,
            **self.variables_fx
        }

        logger.info(f"Catálogo inicializado con {len(self.catalogo_completo)} variables")

    def _definir_variables_mercado(self) -> Dict:
        """
        Define variables de CICLO DE MERCADO (market sentiment, volatilidad, spreads).

        Fuentes principales: FRED (Federal Reserve Economic Data)
        """
        variables = {
            # =================================================================
            # RENTA VARIABLE - ÍNDICES PRINCIPALES
            # =================================================================
            'US_SP500': {
                'nombre': 'S&P 500 Index',
                'descripcion': 'Índice principal de renta variable USA (500 mayores empresas)',
                'fuente': 'FRED',
                'ticker': 'SP500',
                'frecuencia': 'D',  # Diaria
                'unidad': 'Index',
                'transformacion': None,
                'relevancia_gri': 'Ciclo de Mercado - Indicador principal de sentimiento equity USA',
                'asset_classes': ['Renta Variable USA', 'Renta Variable Táctico']
            },
            'US_NASDAQ': {
                'nombre': 'NASDAQ Composite Index',
                'descripcion': 'Índice de tecnología y growth USA',
                'fuente': 'FRED',
                'ticker': 'NASDAQCOM',
                'frecuencia': 'D',
                'unidad': 'Index',
                'transformacion': None,
                'relevancia_gri': 'Ciclo de Mercado - Sentimiento tecnología/growth',
                'asset_classes': ['Renta Variable USA']
            },
            'US_RUSSELL2000': {
                'nombre': 'Russell 2000 Index',
                'descripcion': 'Índice de small caps USA',
                'fuente': 'FRED',
                'ticker': 'RU2000PR',
                'frecuencia': 'D',
                'unidad': 'Index',
                'transformacion': None,
                'relevancia_gri': 'Ciclo de Mercado - Sentimiento small caps / riesgo',
                'asset_classes': ['Renta Variable USA']
            },
            'EU_STOXX600': {
                'nombre': 'STOXX Europe 600',
                'descripcion': 'Índice principal de renta variable Europa (600 empresas)',
                'fuente': 'OECD',  # Alternativa: Yahoo Finance
                'ticker': 'STOXX600',
                'frecuencia': 'D',
                'unidad': 'Index',
                'transformacion': None,
                'relevancia_gri': 'Ciclo de Mercado - Indicador principal equity Europa',
                'asset_classes': ['Renta Variable Europa']
            },
            'GLOBAL_MSCI_WORLD': {
                'nombre': 'MSCI World Index',
                'descripcion': 'Índice global de renta variable desarrollada',
                'fuente': 'FRED',
                'ticker': 'MXWO',  # Proxy disponible en FRED
                'frecuencia': 'D',
                'unidad': 'Index',
                'transformacion': None,
                'relevancia_gri': 'Ciclo de Mercado - Sentimiento global equity',
                'asset_classes': ['Renta Variable Global']
            },
            'EM_MSCI_EM': {
                'nombre': 'MSCI Emerging Markets Index',
                'descripcion': 'Índice de mercados emergentes',
                'fuente': 'FRED',
                'ticker': 'MXEF',  # Proxy en FRED
                'frecuencia': 'D',
                'unidad': 'Index',
                'transformacion': None,
                'relevancia_gri': 'Ciclo de Mercado - Sentimiento emergentes',
                'asset_classes': ['Renta Variable Emergentes']
            },

            # =================================================================
            # VOLATILIDAD IMPLÍCITA (Risk Sentiment)
            # =================================================================
            'US_VIX': {
                'nombre': 'VIX - CBOE Volatility Index',
                'descripcion': 'Índice de volatilidad implícita S&P 500 (Fear Index)',
                'fuente': 'FRED',
                'ticker': 'VIXCLS',
                'frecuencia': 'D',
                'unidad': 'Index',
                'transformacion': 'momentum_negative',  # Invertir para GRI (↑VIX = ↓Risk)
                'relevancia_gri': 'Ciclo de Mercado - Indicador CLAVE de miedo/estrés',
                'asset_classes': ['Global Risk Indicator']
            },
            'EU_VSTOXX': {
                'nombre': 'VSTOXX - Euro STOXX 50 Volatility',
                'descripcion': 'Índice de volatilidad implícita Euro STOXX 50',
                'fuente': 'FRED',
                'ticker': 'V2TX',  # Proxy
                'frecuencia': 'D',
                'unidad': 'Index',
                'transformacion': 'momentum_negative',
                'relevancia_gri': 'Ciclo de Mercado - Fear index Europa',
                'asset_classes': ['Renta Variable Europa']
            },
            'US_MOVE': {
                'nombre': 'MOVE Index - Bond Volatility',
                'descripcion': 'Índice de volatilidad de bonos del Tesoro USA',
                'fuente': 'FRED',
                'ticker': 'MOVE',  # ICE BofA MOVE Index
                'frecuencia': 'D',
                'unidad': 'Index',
                'transformacion': 'momentum_negative',
                'relevancia_gri': 'Ciclo de Mercado - Estrés en renta fija',
                'asset_classes': ['Renta Fija Gobierno']
            },

            # =================================================================
            # CURVA DE TIPOS - USA (Treasury Yields)
            # =================================================================
            'US_YIELD_3M': {
                'nombre': 'US Treasury 3-Month Yield',
                'descripcion': 'Rendimiento bonos del Tesoro USA a 3 meses',
                'fuente': 'FRED',
                'ticker': 'DGS3MO',
                'frecuencia': 'D',
                'unidad': '%',
                'transformacion': None,
                'relevancia_gri': 'Ciclo Económico - Política monetaria corto plazo',
                'asset_classes': ['Renta Fija Gobierno', 'Monetario']
            },
            'US_YIELD_2Y': {
                'nombre': 'US Treasury 2-Year Yield',
                'descripcion': 'Rendimiento bonos del Tesoro USA a 2 años',
                'fuente': 'FRED',
                'ticker': 'DGS2',
                'frecuencia': 'D',
                'unidad': '%',
                'transformacion': None,
                'relevancia_gri': 'Ciclo Económico - Expectativas de tipos',
                'asset_classes': ['Renta Fija Gobierno']
            },
            'US_YIELD_5Y': {
                'nombre': 'US Treasury 5-Year Yield',
                'descripcion': 'Rendimiento bonos del Tesoro USA a 5 años',
                'fuente': 'FRED',
                'ticker': 'DGS5',
                'frecuencia': 'D',
                'unidad': '%',
                'transformacion': None,
                'relevancia_gri': 'Ciclo Económico - Tipos medio plazo',
                'asset_classes': ['Renta Fija Gobierno']
            },
            'US_YIELD_10Y': {
                'nombre': 'US Treasury 10-Year Yield',
                'descripcion': 'Rendimiento bonos del Tesoro USA a 10 años (benchmark)',
                'fuente': 'FRED',
                'ticker': 'DGS10',
                'frecuencia': 'D',
                'unidad': '%',
                'transformacion': None,
                'relevancia_gri': 'Ciclo Económico - BENCHMARK tipos largo plazo',
                'asset_classes': ['Renta Fija Gobierno']
            },
            'US_YIELD_30Y': {
                'nombre': 'US Treasury 30-Year Yield',
                'descripcion': 'Rendimiento bonos del Tesoro USA a 30 años',
                'fuente': 'FRED',
                'ticker': 'DGS30',
                'frecuencia': 'D',
                'unidad': '%',
                'transformacion': None,
                'relevancia_gri': 'Ciclo Económico - Tipos ultra largo plazo',
                'asset_classes': ['Renta Fija Gobierno']
            },

            # =================================================================
            # SPREADS DE CURVA (Yield Curve Signals)
            # =================================================================
            'US_SPREAD_10Y2Y': {
                'nombre': 'US 10Y-2Y Spread',
                'descripcion': 'Diferencial 10Y - 2Y (indicador de recesión si negativo)',
                'fuente': 'FRED',
                'ticker': 'T10Y2Y',
                'frecuencia': 'D',
                'unidad': 'pp',
                'transformacion': None,
                'relevancia_gri': 'Ciclo Económico - CLAVE: Predictor de recesión',
                'asset_classes': ['Global Risk Indicator']
            },
            'US_SPREAD_10Y3M': {
                'nombre': 'US 10Y-3M Spread',
                'descripcion': 'Diferencial 10Y - 3M (señal temprana de recesión)',
                'fuente': 'FRED',
                'ticker': 'T10Y3M',
                'frecuencia': 'D',
                'unidad': 'pp',
                'transformacion': None,
                'relevancia_gri': 'Ciclo Económico - Señal adelantada recesión',
                'asset_classes': ['Global Risk Indicator']
            },

            # =================================================================
            # SPREADS DE CRÉDITO (Credit Risk)
            # =================================================================
            'US_CREDIT_IG_SPREAD': {
                'nombre': 'ICE BofA US Corporate IG OAS',
                'descripcion': 'Option-Adjusted Spread de bonos corporativos Investment Grade USA',
                'fuente': 'FRED',
                'ticker': 'BAMLC0A0CM',
                'frecuencia': 'D',
                'unidad': 'bp',
                'transformacion': 'momentum_negative',  # ↑Spread = ↓Risk
                'relevancia_gri': 'Ciclo de Mercado - Estrés crédito IG',
                'asset_classes': ['Renta Fija Corporativa', 'Global Risk Indicator']
            },
            'US_CREDIT_HY_SPREAD': {
                'nombre': 'ICE BofA US High Yield OAS',
                'descripcion': 'Option-Adjusted Spread de bonos High Yield USA',
                'fuente': 'FRED',
                'ticker': 'BAMLH0A0HYM2',
                'frecuencia': 'D',
                'unidad': 'bp',
                'transformacion': 'momentum_negative',
                'relevancia_gri': 'Ciclo de Mercado - Estrés crédito HY (indicador líder)',
                'asset_classes': ['Renta Fija High Yield', 'Global Risk Indicator']
            },
            'EU_CREDIT_IG_SPREAD': {
                'nombre': 'ICE BofA Euro Corporate IG OAS',
                'descripcion': 'Spread de bonos corporativos Investment Grade EUR',
                'fuente': 'FRED',
                'ticker': 'BAMLHE00EHYIEY',  # Proxy EUR IG
                'frecuencia': 'D',
                'unidad': 'bp',
                'transformacion': 'momentum_negative',
                'relevancia_gri': 'Ciclo de Mercado - Estrés crédito IG Europa',
                'asset_classes': ['Renta Fija Corporativa EUR']
            },
            'EU_CREDIT_HY_SPREAD': {
                'nombre': 'ICE BofA Euro High Yield OAS',
                'descripcion': 'Spread de bonos High Yield EUR',
                'fuente': 'FRED',
                'ticker': 'BAMLHE00EHYIOAS',
                'frecuencia': 'D',
                'unidad': 'bp',
                'transformacion': 'momentum_negative',
                'relevancia_gri': 'Ciclo de Mercado - Estrés HY Europa',
                'asset_classes': ['Renta Fija High Yield EUR']
            },
            'EM_CREDIT_SPREAD': {
                'nombre': 'JPM EMBI Global Spread',
                'descripcion': 'Spread de bonos soberanos emergentes',
                'fuente': 'FRED',
                'ticker': 'BAMLEMCBPITRIV',  # Proxy EM spreads
                'frecuencia': 'D',
                'unidad': 'bp',
                'transformacion': 'momentum_negative',
                'relevancia_gri': 'Ciclo de Mercado - Riesgo emergentes',
                'asset_classes': ['Renta Fija Emergente']
            },

            # =================================================================
            # CURVA DE TIPOS - EUROZONA (German Bunds)
            # =================================================================
            'EU_YIELD_2Y': {
                'nombre': 'German Bund 2-Year Yield',
                'descripcion': 'Rendimiento bonos alemanes a 2 años',
                'fuente': 'ECB',
                'ticker': 'FM.M.U2.EUR.RT.MM.EURIBOR2MD_.HSTA',
                'frecuencia': 'D',
                'unidad': '%',
                'transformacion': None,
                'relevancia_gri': 'Ciclo Económico - Tipos cortos EUR',
                'asset_classes': ['Renta Fija Gobierno EUR']
            },
            'EU_YIELD_10Y': {
                'nombre': 'German Bund 10-Year Yield',
                'descripcion': 'Rendimiento bonos alemanes a 10 años (benchmark EUR)',
                'fuente': 'FRED',
                'ticker': 'IRLTLT01DEM156N',  # Proxy en FRED
                'frecuencia': 'D',
                'unidad': '%',
                'transformacion': None,
                'relevancia_gri': 'Ciclo Económico - BENCHMARK tipos EUR',
                'asset_classes': ['Renta Fija Gobierno EUR']
            },

            # =================================================================
            # ÍNDICES DE CONDICIONES FINANCIERAS
            # =================================================================
            'US_FINANCIAL_CONDITIONS': {
                'nombre': 'Chicago Fed National Financial Conditions Index',
                'descripcion': 'Índice de condiciones financieras USA (>0 = restrictivo)',
                'fuente': 'FRED',
                'ticker': 'NFCI',
                'frecuencia': 'W',  # Semanal
                'unidad': 'Index',
                'transformacion': 'momentum_negative',
                'relevancia_gri': 'Ciclo de Mercado - Condiciones financieras generales',
                'asset_classes': ['Global Risk Indicator']
            },
        }

        return variables

    def _definir_variables_macro(self) -> Dict:
        """
        Define variables de CICLO ECONÓMICO (actividad, empleo, inflación, política monetaria).
        """
        variables = {
            # =================================================================
            # ACTIVIDAD ECONÓMICA - USA
            # =================================================================
            'US_GDP': {
                'nombre': 'US Real GDP',
                'descripcion': 'PIB real USA (nivel)',
                'fuente': 'FRED',
                'ticker': 'GDPC1',
                'frecuencia': 'Q',  # Trimestral
                'unidad': 'Billions of Chained 2017 Dollars',
                'transformacion': 'yoy_pct',  # Calcular variación interanual
                'relevancia_gri': 'Ciclo Económico - Crecimiento económico USA',
                'asset_classes': ['Global Risk Indicator']
            },
            'US_CFNAI': {
                'nombre': 'Chicago Fed National Activity Index',
                'descripcion': 'Índice de actividad económica USA (promedio móvil 3 meses)',
                'fuente': 'FRED',
                'ticker': 'CFNAIMA3',
                'frecuencia': 'M',  # Mensual
                'unidad': 'Index',
                'transformacion': 'momentum',
                'relevancia_gri': 'Ciclo Económico - INDICADOR PRINCIPAL GRI (CFNAI 2.1)',
                'asset_classes': ['Global Risk Indicator']
            },
            'US_ISM_MANUFACTURING': {
                'nombre': 'ISM Manufacturing PMI',
                'descripcion': 'Índice de gerentes de compras manufacturero USA (>50 = expansión)',
                'fuente': 'FRED',
                'ticker': 'NAPM',
                'frecuencia': 'M',
                'unidad': 'Index',
                'transformacion': 'momentum',
                'relevancia_gri': 'Ciclo Económico - Actividad manufacturera',
                'asset_classes': ['Global Risk Indicator']
            },
            'US_ISM_SERVICES': {
                'nombre': 'ISM Services PMI',
                'descripcion': 'Índice PMI de servicios USA',
                'fuente': 'FRED',
                'ticker': 'NMFCI',  # Proxy
                'frecuencia': 'M',
                'unidad': 'Index',
                'transformacion': 'momentum',
                'relevancia_gri': 'Ciclo Económico - Actividad servicios',
                'asset_classes': ['Global Risk Indicator']
            },
            'US_INDUSTRIAL_PRODUCTION': {
                'nombre': 'Industrial Production Index',
                'descripcion': 'Índice de producción industrial USA',
                'fuente': 'FRED',
                'ticker': 'INDPRO',
                'frecuencia': 'M',
                'unidad': 'Index 2017=100',
                'transformacion': 'yoy_pct',
                'relevancia_gri': 'Ciclo Económico - Producción industrial',
                'asset_classes': ['Global Risk Indicator']
            },
            'US_RETAIL_SALES': {
                'nombre': 'Retail Sales',
                'descripcion': 'Ventas minoristas USA',
                'fuente': 'FRED',
                'ticker': 'RSXFS',
                'frecuencia': 'M',
                'unidad': 'Millions of Dollars',
                'transformacion': 'yoy_pct',
                'relevancia_gri': 'Ciclo Económico - Consumo',
                'asset_classes': ['Global Risk Indicator']
            },

            # =================================================================
            # INFLACIÓN - USA
            # =================================================================
            'US_CPI': {
                'nombre': 'Consumer Price Index',
                'descripcion': 'Índice de precios al consumidor USA (headline)',
                'fuente': 'FRED',
                'ticker': 'CPIAUCSL',
                'frecuencia': 'M',
                'unidad': 'Index 1982-84=100',
                'transformacion': 'yoy_pct',
                'relevancia_gri': 'Ciclo Económico - Inflación general',
                'asset_classes': ['Global Risk Indicator']
            },
            'US_CORE_CPI': {
                'nombre': 'Core CPI',
                'descripcion': 'IPC subyacente (sin alimentos ni energía)',
                'fuente': 'FRED',
                'ticker': 'CPILFESL',
                'frecuencia': 'M',
                'unidad': 'Index 1982-84=100',
                'transformacion': 'yoy_pct',
                'relevancia_gri': 'Ciclo Económico - Inflación subyacente (clave Fed)',
                'asset_classes': ['Global Risk Indicator']
            },
            'US_PCE': {
                'nombre': 'Personal Consumption Expenditures Price Index',
                'descripcion': 'Índice PCE (preferido por la Fed)',
                'fuente': 'FRED',
                'ticker': 'PCEPI',
                'frecuencia': 'M',
                'unidad': 'Index 2017=100',
                'transformacion': 'yoy_pct',
                'relevancia_gri': 'Ciclo Económico - Inflación PCE',
                'asset_classes': ['Global Risk Indicator']
            },
            'US_CORE_PCE': {
                'nombre': 'Core PCE',
                'descripcion': 'PCE subyacente (objetivo principal Fed)',
                'fuente': 'FRED',
                'ticker': 'PCEPILFE',
                'frecuencia': 'M',
                'unidad': 'Index 2017=100',
                'transformacion': 'yoy_pct',
                'relevancia_gri': 'Ciclo Económico - OBJETIVO FED inflación',
                'asset_classes': ['Global Risk Indicator']
            },
            'US_INFLATION_EXPECTATIONS_5Y': {
                'nombre': '5-Year Breakeven Inflation Rate',
                'descripcion': 'Expectativas de inflación implícitas a 5 años',
                'fuente': 'FRED',
                'ticker': 'T5YIE',
                'frecuencia': 'D',
                'unidad': '%',
                'transformacion': None,
                'relevancia_gri': 'Ciclo Económico - Expectativas inflación',
                'asset_classes': ['Global Risk Indicator']
            },
            'US_INFLATION_EXPECTATIONS_5Y5Y': {
                'nombre': '5-Year, 5-Year Forward Inflation Expectation',
                'descripcion': 'Expectativas inflación 5 años dentro de 5 años (meta Fed)',
                'fuente': 'FRED',
                'ticker': 'T5YIFR',
                'frecuencia': 'D',
                'unidad': '%',
                'transformacion': None,
                'relevancia_gri': 'Ciclo Económico - Anclaje expectativas inflación',
                'asset_classes': ['Global Risk Indicator']
            },

            # =================================================================
            # EMPLEO - USA
            # =================================================================
            'US_UNEMPLOYMENT_RATE': {
                'nombre': 'Unemployment Rate',
                'descripcion': 'Tasa de desempleo USA',
                'fuente': 'FRED',
                'ticker': 'UNRATE',
                'frecuencia': 'M',
                'unidad': '%',
                'transformacion': 'momentum_negative',  # ↑Desempleo = ↓Risk
                'relevancia_gri': 'Ciclo Económico - Mercado laboral',
                'asset_classes': ['Global Risk Indicator']
            },
            'US_NONFARM_PAYROLLS': {
                'nombre': 'Non-Farm Payrolls',
                'descripcion': 'Creación de empleo no agrícola USA (variación mensual)',
                'fuente': 'FRED',
                'ticker': 'PAYEMS',
                'frecuencia': 'M',
                'unidad': 'Thousands',
                'transformacion': 'mom_change',  # Variación mensual
                'relevancia_gri': 'Ciclo Económico - Creación empleo (muy seguido)',
                'asset_classes': ['Global Risk Indicator']
            },
            'US_INITIAL_CLAIMS': {
                'nombre': 'Initial Unemployment Claims',
                'descripcion': 'Solicitudes iniciales de desempleo (semanal)',
                'fuente': 'FRED',
                'ticker': 'ICSA',
                'frecuencia': 'W',
                'unidad': 'Thousands',
                'transformacion': 'momentum_negative',
                'relevancia_gri': 'Ciclo Económico - Indicador adelantado empleo',
                'asset_classes': ['Global Risk Indicator']
            },

            # =================================================================
            # POLÍTICA MONETARIA - USA
            # =================================================================
            'US_FED_FUNDS_RATE': {
                'nombre': 'Federal Funds Effective Rate',
                'descripcion': 'Tipo de interés oficial de la Fed',
                'fuente': 'FRED',
                'ticker': 'FEDFUNDS',
                'frecuencia': 'M',
                'unidad': '%',
                'transformacion': None,
                'relevancia_gri': 'Ciclo Económico - CLAVE política monetaria',
                'asset_classes': ['Global Risk Indicator', 'Monetario']
            },

            # =================================================================
            # ACTIVIDAD ECONÓMICA - EUROZONA
            # =================================================================
            'EU_GDP': {
                'nombre': 'Eurozone Real GDP',
                'descripcion': 'PIB real Eurozona',
                'fuente': 'OECD',
                'ticker': 'NAEXKP01EZQ652S',  # Proxy en FRED
                'frecuencia': 'Q',
                'unidad': 'Index',
                'transformacion': 'yoy_pct',
                'relevancia_gri': 'Ciclo Económico - Crecimiento Eurozona',
                'asset_classes': ['Renta Variable Europa']
            },
            'EU_PMI_MANUFACTURING': {
                'nombre': 'Eurozone Manufacturing PMI',
                'descripcion': 'PMI manufacturero Eurozona',
                'fuente': 'FRED',
                'ticker': 'EAPMI',  # Proxy
                'frecuencia': 'M',
                'unidad': 'Index',
                'transformacion': 'momentum',
                'relevancia_gri': 'Ciclo Económico - Actividad manufacturera EUR',
                'asset_classes': ['Renta Variable Europa']
            },
            'EU_PMI_SERVICES': {
                'nombre': 'Eurozone Services PMI',
                'descripcion': 'PMI servicios Eurozona',
                'fuente': 'OECD',
                'ticker': 'EA_PMI_SERVICES',  # Proxy
                'frecuencia': 'M',
                'unidad': 'Index',
                'transformacion': 'momentum',
                'relevancia_gri': 'Ciclo Económico - Actividad servicios EUR',
                'asset_classes': ['Renta Variable Europa']
            },

            # =================================================================
            # INFLACIÓN - EUROZONA
            # =================================================================
            'EU_HICP': {
                'nombre': 'Eurozone HICP',
                'descripcion': 'Índice armonizado de precios al consumidor',
                'fuente': 'ECB',
                'ticker': 'ICP.M.U2.Y.000000.3.INX',
                'frecuencia': 'M',
                'unidad': 'Index 2015=100',
                'transformacion': 'yoy_pct',
                'relevancia_gri': 'Ciclo Económico - Inflación Eurozona',
                'asset_classes': ['Renta Variable Europa']
            },
            'EU_CORE_HICP': {
                'nombre': 'Eurozone Core HICP',
                'descripcion': 'HICP subyacente (sin energía ni alimentos)',
                'fuente': 'ECB',
                'ticker': 'ICP.M.U2.Y.XEF000.3.INX',
                'frecuencia': 'M',
                'unidad': 'Index 2015=100',
                'transformacion': 'yoy_pct',
                'relevancia_gri': 'Ciclo Económico - Inflación subyacente EUR',
                'asset_classes': ['Renta Variable Europa']
            },

            # =================================================================
            # EMPLEO - EUROZONA
            # =================================================================
            'EU_UNEMPLOYMENT_RATE': {
                'nombre': 'Eurozone Unemployment Rate',
                'descripcion': 'Tasa de desempleo Eurozona',
                'fuente': 'OECD',
                'ticker': 'LRHUTTTTEZM156S',  # Proxy en FRED
                'frecuencia': 'M',
                'unidad': '%',
                'transformacion': 'momentum_negative',
                'relevancia_gri': 'Ciclo Económico - Mercado laboral EUR',
                'asset_classes': ['Renta Variable Europa']
            },

            # =================================================================
            # POLÍTICA MONETARIA - EUROZONA
            # =================================================================
            'EU_ECB_DEPOSIT_RATE': {
                'nombre': 'ECB Deposit Facility Rate',
                'descripcion': 'Tipo de depósito del BCE (tipo director principal)',
                'fuente': 'ECB',
                'ticker': 'FM.D.U2.EUR.4F.KR.DFR.LEV',
                'frecuencia': 'D',
                'unidad': '%',
                'transformacion': None,
                'relevancia_gri': 'Ciclo Económico - Política monetaria BCE',
                'asset_classes': ['Renta Variable Europa', 'Monetario EUR']
            },

            # =================================================================
            # ACTIVIDAD - CHINA (para Asia ex-Japan y EM)
            # =================================================================
            'CN_GDP': {
                'nombre': 'China Real GDP',
                'descripcion': 'PIB real China',
                'fuente': 'FRED',
                'ticker': 'MKTGDPCNA646NWDB',  # World Bank via FRED
                'frecuencia': 'Q',
                'unidad': 'Billions USD',
                'transformacion': 'yoy_pct',
                'relevancia_gri': 'Ciclo Económico - Crecimiento China',
                'asset_classes': ['Renta Variable Asia ex-Japan', 'Renta Variable Emergentes']
            },
            'CN_PMI_MANUFACTURING': {
                'nombre': 'China Manufacturing PMI',
                'descripcion': 'PMI manufacturero China (oficial)',
                'fuente': 'FRED',
                'ticker': 'CHNPMINTO',
                'frecuencia': 'M',
                'unidad': 'Index',
                'transformacion': 'momentum',
                'relevancia_gri': 'Ciclo Económico - Actividad manufacturera China',
                'asset_classes': ['Renta Variable Asia ex-Japan']
            },
        }

        return variables

    def _definir_variables_fx(self) -> Dict:
        """Define variables de tipos de cambio (FX)."""
        variables = {
            'FX_EURUSD': {
                'nombre': 'EUR/USD Exchange Rate',
                'descripcion': 'Tipo de cambio Euro vs Dólar',
                'fuente': 'FRED',
                'ticker': 'DEXUSEU',
                'frecuencia': 'D',
                'unidad': 'USD per 1 EUR',
                'transformacion': None,
                'relevancia_gri': 'Factor de conversión y carry trade',
                'asset_classes': ['FX', 'Global']
            },
            'FX_GBPUSD': {
                'nombre': 'GBP/USD Exchange Rate',
                'descripcion': 'Tipo de cambio Libra vs Dólar',
                'fuente': 'FRED',
                'ticker': 'DEXUSUK',
                'frecuencia': 'D',
                'unidad': 'USD per 1 GBP',
                'transformacion': None,
                'relevancia_gri': 'Factor de conversión',
                'asset_classes': ['FX']
            },
            'FX_USDJPY': {
                'nombre': 'USD/JPY Exchange Rate',
                'descripcion': 'Tipo de cambio Dólar vs Yen',
                'fuente': 'FRED',
                'ticker': 'DEXJPUS',
                'frecuencia': 'D',
                'unidad': 'JPY per 1 USD',
                'transformacion': None,
                'relevancia_gri': 'Factor de conversión y carry trade',
                'asset_classes': ['FX']
            },
            'FX_USDCHF': {
                'nombre': 'USD/CHF Exchange Rate',
                'descripcion': 'Tipo de cambio Dólar vs Franco Suizo',
                'fuente': 'FRED',
                'ticker': 'DEXSZUS',
                'frecuencia': 'D',
                'unidad': 'CHF per 1 USD',
                'transformacion': None,
                'relevancia_gri': 'Factor de conversión',
                'asset_classes': ['FX']
            },
        }

        return variables

    def get_variable(self, codigo: str) -> Optional[Dict]:
        """Obtiene los metadatos de una variable específica."""
        return self.catalogo_completo.get(codigo)

    def get_variables_por_asset_class(self, asset_class: str) -> Dict:
        """Obtiene todas las variables relevantes para una clase de activo."""
        variables_filtradas = {}

        for codigo, metadata in self.catalogo_completo.items():
            if 'asset_classes' in metadata and asset_class in metadata['asset_classes']:
                variables_filtradas[codigo] = metadata

        return variables_filtradas

    def get_variables_por_fuente(self, fuente: str) -> Dict:
        """Obtiene todas las variables de una fuente específica."""
        return {
            codigo: metadata
            for codigo, metadata in self.catalogo_completo.items()
            if metadata.get('fuente') == fuente
        }

    def exportar_diccionario_datos(self, filepath: Path = None) -> pd.DataFrame:
        """
        Exporta el diccionario de datos completo a CSV para auditoria.

        Returns:
            DataFrame con el diccionario de datos
        """
        if filepath is None:
            filepath = config.data_dir / "diccionario_datos_macro.csv"

        registros = []
        for codigo, metadata in self.catalogo_completo.items():
            registro = {
                'Codigo_Variable': codigo,
                'Nombre': metadata.get('nombre'),
                'Descripcion': metadata.get('descripcion'),
                'Fuente': metadata.get('fuente'),
                'Ticker_ID': metadata.get('ticker'),
                'Frecuencia': metadata.get('frecuencia'),
                'Unidad': metadata.get('unidad'),
                'Transformacion': metadata.get('transformacion'),
                'Relevancia_GRI': metadata.get('relevancia_gri'),
                'Asset_Classes': ', '.join(metadata.get('asset_classes', []))
            }
            registros.append(registro)

        df_dict = pd.DataFrame(registros)
        df_dict.to_csv(filepath, index=False, encoding='utf-8-sig')

        logger.info(f"Diccionario de datos exportado a: {filepath}")
        logger.info(f"Total variables documentadas: {len(df_dict)}")

        return df_dict


# ============================================================================
# MAPEO ACTIVO → FACTORES
# ============================================================================

class MapeoActivoFactores:
    """
    Genera el mapeo entre activos del universo invertible y las variables
    macro/mercado relevantes para cada uno.
    """

    def __init__(self, catalogo: CatalogVariablesMacro, ruta_catalogo_etfs: Path = None):
        """
        Inicializa el mapeo.

        Args:
            catalogo: Instancia del catalogo de variables macro
            ruta_catalogo_etfs: Ruta al archivo Excel/CSV con el catalogo de ETFs.
                                Si no se proporciona, se usa la ruta de la configuracion global.
        """
        self.catalogo = catalogo

        # Usar ruta proporcionada o la de la configuracion global
        if ruta_catalogo_etfs is not None:
            self.ruta_universo = Path(ruta_catalogo_etfs)
        elif config.ruta_catalogo_etfs is not None:
            self.ruta_universo = config.ruta_catalogo_etfs
        else:
            # Intentar buscar en el directorio de input por defecto
            self.ruta_universo = None

        self.df_universo = None
        self.df_mapeo = None

        logger.info("MapeoActivoFactores inicializado")

    def cargar_universo_invertible(self, ruta_archivo: Path = None) -> pd.DataFrame:
        """
        Carga el catalogo de ETFs del universo invertible.

        Args:
            ruta_archivo: Ruta opcional al archivo. Si no se proporciona, usa self.ruta_universo

        Returns:
            DataFrame con el catalogo de ETFs

        Raises:
            FileNotFoundError: Si no se encuentra el archivo
            ValueError: Si el archivo no tiene el formato correcto
        """
        # Usar ruta proporcionada o la del constructor
        ruta = ruta_archivo if ruta_archivo else self.ruta_universo

        if ruta is None:
            raise FileNotFoundError(
                "No se ha configurado la ruta al catalogo de ETFs.\n"
                "Por favor, proporcione la ruta al archivo Excel/CSV con el catalogo."
            )

        if not Path(ruta).exists():
            raise FileNotFoundError(
                f"No se encontro el archivo: {ruta}\n"
                "Por favor, verifique que la ruta sea correcta."
            )

        # Validar formato del archivo
        es_valido, mensaje, df = validar_archivo_catalogo(Path(ruta))

        if not es_valido:
            logger.error(f"Error de validacion del archivo:")
            logger.error(mensaje)
            mostrar_formato_esperado()
            raise ValueError(mensaje)

        self.df_universo = df
        self.ruta_universo = Path(ruta)
        logger.info(f"Universo invertible cargado: {len(self.df_universo)} ETFs")

        # Mostrar estadisticas
        tipos_activo = self.df_universo['V001_TipoActivo'].value_counts()
        for tipo, count in tipos_activo.items():
            logger.info(f"  - {tipo}: {count} ETFs")

        return self.df_universo

    def generar_mapeo_completo(self) -> pd.DataFrame:
        """
        Genera el mapeo completo entre cada ETF y las variables macro/mercado relevantes.

        Returns:
            DataFrame con el mapeo Activo → Factores
        """
        if self.df_universo is None:
            self.cargar_universo_invertible()

        mapeos = []

        for idx, etf in self.df_universo.iterrows():
            # Extraer metadatos del ETF
            ticker = etf['V001_Ticker']
            nombre = etf['V001_Name']
            tipo_activo = etf['V001_TipoActivo']
            zona_geografica = etf['V001_ZonaGeografica']
            moneda = etf['V001_Moneda']
            clasificacion_l1 = etf['Clasificacion_L1']

            # Identificar variables relevantes basadas en clasificación
            variables_asignadas = self._asignar_variables_por_clasificacion(
                tipo_activo, zona_geografica, clasificacion_l1, moneda
            )

            # Crear registro de mapeo
            mapeo = {
                'ETF_Ticker': ticker,
                'ETF_Nombre': nombre,
                'Tipo_Activo': tipo_activo,
                'Zona_Geografica': zona_geografica,
                'Moneda': moneda,
                'Clasificacion_L1': clasificacion_l1,
                'Variables_Asignadas': ', '.join(variables_asignadas),
                'Num_Variables': len(variables_asignadas)
            }

            mapeos.append(mapeo)

        self.df_mapeo = pd.DataFrame(mapeos)

        # Guardar mapeo
        filepath_mapeo = config.data_dir / "mapeo_activo_factores.csv"
        self.df_mapeo.to_csv(filepath_mapeo, index=False, encoding='utf-8-sig')

        logger.info(f"Mapeo Activo→Factores generado: {filepath_mapeo}")
        logger.info(f"Total mapeos: {len(self.df_mapeo)}")

        return self.df_mapeo

    def _asignar_variables_por_clasificacion(
        self,
        tipo_activo: str,
        zona: str,
        clasificacion: str,
        moneda: str
    ) -> List[str]:
        """
        Asigna las variables macro/mercado relevantes según la clasificación del activo.

        Args:
            tipo_activo: Equities, Fixed Income, Alternatives, Monetary
            zona: USA, Europe, Global, Asia Ex-Japan, Emerging Markets, etc.
            clasificacion: Clasificación L1 específica
            moneda: EUR, USD, GBP, CHF

        Returns:
            Lista de códigos de variables asignadas
        """
        variables = set()

        # Variables GLOBALES que se asignan a TODOS los activos (GRI base)
        variables.update([
            'US_VIX',  # Volatilidad global
            'US_SPREAD_10Y2Y',  # Señal recesión
            'US_CFNAI',  # Actividad económica USA (líder global)
            'US_FED_FUNDS_RATE',  # Política monetaria global
            'US_CREDIT_HY_SPREAD',  # Estrés crédito global
        ])

        # ===== RENTA VARIABLE =====
        #if tipo_activo == 'Equities':
        if tipo_activo in ('Renta Variable', 'Equities'):
            if zona == 'USA':
                variables.update([
                    'US_SP500', 'US_NASDAQ', 'US_RUSSELL2000',
                    'US_GDP', 'US_ISM_MANUFACTURING', 'US_UNEMPLOYMENT_RATE',
                    'US_CPI', 'US_CORE_PCE'
                ])
            elif zona == 'Europe':
                variables.update([
                    'EU_STOXX600', 'EU_VSTOXX',
                    'EU_GDP', 'EU_PMI_MANUFACTURING', 'EU_PMI_SERVICES',
                    'EU_HICP', 'EU_CORE_HICP', 'EU_UNEMPLOYMENT_RATE',
                    'EU_ECB_DEPOSIT_RATE', 'EU_YIELD_10Y'
                ])
            elif zona == 'Global':
                variables.update([
                    'GLOBAL_MSCI_WORLD', 'US_SP500', 'EU_STOXX600',
                    'US_GDP', 'EU_GDP', 'US_ISM_MANUFACTURING'
                ])
            elif zona == 'Asia Ex-Japan':
                variables.update([
                    'CN_GDP', 'CN_PMI_MANUFACTURING',
                    'EM_MSCI_EM', 'EM_CREDIT_SPREAD'
                ])
            elif zona == 'Emerging Markets':
                variables.update([
                    'EM_MSCI_EM', 'EM_CREDIT_SPREAD',
                    'CN_GDP', 'CN_PMI_MANUFACTURING',
                    'FX_EURUSD'  # Sensibilidad USD
                ])

        # ===== RENTA FIJA =====
        #elif tipo_activo == 'Fixed Income':
        elif tipo_activo in ('Renta Fija', 'Fixed Income'):
            #if 'Gobierno' in clasificacion:
            if any(x in clasificacion for x in ['Gobierno', 'RF - Gobierno','RF - Municipal']):
                if 'EUR' in moneda or zona == 'Europe':
                    variables.update([
                        'EU_YIELD_2Y', 'EU_YIELD_10Y',
                        'EU_HICP', 'EU_ECB_DEPOSIT_RATE',
                        'US_YIELD_10Y'  # Referencia global
                    ])
                elif 'USD' in moneda or zona == 'USA':
                    variables.update([
                        'US_YIELD_2Y', 'US_YIELD_5Y', 'US_YIELD_10Y', 'US_YIELD_30Y',
                        'US_SPREAD_10Y2Y', 'US_SPREAD_10Y3M',
                        'US_CPI', 'US_CORE_PCE', 'US_INFLATION_EXPECTATIONS_5Y',
                        'US_MOVE'
                    ])

            #elif 'Corporativa' in clasificacion:
            elif any(x in clasificacion for x in ['Corporativa', 'RF - Corporativa']):
                if 'EUR' in moneda:
                    variables.update([
                        'EU_CREDIT_IG_SPREAD', 'EU_YIELD_10Y',
                        'EU_PMI_MANUFACTURING', 'EU_VSTOXX'
                    ])
                else:  # USD
                    variables.update([
                        'US_CREDIT_IG_SPREAD', 'US_YIELD_10Y',
                        'US_ISM_MANUFACTURING', 'US_VIX'
                    ])

            #elif 'High Yield' in clasificacion:
            elif any(x in clasificacion for x in ['High Yield', 'RF PREFERENTES','RF - Internacional']):
                if 'EUR' in moneda:
                    variables.update([
                        'EU_CREDIT_HY_SPREAD', 'EU_VSTOXX',
                        'EU_PMI_MANUFACTURING'
                    ])
                else:
                    variables.update([
                        'US_CREDIT_HY_SPREAD', 'US_VIX',
                        'US_ISM_MANUFACTURING', 'US_FINANCIAL_CONDITIONS'
                    ])

            #elif 'Emergente' in clasificacion:
            elif any(x in clasificacion for x in ['Emergente', 'RF EMERGENTES']):
                variables.update([
                    'EM_CREDIT_SPREAD', 'FX_EURUSD',
                    'US_YIELD_10Y', 'US_VIX',
                    'CN_GDP'
                ])

        # ===== MONETARIO =====
        #elif tipo_activo == 'Monetary':
        elif tipo_activo in ('Monetary', 'MONETARIO'):
            if 'EUR' in moneda:
                variables.update(['EU_ECB_DEPOSIT_RATE', 'US_YIELD_3M'])
            else:
                variables.update(['US_FED_FUNDS_RATE', 'US_YIELD_3M'])

        # ===== TIPO DE CAMBIO según moneda =====
        if moneda == 'EUR':
            variables.add('FX_EURUSD')
        elif moneda == 'GBP':
            variables.add('FX_GBPUSD')
        elif moneda == 'CHF':
            variables.add('FX_USDCHF')

        return sorted(list(variables))


# ============================================================================
# FUNCIÓN PRINCIPAL PARA TESTING
# ============================================================================

def main():
    """Función principal para testing del módulo."""
    logger.info("="*100)
    logger.info("SISTEMA DE DESCARGA AUTOMÁTICA DE VARIABLES MACRO Y DE MERCADO - TESTING")
    logger.info("="*100)

    # 1. Inicializar catálogo de variables
    logger.info("\n[1] Inicializando catálogo de variables...")
    catalogo = CatalogVariablesMacro()

    # 2. Exportar diccionario de datos
    logger.info("\n[2] Exportando diccionario de datos para auditoría...")
    df_dict = catalogo.exportar_diccionario_datos()
    print("\nPrimeras 10 variables del diccionario:")
    print(df_dict.head(10))

    # 3. Generar mapeo Activo → Factores
    logger.info("\n[3] Generando mapeo Activo → Factores...")
    mapeo = MapeoActivoFactores(catalogo)
    df_mapeo = mapeo.generar_mapeo_completo()
    print("\nPrimeros 10 mapeos:")
    print(df_mapeo.head(10))

    # 4. Resumen estadístico
    logger.info("\n[4] Resumen estadístico:")
    logger.info(f"  - Total variables definidas: {len(catalogo.catalogo_completo)}")
    logger.info(f"  - Variables de mercado: {len(catalogo.variables_mercado)}")
    logger.info(f"  - Variables macroeconómicas: {len(catalogo.variables_macro)}")
    logger.info(f"  - Variables FX: {len(catalogo.variables_fx)}")
    logger.info(f"  - Total ETFs mapeados: {len(df_mapeo)}")
    logger.info(f"  - Media variables por ETF: {df_mapeo['Num_Variables'].mean():.1f}")

    logger.info("\n" + "="*100)
    logger.info("TESTING COMPLETADO - Módulo funcionando correctamente")
    logger.info("="*100)


if __name__ == "__main__":
    main()
