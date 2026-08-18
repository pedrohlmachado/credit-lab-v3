"""Pagina de analise de debentures (IPCA+ e DI+) — dados reais.

Fonte: REUNE (taxas) + SND (cadastro, garantia, incentivada) + CVM (setor)
+ ETTJ (NTN-B de referencia para Z-spread IPCA+). Substitui
src/mock_debentures.py inteiro (100 tuplas hardcoded + rng.uniform/randint
para z-score/delta + random walk de 5 anos) — deletado ao final da
migracao original.

IPCA+ e DI+ usam unidades diferentes de taxa (taxa real cheia vs. spread
sobre o DI) — por isso o grafico e o heatmap sempre respeitam o indexador
selecionado no filtro; a tabela de baixo, essa sim, pode mostrar os dois
juntos, com a coluna de taxa rotulada por linha.
"""

import numpy as np
import plotly.graph_objects as go
import streamlit as st

from src.db.repository import Repository
from src.services.debentures_service import (
    get_emissor_debentures,
    get_heatmap_setor_duration,
    get_serie_temporal,
    get_universo_debentures,
    get_zscore_temporal,
)
from src.ui.data_quality import render_depth_badge, render_freshness_banner, render_insufficient
from src.ui.formatting import fmt_col_num, fmt_col_pct, fmt_col_signed, fmt_col_str
from src.ui.theme import POLO, polo_layout

PALETTE = [POLO["azul"], POLO["azul_esc"], "#ff8c42", "#2ecc71", "#8e44ad", "#e74c3c",
           "#f39c12", "#95a5a6", "#27ae60", "#d35400"]

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

st.markdown('<p class="page-title">Debentures</p>', unsafe_allow_html=True)
st.markdown(
    '<p class="page-subtitle">IPCA+ e DI+: taxas, valor relativo e cadastro real</p>',
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Dados
# ---------------------------------------------------------------------------

repo = Repository()
datas_disp_iso = repo.get_datas_disponiveis("fato_reune")
if not datas_disp_iso:
    st.error("Nenhum dado carregado. Rode `python -m src.ingest.backfill` "
              "e depois `python -m src.ingest.load_raw`.")
    st.stop()

render_freshness_banner(datas_disp_iso[-1])

df_all = get_universo_debentures(repo)
if df_all.empty:
    st.warning("Sem debentures carregadas para a data mais recente.")
    st.stop()

st.caption(
    f"Universo: {len(df_all)} debentures (IPCA+ e DI+) &nbsp;•&nbsp; "
    f"Janela real: {datas_disp_iso[0][8:10]}/{datas_disp_iso[0][5:7]}/{datas_disp_iso[0][:4]} → "
    f"{datas_disp_iso[-1][8:10]}/{datas_disp_iso[-1][5:7]}/{datas_disp_iso[-1][:4]} "
    f"({len(datas_disp_iso)} dias uteis)"
)

# ---------------------------------------------------------------------------
# Filtro de indexador — controla grafico/heatmap (unidades diferentes,
# nunca misturar) e tambem filtra a tabela
# ---------------------------------------------------------------------------

indexador_sel = st.radio(
    "Indexador", options=["IPCA+", "DI+", "Todos"], horizontal=True, label_visibility="collapsed",
)
# DI_PERC ("% do DI") fica de fora do DI+: e convencao percentual, nao
# aditiva, e misturada num grafico rotulado "Spread DI+ (%)" apareceria
# numa escala incompativel (ex.: 114,65 contra spreads de ~1-5). So
# aparece em "Todos", onde a tabela mostra os tres indexadores lado a lado
# sem fazer nenhuma conta entre eles.
indexador_map = {"IPCA+": ["IPCA"], "DI+": ["DI"], "Todos": ["IPCA", "DI", "DI_PERC"]}
df_idx = df_all[df_all["indexador"].isin(indexador_map[indexador_sel])]

# ---------------------------------------------------------------------------
# Graficos: Scatter + Heatmap — so quando um unico indexador esta ativo
# ---------------------------------------------------------------------------

if indexador_sel == "Todos":
    st.info(
        "Selecione IPCA+ ou DI+ para ver o grafico de valor relativo. Taxa real e spread "
        "sobre o DI nao sao comparaveis na mesma escala. A tabela abaixo mostra os dois juntos."
    )
else:
    label_y = "IPCA+ (%)" if indexador_sel == "IPCA+" else "Spread DI+ (%)"
    col_scatter, col_heat = st.columns(2)

    with col_scatter:
        fig_scatter = go.Figure()
        setores_unicos = sorted(df_idx["setor"].dropna().unique())
        for i, setor in enumerate(setores_unicos[:10]):
            mask = df_idx["setor"] == setor
            fig_scatter.add_trace(go.Scatter(
                x=df_idx.loc[mask, "duration_anos"], y=df_idx.loc[mask, "taxa_indicativa"],
                mode="markers", name=setor,
                marker=dict(
                    color=PALETTE[i % len(PALETTE)], size=6, line=dict(color="#ffffff", width=0.5)
                ),
                text=df_idx.loc[mask, "codigo"],
                hovertemplate="%{text}<br>Duration: %{x:.1f}<br>Taxa: %{y:.2f}%<extra></extra>",
            ))
        if len(setores_unicos) > 10:
            mask = ~df_idx["setor"].isin(setores_unicos[:10])
            fig_scatter.add_trace(go.Scatter(
                x=df_idx.loc[mask, "duration_anos"], y=df_idx.loc[mask, "taxa_indicativa"],
                mode="markers", name="Outros setores",
                marker=dict(color=POLO["cinza"], size=6),
                text=df_idx.loc[mask, "codigo"],
            ))

        df_reg = df_idx.dropna(subset=["duration_anos", "taxa_indicativa"])
        if len(df_reg) >= 2:
            coeffs = np.polyfit(df_reg["duration_anos"], df_reg["taxa_indicativa"], 1)
            x_reg = np.linspace(
                df_reg["duration_anos"].min() * 0.9, df_reg["duration_anos"].max() * 1.1, 50
            )
            fig_scatter.add_trace(go.Scatter(
                x=x_reg, y=np.polyval(coeffs, x_reg), mode="lines",
                name="Curva de credito (regressao)",
                line=dict(color=POLO["azul_esc"], width=2, dash="dash"), hoverinfo="skip",
            ))

        fig_scatter.update_layout(**polo_layout(
            title=dict(
                text=f"{indexador_sel} vs Duration", font=dict(color=POLO["azul_esc"], size=14)
            ),
            xaxis=dict(title="Duration (anos)"), yaxis=dict(title=label_y, ticksuffix="%"),
            legend=dict(font=dict(size=9)), height=400,
        ))
        st.plotly_chart(fig_scatter, use_container_width=True)

    with col_heat:
        hm = get_heatmap_setor_duration(df_idx)
        if hm.empty:
            st.info("Amostra insuficiente para o heatmap (celulas exigem n≥5).")
        else:
            order = ["0-2a", "2-4a", "4-6a", "6a+"]
            cols_present = [c for c in order if c in hm.columns]
            hm = hm[cols_present].sort_index()

            annotations = [
                dict(x=bucket, y=setor, text=f"{hm.loc[setor, bucket]:.2f}",
                     font=dict(size=9, color=POLO["azul_esc"]), showarrow=False)
                for setor in hm.index for bucket in hm.columns
                if hm.loc[setor, bucket] == hm.loc[setor, bucket]  # notna
            ]

            fig_heat = go.Figure(go.Heatmap(
                z=hm.values, x=hm.columns.tolist(), y=hm.index.tolist(),
                colorscale=[[0, "#e8f5e9"], [0.5, "#fff8e1"], [1, "#fce4e4"]],
                hovertemplate="Setor: %{y}<br>Duration: %{x}<br>Mediano: %{z:.2f}%<extra></extra>",
                showscale=False,
            ))
            fig_heat.update_layout(**polo_layout(
                title=dict(
                    text=f"{indexador_sel} mediano: Setor x Duration",
                    font=dict(color=POLO["azul_esc"], size=14),
                ),
                xaxis=dict(title="", side="top"), yaxis=dict(title="", autorange="reversed"),
                annotations=annotations, height=400, margin=dict(l=140, r=10, t=55, b=10),
            ))
            st.plotly_chart(fig_heat, use_container_width=True)
            st.caption(
                "Celulas com menos de 5 ativos ficam vazias: sem amostra suficiente "
                "pra um numero estavel."
            )

# ---------------------------------------------------------------------------
# Filtros de busca
# ---------------------------------------------------------------------------

col_f1, col_f2, col_f3, col_f4 = st.columns(4)
with col_f1:
    ticker_busca = st.text_input("Ticker", placeholder="ex.: ACRC21")
with col_f2:
    emissor_busca = st.text_input("Emissor", placeholder="ex.: Equipav")
with col_f3:
    setores_sel = st.multiselect(
        "Setor", options=sorted(df_idx["setor"].dropna().unique()), default=[],
        placeholder="Todos os setores",
    )
with col_f4:
    garantia_sel = st.multiselect(
        "Especie/Garantia",
        options=sorted(df_idx["especie_garantia"].dropna().unique()), default=[],
        placeholder="Todas as especies",
    )

df = df_idx.copy()
if ticker_busca:
    df = df[df["codigo"].str.contains(ticker_busca, case=False, na=False, regex=False)]
if emissor_busca:
    df = df[df["empresa"].str.contains(emissor_busca, case=False, na=False, regex=False)]
if setores_sel:
    df = df[df["setor"].isin(setores_sel)]
if garantia_sel:
    df = df[df["especie_garantia"].isin(garantia_sel)]

if df.empty:
    st.info("Nenhuma debenture encontrada com os filtros selecionados.")
    st.stop()

# ---------------------------------------------------------------------------
# KPIs
# ---------------------------------------------------------------------------

kpi1, kpi2, kpi3, kpi4 = st.columns(4)
with kpi1:
    st.metric("Total", len(df))
with kpi2:
    atrativos = (df["z_score_cross"] < 0).sum()
    st.metric("Atrativos (z < 0)", int(atrativos),
              help="Taxa acima da mediana dos pares comparaveis hoje (mesmo indexador e "
                   "bucket de duration) = maior rentabilidade relativa.")
with kpi3:
    st.metric("Taxa media", f"{df['taxa_indicativa'].mean():.2f}%")
with kpi4:
    z_medio = df["z_spread_bruto"].dropna().mean()
    st.metric("Z-spread/Spread medio", f"{z_medio:.2f}%" if z_medio == z_medio else "—",
              help="IPCA+: formula oficial ANBIMA contra a NTN-B. DI+: spread de mercado "
                   "sobre o DI, ja publicado pela ANBIMA.")

# ---------------------------------------------------------------------------
# Tabela
# ---------------------------------------------------------------------------

st.caption(
    "Ordem alfabetica por ticker. Clique numa coluna do cabecalho pra reordenar, "
    "selecione uma linha para ver detalhes"
)

cols_show = ["codigo", "empresa", "indexador", "setor", "especie_garantia", "duration_anos",
             "taxa_indicativa", "z_spread_bruto", "delta_med_bps", "z_score_cross"]
display_df = df[cols_show].copy()

# Pre-formatadas como texto com "—" no lugar de NaN — o NumberColumn nativo
# do st.dataframe mostra o texto literal "None" pra valor ausente (ex.:
# DI_PERC nao tem Z-spread; alguns ativos ficam sem par suficiente pro
# z-score). A selecao de linha (abaixo) usa indice posicional, nao o
# conteudo da coluna, entao a conversao pra texto nao afeta essa parte.
display_df["duration_anos"] = fmt_col_num(display_df["duration_anos"], 1)
display_df["taxa_indicativa"] = fmt_col_pct(display_df["taxa_indicativa"])
display_df["z_spread_bruto"] = fmt_col_pct(display_df["z_spread_bruto"])
display_df["delta_med_bps"] = fmt_col_signed(display_df["delta_med_bps"], 0)
display_df["z_score_cross"] = fmt_col_num(display_df["z_score_cross"])
# Setor sem match no cadastro CVM (13% do universo, SPEs de capital
# fechado) fica "Nao classificado" — explicito, nunca "None" nem chutado.
display_df["setor"] = fmt_col_str(display_df["setor"]).replace("", "Nao classificado")
display_df["empresa"] = fmt_col_str(display_df["empresa"]).replace("", "—")
display_df["especie_garantia"] = fmt_col_str(display_df["especie_garantia"]).replace("", "—")

display_df.columns = ["TICKER", "EMISSOR", "INDEXADOR", "SETOR", "GARANTIA", "DURATION",
                       "TAXA", "Z-SPREAD/SPREAD", "Δ MEDIANA (bps)", "Z-SCORE"]

event = st.dataframe(
    display_df, use_container_width=True, hide_index=True,
    on_select="rerun", selection_mode="single-row",
    column_config={
        "DURATION": st.column_config.TextColumn(help="Duration (anos)."),
        "TAXA": st.column_config.TextColumn(
            help="IPCA+: taxa real cheia. DI+: spread sobre o DI. Nao comparar entre indexadores."),
        "Z-SPREAD/SPREAD": st.column_config.TextColumn(
            help="IPCA+: Z-spread oficial ANBIMA contra NTN-B. DI+: a propria taxa indicativa, "
                 "que ja e o spread de mercado sobre o DI. Sem valor para DI_PERC (convencao "
                 "percentual, nao aditiva)."),
        "Δ MEDIANA (bps)": st.column_config.TextColumn(
            help="Positivo = taxa acima da mediana dos pares (mesmo indexador e bucket de "
                 "duration) hoje = barato. Negativo = abaixo = caro."),
        "Z-SCORE": st.column_config.TextColumn(
            help="Contra os pares do mesmo indexador no MESMO dia (metrica primaria: a serie "
                 "temporal ainda e curta). Negativo = taxa acima da media dos pares. Vazio "
                 "quando o grupo comparavel tem menos de 8 ativos."),
    },
)

# ---------------------------------------------------------------------------
# Detalhe da debenture selecionada
# ---------------------------------------------------------------------------

selected_rows = event.selection.rows if event.selection else []
if not selected_rows:
    selected_rows = [0]

idx = selected_rows[0]
selected = df.iloc[idx]
codigo = selected["codigo"]
empresa = selected["empresa"]
setor = selected["setor"]
indexador_ativo = selected["indexador"]

st.markdown("---")

cob = repo.get_cobertura(codigo)
render_depth_badge(cob)

hist = get_serie_temporal(repo, codigo, indexador_ativo)
if not hist.empty:
    mediana = hist.median()
    label_serie = "IPCA+" if indexador_ativo == "IPCA" else "Spread DI+"

    fig_hist = go.Figure()
    fig_hist.add_trace(go.Scatter(
        x=hist.index, y=hist.values, mode="lines", name=label_serie,
        line=dict(color=POLO["azul"], width=2),
        hovertemplate=f"Data: %{{x|%d/%m/%Y}}<br>{label_serie}: %{{y:.2f}}%<extra></extra>",
    ))
    fig_hist.add_hline(y=mediana, line_dash="dash", line_color="#ff8c42",
                        annotation_text=f"Mediana: {mediana:.2f}%", annotation_position="top right")
    fig_hist.update_layout(**polo_layout(
        title=dict(text=f"Historico real: {codigo}", font=dict(color=POLO["azul_esc"], size=14)),
        yaxis=dict(title=f"{label_serie} (%)", ticksuffix="%"), height=350, showlegend=False,
    ))
    st.plotly_chart(fig_hist, use_container_width=True)

    zstat = get_zscore_temporal(repo, codigo, indexador_ativo)
    if zstat.suficiente:
        st.markdown(
            f'<p class="source-label">Setor: {setor} &nbsp;•&nbsp; '
            f"{label_serie} atual: {hist.iloc[-1]:.2f}% &nbsp;•&nbsp; "
            f"Mediana da janela (n={zstat.n_obs}, desde {datas_disp_iso[0]}): {mediana:.2f}% "
            f"&nbsp;•&nbsp; Z-score temporal: {zstat.valor:+.2f}</p>",
            unsafe_allow_html=True,
        )
    else:
        render_insufficient(zstat, "Z-score temporal")
else:
    st.info("Sem historico real disponivel para este ativo.")

emissor_debs = get_emissor_debentures(
    df_all[df_all["indexador"] == indexador_ativo], empresa
)
if len(emissor_debs) > 1:
    st.markdown(f"### Curva do Emissor: {empresa}")
    fig_e = go.Figure()
    other = emissor_debs[emissor_debs["codigo"] != codigo]
    fig_e.add_trace(go.Scatter(
        x=other["duration_anos"], y=other["taxa_indicativa"], mode="markers+text", name="Outras",
        marker=dict(color=POLO["cinza"], size=10, line=dict(color="#ffffff", width=1)),
        text=other["codigo"], textposition="top center", textfont=dict(size=9, color=POLO["cinza"]),
    ))
    sel_r = emissor_debs[emissor_debs["codigo"] == codigo]
    fig_e.add_trace(go.Scatter(
        x=sel_r["duration_anos"], y=sel_r["taxa_indicativa"], mode="markers+text", name=codigo,
        marker=dict(color="#e74c3c", size=14, line=dict(color="#ffffff", width=2)),
        text=[codigo], textposition="top center", textfont=dict(size=10, color="#e74c3c"),
    ))
    fig_e.update_layout(**polo_layout(
        title=dict(
            text=f"Taxa vs Duration: {empresa}", font=dict(color=POLO["azul_esc"], size=14)
        ),
        xaxis=dict(title="Duration (anos)"),
        yaxis=dict(title="Taxa (%)", ticksuffix="%"), height=350,
    ))
    st.plotly_chart(fig_e, use_container_width=True)

repo.close()
