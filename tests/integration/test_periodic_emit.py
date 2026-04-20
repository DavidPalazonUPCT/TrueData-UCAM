"""Tests for the periodic-emit design (T=40s default, LOCF, no TTL).

Per-test timing comes from the autouse clean_state fixture in conftest.py.
Tests calibrated for interval=2000ms to keep runtime reasonable while
preserving the spec's duration/interval ratios.

Expected tags are pulled from deploy/clients/<CLIENT>.yaml (session fixture
client_expected_tags), never hardcoded.
"""
from __future__ import annotations

import time

from tests.integration.conftest import MockMl, NrApi


def _full_scan_body(ts: int, tags: list[str]) -> dict:
    return {"ts": ts, "values": {t: 1.0 for t in tags}}


def _now_ms() -> int:
    return int(time.time() * 1000)


class TestPeriodicEmit:
    """Contract: periodic emit every inference_emit_interval_ms with LOCF."""

    def test_periodic_emit_rate(
        self,
        nr_api: NrApi,
        mock_ml: MockMl,
        client_expected_tags: list[str],
    ):
        """POST 1 full scan; esperar N×T; verificar ~N frames con los 27 tags.

        Ratio del spec (T=40 000 ms, wait 600 000 ms, ~15 frames) implementado
        con T=2 000 ms, wait 30 s, ~15 frames. Mismo ratio, 20× más rápido.
        """
        nr_api.set_expected_tags(client_expected_tags)
        nr_api.set_ai_url(mock_ml.url)
        nr_api.set_timing(interval_ms=2000)
        time.sleep(0.6)  # config reload caught by next tick

        ts = _now_ms()
        body = _full_scan_body(ts, client_expected_tags)
        r = nr_api.post_ingest(body)
        assert r.status_code == 200

        # Wait 30s at T=2s → expect ~15 emits (±10% tolerance per spec)
        time.sleep(30.0)

        emits = len(mock_ml.received)
        assert 12 <= emits <= 17, (
            f"esperado ~15 emits (±10%) en 30s @ T=2s, got {emits}"
        )
        # Each frame must contain exactly the expected tags
        n = len(client_expected_tags)
        for rec in mock_ml.received:
            assert set(rec["sensors"].keys()) == set(client_expected_tags), (
                f"snapshot tag-set mismatch: "
                f"missing={set(client_expected_tags)-set(rec['sensors'])}, "
                f"extra={set(rec['sensors'])-set(client_expected_tags)}"
            )
            assert len(rec["sensors"]) == n
            assert isinstance(rec["ts"], int)

    def test_warmup_blocks_until_all_seen(
        self,
        nr_api: NrApi,
        mock_ml: MockMl,
        client_expected_tags: list[str],
    ):
        """Partial scan → no emit. Tras completar faltantes → ≥1 emit.

        Spec: scan parcial (20 de 27), espera 2 ticks, cero emits; scan
        complementario con los 7 restantes, espera 2 ticks, ≥1 frame con 27.
        Aquí con T=2s: espera 4s (2 ticks) en cada fase.
        """
        tags = client_expected_tags
        assert len(tags) >= 10, "test asume ≥10 tags en el manifest"

        split = int(len(tags) * 0.75)  # ~75% en la primera tanda
        first, second = tags[:split], tags[split:]
        assert first and second, "split produjo lista vacía"

        nr_api.set_expected_tags(tags)
        nr_api.set_ai_url(mock_ml.url)
        nr_api.set_timing(interval_ms=2000)
        time.sleep(0.6)

        # Fase 1: partial scan, esperar 2 ticks, verificar 0 emits
        ts1 = _now_ms()
        r1 = nr_api.post_ingest({"ts": ts1, "values": {t: 1.0 for t in first}})
        assert r1.status_code == 200
        time.sleep(4.5)  # 2 ticks + margen

        assert len(mock_ml.received) == 0, (
            f"warmup incompleto ({len(first)}/{len(tags)}), "
            f"no debería haber emits, got {len(mock_ml.received)}"
        )

        # Fase 2: scan complementario, esperar 2 ticks, verificar ≥1 emit con todos los tags
        ts2 = _now_ms()
        r2 = nr_api.post_ingest({"ts": ts2, "values": {t: 2.0 for t in second}})
        assert r2.status_code == 200
        time.sleep(4.5)

        assert len(mock_ml.received) >= 1, (
            f"warmup completado pero sin emits tras 2 ticks, "
            f"received={len(mock_ml.received)}"
        )
        # Todos los frames emitidos post-warmup deben tener los N tags
        for rec in mock_ml.received:
            assert set(rec["sensors"].keys()) == set(tags), (
                f"snapshot tag-set mismatch post-warmup: "
                f"missing={set(tags)-set(rec['sensors'])}"
            )
