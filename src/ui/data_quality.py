"""Camada de honestidade da UI: badges de profundidade/frescor de dados,
e o rodape padrao que substitui o `st.warning('Dados ilustrativos...')`
das paginas mockadas. Regra inegociavel do plano: nenhuma pagina exibe um
numero estatistico sem tambem exibir o n que o produziu.
"""

from __future__ import annotations

from datetime import date, datetime

import streamlit as st

from src.analytics.stats import SerieStat
from src.db.repository import Cobertura


def render_depth_badge(cob: Cobertura) -> None:
    """Ex.: 'Serie real: 23/02/2026 -> 14/08/2026 - 121 dias uteis'.
    Sempre com as datas reais — nunca 'historico de 5 anos'."""
    if cob.n_obs == 0:
        st.caption(f"⚠️ Sem historico para {cob.codigo}.")
        return
    d0 = _fmt(cob.primeira_data)
    d1 = _fmt(cob.ultima_data)
    st.markdown(
        f'<p class="freshness-ok">Serie real: {d0} → {d1} '
        f"&nbsp;•&nbsp; {cob.n_obs} observacoes</p>",
        unsafe_allow_html=True,
    )


def render_insufficient(stat: SerieStat, metrica: str) -> None:
    """Em vez de um valor falso ou zero, mostra o motivo explicito."""
    st.markdown(
        f'<p class="freshness-warn">{metrica}: — '
        f"(n={stat.n_obs}, {stat.motivo or 'amostra insuficiente'})</p>",
        unsafe_allow_html=True,
    )


def render_freshness_banner(ultima_data_disponivel: str | None, max_atraso_du: int = 2) -> None:
    """Banner de topo quando o dado mais recente carregado no banco esta
    atrasado em relacao a hoje alem do tolerado."""
    if ultima_data_disponivel is None:
        st.error("Nenhum dado carregado. Rode `python -m src.ingest.load_raw`.")
        return

    ultima = datetime.strptime(ultima_data_disponivel, "%Y-%m-%d").date()
    hoje = date.today()
    dias_corridos_atraso = (hoje - ultima).days

    # Aproximacao grosseira de dias uteis de atraso (sem calendario de feriados aqui)
    du_atraso = max(0, round(dias_corridos_atraso * 5 / 7))

    if du_atraso > max_atraso_du:
        st.warning(
            f"Ultimo dado disponivel: {ultima.strftime('%d/%m/%Y')} "
            f"(~{du_atraso} dias uteis atras). Rode o job diario para atualizar.",
            icon="⚠️",
        )


def _fmt(iso_date: str | None) -> str:
    if not iso_date:
        return "—"
    return datetime.strptime(iso_date, "%Y-%m-%d").strftime("%d/%m/%Y")
