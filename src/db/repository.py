"""DAO unico do projeto. Todo write e todo read de dado real passam por aqui.

Upsert idempotente via `INSERT OR REPLACE` sobre PK natural — rodar o mesmo
ingest N vezes produz o mesmo banco. Nenhuma query e montada por f-string
com valor de usuario; tudo parametrizado.
"""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

import pandas as pd

from src.db.engine import apply_schema, get_connection


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _d(v: date | str | None) -> str | None:
    if v is None:
        return None
    return v.isoformat() if isinstance(v, date) else v


@dataclass(frozen=True)
class Cobertura:
    codigo: str
    n_obs: int
    primeira_data: str | None
    ultima_data: str | None


@dataclass(frozen=True)
class IngestLogEntry:
    fonte: str
    data_alvo: str | None
    started_at: str
    finished_at: str | None
    status: str  # ok | vazio | erro_http | erro_parse | skip
    http_status: int | None = None
    bytes_baixados: int | None = None
    linhas_parsed: int | None = None
    linhas_upsert: int | None = None
    mensagem: str | None = None
    payload_sha256: str | None = None


def sha256_of(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


class Repository:
    def __init__(self, conn: sqlite3.Connection | None = None):
        self.conn = conn or get_connection()
        apply_schema(self.conn)

    def close(self) -> None:
        self.conn.close()

    # ------------------------------------------------------------------
    # Upsert generico
    # ------------------------------------------------------------------

    def _upsert_rows(self, table: str, rows: list[dict[str, Any]]) -> int:
        if not rows:
            return 0
        cols = list(rows[0].keys())
        placeholders = ", ".join("?" for _ in cols)
        col_list = ", ".join(cols)
        sql = f"INSERT OR REPLACE INTO {table} ({col_list}) VALUES ({placeholders})"
        values = [tuple(r[c] for c in cols) for r in rows]
        cur = self.conn.executemany(sql, values)
        self.conn.commit()
        return cur.rowcount if cur.rowcount is not None else len(rows)

    # ------------------------------------------------------------------
    # Escrita — REUNE
    # ------------------------------------------------------------------

    def upsert_reune(self, ativos: list[Any], data_referencia: date) -> int:
        """`ativos` e uma lista de AtivoReune (src.parsers.reune_txt)."""
        now = _now_iso()
        rows = [
            {
                "data_referencia": _d(data_referencia),
                "codigo": a.codigo,
                "nome_anbima": a.nome_anbima,
                "data_repac_venc": _d(a.data_repac_venc),
                "indexador": a.indexador,
                "spread_emissao": a.spread_emissao,
                "percentual_di": a.percentual_di,
                "convencao_taxa": a.convencao_taxa,
                "taxa_compra": a.taxa_compra,
                "taxa_venda": a.taxa_venda,
                "taxa_indicativa": a.taxa_indicativa,
                "desvio_padrao": a.desvio_padrao,
                "intervalo_min": a.intervalo_min,
                "intervalo_max": a.intervalo_max,
                "pu": a.pu,
                "pct_pu_par": a.pct_pu_par,
                "duration_du": a.duration_du,
                "pct_reune": a.pct_reune,
                "ref_ntnb_venc": _d(a.ref_ntnb_venc),
                "flag_resgate": int(a.flag_resgate),
                "flag_exercicio": int(a.flag_exercicio),
                "ingested_at": now,
            }
            for a in ativos
        ]
        return self._upsert_rows("fato_reune", rows)

    # ------------------------------------------------------------------
    # Escrita — ETTJ
    # ------------------------------------------------------------------

    def upsert_curva(self, ettj_result: Any) -> int:
        """`ettj_result` e um EttjParseResult (src.parsers.ettj_csv)."""
        now = _now_iso()
        d = _d(ettj_result.data_referencia)

        param_rows = [
            {
                "data_referencia": d,
                "curva": p.curva,
                "beta1": p.beta1,
                "beta2": p.beta2,
                "beta3": p.beta3,
                "beta4": p.beta4,
                "lambda1": p.lambda1,
                "lambda2": p.lambda2,
                "ingested_at": now,
            }
            for p in ettj_result.params
        ]
        n1 = self._upsert_rows("fato_curva_param", param_rows)

        vert_rows = [
            {
                "data_referencia": d,
                "du": v.du,
                "taxa_ipca": v.taxa_ipca,
                "taxa_pre": v.taxa_pre,
                "inflacao_impl": v.inflacao_impl,
            }
            for v in ettj_result.vertices
        ]
        n2 = self._upsert_rows("fato_curva_vertice", vert_rows)

        tpf_rows = [
            {
                "data_referencia": d,
                "titulo": r.titulo,
                "codigo_selic": r.codigo_selic,
                "data_vencimento": _d(r.data_vencimento),
                "taxa_indicativa": None,
                "residuo": r.residuo,
                "du_ate_venc": None,
            }
            for r in ettj_result.residuos
        ]
        n3 = self._upsert_rows("fato_tpf", tpf_rows)

        return n1 + n2 + n3

    # ------------------------------------------------------------------
    # Escrita — cadastro SND
    # ------------------------------------------------------------------

    def upsert_cadastro(self, ativos: list[Any], snapshot: date, cnpj_incentivada_map=None) -> int:
        """`ativos` e uma lista de AtivoSnd (src.parsers.snd_tsv)."""
        rows = [
            {
                "codigo": a.codigo,
                "snapshot_date": _d(snapshot),
                "empresa": a.empresa,
                "cnpj": a.cnpj,
                "isin": a.isin,
                "situacao": a.situacao,
                "serie": a.serie,
                "emissao": a.emissao,
                "data_emissao": _d(a.data_emissao),
                "data_vencimento": _d(a.data_vencimento),
                "data_prox_repac": _d(a.data_prox_repac),
                "forma": a.forma,
                "especie_garantia": a.especie_garantia,
                "indexador_cad": a.indexador_cad,
                "percentual_rentab": a.percentual_rentab,
                "quantidade_emitida": a.quantidade_emitida,
                "quantidade_mercado": a.quantidade_mercado,
                "valor_nominal_emis": a.valor_nominal_emissao,
                "valor_nominal_atual": a.valor_nominal_atual,
                "data_ult_vna": _d(a.data_ult_vna),
                "incentivada_12431": int(a.incentivada_12431),
                "resgate_antecipado": int(a.resgate_antecipado),
                "juros_taxa": a.juros_taxa,
                "juros_prazo": a.juros_prazo,
                "juros_cada": a.juros_cada,
                "juros_unidade": a.juros_unidade,
                "juros_carencia": a.juros_carencia,
                "juros_criterio": a.juros_criterio,
                "juros_tipo": a.juros_tipo,
                "amort_taxa": a.amort_taxa,
                "amort_cada": a.amort_cada,
                "amort_unidade": a.amort_unidade,
                "amort_carencia": a.amort_carencia,
                "amort_tipo": a.amort_tipo,
            }
            for a in ativos
        ]
        return self._upsert_rows("dim_ativo", rows)

    def upsert_setor(self, cnpj_raiz: str, cnae_codigo: str | None, cnae_desc: str | None,
                      setor: str | None, fonte: str) -> None:
        self._upsert_rows(
            "dim_setor",
            [{
                "cnpj_raiz": cnpj_raiz,
                "cnae_codigo": cnae_codigo,
                "cnae_desc": cnae_desc,
                "setor": setor,
                "fonte": fonte,
                "atualizado_em": _d(date.today()),
            }],
        )

    def upsert_setor_bulk(self, rows: list[dict[str, Any]]) -> int:
        for r in rows:
            r.setdefault("atualizado_em", _d(date.today()))
        return self._upsert_rows("dim_setor", rows)

    # ------------------------------------------------------------------
    # Escrita — macro e spread derivado
    # ------------------------------------------------------------------

    def upsert_macro(self, serie_id: str, serie: pd.Series) -> int:
        rows = [
            {"serie_id": serie_id, "data": _d(idx), "valor": float(val)}
            for idx, val in serie.items()
            if pd.notna(val)
        ]
        return self._upsert_rows("fato_macro", rows)

    def upsert_spread(self, rows: list[dict[str, Any]]) -> int:
        for r in rows:
            r["data_referencia"] = _d(r["data_referencia"])
        return self._upsert_rows("fato_spread", rows)

    # ------------------------------------------------------------------
    # Log de ingestao
    # ------------------------------------------------------------------

    def log_ingest(self, entry: IngestLogEntry) -> None:
        self.conn.execute(
            """INSERT INTO ingest_log
               (fonte, data_alvo, started_at, finished_at, status, http_status,
                bytes_baixados, linhas_parsed, linhas_upsert, mensagem, payload_sha256)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                entry.fonte, entry.data_alvo, entry.started_at, entry.finished_at,
                entry.status, entry.http_status, entry.bytes_baixados,
                entry.linhas_parsed, entry.linhas_upsert, entry.mensagem,
                entry.payload_sha256,
            ),
        )
        self.conn.commit()

    # ------------------------------------------------------------------
    # Leitura
    # ------------------------------------------------------------------

    def get_reune_dia(self, d: date, indexador: str | None = None) -> pd.DataFrame:
        sql = "SELECT * FROM fato_reune WHERE data_referencia = ?"
        params: list[Any] = [_d(d)]
        if indexador:
            sql += " AND indexador = ?"
            params.append(indexador)
        return pd.read_sql_query(sql, self.conn, params=params)

    def get_reune_serie(self, codigos: list[str], inicio: date, fim: date) -> pd.DataFrame:
        if not codigos:
            return pd.DataFrame()
        placeholders = ", ".join("?" for _ in codigos)
        sql = f"""SELECT * FROM fato_reune
                  WHERE codigo IN ({placeholders})
                    AND data_referencia BETWEEN ? AND ?
                  ORDER BY data_referencia"""
        params = [*codigos, _d(inicio), _d(fim)]
        return pd.read_sql_query(sql, self.conn, params=params)

    def get_universo(
        self,
        data_ref: date | None = None,
        indexador: str | None = None,
        incentivada: bool | None = None,
        dur_min: float | None = None,
        dur_max: float | None = None,
    ) -> pd.DataFrame:
        """JOIN v_ativo_atual + fato_reune(data_ref mais recente ou pedida)
        + fato_spread + dim_setor via CNPJ."""
        if data_ref is None:
            row = self.conn.execute(
                "SELECT MAX(data_referencia) AS d FROM fato_reune"
            ).fetchone()
            if row is None or row["d"] is None:
                return pd.DataFrame()
            data_ref_s = row["d"]
        else:
            data_ref_s = _d(data_ref)

        sql = """
            SELECT
                r.data_referencia, r.codigo, r.indexador, r.convencao_taxa,
                r.spread_emissao, r.percentual_di, r.taxa_indicativa,
                r.taxa_compra, r.taxa_venda, r.duration_du, r.pu, r.pct_pu_par,
                r.desvio_padrao, r.pct_reune, r.ref_ntnb_venc,
                r.flag_resgate, r.flag_exercicio,
                a.empresa, a.cnpj, a.especie_garantia, a.situacao,
                a.incentivada_12431, a.data_vencimento AS venc_cadastro,
                s.setor, s.fonte AS setor_fonte,
                sp.z_spread_bruto, sp.z_spread_grossup, sp.metodo_grossup, sp.regime_ir
            FROM fato_reune r
            LEFT JOIN v_ativo_atual a ON a.codigo = r.codigo
            LEFT JOIN dim_setor s ON s.cnpj_raiz = substr(a.cnpj, 1, 8)
            LEFT JOIN fato_spread sp
                ON sp.codigo = r.codigo AND sp.data_referencia = r.data_referencia
            WHERE r.data_referencia = ?
        """
        params: list[Any] = [data_ref_s]
        if indexador:
            sql += " AND r.indexador = ?"
            params.append(indexador)
        if incentivada is not None:
            sql += " AND a.incentivada_12431 = ?"
            params.append(int(incentivada))
        if dur_min is not None:
            sql += " AND r.duration_du >= ?"
            params.append(dur_min * 252)
        if dur_max is not None:
            sql += " AND r.duration_du <= ?"
            params.append(dur_max * 252)

        return pd.read_sql_query(sql, self.conn, params=params)

    def get_curva_vertices(self, d: date) -> pd.DataFrame:
        return pd.read_sql_query(
            "SELECT * FROM fato_curva_vertice WHERE data_referencia = ? ORDER BY du",
            self.conn, params=[_d(d)],
        )

    def get_curva_param(self, d: date, curva: str) -> pd.DataFrame:
        return pd.read_sql_query(
            "SELECT * FROM fato_curva_param WHERE data_referencia = ? AND curva = ?",
            self.conn, params=[_d(d), curva],
        )

    def get_tpf_dia(self, d: date, titulo: str | None = None) -> pd.DataFrame:
        sql = "SELECT * FROM fato_tpf WHERE data_referencia = ?"
        params: list[Any] = [_d(d)]
        if titulo:
            sql += " AND titulo = ?"
            params.append(titulo)
        return pd.read_sql_query(sql, self.conn, params=params)

    def get_macro(self, serie_id: str, inicio: date | None = None,
                   fim: date | None = None) -> pd.Series:
        sql = "SELECT data, valor FROM fato_macro WHERE serie_id = ?"
        params: list[Any] = [serie_id]
        if inicio:
            sql += " AND data >= ?"
            params.append(_d(inicio))
        if fim:
            sql += " AND data <= ?"
            params.append(_d(fim))
        sql += " ORDER BY data"
        df = pd.read_sql_query(sql, self.conn, params=params)
        if df.empty:
            return pd.Series(dtype=float)
        df["data"] = pd.to_datetime(df["data"])
        return df.set_index("data")["valor"]

    def get_datas_disponiveis(self, tabela: str = "fato_reune") -> list[str]:
        if tabela not in {"fato_reune", "fato_curva_vertice", "fato_curva_param"}:
            raise ValueError(f"tabela nao permitida: {tabela}")
        rows = self.conn.execute(
            f"SELECT DISTINCT data_referencia FROM {tabela} ORDER BY data_referencia"
        ).fetchall()
        return [r["data_referencia"] for r in rows]

    def get_cobertura(self, codigo: str) -> Cobertura:
        row = self.conn.execute(
            """SELECT COUNT(*) AS n, MIN(data_referencia) AS d0, MAX(data_referencia) AS d1
               FROM fato_reune WHERE codigo = ?""",
            (codigo,),
        ).fetchone()
        return Cobertura(
            codigo=codigo, n_obs=row["n"], primeira_data=row["d0"], ultima_data=row["d1"]
        )

    def get_health(self) -> pd.DataFrame:
        sql = """
            SELECT fonte, MAX(data_alvo) AS ultima_data_alvo, MAX(finished_at) AS ultima_execucao,
                   status, COUNT(*) AS n_execucoes
            FROM ingest_log
            GROUP BY fonte, status
            ORDER BY fonte
        """
        return pd.read_sql_query(sql, self.conn)
