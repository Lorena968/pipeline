-- Série limpa em formato longo: uma linha por (nó, pacote, métrica).
-- Linha e não coluna: tipos de pacote têm métricas diferentes e o firmware adiciona campos;
-- formato longo aceita métrica nova sem ALTER TABLE e não gera colunas cheias de NULL.
CREATE TABLE IF NOT EXISTS lorena_serie (
  no_origem   VARCHAR(16)  NOT NULL,
  pacote_id   BIGINT       NOT NULL,
  instante    DATETIME(3)  NOT NULL,  -- recebimento no consumidor (referência)
  instante_no DATETIME(3)  NULL,      -- relógio do nó, só como atributo
  tipo        VARCHAR(32)  NOT NULL,
  metrica     VARCHAR(48)  NOT NULL,
  valor       DOUBLE       NOT NULL,
  PRIMARY KEY (no_origem, pacote_id, metrica),   -- deduplicação idempotente
  KEY idx_metrica_tempo (metrica, instante),
  KEY idx_no_tempo (no_origem, instante)
);

-- Agregados por hora e dia: telemetria de dispositivo sai a cada ~30 min por padrão,
-- então janelas de 15 min ficariam com 0 ou 1 amostra (média sem sentido).
CREATE TABLE IF NOT EXISTS lorena_agregado (
  granularidade ENUM('hora','dia') NOT NULL,
  periodo   DATETIME    NOT NULL,
  no_origem VARCHAR(16) NOT NULL,
  metrica   VARCHAR(48) NOT NULL,
  n INT NOT NULL, media DOUBLE, minimo DOUBLE, maximo DOUBLE,
  PRIMARY KEY (granularidade, periodo, no_origem, metrica)
);

CREATE TABLE IF NOT EXISTS lorena_quarentena (
  mongo_id VARCHAR(32) PRIMARY KEY,
  recebido_em DATETIME(3) NOT NULL,
  motivo VARCHAR(64) NOT NULL,
  bruto MEDIUMTEXT,
  KEY idx_motivo (motivo)
);

CREATE TABLE IF NOT EXISTS lorena_silencios (
  no_origem VARCHAR(16) NOT NULL,
  inicio DATETIME(3) NOT NULL,
  fim DATETIME(3) NOT NULL,
  minutos INT NOT NULL,
  PRIMARY KEY (no_origem, inicio)
);

CREATE TABLE IF NOT EXISTS lorena_no_visto (
  no_origem VARCHAR(16) PRIMARY KEY,
  ultimo DATETIME(3) NOT NULL
);

CREATE TABLE IF NOT EXISTS lorena_contadores (
  nome VARCHAR(32) NOT NULL,
  motivo VARCHAR(64) NOT NULL DEFAULT '',
  valor BIGINT NOT NULL DEFAULT 0,
  PRIMARY KEY (nome, motivo)
);

CREATE TABLE IF NOT EXISTS lorena_checkpoint (
  id TINYINT PRIMARY KEY,
  ultimo_recebido DATETIME(3)
);
