"""Pipeline contínuo: pacotes_brutos (MongoDB) -> série limpa + agregados (MariaDB) + último valor (Redis).

Garantia de reinício sem duplicar nem perder:
  * Checkpoint (último _id/instante processado) salvo no MariaDB na MESMA transação das linhas escritas.
  * Chave única (no_origem, pacote_id, metrica) na série limpa + INSERT IGNORE => reprocessar é idempotente.
  * Ao reiniciar, relê a partir do checkpoint menos uma janela de segurança (SAFETY_SECONDS);
    o que já foi gravado é descartado pela chave única e contado como duplicata.
"""
import json
import logging
import os
import signal
import time
from datetime import datetime, timedelta, timezone

import pymongo
import redis
import mysql.connector

from validate import decode_packet, ValidationError

PFX = os.getenv("PREFIX", "lorena")
SAFETY = int(os.getenv("SAFETY_SECONDS", "300"))
BATCH = int(os.getenv("BATCH_SIZE", "500"))
POLL = int(os.getenv("POLL_SECONDS", "15"))

log = logging.getLogger("pipeline")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
running = True


def stop(*_):
    global running
    running = False


signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)


def connect():
    mongo = pymongo.MongoClient(os.environ["MONGO_URI"])[os.environ["MONGO_DB"]]
    db = mysql.connector.connect(
        host=os.environ["MARIADB_HOST"], port=int(os.getenv("MARIADB_PORT", "3306")),
        user=os.environ["MARIADB_USER"], password=os.environ["MARIADB_PASSWORD"],
        database=os.environ["MARIADB_DB"], autocommit=False,
    )
    r = redis.Redis.from_url(os.environ["REDIS_URL"], decode_responses=True)
    return mongo, db, r


def get_checkpoint(cur):
    cur.execute(f"SELECT ultimo_recebido FROM {PFX}_checkpoint WHERE id=1")
    row = cur.fetchone()
    return row[0].replace(tzinfo=timezone.utc) if row and row[0] else datetime(1970, 1, 1, tzinfo=timezone.utc)


def bump(cur, nome, motivo="", n=1):
    cur.execute(
        f"INSERT INTO {PFX}_contadores (nome, motivo, valor) VALUES (%s,%s,%s) "
        "ON DUPLICATE KEY UPDATE valor = valor + VALUES(valor)", (nome, motivo, n))


def process_batch(mongo, db, r):
    cur = db.cursor()
    desde = get_checkpoint(cur) - timedelta(seconds=SAFETY)
    docs = list(mongo["pacotes_brutos"].find({"recebido_em": {"$gt": desde}})
                .sort("recebido_em", 1).limit(BATCH))
    if not docs:
        return 0
    ultimo = desde
    redis_updates = {}
    seen = set()
    for doc in docs:
        recebido = doc["recebido_em"]
        recebido = recebido.replace(tzinfo=timezone.utc) if recebido.tzinfo is None else recebido
        ultimo = max(ultimo, recebido)
        bump(cur, "lidos")
        try:
            pkt = decode_packet(doc, recebido)
        except ValidationError as e:
            bump(cur, "quarentena", e.motivo)
            cur.execute(
                f"INSERT IGNORE INTO {PFX}_quarentena (mongo_id, recebido_em, motivo, bruto) VALUES (%s,%s,%s,%s)",
                (str(doc["_id"]), recebido, e.motivo, json.dumps(doc, default=str)[:60000]))
            continue
        if pkt.ts_no_invalido:
            bump(cur, "timestamp_invalido")
        key = (pkt.no, pkt.pacote_id)
        if key in seen:
            bump(cur, "duplicatas")
            continue
        seen.add(key)
        inseridas = 0
        for metrica, valor in pkt.metricas.items():
            cur.execute(
                f"INSERT IGNORE INTO {PFX}_serie (no_origem, pacote_id, instante, instante_no, tipo, metrica, valor) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (pkt.no, pkt.pacote_id, recebido, pkt.instante_no, pkt.tipo, metrica, valor))
            inseridas += cur.rowcount
            redis_updates[(pkt.no, metrica)] = (valor, recebido)
        if pkt.metricas and inseridas == 0:
            bump(cur, "duplicatas")
        elif inseridas:
            bump(cur, "aceitos")
            detect_gap(cur, pkt.no, recebido)
    cur.execute(f"REPLACE INTO {PFX}_checkpoint (id, ultimo_recebido) VALUES (1, %s)", (ultimo,))
    db.commit()  # série + contadores + checkpoint atômicos
    pipe = r.pipeline()
    for (no, metrica), (valor, inst) in redis_updates.items():
        k = f"{PFX}:ultimo:{no}:{metrica}"
        pipe.hset(k, mapping={"valor": valor, "instante": inst.isoformat()})
        pipe.set(f"{PFX}:visto:{no}", inst.isoformat())
    pipe.execute()
    return len(docs)


def detect_gap(cur, no, recebido, limite_min=int(os.getenv("GAP_MINUTES", "60"))):
    """Silêncio > limite vira linha em _silencios (ausência modelada, sem interpolar)."""
    cur.execute(f"SELECT ultimo FROM {PFX}_no_visto WHERE no_origem=%s", (no,))
    row = cur.fetchone()
    if row:
        ant = row[0].replace(tzinfo=timezone.utc)
        if recebido - ant > timedelta(minutes=limite_min):
            cur.execute(f"INSERT IGNORE INTO {PFX}_silencios (no_origem, inicio, fim, minutos) VALUES (%s,%s,%s,%s)",
                        (no, ant, recebido, int((recebido - ant).total_seconds() // 60)))
            bump(cur, "buracos")
        if recebido < ant:
            bump(cur, "fora_de_ordem")
    cur.execute(f"INSERT INTO {PFX}_no_visto (no_origem, ultimo) VALUES (%s,%s) "
                "ON DUPLICATE KEY UPDATE ultimo = GREATEST(ultimo, VALUES(ultimo))", (no, recebido))


def aggregate(db):
    """Recalcula agregados horários/diários das últimas 48h (idempotente via REPLACE)."""
    cur = db.cursor()
    for gran, fmt in (("hora", "%Y-%m-%d %H:00:00"), ("dia", "%Y-%m-%d 00:00:00")):
        cur.execute(f"""
            REPLACE INTO {PFX}_agregado (granularidade, periodo, no_origem, metrica, n, media, minimo, maximo)
            SELECT %s, DATE_FORMAT(instante, %s), no_origem, metrica, COUNT(*), AVG(valor), MIN(valor), MAX(valor)
            FROM {PFX}_serie WHERE instante >= NOW() - INTERVAL 48 HOUR
            GROUP BY DATE_FORMAT(instante, %s), no_origem, metrica""", (gran, fmt, fmt))
    db.commit()


def main():
    mongo, db, r = connect()
    last_agg = 0
    while running:
        try:
            n = process_batch(mongo, db, r)
            if time.time() - last_agg > 300:
                aggregate(db)
                last_agg = time.time()
            if n < BATCH:
                time.sleep(POLL)
        except (mysql.connector.Error, pymongo.errors.PyMongoError, redis.RedisError) as e:
            log.exception("erro de conexão, reconectando: %s", e)
            try:
                db.rollback()
            except Exception:
                pass
            time.sleep(10)
            mongo, db, r = connect()
    log.info("encerrado com segurança")


if __name__ == "__main__":
    main()
