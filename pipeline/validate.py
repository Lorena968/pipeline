"""Decodificação por tipo de pacote + validação de campos, faixas e relógio."""
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

# Aliases cobrem nomes que mudaram entre versões de firmware (camelCase x snake_case).
DEVICE = {
    "battery_level": (("battery_level", "batteryLevel"), 0, 101),
    "voltage": (("voltage",), 0, 6),
    "channel_utilization": (("channel_utilization", "channelUtilization"), 0, 100),
    "air_util_tx": (("air_util_tx", "airUtilTx"), 0, 100),
    "uptime_seconds": (("uptime_seconds", "uptimeSeconds"), 0, 10 * 365 * 86400),
}
ENVIRONMENT = {
    "temperature": (("temperature",), -40, 85),
    "relative_humidity": (("relative_humidity", "relativeHumidity"), 0, 100),
    "barometric_pressure": (("barometric_pressure", "barometricPressure"), 300, 1100),
}
MIN_VALID = datetime(2020, 1, 1, tzinfo=timezone.utc)


class ValidationError(Exception):
    def __init__(self, motivo):
        super().__init__(motivo)
        self.motivo = motivo


@dataclass
class Packet:
    no: str
    pacote_id: int
    tipo: str
    instante_no: datetime | None
    ts_no_invalido: bool
    metricas: dict = field(default_factory=dict)


def _get(d, *keys):
    for k in keys:
        if isinstance(d, dict) and k in d:
            return d[k]
    return None


def decode_packet(doc, recebido: datetime) -> Packet:
    msg = doc.get("payload_json") or doc.get("mensagem") or doc
    no = _get(msg, "from", "sender")
    pid = _get(msg, "id")
    if no is None or pid is None:
        raise ValidationError("sem_origem_ou_id")
    tipo = _get(msg, "type") or "desconhecido"
    payload = _get(msg, "payload") or {}

    ts = _get(msg, "timestamp") or _get(payload, "time")
    instante_no, invalido = None, True
    if isinstance(ts, (int, float)) and ts > 0:
        instante_no = datetime.fromtimestamp(ts, tz=timezone.utc)
        invalido = instante_no < MIN_VALID or abs(instante_no - recebido) > timedelta(hours=24)

    if tipo == "telemetry":
        src = _get(payload, "device_metrics", "deviceMetrics")
        schema, sub = (DEVICE, "device") if src or _get(payload, "voltage", "battery_level", "batteryLevel") is not None \
            else (ENVIRONMENT, "environment")
        src = src or _get(payload, "environment_metrics", "environmentMetrics") or payload
        metricas = {}
        for nome, (aliases, lo, hi) in schema.items():
            v = _get(src, *aliases)
            if v is None:
                continue
            if not isinstance(v, (int, float)):
                raise ValidationError(f"tipo_invalido:{nome}")
            if not lo <= v <= hi:
                raise ValidationError(f"fora_da_faixa:{nome}")
            metricas[nome] = float(v)
        if not metricas:
            raise ValidationError("telemetria_sem_metricas")
        return Packet(str(no), int(pid), f"telemetry_{sub}", instante_no, invalido, metricas)
    if tipo == "position":
        lat, lon = _get(payload, "latitude_i"), _get(payload, "longitude_i")
        if lat is None or lon is None:
            raise ValidationError("posicao_incompleta")
        return Packet(str(no), int(pid), "position", instante_no, invalido,
                      {"latitude": lat / 1e7, "longitude": lon / 1e7})
    raise ValidationError(f"tipo_nao_modelado:{tipo}")
