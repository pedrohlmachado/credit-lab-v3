"""Formatacao de numeros em notacao brasileira."""

from __future__ import annotations

import pandas as pd


def format_br(x: float | None, decimals: int = 2) -> str:
    """1234.56 -> '1.234,56'. NaN/None -> '—'."""
    if x is None or pd.isna(x):
        return "—"
    formatted = f"{x:,.{decimals}f}"
    return formatted.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def fmt_col_num(s: pd.Series, casas: int = 2) -> pd.Series:
    """Formata uma coluna numerica como texto, com '—' no lugar de NaN.

    Necessario porque o NumberColumn nativo do st.dataframe renderiza NaN
    como o texto literal 'None' (comportamento confirmado do componente,
    nao configuravel via column_config) — visivelmente ruim quando uma
    coluna tem muitos ausentes legitimos (ex.: Z-spread so existe para
    IPCA+, %REUNE fica nulo na maioria das linhas)."""
    return s.apply(lambda v: "—" if pd.isna(v) else f"{v:.{casas}f}")


def fmt_col_pct(s: pd.Series, casas: int = 2) -> pd.Series:
    return s.apply(lambda v: "—" if pd.isna(v) else f"{v:.{casas}f}%")


def fmt_col_signed(s: pd.Series, casas: int = 0) -> pd.Series:
    return s.apply(lambda v: "—" if pd.isna(v) else f"{v:+.{casas}f}")


def fmt_col_str(s: pd.Series) -> pd.Series:
    """Coluna de texto: None -> string vazia (o st.dataframe ja renderiza
    None como 'None' em colunas de objeto tambem)."""
    return s.apply(lambda v: "" if v is None or (isinstance(v, float) and pd.isna(v)) else v)
