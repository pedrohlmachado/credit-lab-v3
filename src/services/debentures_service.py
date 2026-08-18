"""Servico da pagina Debentures: repository + analytics -> DataFrame pronto
pra UI. Substitui src/mock_debentures.py inteiro (100 tuplas hardcoded +
rng.uniform/randint para z-score e delta, random walk de 5 anos para
historico) por dados reais do REUNE/SND/CVM e Z-spread ANBIMA.

Universo: IPCA+ e DI+ (CDI+) — as duas familias que o usuario efetivamente
acompanha. Prefixadas (22 ativos) e IGP-M (1 ativo) ficam de fora por serem
residuais e nao terem metodologia de valor relativo definida aqui.

Cuidado central deste modulo: taxa_indicativa significa coisas DIFERENTES
por indexador (taxa real cheia para IPCA, spread sobre DI para DI+) — por
isso toda comparacao (delta vs mediana, z-score cross-section, heatmap)
agrupa por indexador ALEM de bucket de duration. Nunca comparar um numero
IPCA com um numero DI diretamente.
"""

from __future__ import annotations

from datetime import date

import pandas as pd

from src.analytics.curve import flat_forward_interpolate
from src.analytics.stats import (
    MIN_OBS,
    SerieStat,
    bucket_duration,
    zscore_cross_section,
    zscore_temporal,
)
from src.analytics.zspread import zspread_com_grossup
from src.db.repository import Repository

INDEXADORES_UNIVERSO = ("IPCA", "DI", "DI_PERC")


def get_universo_debentures(
    repo: Repository,
    data_ref: date | None = None,
    indexadores: tuple[str, ...] = INDEXADORES_UNIVERSO,
) -> pd.DataFrame:
    """Universo de debentures do dia (IPCA+ e/ou DI+, conforme `indexadores`),
    com setor/garantia/incentivada do cadastro real e valor relativo
    calculado ao vivo contra a curva ANBIMA do dia."""
    df = repo.get_universo(data_ref=data_ref)
    if df.empty:
        return df
    df = df[df["indexador"].isin(indexadores)].reset_index(drop=True)
    if df.empty:
        return df

    d = pd.Timestamp(df["data_referencia"].iloc[0]).date()
    df_vert = repo.get_curva_vertices(d)
    vertices_ipca = [
        (int(r.du), float(r.taxa_ipca)) for r in df_vert.itertuples() if pd.notna(r.taxa_ipca)
    ]

    z_bruto, z_gross, metodo, ntnb_taxa = [], [], [], []
    for row in df.itertuples():
        if row.indexador == "IPCA":
            if pd.isna(row.taxa_indicativa) or not row.ref_ntnb_venc or not vertices_ipca:
                z_bruto.append(None)
                z_gross.append(None)
                metodo.append(None)
                ntnb_taxa.append(None)
                continue
            ref_venc = pd.Timestamp(row.ref_ntnb_venc).date()
            du_ate_venc = max(1, (ref_venc - d).days * 252 // 365)
            taxa_ntnb = flat_forward_interpolate(vertices_ipca, du_ate_venc)
            incentivada = bool(row.incentivada_12431) if pd.notna(row.incentivada_12431) else True
            r = zspread_com_grossup(row.taxa_indicativa, taxa_ntnb, incentivada)
            z_bruto.append(round(r.z_spread_bruto, 4))
            z_gross.append(round(r.z_spread_grossup, 4) if r.z_spread_grossup is not None else None)
            metodo.append(r.metodo_grossup)
            ntnb_taxa.append(round(taxa_ntnb, 4))
        elif row.indexador == "DI":
            # A taxa indicativa de um papel "DI + x%" JA E o spread de mercado
            # sobre o DI — nao ha NTN-B de referencia envolvida (nem precisa).
            z_bruto.append(round(row.taxa_indicativa, 4) if pd.notna(row.taxa_indicativa) else None)
            z_gross.append(None)
            metodo.append("nao_aplicavel")
            ntnb_taxa.append(None)
        else:
            # DI_PERC ("% do DI"): convencao percentual, nao aditiva — nao da
            # pra transformar num spread comparavel sem uma premissa extra.
            # Fica de fora do Z-spread em vez de forcar um numero errado.
            z_bruto.append(None)
            z_gross.append(None)
            metodo.append(None)
            ntnb_taxa.append(None)

    df = df.copy()
    df["z_spread_bruto"] = z_bruto
    df["z_spread_grossup"] = z_gross
    df["metodo_grossup"] = metodo
    df["ntnb_ref_taxa"] = ntnb_taxa
    df["duration_anos"] = (df["duration_du"] / 252).round(2)
    df["bucket_duration"] = df["duration_anos"].apply(
        lambda x: bucket_duration(x) if pd.notna(x) else None
    )

    # Delta vs mediana dos pares comparaveis hoje — SEMPRE dentro do mesmo
    # indexador e do mesmo bucket de duration, nunca misturando IPCA com DI.
    df["mediana_bucket_hoje"] = df.groupby(["indexador", "bucket_duration"])[
        "taxa_indicativa"
    ].transform("median")
    df["delta_med_bps"] = ((df["taxa_indicativa"] - df["mediana_bucket_hoje"]) * 100).round(1)

    # Z-score cross-section: metrica primaria (janela temporal ainda curta),
    # tambem agrupado por indexador + bucket de duration.
    df["z_score_cross"] = zscore_cross_section(
        df, "taxa_indicativa", ["indexador", "bucket_duration"], min_grupo=8
    ).round(3)

    return df.sort_values("codigo").reset_index(drop=True)


def get_serie_temporal(repo: Repository, codigo: str, indexador: str) -> pd.Series:
    """Serie real (nao sintetica) da taxa indicativa de um ativo. Profundidade
    limitada pela janela publica da ANBIMA — nunca inventar historico."""
    cob = repo.get_cobertura(codigo)
    if cob.n_obs == 0:
        return pd.Series(dtype=float)
    df = repo.get_reune_serie([codigo], date(2000, 1, 1), date(2100, 1, 1))
    df = df[df["indexador"] == indexador]
    if df.empty:
        return pd.Series(dtype=float)
    s = df.set_index("data_referencia")["taxa_indicativa"]
    s.index = pd.to_datetime(s.index)
    return s.sort_index()


def get_zscore_temporal(repo: Repository, codigo: str, indexador: str) -> SerieStat:
    s = get_serie_temporal(repo, codigo, indexador)
    return zscore_temporal(s, min_obs=MIN_OBS["zscore_temporal"])


def get_emissor_debentures(df_universo: pd.DataFrame, empresa: str) -> pd.DataFrame:
    return df_universo[df_universo["empresa"] == empresa][
        ["codigo", "duration_anos", "taxa_indicativa", "setor"]
    ].copy()


def get_heatmap_setor_duration(df_universo: pd.DataFrame) -> pd.DataFrame:
    """Mediana de Z-spread/valor relativo por Setor x bucket de duration,
    sobre o subconjunto ja filtrado (o chamador decide o indexador — nunca
    misturar IPCA com DI no mesmo heatmap). Celulas com n<5 ficam None em
    vez de um numero instavel."""
    if df_universo.empty:
        return pd.DataFrame()
    g = df_universo.dropna(subset=["setor", "bucket_duration", "z_spread_bruto"])
    if g.empty:
        return pd.DataFrame()
    counts = g.groupby(["setor", "bucket_duration"])["z_spread_bruto"].count()
    medians = g.groupby(["setor", "bucket_duration"])["z_spread_bruto"].median()
    medians = medians.where(counts >= 5)
    return medians.unstack("bucket_duration")
