"""Tema visual Polo Capital — tokens portados de
~/.claude/skills/carreira-curriculo-teorico/assets/dossie-polo.css (unica
copia viva da identidade Polo). Consumido pelo app (via .streamlit/config.toml
e CSS inline) e pelos graficos Plotly de cada pagina (via polo_layout()).

Restricao herdada do CSS original: paleta e tipografia apenas — sem logo da
Polo, sem apresentar o material como comunicacao institucional da empresa.
Futura Lt BT tem fallback nativo no macOS (Futura); a cascata de fontes
abaixo garante que quem abrir sem a fonte cai em Century Gothic/Avenir sem
quebra de layout.
"""

from __future__ import annotations

POLO = {
    "azul": "#00A3DD",       # PANTONE 299 — cor primaria, curva atual, CTAs
    "azul_esc": "#0079A6",   # hover, curva D-1, titulos
    "cinza": "#777772",      # Cool Gray 10 — texto secundario, curvas historicas
    "cinza_cl": "#EDEDEB",   # bordas, gridlines
    "cinza_bg": "#F7F7F6",   # fundo de cards
    "texto": "#2E2E2C",
    "branco": "#FFFFFF",
    "fonte": '"Futura Lt BT", "Futura", "Century Gothic", "Avenir Next", sans-serif',
}

# Semantica de dados — mantida FORA da paleta de marca. Sinal nao e branding:
# COMPRA/VENDA e escalas divergentes de heatmap continuam com verde/vermelho
# funcionais, independente da identidade visual.
SEMANTICA = {
    "compra": "#16a34a",
    "venda": "#dc2626",
    "neutro": "#d97706",
    "heatmap_baixo": "#e8f5e9",
    "heatmap_medio": "#fff8e1",
    "heatmap_alto": "#fce4e4",
}


def polo_layout(**overrides) -> dict:
    """update_layout base compartilhado por todos os graficos Plotly do
    app, elimina a duplicacao de ~90 linhas de fig.update_layout()
    repetidas em cada pagina do projeto original."""
    base = dict(
        plot_bgcolor=POLO["branco"],
        paper_bgcolor=POLO["branco"],
        font=dict(color=POLO["texto"], family=POLO["fonte"], size=12),
        xaxis=dict(gridcolor=POLO["cinza_cl"], zerolinecolor=POLO["cinza_cl"]),
        yaxis=dict(gridcolor=POLO["cinza_cl"], zerolinecolor=POLO["cinza_cl"]),
        legend=dict(
            bgcolor=POLO["branco"], bordercolor=POLO["cinza_cl"], borderwidth=1,
            font=dict(color=POLO["texto"]),
        ),
        margin=dict(l=50, r=20, t=40, b=40),
        height=400,
    )
    base.update(overrides)
    return base


def streamlit_css() -> str:
    """CSS injetado em app.py — substitui a paleta azul antiga (#3a7fc1
    etc.) pelos tokens Polo. Esconde chrome padrao do Streamlit, mantem o
    layout de navbar customizada."""
    p = POLO
    return f"""
    <style>
    #MainMenu {{visibility: hidden;}}
    footer {{visibility: hidden;}}
    header[data-testid="stHeader"] {{visibility: hidden; height: 0;}}
    .block-container {{padding-top: 0rem; padding-bottom: 0rem; max-width: 100%;}}
    [data-testid="stSidebar"] {{display: none;}}
    [data-testid="stSidebarCollapsedControl"] {{display: none;}}

    .stApp {{background-color: {p["branco"]}; color: {p["texto"]}; font-weight: 400;
             font-family: {p["fonte"]};}}

    .stTabs [data-baseweb="tab-list"] {{gap: 6px;}}
    .stTabs [data-baseweb="tab"] {{
        background: transparent; border: 1px solid {p["cinza_cl"]}; border-radius: 6px;
        color: {p["cinza"]}; padding: 8px 20px; font-weight: 500; letter-spacing: 0.04em;
    }}
    .stTabs [aria-selected="true"] {{
        background: {p["cinza_bg"]}; color: {p["azul_esc"]}; border-color: {p["azul"]};
        font-weight: 600;
    }}

    .stMetric {{
        background: {p["cinza_bg"]}; border: 1px solid {p["cinza_cl"]}; border-radius: 8px;
        padding: 14px;
    }}
    .stMetric label {{color: {p["cinza"]} !important; font-size: 11px !important;
                       text-transform: uppercase; letter-spacing: 0.05em;}}
    .stMetric [data-testid="stMetricValue"] {{color: {p["azul_esc"]} !important; font-weight: 600;}}

    .stDataFrame {{background: {p["branco"]};}}

    h1, h2, h3 {{color: {p["azul_esc"]} !important;}}

    .page-title {{
        font-size: 20px; font-weight: 700; color: {p["azul_esc"]};
        letter-spacing: 0.03em; margin: 0 0 4px 0; padding: 0;
    }}
    .page-subtitle {{font-size: 12px; color: {p["cinza"]}; margin: 0 0 12px 0;}}
    .source-label {{font-size: 10px; color: {p["cinza"]}; font-family: monospace;}}
    .freshness-ok {{font-size: 11px; color: {p["cinza"]}; margin-bottom: 12px;}}
    .freshness-warn {{
        font-size: 11px; color: #92400e; background: #fef3c7; padding: 6px 10px;
        border-radius: 4px; margin-bottom: 12px; border-left: 3px solid #d97706;
    }}

    .st-key-navbar {{
        background: {p["branco"]}; padding: 8px 24px 8px 24px;
        margin: 0 -1rem 0.8rem -1rem; border-bottom: 1px solid {p["cinza_cl"]};
    }}
    .st-key-navbar [data-testid="stPageLink-NavLink"] {{
        background: transparent; border: 1.5px solid {p["azul"]}; border-radius: 6px;
        padding: 7px 18px; color: {p["azul_esc"]} !important; font-weight: 600; font-size: 13px;
        letter-spacing: 0.03em; text-decoration: none !important; transition: all 0.2s ease;
    }}
    .st-key-navbar [data-testid="stPageLink-NavLink"] span {{color: {p["azul_esc"]} !important;}}
    .st-key-navbar [data-testid="stPageLink-NavLink"]:hover {{
        background: {p["cinza_bg"]}; border-color: {p["azul_esc"]};
    }}
    .st-key-navbar [data-testid="stPageLink-NavLink"][aria-current="page"] {{
        background: {p["azul_esc"]}; color: {p["branco"]} !important; border-color: {p["azul_esc"]};
    }}
    .st-key-navbar [data-testid="stPageLink-NavLink"][aria-current="page"] span {{
        color: {p["branco"]} !important;
    }}
    </style>
    """
