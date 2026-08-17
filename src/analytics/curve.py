"""Curvas de juros: flat forward (mercado) e Svensson (ANBIMA/ETTJ).

flat_forward_interpolate e generate_interpolated_curve foram movidos
intactos de src/interpolation.py — logica identica, unico modulo puro e
correto do projeto original.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd


def flat_forward_interpolate(vertices: list[tuple[int, float]], du_target: int) -> float:
    """Interpola taxa via flat forward (padrao de mercado, base 252).

    Args:
        vertices: lista ordenada de (du, taxa%)
        du_target: dias uteis alvo

    Returns:
        Taxa interpolada em %.
    """
    if not vertices:
        raise ValueError("vertices nao pode ser vazio")
    if du_target <= 0:
        raise ValueError(f"du_target deve ser positivo, recebido {du_target}")

    vertices = sorted(vertices)

    if du_target <= vertices[0][0]:
        return vertices[0][1]
    if du_target >= vertices[-1][0]:
        return vertices[-1][1]

    for du_v, rate_v in vertices:
        if du_target == du_v:
            return rate_v

    for i in range(len(vertices) - 1):
        du_short, r_short_pct = vertices[i]
        du_long, r_long_pct = vertices[i + 1]

        if du_short < du_target <= du_long:
            r_short = r_short_pct / 100.0
            r_long = r_long_pct / 100.0

            acc_short = (1 + r_short) ** (du_short / 252.0)
            acc_long = (1 + r_long) ** (du_long / 252.0)

            fwd = (acc_long / acc_short) ** (252.0 / (du_long - du_short)) - 1
            acc_target = acc_short * (1 + fwd) ** ((du_target - du_short) / 252.0)
            rate = acc_target ** (252.0 / du_target) - 1

            return rate * 100.0

    return vertices[-1][1]


def generate_interpolated_curve(
    vertices: list[tuple[int, float]], n_points: int = 100
) -> pd.DataFrame:
    """Gera N pontos interpolados ao longo da curva. Colunas: du, anos, taxa."""
    if not vertices:
        return pd.DataFrame(columns=["du", "anos", "taxa"])

    vertices = sorted(vertices)
    du_min, du_max = vertices[0][0], vertices[-1][0]

    dus = np.unique(np.round(np.linspace(du_min, du_max, n_points)).astype(int))

    rows = []
    for du in dus:
        taxa = flat_forward_interpolate(vertices, int(du))
        rows.append({"du": int(du), "anos": round(du / 252, 2), "taxa": round(taxa, 4)})

    return pd.DataFrame(rows)


def implied_inflation(taxa_pre: float, taxa_ipca: float) -> float:
    """Inflacao implicita via Fisher: (1+pre)/(1+ipca) - 1, em %.

    Usado como checagem de regressao contra a coluna 'Inflacao Implicita'
    que a propria ANBIMA ja publica na ETTJ — nao mais a fonte primaria.
    """
    denom = 1 + taxa_ipca / 100
    if abs(denom) < 1e-10:
        raise ValueError("taxa_ipca invalida (denominador proximo de zero)")
    return ((1 + taxa_pre / 100) / denom - 1) * 100


def _svensson_f(x: float) -> float:
    if abs(x) < 1e-12:
        return 1.0  # limite de (1-e^-x)/x quando x->0
    return (1 - math.exp(-x)) / x


def svensson_rate(
    beta1: float, beta2: float, beta3: float, beta4: float,
    lambda1: float, lambda2: float, du: int,
) -> float:
    """Avalia a curva ANBIMA (Svensson, 6 parametros) no DU informado.

    r(tau) = b1 + b2*f(l1*tau) + b3*g(l1*tau) + b4*g(l2*tau)
    f(x) = (1-e^-x)/x ; g(x) = f(x) - e^-x ; tau em anos (DU/252)
    Retorna a taxa em % a.a. (os betas da ETTJ vem em decimal).
    """
    tau = du / 252.0
    x1 = lambda1 * tau
    x2 = lambda2 * tau
    f1 = _svensson_f(x1)
    g1 = f1 - math.exp(-x1)
    f2 = _svensson_f(x2)
    g2 = f2 - math.exp(-x2)

    r = beta1 + beta2 * f1 + beta3 * g1 + beta4 * g2
    return r * 100.0
