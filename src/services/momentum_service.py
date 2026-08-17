"""Servico da pagina Momentum: repository + analytics.momentum -> DataFrame
pronto pra UI. Consolidacao por indice encadeado (nunca media simples de
cesta variavel — ver analytics.momentum.consolidar_serie_encadeada) e
ranking de momentum por ativo (get_top_trades, reativado — estava escrita
em mock_debentures.py e nunca importada por nenhuma pagina).

Parametrizado por indexador (IPCA ou DI, nunca DI_PERC — convencao
percentual, incompativel com o nivel aditivo do indice encadeado), mas
cada chamada opera sobre UM indexador por vez: misturar spread sobre DI
com taxa real no mesmo indice consolidado produziria um numero sem
significado. A pagina oferece as duas series como abas separadas (mesmo
padrao do toggle IPCA+/DI+ de pages/debentures.py), nunca combinadas."""

from __future__ import annotations

from datetime import date

import pandas as pd

from src.analytics.momentum import MomentumResult, calculate_momentum, consolidar_serie_encadeada
from src.analytics.stats import MIN_OBS
from src.db.repository import Repository


def get_serie_consolidada(
    repo: Repository,
    indexador: str = "IPCA",
    setores: list[str] | None = None,
    emissores: list[str] | None = None,
    especies: list[str] | None = None,
    codigos: list[str] | None = None,
    dur_min: float | None = None,
    dur_max: float | None = None,
) -> pd.Series:
    """Serie de nivel encadeado sobre o universo filtrado, para um unico
    `indexador` ('IPCA' ou 'DI'). Le a serie completa de cada ativo do
    universo e consolida via indice encadeado — a media simples de uma
    cesta que muda de composicao dia a dia geraria saltos espurios (ver
    docstring de consolidar_serie_encadeada)."""
    from src.services.debentures_service import get_universo_debentures

    df_universo = get_universo_debentures(repo, indexadores=(indexador,))
    if df_universo.empty:
        return pd.Series(dtype=float)

    if setores:
        df_universo = df_universo[df_universo["setor"].isin(setores)]
    if emissores:
        df_universo = df_universo[df_universo["empresa"].isin(emissores)]
    if especies:
        df_universo = df_universo[df_universo["especie_garantia"].isin(especies)]
    if codigos:
        df_universo = df_universo[df_universo["codigo"].isin(codigos)]
    if dur_min is not None:
        df_universo = df_universo[df_universo["duration_anos"] >= dur_min]
    if dur_max is not None:
        df_universo = df_universo[df_universo["duration_anos"] <= dur_max]

    if df_universo.empty:
        return pd.Series(dtype=float)

    codigos_filtrados = df_universo["codigo"].tolist()
    df_serie = repo.get_reune_serie(codigos_filtrados, date(2000, 1, 1), date(2100, 1, 1))
    df_serie = df_serie[df_serie["indexador"] == indexador]
    if df_serie.empty:
        return pd.Series(dtype=float)

    historico_por_ativo = {}
    for codigo, g in df_serie.groupby("codigo"):
        s = g.set_index("data_referencia")["taxa_indicativa"]
        s.index = pd.to_datetime(s.index)
        historico_por_ativo[codigo] = s.sort_index()

    return consolidar_serie_encadeada(historico_por_ativo)


def get_momentum(serie_consolidada: pd.Series) -> MomentumResult:
    return calculate_momentum(serie_consolidada, min_obs=MIN_OBS["momentum"])


def get_top_trades(repo: Repository, indexador: str = "IPCA", n: int = 5) -> pd.DataFrame:
    """Ranking de momentum por ativo individual, para um unico `indexador`
    ('IPCA' ou 'DI') — reativa a feature que estava escrita em
    mock_debentures.py::get_top_trades() e nunca era chamada por nenhuma
    pagina."""
    from src.services.debentures_service import get_serie_temporal, get_universo_debentures

    df_universo = get_universo_debentures(repo, indexadores=(indexador,))
    if df_universo.empty:
        return pd.DataFrame()

    rows = []
    for _, deb in df_universo.iterrows():
        hist = get_serie_temporal(repo, deb["codigo"], indexador).dropna()
        if len(hist) < MIN_OBS["momentum"]:
            continue
        mom = calculate_momentum(hist, min_obs=MIN_OBS["momentum"])
        if not mom.suficiente:
            continue
        rows.append({
            "codigo": deb["codigo"], "empresa": deb["empresa"], "setor": deb["setor"],
            "taxa": deb["taxa_indicativa"], "score": mom.score, "sinal": mom.sinal,
        })

    result = pd.DataFrame(rows)
    if result.empty:
        return result

    top_buy = result.nlargest(n, "score")
    top_sell = result.nsmallest(n, "score")
    return pd.concat([top_buy, top_sell]).drop_duplicates(subset="codigo")
