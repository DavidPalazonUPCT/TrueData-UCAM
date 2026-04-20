"""Tests for the periodic emit design (T, TTL, warmup timeout).

Per-test timing comes from the autouse clean_state fixture in conftest.py:
interval_ms=500, ttl_ms=5000, warmup_timeout_ms=30000. The inject heartbeat
is hardcoded at 1s in flows.json so effective emit cadence is ~1 Hz.
"""
from __future__ import annotations

import time

from tests.integration.conftest import MockMl, NrApi, now_ms, wait_for_ml

FR_ARAGON_TAGS = [
    "ERROR_COMM", "Q_SALIDA_D1", "DI_02", "DI_10", "EA_4", "EA_3",
    "DI_05", "EA_2", "CE_RECHAZO", "DI_11", "DI_07", "DI_06", "DI_04",
    "Q_RECHAZO", "Heart_Bit", "DI_03", "CE_SALIDA_D2", "DI_01", "DI_09",
    "DI_12", "CE_SALIDA_D1", "Q_SALIDA_D2", "DI_13", "EA_1", "DI_08",
    "PH_D1", "DI_00",
]


def _full_scan_body(ts: int, tags: list[str]) -> dict:
    return {"ts": ts, "values": {t: 1.0 for t in tags}}


class TestPeriodicEmit:
    """Rediseño event-driven → periódico con LOCF + TTL."""

    def test_periodic_emit_rate(self, nr_api: NrApi, mock_ml: MockMl):
        """POST 1 full scan; tras warmup se emite 1 frame por tick (~1/s).

        Con T=500ms, inject=1s, esperar 6s y exigir 4-6 frames (±margen de
        jitter del inject y del primer tick post-POST).
        """
        tags = ["PR_X", "PR_Y", "PR_Z"]
        nr_api.set_expected_tags(tags)
        nr_api.set_ai_url(mock_ml.url)
        time.sleep(0.6)  # ensure config reload caught by next tick

        nr_api.post_ingest({"ts": now_ms(), "values": {"PR_X": 1, "PR_Y": 2, "PR_Z": 3}})

        # 6s window → expected ~5-6 emits (inject ticks every 1s, gate 500ms)
        time.sleep(6.0)

        emits = len(mock_ml.received)
        assert 4 <= emits <= 7, (
            f"esperado 4-7 emits en 6s (periodic @ ~1Hz), got {emits}"
        )
        # Each frame carries the same LOCF state
        for rec in mock_ml.received:
            assert rec["sensors"] == {"PR_X": 1, "PR_Y": 2, "PR_Z": 3}
            assert isinstance(rec["ts"], int)

    def test_ttl_skip_after_silence(self, nr_api: NrApi, mock_ml: MockMl):
        """POST full scan; silencio > TTL → tick siguiente skip (stale)."""
        tags = ["TS_X", "TS_Y"]
        nr_api.set_expected_tags(tags)
        nr_api.set_ai_url(mock_ml.url)
        nr_api.set_timing(interval_ms=500, ttl_ms=3000)
        time.sleep(0.6)

        nr_api.post_ingest({"ts": now_ms(), "values": {"TS_X": 10, "TS_Y": 20}})
        wait_for_ml(mock_ml, 1, timeout=2.0)

        stats_before = nr_api.get_stats()
        emits_before = stats_before["emitCounters"]["emitted"]
        stale_before = stats_before["emitCounters"]["skippedStale"]

        # Silencio > TTL (3s) — esperar 4s extra para que el próximo tick skip
        time.sleep(4.0)

        stats_after = nr_api.get_stats()
        emits_after = stats_after["emitCounters"]["emitted"]
        stale_after = stats_after["emitCounters"]["skippedStale"]

        assert stale_after > stale_before, (
            f"skippedStale no incrementó: before={stale_before} after={stale_after}"
        )
        # Emit count may have grown briefly while TTL was valid (<3s) and then
        # frozen when TTL expired. Cap it: cannot be unbounded.
        assert emits_after <= emits_before + 4, (
            f"emit count creció más de lo esperado bajo stale: "
            f"before={emits_before} after={emits_after}"
        )

    def test_ttl_boundary(self, nr_api: NrApi, mock_ml: MockMl):
        """Pre-TTL tick emite, post-TTL tick skip. Anti off-by-one.

        Con TTL=3s y T=500ms: POST en t=0; en t=2s hay emits (staleness≈2s<3s),
        en t=5s no hay emits nuevos respecto a t=2s (staleness>3s → skip).
        """
        tags = ["TB_X"]
        nr_api.set_expected_tags(tags)
        nr_api.set_ai_url(mock_ml.url)
        nr_api.set_timing(interval_ms=500, ttl_ms=3000)
        time.sleep(0.6)

        nr_api.post_ingest({"ts": now_ms(), "values": {"TB_X": 99}})
        time.sleep(2.0)

        emits_pre_ttl = len(mock_ml.received)
        assert emits_pre_ttl >= 1, (
            f"en t=2s (pre-TTL 3s) esperábamos >=1 emit, got {emits_pre_ttl}"
        )

        # Wait past TTL boundary
        time.sleep(3.0)  # total elapsed ≈ 5s > TTL

        emits_post_ttl = len(mock_ml.received)
        stats = nr_api.get_stats()

        # Between t=2 and t=5 some ticks might still have been within TTL (up
        # to t=3), so allow up to 2 extra emits. After that, pure skip.
        assert emits_post_ttl - emits_pre_ttl <= 2, (
            f"demasiados emits después de TTL: pre={emits_pre_ttl} post={emits_post_ttl}"
        )
        assert stats["emitCounters"]["skippedStale"] >= 1, (
            f"esperado >=1 skippedStale, stats={stats['emitCounters']}"
        )

    def test_warmup_recovers_post_outage(self, nr_api: NrApi, mock_ml: MockMl):
        """Simula outage: sin POST durante >TTL, luego full scan → emit válido.

        Modela el escenario realista donde NR corre continuo pero el OPC client
        ha estado caído. Tras reconexión el primer scan completo debe
        desbloquear emits inmediatamente.
        """
        tags = ["WR_X", "WR_Y"]
        nr_api.set_expected_tags(tags)
        nr_api.set_ai_url(mock_ml.url)
        nr_api.set_timing(interval_ms=500, ttl_ms=3000)
        time.sleep(0.6)

        # Outage simulation: no POSTs for >TTL. Stats should be all skipped.
        time.sleep(4.0)
        stats_outage = nr_api.get_stats()
        # No full scan ever → either warmup or stale (if previous test left
        # state within TTL). Both are valid "no emit" outcomes.
        assert len(mock_ml.received) == 0, (
            f"no debería haber emits durante outage, got {len(mock_ml.received)}"
        )

        # Reconnect: single full scan
        t = now_ms()
        nr_api.post_ingest({"ts": t, "values": {"WR_X": 42, "WR_Y": 43}})

        # First tick after POST should emit
        wait_for_ml(mock_ml, 1, timeout=2.0)

        rec = mock_ml.received[0]
        assert rec["sensors"] == {"WR_X": 42, "WR_Y": 43}
        assert rec["ts"] == t
