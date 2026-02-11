"""
SCRIPT PRINCIPAL - SISTEMA DE DESCARGA AUTOMATICA GRI
======================================================

Ejecuta el flujo completo de generacion de variables macro y de mercado.

Uso:
    python main.py

Version: 2.1 (Parametrizado para GitHub + Dialogo Guardar Como)
Autor: Sistema Automatizado GRI
Fecha: 2025-01-19
"""

import logging
import sys
import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

# Importar tkinter para dialogos graficos
try:
    import tkinter as tk
    from tkinter import filedialog, messagebox
    TKINTER_AVAILABLE = True
except ImportError:
    TKINTER_AVAILABLE = False
    print("NOTA: tkinter no disponible. Se usara entrada por consola.")

# Importar configuracion ANTES que los otros modulos
from config import (
    config,
    validar_archivo_catalogo,
    mostrar_formato_esperado,
    COLUMNAS_REQUERIDAS_CATALOGO
)

# Importar modulos del sistema
from Mod_GRI_MacroEconomicos import (
    CatalogVariablesMacro,
    MapeoActivoFactores,
    configurar_logging
)

from Mod_Descarga_API_Publica import (
    OrquestadorDescargaMacro,
)

from Mod_Calculo_GRI import (
    SistemaGRI,
    CalculadorGRI,
    Interprete,
    CalculadorACRI,
    GeneradorReportes
)

# Configurar logging principal
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def mostrar_bienvenida():
    """Muestra el mensaje de bienvenida."""
    print("\n" + "="*100)
    print("SISTEMA GRI - GLOBAL RISK INDICATOR")
    print("="*100)
    print(f"Fecha ejecucion: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*100)
    print("\nEste sistema descarga datos macroeconomicos y calcula:")
    print("  - GRI (Global Risk Indicator) = Ciclo de Mercado + Ciclo Economico")
    print("  - Interprete = Momentum + Tendencia + Seasonality")
    print("  - ACRI (Asset Class Risk Indicator) por clase de activo")
    print("\nFuentes de datos disponibles:")
    print("  - FRED (Federal Reserve Economic Data) - Principal")
    print("  - Yahoo Finance - Indices bursatiles")
    print("  - Alpha Vantage - Alternativa para datos de mercado")
    print("  - World Bank - Datos macroeconomicos globales")
    print("  - Quandl/Nasdaq Data Link - Series financieras")
    print("\nSenales de salida:")
    print("  - GRI: AGRESIVO / NEUTRAL / DEFENSIVO")
    print("  - ACRI: OW+ / OW / N / UW / UW-\n")


def inicializar_tkinter():
    """Inicializa tkinter y oculta la ventana principal."""
    if TKINTER_AVAILABLE:
        root = tk.Tk()
        root.withdraw()  # Ocultar ventana principal
        root.attributes('-topmost', True)  # Mantener dialogos en primer plano
        return root
    return None


def solicitar_catalogo_etfs() -> Path:
    """Solicita al usuario la ruta del catalogo de ETFs mediante dialogo grafico."""
    print("\n" + "-"*80)
    print("CONFIGURACION DEL CATALOGO DE ETFs")
    print("-"*80)

    print("\nEl sistema necesita un archivo Excel o CSV con el catalogo de ETFs.")
    print("Este archivo debe contener las siguientes columnas:\n")

    for col in COLUMNAS_REQUERIDAS_CATALOGO:
        print(f"  - {col}")

    print("\n¿Deseas ver el formato detallado con ejemplos? (s/N): ", end="")
    if input().strip().lower() in ['s', 'si', 'yes', 'y']:
        mostrar_formato_esperado()

    directorio_actual = Path.cwd()
    ejemplo_path = directorio_actual / "ejemplo_catalogo_etfs.csv"

    while True:
        print("\nOpciones:")
        print("  [1] Seleccionar archivo de catalogo de ETFs (abre dialogo)")
        print("  [2] Usar archivo de ejemplo (ejemplo_catalogo_etfs.csv)")
        print("  [3] Saltar este paso (solo genera catalogo de variables, sin mapeo)")

        opcion = input("\nSelecciona una opcion (1/2/3): ").strip()

        if opcion == '1':
            if TKINTER_AVAILABLE:
                print("\n  Abriendo dialogo para seleccionar archivo...")
                print("  (Si no aparece, revisa la barra de tareas)")

                root = inicializar_tkinter()

                ruta = filedialog.askopenfilename(
                    title="Selecciona el archivo de catalogo de ETFs",
                    initialdir=str(directorio_actual),
                    filetypes=[
                        ("Archivos Excel/CSV", "*.xlsx *.xls *.csv"),
                        ("Excel", "*.xlsx *.xls"),
                        ("CSV", "*.csv"),
                        ("Todos los archivos", "*.*")
                    ]
                )

                if root:
                    root.destroy()

                if not ruta:
                    print("  No se selecciono archivo.")
                    continue

                ruta_path = Path(ruta)
            else:
                ruta = input("\nIntroduce la ruta completa al archivo: ").strip()
                ruta = ruta.strip('"').strip("'")

                if not ruta:
                    print("  Ruta no valida. Intenta de nuevo.")
                    continue

                ruta_path = Path(ruta)

                if not ruta_path.exists():
                    print(f"  ERROR: El archivo no existe: {ruta_path}")
                    continue

            es_valido, mensaje, _ = validar_archivo_catalogo(ruta_path)

            if es_valido:
                print(f"  {mensaje}")
                print(f"  Archivo seleccionado: {ruta_path}")
                return ruta_path
            else:
                print(f"\n  ERROR DE VALIDACION:")
                print(f"  {mensaje}")

                if TKINTER_AVAILABLE:
                    root = inicializar_tkinter()
                    reintentar = messagebox.askyesno(
                        "Error de validacion",
                        f"El archivo no tiene el formato correcto:\n\n{mensaje}\n\n¿Deseas seleccionar otro archivo?"
                    )
                    if root:
                        root.destroy()
                    if not reintentar:
                        return None
                else:
                    print("\n  ¿Deseas intentar con otro archivo? (S/n): ", end="")
                    if input().strip().lower() in ['n', 'no']:
                        return None
                continue

        elif opcion == '2':
            if ejemplo_path.exists():
                print(f"  Usando archivo de ejemplo: {ejemplo_path}")
                return ejemplo_path
            else:
                print(f"  ERROR: No se encontro el archivo de ejemplo en: {ejemplo_path}")
                print("  Por favor, asegurate de que el archivo existe.")
                continue

        elif opcion == '3':
            print("\n  Saltando configuracion del catalogo de ETFs.")
            print("  Solo se generara el catalogo de variables macro.")
            return None

        else:
            print("  Opcion no valida. Selecciona 1, 2 o 3.")


def solicitar_api_keys() -> dict:
    """Solicita al usuario las API keys disponibles."""
    print("\n" + "-"*80)
    print("CONFIGURACION DE API KEYS")
    print("-"*80)

    api_keys = {
        'fred': None,
        'alpha_vantage': None,
        'quandl': None
    }

    # FRED API Key
    print("\n[1/3] FRED (Federal Reserve Economic Data) - Fuente Principal")
    print("-"*50)

    api_key_env = os.environ.get('FRED_API_KEY')
    if api_key_env:
        print(f"  API key encontrada en variable de entorno FRED_API_KEY")
        usar_env = input("  ¿Usar esta API key? (S/n): ").strip().lower()
        if usar_env not in ['n', 'no']:
            api_keys['fred'] = api_key_env

    if not api_keys['fred']:
        print("\n  Para obtener tu API key GRATUITA de FRED:")
        print("    https://fredaccount.stlouisfed.org/apikeys")
        respuesta = input("\n  ¿Tienes una API key de FRED? (S/n): ").strip().lower()

        if respuesta in ['s', 'si', 'yes', 'y', '']:
            api_key = input("  Introduce tu API key de FRED: ").strip()
            if api_key:
                api_keys['fred'] = api_key
                print("    API key FRED configurada.")

    # Alpha Vantage API Key (Alternativa)
    print("\n[2/3] Alpha Vantage - Fuente Alternativa (opcional)")
    print("-"*50)

    api_key_env = os.environ.get('ALPHAVANTAGE_API_KEY')
    if api_key_env:
        print(f"  API key encontrada en variable de entorno ALPHAVANTAGE_API_KEY")
        api_keys['alpha_vantage'] = api_key_env
    else:
        print("  Para obtener tu API key GRATUITA de Alpha Vantage:")
        print("    https://www.alphavantage.co/support/#api-key")
        respuesta = input("\n  ¿Tienes una API key de Alpha Vantage? (s/N): ").strip().lower()

        if respuesta in ['s', 'si', 'yes', 'y']:
            api_key = input("  Introduce tu API key de Alpha Vantage: ").strip()
            if api_key:
                api_keys['alpha_vantage'] = api_key
                print("    API key Alpha Vantage configurada.")

    # Quandl/Nasdaq Data Link API Key (Alternativa)
    print("\n[3/3] Quandl/Nasdaq Data Link - Fuente Alternativa (opcional)")
    print("-"*50)

    api_key_env = os.environ.get('QUANDL_API_KEY') or os.environ.get('NASDAQ_DATA_LINK_API_KEY')
    if api_key_env:
        print(f"  API key encontrada en variable de entorno")
        api_keys['quandl'] = api_key_env
    else:
        print("  Para obtener tu API key GRATUITA de Nasdaq Data Link:")
        print("    https://data.nasdaq.com/sign-up")
        respuesta = input("\n  ¿Tienes una API key de Quandl/Nasdaq? (s/N): ").strip().lower()

        if respuesta in ['s', 'si', 'yes', 'y']:
            api_key = input("  Introduce tu API key: ").strip()
            if api_key:
                api_keys['quandl'] = api_key
                print("    API key Quandl configurada.")

    # Resumen
    print("\n" + "-"*50)
    print("RESUMEN DE API KEYS CONFIGURADAS:")
    print(f"  - FRED: {'Configurada' if api_keys['fred'] else 'No configurada (usara fallback)'}")
    print(f"  - Alpha Vantage: {'Configurada' if api_keys['alpha_vantage'] else 'No configurada'}")
    print(f"  - Quandl: {'Configurada' if api_keys['quandl'] else 'No configurada'}")

    return api_keys


def dialogo_guardar_como(archivos_generados: list) -> Path:
    """
    Muestra un dialogo 'Guardar Como' para que el usuario elija donde guardar los resultados.

    Args:
        archivos_generados: Lista de rutas de archivos generados

    Returns:
        Path del directorio destino seleccionado
    """
    print("\n" + "="*100)
    print("GUARDAR RESULTADOS")
    print("="*100)

    if TKINTER_AVAILABLE:
        print("\n  Abriendo dialogo para seleccionar donde guardar los resultados...")
        print("  (Si no aparece, revisa la barra de tareas)")

        root = inicializar_tkinter()

        # Mostrar mensaje informativo
        messagebox.showinfo(
            "Proceso Completado",
            f"Se han generado {len(archivos_generados)} archivos.\n\n"
            "Selecciona la carpeta donde deseas guardar los resultados."
        )

        # Abrir dialogo de seleccion de carpeta
        directorio_destino = filedialog.askdirectory(
            title="Guardar Como - Selecciona la carpeta destino",
            initialdir=str(Path.home() / "Documents"),
            mustexist=False
        )

        if root:
            root.destroy()

        if directorio_destino:
            return Path(directorio_destino)
        else:
            print("  No se selecciono carpeta. Guardando en directorio actual.")
            return Path.cwd() / "output_gri"
    else:
        print("\n  Archivos generados:")
        for archivo in archivos_generados:
            print(f"    - {archivo.name}")

        print("\n  Introduce la ruta donde deseas guardar los resultados")
        print("  (Presiona Enter para usar './output_gri'): ", end="")

        ruta = input().strip()

        if ruta:
            return Path(ruta)
        else:
            return Path.cwd() / "output_gri"


def copiar_resultados(origen_dir: Path, destino_dir: Path) -> list:
    """
    Copia los archivos generados al directorio destino.

    Args:
        origen_dir: Directorio con los archivos generados
        destino_dir: Directorio destino seleccionado por el usuario

    Returns:
        Lista de archivos copiados
    """
    destino_dir.mkdir(parents=True, exist_ok=True)

    archivos_copiados = []
    archivos_origen = list(origen_dir.glob("*"))

    for archivo in archivos_origen:
        if archivo.is_file():
            destino = destino_dir / archivo.name
            shutil.copy2(archivo, destino)
            archivos_copiados.append(destino)
            print(f"    Copiado: {archivo.name}")

    return archivos_copiados


def ejecutar_flujo_principal(ruta_catalogo_etfs: Path, api_keys: dict) -> tuple:
    """
    Ejecuta el flujo principal del sistema.

    Returns:
        tuple: (catalogo, df_maestro, archivos_generados)
    """
    archivos_generados = []

    # Configurar logging con las rutas correctas
    configurar_logging()

    # ========================================================================
    # PASO 1: GENERAR CATALOGO DE VARIABLES
    # ========================================================================
    print("\n[PASO 1/5] GENERANDO CATALOGO DE VARIABLES...")
    print("-"*100)

    try:
        catalogo = CatalogVariablesMacro()
        logger.info(f"Catalogo generado: {len(catalogo.catalogo_completo)} variables")

        df_dict = catalogo.exportar_diccionario_datos()
        archivos_generados.append(config.data_dir / "diccionario_datos_macro.csv")

        print(f"  Diccionario de datos exportado: {len(df_dict)} variables")
        print(f"    - Variables de mercado: {len(catalogo.variables_mercado)}")
        print(f"    - Variables macroeconomicas: {len(catalogo.variables_macro)}")
        print(f"    - Variables FX: {len(catalogo.variables_fx)}")

    except Exception as e:
        logger.error(f"Error en PASO 1: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    # ========================================================================
    # PASO 2: GENERAR MAPEO ACTIVO -> FACTORES
    # ========================================================================
    print("\n[PASO 2/5] GENERANDO MAPEO ACTIVO -> FACTORES...")
    print("-"*100)

    if ruta_catalogo_etfs:
        try:
            mapeo = MapeoActivoFactores(catalogo, ruta_catalogo_etfs)
            df_mapeo = mapeo.generar_mapeo_completo()
            archivos_generados.append(config.data_dir / "mapeo_activo_factores.csv")

            print(f"  Mapeo generado: {len(df_mapeo)} ETFs mapeados")
            print(f"    - Media variables por ETF: {df_mapeo['Num_Variables'].mean():.1f}")
            print(f"    - Min variables: {df_mapeo['Num_Variables'].min()}")
            print(f"    - Max variables: {df_mapeo['Num_Variables'].max()}")

            print("\n  Distribucion por Tipo de Activo:")
            distribucion = df_mapeo.groupby('Tipo_Activo').agg({
                'ETF_Ticker': 'count',
                'Num_Variables': 'mean'
            }).rename(columns={'ETF_Ticker': 'Num_ETFs', 'Num_Variables': 'Media_Variables'})

            for tipo, row in distribucion.iterrows():
                print(f"    - {tipo}: {int(row['Num_ETFs'])} ETFs (promedio {row['Media_Variables']:.1f} variables)")

        except Exception as e:
            logger.error(f"Error en PASO 2: {e}")
            import traceback
            traceback.print_exc()
            print("\n  Continuando sin mapeo de activos...")
    else:
        print("  PASO OMITIDO: No se proporciono catalogo de ETFs.")
        print("  Para generar el mapeo, ejecuta de nuevo con un archivo de catalogo.")

    # ========================================================================
    # PASO 3: DESCARGAR SERIES HISTORICAS
    # ========================================================================
    print("\n[PASO 3/5] DESCARGANDO SERIES HISTORICAS DESDE APIS PUBLICAS...")
    print("-"*100)

    df_maestro = None

    try:
        # Inicializar orquestador con todas las API keys
        orquestador = OrquestadorDescargaMacro(
            fred_api_key=api_keys.get('fred'),
            alpha_vantage_api_key=api_keys.get('alpha_vantage'),
            quandl_api_key=api_keys.get('quandl')
        )

        # Descargar todas las series
        df_maestro = orquestador.descargar_todas_las_series()

        print("\n  Descarga completada")
        print(f"    - Series descargadas: {len(orquestador.series_descargadas)}")
        print(f"    - Shape DataFrame maestro: {df_maestro.shape}")

        if len(df_maestro) > 0:
            print(f"    - Rango temporal: {df_maestro.index.min().strftime('%Y-%m-%d')} a {df_maestro.index.max().strftime('%Y-%m-%d')}")
            archivos_generados.append(config.data_dir / "df_maestro_variables_macro.csv")
            archivos_generados.append(config.data_dir / "df_maestro_variables_macro.pkl")
            archivos_generados.append(config.data_dir / "metadata_descarga_series.csv")

    except Exception as e:
        logger.error(f"Error en PASO 3: {e}")
        import traceback
        traceback.print_exc()
        print("\n  La descarga puede haber fallado.")
        print("  Verifica las API keys e intenta de nuevo.")

    # ========================================================================
    # PASO 4: CALCULAR GRI, INTERPRETE Y ACRI
    # ========================================================================
    print("\n[PASO 4/5] CALCULANDO GRI, INTERPRETE Y ACRI...")
    print("-"*100)

    resultados_gri = None

    if df_maestro is not None and len(df_maestro) > 0:
        try:
            # Inicializar y ejecutar el sistema GRI completo
            sistema_gri = SistemaGRI(df_maestro)
            resultados_gri = sistema_gri.ejecutar_analisis_completo()

            # Obtener senal actual
            senal_actual = sistema_gri.obtener_senal_actual()

            print(f"\n  GRI calculado exitosamente")
            print(f"    - GRI actual: {senal_actual['gri_valor']} ({senal_actual['gri_posicion']})")
            print(f"    - Decision final: {senal_actual.get('decision_final', 'N/A')}")

            # Agregar archivos generados por el sistema GRI
            archivos_gri = [
                config.data_dir / "gri_historico.csv",
                config.data_dir / "interprete_senales.csv",
                config.data_dir / "acri_historico.csv",
                config.data_dir / "ranking_acri_actual.csv"
            ]
            for archivo in archivos_gri:
                if archivo.exists():
                    archivos_generados.append(archivo)

            # Mostrar ranking ACRI
            if 'ranking_acri' in senal_actual and senal_actual['ranking_acri']:
                print("\n  Ranking ACRI actual:")
                for item in senal_actual['ranking_acri']:
                    print(f"    - {item['Categoria_L1']}: {item['Valor_Actual']:.2f} ({item['Posicion']})")

            # Generar reportes
            print("\n  Generando reportes...")
            generador = GeneradorReportes(sistema_gri)

            # Reporte texto
            reporte_txt = config.data_dir / "reporte_gri.txt"
            generador.generar_reporte_texto(reporte_txt)
            archivos_generados.append(reporte_txt)

            # Reporte HTML
            reporte_html = config.data_dir / "reporte_gri.html"
            generador.generar_reporte_html(reporte_html)
            archivos_generados.append(reporte_html)

            print(f"    - Reporte TXT: {reporte_txt.name}")
            print(f"    - Reporte HTML: {reporte_html.name}")

        except Exception as e:
            logger.error(f"Error en PASO 4 (Calculo GRI): {e}")
            import traceback
            traceback.print_exc()
            print("\n  El calculo del GRI puede haber fallado parcialmente.")
    else:
        print("  PASO OMITIDO: No hay datos descargados para calcular GRI.")

    # ========================================================================
    # PASO 5: RESUMEN
    # ========================================================================
    print("\n[PASO 5/5] PROCESO COMPLETADO")
    print("-"*100)

    print(f"\n  Archivos generados temporalmente en: {config.data_dir}")
    print(f"  Total archivos: {len(archivos_generados)}")

    return catalogo, df_maestro, archivos_generados


def main():
    """Flujo principal interactivo del sistema."""

    mostrar_bienvenida()

    # Usar directorio temporal para el proceso
    temp_dir = Path(tempfile.mkdtemp(prefix="gri_macro_"))
    config.output_dir = str(temp_dir)
    config.inicializar_directorios()

    print(f"  Directorio de trabajo temporal: {temp_dir}")

    # Paso 1: Solicitar catalogo de ETFs
    ruta_catalogo = solicitar_catalogo_etfs()
    if ruta_catalogo:
        config.ruta_catalogo_etfs = ruta_catalogo

    # Paso 2: Solicitar API keys
    api_keys = solicitar_api_keys()
    if api_keys.get('fred'):
        config.fred_api_key = api_keys['fred']

    # Confirmar ejecucion
    print("\n" + "-"*80)
    confirmar = input("¿Iniciar el proceso de descarga? (S/n): ").strip().lower()

    if confirmar in ['n', 'no']:
        print("\nProceso cancelado por el usuario.")
        # Limpiar directorio temporal
        shutil.rmtree(temp_dir, ignore_errors=True)
        sys.exit(0)

    # Ejecutar flujo principal
    catalogo, df_maestro, archivos_generados = ejecutar_flujo_principal(ruta_catalogo, api_keys)

    # Dialogo "Guardar Como" al final
    archivos_reales = [f for f in archivos_generados if f.exists()]

    if archivos_reales:
        destino_dir = dialogo_guardar_como(archivos_reales)

        print(f"\n  Guardando archivos en: {destino_dir}")
        print("-"*50)

        # Copiar archivos al destino
        archivos_copiados = copiar_resultados(config.data_dir, destino_dir)

        # Copiar logs tambien
        logs_destino = destino_dir / "logs"
        if config.logs_dir.exists():
            shutil.copytree(config.logs_dir, logs_destino, dirs_exist_ok=True)
            print(f"    Logs copiados a: {logs_destino}")

        # Mostrar resumen final
        print("\n" + "="*100)
        print("  ARCHIVOS GUARDADOS CORRECTAMENTE")
        print("="*100)
        print(f"\n  Ubicacion: {destino_dir}")
        print(f"  Total archivos: {len(archivos_copiados)}")

        # Mensaje final con dialogo
        if TKINTER_AVAILABLE:
            root = inicializar_tkinter()
            messagebox.showinfo(
                "Guardado Completado",
                f"Los archivos se han guardado correctamente en:\n\n{destino_dir}\n\n"
                f"Total: {len(archivos_copiados)} archivos"
            )
            if root:
                root.destroy()

        # Limpiar directorio temporal
        shutil.rmtree(temp_dir, ignore_errors=True)

    else:
        print("\n  ADVERTENCIA: No se generaron archivos para guardar.")
        shutil.rmtree(temp_dir, ignore_errors=True)

    print("\n" + "="*100)
    print("  PROCESO FINALIZADO")
    print("="*100)
    print(f"Tiempo de finalizacion: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*100 + "\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n  Proceso interrumpido por el usuario.")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Error fatal: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
