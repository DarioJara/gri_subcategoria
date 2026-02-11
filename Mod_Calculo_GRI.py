"""
MODULO DE CALCULO DEL GRI, INTERPRETE Y ACRI
=============================================

Este modulo implementa el calculo del Global Risk Indicator (GRI),
el Interprete y el Asset Class Risk Indicator (ACRI) segun la metodologia
descrita en la documentacion.

Componentes:
    - GRI = Ciclo de Mercado + Ciclo Economico (basado en CFNAI 2.1)
    - Interprete = Momentum + Tendencia + Seasonality
    - ACRI = GRI por clase de activo

Autor: Sistema Automatizado GRI
Fecha: 2025-01-19
Version: 1.0
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional, Union
from pathlib import Path
import logging
import warnings
warnings.filterwarnings('ignore')

from config import config

# Configurar logging
logger = logging.getLogger(__name__)


# ============================================================================
# CONSTANTES Y CONFIGURACION
# ============================================================================

# Umbrales para clasificacion de posicion del GRI
class UmbralesGRI:
    """Umbrales para clasificacion del GRI."""
    AGRESIVO = 0.0       # GRI > 0 = Agresivo
    DEFENSIVO = 0.0      # GRI < 0 = Defensivo
    NEUTRAL_SUPERIOR = 0.1
    NEUTRAL_INFERIOR = -0.1


# Umbrales para ACRI (Asset Class Risk Indicator)
class UmbralesACRI:
    """Umbrales para clasificacion del ACRI por clase de activo."""
    VERY_OVERWEIGHT = 0.60    # > 0.60 = OW+
    OVERWEIGHT = 0.20         # > 0.20 = OW
    NEUTRAL_SUPERIOR = 0.20   # -0.20 a 0.20 = N
    NEUTRAL_INFERIOR = -0.20
    UNDERWEIGHT = -0.20       # < -0.20 = UW
    VERY_UNDERWEIGHT = -0.60  # < -0.60 = UW-


# Mapeo de posiciones a valores numericos
POSICION_A_VALOR = {
    'OW+': 0.80,
    'OW': 0.40,
    'N': 0.00,
    'UW': -0.40,
    'UW-': -0.80
}

VALOR_A_POSICION = {
    0.80: 'OW+',
    0.40: 'OW',
    0.00: 'N',
    -0.40: 'UW',
    -0.80: 'UW-'
}


# ============================================================================
# CLASE PRINCIPAL: CALCULADOR GRI
# ============================================================================

class CalculadorGRI:
    """
    Calcula el Global Risk Indicator (GRI) combinando:
        - Ciclo de Mercado: indices, volatilidad, spreads de credito
        - Ciclo Economico: CFNAI, PIB, empleo, inflacion

    El GRI indica si el entorno favorece tomar mas o menos riesgo:
        - GRI > 0: Posicion AGRESIVA (risk-on)
        - GRI < 0: Posicion DEFENSIVA (risk-off)
    """

    def __init__(self, df_datos: pd.DataFrame):
        """
        Inicializa el calculador con los datos descargados.

        Args:
            df_datos: DataFrame con las series macro y de mercado
        """
        self.df = df_datos.copy()
        self.gri_series = None
        self.ciclo_mercado = None
        self.ciclo_economico = None

        logger.info(f"CalculadorGRI inicializado con {len(self.df)} observaciones")

    # ========================================================================
    # CICLO DE MERCADO
    # ========================================================================

    def calcular_ciclo_mercado(self) -> pd.Series:
        """
        Calcula el componente de Ciclo de Mercado del GRI.

        Variables utilizadas:
            - VIX (volatilidad - invertido)
            - Spreads de credito IG y HY (invertidos)
            - Indices bursatiles (momentum)
            - Spread de curva 10Y-2Y

        Returns:
            Serie con el indicador de Ciclo de Mercado normalizado [-1, 1]
        """
        logger.info("Calculando Ciclo de Mercado...")

        componentes = []
        pesos = []

        # 1. VIX - Volatilidad (invertido: alto VIX = riesgo)
        if 'US_VIX' in self.df.columns:
            vix = self.df['US_VIX'].dropna()
            if len(vix) > 0:
                vix_z = self._calcular_zscore_rolling(vix, window=252)
                vix_signal = -vix_z  # Invertir: alto VIX = senal negativa
                componentes.append(('VIX', vix_signal, 0.25))
                logger.info(f"  - VIX: {len(vix_signal)} obs")

        # 2. Spread HY (invertido: alto spread = riesgo)
        if 'US_CREDIT_HY_SPREAD' in self.df.columns:
            hy_spread = self.df['US_CREDIT_HY_SPREAD'].dropna()
            if len(hy_spread) > 0:
                hy_z = self._calcular_zscore_rolling(hy_spread, window=252)
                hy_signal = -hy_z  # Invertir
                componentes.append(('HY_Spread', hy_signal, 0.20))
                logger.info(f"  - HY Spread: {len(hy_signal)} obs")

        # 3. Spread IG (invertido)
        if 'US_CREDIT_IG_SPREAD' in self.df.columns:
            ig_spread = self.df['US_CREDIT_IG_SPREAD'].dropna()
            if len(ig_spread) > 0:
                ig_z = self._calcular_zscore_rolling(ig_spread, window=252)
                ig_signal = -ig_z
                componentes.append(('IG_Spread', ig_signal, 0.15))
                logger.info(f"  - IG Spread: {len(ig_signal)} obs")

        # 4. Spread curva 10Y-2Y (positivo = expansivo)
        if 'US_SPREAD_10Y2Y' in self.df.columns:
            spread_curva = self.df['US_SPREAD_10Y2Y'].dropna()
            if len(spread_curva) > 0:
                curva_z = self._calcular_zscore_rolling(spread_curva, window=252)
                componentes.append(('Curva_10Y2Y', curva_z, 0.15))
                logger.info(f"  - Curva 10Y-2Y: {len(curva_z)} obs")

        # 5. S&P 500 momentum (retorno 6 meses)
        if 'US_SP500' in self.df.columns:
            sp500 = self.df['US_SP500'].dropna()
            if len(sp500) > 126:  # 6 meses
                sp500_mom = sp500.pct_change(126)  # Retorno 6 meses
                sp500_z = self._calcular_zscore_rolling(sp500_mom, window=252)
                componentes.append(('SP500_Mom', sp500_z, 0.15))
                logger.info(f"  - S&P 500 Momentum: {len(sp500_z)} obs")

        # 6. Financial Conditions Index (invertido si >0 = restrictivo)
        if 'US_FINANCIAL_CONDITIONS' in self.df.columns:
            nfci = self.df['US_FINANCIAL_CONDITIONS'].dropna()
            if len(nfci) > 0:
                nfci_signal = -nfci  # NFCI > 0 significa condiciones restrictivas
                nfci_z = self._calcular_zscore_rolling(nfci_signal, window=52)
                componentes.append(('NFCI', nfci_z, 0.10))
                logger.info(f"  - NFCI: {len(nfci_z)} obs")

        # Combinar componentes
        if componentes:
            self.ciclo_mercado = self._combinar_componentes(componentes)
            logger.info(f"Ciclo de Mercado calculado: {len(self.ciclo_mercado)} obs")
            return self.ciclo_mercado
        else:
            logger.warning("No se pudieron calcular componentes del Ciclo de Mercado")
            return pd.Series(dtype=float)

    # ========================================================================
    # CICLO ECONOMICO
    # ========================================================================

    def calcular_ciclo_economico(self) -> pd.Series:
        """
        Calcula el componente de Ciclo Economico del GRI.

        Variable principal: CFNAI (Chicago Fed National Activity Index)
        Variables complementarias: ISM, desempleo, produccion industrial

        Returns:
            Serie con el indicador de Ciclo Economico normalizado [-1, 1]
        """
        logger.info("Calculando Ciclo Economico...")

        componentes = []

        # 1. CFNAI - Indicador PRINCIPAL (CFNAI 2.1)
        if 'US_CFNAI' in self.df.columns:
            cfnai = self.df['US_CFNAI'].dropna()
            if len(cfnai) > 0:
                # CFNAI ya esta en forma de z-score (media 0)
                # Valores > 0 indican crecimiento por encima de tendencia
                cfnai_signal = cfnai.clip(-3, 3) / 3  # Normalizar a [-1, 1]
                componentes.append(('CFNAI', cfnai_signal, 0.40))
                logger.info(f"  - CFNAI: {len(cfnai_signal)} obs (peso 40%)")

        # 2. ISM Manufacturing PMI
        if 'US_ISM_MANUFACTURING' in self.df.columns:
            ism = self.df['US_ISM_MANUFACTURING'].dropna()
            if len(ism) > 0:
                # ISM: >50 = expansion, <50 = contraccion
                ism_signal = (ism - 50) / 15  # Normalizar aprox [-1, 1]
                ism_signal = ism_signal.clip(-1, 1)
                componentes.append(('ISM_Mfg', ism_signal, 0.20))
                logger.info(f"  - ISM Manufacturing: {len(ism_signal)} obs")

        # 3. Tasa de desempleo (invertido: alto desempleo = malo)
        if 'US_UNEMPLOYMENT_RATE' in self.df.columns:
            unemp = self.df['US_UNEMPLOYMENT_RATE'].dropna()
            if len(unemp) > 0:
                # Calcular cambio vs promedio historico
                unemp_z = self._calcular_zscore_rolling(unemp, window=520)  # ~2 anos
                unemp_signal = -unemp_z  # Invertir
                componentes.append(('Unemployment', unemp_signal, 0.15))
                logger.info(f"  - Unemployment: {len(unemp_signal)} obs")

        # 4. Produccion Industrial (YoY)
        if 'US_INDUSTRIAL_PRODUCTION' in self.df.columns:
            indpro = self.df['US_INDUSTRIAL_PRODUCTION'].dropna()
            if len(indpro) > 12:
                indpro_yoy = indpro.pct_change(12) * 100  # YoY %
                indpro_z = self._calcular_zscore_rolling(indpro_yoy, window=120)
                componentes.append(('IndPro', indpro_z, 0.15))
                logger.info(f"  - Industrial Production: {len(indpro_z)} obs")

        # 5. Initial Claims (invertido)
        if 'US_INITIAL_CLAIMS' in self.df.columns:
            claims = self.df['US_INITIAL_CLAIMS'].dropna()
            if len(claims) > 0:
                claims_z = self._calcular_zscore_rolling(claims, window=52)
                claims_signal = -claims_z  # Invertir
                componentes.append(('InitialClaims', claims_signal, 0.10))
                logger.info(f"  - Initial Claims: {len(claims_signal)} obs")

        # Combinar componentes
        if componentes:
            self.ciclo_economico = self._combinar_componentes(componentes)
            logger.info(f"Ciclo Economico calculado: {len(self.ciclo_economico)} obs")
            return self.ciclo_economico
        else:
            logger.warning("No se pudieron calcular componentes del Ciclo Economico")
            return pd.Series(dtype=float)

    # ========================================================================
    # CALCULO GRI PRINCIPAL
    # ========================================================================

    def calcular_gri(self, peso_mercado: float = 0.5, peso_economico: float = 0.5) -> pd.Series:
        """
        Calcula el GRI combinando Ciclo de Mercado y Ciclo Economico.

        GRI = peso_mercado * Ciclo_Mercado + peso_economico * Ciclo_Economico

        Args:
            peso_mercado: Peso del componente de mercado (default 0.5)
            peso_economico: Peso del componente economico (default 0.5)

        Returns:
            Serie con el GRI normalizado aproximadamente en [-1, 1]
        """
        logger.info("="*80)
        logger.info("CALCULANDO GRI (Global Risk Indicator)")
        logger.info("="*80)

        # Calcular componentes si no existen
        if self.ciclo_mercado is None:
            self.calcular_ciclo_mercado()

        if self.ciclo_economico is None:
            self.calcular_ciclo_economico()

        # Verificar que tenemos datos
        if self.ciclo_mercado is None or len(self.ciclo_mercado) == 0:
            logger.error("No hay datos de Ciclo de Mercado")
            return pd.Series(dtype=float)

        if self.ciclo_economico is None or len(self.ciclo_economico) == 0:
            logger.error("No hay datos de Ciclo Economico")
            return pd.Series(dtype=float)

        # Alinear indices
        df_combinado = pd.DataFrame({
            'Ciclo_Mercado': self.ciclo_mercado,
            'Ciclo_Economico': self.ciclo_economico
        }).dropna()

        if len(df_combinado) == 0:
            logger.error("No hay datos comunes entre Ciclo de Mercado y Economico")
            return pd.Series(dtype=float)

        # Calcular GRI
        self.gri_series = (
            peso_mercado * df_combinado['Ciclo_Mercado'] +
            peso_economico * df_combinado['Ciclo_Economico']
        )

        # Normalizar a [-1, 1] aprox
        self.gri_series = self.gri_series.clip(-1, 1)

        logger.info(f"\nGRI calculado:")
        logger.info(f"  - Observaciones: {len(self.gri_series)}")
        logger.info(f"  - Rango: [{self.gri_series.min():.3f}, {self.gri_series.max():.3f}]")
        logger.info(f"  - Valor actual: {self.gri_series.iloc[-1]:.3f}")
        logger.info(f"  - Posicion actual: {self.clasificar_posicion_gri(self.gri_series.iloc[-1])}")

        return self.gri_series

    def clasificar_posicion_gri(self, valor: float) -> str:
        """Clasifica el valor del GRI en Agresivo/Neutral/Defensivo."""
        if valor > UmbralesGRI.NEUTRAL_SUPERIOR:
            return "AGRESIVO"
        elif valor < UmbralesGRI.NEUTRAL_INFERIOR:
            return "DEFENSIVO"
        else:
            return "NEUTRAL"

    # ========================================================================
    # METODOS AUXILIARES
    # ========================================================================

    def _calcular_zscore_rolling(self, serie: pd.Series, window: int = 252) -> pd.Series:
        """Calcula z-score rolling de una serie."""
        media = serie.rolling(window=window, min_periods=window//2).mean()
        std = serie.rolling(window=window, min_periods=window//2).std()
        zscore = (serie - media) / std
        return zscore.clip(-3, 3)  # Limitar outliers

    def _combinar_componentes(
        self,
        componentes: List[Tuple[str, pd.Series, float]]
    ) -> pd.Series:
        """
        Combina multiples componentes con sus pesos.

        Args:
            componentes: Lista de tuplas (nombre, serie, peso)

        Returns:
            Serie combinada ponderada
        """
        # Crear DataFrame con todos los componentes
        df_comp = pd.DataFrame()
        pesos_dict = {}

        for nombre, serie, peso in componentes:
            df_comp[nombre] = serie
            pesos_dict[nombre] = peso

        # Normalizar pesos para que sumen 1
        peso_total = sum(pesos_dict.values())
        pesos_norm = {k: v/peso_total for k, v in pesos_dict.items()}

        # Calcular promedio ponderado
        resultado = pd.Series(0.0, index=df_comp.index)
        for col in df_comp.columns:
            # Usar interpolacion para valores faltantes
            serie_interpolada = df_comp[col].interpolate(method='time', limit=5)
            resultado += pesos_norm[col] * serie_interpolada.fillna(0)

        return resultado


# ============================================================================
# CLASE: INTERPRETE
# ============================================================================

class Interprete:
    """
    Implementa el Interprete que corrige las senales del GRI.

    Componentes:
        - Momentum relativo: crecimiento de fundamentales en ventanas de 90 dias
        - Tendencia: analisis de sentimiento (simplificado sin NLP)
        - Seasonality: comportamiento historico mes a mes (25 anos)

    Regla de decision:
        - Solo cambia posicion si las 3 senales coinciden
        - Si solo coinciden 2, mantiene la senal del GRI
    """

    def __init__(self, df_datos: pd.DataFrame, gri_series: pd.Series):
        """
        Inicializa el Interprete.

        Args:
            df_datos: DataFrame con las series macro y de mercado
            gri_series: Serie del GRI calculado
        """
        self.df = df_datos.copy()
        self.gri = gri_series.copy()

        self.momentum = None
        self.tendencia = None
        self.seasonality = None
        self.senal_final = None

        logger.info("Interprete inicializado")

    def calcular_momentum(self, ventana: int = 90) -> pd.Series:
        """
        Calcula el Momentum relativo del GRI.

        Mide si el mercado esta creciendo en sus fundamentales
        a menor ritmo que antes (ventanas de 90 dias).

        Args:
            ventana: Numero de dias para calcular momentum (default 90)

        Returns:
            Serie con senal de momentum: 1 (positivo), -1 (negativo), 0 (neutral)
        """
        logger.info(f"Calculando Momentum (ventana {ventana} dias)...")

        if len(self.gri) < ventana:
            logger.warning(f"Datos insuficientes para momentum (min {ventana})")
            return pd.Series(dtype=float)

        # Calcular cambio del GRI en la ventana
        momentum_raw = self.gri.diff(ventana)

        # Calcular aceleracion (derivada segunda)
        aceleracion = momentum_raw.diff(ventana // 2)

        # Combinar momentum y aceleracion
        momentum_score = (
            0.6 * self._normalizar_serie(momentum_raw) +
            0.4 * self._normalizar_serie(aceleracion)
        )

        # Clasificar senal
        self.momentum = momentum_score.apply(self._clasificar_senal_momentum)

        ultimo_valor = self.momentum.dropna().iloc[-1] if len(self.momentum.dropna()) > 0 else 0
        logger.info(f"  Momentum actual: {self._senal_a_texto(ultimo_valor)}")

        return self.momentum

    def calcular_tendencia(self) -> pd.Series:
        """
        Calcula la Tendencia usando indicadores tecnicos.

        Nota: La implementacion completa usaria NLP (FinBERT) para analizar
        noticias. Esta version simplificada usa indicadores tecnicos como proxy.

        Returns:
            Serie con senal de tendencia: 1 (alcista), -1 (bajista), 0 (neutral)
        """
        logger.info("Calculando Tendencia...")

        componentes = []

        # 1. Tendencia del GRI (media movil)
        if len(self.gri) > 50:
            gri_ma50 = self.gri.rolling(50).mean()
            gri_ma200 = self.gri.rolling(200).mean()

            # Senal: GRI sobre/bajo sus medias
            tendencia_gri = pd.Series(0, index=self.gri.index)
            tendencia_gri[self.gri > gri_ma50] = 0.5
            tendencia_gri[self.gri > gri_ma200] += 0.5
            tendencia_gri[self.gri < gri_ma50] = -0.5
            tendencia_gri[self.gri < gri_ma200] -= 0.5

            componentes.append(tendencia_gri)

        # 2. Tendencia de spreads de credito (direccion)
        if 'US_CREDIT_HY_SPREAD' in self.df.columns:
            hy = self.df['US_CREDIT_HY_SPREAD'].dropna()
            if len(hy) > 50:
                hy_ma = hy.rolling(50).mean()
                tendencia_hy = pd.Series(0, index=hy.index)
                tendencia_hy[hy < hy_ma] = 1  # Spread bajando = positivo
                tendencia_hy[hy > hy_ma] = -1
                componentes.append(tendencia_hy)

        # 3. Tendencia del VIX
        if 'US_VIX' in self.df.columns:
            vix = self.df['US_VIX'].dropna()
            if len(vix) > 50:
                vix_ma = vix.rolling(50).mean()
                tendencia_vix = pd.Series(0, index=vix.index)
                tendencia_vix[vix < vix_ma] = 1  # VIX bajando = positivo
                tendencia_vix[vix > vix_ma] = -1
                componentes.append(tendencia_vix)

        # Combinar componentes
        if componentes:
            df_tend = pd.DataFrame(componentes).T
            tendencia_raw = df_tend.mean(axis=1)
            self.tendencia = tendencia_raw.apply(self._clasificar_senal_tendencia)
        else:
            self.tendencia = pd.Series(0, index=self.gri.index)

        ultimo_valor = self.tendencia.dropna().iloc[-1] if len(self.tendencia.dropna()) > 0 else 0
        logger.info(f"  Tendencia actual: {self._senal_a_texto(ultimo_valor)}")

        return self.tendencia

    def calcular_seasonality(self, anos_historicos: int = 25) -> pd.Series:
        """
        Calcula la Seasonality basada en comportamiento historico mes a mes.

        Recuerda cual ha sido el comportamiento del riesgo de mercado
        mes a mes durante los ultimos 25 anos.

        Args:
            anos_historicos: Numero de anos de historia a considerar

        Returns:
            Serie con senal de seasonality: 1 (favorable), -1 (desfavorable), 0 (neutral)
        """
        logger.info(f"Calculando Seasonality ({anos_historicos} anos)...")

        # Calcular retornos mensuales historicos del mercado
        if 'US_SP500' in self.df.columns:
            sp500 = self.df['US_SP500'].dropna()
        elif len(self.gri) > 0:
            sp500 = self.gri  # Usar GRI como proxy
        else:
            logger.warning("No hay datos para calcular seasonality")
            self.seasonality = pd.Series(0, index=self.gri.index)
            return self.seasonality

        # Calcular retornos mensuales
        retornos_mensuales = sp500.resample('M').last().pct_change()

        # Calcular promedio y desviacion por mes
        retornos_mensuales_df = retornos_mensuales.to_frame('retorno')
        retornos_mensuales_df['mes'] = retornos_mensuales_df.index.month

        # Estadisticas por mes (ultimos N anos)
        fecha_corte = datetime.now() - timedelta(days=365 * anos_historicos)
        datos_historicos = retornos_mensuales_df[retornos_mensuales_df.index >= fecha_corte]

        stats_mensuales = datos_historicos.groupby('mes').agg({
            'retorno': ['mean', 'std', 'count']
        })
        stats_mensuales.columns = ['media', 'std', 'count']

        # Clasificar meses por rendimiento historico
        media_global = datos_historicos['retorno'].mean()
        std_global = datos_historicos['retorno'].std()

        senal_por_mes = {}
        for mes in range(1, 13):
            if mes in stats_mensuales.index:
                media_mes = stats_mensuales.loc[mes, 'media']
                if media_mes > media_global + 0.5 * std_global:
                    senal_por_mes[mes] = 1  # Mes historicamente bueno
                elif media_mes < media_global - 0.5 * std_global:
                    senal_por_mes[mes] = -1  # Mes historicamente malo
                else:
                    senal_por_mes[mes] = 0
            else:
                senal_por_mes[mes] = 0

        # Meses tipicamente problematicos (ajuste manual basado en literatura)
        # Septiembre y Octubre historicamente volatiles
        meses_peligrosos = [9, 10]  # Septiembre, Octubre
        for mes in meses_peligrosos:
            if mes in senal_por_mes:
                senal_por_mes[mes] = min(senal_por_mes[mes], 0)  # Al menos neutral

        # Meses tipicamente buenos
        # Noviembre-Diciembre ("Santa Rally"), Abril
        meses_buenos = [4, 11, 12]
        for mes in meses_buenos:
            if mes in senal_por_mes:
                senal_por_mes[mes] = max(senal_por_mes[mes], 0)

        # Aplicar senal a cada fecha
        self.seasonality = self.gri.index.to_series().apply(
            lambda x: senal_por_mes.get(x.month, 0)
        )
        self.seasonality.index = self.gri.index

        mes_actual = datetime.now().month
        logger.info(f"  Seasonality mes actual ({mes_actual}): {self._senal_a_texto(senal_por_mes.get(mes_actual, 0))}")

        return self.seasonality

    def calcular_senal_final(self) -> pd.DataFrame:
        """
        Calcula la senal final del Interprete combinando las 3 senales.

        Regla de decision:
            - Solo cambia posicion si las 3 senales coinciden
            - Si solo coinciden 2, mantiene la senal del GRI

        Returns:
            DataFrame con GRI, componentes del Interprete y decision final
        """
        logger.info("\n" + "="*80)
        logger.info("CALCULANDO SENAL FINAL DEL INTERPRETE")
        logger.info("="*80)

        # Calcular componentes si no existen
        if self.momentum is None:
            self.calcular_momentum()
        if self.tendencia is None:
            self.calcular_tendencia()
        if self.seasonality is None:
            self.calcular_seasonality()

        # Crear DataFrame con todas las senales
        df_senales = pd.DataFrame({
            'GRI': self.gri,
            'GRI_Posicion': self.gri.apply(
                lambda x: 1 if x > UmbralesGRI.NEUTRAL_SUPERIOR else (-1 if x < UmbralesGRI.NEUTRAL_INFERIOR else 0)
            ),
            'Momentum': self.momentum,
            'Tendencia': self.tendencia,
            'Seasonality': self.seasonality
        }).dropna()

        if len(df_senales) == 0:
            logger.error("No hay datos suficientes para calcular senal final")
            return pd.DataFrame()

        # Calcular suma de senales del interprete
        df_senales['Suma_Interprete'] = (
            df_senales['Momentum'] +
            df_senales['Tendencia'] +
            df_senales['Seasonality']
        )

        # Regla de decision: las 3 senales deben coincidir para cambiar
        def decision_final(row):
            gri_pos = row['GRI_Posicion']
            suma_int = row['Suma_Interprete']

            # Si las 3 senales del interprete coinciden (todas positivas o negativas)
            if suma_int >= 2:  # Al menos 2 de 3 positivas (mas flexible)
                return 1  # AGRESIVO
            elif suma_int <= -2:  # Al menos 2 de 3 negativas
                return -1  # DEFENSIVO
            else:
                # Mantener senal del GRI
                return gri_pos

        df_senales['Decision_Final'] = df_senales.apply(decision_final, axis=1)

        # Convertir a texto
        df_senales['Decision_Texto'] = df_senales['Decision_Final'].apply(
            lambda x: 'AGRESIVO' if x > 0 else ('DEFENSIVO' if x < 0 else 'NEUTRAL')
        )

        self.senal_final = df_senales

        # Log resumen
        ultimo = df_senales.iloc[-1]
        logger.info(f"\nResultado actual:")
        logger.info(f"  GRI: {ultimo['GRI']:.3f} ({self._senal_a_texto(ultimo['GRI_Posicion'])})")
        logger.info(f"  Momentum: {self._senal_a_texto(ultimo['Momentum'])}")
        logger.info(f"  Tendencia: {self._senal_a_texto(ultimo['Tendencia'])}")
        logger.info(f"  Seasonality: {self._senal_a_texto(ultimo['Seasonality'])}")
        logger.info(f"  >>> DECISION FINAL: {ultimo['Decision_Texto']}")

        return df_senales

    # ========================================================================
    # METODOS AUXILIARES
    # ========================================================================

    def _normalizar_serie(self, serie: pd.Series) -> pd.Series:
        """Normaliza serie a rango aproximado [-1, 1]."""
        if len(serie.dropna()) == 0:
            return serie
        media = serie.rolling(252, min_periods=50).mean()
        std = serie.rolling(252, min_periods=50).std()
        normalizado = (serie - media) / std
        return normalizado.clip(-3, 3) / 3

    def _clasificar_senal_momentum(self, valor: float) -> int:
        """Clasifica valor de momentum en senal."""
        if pd.isna(valor):
            return 0
        if valor > 0.1:
            return 1
        elif valor < -0.1:
            return -1
        return 0

    def _clasificar_senal_tendencia(self, valor: float) -> int:
        """Clasifica valor de tendencia en senal."""
        if pd.isna(valor):
            return 0
        if valor > 0.3:
            return 1
        elif valor < -0.3:
            return -1
        return 0

    def _senal_a_texto(self, senal: int) -> str:
        """Convierte senal numerica a texto."""
        if senal > 0:
            return "AGRESIVO"
        elif senal < 0:
            return "DEFENSIVO"
        return "NEUTRAL"


# ============================================================================
# CLASE: ACRI (ASSET CLASS RISK INDICATOR)
# ============================================================================

class CalculadorACRI:
    """
    Calcula el Asset Class Risk Indicator (ACRI) para cada clase de activo.

    Cada subcategoria tiene su propio GRI + Interprete que genera
    una posicion de:
        - OW+ (Very Overweight): +0.80
        - OW (Overweight): +0.40
        - N (Neutral): 0.00
        - UW (Underweight): -0.40
        - UW- (Very Underweight): -0.80
    """

    # Definicion de clases de activo y sus variables relevantes
    CLASES_ACTIVO = {
        'MONETARIO': {
            'variables': ['US_FED_FUNDS_RATE', 'US_YIELD_3M'],
            'descripcion': 'Liquidez y activos monetarios'
        },
        'RENTA_FIJA_GOBIERNO': {
            'variables': ['US_YIELD_10Y', 'US_YIELD_2Y', 'US_SPREAD_10Y2Y', 'US_MOVE'],
            'descripcion': 'Bonos gubernamentales'
        },
        'RENTA_FIJA_CORPORATIVA': {
            'variables': ['US_CREDIT_IG_SPREAD', 'US_YIELD_10Y', 'US_ISM_MANUFACTURING'],
            'descripcion': 'Bonos corporativos Investment Grade'
        },
        'RENTA_FIJA_HIGH_YIELD': {
            'variables': ['US_CREDIT_HY_SPREAD', 'US_VIX', 'US_ISM_MANUFACTURING'],
            'descripcion': 'Bonos High Yield'
        },
        'RENTA_FIJA_EMERGENTE': {
            'variables': ['EM_CREDIT_SPREAD', 'US_VIX', 'FX_EURUSD'],
            'descripcion': 'Bonos de mercados emergentes'
        },
        'RENTA_VARIABLE_USA': {
            'variables': ['US_SP500', 'US_VIX', 'US_CFNAI', 'US_ISM_MANUFACTURING'],
            'descripcion': 'Acciones USA'
        },
        'RENTA_VARIABLE_EUROPA': {
            'variables': ['EU_STOXX600', 'EU_VSTOXX', 'EU_PMI_MANUFACTURING'],
            'descripcion': 'Acciones Europa'
        },
        'RENTA_VARIABLE_EMERGENTES': {
            'variables': ['EM_MSCI_EM', 'EM_CREDIT_SPREAD', 'CN_PMI_MANUFACTURING'],
            'descripcion': 'Acciones mercados emergentes'
        },
        'RENTA_VARIABLE_TACTICA': {
            'variables': ['US_SP500', 'US_VIX', 'US_CREDIT_HY_SPREAD', 'US_CFNAI'],
            'descripcion': 'Posicion tactica en renta variable'
        },
        'RENTA_VARIABLE_ASIA_PACIFICO': {
            'variables': ['CN_PMI_MANUFACTURING', 'FX_USDJPY', 'EM_MSCI_EM'],
            'descripcion': 'Acciones Asia Pacifico ex-Japan'
        }
    }

    def __init__(self, df_datos: pd.DataFrame, gri_global: pd.Series):
        """
        Inicializa el calculador de ACRI.

        Args:
            df_datos: DataFrame con las series macro y de mercado
            gri_global: Serie del GRI global calculado
        """
        self.df = df_datos.copy()
        self.gri_global = gri_global.copy()
        self.acri_resultados = {}

        logger.info("CalculadorACRI inicializado")

    def calcular_acri_clase(self, clase: str) -> pd.Series:
        """
        Calcula el ACRI para una clase de activo especifica.

        Args:
            clase: Nombre de la clase de activo

        Returns:
            Serie con el ACRI de la clase
        """
        if clase not in self.CLASES_ACTIVO:
            logger.warning(f"Clase de activo no reconocida: {clase}")
            return pd.Series(dtype=float)

        config_clase = self.CLASES_ACTIVO[clase]
        variables = config_clase['variables']

        logger.info(f"Calculando ACRI para {clase}...")

        # Verificar variables disponibles
        variables_disponibles = [v for v in variables if v in self.df.columns]

        if not variables_disponibles:
            logger.warning(f"  No hay variables disponibles para {clase}")
            # Usar GRI global como fallback
            return self.gri_global

        # Calcular indicador especifico de la clase
        componentes = []

        for var in variables_disponibles:
            serie = self.df[var].dropna()
            if len(serie) > 0:
                # Normalizar cada variable
                zscore = self._calcular_zscore(serie)

                # Determinar si la variable es "positiva" o "negativa" para la clase
                if any(x in var for x in ['VIX', 'SPREAD', 'MOVE', 'UNEMPLOYMENT', 'CLAIMS']):
                    # Variables de riesgo: invertir
                    zscore = -zscore

                componentes.append(zscore)

        if not componentes:
            return self.gri_global

        # Combinar componentes
        df_comp = pd.DataFrame(componentes).T
        acri_raw = df_comp.mean(axis=1)

        # Combinar con GRI global (50% especifico, 50% global)
        acri_combinado = pd.DataFrame({
            'especifico': acri_raw,
            'global': self.gri_global
        }).dropna()

        if len(acri_combinado) > 0:
            acri = 0.6 * acri_combinado['especifico'] + 0.4 * acri_combinado['global']
        else:
            acri = self.gri_global

        # Normalizar a rango [-1, 1]
        acri = acri.clip(-1, 1)

        self.acri_resultados[clase] = acri

        return acri

    def calcular_todos_acri(self) -> pd.DataFrame:
        """
        Calcula el ACRI para todas las clases de activo.

        Returns:
            DataFrame con ACRI de todas las clases
        """
        logger.info("\n" + "="*80)
        logger.info("CALCULANDO ACRI PARA TODAS LAS CLASES DE ACTIVO")
        logger.info("="*80)

        resultados = {}

        for clase in self.CLASES_ACTIVO.keys():
            acri = self.calcular_acri_clase(clase)
            if len(acri) > 0:
                resultados[clase] = acri

        # Crear DataFrame consolidado
        df_acri = pd.DataFrame(resultados)

        logger.info(f"\nACRI calculados para {len(resultados)} clases de activo")

        return df_acri

    def generar_ranking_actual(self) -> pd.DataFrame:
        """
        Genera el ranking actual de clases de activo con posiciones.

        Returns:
            DataFrame con el ranking y posiciones actuales
        """
        if not self.acri_resultados:
            self.calcular_todos_acri()

        ranking = []

        for clase, acri in self.acri_resultados.items():
            if len(acri) > 0:
                valor_actual = acri.iloc[-1]
                posicion = self._clasificar_posicion_acri(valor_actual)

                ranking.append({
                    'Categoria_L1': clase.replace('_', ' '),
                    'Valor_Actual': round(valor_actual, 2),
                    'Posicion': posicion,
                    'Descripcion': self.CLASES_ACTIVO[clase]['descripcion']
                })

        df_ranking = pd.DataFrame(ranking)

        # Ordenar por valor (mayor a menor)
        df_ranking = df_ranking.sort_values('Valor_Actual', ascending=False)
        df_ranking = df_ranking.reset_index(drop=True)

        logger.info("\n" + "="*80)
        logger.info("RANKING ACRI ACTUAL")
        logger.info("="*80)
        for _, row in df_ranking.iterrows():
            logger.info(f"  {row['Categoria_L1']}: {row['Valor_Actual']:.2f} ({row['Posicion']})")

        return df_ranking

    def _calcular_zscore(self, serie: pd.Series, window: int = 252) -> pd.Series:
        """Calcula z-score rolling."""
        media = serie.rolling(window=window, min_periods=window//4).mean()
        std = serie.rolling(window=window, min_periods=window//4).std()
        zscore = (serie - media) / std
        return zscore.clip(-3, 3) / 3  # Normalizar a [-1, 1] aprox

    def _clasificar_posicion_acri(self, valor: float) -> str:
        """Clasifica el valor del ACRI en posicion."""
        if valor >= UmbralesACRI.VERY_OVERWEIGHT:
            return 'OW+'
        elif valor >= UmbralesACRI.OVERWEIGHT:
            return 'OW'
        elif valor <= -UmbralesACRI.VERY_OVERWEIGHT:
            return 'UW-'
        elif valor <= UmbralesACRI.UNDERWEIGHT:
            return 'UW'
        else:
            return 'N'


# ============================================================================
# CLASE: BANDAS DINAMICAS (ATR)
# ============================================================================

class BandasDinamicas:
    """
    Implementa bandas dinamicas para ajustar umbrales del GRI.

    Utiliza:
        - ATR (Average True Range): mide volatilidad del mercado
        - Bollinger Bands: para identificar extremos
    """

    def __init__(self, gri_series: pd.Series):
        """
        Inicializa las bandas dinamicas.

        Args:
            gri_series: Serie del GRI
        """
        self.gri = gri_series.copy()
        self.banda_superior = None
        self.banda_inferior = None
        self.atr = None

    def calcular_bandas_bollinger(self, window: int = 20, num_std: float = 2.0) -> Tuple[pd.Series, pd.Series]:
        """
        Calcula bandas de Bollinger para el GRI.

        Args:
            window: Ventana para media movil
            num_std: Numero de desviaciones estandar

        Returns:
            Tuple con (banda_superior, banda_inferior)
        """
        media = self.gri.rolling(window=window).mean()
        std = self.gri.rolling(window=window).std()

        self.banda_superior = media + (num_std * std)
        self.banda_inferior = media - (num_std * std)

        return self.banda_superior, self.banda_inferior

    def calcular_atr(self, high: pd.Series, low: pd.Series, close: pd.Series, window: int = 14) -> pd.Series:
        """
        Calcula Average True Range (ATR).

        Args:
            high: Serie de precios maximos
            low: Serie de precios minimos
            close: Serie de precios de cierre
            window: Ventana para ATR

        Returns:
            Serie con ATR
        """
        # True Range
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))

        true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

        # ATR (media movil exponencial del True Range)
        self.atr = true_range.ewm(span=window, adjust=False).mean()

        return self.atr

    def ajustar_umbrales(self, volatilidad_actual: float) -> Tuple[float, float]:
        """
        Ajusta los umbrales del GRI segun la volatilidad.

        En periodos de alta volatilidad, los umbrales se amplian
        para evitar senales falsas.

        Args:
            volatilidad_actual: Nivel de volatilidad normalizado [0, 1]

        Returns:
            Tuple con (umbral_agresivo, umbral_defensivo)
        """
        # Umbrales base
        base_superior = UmbralesGRI.NEUTRAL_SUPERIOR
        base_inferior = UmbralesGRI.NEUTRAL_INFERIOR

        # Factor de ajuste por volatilidad (mayor vol = umbrales mas amplios)
        factor_ajuste = 1 + (volatilidad_actual * 0.5)  # Max 50% mas amplio

        umbral_agresivo = base_superior * factor_ajuste
        umbral_defensivo = base_inferior * factor_ajuste

        return umbral_agresivo, umbral_defensivo


# ============================================================================
# CLASE PRINCIPAL: SISTEMA GRI COMPLETO
# ============================================================================

class SistemaGRI:
    """
    Sistema completo que integra GRI, Interprete y ACRI.

    Uso:
        sistema = SistemaGRI(df_datos)
        resultado = sistema.ejecutar_analisis_completo()
    """

    def __init__(self, df_datos: pd.DataFrame):
        """
        Inicializa el sistema GRI completo.

        Args:
            df_datos: DataFrame con las series macro y de mercado descargadas
        """
        self.df = df_datos.copy()

        # Componentes del sistema
        self.calculador_gri = None
        self.interprete = None
        self.calculador_acri = None
        self.bandas = None

        # Resultados
        self.gri = None
        self.senal_interprete = None
        self.acri = None
        self.ranking_acri = None

        logger.info("="*80)
        logger.info("SISTEMA GRI INICIALIZADO")
        logger.info("="*80)
        logger.info(f"Datos disponibles: {len(self.df)} observaciones, {len(self.df.columns)} variables")

    def ejecutar_analisis_completo(self) -> Dict:
        """
        Ejecuta el analisis completo del sistema GRI.

        Returns:
            Diccionario con todos los resultados
        """
        logger.info("\n" + "="*80)
        logger.info("EJECUTANDO ANALISIS COMPLETO DEL SISTEMA GRI")
        logger.info("="*80)

        resultados = {}

        # 1. Calcular GRI
        logger.info("\n[1/4] CALCULANDO GRI...")
        self.calculador_gri = CalculadorGRI(self.df)
        self.gri = self.calculador_gri.calcular_gri()
        resultados['gri'] = self.gri
        resultados['ciclo_mercado'] = self.calculador_gri.ciclo_mercado
        resultados['ciclo_economico'] = self.calculador_gri.ciclo_economico

        if len(self.gri) == 0:
            logger.error("No se pudo calcular el GRI")
            return resultados

        # 2. Calcular Interprete
        logger.info("\n[2/4] CALCULANDO INTERPRETE...")
        self.interprete = Interprete(self.df, self.gri)
        self.senal_interprete = self.interprete.calcular_senal_final()
        resultados['interprete'] = self.senal_interprete

        # 3. Calcular ACRI
        logger.info("\n[3/4] CALCULANDO ACRI...")
        self.calculador_acri = CalculadorACRI(self.df, self.gri)
        self.acri = self.calculador_acri.calcular_todos_acri()
        self.ranking_acri = self.calculador_acri.generar_ranking_actual()
        resultados['acri'] = self.acri
        resultados['ranking_acri'] = self.ranking_acri

        # 4. Calcular Bandas Dinamicas
        logger.info("\n[4/4] CALCULANDO BANDAS DINAMICAS...")
        self.bandas = BandasDinamicas(self.gri)
        banda_sup, banda_inf = self.bandas.calcular_bandas_bollinger()
        resultados['banda_superior'] = banda_sup
        resultados['banda_inferior'] = banda_inf

        # Guardar resultados
        self._guardar_resultados(resultados)

        # Generar reporte
        self._generar_reporte_resumen()

        return resultados

    def _guardar_resultados(self, resultados: Dict):
        """Guarda los resultados a archivos."""
        output_dir = config.data_dir

        # GRI historico
        if self.gri is not None and len(self.gri) > 0:
            df_gri = pd.DataFrame({
                'GRI': self.gri,
                'Ciclo_Mercado': self.calculador_gri.ciclo_mercado,
                'Ciclo_Economico': self.calculador_gri.ciclo_economico
            })
            df_gri.to_csv(output_dir / 'gri_historico.csv', encoding='utf-8-sig')
            logger.info(f"GRI historico guardado: {output_dir / 'gri_historico.csv'}")

        # Interprete
        if self.senal_interprete is not None and len(self.senal_interprete) > 0:
            self.senal_interprete.to_csv(output_dir / 'interprete_senales.csv', encoding='utf-8-sig')
            logger.info(f"Senales Interprete guardadas: {output_dir / 'interprete_senales.csv'}")

        # ACRI
        if self.acri is not None and len(self.acri) > 0:
            self.acri.to_csv(output_dir / 'acri_historico.csv', encoding='utf-8-sig')
            logger.info(f"ACRI historico guardado: {output_dir / 'acri_historico.csv'}")

        # Ranking actual
        if self.ranking_acri is not None and len(self.ranking_acri) > 0:
            self.ranking_acri.to_csv(output_dir / 'ranking_acri_actual.csv', index=False, encoding='utf-8-sig')
            logger.info(f"Ranking ACRI guardado: {output_dir / 'ranking_acri_actual.csv'}")

    def _generar_reporte_resumen(self):
        """Genera un reporte resumen del analisis."""
        logger.info("\n" + "="*80)
        logger.info("REPORTE RESUMEN - SISTEMA GRI")
        logger.info("="*80)

        fecha_actual = datetime.now().strftime('%Y-%m-%d %H:%M')
        logger.info(f"\nFecha del analisis: {fecha_actual}")

        # GRI actual
        if self.gri is not None and len(self.gri) > 0:
            gri_actual = self.gri.iloc[-1]
            posicion_gri = self.calculador_gri.clasificar_posicion_gri(gri_actual)

            logger.info(f"\n--- GRI (Global Risk Indicator) ---")
            logger.info(f"  Valor actual: {gri_actual:.3f}")
            logger.info(f"  Posicion: {posicion_gri}")

            if self.calculador_gri.ciclo_mercado is not None:
                logger.info(f"  Ciclo Mercado: {self.calculador_gri.ciclo_mercado.iloc[-1]:.3f}")
            if self.calculador_gri.ciclo_economico is not None:
                logger.info(f"  Ciclo Economico: {self.calculador_gri.ciclo_economico.iloc[-1]:.3f}")

        # Interprete
        if self.senal_interprete is not None and len(self.senal_interprete) > 0:
            ultimo = self.senal_interprete.iloc[-1]
            logger.info(f"\n--- INTERPRETE ---")
            logger.info(f"  Momentum: {'AGRESIVO' if ultimo['Momentum'] > 0 else ('DEFENSIVO' if ultimo['Momentum'] < 0 else 'NEUTRAL')}")
            logger.info(f"  Tendencia: {'AGRESIVO' if ultimo['Tendencia'] > 0 else ('DEFENSIVO' if ultimo['Tendencia'] < 0 else 'NEUTRAL')}")
            logger.info(f"  Seasonality: {'AGRESIVO' if ultimo['Seasonality'] > 0 else ('DEFENSIVO' if ultimo['Seasonality'] < 0 else 'NEUTRAL')}")
            logger.info(f"  >>> DECISION FINAL: {ultimo['Decision_Texto']}")

        # ACRI Ranking
        if self.ranking_acri is not None and len(self.ranking_acri) > 0:
            logger.info(f"\n--- RANKING ACRI (Asset Class Risk Indicator) ---")
            for _, row in self.ranking_acri.iterrows():
                logger.info(f"  {row['Categoria_L1']}: {row['Valor_Actual']:.2f} ({row['Posicion']})")

        logger.info("\n" + "="*80)
        logger.info("FIN DEL REPORTE")
        logger.info("="*80)

    def obtener_senal_actual(self) -> Dict:
        """
        Obtiene la senal actual del sistema.

        Returns:
            Diccionario con la senal actual
        """
        if self.gri is None:
            self.ejecutar_analisis_completo()

        senal = {
            'fecha': datetime.now().strftime('%Y-%m-%d'),
            'gri_valor': round(self.gri.iloc[-1], 3) if self.gri is not None else None,
            'gri_posicion': self.calculador_gri.clasificar_posicion_gri(self.gri.iloc[-1]) if self.gri is not None else None,
        }

        if self.senal_interprete is not None and len(self.senal_interprete) > 0:
            ultimo = self.senal_interprete.iloc[-1]
            senal['momentum'] = int(ultimo['Momentum'])
            senal['tendencia'] = int(ultimo['Tendencia'])
            senal['seasonality'] = int(ultimo['Seasonality'])
            senal['decision_final'] = ultimo['Decision_Texto']

        if self.ranking_acri is not None:
            senal['ranking_acri'] = self.ranking_acri.to_dict('records')

        return senal


# ============================================================================
# FUNCION PRINCIPAL PARA TESTING
# ============================================================================

def main():
    """Funcion principal para testing del modulo."""
    import sys

    # Intentar cargar datos existentes
    filepath_datos = config.data_dir / "df_maestro_variables_macro.pkl"

    if not filepath_datos.exists():
        filepath_csv = config.data_dir / "df_maestro_variables_macro.csv"
        if filepath_csv.exists():
            logger.info(f"Cargando datos desde CSV: {filepath_csv}")
            df = pd.read_csv(filepath_csv, index_col=0, parse_dates=True)
        else:
            logger.error("No se encontraron datos. Ejecuta primero main.py para descargar datos.")
            logger.error(f"Ruta esperada: {filepath_datos}")
            sys.exit(1)
    else:
        logger.info(f"Cargando datos desde: {filepath_datos}")
        df = pd.read_pickle(filepath_datos)

    logger.info(f"Datos cargados: {df.shape[0]} filas x {df.shape[1]} columnas")

    # Ejecutar sistema GRI
    sistema = SistemaGRI(df)
    resultados = sistema.ejecutar_analisis_completo()

    # Mostrar senal actual
    senal = sistema.obtener_senal_actual()
    print("\n" + "="*80)
    print("SENAL ACTUAL DEL SISTEMA GRI")
    print("="*80)
    print(f"Fecha: {senal['fecha']}")
    print(f"GRI: {senal['gri_valor']} ({senal['gri_posicion']})")
    print(f"Decision Final: {senal.get('decision_final', 'N/A')}")
    print("="*80)


# ============================================================================
# GENERADOR DE REPORTES
# ============================================================================

class GeneradorReportes:
    """
    Genera reportes en diferentes formatos con las senales del GRI.
    """

    def __init__(self, sistema_gri: SistemaGRI):
        """
        Inicializa el generador de reportes.

        Args:
            sistema_gri: Instancia del sistema GRI con resultados calculados
        """
        self.sistema = sistema_gri

    def generar_reporte_texto(self, filepath: Path = None) -> str:
        """
        Genera un reporte en formato texto.

        Args:
            filepath: Ruta donde guardar el reporte (opcional)

        Returns:
            String con el reporte
        """
        senal = self.sistema.obtener_senal_actual()
        fecha = datetime.now().strftime('%Y-%m-%d %H:%M')

        lineas = []
        lineas.append("=" * 80)
        lineas.append("REPORTE GRI - GLOBAL RISK INDICATOR")
        lineas.append("=" * 80)
        lineas.append(f"Fecha de generacion: {fecha}")
        lineas.append("")

        # GRI Principal
        lineas.append("-" * 80)
        lineas.append("1. GRI (GLOBAL RISK INDICATOR)")
        lineas.append("-" * 80)
        lineas.append(f"   Valor actual:     {senal['gri_valor']}")
        lineas.append(f"   Posicion:         {senal['gri_posicion']}")
        lineas.append("")

        # Interprete
        if 'momentum' in senal:
            lineas.append("-" * 80)
            lineas.append("2. INTERPRETE")
            lineas.append("-" * 80)
            lineas.append(f"   Momentum:         {self._senal_texto(senal['momentum'])}")
            lineas.append(f"   Tendencia:        {self._senal_texto(senal['tendencia'])}")
            lineas.append(f"   Seasonality:      {self._senal_texto(senal['seasonality'])}")
            lineas.append("")
            lineas.append(f"   >>> DECISION:     {senal['decision_final']}")
            lineas.append("")

        # ACRI
        if 'ranking_acri' in senal and senal['ranking_acri']:
            lineas.append("-" * 80)
            lineas.append("3. ACRI (ASSET CLASS RISK INDICATOR)")
            lineas.append("-" * 80)
            lineas.append("")
            lineas.append(f"   {'Categoria':<35} {'Valor':>10} {'Posicion':>10}")
            lineas.append("   " + "-" * 55)

            for item in senal['ranking_acri']:
                lineas.append(f"   {item['Categoria_L1']:<35} {item['Valor_Actual']:>10.2f} {item['Posicion']:>10}")

            lineas.append("")

        # Leyenda
        lineas.append("-" * 80)
        lineas.append("LEYENDA")
        lineas.append("-" * 80)
        lineas.append("   GRI Posiciones:")
        lineas.append("     AGRESIVO  = Entorno favorable para asumir riesgo (risk-on)")
        lineas.append("     NEUTRAL   = Entorno mixto, mantener posicion")
        lineas.append("     DEFENSIVO = Entorno desfavorable, reducir riesgo (risk-off)")
        lineas.append("")
        lineas.append("   ACRI Posiciones:")
        lineas.append("     OW+  = Very Overweight (+0.80) - Expectativa muy alcista")
        lineas.append("     OW   = Overweight (+0.40)      - Expectativa alcista")
        lineas.append("     N    = Neutral (0.00)          - Expectativa neutral")
        lineas.append("     UW   = Underweight (-0.40)     - Expectativa bajista")
        lineas.append("     UW-  = Very Underweight (-0.80)- Expectativa muy bajista")
        lineas.append("")
        lineas.append("=" * 80)
        lineas.append("Generado por Sistema GRI v1.0")
        lineas.append("=" * 80)

        reporte = "\n".join(lineas)

        if filepath:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(reporte)
            logger.info(f"Reporte guardado en: {filepath}")

        return reporte

    def generar_reporte_html(self, filepath: Path = None) -> str:
        """
        Genera un reporte en formato HTML.

        Args:
            filepath: Ruta donde guardar el reporte (opcional)

        Returns:
            String con el HTML del reporte
        """
        senal = self.sistema.obtener_senal_actual()
        fecha = datetime.now().strftime('%Y-%m-%d %H:%M')

        # Determinar colores segun posicion
        def color_posicion(pos):
            if pos in ['AGRESIVO', 'OW+', 'OW']:
                return '#28a745'  # Verde
            elif pos in ['DEFENSIVO', 'UW', 'UW-']:
                return '#dc3545'  # Rojo
            return '#6c757d'  # Gris

        html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Reporte GRI - {fecha}</title>
    <style>
        body {{ font-family: 'Segoe UI', Arial, sans-serif; margin: 40px; background: #f5f5f5; }}
        .container {{ max-width: 900px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
        h1 {{ color: #2c3e50; border-bottom: 3px solid #3498db; padding-bottom: 15px; }}
        h2 {{ color: #34495e; margin-top: 30px; }}
        .fecha {{ color: #7f8c8d; font-size: 14px; }}
        .gri-box {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 25px; border-radius: 10px; margin: 20px 0; text-align: center; }}
        .gri-valor {{ font-size: 48px; font-weight: bold; }}
        .gri-posicion {{ font-size: 24px; padding: 10px 20px; border-radius: 5px; display: inline-block; margin-top: 10px; background: rgba(255,255,255,0.2); }}
        .interprete {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 15px; margin: 20px 0; }}
        .interprete-item {{ background: #f8f9fa; padding: 20px; border-radius: 8px; text-align: center; }}
        .interprete-label {{ color: #6c757d; font-size: 12px; text-transform: uppercase; }}
        .interprete-valor {{ font-size: 18px; font-weight: bold; margin-top: 5px; }}
        .decision {{ background: {color_posicion(senal.get('decision_final', 'NEUTRAL'))}; color: white; padding: 15px 30px; border-radius: 8px; font-size: 20px; font-weight: bold; display: inline-block; }}
        table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
        th {{ background: #3498db; color: white; padding: 12px; text-align: left; }}
        td {{ padding: 12px; border-bottom: 1px solid #ddd; }}
        tr:hover {{ background: #f5f5f5; }}
        .pos-ow-plus {{ color: #155724; font-weight: bold; }}
        .pos-ow {{ color: #28a745; }}
        .pos-n {{ color: #6c757d; }}
        .pos-uw {{ color: #dc3545; }}
        .pos-uw-minus {{ color: #721c24; font-weight: bold; }}
        .leyenda {{ background: #e9ecef; padding: 20px; border-radius: 8px; margin-top: 30px; }}
        .leyenda h3 {{ margin-top: 0; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>REPORTE GRI</h1>
        <p class="fecha">Generado: {fecha}</p>

        <div class="gri-box">
            <div>Global Risk Indicator (CFNAI 2.1)</div>
            <div class="gri-valor">{senal['gri_valor']}</div>
            <div class="gri-posicion">{senal['gri_posicion']}</div>
        </div>
"""

        # Interprete
        if 'momentum' in senal:
            html += f"""
        <h2>Interprete</h2>
        <div class="interprete">
            <div class="interprete-item">
                <div class="interprete-label">Momentum</div>
                <div class="interprete-valor" style="color: {color_posicion(self._senal_texto(senal['momentum']))}">{self._senal_texto(senal['momentum'])}</div>
            </div>
            <div class="interprete-item">
                <div class="interprete-label">Tendencia</div>
                <div class="interprete-valor" style="color: {color_posicion(self._senal_texto(senal['tendencia']))}">{self._senal_texto(senal['tendencia'])}</div>
            </div>
            <div class="interprete-item">
                <div class="interprete-label">Seasonality</div>
                <div class="interprete-valor" style="color: {color_posicion(self._senal_texto(senal['seasonality']))}">{self._senal_texto(senal['seasonality'])}</div>
            </div>
        </div>
        <p style="text-align: center;">
            <span class="decision">{senal['decision_final']}</span>
        </p>
"""

        # ACRI
        if 'ranking_acri' in senal and senal['ranking_acri']:
            html += """
        <h2>Ranking ACRI (Asset Class Risk Indicator)</h2>
        <table>
            <tr>
                <th>Categoria</th>
                <th>Valor Actual</th>
                <th>Posicion</th>
            </tr>
"""
            for item in senal['ranking_acri']:
                pos_class = f"pos-{item['Posicion'].lower().replace('+', '-plus').replace('-', '-minus')}"
                html += f"""
            <tr>
                <td>{item['Categoria_L1']}</td>
                <td>{item['Valor_Actual']:.2f}</td>
                <td class="{pos_class}">{item['Posicion']}</td>
            </tr>
"""
            html += """
        </table>
"""

        # Leyenda
        html += """
        <div class="leyenda">
            <h3>Leyenda</h3>
            <p><strong>Posiciones GRI:</strong> AGRESIVO (risk-on) | NEUTRAL | DEFENSIVO (risk-off)</p>
            <p><strong>Posiciones ACRI:</strong> OW+ (+0.80) | OW (+0.40) | N (0.00) | UW (-0.40) | UW- (-0.80)</p>
        </div>
    </div>
</body>
</html>
"""

        if filepath:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(html)
            logger.info(f"Reporte HTML guardado en: {filepath}")

        return html

    def _senal_texto(self, valor: int) -> str:
        """Convierte valor numerico a texto."""
        if valor > 0:
            return "AGRESIVO"
        elif valor < 0:
            return "DEFENSIVO"
        return "NEUTRAL"


if __name__ == "__main__":
    main()
