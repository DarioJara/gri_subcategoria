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

# Importar catálogo de variables
from Mod_GRI_MacroEconomicos import CatalogVariablesMacro, BASE_DIR, DATA_DIR, LOGS_DIR, FECHA_INICIO_OBJETIVO

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
# ORQUESTADOR DE DESCARGA MULTI-FUENTE
# ============================================================================

class OrquestadorDescargaMacro:
    """
    Orquesta la descarga de todas las variables desde múltiples fuentes.

    Prioridad de fuentes:
        1. FRED (datos USA y algunos globales)
        2. Yahoo Finance (índices bursátiles)
        3. ECB (datos Eurozona) - TODO
        4. OECD (datos internacionales) - TODO
    """

    def __init__(self, fred_api_key: Optional[str] = None):
        """
        Inicializa el orquestador.

        Args:
            fred_api_key: API key de FRED (opcional pero recomendado)
        """
        self.fred = DescargadorFRED(api_key=fred_api_key)
        self.yahoo = DescargadorYahooFinance()

        self.catalogo = CatalogVariablesMacro()

        self.series_descargadas = {}
        self.metadata_descarga = []

        logger.info("Orquestador de descarga inicializado")

    def descargar_todas_las_series(self) -> pd.DataFrame:
        """
        Descarga todas las series del catálogo desde las fuentes correspondientes.

        Returns:
            DataFrame con todas las series (index=fecha, columnas=variables)
        """
        logger.info("="*100)
        logger.info("INICIANDO DESCARGA COMPLETA DE VARIABLES MACRO Y DE MERCADO")
        logger.info("="*100)

        # 1. Descargar desde FRED
        logger.info("\n[1/3] Descargando series desde FRED...")
        variables_fred = self.catalogo.get_variables_por_fuente('FRED')
        series_fred = self.fred.descargar_multiples_series(variables_fred, delay_segundos=0.05)
        self.series_descargadas.update(series_fred)

        # 2. Descargar índices desde Yahoo Finance (complemento)
        logger.info("\n[2/3] Descargando índices desde Yahoo Finance...")
        self._descargar_indices_yahoo()

        # 3. TODO: Descargar desde ECB y OECD
        logger.info("\n[3/3] Descarga desde ECB/OECD: TODO (implementación futura)")

        # Construir DataFrame maestro
        logger.info("\n[4/4] Construyendo DataFrame maestro...")
        df_maestro = self._construir_dataframe_maestro()

        # Generar metadata
        self._generar_metadata_descarga()

        logger.info("\n" + "="*100)
        logger.info(f"DESCARGA COMPLETADA: {len(self.series_descargadas)} series descargadas")
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
        filepath_maestro = DATA_DIR / "df_maestro_variables_macro.csv"
        df.to_csv(filepath_maestro, encoding='utf-8-sig')
        logger.info(f"DataFrame maestro exportado a: {filepath_maestro}")

        # Guardar a pickle (más eficiente para cargar)
        filepath_pickle = DATA_DIR / "df_maestro_variables_macro.pkl"
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

        filepath_meta = DATA_DIR / "metadata_descarga_series.csv"
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
            filepath_maestro = DATA_DIR / "df_maestro_variables_macro.pkl"

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
