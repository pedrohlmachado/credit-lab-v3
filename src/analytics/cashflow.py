"""Reconstrucao do fluxo de caixa de uma debenture a partir do cadastro SND.

Modulo puro: sem I/O, sem streamlit, sem banco. Le apenas os campos ja
parseados de `src.parsers.snd_tsv.AtivoSnd` (ou qualquer objeto com os mesmos
atributos — os testes usam tambem `types.SimpleNamespace`).

Limitacao conhecida: nao ha calendario de feriados/dias uteis brasileiro
neste modulo (isso pertenceria a uma camada de dados, nao a analytics puro).
`precificar_fluxo` aproxima dias uteis por `dias_corridos * 252/365`, e a
geracao de datas de cupom ignora o `juros_criterio` ('Util'/'Corrido') —
sempre anda em meses corridos a partir da data de emissao. Para debentures
de prazo longo (ex. 20 anos) isso acumula um desvio de poucos dias uteis
por periodo, que se traduz em divergencia de PU maior do que se teria com
o calendario ANBIMA/B3 real. `validar_contra_pu` existe justamente para
medir essa divergencia contra o PU publicado (oraculo gratuito).
"""

from __future__ import annotations

import calendar
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime

MAX_FLUXOS = 200  # limite de seguranca contra parametro de periodicidade corrompido


@dataclass(frozen=True)
class CashFlow:
    data: date
    tipo: str  # 'juros' | 'amortizacao' | 'juros_e_principal'
    valor_pct_vne: float  # valor do fluxo como fracao do VNE/VNA na data (1.0 = 100%)
    # Componente de juros isolado (fracao do VNA). Para tipo='amortizacao' e 0.0;
    # para 'juros' e igual a valor_pct_vne; para 'juros_e_principal' e a parte
    # que corresponde a juros (o resto e amortizacao de principal). Existe para
    # permitir que `grossup_por_fluxo` aplique IR apenas sobre juros, nunca
    # sobre principal — informacao que se perderia se o CashFlow guardasse so
    # o total combinado.
    juros_pct_vne: float = 0.0


@dataclass(frozen=True)
class CashFlowSchedule:
    codigo: str
    fluxos: list[CashFlow]
    indexador: str
    completo: bool  # False se faltaram campos ou o padrao nao pode ser reconstruido com confianca
    avisos: list[str]


def _add_months(d: date, months: int) -> date:
    """Soma `months` meses a `d`, ajustando o dia se o mes destino for mais
    curto (ex.: 31/01 + 1 mes -> 28/02 ou 29/02)."""
    total = d.month - 1 + months
    year = d.year + total // 12
    month = total % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _parse_data_flexivel(v: object) -> date | None:
    """Aceita tanto `date` quanto string 'DD/MM/AAAA' (formato bruto do SND,
    ex. `AtivoSnd.amort_carencia`/`juros_carencia`, que sao `str`, nao `date`).
    Tokens vazios/'-' -> None."""
    if isinstance(v, date):
        return v
    if isinstance(v, str):
        v = v.strip()
        if not v or v == "-":
            return None
        try:
            return datetime.strptime(v, "%d/%m/%Y").date()
        except ValueError:
            return None
    return None


def _gerar_datas_pagamento(
    data_emissao: date, data_vencimento: date, step_meses: int
) -> tuple[list[date] | None, list[str]]:
    """Gera as datas de pagamento de juros de `data_emissao` (exclusive) ate
    `data_vencimento` (inclusive), em passos de `step_meses`. A ultima data e
    sempre `data_vencimento` — se a periodicidade nao bater exatamente nela,
    a ultima data intermediaria e descartada e substituida, com aviso.
    Retorna (None, avisos) se o limite de seguranca MAX_FLUXOS for excedido."""
    datas: list[date] = []
    avisos: list[str] = []
    d = data_emissao
    while True:
        d = _add_months(d, step_meses)
        if d >= data_vencimento:
            break
        datas.append(d)
        if len(datas) >= MAX_FLUXOS:
            return None, [
                f"limite_de_seguranca_excedido: mais de {MAX_FLUXOS} fluxos gerados "
                "— parametro de periodicidade provavelmente corrompido"
            ]

    if d != data_vencimento:
        avisos.append(
            "ultimo_periodo_irregular: periodicidade de juros nao alinha exatamente "
            "com data_vencimento — ultima data ajustada"
        )
    datas.append(data_vencimento)
    return datas, avisos


def _fracoes_amortizacao(
    ativo: object, payment_dates: list[date], data_emissao: date, data_vencimento: date
) -> dict[date, float]:
    """Fracao do principal ORIGINAL (VNE=1.0) amortizada em cada data de
    pagamento, ANTES da amortizacao final (bullet) do saldo remanescente —
    ver `build_schedule`. Retorna {} (amortizacao unica no vencimento) se
    `amort_taxa` for None/ausente ou `amort_cada` for None/zero, conforme a
    regra de robustez do enunciado.

    Best-effort: como as datas de amortizacao podem ter periodicidade
    diferente das de juros, cada data de amortizacao e 'encaixada' na
    primeira data de pagamento de juros igual ou posterior a ela — este
    modulo nao gera fluxos de amortizacao pura fora do calendario de juros.
    """
    amort_taxa = getattr(ativo, "amort_taxa", None)
    amort_cada = getattr(ativo, "amort_cada", None)
    if amort_taxa is None or not amort_cada:
        return {}

    amort_unidade = getattr(ativo, "amort_unidade", None)
    unidade_norm = amort_unidade if amort_unidade in ("MES", "ANO") else "MES"
    step = amort_cada if unidade_norm == "MES" else amort_cada * 12
    if step <= 0:
        return {}

    inicio = _parse_data_flexivel(getattr(ativo, "amort_carencia", None)) or data_emissao

    fracoes: dict[date, float] = {}
    d = inicio
    contador = 0
    while True:
        d = _add_months(d, step)
        if d >= data_vencimento:
            break
        alvo = next((p for p in payment_dates if p >= d), None)
        if alvo is not None:
            fracoes[alvo] = fracoes.get(alvo, 0.0) + amort_taxa / 100
        contador += 1
        if contador >= MAX_FLUXOS:
            break
    return fracoes


def build_schedule(ativo: object, data_ref: date) -> CashFlowSchedule:
    """Reconstroi o cronograma de pagamento de `ativo` (uma instancia de
    `AtivoSnd`, ou objeto com os mesmos atributos) de `data_emissao` ate
    `data_vencimento`.

    Periodicidade de juros: `juros_cada` + `juros_unidade` ('MES'/'ANO').
    Taxa por periodo via juros composto:
        taxa_periodo = (1 + juros_taxa/100) ** (meses_periodo/12) - 1
    aplicada sobre o saldo de principal remanescente (1.0 no inicio).

    Amortizacao: se `amort_taxa` for None (ou `amort_cada` ausente/zero),
    assume amortizacao unica (bullet) — o saldo inteiro retorna na ultima
    data, combinado com o ultimo cupom (`CashFlow` tipo 'juros_e_principal').
    Caso contrario, amortiza `amort_taxa`% do saldo em cada data de
    amortizacao (ver `_fracoes_amortizacao`), sempre preservando o retorno
    do saldo remanescente na ultima data.

    `data_ref` nao afeta a geracao do cronograma (que e uma propriedade do
    ativo, nao do dia de calculo) — existe na assinatura para uso simetrico
    com `precificar_fluxo`/`validar_contra_pu`/`grossup_por_fluxo`, todas
    consumidoras de `CashFlowSchedule`.

    Nunca lanca excecao para dado incompleto: sempre retorna
    `completo=False` com o motivo em `avisos`.
    """
    codigo = getattr(ativo, "codigo", "") or ""
    indexador = getattr(ativo, "indexador_cad", "") or ""

    juros_taxa = getattr(ativo, "juros_taxa", None)
    data_emissao = getattr(ativo, "data_emissao", None)
    data_vencimento = getattr(ativo, "data_vencimento", None)
    if juros_taxa is None or data_emissao is None or data_vencimento is None:
        return CashFlowSchedule(
            codigo, [], indexador, False,
            ["campos obrigatorios ausentes (juros_taxa/data_emissao/data_vencimento)"],
        )

    juros_cada = getattr(ativo, "juros_cada", None)
    if not juros_cada:
        return CashFlowSchedule(
            codigo, [], indexador, False, ["juros_cada ausente ou zero — periodicidade indefinida"]
        )

    avisos: list[str] = []
    completo = True
    juros_unidade = getattr(ativo, "juros_unidade", None)
    if juros_unidade not in ("MES", "ANO"):
        avisos.append(f"juros_unidade '{juros_unidade}' nao reconhecida — assumindo 'MES'")
        juros_unidade = "MES"
        completo = False

    step_meses = juros_cada if juros_unidade == "MES" else juros_cada * 12
    if step_meses <= 0:
        return CashFlowSchedule(
            codigo, [], indexador, False, avisos + ["periodicidade de juros invalida (<=0)"]
        )

    datas, avisos_datas = _gerar_datas_pagamento(data_emissao, data_vencimento, step_meses)
    avisos.extend(avisos_datas)
    if datas is None:
        return CashFlowSchedule(codigo, [], indexador, False, avisos)
    if any("ultimo_periodo_irregular" in a for a in avisos_datas):
        completo = False

    fracoes_amort = _fracoes_amortizacao(ativo, datas, data_emissao, data_vencimento)
    taxa_periodo = (1 + juros_taxa / 100) ** (step_meses / 12) - 1

    fluxos: list[CashFlow] = []
    saldo = 1.0
    ultimo_indice = len(datas) - 1
    for i, d in enumerate(datas):
        juros_valor = saldo * taxa_periodo
        amort_valor = min(fracoes_amort.get(d, 0.0), saldo)
        if i == ultimo_indice:
            amort_valor = saldo  # devolve todo o saldo remanescente no vencimento
        saldo -= amort_valor

        if amort_valor > 1e-12 and juros_valor > 1e-12:
            tipo = "juros_e_principal"
        elif amort_valor > 1e-12:
            tipo = "amortizacao"
        else:
            tipo = "juros"
        fluxos.append(CashFlow(d, tipo, juros_valor + amort_valor, juros_valor))

    return CashFlowSchedule(codigo, fluxos, indexador, completo, avisos)


def precificar_fluxo(
    schedule: CashFlowSchedule, taxa_desconto_pct: float, data_ref: date
) -> float:
    """PU teorico (base 100, comparavel a PU par) = soma dos fluxos futuros
    (data > data_ref) descontados exponencialmente por `taxa_desconto_pct`
    (% a.a. base 252). Sem calendario de feriados: du e aproximado por
    `dias_corridos * 252/365`."""
    soma = 0.0
    for fluxo in schedule.fluxos:
        if fluxo.data <= data_ref:
            continue
        dias_corridos = (fluxo.data - data_ref).days
        du = dias_corridos * 252 / 365
        fator = (1 + taxa_desconto_pct / 100) ** (-du / 252)
        soma += fluxo.valor_pct_vne * 100 * fator
    return soma


def validar_contra_pu(
    schedule: CashFlowSchedule,
    taxa_indicativa_pct: float,
    pu_publicado: float,
    data_ref: date,
    tolerancia_pct: float = 5.0,
) -> tuple[bool, float]:
    """Reprecifica `schedule` pela taxa indicativa do REUNE e compara com o
    PU publicado (mesma linha do REUNE — normalize antes se `pu_publicado`
    nao estiver em base 100, ex. use `pct_pu_par` em vez do `pu` em R$).
    Oraculo de teste gratuito: se o fluxo reconstruido bate com o PU real da
    ANBIMA, a reconstrucao esta correta."""
    pu_calculado = precificar_fluxo(schedule, taxa_indicativa_pct, data_ref)
    if pu_publicado == 0:
        return False, float("inf")
    divergencia_pct = abs(pu_calculado - pu_publicado) / pu_publicado * 100
    return divergencia_pct <= tolerancia_pct, divergencia_pct


def _aplicar_ir(schedule: CashFlowSchedule, aliquota_ir: float) -> CashFlowSchedule:
    """Fluxo tributado: cada cupom de juros perde `aliquota_ir` (amortizacao
    de principal nunca e tributada). Usa `CashFlow.juros_pct_vne` para isolar
    exatamente a parte de juros de cada fluxo, mesmo nos combinados
    'juros_e_principal'."""
    novos = [
        CashFlow(
            f.data,
            f.tipo,
            f.juros_pct_vne * (1 - aliquota_ir) + (f.valor_pct_vne - f.juros_pct_vne),
            f.juros_pct_vne * (1 - aliquota_ir),
        )
        for f in schedule.fluxos
    ]
    return CashFlowSchedule(
        schedule.codigo, novos, schedule.indexador, schedule.completo, schedule.avisos
    )


def _bissecao(
    f: Callable[[float], float], lo: float, hi: float, tol: float = 1e-6, max_iter: int = 200
) -> float:
    """Fallback sem scipy: bisseccao manual assumindo f(lo) e f(hi) com
    sinais opostos (garantido pelo chamador)."""
    f_lo = f(lo)
    for _ in range(max_iter):
        mid = (lo + hi) / 2
        f_mid = f(mid)
        if abs(f_mid) < tol or (hi - lo) < 1e-9:
            return mid
        if f_lo * f_mid <= 0:
            hi = mid
        else:
            lo, f_lo = mid, f_mid
    return (lo + hi) / 2


def grossup_por_fluxo(
    schedule: CashFlowSchedule, taxa_liquida_pct: float, aliquota_ir: float, data_ref: date
) -> float | None:
    """Gross-up exato via reconstrucao de fluxo. Retorna a taxa bruta anual
    (% a.a.) tal que um investidor tributado a `aliquota_ir`, pagando o
    preco desse fluxo bruto descontado a propria taxa bruta, realiza
    liquido o mesmo retorno que `taxa_liquida_pct` (o que um investidor
    isento obteria).

    Metodo (equivalente a resolver o IRR liquido do investidor tributado,
    mas resolvido em um unico passo por monotonicidade da funcao de preco):
    1. `referencia` = preco do fluxo TRIBUTADO (juros liquidos de IR,
       principal intacto) descontado a `taxa_liquida_pct` — e o preco que
       um investidor tributado precisaria pagar, ao receber fluxo liquido,
       para realizar exatamente `taxa_liquida_pct` de retorno liquido.
    2. Busca a taxa bruta candidata x tal que o preco do fluxo BRUTO
       (contratual, sem imposto) descontado a x reproduza `referencia` —
       isto e, o preco de mercado desse titulo tributavel, cotado a x,
       coincide com o preco que entrega o retorno liquido-alvo.

    Nota de design: preservar a invariante financeira "taxa bruta sempre
    maior que taxa liquida" (verificavel com `grossup_aproximado` em
    zspread.py) foi tratado como requisito mais forte do que uma leitura
    literal alternativa (tributar e descontar o MESMO fluxo pela MESMA
    taxa candidata) — essa leitura alternativa produz raiz MENOR que a
    taxa liquida (verificado numericamente), o que contraria o proprio
    conceito de gross-up.

    scipy.optimize.brentq quando disponivel, bisseccao manual como
    fallback. Retorna None se `schedule.completo` for False, se nao houver
    fluxos, ou se a busca nao convergir (nunca lanca excecao)."""
    if not schedule.completo or not schedule.fluxos:
        return None

    fluxo_tributado = _aplicar_ir(schedule, aliquota_ir)
    referencia = precificar_fluxo(fluxo_tributado, taxa_liquida_pct, data_ref)

    def objetivo(taxa_candidata: float) -> float:
        return precificar_fluxo(schedule, taxa_candidata, data_ref) - referencia

    try:
        lo = taxa_liquida_pct
        f_lo = objetivo(lo)
        if abs(f_lo) < 1e-6:
            return lo

        hi = taxa_liquida_pct * 3 if taxa_liquida_pct > 0 else taxa_liquida_pct + 10
        f_hi = objetivo(hi)
        tentativas = 0
        while f_lo * f_hi > 0 and tentativas < 6:
            hi = hi * 2 if hi != 0 else 1.0
            f_hi = objetivo(hi)
            tentativas += 1
        if f_lo * f_hi > 0:
            return None

        try:
            import scipy.optimize

            return float(scipy.optimize.brentq(objetivo, lo, hi, xtol=1e-6))
        except ImportError:
            return _bissecao(objetivo, lo, hi)
    except (ValueError, ZeroDivisionError, OverflowError):
        return None
