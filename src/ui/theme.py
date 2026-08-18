"""Tema visual Polo Capital — tokens portados de
~/.claude/skills/carreira-curriculo-teorico/assets/dossie-polo.css (unica
copia viva da identidade Polo). Consumido pelo app (via CSS inline em
streamlit_css()) e pelos graficos Plotly de cada pagina (via polo_layout()).

Restricao herdada do CSS original: paleta e tipografia apenas — sem logo da
Polo, sem apresentar o material como comunicacao institucional da empresa.

Duas decisoes que existem por causa de deploy, nao de estetica:

1. `streamlit_css()` NAO depende de `.streamlit/config.toml`. O config.toml
   e um arquivo dentro de uma pasta oculta (comeca com ponto), e o upload
   manual pela interface web do GitHub engole arquivos ocultos sem avisar —
   foi exatamente o que aconteceu no primeiro deploy deste app, que subiu
   com a cor primaria vermelha padrao do Streamlit em vez do azul Polo.
   O config.toml continua no projeto (e o jeito canonico), mas tudo que
   e visualmente critico esta replicado no CSS injetado, que vive no
   codigo Python e por isso sempre sobe junto.

2. A cascata de fontes coloca Futura primeiro (nativa do macOS, e o que o
   dono do projeto ve localmente) e Jost logo depois, carregada da Google
   Fonts. Jost e um geometrico desenhado na mesma linhagem da Futura, entao
   quem abrir o app publicado de um Windows, Linux ou celular — onde Futura
   nao existe — ve algo proximo em vez de cair num sans-serif generico.
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
    "fonte": (
        '"Futura Lt BT", "Futura", "Jost", "Century Gothic", '
        '"Avenir Next", sans-serif'
    ),
}

# Fonte web carregada para quem nao tem Futura instalada (todo mundo fora do
# macOS). Fica depois de Futura na cascata, entao nao muda nada pra quem ja
# tem a fonte nativa.
_FONTE_WEB = (
    "https://fonts.googleapis.com/css2?"
    "family=Jost:wght@300;400;500;600;700&display=swap"
)

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


def forcar_tema_polo() -> None:
    """Forca o tema Polo por codigo, sem depender de .streamlit/config.toml.

    O config.toml vive numa pasta oculta e o upload manual pro GitHub
    (interface web / Finder) engole dotfiles — o primeiro deploy deste app
    subiu sem ele. Sem config, o Streamlit segue o prefers-color-scheme do
    navegador do visitante: quem usa modo escuro ve tabela preta (o
    st.dataframe e desenhado em canvas, imune ao CSS injetado), inputs
    escuros e a cor primaria vermelha padrao.

    set_option escreve na config global do processo, mas o navegador so
    recebe o tema na proxima mensagem de sessao — por isso o rerun unico
    por sessao: ele dispara antes de qualquer conteudo ser desenhado, entao
    nao ha flash perceptivel. Da segunda sessao em diante (processo ja
    configurado) nem o rerun e necessario, mas o guard de session_state ja
    cuida disso sozinho.

    Chamar logo apos st.set_page_config(), antes de renderizar qualquer
    coisa.
    """
    import streamlit as st
    from streamlit import config as _config

    for k, v in {
        "theme.base": "light",
        "theme.primaryColor": POLO["azul"],
        "theme.backgroundColor": POLO["branco"],
        "theme.secondaryBackgroundColor": POLO["cinza_bg"],
        "theme.textColor": POLO["texto"],
    }.items():
        _config.set_option(k, v)

    if not st.session_state.get("_tema_polo_aplicado"):
        st.session_state["_tema_polo_aplicado"] = True
        st.rerun()


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
    layout de navbar customizada, e replica o que o config.toml faria
    (ver decisao 1 no docstring do modulo)."""
    p = POLO
    return f"""
    <style>
    @import url('{_FONTE_WEB}');

    #MainMenu {{visibility: hidden;}}
    footer {{visibility: hidden;}}
    header[data-testid="stHeader"] {{visibility: hidden; height: 0;}}
    [data-testid="stToolbar"] {{display: none;}}
    .block-container {{padding-top: 0rem; padding-bottom: 0rem; max-width: 100%;}}
    [data-testid="stSidebar"] {{display: none;}}
    [data-testid="stSidebarCollapsedControl"] {{display: none;}}

    /* ---- Equivalente ao [theme] do config.toml ----
       Repetido aqui porque o config.toml vive numa pasta oculta e nem
       sempre chega ao repositorio no upload manual. Sem isto, o app
       publicado cai no tema padrao do Streamlit: texto #31333F e cor
       primaria vermelha (#FF4B4B) nos widgets. */
    .stApp {{background-color: {p["branco"]}; color: {p["texto"]}; font-weight: 400;
             font-family: {p["fonte"]};}}
    /* Só em body/.stApp, deixando a herança levar cor e fonte para baixo.
       Uma regra ampla tipo `.stApp p, .stApp span` teria especificidade
       maior que `.page-title` e apagaria o azul dos títulos. */
    body {{
        color: {p["texto"]};
        font-family: {p["fonte"]};
        background-color: {p["branco"]};
    }}
    /* Os icones do Material sao ligaduras tipograficas: o glifo so aparece
       se a fonte do elemento for a "Material Symbols". Sem esta excecao a
       fonte herdada vence e o icone degrada para o nome dele em texto puro
       ("account_balance" colado no rotulo do botao). */
    [data-testid="stIconMaterial"],
    [data-testid="stIconMaterial"] * {{
        font-family: "Material Symbols Rounded", "Material Symbols Outlined" !important;
    }}
    [data-testid="stAppViewContainer"], [data-testid="stMain"] {{
        background-color: {p["branco"]};
    }}

    /* Cor primaria nos widgets nativos (radio, slider, checkbox). O
       Streamlit gera essas classes com hash instavel, entao a ancora e o
       data-testid + a posicao na arvore, que sao estaveis. */
    [data-testid="stRadioOption"][data-selected="true"] > div > div > div:first-child {{
        background-color: {p["azul"]} !important;
        border-color: {p["azul"]} !important;
    }}
    [data-testid="stSlider"] [data-baseweb="slider"] div[role="slider"] {{
        background-color: {p["azul"]} !important;
    }}
    [data-testid="stCheckbox"] input:checked + div {{
        background-color: {p["azul"]} !important;
        border-color: {p["azul"]} !important;
    }}
    a, .stApp a {{color: {p["azul_esc"]};}}

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
