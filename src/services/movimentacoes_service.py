"""Servico da pagina Negocios: repository + analytics.zspread -> DataFrame
pronto pra UI. Substitui src/anbima_reune.py (scraper HTML por regex, so
IPCA+) — a fonte real agora e o TXT estruturado do REUNE, ja parseado e
carregado no banco por src/ingest/load_raw.py, cobrindo IPCA/DI/PRE/IGP-M.
"""

from __future__ import annotations

from datetime import date

import pandas as pd

from src.analytics.curve import flat_forward_interpolate
from src.analytics.zspread import zspread_com_grossup
from src.db.repository import Repository


def get_datas_disponiveis(repo: Repository) -> list[date]:
    from datetime import datetime as _dt

    datas_iso = repo.get_datas_disponiveis("fato_reune")
    return [_dt.strptime(d, "%Y-%m-%d").date() for d in datas_iso]


def get_negocios_dia(repo: Repository, d: date, indexador: str | None = None) -> pd.DataFrame:
    """Retorna o dia com Z-spread calculado para os ativos IPCA (unicos
    para os quais a formula ANBIMA de Z-spread se aplica diretamente —
    DI/PRE nao tem NTN-B de referencia no REUNE)."""
    df = repo.get_reune_dia(d, indexador=indexador)
    if df.empty:
        return df

    df_vert = repo.get_curva_vertices(d)
    vertices_ipca = [
        (int(r.du), float(r.taxa_ipca)) for r in df_vert.itertuples() if pd.notna(r.taxa_ipca)
    ]

    df_ativo = repo.conn.execute(
        "SELECT codigo, incentivada_12431 FROM v_ativo_atual"
    ).fetchall()
    incentivada_map = {r["codigo"]: bool(r["incentivada_12431"]) for r in df_ativo}

    z_bruto_col = []
    z_gross_col = []
    metodo_col = []
    ntnb_taxa_col = []

    for row in df.itertuples():
        if row.indexador != "IPCA" or pd.isna(row.taxa_indicativa) or not row.ref_ntnb_venc:
            z_bruto_col.append(None)
            z_gross_col.append(None)
            metodo_col.append(None)
            ntnb_taxa_col.append(None)
            continue

        if not vertices_ipca:
            z_bruto_col.append(None)
            z_gross_col.append(None)
            metodo_col.append(None)
            ntnb_taxa_col.append(None)
            continue

        ref_venc = pd.Timestamp(row.ref_ntnb_venc).date()
        du_ate_venc = max(1, (ref_venc - d).days * 252 // 365)
        taxa_ntnb = flat_forward_interpolate(vertices_ipca, du_ate_venc)

        incentivada = incentivada_map.get(row.codigo, True)  # maioria IPCA e incentivada
        r = zspread_com_grossup(row.taxa_indicativa, taxa_ntnb, incentivada)

        z_bruto_col.append(round(r.z_spread_bruto, 4))
        z_gross_col.append(round(r.z_spread_grossup, 4) if r.z_spread_grossup is not None else None)
        metodo_col.append(r.metodo_grossup)
        ntnb_taxa_col.append(round(taxa_ntnb, 4))

    df = df.copy()
    df["ntnb_ref_taxa"] = ntnb_taxa_col
    df["z_spread_bruto"] = z_bruto_col
    df["z_spread_grossup"] = z_gross_col
    df["metodo_grossup"] = metodo_col
    return df
