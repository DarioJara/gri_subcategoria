# Sistema de Descarga Automática de Variables Macro y de Mercado

## Descripción del Proyecto

Sistema automatizado para **descargar, actualizar y gestionar series históricas** de variables macroeconómicas y de mercado desde fuentes públicas (FRED, ECB, Eurostat, OECD), diseñado para alimentar el cálculo del **GRI (Global Risk Indicator)**, **Intérprete** y **ACRI**.

---

## Objetivo

Generar un proceso reproducible y auditable que:

1. **Identifique** las variables macro y de mercado relevantes para cada activo/clase de activo del universo invertible
2. **Descargue** automáticamente las series históricas desde fuentes públicas
3. **Estructure** los datos en DataFrames listos para integración con el modelo GRI
4. **Documente** la trazabilidad completa (activo → factor → fuente → ticker/ID)

---

## Marco Conceptual: GRI e Intérprete

### GRI (Global Risk Indicator)

El GRI combina dos componentes fundamentales:

```
GRI = CICLO DE MERCADO + CICLO ECONÓMICO
```

- **CICLO DE MERCADO**: Sentimiento de mercado (índices bursátiles, volatilidad implícita VIX, spreads de crédito)
- **CICLO ECONÓMICO**: Salud de la economía real (PIB, empleo, inflación, políticas monetarias)

### Intérprete

Sistema de alerta que valida el GRI mediante 3 señales:

```
INTÉRPRETE = MOMENTUM + TENDENCIA + SEASONALITY
```

- **Momentum relativo**: Crecimiento en ventanas de 90 días
- **Tendencia**: Sentimiento de expertos (análisis de noticias)
- **Seasonality**: Comportamiento histórico 25 años (patrones estacionales)

**Decisión final**: Solo cambia el perfil de riesgo si las 3 señales del intérprete coinciden.

---

## Arquitectura del Sistema

### Componentes Principales

```
┌─────────────────────────────────────────────────────────────┐
│  1. CATÁLOGO DE VARIABLES (CatalogVariablesMacro)          │
│     - 53 variables macro y de mercado                       │
│     - Metadata completa: fuente, ticker, frecuencia, etc.   │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  2. MAPEO ACTIVO → FACTORES (MapeoActivoFactores)          │
│     - 142 ETFs del universo invertible                      │
│     - Mapeo automático según clase/región/moneda            │
│     - Promedio: 12.4 variables por ETF                      │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  3. DESCARGA AUTOMATIZADA (OrquestadorDescargaMacro)       │
│     - FRED (Federal Reserve Economic Data)                  │
│     - Yahoo Finance (índices bursátiles)                    │
│     - ECB / OECD (futuro)                                   │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  4. OUTPUTS                                                 │
│     - DataFrame maestro (CSV + Pickle)                      │
│     - Diccionario de datos                                  │
│     - Mapeo activo-factores                                 │
│     - Metadata de descarga                                  │
└─────────────────────────────────────────────────────────────┘
```

### Distribución de Variables

El sistema gestiona **53 variables** catalogadas:

- **24 variables de MERCADO** (Ciclo de Mercado):
  - Índices bursátiles (S&P 500, NASDAQ, STOXX 600, MSCI World/EM)
  - Volatilidad (VIX, VSTOXX, MOVE Index)
  - Curva de tipos USA (3M, 2Y, 5Y, 10Y, 30Y)
  - Spreads de curva (10Y-2Y, 10Y-3M)
  - Spreads de crédito (IG/HY USA/EUR, EM spreads)
  - Curva de tipos Eurozona (Bund 2Y, 10Y)
  - Índices de condiciones financieras

- **25 variables MACROECONÓMICAS** (Ciclo Económico):
  - **USA**: GDP, CFNAI, ISM Manufacturing/Services, Industrial Production, Retail Sales
  - **Inflación USA**: CPI, Core CPI, PCE, Core PCE, Breakeven Inflation 5Y/5Y5Y
  - **Empleo USA**: Unemployment Rate, Non-Farm Payrolls, Initial Claims
  - **Política Monetaria**: Fed Funds Rate, ECB Deposit Rate
  - **Eurozona**: GDP, PMI Manufacturing/Services, HICP, Core HICP, Unemployment
  - **China/Asia**: GDP, PMI Manufacturing

- **4 variables de FX**:
  - EUR/USD, GBP/USD, USD/JPY, USD/CHF

---

## Instalación

### 1. Requisitos del Sistema

- **Python**: 3.8 o superior
- **Sistema Operativo**: Windows, macOS, Linux

### 2. Instalar Dependencias

```bash
pip install -r requirements.txt
```

**Librerías principales**:
- `pandas`, `numpy`: Manipulación de datos
- `pandas-datareader`: Acceso a FRED, Yahoo Finance, World Bank
- `fredapi`: Cliente oficial de FRED (recomendado)
- `yfinance`: Descarga de índices bursátiles
- `openpyxl`: Lectura de archivos Excel

### 3. Obtener API Key de FRED (GRATUITA Y OBLIGATORIA)

FRED (Federal Reserve Economic Data) es la fuente principal de datos. Requiere API key gratuita:

1. **Registrarse** en FRED: https://fredaccount.stlouisfed.org/apikeys
2. **Solicitar API Key** (proceso instantáneo)
3. **Copiar** la API key generada (ejemplo: `a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6`)

### 4. Configurar API Key

**Opción A: Variable de entorno** (recomendado):
```bash
# Windows
set FRED_API_KEY=tu_api_key_aqui

# Linux/macOS
export FRED_API_KEY=tu_api_key_aqui
```

**Opción B: Editar directamente en el código**:
```python
# En Mod_Descarga_API_Publica.py, línea ~450
FRED_API_KEY = "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6"  # Tu API key aquí
```

---

## Uso Básico

### Paso 1: Generar Catálogo y Mapeo (sin descarga)

```python
from Mod_GRI_MacroEconomicos import CatalogVariablesMacro, MapeoActivoFactores

# 1. Inicializar catálogo de variables
catalogo = CatalogVariablesMacro()

# 2. Exportar diccionario de datos
df_diccionario = catalogo.exportar_diccionario_datos()
print(df_diccionario.head(10))

# 3. Generar mapeo Activo → Factores
mapeo = MapeoActivoFactores(catalogo)
df_mapeo = mapeo.generar_mapeo_completo()
print(df_mapeo.head(10))
```

**Outputs generados**:
- `2.-Output/data/diccionario_datos_macro.csv`: Metadata de las 53 variables
- `2.-Output/data/mapeo_activo_factores.csv`: Mapeo de 142 ETFs a factores

### Paso 2: Descargar Series Históricas

```python
from Mod_Descarga_API_Publica import OrquestadorDescargaMacro

# 1. Inicializar orquestador (con tu API key de FRED)
orquestador = OrquestadorDescargaMacro(fred_api_key="TU_API_KEY_AQUI")

# 2. Descargar todas las series
df_maestro = orquestador.descargar_todas_las_series()

# 3. Ver resumen
print(f"Shape: {df_maestro.shape}")
print(f"Rango: {df_maestro.index.min()} a {df_maestro.index.max()}")
print(df_maestro.head())
```

**Outputs generados**:
- `2.-Output/data/df_maestro_variables_macro.csv`: DataFrame maestro (todas las series)
- `2.-Output/data/df_maestro_variables_macro.pkl`: DataFrame en formato pickle (más eficiente)
- `2.-Output/data/metadata_descarga_series.csv`: Metadata de la descarga (auditoría)

### Paso 3: Actualizar Series Existentes

```python
# Actualiza solo datos nuevos (incremental)
df_actualizado = orquestador.actualizar_series_existentes()
```

---

## Estructura de Outputs

### 1. Diccionario de Datos (`diccionario_datos_macro.csv`)

Documentación completa de cada variable:

| Codigo_Variable | Nombre | Descripcion | Fuente | Ticker_ID | Frecuencia | Unidad | Transformacion | Relevancia_GRI | Asset_Classes |
|----------------|--------|-------------|--------|-----------|------------|--------|----------------|----------------|---------------|
| US_VIX | VIX - CBOE Volatility Index | Índice de volatilidad implícita S&P 500 | FRED | VIXCLS | D | Index | momentum_negative | Ciclo de Mercado - Indicador CLAVE de miedo/estrés | Global Risk Indicator |
| US_CFNAI | Chicago Fed National Activity Index | Índice de actividad económica USA | FRED | CFNAIMA3 | M | Index | momentum | Ciclo Económico - INDICADOR PRINCIPAL GRI (CFNAI 2.1) | Global Risk Indicator |

**Frecuencias**:
- `D`: Diaria
- `W`: Semanal
- `M`: Mensual
- `Q`: Trimestral

**Transformaciones**:
- `None`: Sin transformación (nivel)
- `momentum`: Retornos logarítmicos (log-diferencias)
- `momentum_negative`: Momentum invertido (para VIX, spreads - ↑ riesgo = ↓ GRI)
- `yoy_pct`: Variación interanual en %
- `mom_change`: Variación mensual

### 2. Mapeo Activo-Factores (`mapeo_activo_factores.csv`)

Para cada ETF, lista las variables relevantes:

| ETF_Ticker | ETF_Nombre | Tipo_Activo | Zona_Geografica | Moneda | Clasificacion_L1 | Variables_Asignadas | Num_Variables |
|-----------|------------|-------------|-----------------|--------|------------------|---------------------|---------------|
| ESGE.PA | Amundi MSCI Europe ESG Leaders | Equities | Europe | EUR | Renta Variable EUR | EU_STOXX600, EU_VSTOXX, EU_GDP, EU_PMI_MANUFACTURING, ... | 16 |
| VECA.DE | Vanguard EUR Corporate Bond | Fixed Income | Europe | EUR | Renta Fija Corporativa EUR | EU_CREDIT_IG_SPREAD, EU_YIELD_10Y, EU_PMI_MANUFACTURING, ... | 10 |

### 3. DataFrame Maestro (`df_maestro_variables_macro.csv`)

Serie temporal con todas las variables:

| Fecha | US_SP500 | US_VIX | US_YIELD_10Y | EU_HICP | FX_EURUSD | ... |
|-------|----------|--------|--------------|---------|-----------|-----|
| 2000-01-03 | 1455.22 | 24.21 | 6.58 | 85.3 | 1.0046 | ... |
| 2000-01-04 | 1399.42 | 25.89 | 6.49 | 85.3 | 1.0008 | ... |
| ... | ... | ... | ... | ... | ... | ... |
| 2025-11-19 | 5894.32 | 14.52 | 4.41 | 118.2 | 1.0572 | ... |

**Características**:
- Index: `Fecha` (datetime)
- Columnas: Códigos de variables (ej: `US_VIX`, `EU_GDP`, etc.)
- Valores: Nivel original de la serie (sin transformaciones aplicadas)
- Cobertura: Hasta 25 años históricos (cuando disponible)

### 4. Metadata de Descarga (`metadata_descarga_series.csv`)

Registro de auditoría de cada descarga:

| Codigo | Nombre | Fuente | Ticker | Fecha_Descarga | Fecha_Inicio_Datos | Fecha_Fin_Datos | Num_Observaciones | Valores_Nulos | Pct_Nulos | Valor_Medio | Valor_Min | Valor_Max |
|--------|--------|--------|--------|----------------|-------------------|-----------------|-------------------|---------------|-----------|-------------|-----------|-----------|
| US_VIX | VIX Index | FRED | VIXCLS | 2025-11-19 17:30:00 | 1990-01-02 | 2025-11-18 | 8978 | 0 | 0.0% | 19.23 | 9.14 | 82.69 |

---

## Ejemplos de Uso Avanzado

### Ejemplo 1: Filtrar Variables por Asset Class

```python
from Mod_GRI_MacroEconomicos import CatalogVariablesMacro

catalogo = CatalogVariablesMacro()

# Obtener variables para Renta Fija High Yield
vars_hy = catalogo.get_variables_por_asset_class('Renta Fija High Yield')

print(f"Variables para High Yield: {len(vars_hy)}")
for codigo, metadata in vars_hy.items():
    print(f"  - {codigo}: {metadata['nombre']}")
```

### Ejemplo 2: Descargar Solo Una Variable Específica

```python
from Mod_Descarga_API_Publica import DescargadorFRED

# Inicializar cliente FRED
fred = DescargadorFRED(api_key="TU_API_KEY")

# Descargar solo el VIX
vix = fred.descargar_serie(
    ticker='VIXCLS',
    nombre_serie='VIX Index'
)

print(vix.tail(10))
```

### Ejemplo 3: Integración con Cálculo del GRI

```python
import pandas as pd
from Mod_Descarga_API_Publica import OrquestadorDescargaMacro

# 1. Descargar datos
orquestador = OrquestadorDescargaMacro(fred_api_key="TU_API_KEY")
df_maestro = orquestador.descargar_todas_las_series()

# 2. Calcular Momentum del VIX (para GRI)
df_maestro['VIX_Momentum'] = np.log(df_maestro['US_VIX']) - np.log(df_maestro['US_VIX'].shift(1))
df_maestro['VIX_Momentum_Negative'] = -df_maestro['VIX_Momentum']  # Invertir

# 3. Aplicar filtro lowpass (Butterworth) y media móvil
from scipy.signal import butter, filtfilt

def apply_lowpass(serie, cutoff=40):
    b, a = butter(2, 1/cutoff, btype='low')
    return filtfilt(b, a, serie.fillna(method='ffill'))

vix_filtered = apply_lowpass(df_maestro['VIX_Momentum_Negative'].values, cutoff=40)
vix_ma = pd.Series(vix_filtered).rolling(40).mean()

# 4. Normalizar (2-sided incremental, 252 días)
vix_normalized = vix_ma / vix_ma.rolling(252).std()

print("VIX procesado para GRI:")
print(vix_normalized.tail(10))
```

---

## FAQ y Troubleshooting

### ¿Por qué no se descargan todas las series?

**Problema**: Solo se descargan algunas variables.

**Causa**: Sin API key de FRED, `pandas_datareader` tiene limitaciones.

**Solución**: Obtén una API key gratuita de FRED (ver sección Instalación).

### ¿Cómo añadir nuevas variables?

1. Editar `Mod_GRI_MacroEconomicos.py`
2. Añadir la variable en `_definir_variables_mercado()` o `_definir_variables_macro()`
3. Especificar: ticker, fuente, frecuencia, transformación, asset_classes
4. Ejecutar de nuevo el sistema

**Ejemplo**:
```python
'US_LEADING_INDICATORS': {
    'nombre': 'US Leading Economic Indicators',
    'descripcion': 'Índice de indicadores adelantados',
    'fuente': 'FRED',
    'ticker': 'USSLIND',
    'frecuencia': 'M',
    'unidad': 'Index',
    'transformacion': 'yoy_pct',
    'relevancia_gri': 'Ciclo Económico - Indicador adelantado',
    'asset_classes': ['Global Risk Indicator']
}
```

### ¿Cómo gestionar series con datos faltantes?

El sistema **no rellena artificialmente** datos faltantes para mantener integridad.

**Recomendaciones**:
- Usar `.fillna(method='ffill')` (forward fill) para festivos/fines de semana
- Usar interpolación lineal para gaps pequeños (<5 días)
- Documentar cualquier transformación aplicada

### ¿Cómo acelerar las descargas?

1. **Usar fredapi**: Más rápido que `pandas_datareader`
2. **Reducir delay**: En `descargar_multiples_series(delay_segundos=0.01)`
3. **Descarga incremental**: Usar `actualizar_series_existentes()` en lugar de descargar todo
4. **Formato pickle**: Cargar `.pkl` es 10x más rápido que `.csv`

### Error: 'charmap' codec can't encode character

**Causa**: Problemas de encoding en Windows.

**Solución**: Ya está resuelto en el código usando `encoding='utf-8-sig'` en todos los CSV.

---

## Roadmap y Futuras Mejoras

- [ ] **Descarga desde ECB** (European Central Bank Statistical Data Warehouse)
- [ ] **Descarga desde OECD** (OECD.Stat)
- [ ] **Descarga desde Eurostat** (datos europeos detallados)
- [ ] **Soporte para Quandl/Nasdaq Data Link** (datos alternativos)
- [ ] **Cálculo automático de transformaciones** (momentum, normalization, filters)
- [ ] **Dashboard interactivo** (Streamlit/Dash) para visualizar series
- [ ] **Alertas automáticas** cuando GRI cambia de régimen
- [ ] **Backtesting del GRI** con datos históricos
- [ ] **API REST** para integración con otros sistemas

---

## Licencia y Contacto

**Proyecto**: Sistema GRI - Descarga Automática de Variables Macro
**Cliente**: Creand Asset Management
**Fecha**: Noviembre 2025
**Versión**: 1.0

**Documentación de referencia**:
- FRED API Documentation: https://fred.stlouisfed.org/docs/api/
- pandas-datareader: https://pandas-datareader.readthedocs.io/
- yfinance: https://github.com/ranaroussi/yfinance

---

## Anexo: Lista Completa de Variables

### Variables de Mercado (24)

**Índices Bursátiles**:
- `US_SP500`: S&P 500 Index
- `US_NASDAQ`: NASDAQ Composite
- `US_RUSSELL2000`: Russell 2000
- `EU_STOXX600`: STOXX Europe 600
- `GLOBAL_MSCI_WORLD`: MSCI World
- `EM_MSCI_EM`: MSCI Emerging Markets

**Volatilidad**:
- `US_VIX`: CBOE Volatility Index (Fear Index)
- `EU_VSTOXX`: Euro STOXX 50 Volatility
- `US_MOVE`: ICE BofA MOVE Index (bond volatility)

**Curva de Tipos USA**:
- `US_YIELD_3M`: Treasury 3-Month
- `US_YIELD_2Y`: Treasury 2-Year
- `US_YIELD_5Y`: Treasury 5-Year
- `US_YIELD_10Y`: Treasury 10-Year (benchmark)
- `US_YIELD_30Y`: Treasury 30-Year

**Spreads de Curva**:
- `US_SPREAD_10Y2Y`: 10Y-2Y Spread (predictor recesión)
- `US_SPREAD_10Y3M`: 10Y-3M Spread

**Spreads de Crédito**:
- `US_CREDIT_IG_SPREAD`: ICE BofA US Corporate IG OAS
- `US_CREDIT_HY_SPREAD`: ICE BofA US High Yield OAS
- `EU_CREDIT_IG_SPREAD`: ICE BofA Euro Corporate IG OAS
- `EU_CREDIT_HY_SPREAD`: ICE BofA Euro High Yield OAS
- `EM_CREDIT_SPREAD`: JPM EMBI Global Spread

**Curva Eurozona**:
- `EU_YIELD_2Y`: German Bund 2-Year
- `EU_YIELD_10Y`: German Bund 10-Year

**Condiciones Financieras**:
- `US_FINANCIAL_CONDITIONS`: Chicago Fed NFCI

### Variables Macroeconómicas (25)

**Actividad - USA**:
- `US_GDP`: Real GDP
- `US_CFNAI`: Chicago Fed National Activity Index (CLAVE GRI)
- `US_ISM_MANUFACTURING`: ISM Manufacturing PMI
- `US_ISM_SERVICES`: ISM Services PMI
- `US_INDUSTRIAL_PRODUCTION`: Industrial Production Index
- `US_RETAIL_SALES`: Retail Sales

**Inflación - USA**:
- `US_CPI`: Consumer Price Index
- `US_CORE_CPI`: Core CPI
- `US_PCE`: PCE Price Index
- `US_CORE_PCE`: Core PCE (objetivo Fed)
- `US_INFLATION_EXPECTATIONS_5Y`: 5-Year Breakeven
- `US_INFLATION_EXPECTATIONS_5Y5Y`: 5Y5Y Forward

**Empleo - USA**:
- `US_UNEMPLOYMENT_RATE`: Unemployment Rate
- `US_NONFARM_PAYROLLS`: Non-Farm Payrolls
- `US_INITIAL_CLAIMS`: Initial Unemployment Claims

**Política Monetaria**:
- `US_FED_FUNDS_RATE`: Federal Funds Rate
- `EU_ECB_DEPOSIT_RATE`: ECB Deposit Facility Rate

**Eurozona**:
- `EU_GDP`: Real GDP
- `EU_PMI_MANUFACTURING`: Manufacturing PMI
- `EU_PMI_SERVICES`: Services PMI
- `EU_HICP`: Harmonized Index of Consumer Prices
- `EU_CORE_HICP`: Core HICP
- `EU_UNEMPLOYMENT_RATE`: Unemployment Rate

**Asia/EM**:
- `CN_GDP`: China Real GDP
- `CN_PMI_MANUFACTURING`: China Manufacturing PMI

### Variables FX (4)

- `FX_EURUSD`: EUR/USD Exchange Rate
- `FX_GBPUSD`: GBP/USD Exchange Rate
- `FX_USDJPY`: USD/JPY Exchange Rate
- `FX_USDCHF`: USD/CHF Exchange Rate

---

**Total: 53 variables catalogadas y listas para descarga automática**
