"""Negocios do Dia — mercado secundario ANBIMA (REUNE), todos os indexadores.

Fonte: TXT diario do REUNE, parseado e carregado no banco por
src/ingest/load_raw.py. Substitui o scraper HTML antigo (src/anbima_reune.py,
regex sobre <TD>, so 633 IPCA+) — cobre agora IPCA/DI/PRE/IGP-M (~1.275
ativos/dia). Pagina nao faz mais I/O de rede na renderizacao.
"""

import pandas as pd
import streamlit as st

from src.db.repository import Repository
from src.services.movimentacoes_service import get_datas_disponiveis, get_negocios_dia
from src.ui.data_quality import render_freshness_banner
from src.ui.formatting import fmt_col_num, fmt_col_pct, fmt_col_str

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

st.markdown('<p class="page-title">Negocios do Dia</p>', unsafe_allow_html=True)
st.markdown(
    '<p class="page-subtitle">Mercado secundario ANBIMA (REUNE): '
    'IPCA+ / DI / Prefixado / IGP-M</p>',
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Repositorio (sem I/O de rede aqui — a pagina so le o banco)
# ---------------------------------------------------------------------------

repo = Repository()
datas_disp = get_datas_disponiveis(repo)

if not datas_disp:
    st.error(
        "Nenhum negocio carregado no banco. Rode `python -m src.ingest.backfill` "
        "e depois `python -m src.ingest.load_raw`."
    )
    st.stop()

render_freshness_banner(datas_disp[-1].isoformat())

# ---------------------------------------------------------------------------
# Filtros
# ---------------------------------------------------------------------------

col_date, col_idx, col_search = st.columns([1, 1, 1])
with col_date:
    selected_date = st.selectbox(
        "Data de referencia",
        options=list(reversed(datas_disp)),
        format_func=lambda d: d.strftime("%d/%m/%Y"),
    )
with col_idx:
    indexador_sel = st.selectbox(
        "Indexador", options=["Todos", "IPCA", "DI", "DI_PERC", "PRE", "IGPM"],
    )
with col_search:
    search = st.text_input("Buscar por codigo ou emissor", value="", key="neg_search")

df_all = get_negocios_dia(
    repo, selected_date, indexador=None if indexador_sel == "Todos" else indexador_sel
)

if df_all.empty:
    st.info("Nenhuma movimentacao encontrada para esta data.")
    st.stop()

st.caption(
    f"{len(df_all)} ativos &nbsp;•&nbsp; "
    f"{selected_date.strftime('%d/%m/%Y')} &nbsp;•&nbsp; Fonte: ANBIMA (REUNE)"
)

df = df_all.copy()
if search:
    mask = (
        df["codigo"].str.contains(search, case=False, na=False)
        | df["nome_anbima"].str.contains(search, case=False, na=False)
    )
    df = df[mask]

if df.empty:
    st.info("Nenhuma movimentacao encontrada com os filtros selecionados.")
    st.stop()

# ---------------------------------------------------------------------------
# KPIs
# ---------------------------------------------------------------------------

k1, k2, k3, k4 = st.columns(4)
with k1:
    st.metric("Total de ativos", len(df))
with k2:
    ipca_n = (df["indexador"] == "IPCA").sum()
    di_n = df["indexador"].isin(["DI", "DI_PERC"]).sum()
    st.metric("IPCA / DI", f"{ipca_n} / {di_n}")
with k3:
    z_medio = df["z_spread_bruto"].dropna().mean()
    st.metric(
        "Z-spread medio (IPCA)", f"{z_medio:.2f}%" if z_medio == z_medio else "—",
        help="Formula oficial ANBIMA: Z = ((1+taxa)/(1+taxa_ntnb)-1)*100, sem gross-up.",
    )
with k4:
    n_zspread = df["z_spread_bruto"].notna().sum()
    st.metric("Com Z-spread calculado", f"{n_zspread}/{len(df)}")

# ---------------------------------------------------------------------------
# Tabela
# ---------------------------------------------------------------------------

label_taxa = {
    "IPCA": "Taxa real (a.a.)", "DI": "Spread s/ DI (a.a.)",
    "DI_PERC": "% do DI", "PRE": "Taxa nominal (a.a.)", "IGPM": "Taxa real (a.a.)",
}
if indexador_sel != "Todos":
    st.caption(f"Convencao da coluna de taxa: **{label_taxa.get(indexador_sel, 'Taxa (a.a.)')}**")
else:
    st.caption(
        "Atencao: a coluna 'Taxa Indicativa' tem convencao diferente por indexador "
        "(taxa real para IPCA, spread sobre DI para DI). Filtre por indexador "
        "antes de comparar taxas entre linhas."
    )

def _fmt_indice(row) -> str:
    if row["indexador"] == "IPCA" and pd.notna(row["spread_emissao"]):
        return f"IPCA + {row['spread_emissao']:.3f}%"
    if row["indexador"] == "DI" and pd.notna(row["spread_emissao"]):
        return f"DI + {row['spread_emissao']:.3f}%"
    if row["indexador"] == "DI_PERC" and pd.notna(row["percentual_di"]):
        return f"{row['percentual_di']:.2f}% do DI"
    return row["indexador"]


df["indice_fmt"] = df.apply(_fmt_indice, axis=1)

# Diferenca entre a taxa indicativa (a marcacao oficial da ANBIMA pro dia)
# e as pontas de compra/venda de fato registradas — pega a maior das duas
# distancias, porque tanto negociar acima quanto abaixo da marcacao e
# igualmente "diferente do esperado". Ordena a tabela por essa coluna por
# padrao: o ativo que mais fugiu da marcacao do dia aparece primeiro.
diff_compra = (df["taxa_compra"] - df["taxa_indicativa"]).abs()
diff_venda = (df["taxa_venda"] - df["taxa_indicativa"]).abs()
df["diferenca"] = pd.concat([diff_compra, diff_venda], axis=1).max(axis=1)
df = df.sort_values("diferenca", ascending=False, na_position="last")

display = df[[
    "codigo", "nome_anbima", "data_repac_venc", "indexador", "indice_fmt",
    "diferenca", "taxa_compra", "taxa_venda", "taxa_indicativa",
    "z_spread_bruto", "z_spread_grossup", "metodo_grossup",
    "desvio_padrao", "pu", "pct_pu_par", "duration_du", "pct_reune",
]].copy()

# Varias colunas tem muitos ausentes legitimos (Z-spread so existe pra
# IPCA+, %REUNE fica nulo na maioria das linhas) — pre-formatadas como
# texto com "—" no lugar de NaN, porque o NumberColumn nativo do
# st.dataframe mostra o texto literal "None" pra valor ausente.
display["diferenca"] = fmt_col_num(display["diferenca"], 4)
display["taxa_compra"] = fmt_col_num(display["taxa_compra"], 4)
display["taxa_venda"] = fmt_col_num(display["taxa_venda"], 4)
display["taxa_indicativa"] = fmt_col_num(display["taxa_indicativa"], 4)
display["z_spread_bruto"] = fmt_col_pct(display["z_spread_bruto"])
display["z_spread_grossup"] = fmt_col_pct(display["z_spread_grossup"])
display["metodo_grossup"] = fmt_col_str(display["metodo_grossup"])
display["desvio_padrao"] = fmt_col_num(display["desvio_padrao"], 4)
display["pu"] = fmt_col_num(display["pu"], 6)
display["pct_pu_par"] = fmt_col_num(display["pct_pu_par"], 2)
display["duration_du"] = fmt_col_num(display["duration_du"], 0)
display["pct_reune"] = fmt_col_pct(display["pct_reune"], 0)

display.columns = [
    "CODIGO", "EMISSOR", "VENC.", "INDEXADOR", "INDICE",
    "DIFERENCA", "TX COMPRA", "TX VENDA", "TX INDIC.",
    "Z-SPREAD", "Z-SPREAD (GROSS-UP)", "METODO GROSS-UP",
    "DESVIO", "PU", "% PU PAR", "DURATION (DU)", "% REUNE",
]

st.caption(
    "Ordenado pela coluna DIFERENCA: o quanto a compra ou a venda do dia se afastou "
    "da taxa indicativa da ANBIMA (quem afastou mais aparece primeiro)."
)

st.dataframe(
    display, use_container_width=True, hide_index=True,
    column_config={
        "DIFERENCA": st.column_config.TextColumn(
            help="Maior distancia entre TX COMPRA ou TX VENDA e a TX INDIC. do dia. "
                 "Ex.: indicativa 10%, negociado a 15% -> diferenca de 5 pontos."
        ),
        "Z-SPREAD": st.column_config.TextColumn(
            help="Formula oficial ANBIMA contra a NTN-B de referencia. So calculado para IPCA+."
        ),
        "Z-SPREAD (GROSS-UP)": st.column_config.TextColumn(
            help="Gross-up para incentivadas isentas de IR (metodo exato ou aproximacao "
                 "fechada, ver coluna METODO GROSS-UP).",
        ),
        "% REUNE": st.column_config.TextColumn(
            help="Contribuicao no indice REUNE. Nulo na maioria dos ativos."
        ),
    },
)

st.markdown(
    f'<p class="source-label">'
    f"Data: {selected_date.strftime('%d/%m/%Y')} &nbsp;•&nbsp; "
    f"{len(df)} ativos &nbsp;•&nbsp; Fonte: ANBIMA, Mercado Secundario (REUNE)</p>",
    unsafe_allow_html=True,
)

repo.close()
