"""Entry point — Analise de Renda Fixa (credit-lab)."""

import sys

from streamlit.runtime.scriptrunner import get_script_run_ctx

if get_script_run_ctx() is None:
    # Script rodado diretamente (ex.: botao "Run" do VSCode faz `python3
    # app.py`), em vez de `streamlit run app.py`. Streamlit apps precisam
    # do proprio servidor — sem isso so aparecem avisos de "missing
    # ScriptRunContext" e nada sobe. Em vez de deixar o usuario preso
    # nisso, relanca a si mesmo do jeito certo.
    import subprocess

    subprocess.run([sys.executable, "-m", "streamlit", "run", __file__, *sys.argv[1:]])
    sys.exit(0)

# ---------------------------------------------------------------------------
# Banco de dados: o repositorio carrega o banco comprimido
# (data/credit_lab.db.gz, ~13 MB) em vez do arquivo cru (~46 MB) — o upload
# pela interface web do GitHub bloqueia arquivos acima de 25 MB. Descompacta
# uma unica vez, na primeira execucao (aqui ou no primeiro boot do container
# do Streamlit Cloud); depois disso o .db fica em disco e as proximas
# cargas de pagina usam ele direto, sem descompactar de novo.
# ---------------------------------------------------------------------------
import gzip
import shutil
from pathlib import Path

_db_path = Path(__file__).parent / "data" / "credit_lab.db"
_db_gz_path = _db_path.parent / (_db_path.name + ".gz")

if not _db_path.exists() and _db_gz_path.exists():
    with gzip.open(_db_gz_path, "rb") as f_in, open(_db_path, "wb") as f_out:
        shutil.copyfileobj(f_in, f_out)

import streamlit as st

from src.ui.theme import POLO, streamlit_css

st.set_page_config(
    page_title="Analise de Renda Fixa",
    page_icon=":material/show_chart:",
    layout="wide",
)

# ---------------------------------------------------------------------------
# CSS global — tema Polo Capital (ver src/ui/theme.py)
# ---------------------------------------------------------------------------

st.markdown(streamlit_css(), unsafe_allow_html=True)

st.markdown(
    f"""
    <style>
    /* Navigation bar — fundo limpo, botoes outline */
    .st-key-navbar {{
        background: {POLO["branco"]};
        padding: 8px 24px 8px 24px;
        margin: 0 -1rem 0.8rem -1rem;
        border-bottom: 1px solid {POLO["cinza_cl"]};
    }}
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------

PAGE_MAP = {
    "Debentures": "pages/debentures.py",
    "Negocios": "pages/movimentacoes.py",
    "Momentum": "pages/momentum.py",
    "Status das Fontes": "pages/status.py",
}

pages = {label: st.Page(path, title=label) for label, path in PAGE_MAP.items()}
pg = st.navigation(list(pages.values()), position="hidden")

with st.container(key="navbar"):
    cols = st.columns([1, 1, 1, 1])
    with cols[0]:
        st.page_link(
            "pages/debentures.py", label="Debentures",
            icon=":material/account_balance:", use_container_width=True,
        )
    with cols[1]:
        st.page_link(
            "pages/movimentacoes.py", label="Negocios",
            icon=":material/receipt_long:", use_container_width=True,
        )
    with cols[2]:
        st.page_link(
            "pages/momentum.py", label="Momentum",
            icon=":material/speed:", use_container_width=True,
        )
    with cols[3]:
        st.page_link(
            "pages/status.py", label="Status",
            icon=":material/monitor_heart:", use_container_width=True,
        )

pg.run()
