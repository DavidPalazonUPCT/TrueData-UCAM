"""Suite de regresión para el pipeline v2."""
from __future__ import annotations

import time

import pytest
import requests

from tests.integration.conftest import MockMl, NrApi, TbClient, now_ms, wait_for_ml


# ===========================================================================
# Bloque A — Validación defensiva
# ===========================================================================

class TestBlockA:
    """Validación defensiva del endpoint /api/opc-ingest."""

    def test_A1_ts_missing(self, nr_api: NrApi):
        r = nr_api.post_ingest({"values": {"X": 1}})
        assert r.status_code == 400
        assert r.json()["reason"] == "ts missing or not finite number"

    def test_A2_ts_null(self, nr_api: NrApi):
        r = nr_api.post_ingest({"ts": None, "values": {"X": 1}})
        assert r.status_code == 400
        assert r.json()["reason"] == "ts missing or not finite number"

    def test_A3_ts_string(self, nr_api: NrApi):
        r = nr_api.post_ingest({"ts": "2026-01-01", "values": {"X": 1}})
        assert r.status_code == 400
        assert r.json()["reason"] == "ts missing or not finite number"

    def test_A4_values_missing(self, nr_api: NrApi):
        r = nr_api.post_ingest({"ts": now_ms()})
        assert r.status_code == 400
        assert r.json()["reason"] == "values must be non-empty object"

    def test_A5_values_empty(self, nr_api: NrApi):
        r = nr_api.post_ingest({"ts": now_ms(), "values": {}})
        assert r.status_code == 400
        assert r.json()["reason"] == "values must be non-empty object"

    def test_A6_values_array(self, nr_api: NrApi):
        """BUG-1: values como array debe rechazarse."""
        r = nr_api.post_ingest({"ts": now_ms(), "values": [{"tag": "X"}]})
        assert r.status_code == 400
        assert r.json()["reason"] == "values must be non-empty object"

    def test_A7_body_not_json_text_plain(self, nr_api: NrApi):
        """BUG-2: body no-JSON con Content-Type text/plain debe dar mensaje claro."""
        r = nr_api.post_ingest("this is not json", content_type="text/plain")
        assert r.status_code == 400
        assert r.json()["reason"] == "body not valid JSON object"

    def test_E1_body_empty(self, nr_api: NrApi):
        """BUG-2: body vacío debe dar mensaje claro."""
        r = nr_api.post_ingest(None)
        assert r.status_code == 400
        assert r.json()["reason"] == "body not valid JSON object"

    def test_E2_json_body_with_text_plain(self, nr_api: NrApi):
        """BUG-2: JSON válido con CT text/plain debe rechazarse con mensaje claro."""
        r = nr_api.post_ingest('{"ts":123,"values":{"X":1}}', content_type="text/plain")
        assert r.status_code == 400
        assert r.json()["reason"] == "body not valid JSON object"


# ===========================================================================
# Bloque B — Comportamiento de values
# ===========================================================================

class TestBlockB:
    """Null, type change, valores extremos, idempotencia TB."""

    def test_B1_null_value_doesnt_contaminate_locf(
        self, nr_api: NrApi, mock_ml: MockMl
    ):
        """LIMIT-2: values.X = null NO debe contaminar lastSeen ni snapshots.

        Adaptado al emit periódico: POSTs espaciados 1.2s para que cada uno
        caiga en un tick distinto. Property: ningún snapshot emitido contiene
        null, y el estado LOCF final es el esperado (B1_X preservado tras null).
        """
        nr_api.set_expected_tags(["B1_X", "B1_Y", "B1_Z"])
        nr_api.set_ai_url(mock_ml.url)
        time.sleep(0.6)

        t1 = now_ms()
        nr_api.post_ingest({"ts": t1, "values": {"B1_X": 1.0, "B1_Y": 2.0, "B1_Z": 3.0}})
        time.sleep(1.2)

        t2 = t1 + 1000
        r = nr_api.post_ingest({"ts": t2, "values": {"B1_X": None, "B1_Y": 4.0}})
        assert r.status_code == 200
        time.sleep(1.2)

        t3 = t2 + 1000
        nr_api.post_ingest({"ts": t3, "values": {"B1_Z": 5.0}})
        time.sleep(1.5)

        assert len(mock_ml.received) >= 2, (
            f"esperados >=2 emits tras POSTs espaciados, got {len(mock_ml.received)}"
        )

        for rec in mock_ml.received:
            for tag, val in rec["sensors"].items():
                assert val is not None, f"Snapshot contenía null para {tag}: {rec}"

        final = mock_ml.received[-1]["sensors"]
        assert final["B1_X"] == 1.0  # LOCF preservó el valor original tras null
        assert final["B1_Y"] == 4.0  # del bundle 2
        assert final["B1_Z"] == 5.0  # del bundle 3

    def test_B2_type_change_between_bundles(self, nr_api: NrApi, tb_client: TbClient):
        """LIMIT-3 regresión: tipo distinto entre bundles del mismo tag → ambos aceptados."""
        tag = "B2_TYPE_CHANGE"
        t1 = now_ms()
        r1 = nr_api.post_ingest({"ts": t1, "values": {tag: 1.5}})
        assert r1.status_code == 200
        t2 = t1 + 1000
        r2 = nr_api.post_ingest({"ts": t2, "values": {tag: "TYPE_CHANGED"}})
        assert r2.status_code == 200

        time.sleep(1.5)  # Dar tiempo a MQTT Gateway a persistir en TB
        ts_data = tb_client.query_timeseries(tag, ["value"], t1 - 1000, t2 + 1000)
        assert len(ts_data.get("value", [])) == 2

    def test_B3_extreme_float_value(self, nr_api: NrApi, tb_client: TbClient):
        """Regresión: float64 max se acepta y persiste."""
        tag = "B3_EXTREME"
        t1 = now_ms()
        r = nr_api.post_ingest({"ts": t1, "values": {tag: 1.79e308}})
        assert r.status_code == 200

        time.sleep(1.5)
        ts_data = tb_client.query_timeseries(tag, ["value"], t1 - 1000, t1 + 1000)
        assert len(ts_data.get("value", [])) >= 1

    def test_B5_tb_idempotency_last_write_wins(
        self, nr_api: NrApi, tb_client: TbClient
    ):
        """Regresión: dos POSTs mismo ts con vals distintos → TB guarda el último."""
        tag = "B5_IDEMPOTENCY"
        t1 = now_ms()
        nr_api.post_ingest({"ts": t1, "values": {tag: 111}})
        nr_api.post_ingest({"ts": t1, "values": {tag: 222}})

        time.sleep(1.5)
        ts_data = tb_client.query_timeseries(tag, ["value"], t1 - 100, t1 + 100)
        values = ts_data.get("value", [])
        assert len(values) == 1
        assert int(values[0]["value"]) == 222


# ===========================================================================
# Bloque C — Tag handling
# ===========================================================================

class TestBlockC:
    """Tags fuera de EXPECTED_TAGS, dropout LOCF."""

    def test_C1_unknown_tag_provisioned_excluded_from_snapshot(
        self, nr_api: NrApi, mock_ml: MockMl, tb_client: TbClient
    ):
        """Tag fuera de EXPECTED_TAGS: device TB auto-provisionado, excluido de snapshot ML."""
        nr_api.set_expected_tags(["C1_X", "C1_Y"])
        nr_api.set_ai_url(mock_ml.url)
        time.sleep(0.6)

        t1 = now_ms()
        nr_api.post_ingest({
            "ts": t1,
            "values": {"C1_X": 1, "C1_Y": 2, "C1_NUEVO": 99},
        })
        wait_for_ml(mock_ml, 1, timeout=2.5)

        snapshot = mock_ml.received[-1]["sensors"]
        assert "C1_X" in snapshot
        assert "C1_Y" in snapshot
        assert "C1_NUEVO" not in snapshot, "Tag fuera de EXPECTED_TAGS filtró al ML"

        time.sleep(1.5)
        ts_data = tb_client.query_timeseries("C1_NUEVO", ["value"], t1 - 1000, t1 + 1000)
        assert len(ts_data.get("value", [])) >= 1

    def test_C2_dropout_locf_holds_stale_value(self, nr_api: NrApi, mock_ml: MockMl):
        """LIMIT-1 regresión: sensor ausente N bundles → LOCF mantiene último valor.

        Adaptado al emit periódico: POSTs espaciados 1.2s. Cada emit intermedio
        debe mantener C2_X=100 (no ha cambiado desde t_base) mientras que C2_Y
        evoluciona. Verificamos la propiedad LOCF sobre los emits recibidos.
        """
        nr_api.set_expected_tags(["C2_X", "C2_Y"])
        nr_api.set_ai_url(mock_ml.url)
        time.sleep(0.6)

        t_base = now_ms()
        nr_api.post_ingest({"ts": t_base, "values": {"C2_X": 100, "C2_Y": 200}})
        time.sleep(1.2)

        for i in range(1, 4):
            nr_api.post_ingest({"ts": t_base + i * 1000, "values": {"C2_Y": 200 + i}})
            time.sleep(1.2)

        assert len(mock_ml.received) >= 3, (
            f"esperados >=3 emits, got {len(mock_ml.received)}"
        )
        for rec in mock_ml.received:
            assert rec["sensors"]["C2_X"] == 100, "LOCF no mantuvo el valor stale"
        # Último emit debe reflejar el Y más reciente (200+3=203)
        assert mock_ml.received[-1]["sensors"]["C2_Y"] == 203


# ===========================================================================
# Bloque Warmup
# ===========================================================================

class TestWarmup:
    """Gate LOCF pre/post warmup."""

    def test_W_partial_no_emit(self, nr_api: NrApi, mock_ml: MockMl):
        """Bundle parcial (no cubre todos los expected_tags) → no emit, warmup counter sube."""
        nr_api.set_expected_tags(["W1_X", "W1_Y", "W1_Z"])
        nr_api.set_ai_url(mock_ml.url)
        time.sleep(0.6)

        stats_before = nr_api.get_stats()
        warmup_before = stats_before["emitCounters"]["skippedWarmup"]

        r = nr_api.post_ingest({"ts": now_ms(), "values": {"W1_X": 1, "W1_Y": 2}})
        assert r.status_code == 200
        # Response no longer carries `inference` field in periodic design
        assert "inference" not in r.json()
        time.sleep(2.0)  # Wait for several ticks

        assert len(mock_ml.received) == 0, "warmup incompleto, no debería emitir"
        stats_after = nr_api.get_stats()
        assert stats_after["emitCounters"]["skippedWarmup"] > warmup_before, (
            "skippedWarmup counter no incrementó durante warmup incompleto"
        )

    def test_W_full_emits_snapshot(self, nr_api: NrApi, mock_ml: MockMl):
        """Cubrir los 3 expected_tags con 3 POSTs → próximo tick emite snapshot."""
        nr_api.set_expected_tags(["W2_X", "W2_Y", "W2_Z"])
        nr_api.set_ai_url(mock_ml.url)
        time.sleep(0.6)

        t = now_ms()
        nr_api.post_ingest({"ts": t, "values": {"W2_X": 1}})
        nr_api.post_ingest({"ts": t + 1, "values": {"W2_Y": 2}})
        r = nr_api.post_ingest({"ts": t + 2, "values": {"W2_Z": 3}})
        assert r.status_code == 200

        wait_for_ml(mock_ml, 1, timeout=2.5)

        assert mock_ml.received[-1]["sensors"] == {"W2_X": 1, "W2_Y": 2, "W2_Z": 3}
        assert mock_ml.received[-1]["ts"] == t + 2


# ===========================================================================
# Bloque F — Escenarios OPC-UA realistas
# ===========================================================================

class TestBlockF:
    """F1 está en runbook manual. F2..F6 automatizados."""

    def test_F2_out_of_order_doesnt_corrupt_locf(
        self, nr_api: NrApi, mock_ml: MockMl
    ):
        """BUG-3: bundle late (ts antiguo) NO debe sobreescribir state LOCF.

        Adaptado al emit periódico: POSTs espaciados 1.2s. Verificamos que el
        valor observado en cada emit respeta el orden temporal de LOCF, no
        el orden de llegada.
        """
        nr_api.set_expected_tags(["F2_X"])
        nr_api.set_ai_url(mock_ml.url)
        # TTL amplio: este test usa ts en el pasado (-60s), que sumado a
        # varios segundos de wall-clock puede superar el TTL=5s default.
        nr_api.set_timing(ttl_ms=120000)
        time.sleep(0.6)

        t_base = now_ms() - 60_000  # 1 min atrás, dentro ventana

        nr_api.post_ingest({"ts": t_base, "values": {"F2_X": 100}})
        time.sleep(1.2)

        nr_api.post_ingest({"ts": t_base + 1000, "values": {"F2_X": 200}})
        time.sleep(1.2)
        n_after_200 = len(mock_ml.received)

        # Late arrival: ts anterior → LOCF rechaza, lastSeen sigue en 200
        nr_api.post_ingest({"ts": t_base - 500, "values": {"F2_X": 50}})
        time.sleep(1.2)
        n_after_late = len(mock_ml.received)

        nr_api.post_ingest({"ts": t_base + 2000, "values": {"F2_X": 300}})
        time.sleep(1.5)

        assert n_after_late > n_after_200, "no se observaron emits tras el late"
        # Emits entre late y el bundle fresco: deben ser 200, NO 50
        for rec in mock_ml.received[n_after_200:n_after_late]:
            assert rec["sensors"]["F2_X"] == 200, (
                f"BUG-3 regressed: late arrival corrompió LOCF. "
                f"Snapshots: {[r['sensors']['F2_X'] for r in mock_ml.received]}"
            )
        # Último emit: 300 (fresco)
        assert mock_ml.received[-1]["sensors"]["F2_X"] == 300

    def test_F3_reconnect_burst_past_ts_accepted(
        self, nr_api: NrApi, tb_client: TbClient
    ):
        """Regresión: 30 bundles con ts=now-10min → aceptados y persistidos."""
        base_ts = now_ms() - 10 * 60 * 1000
        tag = "F3_RECONNECT"
        nr_api.set_expected_tags([tag])

        for i in range(30):
            r = nr_api.post_ingest({"ts": base_ts + i * 1000, "values": {tag: i}})
            assert r.status_code == 200

        time.sleep(2)
        ts_data = tb_client.query_timeseries(
            tag, ["value"], base_ts - 1000, base_ts + 60_000, limit=100
        )
        # Tag TB se reusa entre runs: TB acumula puntos históricos. Verificamos
        # que los 30 ts de esta ejecución están presentes (presencia, no igualdad).
        expected_ts = {base_ts + i * 1000 for i in range(30)}
        actual_ts = {int(p["ts"]) for p in ts_data.get("value", [])}
        missing = expected_ts - actual_ts
        assert not missing, f"TB no persistió {len(missing)}/30 timestamps: {sorted(missing)[:5]}..."

    @pytest.mark.skip(
        reason="Semántica obsoleta: con emit periódico, 2 POSTs 20ms apart "
        "caen en el mismo tick → 1 emit con el último LOCF. Fragmentación "
        "fina a nivel de POST es inobservable por diseño del contrato nuevo. "
        "Ver ai-service.md §Reglas semánticas (cadencia periódica)."
    )
    def test_F4_fragmentation_two_bundles_two_snapshots(
        self, nr_api: NrApi, mock_ml: MockMl
    ):
        pass

    @pytest.mark.parametrize(
        "ts_strategy,expected_status",
        [
            ("epoch_zero", 400),        # ts=0
            ("negative", 400),          # ts=-1
            ("future_far", 400),        # now + 10min
            ("past_1h", 200),           # now - 1h (dentro ventana)
            ("past_40d", 400),          # now - 40d (fuera ventana)
        ],
    )
    def test_F5_ts_sanity_window(
        self, nr_api: NrApi, ts_strategy: str, expected_status: int
    ):
        """LIMIT-4: ventana de ts [now-30d .. now+5min]."""
        now = now_ms()
        ts = {
            "epoch_zero": 0,
            "negative": -1,
            "future_far": now + 10 * 60 * 1000,
            "past_1h": now - 60 * 60 * 1000,
            "past_40d": now - 40 * 24 * 3600 * 1000,
        }[ts_strategy]

        r = nr_api.post_ingest({"ts": ts, "values": {"F5_X": 1}})
        assert r.status_code == expected_status, (
            f"{ts_strategy} (ts={ts}): esperaba {expected_status}, got {r.status_code} "
            f"body={r.text[:200]}"
        )
        if expected_status == 400:
            assert "ts outside acceptable window" in r.json()["reason"]

    def test_F6_sensor_fault_recovery(self, nr_api: NrApi, mock_ml: MockMl):
        """Sensor ausente durante varios bundles y vuelve → LOCF reacciona al recovery.

        Adaptado al emit periódico: POSTs espaciados 1.2s. Property: mientras
        F6_X no se reenvía, los emits intermedios mantienen F6_X=100 (LOCF);
        cuando vuelve, el siguiente emit refleja el nuevo valor.
        """
        nr_api.set_expected_tags(["F6_X", "F6_Y"])
        nr_api.set_ai_url(mock_ml.url)
        time.sleep(0.6)

        t_base = now_ms()
        nr_api.post_ingest({"ts": t_base, "values": {"F6_X": 100, "F6_Y": 200}})
        time.sleep(1.2)

        for i in range(1, 3):
            nr_api.post_ingest({"ts": t_base + i * 1000, "values": {"F6_Y": 200 + i * 10}})
            time.sleep(1.2)

        n_during_dropout = len(mock_ml.received)
        assert n_during_dropout >= 2, (
            f"esperados >=2 emits durante dropout, got {n_during_dropout}"
        )
        for rec in mock_ml.received:
            assert rec["sensors"]["F6_X"] == 100, (
                f"LOCF no mantuvo F6_X: {rec}"
            )

        nr_api.post_ingest({"ts": t_base + 3000, "values": {"F6_X": 500, "F6_Y": 240}})
        time.sleep(1.5)

        assert mock_ml.received[-1]["sensors"]["F6_X"] == 500
        assert mock_ml.received[-1]["sensors"]["F6_Y"] == 240
