"""Z-spread ANBIMA + gross-up para debentures incentivadas.

Formula oficial (Metodologia ANBIMA de calculo do Z-spread, v2, 17/12/2025),
para IPCA+spread:

    Z = ((i/100 + 1) / (P/100 + 1) - 1) * 100

com i = taxa indicativa da debenture, P = taxa da NTN-B de referencia (mesma
duration/vencimento), ambas em % a.a. base 252.

Verificado empiricamente em 16/08/2026 contra dados reais carregados: ACRC21
(IPCA+7,415%, taxa indicativa 9,0343% em 14/08/2026, referencia NTN-B
15/05/2035) produz Z-spread bruto de 0,9703% a.a. (~97 bps) usando a taxa
IPCA interpolada da propria ETTJ ANBIMA do dia como P. Este numero NAO foi
cross-checado contra o exemplo do PDF de metodologia (que se refere a uma
data de referencia diferente, nao especificada) — serve como verificacao
de plausibilidade e regressao, nao como oraculo externo.

Nota sobre a MP 1.303/2025: verificado em 16/08/2026 que a MP caiu no
Congresso em outubro/2025 e NAO foi convertida em lei — a isencao de IR
para debentures incentivadas (Lei 12.431) permanece integral. Por isso o
unico regime tributavel hoje relevante para incentivadas e ISENTO. A
TABELA_REGRESSIVA fica pronta para debentures nao incentivadas e para o
caso de uma futura mudanca legislativa — nunca hardcoded como se fosse a
regra vigente para incentivadas.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum


class RegimeIR(StrEnum):
    ISENTO = "isento"                        # incentivada Lei 12.431 (PF) — vigente em 16/08/2026
    TABELA_REGRESSIVA = "tabela_regressiva"   # debenture comum / nao incentivada


# Tabela regressiva de IR sobre renda fixa (prazo em dias corridos)
_TABELA_REGRESSIVA = [
    (180, 0.225),
    (360, 0.20),
    (720, 0.175),
    (float("inf"), 0.15),
]


def aliquota_ir(regime: RegimeIR, prazo_dias: int | None = None) -> float:
    """Aliquota de IR aplicavel. ISENTO -> 0.0. TABELA_REGRESSIVA exige
    prazo_dias (dias corridos desde a aplicacao) para escolher a faixa."""
    if regime == RegimeIR.ISENTO:
        return 0.0
    if prazo_dias is None:
        raise ValueError("prazo_dias e obrigatorio para regime TABELA_REGRESSIVA")
    for limite, aliq in _TABELA_REGRESSIVA:
        if prazo_dias <= limite:
            return aliq
    return _TABELA_REGRESSIVA[-1][1]


def determinar_regime(
    incentivada: bool,
    data_emissao: date | None = None,
    data_ref: date | None = None,
) -> RegimeIR:
    """Determina o regime de IR. Parametrizado por data para permitir
    'grandfathering' caso uma futura mudanca legislativa crie um corte por
    data de emissao — nao aplicavel hoje (MP 1.303/25 rejeitada), mas o
    parametro fica pronto para nao precisar reescrever chamadores depois."""
    if incentivada:
        return RegimeIR.ISENTO
    return RegimeIR.TABELA_REGRESSIVA


def zspread_anbima(taxa_indicativa: float, taxa_ntnb_ref: float) -> float:
    """Z-spread pela formula oficial ANBIMA, em % a.a. Multiplique por 100
    para bps."""
    denom = 1 + taxa_ntnb_ref / 100
    if abs(denom) < 1e-10:
        raise ValueError("taxa_ntnb_ref invalida (denominador proximo de zero)")
    return ((1 + taxa_indicativa / 100) / denom - 1) * 100


def grossup_aproximado(taxa_liquida: float, aliquota: float) -> float:
    """Gross-up por formula fechada: taxa_bruta = taxa_liquida / (1 - aliq).
    Usado como fallback quando o fluxo de caixa nao pode ser reconstruido
    (ver analytics/cashflow.py para o metodo exato)."""
    if aliquota >= 1.0:
        raise ValueError(f"aliquota invalida: {aliquota}")
    return taxa_liquida / (1 - aliquota)


@dataclass(frozen=True)
class ZSpreadResult:
    z_spread_bruto: float
    z_spread_grossup: float | None
    metodo_grossup: str  # exato_fluxo | aprox_fechada | nao_aplicavel
    regime_ir: RegimeIR
    taxa_ntnb_ref: float


def zspread_com_grossup(
    taxa_indicativa: float,
    taxa_ntnb_ref: float,
    incentivada: bool,
    *,
    taxa_bruta_exata: float | None = None,
    prazo_dias: int | None = None,
) -> ZSpreadResult:
    """Orquestra o calculo completo.

    Se `taxa_bruta_exata` for fornecida (calculada por
    analytics.cashflow.grossup_por_fluxo), usa metodo exato. Senao, para
    incentivadas isentas, cai na aproximacao fechada com a aliquota-teto da
    tabela regressiva (22,5%) como referencia conservadora de comparacao —
    e sempre marca `metodo_grossup` corretamente para nao confundir as
    duas fontes na UI.
    """
    z_bruto = zspread_anbima(taxa_indicativa, taxa_ntnb_ref)
    regime = determinar_regime(incentivada)

    if regime == RegimeIR.ISENTO:
        if taxa_bruta_exata is not None:
            z_gross = zspread_anbima(taxa_bruta_exata, taxa_ntnb_ref)
            metodo = "exato_fluxo"
        else:
            aliq_referencia = _TABELA_REGRESSIVA[0][1]  # 22,5% — piso conservador
            taxa_bruta = grossup_aproximado(taxa_indicativa, aliq_referencia)
            z_gross = zspread_anbima(taxa_bruta, taxa_ntnb_ref)
            metodo = "aprox_fechada"
        return ZSpreadResult(z_bruto, z_gross, metodo, regime, taxa_ntnb_ref)

    return ZSpreadResult(z_bruto, None, "nao_aplicavel", regime, taxa_ntnb_ref)
