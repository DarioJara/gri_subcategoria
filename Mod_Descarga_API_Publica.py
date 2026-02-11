"""
MÓDULO DE DESCARGA AUTOMATIZADA DESDE APIS PÚBLICAS
====================================================

Descarga series históricas desde fuentes públicas:
    - FRED (Federal Reserve Economic Data) - Principal fuente USA
    - Yahoo Finance - Índices bursátiles (fallback)
    - ECB Statistical Data Warehouse - Datos Eurozona
    - OECD - Datos internacionales

Requisitos:
    pip install pandas-datareader fredapi yfinance oecd requests

Autor: Sistema Automatizado GRI
Fecha: 2025-01-19
Versión: 1.0
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import logging
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Union
import time
import warnings
warnings.filterwarnings('ignore')

# Imports para APIs
try:
    import pandas_datareader.data as web
    PANDAS_DATAREADER_AVAILABLE = True
except ImportError:
    PANDAS_DATAREADER_AVAILABLE = False
    print("ADVERTENCIA: pandas-datareader no disponible. Instalar: pip install pandas-datareader")

try:
    from fredapi import Fred
    FREDAPI_AVAILABLE = True
except ImportError:
    FREDAPI_AVAILABLE = False
    print("ADVERTENCIA: fredapi no disponible. Instalar: pip install fredapi")

try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False
    print("ADVERTENCIA: yfinance no disponible. Instalar: pip install yfinance")

# Alpha Vantage (fuente alternativa)
try:
    from alpha_vantage.timeseries import TimeSeries
    from alpha_vantage.foreignexchange import ForeignExchange
    ALPHAVANTAGE_AVAILABLE = True
except ImportError:
    ALPHAVANTAGE_AVAILABLE = False
    # No mostrar advertencia ya que es opcional

# Quandl / Nasdaq Data Link
try:
    import quandl
    QUANDL_AVAILABLE = True
except ImportError:
    try:
        import nasdaqdatalink as quandl
        QUANDL_AVAILABLE = True
    except ImportError:
        QUANDL_AVAILABLE = False
        # No mostrar advertencia ya que es opcional

# Requests para World Bank API
try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

# Importar catalogo de variables y configuracion
from config import config
from Mod_GRI_MacroEconomicos import CatalogVariablesMacro, get_data_dir, get_logs_dir, get_fecha_inicio_objetivo

# Aliases para compatibilidad
FECHA_INICIO_OBJETIVO = get_fecha_inicio_objetivo()

# Configurar logging
logger = logging.getLogger(__name__)

# ============================================================================
# GESTOR DE DESCARGA DESDE FRED (FEDERAL RESERVE ECONOMIC DATA)
# ============================================================================

class DescargadorFRED:
    """
    Descarga series desde FRED (Federal Reserve Economic Data).

    FRED es la base de datos pública más completa para datos económicos USA.
    Requiere API key gratuita: https://fred.stlouisfed.org/docs/api/api_key.html

    Limitaciones:
        - Sin límite de requests (con API key)
        - Datos principalmente USA, algunos internacionales
        - Frecuencias: diaria, semanal, mensual, trimestral, anual
    """

    def __init__(self, api_key: Optional[str] = None):
        """
        Inicializa el descargador de FRED.

        Args:
            api_key: API key de FRED (gratuita). Si no se proporciona, se intentará
                     usar pandas_datareader sin autenticación (limitado).
        """
        self.api_key = api_key
        self.fred_client = None

        if FREDAPI_AVAILABLE and api_key:
            try:
                self.fred_client = Fred(api_key=api_key)
                logger.info("Cliente FRED inicializado correctamente con API key")
            except Exception as e:
                logger.warning(f"No se pudo inicializar FRED client: {e}")
                logger.info("Se usará pandas_datareader como fallback")

        elif not api_key:
            logger.warning("No se proporcionó API key de FRED")
            logger.info("Para obtener una (gratis): https://fred.stlouisfed.org/docs/api/api_key.html")
            logger.info("Se usará pandas_datareader sin autenticación (limitado)")

    def descargar_serie(
        self,
        ticker: str,
        fecha_inicio: Optional[datetime] = None,
        fecha_fin: Optional[datetime] = None,
        nombre_serie: str = None
    ) -> Optional[pd.Series]:
        """
        Descarga una serie individual desde FRED.

        Args:
            ticker: ID de la serie en FRED (ej: 'VIXCLS', 'DGS10')
            fecha_inicio: Fecha de inicio (por defecto: 25 años atrás)
            fecha_fin: Fecha de fin (por defecto: hoy)
            nombre_serie: Nombre descriptivo para logging

        Returns:
            Series con los datos o None si falla
        """
        if fecha_inicio is None:
            fecha_inicio = FECHA_INICIO_OBJETIVO

        if fecha_fin is None:
            fecha_fin = datetime.now()

        nombre_log = nombre_serie if nombre_serie else ticker

        try:
            # Método 1: Usar fredapi (preferido si hay API key)
            if self.fred_client:
                serie = self.fred_client.get_series(
                    ticker,
                    observation_start=fecha_inicio.strftime('%Y-%m-%d'),
                    observation_end=fecha_fin.strftime('%Y-%m-%d')
                )

                if serie is not None and len(serie) > 0:
                    logger.info(f"✓ FRED: {nombre_log} descargada - {len(serie)} observaciones "
                                f"({serie.index.min().strftime('%Y-%m-%d')} a {serie.index.max().strftime('%Y-%m-%d')})")
                    return serie
                else:
                    logger.warning(f"✗ FRED: {nombre_log} sin datos")
                    return None

            # Método 2: Usar pandas_datareader (fallback sin API key)
            elif PANDAS_DATAREADER_AVAILABLE:
                serie = web.DataReader(
                    ticker,
                    'fred',
                    start=fecha_inicio,
                    end=fecha_fin
                )

                if isinstance(serie, pd.DataFrame):
                    serie = serie.iloc[:, 0]  # Tomar primera columna

                if serie is not None and len(serie) > 0:
                    logger.info(f"✓ FRED (datareader): {nombre_log} - {len(serie)} obs")
                    return serie
                else:
                    logger.warning(f"✗ FRED: {nombre_log} sin datos")
                    return None

            else:
                logger.error("No hay cliente FRED disponible (falta fredapi o pandas-datareader)")
                return None

        except Exception as e:
            logger.error(f"✗ Error descargando {nombre_log} de FRED: {e}")
            return None

    def descargar_multiples_series(
        self,
        variables_dict: Dict[str, Dict],
        delay_segundos: float = 0.1
    ) -> Dict[str, pd.Series]:
        """
        Descarga múltiples series desde FRED.

        Args:
            variables_dict: Diccionario {codigo: metadata} del catálogo
            delay_segundos: Pausa entre requests para no saturar la API

        Returns:
            Diccionario {codigo: serie}
        """
        series_descargadas = {}
        total = len(variables_dict)

        logger.info(f"Iniciando descarga de {total} series desde FRED...")

        for idx, (codigo, metadata) in enumerate(variables_dict.items(), 1):
            if metadata.get('fuente') != 'FRED':
                continue  # Saltar si no es de FRED

            ticker = metadata.get('ticker')
            nombre = metadata.get('nombre')

            logger.info(f"[{idx}/{total}] Descargando {codigo}: {nombre}")

            serie = self.descargar_serie(
                ticker=ticker,
                nombre_serie=f"{codigo} ({nombre})"
            )

            if serie is not None:
                series_descargadas[codigo] = serie

            # Pausa para no saturar API
            time.sleep(delay_segundos)

        tasa_exito = len(series_descargadas) / total * 100 if total > 0 else 0
        logger.info(f"Descarga FRED completada: {len(series_descargadas)}/{total} series ({tasa_exito:.1f}%)")

        return series_descargadas


# ============================================================================
# GESTOR DE DESCARGA DESDE YAHOO FINANCE (ÍNDICES BURSÁTILES)
# ============================================================================

class DescargadorYahooFinance:
    """
    Descarga índices bursátiles y datos de mercado desde Yahoo Finance.

    Útil para:
        - Índices bursátiles (S&P 500, NASDAQ, etc.)
        - Precios de ETFs
        - Datos de volatilidad (VIX)
        - Commodities

    Limitaciones:
        - Sin autenticación necesaria
        - Puede tener límites de rate si se abusa
        - Cobertura global buena
    """

    def __init__(self):
        """Inicializa el descargador de Yahoo Finance."""
        if not YFINANCE_AVAILABLE:
            logger.warning("yfinance no disponible. Instalar: pip install yfinance")

    def descargar_indice(
        self,
        ticker: str,
        fecha_inicio: Optional[datetime] = None,
        fecha_fin: Optional[datetime] = None,
        nombre_serie: str = None
    ) -> Optional[pd.Series]:
        """
        Descarga un índice bursátil desde Yahoo Finance.

        Args:
            ticker: Ticker de Yahoo (ej: '^GSPC' para S&P 500, '^VIX' para VIX)
            fecha_inicio: Fecha inicio
            fecha_fin: Fecha fin
            nombre_serie: Nombre descriptivo

        Returns:
            Serie con precios de cierre ajustados
        """
        if not YFINANCE_AVAILABLE:
            logger.error("yfinance no disponible")
            return None

        if fecha_inicio is None:
            fecha_inicio = FECHA_INICIO_OBJETIVO

        if fecha_fin is None:
            fecha_fin = datetime.now()

        nombre_log = nombre_serie if nombre_serie else ticker

        try:
            data = yf.download(
                ticker,
                start=fecha_inicio.strftime('%Y-%m-%d'),
                end=fecha_fin.strftime('%Y-%m-%d'),
                progress=False,
                show_errors=False
            )

            if data is not None and len(data) > 0:
                # Usar 'Adj Close' si existe, sino 'Close'
                if 'Adj Close' in data.columns:
                    serie = data['Adj Close']
                else:
                    serie = data['Close']

                logger.info(f"✓ Yahoo Finance: {nombre_log} - {len(serie)} obs "
                            f"({serie.index.min().strftime('%Y-%m-%d')} a {serie.index.max().strftime('%Y-%m-%d')})")
                return serie
            else:
                logger.warning(f"✗ Yahoo Finance: {nombre_log} sin datos")
                return None

        except Exception as e:
            logger.error(f"✗ Error descargando {nombre_log} de Yahoo Finance: {e}")
            return None


# ============================================================================
# GESTOR DE DESCARGA DESDE ALPHA VANTAGE (ALTERNATIVA)
# ============================================================================

class DescargadorAlphaVantage:
    """
    Descarga series desde Alpha Vantage.

    Alpha Vantage ofrece datos de mercado gratuitos con limite de 5 llamadas/minuto.
    API Key gratuita: https://www.alphavantage.co/support/#api-key

    Util para:
        - Datos de acciones e indices
        - Tipos de cambio (FX)
        - Indicadores tecnicos
        - Criptomonedas
    """

    def __init__(self, api_key: Optional[str] = None):
        """Inicializa el descargador de Alpha Vantage."""
        self.api_key = api_key
        self.ts_client = None
        self.fx_client = None

        if ALPHAVANTAGE_AVAILABLE and api_key:
            try:
                self.ts_client = TimeSeries(key=api_key, output_format='pandas')
                self.fx_client = ForeignExchange(key=api_key, output_format='pandas')
                logger.info("Cliente Alpha Vantage inicializado")
            except Exception as e:
                logger.warning(f"No se pudo inicializar Alpha Vantage: {e}")
        elif not ALPHAVANTAGE_AVAILABLE:
            logger.info("Alpha Vantage no disponible. Instalar: pip install alpha_vantage")

    def descargar_serie_diaria(
        self,
        ticker: str,
        nombre_serie: str = None
    ) -> Optional[pd.Series]:
        """Descarga serie diaria de un ticker."""
        if not self.ts_client:
            return None

        nombre_log = nombre_serie if nombre_serie else ticker

        try:
            data, meta = self.ts_client.get_daily(symbol=ticker, outputsize='full')

            if data is not None and len(data) > 0:
                # Alpha Vantage devuelve datos en orden descendente
                data = data.sort_index()
                serie = data['4. close']  # Precio de cierre
                logger.info(f"✓ Alpha Vantage: {nombre_log} - {len(serie)} obs")
                return serie
            else:
                logger.warning(f"✗ Alpha Vantage: {nombre_log} sin datos")
                return None

        except Exception as e:
            logger.error(f"✗ Error Alpha Vantage {nombre_log}: {e}")
            return None

    def descargar_fx(
        self,
        from_currency: str,
        to_currency: str,
        nombre_serie: str = None
    ) -> Optional[pd.Series]:
        """Descarga tipo de cambio FX."""
        if not self.fx_client:
            return None

        nombre_log = nombre_serie if nombre_serie else f"{from_currency}/{to_currency}"

        try:
            data, meta = self.fx_client.get_currency_exchange_daily(
                from_symbol=from_currency,
                to_symbol=to_currency,
                outputsize='full'
            )

            if data is not None and len(data) > 0:
                data = data.sort_index()
                serie = data['4. close']
                logger.info(f"✓ Alpha Vantage FX: {nombre_log} - {len(serie)} obs")
                return serie
            else:
                return None

        except Exception as e:
            logger.error(f"✗ Error Alpha Vantage FX {nombre_log}: {e}")
            return None


# ============================================================================
# GESTOR DE DESCARGA DESDE WORLD BANK API
# ============================================================================

class DescargadorWorldBank:
    """
    Descarga datos macroeconomicos desde World Bank Open Data.

    API publica sin autenticacion: https://data.worldbank.org/

    Indicadores disponibles:
        - PIB (NY.GDP.MKTP.CD)
        - Inflacion (FP.CPI.TOTL.ZG)
        - Desempleo (SL.UEM.TOTL.ZS)
        - Comercio internacional
        - Indicadores sociales
    """

    BASE_URL = "https://api.worldbank.org/v2"

    # Mapeo de indicadores World Bank
    INDICADORES = {
        'GDP': 'NY.GDP.MKTP.CD',           # PIB nominal
        'GDP_GROWTH': 'NY.GDP.MKTP.KD.ZG', # Crecimiento PIB real
        'INFLATION': 'FP.CPI.TOTL.ZG',      # Inflacion CPI
        'UNEMPLOYMENT': 'SL.UEM.TOTL.ZS',   # Tasa desempleo
        'INTEREST_RATE': 'FR.INR.RINR',     # Tipo interes real
        'TRADE_BALANCE': 'NE.RSB.GNFS.ZS',  # Balanza comercial % PIB
    }

    def __init__(self):
        """Inicializa el descargador de World Bank."""
        if not REQUESTS_AVAILABLE:
            logger.warning("requests no disponible para World Bank API")

    def descargar_indicador(
        self,
        indicador: str,
        pais: str = "USA",
        fecha_inicio: int = 2000,
        fecha_fin: int = None,
        nombre_serie: str = None
    ) -> Optional[pd.Series]:
        """
        Descarga un indicador del World Bank.

        Args:
            indicador: Codigo del indicador (ej: 'NY.GDP.MKTP.CD')
            pais: Codigo ISO del pais (ej: 'USA', 'EMU' para Eurozona)
            fecha_inicio: Ano de inicio
            fecha_fin: Ano de fin (por defecto: actual)
        """
        if not REQUESTS_AVAILABLE:
            return None

        if fecha_fin is None:
            fecha_fin = datetime.now().year

        nombre_log = nombre_serie if nombre_serie else f"WB_{indicador}_{pais}"

        try:
            url = (
                f"{self.BASE_URL}/country/{pais}/indicator/{indicador}"
                f"?format=json&date={fecha_inicio}:{fecha_fin}&per_page=1000"
            )

            response = requests.get(url, timeout=30)
            response.raise_for_status()

            data = response.json()

            if len(data) < 2 or data[1] is None:
                logger.warning(f"✗ World Bank: {nombre_log} sin datos")
                return None

            # Parsear datos
            registros = []
            for item in data[1]:
                if item['value'] is not None:
                    registros.append({
                        'date': pd.to_datetime(f"{item['date']}-12-31"),
                        'value': float(item['value'])
                    })

            if not registros:
                return None

            df = pd.DataFrame(registros)
            df = df.set_index('date').sort_index()
            serie = df['value']

            logger.info(f"✓ World Bank: {nombre_log} - {len(serie)} obs")
            return serie

        except Exception as e:
            logger.error(f"✗ Error World Bank {nombre_log}: {e}")
            return None


# ============================================================================
# GESTOR DE DESCARGA DESDE QUANDL / NASDAQ DATA LINK
# ============================================================================

class DescargadorQuandl:
    """
    Descarga series desde Quandl / Nasdaq Data Link.

    Fuentes disponibles (gratuitas):
        - FRED (mirror)
        - Wiki Prices (acciones USA historicas)
        - USTREASURY (bonos USA)
        - CHRIS (futuros)

    API Key gratuita: https://data.nasdaq.com/sign-up
    """

    def __init__(self, api_key: Optional[str] = None):
        """Inicializa el descargador de Quandl."""
        self.api_key = api_key

        if QUANDL_AVAILABLE and api_key:
            quandl.ApiConfig.api_key = api_key
            logger.info("Cliente Quandl/Nasdaq Data Link inicializado")
        elif not QUANDL_AVAILABLE:
            logger.info("Quandl no disponible. Instalar: pip install quandl o pip install nasdaq-data-link")

    def descargar_serie(
        self,
        codigo: str,
        fecha_inicio: Optional[datetime] = None,
        fecha_fin: Optional[datetime] = None,
        nombre_serie: str = None
    ) -> Optional[pd.Series]:
        """
        Descarga una serie de Quandl.

        Args:
            codigo: Codigo de la serie (ej: 'FRED/GDP', 'USTREASURY/YIELD')
        """
        if not QUANDL_AVAILABLE:
            return None

        nombre_log = nombre_serie if nombre_serie else codigo

        try:
            if fecha_inicio is None:
                fecha_inicio = FECHA_INICIO_OBJETIVO

            if fecha_fin is None:
                fecha_fin = datetime.now()

            data = quandl.get(
                codigo,
                start_date=fecha_inicio.strftime('%Y-%m-%d'),
                end_date=fecha_fin.strftime('%Y-%m-%d')
            )

            if data is not None and len(data) > 0:
                # Si es DataFrame, tomar primera columna
                if isinstance(data, pd.DataFrame):
                    serie = data.iloc[:, 0]
                else:
                    serie = data

                logger.info(f"✓ Quandl: {nombre_log} - {len(serie)} obs")
                return serie
            else:
                logger.warning(f"✗ Quandl: {nombre_log} sin datos")
                return None

        except Exception as e:
            logger.error(f"✗ Error Quandl {nombre_log}: {e}")
            return None

    def descargar_treasury_yields(self) -> Dict[str, pd.Series]:
        """Descarga curva de rendimientos del Tesoro USA desde Quandl."""
        series = {}

        yields_codes = {
            'US_YIELD_1M': 'USTREASURY/YIELD',   # Columna '1 MO'
            'US_YIELD_3M': 'USTREASURY/YIELD',   # Columna '3 MO'
            'US_YIELD_1Y': 'USTREASURY/YIELD',   # Columna '1 YR'
            'US_YIELD_5Y': 'USTREASURY/YIELD',   # Columna '5 YR'
            'US_YIELD_10Y': 'USTREASURY/YIELD',  # Columna '10 YR'
            'US_YIELD_30Y': 'USTREASURY/YIELD',  # Columna '30 YR'
        }

        try:
            data = quandl.get('USTREASURY/YIELD')

            if data is not None:
                column_map = {
                    'US_YIELD_1M': '1 MO',
                    'US_YIELD_3M': '3 MO',
                    'US_YIELD_1Y': '1 YR',
                    'US_YIELD_5Y': '5 YR',
                    'US_YIELD_10Y': '10 YR',
                    'US_YIELD_30Y': '30 YR',
                }

                for codigo, columna in column_map.items():
                    if columna in data.columns:
                        series[codigo] = data[columna]
                        logger.info(f"✓ Quandl Treasury: {codigo} - {len(data[columna])} obs")

        except Exception as e:
            logger.error(f"✗ Error descargando Treasury yields: {e}")

        return series


# ============================================================================
# ORQUESTADOR DE DESCARGA MULTI-FUENTE
# ============================================================================

class OrquestadorDescargaMacro:
    """
    Orquesta la descarga de todas las variables desde multiples fuentes.

    Prioridad de fuentes:
        1. FRED (datos USA y algunos globales) - Principal
        2. Yahoo Finance (indices bursatiles)
        3. Alpha Vantage (alternativa para mercado)
        4. World Bank (datos macro globales)
        5. Quandl/Nasdaq Data Link (series financieras)
    """

    def __init__(
        self,
        fred_api_key: Optional[str] = None,
        alpha_vantage_api_key: Optional[str] = None,
        quandl_api_key: Optional[str] = None
    ):
        """
        Inicializa el orquestador con multiples fuentes de datos.

        Args:
            fred_api_key: API key de FRED (principal, gratuita)
            alpha_vantage_api_key: API key de Alpha Vantage (alternativa)
            quandl_api_key: API key de Quandl/Nasdaq Data Link (alternativa)
        """
        # Fuentes principales
        self.fred = DescargadorFRED(api_key=fred_api_key)
        self.yahoo = DescargadorYahooFinance()

        # Fuentes alternativas
        self.alpha_vantage = DescargadorAlphaVantage(api_key=alpha_vantage_api_key)
        self.world_bank = DescargadorWorldBank()
        self.quandl = DescargadorQuandl(api_key=quandl_api_key)

        self.catalogo = CatalogVariablesMacro()

        self.series_descargadas = {}
        self.series_fallidas = []
        self.metadata_descarga = []

        # Mostrar fuentes disponibles
        logger.info("Orquestador de descarga inicializado")
        logger.info("Fuentes configuradas:")
        logger.info(f"  - FRED: {'API key configurada' if fred_api_key else 'Sin API key (limitado)'}")
        logger.info(f"  - Yahoo Finance: Disponible")
        logger.info(f"  - Alpha Vantage: {'API key configurada' if alpha_vantage_api_key else 'No configurada'}")
        logger.info(f"  - World Bank: Disponible (sin autenticacion)")
        logger.info(f"  - Quandl: {'API key configurada' if quandl_api_key else 'No configurada'}")

    def descargar_todas_las_series(self) -> pd.DataFrame:
        """
        Descarga todas las series del catalogo desde las fuentes correspondientes.
        Usa fuentes alternativas cuando la principal falla.

        Returns:
            DataFrame con todas las series (index=fecha, columnas=variables)
        """
        logger.info("="*100)
        logger.info("INICIANDO DESCARGA COMPLETA DE VARIABLES MACRO Y DE MERCADO")
        logger.info("="*100)

        # 1. Descargar desde FRED (fuente principal)
        logger.info("\n[1/5] Descargando series desde FRED...")
        variables_fred = self.catalogo.get_variables_por_fuente('FRED')
        series_fred = self.fred.descargar_multiples_series(variables_fred, delay_segundos=0.05)
        self.series_descargadas.update(series_fred)

        # Identificar series fallidas para intentar con alternativas
        self.series_fallidas = [
            codigo for codigo in variables_fred.keys()
            if codigo not in self.series_descargadas
        ]

        if self.series_fallidas:
            logger.info(f"\n  Series no descargadas de FRED: {len(self.series_fallidas)}")

        # 2. Descargar indices desde Yahoo Finance (complemento)
        logger.info("\n[2/5] Descargando indices desde Yahoo Finance...")
        self._descargar_indices_yahoo()

        # 3. Intentar fuentes alternativas para series fallidas
        logger.info("\n[3/5] Intentando fuentes alternativas para series faltantes...")
        self._intentar_fuentes_alternativas()

        # 4. Descargar datos macro desde World Bank
        logger.info("\n[4/5] Descargando datos macro desde World Bank...")
        self._descargar_world_bank()

        # 5. Intentar Quandl para Treasury yields si faltan
        logger.info("\n[5/6] Verificando datos de Quandl...")
        self._descargar_quandl_fallback()

        # 6. Construir DataFrame maestro
        logger.info("\n[6/6] Construyendo DataFrame maestro...")
        df_maestro = self._construir_dataframe_maestro()

        # Generar metadata
        self._generar_metadata_descarga()

        # Resumen final
        logger.info("\n" + "="*100)
        logger.info(f"DESCARGA COMPLETADA: {len(self.series_descargadas)} series descargadas")
        if self.series_fallidas:
            logger.warning(f"Series no disponibles: {len(self.series_fallidas)}")
            for codigo in self.series_fallidas[:10]:  # Mostrar max 10
                logger.warning(f"  - {codigo}")
            if len(self.series_fallidas) > 10:
                logger.warning(f"  ... y {len(self.series_fallidas) - 10} mas")
        logger.info("="*100)

        return df_maestro

    def _descargar_indices_yahoo(self):
        """Descarga índices bursátiles específicos desde Yahoo Finance."""

        # Mapeo de códigos internos a tickers de Yahoo
        indices_yahoo = {
            'US_SP500': '^GSPC',  # S&P 500
            'US_NASDAQ': '^IXIC',  # NASDAQ Composite
            'US_RUSSELL2000': '^RUT',  # Russell 2000
            'US_VIX': '^VIX',  # VIX
            'EU_STOXX600': '^STOXX',  # STOXX 600 (verificar ticker)
            'GLOBAL_MSCI_WORLD': 'URTH',  # ETF proxy MSCI World
            'EM_MSCI_EM': 'EEM',  # ETF proxy MSCI EM
        }

        for codigo, ticker_yahoo in indices_yahoo.items():
            metadata = self.catalogo.get_variable(codigo)

            if metadata and codigo not in self.series_descargadas:
                nombre = metadata.get('nombre')
                logger.info(f"Descargando {codigo}: {nombre}")

                serie = self.yahoo.descargar_indice(
                    ticker=ticker_yahoo,
                    nombre_serie=f"{codigo} ({nombre})"
                )

                if serie is not None:
                    self.series_descargadas[codigo] = serie

                time.sleep(0.1)  # Pausa

    def _intentar_fuentes_alternativas(self):
        """Intenta descargar series fallidas desde fuentes alternativas."""
        if not self.series_fallidas:
            logger.info("  No hay series fallidas que reintentar")
            return

        logger.info(f"  Intentando {len(self.series_fallidas)} series con fuentes alternativas...")

        # Mapeo de series a tickers de Alpha Vantage
        alpha_vantage_map = {
            'US_SP500': 'SPY',      # ETF proxy
            'US_NASDAQ': 'QQQ',     # ETF proxy
            'US_VIX': 'VXX',        # ETN proxy
        }

        # Mapeo de FX para Alpha Vantage
        fx_map = {
            'FX_EURUSD': ('EUR', 'USD'),
            'FX_GBPUSD': ('GBP', 'USD'),
            'FX_USDJPY': ('USD', 'JPY'),
            'FX_USDCHF': ('USD', 'CHF'),
        }

        for codigo in self.series_fallidas.copy():
            # Intentar Alpha Vantage para indices
            if codigo in alpha_vantage_map and self.alpha_vantage.ts_client:
                ticker = alpha_vantage_map[codigo]
                serie = self.alpha_vantage.descargar_serie_diaria(ticker, nombre_serie=codigo)
                if serie is not None:
                    self.series_descargadas[codigo] = serie
                    self.series_fallidas.remove(codigo)
                    logger.info(f"  ✓ {codigo} descargado desde Alpha Vantage")
                time.sleep(12)  # Alpha Vantage tiene limite de 5/min

            # Intentar Alpha Vantage para FX
            elif codigo in fx_map and self.alpha_vantage.fx_client:
                from_curr, to_curr = fx_map[codigo]
                serie = self.alpha_vantage.descargar_fx(from_curr, to_curr, nombre_serie=codigo)
                if serie is not None:
                    self.series_descargadas[codigo] = serie
                    self.series_fallidas.remove(codigo)
                    logger.info(f"  ✓ {codigo} descargado desde Alpha Vantage FX")
                time.sleep(12)

        logger.info(f"  Series aun faltantes: {len(self.series_fallidas)}")

    def _descargar_world_bank(self):
        """Descarga indicadores macro desde World Bank como complemento."""
        # Solo descargar si faltan datos macro importantes
        indicadores_wb = {
            'WB_US_GDP_GROWTH': ('NY.GDP.MKTP.KD.ZG', 'USA'),
            'WB_EU_GDP_GROWTH': ('NY.GDP.MKTP.KD.ZG', 'EMU'),
            'WB_CN_GDP_GROWTH': ('NY.GDP.MKTP.KD.ZG', 'CHN'),
            'WB_US_INFLATION': ('FP.CPI.TOTL.ZG', 'USA'),
            'WB_EU_INFLATION': ('FP.CPI.TOTL.ZG', 'EMU'),
            'WB_US_UNEMPLOYMENT': ('SL.UEM.TOTL.ZS', 'USA'),
        }

        for codigo, (indicador, pais) in indicadores_wb.items():
            # Solo descargar si no tenemos datos equivalentes
            if codigo not in self.series_descargadas:
                serie = self.world_bank.descargar_indicador(
                    indicador=indicador,
                    pais=pais,
                    nombre_serie=codigo
                )
                if serie is not None:
                    self.series_descargadas[codigo] = serie

    def _descargar_quandl_fallback(self):
        """Usa Quandl como fallback para Treasury yields."""
        if not QUANDL_AVAILABLE or not self.quandl.api_key:
            return

        # Verificar si faltan yields del tesoro
        yields_faltantes = [
            codigo for codigo in ['US_YIELD_3M', 'US_YIELD_2Y', 'US_YIELD_5Y', 'US_YIELD_10Y', 'US_YIELD_30Y']
            if codigo not in self.series_descargadas
        ]

        if yields_faltantes:
            logger.info(f"  Intentando descargar {len(yields_faltantes)} Treasury yields desde Quandl...")
            treasury_series = self.quandl.descargar_treasury_yields()

            for codigo, serie in treasury_series.items():
                if codigo not in self.series_descargadas:
                    self.series_descargadas[codigo] = serie

    def _construir_dataframe_maestro(self) -> pd.DataFrame:
        """
        Construye el DataFrame maestro con todas las series descargadas.

        Returns:
            DataFrame con index=fecha, columnas=códigos de variables
        """
        if not self.series_descargadas:
            logger.warning("No hay series descargadas para construir DataFrame")
            return pd.DataFrame()

        # Convertir dict de series a DataFrame
        df = pd.DataFrame(self.series_descargadas)

        # Ordenar por fecha
        df = df.sort_index()

        # Renombrar index
        df.index.name = 'Fecha'

        logger.info(f"DataFrame maestro construido: {df.shape[0]} filas x {df.shape[1]} columnas")
        logger.info(f"Rango temporal: {df.index.min().strftime('%Y-%m-%d')} a {df.index.max().strftime('%Y-%m-%d')}")

        # Guardar a CSV
        filepath_maestro = config.data_dir / "df_maestro_variables_macro.csv"
        df.to_csv(filepath_maestro, encoding='utf-8-sig')
        logger.info(f"DataFrame maestro exportado a: {filepath_maestro}")

        # Guardar a pickle (más eficiente para cargar)
        filepath_pickle = config.data_dir / "df_maestro_variables_macro.pkl"
        df.to_pickle(filepath_pickle)
        logger.info(f"DataFrame maestro exportado (pickle): {filepath_pickle}")

        return df

    def _generar_metadata_descarga(self):
        """Genera metadata de la descarga para auditoría."""
        for codigo, serie in self.series_descargadas.items():
            metadata_var = self.catalogo.get_variable(codigo)

            if metadata_var and serie is not None and len(serie) > 0:
                record = {
                    'Codigo': codigo,
                    'Nombre': metadata_var.get('nombre'),
                    'Fuente': metadata_var.get('fuente'),
                    'Ticker': metadata_var.get('ticker'),
                    'Fecha_Descarga': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'Fecha_Inicio_Datos': serie.index.min().strftime('%Y-%m-%d'),
                    'Fecha_Fin_Datos': serie.index.max().strftime('%Y-%m-%d'),
                    'Num_Observaciones': len(serie),
                    'Valores_Nulos': serie.isna().sum(),
                    'Pct_Nulos': serie.isna().sum() / len(serie) * 100,
                    'Valor_Medio': serie.mean() if serie.dtype in [np.float64, np.int64] else np.nan,
                    'Valor_Min': serie.min() if serie.dtype in [np.float64, np.int64] else np.nan,
                    'Valor_Max': serie.max() if serie.dtype in [np.float64, np.int64] else np.nan,
                }
                self.metadata_descarga.append(record)

        df_meta = pd.DataFrame(self.metadata_descarga)

        filepath_meta = config.data_dir / "metadata_descarga_series.csv"
        df_meta.to_csv(filepath_meta, index=False, encoding='utf-8-sig')

        logger.info(f"Metadata de descarga exportada a: {filepath_meta}")

        return df_meta

    def actualizar_series_existentes(self, filepath_maestro: Path = None) -> pd.DataFrame:
        """
        Actualiza series existentes descargando solo datos nuevos.

        Args:
            filepath_maestro: Ruta al DataFrame maestro existente

        Returns:
            DataFrame actualizado
        """
        if filepath_maestro is None:
            filepath_maestro = config.data_dir / "df_maestro_variables_macro.pkl"

        if not filepath_maestro.exists():
            logger.info("No existe DataFrame maestro previo. Descargando todo desde cero...")
            return self.descargar_todas_las_series()

        # Cargar DataFrame existente
        logger.info(f"Cargando DataFrame maestro existente: {filepath_maestro}")
        df_existente = pd.read_pickle(filepath_maestro)

        fecha_ultima_actualizacion = df_existente.index.max()
        fecha_hoy = pd.Timestamp.now()

        dias_desactualizacion = (fecha_hoy - fecha_ultima_actualizacion).days

        logger.info(f"Última actualización: {fecha_ultima_actualizacion.strftime('%Y-%m-%d')}")
        logger.info(f"Días sin actualizar: {dias_desactualizacion}")

        if dias_desactualizacion < 1:
            logger.info("Datos ya actualizados (menos de 1 día). No se requiere descarga.")
            return df_existente

        # Descargar solo datos nuevos
        logger.info(f"Descargando datos desde {fecha_ultima_actualizacion.strftime('%Y-%m-%d')} hasta hoy...")

        # TODO: Implementar descarga incremental
        logger.warning("Descarga incremental aún no implementada. Descargando todo de nuevo...")

        return self.descargar_todas_las_series()


# ============================================================================
# FUNCIÓN PRINCIPAL PARA TESTING
# ============================================================================

def main():
    """Testing del módulo de descarga."""
    logger.info("="*100)
    logger.info("TESTING - MÓDULO DE DESCARGA AUTOMATIZADA")
    logger.info("="*100)

    # NOTA: Para usar FRED, necesitas una API key gratuita
    # Obtén la tuya en: https://fred.stlouisfed.org/docs/api/api_key.html
    FRED_API_KEY = None  # TODO: Añadir tu API key aquí o usar variable de entorno

    if FRED_API_KEY is None:
        logger.warning("="*100)
        logger.warning("NO SE PROPORCIONÓ API KEY DE FRED")
        logger.warning("Obtén una gratis en: https://fred.stlouisfed.org/docs/api/api_key.html")
        logger.warning("Se usará pandas_datareader como fallback (limitado)")
        logger.warning("="*100)

    # Inicializar orquestador
    orquestador = OrquestadorDescargaMacro(fred_api_key=FRED_API_KEY)

    # Descargar todas las series
    df_maestro = orquestador.descargar_todas_las_series()

    # Mostrar resumen
    print("\n" + "="*100)
    print("RESUMEN DEL DATAFRAME MAESTRO")
    print("="*100)
    print(f"Shape: {df_maestro.shape}")
    print(f"Columnas: {list(df_maestro.columns[:10])}...")
    print(f"\nPrimeras 5 filas:")
    print(df_maestro.head())
    print(f"\nÚltimas 5 filas:")
    print(df_maestro.tail())
    print(f"\nInfo:")
    print(df_maestro.info())
    print("\n" + "="*100)


if __name__ == "__main__":
    main()
