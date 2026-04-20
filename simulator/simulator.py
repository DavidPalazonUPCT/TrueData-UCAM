#!/usr/bin/env python3
"""
OPC Client simulator v2 — inyector para el pipeline TrueData v2.

Lee el dump SQL del OPC Client de Neoradix (tabla
`public.connect_opcua_itemvalue`), agrupa las filas por `datetime`
único (cada grupo es una DataChangeNotification de OPC-UA, 1..N tags
compartiendo sourceTimestamp), y POSTea cada bundle a
`/api/opc-ingest` de Node-RED.

Ver:
- docs/architecture/ADR-003.md — decisión v2 (NR + Gateway MQTT)
- docs/contracts/opc-ingest.md — contrato del endpoint

Uso básico:
    python3 opc_client_v2.py --sql ../src/FR_ARAGON/Francisco_16_01_2026.sql \\
        --url http://localhost:1880/api/opc-ingest \\
        --limit 10 --rate burst

Único inyector del repo (el simulador v1 fue eliminado al migrar a v2).
Flujo: POST HTTP bulk → Node-RED → Gateway MQTT → ThingsBoard.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

import requests

COPY_START_RE = re.compile(
    r"^COPY public\.connect_opcua_itemvalue \(id, item, value, datetime\) FROM stdin;"
)
COPY_END = r"\."


@dataclass(frozen=True)
class Bundle:
    """Una DataChangeNotification: 1..N tags con un sourceTimestamp compartido."""

    ts_ms: int
    values: dict[str, Any]

    @property
    def cardinality(self) -> int:
        return len(self.values)


def coerce_value(raw: str) -> Any:
    """OPC Client guarda todos los valores como string. Recupera el tipo original.

    Orden de intentos: bool → int → float → string (passthrough).
    TB acepta los 4 nativamente (ver docs/contracts/opc-ingest.md §D.2.1).
    """
    if raw == "True":
        return True
    if raw == "False":
        return False
    try:
        as_float = float(raw)
        return int(as_float) if as_float.is_integer() and "." not in raw else as_float
    except ValueError:
        return raw


def parse_iso_to_unix_ms(iso: str) -> int:
    """`2025-12-17 07:12:13.440196+01` → Unix ms (int).

    Python 3.11+ acepta offsets sin `:`. Mantenemos compat manual por si.
    """
    normalized = iso.strip()
    # Normalizar `+01` → `+01:00` para versiones <3.11
    if re.search(r"[+-]\d{2}$", normalized):
        normalized = normalized[:-2] + normalized[-2:] + ":00"
        # Alternativa: reinsertar ":" en la penúltima posición
    # Python tolera `2025-12-17 07:12:13.440196+01:00` con espacio en vez de T
    dt = datetime.fromisoformat(normalized.replace(" ", "T"))
    return int(dt.timestamp() * 1000)


def iter_itemvalue_rows(sql_path: Path) -> Iterator[tuple[str, str, str]]:
    """Generador que emite `(item, value, datetime)` para cada fila del COPY.

    Streaming: no carga el fichero entero en memoria. El dump son ~25 MB
    pero el patrón escala a clientes con meses de retención.
    """
    with sql_path.open("r", encoding="utf-8") as f:
        in_block = False
        for line in f:
            if not in_block:
                if COPY_START_RE.match(line):
                    in_block = True
                continue
            if line.strip() == COPY_END:
                return
            # Formato COPY: campos tab-separated; datetime incluye espacio interno
            parts = line.rstrip("\n").split("\t")
            if len(parts) != 4:
                continue  # fila malformada — saltar silenciosamente
            _id, item, value, dt_iso = parts
            yield item, value, dt_iso


def load_bundles(sql_path: Path) -> list[Bundle]:
    """Agrupa filas por timestamp. El dump ya viene ordenado por id, pero no
    asumimos nada — construimos un dict y ordenamos al final.
    """
    grouped: dict[int, dict[str, Any]] = defaultdict(dict)
    for item, value, dt_iso in iter_itemvalue_rows(sql_path):
        ts_ms = parse_iso_to_unix_ms(dt_iso)
        grouped[ts_ms][item] = coerce_value(value)
    return [Bundle(ts_ms=ts, values=vals) for ts, vals in sorted(grouped.items())]


def sleep_schedule(bundles: list[Bundle], rate: float | None) -> Iterator[Bundle]:
    """Emite bundles respetando el schedule temporal.

    `rate = None` (burst): sin sleep entre bundles.
    `rate = 1.0`: real-time — sleep `(ts_i - ts_{i-1})` segundos.
    `rate = 100`: 100x más rápido.
    """
    if not bundles:
        return
    if rate is None:
        yield from bundles
        return
    yield bundles[0]
    for prev, curr in zip(bundles, bundles[1:]):
        delta_ms = curr.ts_ms - prev.ts_ms
        if delta_ms > 0:
            time.sleep((delta_ms / 1000.0) / rate)
        yield curr


def post_bundle(session: requests.Session, url: str, bundle: Bundle, timeout: float) -> tuple[int, str]:
    """POSTea un bundle al endpoint `/api/opc-ingest`. Devuelve (status_code, body)."""
    body = {"ts": bundle.ts_ms, "values": bundle.values}
    try:
        resp = session.post(url, json=body, timeout=timeout)
        return resp.status_code, resp.text[:200]
    except requests.exceptions.RequestException as e:
        return -1, f"NETWORK_ERROR: {e}"


def format_stats(stats: dict, duration: float) -> str:
    total = stats["bundles_sent"]
    errors = stats["errors"]
    cardinalities = stats["cardinalities"]
    tags_sent = sum(c * n for c, n in cardinalities.items())
    out = [
        f"=== Stats ===",
        f"Bundles sent:    {total}",
        f"Tags sent:       {tags_sent}",
        f"Errors:          {errors}  ({100*errors/max(total,1):.1f}%)",
        f"Duration:        {duration:.2f}s",
        f"Bundles/sec:     {total/max(duration,1e-9):.2f}",
        f"Cardinality distribution:",
    ]
    for c in sorted(cardinalities.keys()):
        bar = "#" * min(40, cardinalities[c] // max(1, total // 40))
        out.append(f"  {c:2d} tags: {cardinalities[c]:6d}  {bar}")
    return "\n".join(out)


def apply_time_shift(bundles: list[Bundle], shift_ms: int) -> list[Bundle]:
    """Desplaza los ts de todos los bundles en `shift_ms` preservando deltas."""
    return [Bundle(ts_ms=b.ts_ms + shift_ms, values=b.values) for b in bundles]


def run(args: argparse.Namespace) -> int:
    sql_path = Path(args.sql).resolve()
    if not sql_path.exists():
        print(f"ERROR: SQL dump not found: {sql_path}", file=sys.stderr)
        return 2

    print(f"Loading bundles from {sql_path}...", file=sys.stderr)
    bundles = load_bundles(sql_path)
    print(f"Loaded {len(bundles)} unique timestamps", file=sys.stderr)

    if args.shift_to_now and bundles:
        shift_ms = int(time.time() * 1000) - bundles[0].ts_ms
        bundles = apply_time_shift(bundles, shift_ms)
        print(
            f"Time-shifted {len(bundles)} bundles by {shift_ms} ms "
            f"(first bundle now at {bundles[0].ts_ms})",
            file=sys.stderr,
        )

    if args.limit:
        bundles = bundles[: args.limit]
        print(f"Limited to first {len(bundles)}", file=sys.stderr)

    cardinalities: dict[int, int] = defaultdict(int)
    for b in bundles:
        cardinalities[b.cardinality] += 1
    print(f"Cardinality distribution (preview):", file=sys.stderr)
    for c in sorted(cardinalities.keys()):
        print(f"  {c:2d} tags: {cardinalities[c]}", file=sys.stderr)

    if args.dry_run:
        print("\n=== DRY RUN — first 3 bundles ===", file=sys.stderr)
        for b in bundles[:3]:
            print(json.dumps({"ts": b.ts_ms, "values": b.values}, indent=2))
        return 0

    rate = None if args.rate == "burst" else float(args.rate)
    session = requests.Session()
    stats = {
        "bundles_sent": 0,
        "errors": 0,
        "cardinalities": defaultdict(int),
    }

    print(f"\nPOSTing to {args.url} (rate={args.rate})...", file=sys.stderr)
    start = time.monotonic()
    try:
        for b in sleep_schedule(bundles, rate):
            status, body = post_bundle(session, args.url, b, args.timeout)
            stats["bundles_sent"] += 1
            stats["cardinalities"][b.cardinality] += 1
            if status != 200:
                stats["errors"] += 1
                print(
                    f"  [ERR] ts={b.ts_ms} tags={b.cardinality} status={status} body={body}",
                    file=sys.stderr,
                )
            elif args.verbose:
                print(
                    f"  [OK]  ts={b.ts_ms} tags={b.cardinality} body={body}",
                    file=sys.stderr,
                )
    except KeyboardInterrupt:
        print("\nInterrupted by user.", file=sys.stderr)

    duration = time.monotonic() - start
    print(format_stats(stats, duration), file=sys.stderr)
    return 0 if stats["errors"] == 0 else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="OPC Client v2 simulator — replays connect_opcua_itemvalue dump to /api/opc-ingest.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--sql", required=True, help="Path al dump SQL (Postgres COPY format)")
    p.add_argument(
        "--url",
        default="http://localhost:1880/api/opc-ingest",
        help="Endpoint HTTP de NR (default: %(default)s)",
    )
    p.add_argument(
        "--rate",
        default="burst",
        help="Velocidad de replay: 'burst' (sin sleep) o multiplicador float "
        "(1.0 = real-time, 100 = 100x). Default: burst",
    )
    p.add_argument("--limit", type=int, default=0, help="Máximo de bundles (0 = todos)")
    p.add_argument("--timeout", type=float, default=5.0, help="Timeout HTTP por POST (s)")
    p.add_argument("--dry-run", action="store_true", help="No POSTea; imprime 3 primeros bundles")
    p.add_argument("-v", "--verbose", action="store_true", help="Log de cada POST OK")
    p.add_argument(
        "--shift-to-now",
        action="store_true",
        help="Desplaza ts de todos los bundles para que el primero caiga en 'ahora' "
             "(preserva deltas relativos). Útil para replayear dumps históricos "
             "fuera de la ventana de validación de NR.",
    )
    return p


if __name__ == "__main__":
    sys.exit(run(build_parser().parse_args()))
