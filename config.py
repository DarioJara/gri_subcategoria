"""
CONFIGURACION GLOBAL DEL SISTEMA GRI
=====================================

Este modulo maneja la configuracion de rutas y parametros de forma dinamica,
permitiendo que el codigo sea portable y funcione en cualquier entorno.

Autor: Sistema Automatizado GRI
Fecha: 2025-01-19
"""

import os
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional


class ConfiguracionGRI:
    """
    Clase singleton para manejar la configuracion global del sistema.
    Permite configurar rutas de forma dinamica via metodos o inputs interactivos.
    """

    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not ConfiguracionGRI._initialized:
            # Directorio base por defecto (donde esta este archivo)
            self._base_dir = Path(__file__).parent
            self._input_dir = None
            self._output_dir = None
            self._data_dir = None
            self._logs_dir = None
            self._ruta_catalogo_etfs = None
            self._fred_api_key = None

            # Horizonte historico
            self.horizonte_historico_anos = 25
            self.fecha_inicio_objetivo = datetime.now() - timedelta(days=365 * self.horizonte_historico_anos)

            ConfiguracionGRI._initialized = True

    @property
    def base_dir(self) -> Path:
        return self._base_dir

    @base_dir.setter
    def base_dir(self, path: str):
        self._base_dir = Path(path)

    @property
    def input_dir(self) -> Path:
        if self._input_dir is None:
            return self._base_dir / "input"
        return self._input_dir

    @input_dir.setter
    def input_dir(self, path: str):
        self._input_dir = Path(path)

    @property
    def output_dir(self) -> Path:
        if self._output_dir is None:
            return self._base_dir / "output"
        return self._output_dir

    @output_dir.setter
    def output_dir(self, path: str):
        self._output_dir = Path(path)
        self._output_dir.mkdir(parents=True, exist_ok=True)

    @property
    def data_dir(self) -> Path:
        if self._data_dir is None:
            return self.output_dir / "data"
        return self._data_dir

    @data_dir.setter
    def data_dir(self, path: str):
        self._data_dir = Path(path)
        self._data_dir.mkdir(parents=True, exist_ok=True)

    @property
    def logs_dir(self) -> Path:
        if self._logs_dir is None:
            return self.output_dir / "logs"
        return self._logs_dir

    @logs_dir.setter
    def logs_dir(self, path: str):
        self._logs_dir = Path(path)
        self._logs_dir.mkdir(parents=True, exist_ok=True)

    @property
    def ruta_catalogo_etfs(self) -> Optional[Path]:
        return self._ruta_catalogo_etfs

    @ruta_catalogo_etfs.setter
    def ruta_catalogo_etfs(self, path: str):
        self._ruta_catalogo_etfs = Path(path) if path else None

    @property
    def fred_api_key(self) -> Optional[str]:
        # Intentar obtener de variable de entorno si no esta configurada
        if self._fred_api_key is None:
            return os.environ.get('FRED_API_KEY')
        return self._fred_api_key

    @fred_api_key.setter
    def fred_api_key(self, key: str):
        self._fred_api_key = key

    def inicializar_directorios(self):
        """Crea los directorios necesarios si no existen."""
        for directory in [self.output_dir, self.data_dir, self.logs_dir]:
            directory.mkdir(parents=True, exist_ok=True)

    def mostrar_configuracion(self):
        """Muestra la configuracion actual."""
        print("\n" + "="*60)
        print("CONFIGURACION ACTUAL")
        print("="*60)
        print(f"  Base Dir:     {self.base_dir}")
        print(f"  Input Dir:    {self.input_dir}")
        print(f"  Output Dir:   {self.output_dir}")
        print(f"  Data Dir:     {self.data_dir}")
        print(f"  Logs Dir:     {self.logs_dir}")
        print(f"  Catalogo ETFs: {self.ruta_catalogo_etfs or 'No configurado'}")
        print(f"  FRED API Key: {'Configurada' if self.fred_api_key else 'No configurada'}")
        print("="*60 + "\n")


# Columnas requeridas en el archivo de catalogo de ETFs
COLUMNAS_REQUERIDAS_CATALOGO = [
    'V001_Ticker',
    'V001_Name',
    'V001_TipoActivo',
    'V001_ZonaGeografica',
    'V001_Moneda',
    'Clasificacion_L1'
]

# Valores validos para cada columna
VALORES_VALIDOS = {
    'V001_TipoActivo': ['Renta Variable', 'Renta Fija', 'Equities', 'Fixed Income', 'Monetary', 'MONETARIO', 'Alternatives'],
    'V001_ZonaGeografica': ['USA', 'Europe', 'Global', 'Asia Ex-Japan', 'Emerging Markets', 'Japan', 'UK'],
    'V001_Moneda': ['USD', 'EUR', 'GBP', 'CHF', 'JPY']
}


def validar_archivo_catalogo(filepath: Path) -> tuple:
    """
    Valida que el archivo de catalogo tenga el formato correcto.

    Args:
        filepath: Ruta al archivo Excel/CSV del catalogo

    Returns:
        tuple: (es_valido: bool, mensaje: str, df: DataFrame o None)
    """
    import pandas as pd

    try:
        # Leer archivo
        if filepath.suffix.lower() in ['.xlsx', '.xls']:
            df = pd.read_excel(filepath)
        elif filepath.suffix.lower() == '.csv':
            df = pd.read_csv(filepath)
        else:
            return False, f"Formato de archivo no soportado: {filepath.suffix}. Use .xlsx, .xls o .csv", None

        # Verificar columnas requeridas
        columnas_faltantes = [col for col in COLUMNAS_REQUERIDAS_CATALOGO if col not in df.columns]

        if columnas_faltantes:
            msg = f"Columnas faltantes en el archivo:\n"
            msg += f"  - {', '.join(columnas_faltantes)}\n\n"
            msg += "Columnas encontradas en el archivo:\n"
            msg += f"  - {', '.join(df.columns.tolist())}\n\n"
            msg += "El archivo debe contener las siguientes columnas:\n"
            for col in COLUMNAS_REQUERIDAS_CATALOGO:
                msg += f"  - {col}\n"
            return False, msg, None

        # Verificar que no este vacio
        if len(df) == 0:
            return False, "El archivo esta vacio", None

        # Verificar valores nulos en columnas criticas
        for col in COLUMNAS_REQUERIDAS_CATALOGO:
            nulos = df[col].isna().sum()
            if nulos > 0:
                print(f"  ADVERTENCIA: {nulos} valores nulos en columna '{col}'")

        return True, f"Archivo valido: {len(df)} ETFs encontrados", df

    except Exception as e:
        return False, f"Error al leer el archivo: {str(e)}", None


def mostrar_formato_esperado():
    """Muestra el formato esperado del archivo de catalogo de ETFs."""
    print("\n" + "="*80)
    print("FORMATO ESPERADO DEL ARCHIVO DE CATALOGO DE ETFs")
    print("="*80)
    print("\nEl archivo debe ser Excel (.xlsx/.xls) o CSV (.csv) con las siguientes columnas:\n")

    print("-"*80)
    print(f"{'Columna':<25} {'Descripcion':<30} {'Ejemplo'}")
    print("-"*80)
    print(f"{'V001_Ticker':<25} {'Simbolo del ETF':<30} {'SPY, IVV, VOO'}")
    print(f"{'V001_Name':<25} {'Nombre completo del ETF':<30} {'SPDR S&P 500 ETF Trust'}")
    print(f"{'V001_TipoActivo':<25} {'Tipo de activo':<30} {'Renta Variable, Renta Fija'}")
    print(f"{'V001_ZonaGeografica':<25} {'Region geografica':<30} {'USA, Europe, Global'}")
    print(f"{'V001_Moneda':<25} {'Moneda base':<30} {'USD, EUR, GBP, CHF'}")
    print(f"{'Clasificacion_L1':<25} {'Clasificacion nivel 1':<30} {'RF - Gobierno, RF - Corporativa'}")
    print("-"*80)

    print("\nVALORES VALIDOS:")
    print("-"*80)
    for col, valores in VALORES_VALIDOS.items():
        print(f"\n{col}:")
        print(f"  {', '.join(valores)}")

    print("\n" + "="*80)


# Instancia global de configuracion
config = ConfiguracionGRI()
