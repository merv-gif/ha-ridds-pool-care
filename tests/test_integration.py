"""End-to-end tests against a mocked ha-connect."""
from __future__ import annotations

from datetime import timedelta

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_capture_events,
    async_fire_time_changed,
)
from pytest_homeassistant_custom_component.components.diagnostics import (
    get_diagnostics_for_config_entry,
)

from custom_components.ridds_pool_care.const import API_URL, CONF_API_KEY, DOMAIN, EVENT_NEW_RECORD

from .conftest import KEY


async def _setup(hass: HomeAssistant, aioclient_mock, snapshot) -> MockConfigEntry:
    aioclient_mock.post(API_URL, json=snapshot)
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_API_KEY: KEY}, unique_id=snapshot["key_id"])
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


# ── config flow ──────────────────────────────────────────────────────────────


async def test_flow_creates_entry(hass: HomeAssistant, aioclient_mock, snapshot) -> None:
    aioclient_mock.post(API_URL, json=snapshot)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_API_KEY: f"  {KEY} "})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Ridd's Pool Care (Main pool, Koi pond)"
    assert result["data"] == {CONF_API_KEY: KEY}
    assert result["result"].unique_id == "key-uuid-1"
    # The key went to the server as a bearer token.
    assert aioclient_mock.mock_calls[0][3]["Authorization"] == f"Bearer {KEY}"


async def test_flow_rejects_wrong_prefix(hass: HomeAssistant, aioclient_mock) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_API_KEY: "si_ha_" + "a" * 64})
    assert result["errors"] == {CONF_API_KEY: "not_a_key"}
    assert aioclient_mock.call_count == 0


async def test_flow_invalid_key(hass: HomeAssistant, aioclient_mock) -> None:
    aioclient_mock.post(API_URL, status=401, json={"error": "invalid_key"})
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_API_KEY: KEY})
    assert result["errors"] == {CONF_API_KEY: "invalid_auth"}


async def test_flow_cannot_connect(hass: HomeAssistant, aioclient_mock) -> None:
    aioclient_mock.post(API_URL, status=500, json={"error": "server_error"})
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_API_KEY: KEY})
    assert result["errors"] == {"base": "cannot_connect"}


async def test_flow_duplicate_key_aborts(hass: HomeAssistant, aioclient_mock, snapshot) -> None:
    await _setup(hass, aioclient_mock, snapshot)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_API_KEY: KEY})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


# ── entities ─────────────────────────────────────────────────────────────────


async def test_pool_entities(hass: HomeAssistant, aioclient_mock, snapshot) -> None:
    entry = await _setup(hass, aioclient_mock, snapshot)
    assert entry.state is ConfigEntryState.LOADED

    devices = dr.async_get(hass)
    pool_dev = devices.async_get_device(identifiers={(DOMAIN, "pool-1")})
    assert pool_dev and pool_dev.name == "Main pool" and pool_dev.manufacturer == "Ridd's Aqua Centre"
    assert devices.async_get_device(identifiers={(DOMAIN, "pond-1")}).model == "Koi pond"

    # Chemistry, with Ridd's verdict alongside.
    ph = hass.states.get("sensor.main_pool_ph")
    assert ph.state == "8.2"
    assert ph.attributes["status"] == "High"
    assert ph.attributes["ideal_range"] == "7.2–7.6"
    alk = hass.states.get("sensor.main_pool_alkalinity")
    assert alk.state == "40" and alk.attributes["unit_of_measurement"] == "ppm"
    assert "3.4 kg" in alk.attributes["dose"]
    assert hass.states.get("sensor.main_pool_free_chlorine").state == "2"
    # Salt came from a technician's visit, not the latest strip test, and still shows.
    salt = hass.states.get("sensor.main_pool_salt")
    assert salt.state == "3800" and salt.attributes["tested_by"] == "Thabo"
    # Stabiliser is a base sensor for a pool but has never been tested.
    assert hass.states.get("sensor.main_pool_stabiliser_cya").state == "unknown"

    # Summaries.
    assert hass.states.get("sensor.main_pool_water_status").state == "attention"
    test = hass.states.get("sensor.main_pool_last_water_test")
    assert test.state == "Needs attention: Alkalinity low, pH high"
    assert len(test.attributes["details"]) == 3
    visit = hass.states.get("sensor.main_pool_last_service_visit")
    assert visit.state.startswith("Routine service by Thabo")
    assert visit.attributes["work_carried_out"] == "Replaced pump basket lid"
    assert visit.attributes["report_url"].startswith("https://")
    assert hass.states.get("sensor.main_pool_last_maintenance_log").state.startswith("Your maintenance log")
    assert hass.states.get("sensor.main_pool_days_since_last_test").state == "3"
    history = hass.states.get("sensor.main_pool_service_history")
    assert history.state == "12" and len(history.attributes["history"]) == 3

    # Pool details.
    assert hass.states.get("sensor.main_pool_volume").state == "40000"
    details = hass.states.get("sensor.main_pool_pool_details")
    assert details.state == "Swimming pool"
    assert details.attributes["chlorination_type"] == "salt"
    assert details.attributes["equipment"]["pumps"][0]["make"] == "Speck"

    # Problems.
    assert hass.states.get("binary_sensor.main_pool_water_needs_attention").state == "on"
    assert hass.states.get("binary_sensor.main_pool_service_due").state == "on"

    # Koi pond: its own parameters, no swimming-pool verdicts.
    assert hass.states.get("sensor.koi_pond_ammonia").state == "0.25"
    assert hass.states.get("sensor.koi_pond_water_temperature").state == "21.5"
    assert hass.states.get("sensor.koi_pond_water_status").state == "unknown"
    assert hass.states.get("binary_sensor.koi_pond_water_needs_attention").state == "unknown"
    assert hass.states.get("binary_sensor.koi_pond_service_due").state == "off"
    assert hass.states.get("sensor.koi_pond_free_chlorine") is None


async def test_new_parameter_and_new_record(hass: HomeAssistant, aioclient_mock, snapshot) -> None:
    await _setup(hass, aioclient_mock, snapshot)
    events = async_capture_events(hass, EVENT_NEW_RECORD)
    assert hass.states.get("sensor.main_pool_copper") is None

    # A new strip test arrives with copper on it.
    pool = snapshot["pools"][0]
    pool["readings"]["copper"] = {"value": 0.5, "label": "Copper", "unit": "ppm", "verdict": "high", "status": "High"}
    pool["history"].insert(0, {"id": "rec-test-2", "date": dt_util.now().date().isoformat(), "kind": "test",
                               "by": "You", "overall": "attention", "summary": "Needs attention: Copper high"})
    aioclient_mock.clear_requests()
    aioclient_mock.post(API_URL, json=snapshot)
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=901))
    await hass.async_block_till_done()

    assert hass.states.get("sensor.main_pool_copper").state == "0.5"
    assert len(events) == 1
    assert events[0].data["pool_name"] == "Main pool"
    assert events[0].data["kind"] == "test"
    assert events[0].data["summary"] == "Needs attention: Copper high"


async def test_revoked_key_starts_reauth(hass: HomeAssistant, aioclient_mock, snapshot) -> None:
    entry = await _setup(hass, aioclient_mock, snapshot)
    aioclient_mock.clear_requests()
    aioclient_mock.post(API_URL, status=401, json={"error": "invalid_key"})
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=901))
    await hass.async_block_till_done()

    flows = hass.config_entries.flow.async_progress()
    assert any(f["context"]["source"] == config_entries.SOURCE_REAUTH for f in flows)
    assert entry.state is ConfigEntryState.LOADED
    assert hass.states.get("sensor.main_pool_ph").state == "unavailable"


async def test_diagnostics_redact(hass: HomeAssistant, hass_client, aioclient_mock, snapshot) -> None:
    entry = await _setup(hass, aioclient_mock, snapshot)
    diag = await get_diagnostics_for_config_entry(hass, hass_client, entry)
    text = str(diag)
    assert KEY not in text
    assert "token=secret" not in text
    assert "Pat Owner" not in text
