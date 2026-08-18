"""Momentum de credito: migracao de src/mock_debentures.py::calculate_momentum,
com honestidade estatistica (ver analytics/stats.py, mesmo principio) e uma
nova funcao de consolidacao de series por indice encadeado.

A logica de calculo (pesos e multiplicadores) foi copiada exatamente do
legado — nao foi recalibrada. O que muda em relacao ao legado e apenas o
contorno: serie insuficiente agora retorna suficiente=False e sinal
'INDEFINIDO' em vez de score=0/sinal='NEUTRO', que era indistinguivel de um
mercado genuinamente neutro.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

MIN_OBS_MOMENTUM = 80


@dataclass(frozen=True)
class MomentumResult:
    score: float | None
    tendencia: float | None
    velocidade: float | None
    aceleracao: float | None
    sinal: str
    n_obs: int
    suficiente: bool
    motivo: str | None


def calculate_momentum(
    ipca_series: pd.Series, min_obs: int = MIN_OBS_MOMENTUM
) -> MomentumResult:
    """Calcula momentum de taxa IPCA+.

    Logica de mercado:
    - IPCA+ fechando (taxa caindo) = precos subindo = COMPRA
    - IPCA+ abrindo (taxa subindo) = precos caindo = VENDA

    Componentes (pesos):
    - Tendencia (45%): SMA9 vs SMA20
    - Velocidade (35%): taxa de variacao 20d
    - Aceleracao (20%): variacao da velocidade

    Matematica identica a src/mock_debentures.py::calculate_momentum (pesos
    45/35/20, multiplicadores -30/-18/-30, clip final em [-100,100],
    limiares de sinal em +/-20) — a unica diferenca e o contorno de serie
    curta: quando n_obs < min_obs, retorna score=None e sinal='INDEFINIDO'
    em vez de score=0/sinal='NEUTRO', para nao confundir "dado insuficiente"
    com "mercado neutro".
    """
    n = len(ipca_series)
    if n < min_obs:
        return MomentumResult(
            score=None,
            tendencia=None,
            velocidade=None,
            aceleracao=None,
            sinal="INDEFINIDO",
            n_obs=n,
            suficiente=False,
            motivo=f"n_obs={n} < {min_obs} exigidas",
        )

    s = ipca_series.values

    # Tendencia: SMA9 vs SMA20 (invertida — IPCA+ caindo = positivo)
    sma9 = np.mean(s[-9:])
    sma20 = np.mean(s[-20:])
    sma_diff = (sma9 - sma20) / sma20 * 100 if sma20 != 0 else 0
    # Multiplicadores calibrados para credito (movimentos de 1-5 bps/dia)
    tendencia = np.clip(-sma_diff * 30, -100, 100)

    # Velocidade: variacao percentual 20d (invertida — queda = positivo)
    if s[-21] != 0:
        vel_pct = (s[-1] - s[-21]) / s[-21] * 100
    else:
        vel_pct = 0
    velocidade = np.clip(-vel_pct * 18, -100, 100)

    # Aceleracao: variacao da velocidade (invertida)
    if len(s) >= 41 and s[-41] != 0:
        vel_anterior = (s[-21] - s[-41]) / s[-41] * 100
    else:
        vel_anterior = 0
    acel = vel_pct - vel_anterior
    aceleracao = np.clip(-acel * 30, -100, 100)

    # Score ponderado
    score = tendencia * 0.45 + velocidade * 0.35 + aceleracao * 0.20
    score = np.clip(score, -100, 100)

    if score > 20:
        sinal = "COMPRA"
    elif score < -20:
        sinal = "VENDA"
    else:
        sinal = "NEUTRO"

    return MomentumResult(
        score=round(float(score), 1),
        tendencia=round(float(tendencia), 1),
        velocidade=round(float(velocidade), 1),
        aceleracao=round(float(aceleracao), 1),
        sinal=sinal,
        n_obs=n,
        suficiente=True,
        motivo=None,
    )


def consolidar_serie_encadeada(
    historico_por_ativo: dict[str, pd.Series],
) -> pd.Series:
    """Consolida N series de taxa (uma por ativo/debenture) numa serie unica
    representativa do 'nivel medio de credito' via indice encadeado
    (chain-linking) — SEM usar media simples entre ativos, que gera saltos
    espurios quando a composicao da cesta muda dia a dia (o que acontece de
    verdade com dados reais do REUNE: nem todo ativo e cotado todo dia).

    Algoritmo:
    1. Une todas as series num DataFrame (index=datas ordenadas,
       colunas=ativos).
    2. Para cada par de dias consecutivos (t-1, t):
       - identifica os ativos com valor nao-nulo em AMBOS os dias;
       - se nao houver nenhum ativo em comum, o delta do dia e NaN (a
         lacuna e propagada honestamente, nunca forcada a zero);
       - delta_medio(t) = media das variacoes (taxa[t] - taxa[t-1]) dos
         ativos em comum.
    3. Constroi o nivel encadeado: nivel no primeiro dia = media das taxas
       do primeiro dia (nao zero — assim a serie fica na mesma escala/
       unidade das taxas de entrada, o que facilita leitura e comparacao
       direta com qualquer um dos ativos de origem); para os dias
       seguintes, nivel[t] = nivel[t-1] + delta_medio(t), com ffill quando
       delta_medio(t) for NaN (propaga o ultimo nivel conhecido em vez de
       quebrar a serie).
    4. Retorna a serie de niveis, indexada pelas mesmas datas unidas.

    Este e o substituto correto de uma media simples de cesta variavel — a
    mesma tecnica usada por indices de mercado reais (ex.: como a ANBIMA
    constroi o IDA) para nao gerar saltos artificiais quando a composicao
    da amostra muda.
    """
    if not historico_por_ativo:
        return pd.Series(dtype=float)

    df = pd.DataFrame(historico_por_ativo).sort_index()

    if len(df) == 0:
        return pd.Series(dtype=float)

    deltas = df.diff()
    delta_medio = deltas.mean(axis=1, skipna=True)
    # Se nenhum ativo tem valor em AMBOS os dias, todas as colunas de
    # deltas.iloc[t] sao NaN e o mean(skipna=True) resulta em NaN por
    # padrao — mantido explicitamente aqui por clareza.
    n_pares_validos = deltas.notna().sum(axis=1)
    delta_medio = delta_medio.where(n_pares_validos > 0, other=np.nan)

    nivel = pd.Series(index=df.index, dtype=float)
    nivel.iloc[0] = df.iloc[0].mean(skipna=True)
    for i in range(1, len(df)):
        d = delta_medio.iloc[i]
        if pd.isna(d):
            nivel.iloc[i] = nivel.iloc[i - 1]  # ffill honesto: sem par comum
        else:
            nivel.iloc[i] = nivel.iloc[i - 1] + d

    return nivel
