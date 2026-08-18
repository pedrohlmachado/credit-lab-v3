"""Pagina de momentum de credito consolidado — dados reais.

Fonte: fato_reune (serie real, ~121 dias uteis a partir de 23/02/2026),
consolidada por indice encadeado (nunca media simples de cesta variavel —
ver src.analytics.momentum.consolidar_serie_encadeada). Substitui
src/mock_debentures.py::get_consolidated_spread_history (media simples
sobre random walks de 5 anos).

Cobre IPCA+ e DI+ como series separadas (toggle, mesmo padrao de
pages/debentures.py) — nunca misturadas no mesmo indice, porque taxa real
e spread sobre o DI sao unidades diferentes (ver momentum_service.py)."""

from datetime import date

import plotly.graph_objects as go
import streamlit as st

from src.db.repository import Repository
from src.services.debentures_service import get_universo_debentures
from src.services.momentum_service import get_momentum, get_serie_consolidada, get_top_trades
from src.ui.data_quality import render_freshness_banner, render_insufficient
from src.ui.formatting import fmt_col_str
from src.ui.theme import POLO, polo_layout

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

st.markdown('<p class="page-title">Momentum</p>', unsafe_allow_html=True)

repo = Repository()
datas_disp_iso = repo.get_datas_disponiveis("fato_reune")
if not datas_disp_iso:
    st.error("Nenhum dado carregado. Rode `python -m src.ingest.backfill` "
              "e depois `python -m src.ingest.load_raw`.")
    st.stop()

render_freshness_banner(datas_disp_iso[-1])

primeira_data = date.fromisoformat(datas_disp_iso[0])
ultima_data = date.fromisoformat(datas_disp_iso[-1])

# ---------------------------------------------------------------------------
# Indexador (controla a serie inteira — nunca misturar IPCA+ com DI+)
# ---------------------------------------------------------------------------

indexador_sel = st.radio(
    "Indexador", options=["IPCA+", "DI+"], horizontal=True, label_visibility="collapsed",
)
indexador_map = {"IPCA+": "IPCA", "DI+": "DI"}
indexador_ativo = indexador_map[indexador_sel]
label_serie = "IPCA+" if indexador_ativo == "IPCA" else "Spread DI+"

# ---------------------------------------------------------------------------
# Filtros
# ---------------------------------------------------------------------------

df_all = get_universo_debentures(repo, indexadores=(indexador_ativo,))
if df_all.empty:
    st.warning(f"Sem debentures {indexador_sel} carregadas para a data mais recente.")
    st.stop()

with st.expander("Filtros", expanded=True):
    row1 = st.columns(4)
    with row1[0]:
        setores_sel = st.multiselect(
            "Setor", options=sorted(df_all["setor"].dropna().unique()), default=[],
            key="mom_setor", placeholder="Todos os setores",
        )
    with row1[1]:
        emissores_sel = st.multiselect(
            "Emissor", options=sorted(df_all["empresa"].dropna().unique()), default=[],
            key="mom_emissor", placeholder="Todos os emissores",
        )
    with row1[2]:
        especies_sel = st.multiselect(
            "Especie/Garantia", options=sorted(df_all["especie_garantia"].dropna().unique()),
            default=[], key="mom_especie", placeholder="Todas as especies",
        )
    with row1[3]:
        codigos_sel = st.multiselect(
            "Ativo", options=sorted(df_all["codigo"].unique()), default=[], key="mom_codigo",
            placeholder="Todos os ativos",
        )

    row2 = st.columns(1)
    with row2[0]:
        dur_range = st.slider(
            "Duration (anos)",
            min_value=float(df_all["duration_anos"].min()),
            max_value=float(df_all["duration_anos"].max()),
            value=(float(df_all["duration_anos"].min()), float(df_all["duration_anos"].max())),
            step=0.5,
        )

# ---------------------------------------------------------------------------
# Serie consolidada (indice encadeado)
# ---------------------------------------------------------------------------

hist = get_serie_consolidada(
    repo,
    indexador=indexador_ativo,
    setores=setores_sel or None,
    emissores=emissores_sel or None,
    especies=especies_sel or None,
    codigos=codigos_sel or None,
    dur_min=dur_range[0],
    dur_max=dur_range[1],
)

if hist.empty:
    st.info("Nenhum dado encontrado com os filtros selecionados.")
    st.stop()

momentum = get_momentum(hist)

if not momentum.suficiente:
    render_insufficient(momentum, "Momentum")
    st.stop()

# ---------------------------------------------------------------------------
# Score central + Componentes
# ---------------------------------------------------------------------------

col_score, col_t, col_v, col_a = st.columns([1.5, 1, 1, 1])

with col_score:
    if momentum.sinal == "COMPRA":
        color, label = "#16a34a", "COMPRA"
    elif momentum.sinal == "VENDA":
        color, label = "#dc2626", "VENDA"
    else:
        color, label = "#d97706", "NEUTRO"

    st.markdown(
        f'<div style="text-align:center; padding:16px 0;">'
        f'<div style="font-size:11px; color:{POLO["cinza"]}; text-transform:uppercase; '
        f'letter-spacing:0.1em;">Momentum Score (n={momentum.n_obs})</div>'
        f'<div style="font-size:48px; font-weight:700; color:{color}; line-height:1.1;">'
        f'{momentum.score:+.0f}</div>'
        f'<div style="font-size:14px; font-weight:600; color:{color}; '
        f'letter-spacing:0.05em;">{label}</div>'
        f'<div style="font-size:10px; color:{POLO["cinza"]}; margin-top:4px;">'
        f'-100 venda &nbsp;•&nbsp; +100 compra</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

with col_t:
    st.metric("Tendencia", f"{momentum.tendencia:+.1f}",
              help=f"SMA 9d vs SMA 20d. Positivo = {label_serie} em queda. Peso: 45%.")
with col_v:
    st.metric("Velocidade", f"{momentum.velocidade:+.1f}",
              help=f"Variacao do {label_serie} em 20d. Queda = positivo. Peso: 35%.")
with col_a:
    st.metric("Aceleracao", f"{momentum.aceleracao:+.1f}",
              help="Mudanca na velocidade vs 20d atras. Peso: 20%.")

# ---------------------------------------------------------------------------
# Grafico historico com SMAs
# ---------------------------------------------------------------------------

fig_hist = go.Figure()
fig_hist.add_trace(go.Scatter(
    x=hist.index, y=hist.values, mode="lines", name="Nivel consolidado (encadeado)",
    line=dict(color=POLO["azul"], width=1.5),
))
if len(hist) >= 9:
    fig_hist.add_trace(go.Scatter(
        x=hist.index, y=hist.rolling(9).mean(), mode="lines", name="SMA 9d",
        line=dict(color="#16a34a", width=1.2, dash="dash"),
    ))
if len(hist) >= 20:
    fig_hist.add_trace(go.Scatter(
        x=hist.index, y=hist.rolling(20).mean(), mode="lines", name="SMA 20d",
        line=dict(color="#dc2626", width=1.2, dash="dot"),
    ))

fig_hist.update_layout(**polo_layout(
    yaxis=dict(title=f"Nivel de {label_serie} (indice encadeado)"),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    height=400,
))
st.plotly_chart(fig_hist, use_container_width=True)

st.caption(
    "Nivel consolidado por indice encadeado: variacao diaria media so entre ativos "
    "presentes em dois dias consecutivos, acumulada. Evita saltos artificiais quando "
    "a composicao da cesta muda (nem todo ativo e cotado todo dia)."
)

# ---------------------------------------------------------------------------
# Top trades
# ---------------------------------------------------------------------------

st.markdown("### Ranking por ativo")
top = get_top_trades(repo, indexador=indexador_ativo, n=5)
if top.empty:
    st.info("Nenhum ativo individual com serie suficiente para ranking (min. 80 dias uteis).")
else:
    top_display = top[["codigo", "empresa", "setor", "taxa", "score", "sinal"]].copy()
    top_display["setor"] = fmt_col_str(top_display["setor"])  # "Nao classificado" em vez de "None"
    top_display["setor"] = top_display["setor"].replace("", "Nao classificado")
    top_display.columns = ["TICKER", "EMISSOR", "SETOR", label_serie.upper(), "SCORE", "SINAL"]
    st.dataframe(
        top_display, use_container_width=True, hide_index=True,
        column_config={
            label_serie.upper(): st.column_config.NumberColumn(format="%.2f%%"),
            "SCORE": st.column_config.NumberColumn(format="%+.0f"),
        },
    )

repo.close()
