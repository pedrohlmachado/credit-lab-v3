"""Status das Fontes — saude do pipeline de dados.

Le ingest_log e as tabelas fato_* para mostrar, por fonte: ultima execucao,
frescor, linhas ingeridas, e a distribuicao do universo do dia (alerta
precoce contra mudanca de layout — um desvio brusco de ~658 IPCA / ~589 DI
indica que a ANBIMA mudou o arquivo, como aconteceu com o pyield em 2026).

O texto visivel nesta pagina e deliberadamente em linguagem simples (sem
jargao de engenharia como "pipeline", "parse" ou "canario") — quem le esta
pagina esta checando se pode confiar no dado, nao depurando o codigo."""

from datetime import date, datetime

import pandas as pd
import streamlit as st

from src.db.repository import Repository

st.markdown('<p class="page-title">Status das Fontes</p>', unsafe_allow_html=True)
st.markdown(
    '<p class="page-subtitle">De onde vem cada dado e se esta atualizado</p>',
    unsafe_allow_html=True,
)

repo = Repository()

# ---------------------------------------------------------------------------
# Log de ingestao por fonte
# ---------------------------------------------------------------------------

st.markdown("### Quando cada fonte foi atualizada")

df_log = pd.read_sql_query(
    """
    SELECT fonte,
           MAX(data_alvo) AS ultima_data_alvo,
           MAX(finished_at) AS ultima_execucao,
           SUM(CASE WHEN status='ok' THEN 1 ELSE 0 END) AS n_ok,
           SUM(CASE WHEN status='erro_parse' THEN 1 ELSE 0 END) AS n_erro
    FROM ingest_log
    GROUP BY fonte
    ORDER BY fonte
    """,
    repo.conn,
)

if df_log.empty:
    st.warning("Nenhum dado de atualizacao encontrado ainda. Rode `python -m src.ingest.backfill` "
               "e depois `python -m src.ingest.load_raw`.")
else:
    def _semaforo(row):
        if row["n_erro"] > 0:
            return "🔴"
        if not row["ultima_data_alvo"]:
            return "🟡"
        try:
            d = datetime.strptime(row["ultima_data_alvo"], "%Y-%m-%d").date()
            atraso = (date.today() - d).days
        except ValueError:
            return "🟢"
        return "🟢" if atraso <= 3 else "🟡"

    df_log["status"] = df_log.apply(_semaforo, axis=1)
    cols_log = ["status", "fonte", "ultima_data_alvo", "ultima_execucao", "n_ok", "n_erro"]
    display = df_log[cols_log].copy()
    display.columns = [
        "", "FONTE", "DADO MAIS RECENTE", "ATUALIZADO EM", "VEZES QUE FUNCIONOU", "ERROS",
    ]
    st.dataframe(display, use_container_width=True, hide_index=True)
    st.caption("🟢 em dia · 🟡 atrasado ha mais de 3 dias uteis · 🔴 deu erro na ultima tentativa")

# ---------------------------------------------------------------------------
# Cobertura por tabela
# ---------------------------------------------------------------------------

st.markdown("### Quanto historico temos guardado")

col1, col2 = st.columns(2)

def _fmt_janela(datas: list[str]) -> str:
    d0 = date.fromisoformat(datas[0]).strftime("%d/%m/%Y")
    d1 = date.fromisoformat(datas[-1]).strftime("%d/%m/%Y")
    return f"{d0} → {d1}"


with col1:
    datas_reune = repo.get_datas_disponiveis("fato_reune")
    if datas_reune:
        st.metric("Precos de debentures (REUNE)", f"{len(datas_reune)} dias uteis")
        st.caption(_fmt_janela(datas_reune))
    else:
        st.metric("Precos de debentures (REUNE)", "0 dias uteis")

with col2:
    datas_ettj = repo.get_datas_disponiveis("fato_curva_vertice")
    if datas_ettj:
        st.metric("Curva de juros (ETTJ)", f"{len(datas_ettj)} dias uteis")
        st.caption(_fmt_janela(datas_ettj))
    else:
        st.metric("Curva de juros (ETTJ)", "0 dias uteis")

# ---------------------------------------------------------------------------
# Quantidade de ativos por indexador no dia mais recente — se cair muito
# de repente, e sinal de que a ANBIMA mudou o formato do arquivo
# ---------------------------------------------------------------------------

st.markdown("### Quantos ativos de cada tipo entraram hoje")
st.caption(
    "Serve pra notar rapido se algo mudou na fonte: se um numero desses cair muito "
    "de um dia pro outro, pode ser que o arquivo da ANBIMA tenha mudado de formato "
    "e o sistema esteja lendo errado."
)

if datas_reune:
    df_dist = pd.read_sql_query(
        "SELECT indexador, COUNT(*) as n FROM fato_reune "
        "WHERE data_referencia = ? GROUP BY indexador",
        repo.conn, params=[datas_reune[-1]],
    )
    esperado = {"IPCA": 658, "DI": 589, "PRE": 22, "DI_PERC": 5, "IGPM": 1}

    cols = st.columns(len(df_dist)) if len(df_dist) else []
    for i, row in df_dist.iterrows():
        idx = row["indexador"]
        n = row["n"]
        base = esperado.get(idx)
        with cols[i]:
            if base:
                desvio = abs(n - base) / base
                delta_color = "inverse" if desvio > 0.3 else "normal"
                st.metric(
                    idx, n, delta=f"{n - base:+d} vs. o normal", delta_color=delta_color
                )
            else:
                st.metric(idx, n)
    st.caption(
        "Comparando com a quantidade normal de cada tipo, medida em 14/08/2026 "
        "(658 IPCA, 589 DI, 22 PRE, 5 DI_PERC, 1 IGPM). Diferenca grande (acima de 30%) "
        "acende o numero em vermelho."
    )
else:
    st.info("Sem dados carregados ainda.")

# ---------------------------------------------------------------------------
# Series macro (BCB)
# ---------------------------------------------------------------------------

st.markdown("### Indicadores da economia (Banco Central)")

macro_cols = st.columns(3)
labels = {"sgs_4389": "CDI (a.a.)", "sgs_432": "Selic meta", "sgs_433": "IPCA (mensal)"}
for i, (serie_id, label) in enumerate(labels.items()):
    s = repo.get_macro(serie_id)
    with macro_cols[i]:
        if not s.empty:
            data_fmt = s.index[-1].strftime("%d/%m/%Y")
            st.metric(label, f"{s.iloc[-1]:.2f}", help=f"Ultimo dado: {data_fmt}")
        else:
            st.metric(label, "—", help="Rode python -m src.ingest.load_macro")

st.caption(
    "Se estiver vazio, rode `python -m src.ingest.load_macro`. Esses dados nao tem "
    "prazo de validade como os de debentures, entao nao ha pressa em atualizar."
)

repo.close()
