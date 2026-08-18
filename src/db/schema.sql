-- Schema do credit-lab. SQLite. Toda PK e natural; todo write passa pelo
-- helper de upsert em src/db/repository.py — nunca INSERT direto fora dali.

CREATE TABLE IF NOT EXISTS dim_ativo (
    codigo              TEXT NOT NULL,
    snapshot_date       TEXT NOT NULL,
    empresa             TEXT,
    cnpj                TEXT,
    isin                TEXT,
    situacao            TEXT,
    serie               TEXT,
    emissao             TEXT,
    data_emissao        TEXT,
    data_vencimento     TEXT,
    data_prox_repac     TEXT,
    forma               TEXT,
    especie_garantia    TEXT,
    indexador_cad       TEXT,
    percentual_rentab   REAL,
    quantidade_emitida  INTEGER,
    quantidade_mercado  INTEGER,
    valor_nominal_emis  REAL,
    valor_nominal_atual REAL,
    data_ult_vna        TEXT,
    incentivada_12431   INTEGER,
    resgate_antecipado  INTEGER,
    juros_taxa          REAL,
    juros_prazo         INTEGER,
    juros_cada          INTEGER,
    juros_unidade       TEXT,
    juros_carencia      TEXT,
    juros_criterio      TEXT,
    juros_tipo          TEXT,
    amort_taxa          REAL,
    amort_cada          INTEGER,
    amort_unidade       TEXT,
    amort_carencia      TEXT,
    amort_tipo          TEXT,
    PRIMARY KEY (codigo, snapshot_date)
);
CREATE INDEX IF NOT EXISTS ix_dim_ativo_codigo ON dim_ativo (codigo);
CREATE INDEX IF NOT EXISTS ix_dim_ativo_cnpj   ON dim_ativo (cnpj);
CREATE INDEX IF NOT EXISTS ix_dim_ativo_venc   ON dim_ativo (data_vencimento);

CREATE TABLE IF NOT EXISTS dim_setor (
    cnpj_raiz     TEXT PRIMARY KEY,
    cnae_codigo   TEXT,
    cnae_desc     TEXT,
    setor         TEXT,
    fonte         TEXT NOT NULL,
    atualizado_em TEXT
);

CREATE TABLE IF NOT EXISTS fato_reune (
    data_referencia   TEXT NOT NULL,
    codigo            TEXT NOT NULL,
    nome_anbima       TEXT,
    data_repac_venc   TEXT,
    indexador         TEXT NOT NULL,       -- IPCA | DI | DI_PERC | PRE | IGPM
    spread_emissao    REAL,
    percentual_di     REAL,
    convencao_taxa    TEXT NOT NULL,       -- TAXA_REAL | SPREAD_DI | TAXA_NOMINAL
    taxa_compra       REAL,
    taxa_venda        REAL,
    taxa_indicativa   REAL,
    desvio_padrao     REAL,
    intervalo_min     REAL,
    intervalo_max     REAL,
    pu                REAL,
    pct_pu_par        REAL,
    duration_du       REAL,
    pct_reune         REAL,
    ref_ntnb_venc     TEXT,
    flag_resgate      INTEGER,
    flag_exercicio    INTEGER,
    ingested_at       TEXT NOT NULL,
    PRIMARY KEY (data_referencia, codigo)
);
CREATE INDEX IF NOT EXISTS ix_reune_codigo_data ON fato_reune (codigo, data_referencia);
CREATE INDEX IF NOT EXISTS ix_reune_data_idx    ON fato_reune (data_referencia, indexador);

CREATE TABLE IF NOT EXISTS fato_curva_param (
    data_referencia TEXT NOT NULL,
    curva           TEXT NOT NULL,   -- PRE | IPCA
    beta1 REAL, beta2 REAL, beta3 REAL, beta4 REAL,
    lambda1 REAL, lambda2 REAL,
    ingested_at TEXT NOT NULL,
    PRIMARY KEY (data_referencia, curva)
);

CREATE TABLE IF NOT EXISTS fato_curva_vertice (
    data_referencia TEXT NOT NULL,
    du              INTEGER NOT NULL,
    taxa_ipca       REAL,
    taxa_pre        REAL,
    inflacao_impl   REAL,
    PRIMARY KEY (data_referencia, du)
);

CREATE TABLE IF NOT EXISTS fato_tpf (
    data_referencia TEXT NOT NULL,
    titulo          TEXT NOT NULL,
    codigo_selic    TEXT,
    data_vencimento TEXT NOT NULL,
    taxa_indicativa REAL,
    residuo         REAL,
    du_ate_venc     INTEGER,
    PRIMARY KEY (data_referencia, titulo, data_vencimento)
);
CREATE INDEX IF NOT EXISTS ix_tpf_data ON fato_tpf (data_referencia);

CREATE TABLE IF NOT EXISTS fato_macro (
    serie_id TEXT NOT NULL,
    data     TEXT NOT NULL,
    valor    REAL NOT NULL,
    PRIMARY KEY (serie_id, data)
);

CREATE TABLE IF NOT EXISTS fato_spread (
    data_referencia  TEXT NOT NULL,
    codigo           TEXT NOT NULL,
    taxa_indicativa  REAL,
    ntnb_ref_taxa    REAL,
    z_spread_bruto   REAL,
    z_spread_grossup REAL,
    metodo_grossup   TEXT,   -- exato_fluxo | aprox_fechada | nao_aplicavel
    regime_ir        TEXT,   -- isento | tabela_regressiva
    spread_duration  REAL,
    dv01             REAL,
    PRIMARY KEY (data_referencia, codigo)
);
CREATE INDEX IF NOT EXISTS ix_spread_codigo ON fato_spread (codigo, data_referencia);

CREATE TABLE IF NOT EXISTS ingest_log (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    fonte          TEXT NOT NULL,
    data_alvo      TEXT,
    started_at     TEXT NOT NULL,
    finished_at    TEXT,
    status         TEXT NOT NULL,   -- ok | vazio | erro_http | erro_parse | skip
    http_status    INTEGER,
    bytes_baixados INTEGER,
    linhas_parsed  INTEGER,
    linhas_upsert  INTEGER,
    mensagem       TEXT,
    payload_sha256 TEXT
);
CREATE INDEX IF NOT EXISTS ix_ingest_fonte_data ON ingest_log (fonte, data_alvo);

CREATE VIEW IF NOT EXISTS v_ativo_atual AS
SELECT a.*
FROM dim_ativo a
JOIN (SELECT codigo, MAX(snapshot_date) AS md FROM dim_ativo GROUP BY codigo) x
  ON a.codigo = x.codigo AND a.snapshot_date = x.md;
