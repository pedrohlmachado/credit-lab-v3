"""Estatistica honesta: nenhum numero sai sem o `n` que o produziu.

Regra de UI inegociavel (ver plano, Parte VI §6.5): uma metrica sem
contagem de observacoes e o mesmo mock com outra roupa.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

MIN_OBS = {
    "zscore_temporal": 60,
    "percentil": 40,
    "momentum": 80,
    "media_movel_20": 20,
}

MIN_GRUPO_CROSS_SECTION = 8


@dataclass(frozen=True)
class SerieStat:
    valor: float | None
    n_obs: int
    inicio: date | None
    fim: date | None
    suficiente: bool
    motivo: str | None = None


def zscore_temporal(
    serie: pd.Series, min_obs: int = MIN_OBS["zscore_temporal"]
) -> SerieStat:
    """Z-score do ultimo valor da serie contra a propria historia. Retorna
    valor=None se n < min_obs — NUNCA extrapola."""
    s = serie.dropna()
    n = len(s)
    inicio = s.index.min() if n else None
    fim = s.index.max() if n else None
    if n < min_obs:
        return SerieStat(None, n, inicio, fim, False, f"n_obs={n} < {min_obs} exigidas")

    media = s.mean()
    desvio = s.std(ddof=1)
    if desvio == 0 or pd.isna(desvio):
        return SerieStat(None, n, inicio, fim, False, "desvio-padrao zero ou indefinido")

    z = (s.iloc[-1] - media) / desvio
    return SerieStat(float(z), n, inicio, fim, True, None)


def percentil_temporal(
    serie: pd.Series, min_obs: int = MIN_OBS["percentil"]
) -> SerieStat:
    s = serie.dropna()
    n = len(s)
    inicio = s.index.min() if n else None
    fim = s.index.max() if n else None
    if n < min_obs:
        return SerieStat(None, n, inicio, fim, False, f"n_obs={n} < {min_obs} exigidas")

    pct = float((s <= s.iloc[-1]).sum()) / n * 100
    return SerieStat(pct, n, inicio, fim, True, None)


def zscore_cross_section(
    df: pd.DataFrame,
    valor_col: str,
    grupo_cols: list[str],
    min_grupo: int = MIN_GRUPO_CROSS_SECTION,
) -> pd.Series:
    """Z-score de cada linha contra o grupo definido por `grupo_cols` no
    MESMO dia (metrica primaria enquanto a serie temporal e curta — ver
    plano, decisao 'cross-section antes de temporal'). Grupos com menos de
    `min_grupo` observacoes retornam NaN em vez de um z-score instavel."""
    def _z(g: pd.Series) -> pd.Series:
        n = g.notna().sum()
        if n < min_grupo:
            return pd.Series(np.nan, index=g.index)
        media = g.mean()
        desvio = g.std(ddof=1)
        if desvio == 0 or pd.isna(desvio):
            return pd.Series(np.nan, index=g.index)
        return (g - media) / desvio

    return df.groupby(grupo_cols)[valor_col].transform(_z)


def bucket_duration(duration_anos: float) -> str:
    """Classifica duration em anos nos buckets padrao do cross-section
    (0-2, 2-4, 4-6, 6+), usados para agrupar pares comparaveis."""
    if duration_anos < 2:
        return "0-2a"
    if duration_anos < 4:
        return "2-4a"
    if duration_anos < 6:
        return "4-6a"
    return "6a+"
