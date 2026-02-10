"""
SCRIPT PRINCIPAL - SISTEMA DE DESCARGA AUTOMÁTICA GRI
======================================================

Ejecuta el flujo completo de generación de variables macro y de mercado.

Uso:
    python main.py

Autor: Sistema Automatizado GRI
Fecha: 2025-11-19
"""

import logging
import sys
from datetime import datetime
from pathlib import Path

# Importar módulos del sistema
from Mod_GRI_MacroEconomicos import (
    CatalogVariablesMacro,
    MapeoActivoFactores,
    logger as logger_macro
)

from Mod_Descarga_API_Publica import (
    OrquestadorDescargaMacro,
    logger as logger_descarga
)

# Configurar logging principal
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """Flujo principal del sistema."""

    print("\n" + "="*100)
    print("SISTEMA DE DESCARGA AUTOMÁTICA DE VARIABLES MACRO Y DE MERCADO - GRI")
    print("="*100)
    print(f"Fecha ejecución: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*100 + "\n")

    # ========================================================================
    # PASO 1: GENERAR CATÁLOGO DE VARIABLES
    # ========================================================================
    print("\n[PASO 1/4] GENERANDO CATÁLOGO DE VARIABLES...")
    print("-"*100)

    try:
        catalogo = CatalogVariablesMacro()
        logger.info(f"Catálogo generado: {len(catalogo.catalogo_completo)} variables")

        # Exportar diccionario de datos
        df_dict = catalogo.exportar_diccionario_datos()
        print(f"  ✓ Diccionario de datos exportado: {len(df_dict)} variables")
        print(f"    - Variables de mercado: {len(catalogo.variables_mercado)}")
        print(f"    - Variables macroeconómicas: {len(catalogo.variables_macro)}")
        print(f"    - Variables FX: {len(catalogo.variables_fx)}")

    except Exception as e:
        logger.error(f"Error en PASO 1: {e}")
        sys.exit(1)

    # ========================================================================
    # PASO 2: GENERAR MAPEO ACTIVO → FACTORES
    # ========================================================================
    print("\n[PASO 2/4] GENERANDO MAPEO ACTIVO → FACTORES...")
    print("-"*100)

    try:
        mapeo = MapeoActivoFactores(catalogo)
        df_mapeo = mapeo.generar_mapeo_completo()

        print(f"  ✓ Mapeo generado: {len(df_mapeo)} ETFs mapeados")
        print(f"    - Media variables por ETF: {df_mapeo['Num_Variables'].mean():.1f}")
        print(f"    - Min variables: {df_mapeo['Num_Variables'].min()}")
        print(f"    - Max variables: {df_mapeo['Num_Variables'].max()}")

        # Mostrar distribución por tipo de activo
        print("\n  Distribución por Tipo de Activo:")
        distribucion = df_mapeo.groupby('Tipo_Activo').agg({
            'ETF_Ticker': 'count',
            'Num_Variables': 'mean'
        }).rename(columns={'ETF_Ticker': 'Num_ETFs', 'Num_Variables': 'Media_Variables'})

        for tipo, row in distribucion.iterrows():
            print(f"    - {tipo}: {row['Num_ETFs']} ETFs (promedio {row['Media_Variables']:.1f} variables)")

    except Exception as e:
        logger.error(f"Error en PASO 2: {e}")
        sys.exit(1)

    # ========================================================================
    # PASO 3: DESCARGAR SERIES HISTÓRICAS
    # ========================================================================
    print("\n[PASO 3/4] DESCARGANDO SERIES HISTÓRICAS DESDE APIS PÚBLICAS...")
    print("-"*100)

    # Solicitar API key al usuario
    fred_api_key = input("\n¿Tienes una API key de FRED? (Sí/No): ").strip().lower()

    if fred_api_key in ['si', 'sí', 's', 'yes', 'y']:
        api_key = input("Introduce tu API key de FRED: ").strip()

        if not api_key:
            print("\n⚠️ ADVERTENCIA: No se proporcionó API key.")
            print("Se usará pandas_datareader como fallback (limitado).")
            api_key = None
    else:
        print("\n⚠️ Para obtener una API key GRATUITA de FRED:")
        print("   https://fredaccount.stlouisfed.org/apikeys")
        print("\n   Se usará pandas_datareader como fallback (limitado).\n")
        api_key = None

    try:
        # Inicializar orquestador
        orquestador = OrquestadorDescargaMacro(fred_api_key=api_key)

        # Descargar todas las series
        df_maestro = orquestador.descargar_todas_las_series()

        print("\n  ✓ Descarga completada")
        print(f"    - Series descargadas: {len(orquestador.series_descargadas)}")
        print(f"    - Shape DataFrame maestro: {df_maestro.shape}")
        print(f"    - Rango temporal: {df_maestro.index.min().strftime('%Y-%m-%d')} a {df_maestro.index.max().strftime('%Y-%m-%d')}")

    except Exception as e:
        logger.error(f"Error en PASO 3: {e}")
        print("\n⚠️ La descarga puede haber fallado por falta de API key de FRED.")
        print("   Revisa la sección 'Instalación' en README.md")
        sys.exit(1)

    # ========================================================================
    # PASO 4: RESUMEN FINAL Y OUTPUTS
    # ========================================================================
    print("\n[PASO 4/4] RESUMEN FINAL Y OUTPUTS GENERADOS...")
    print("-"*100)

    print("\n📁 ARCHIVOS GENERADOS:")
    print("\n  1. DICCIONARIO DE DATOS:")
    print("     - 2.-Output/data/diccionario_datos_macro.csv")
    print("       → Metadata completa de las 53 variables")

    print("\n  2. MAPEO ACTIVO-FACTORES:")
    print("     - 2.-Output/data/mapeo_activo_factores.csv")
    print("       → Relación entre 142 ETFs y variables asignadas")

    print("\n  3. DATAFRAME MAESTRO:")
    print("     - 2.-Output/data/df_maestro_variables_macro.csv")
    print("     - 2.-Output/data/df_maestro_variables_macro.pkl (recomendado)")
    print(f"       → {df_maestro.shape[0]} filas x {df_maestro.shape[1]} columnas")
    print(f"       → Rango: {df_maestro.index.min().strftime('%Y-%m-%d')} a {df_maestro.index.max().strftime('%Y-%m-%d')}")

    print("\n  4. METADATA DE DESCARGA:")
    print("     - 2.-Output/data/metadata_descarga_series.csv")
    print("       → Registro de auditoría de la descarga")

    print("\n  5. LOGS:")
    print("     - 2.-Output/logs/descarga_macro_YYYYMMDD_HHMMSS.log")

    # ========================================================================
    # EJEMPLO DE USO
    # ========================================================================
    print("\n" + "="*100)
    print("PRÓXIMOS PASOS - CÓMO USAR LOS DATOS")
    print("="*100)

    print("\n1. Cargar DataFrame maestro:")
    print("   ```python")
    print("   import pandas as pd")
    print("   df = pd.read_pickle('2.-Output/data/df_maestro_variables_macro.pkl')")
    print("   ```")

    print("\n2. Calcular transformaciones para GRI:")
    print("   - Momentum: log(precio_t) - log(precio_t-1)")
    print("   - Filtros: Butterworth lowpass")
    print("   - Media móvil: rolling(40)")
    print("   - Normalización: 2-sided incremental (252 días)")

    print("\n3. Ejemplo - Procesar VIX para GRI:")
    print("   ```python")
    print("   import numpy as np")
    print("   # Momentum negativo (↑VIX = ↓Risk)")
    print("   vix_momentum = -(np.log(df['US_VIX']) - np.log(df['US_VIX'].shift(1)))")
    print("   # Aplicar filtro lowpass y media móvil...")
    print("   ```")

    print("\n4. Ver documentación completa:")
    print("   - README.md: Guía completa de uso")
    print("   - Ejemplos avanzados de integración con GRI")

    # ========================================================================
    # FIN
    # ========================================================================
    print("\n" + "="*100)
    print("✅ SISTEMA EJECUTADO CORRECTAMENTE")
    print("="*100)
    print(f"Tiempo de ejecución: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*100 + "\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️ Proceso interrumpido por el usuario.")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Error fatal: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
