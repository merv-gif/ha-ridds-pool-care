# Ridd's Pool Care for Home Assistant

![Ridd's Pool Care](custom_components/ridds_pool_care/brand/logo.png)

Your pool's water chemistry, pool details and service history from the
**Ridd's Pool Care** app, in Home Assistant — with a plain-English summary of
every water test and service visit.

Home Assistant does not need to be on any particular network. It reads your
records from Ridd's Pool Care over the internet, and it is **read only**:
nothing in Home Assistant can change your account.

## How it works

1. In the Ridd's Pool Care app open **Account → Home Assistant** and create a
   key. Keys are for pool owner accounts.
2. In Home Assistant, install this integration from HACS and paste the key.
3. Each of your pools appears as a device. Home Assistant checks for new
   records every 15 minutes.

Revoke the key in the app and Home Assistant stops updating at its next
refresh.

## Install

### HACS (recommended)

1. HACS → ⋮ → **Custom repositories** → add
   `https://github.com/merv-gif/ha-ridds-pool-care`, type **Integration**.
2. Search for **Ridd's Pool Care**, download, and restart Home Assistant.
3. **Settings → Devices & services → Add integration → Ridd's Pool Care**,
   paste your key.

### Manual

Copy `custom_components/ridds_pool_care` into your Home Assistant
`config/custom_components/` folder and restart.

## What you get, per pool

**Water chemistry** — free and total chlorine, pH, alkalinity, stabiliser
(CYA), salt, calcium hardness, iron, copper; for koi ponds ammonia, nitrite,
nitrate, KH, GH, dissolved oxygen and water temperature. Each sensor shows the
most recent value of that parameter, wherever it was measured (your own strip
test or a technician's visit), with these attributes:

| Attribute | Example |
|---|---|
| `status` | `Low`, `In range`, `OK for winter` |
| `ideal_range` | `80–120` |
| `advice` | `Add sodium bicarbonate. Fix alkalinity before adjusting pH.` |
| `dose` | `about 3.4 kg sodium bicarbonate for this 40,000 L pool` |
| `tested_on`, `tested_by` | `2026-10-07`, `You` |

The verdicts are the same ones the app, the PDF reports and Christina use.

**Summaries**

| Entity | State |
|---|---|
| Water status | `In range` / `Acceptable` / `Needs attention` / `Not tested` |
| Last water test | One-line summary, e.g. *Needs attention: Alkalinity low, pH high*. Full step-by-step advice in the `details` attribute |
| Last service visit | e.g. *Routine service by Thabo — backwash, brushed, vacuumed — all readings in range*. Work done, spares, observations and a link to the PDF report in attributes |
| Last maintenance log | Your own maintenance entries |
| Last water test date, Last service visit date, Days since last test, Next service | Dates |
| Service history | Number of records; the last 20 with their summaries in the `history` attribute |
| Water needs attention | On when a reading is out of range |
| Service due | On when the next service date has arrived |

**Pool details** — volume, plus a *Pool details* sensor whose attributes hold
surface, chlorination, heating, blanket, filter, pump and equipment details.

## Automations

Every new test, visit or maintenance log fires the event
`ridds_pool_care_new_record`:

```yaml
automation:
  - alias: "Tell me when the pool guy has been"
    trigger:
      - platform: event
        event_type: ridds_pool_care_new_record
        event_data:
          kind: visit
    action:
      - service: notify.mobile_app_my_phone
        data:
          title: "{{ trigger.event.data.pool_name }}"
          message: "{{ trigger.event.data.summary }}"
```

Event data: `pool_id`, `pool_name`, `record_id`, `kind` (`test`, `visit` or
`maintenance`), `date`, `by`, `overall`, `summary`.

## Example card

```yaml
type: entities
title: Pool
entities:
  - sensor.my_pool_water_status
  - sensor.my_pool_free_chlorine
  - sensor.my_pool_ph
  - sensor.my_pool_alkalinity
  - sensor.my_pool_stabiliser_cya
  - sensor.my_pool_last_water_test
  - sensor.my_pool_last_service_visit
  - sensor.my_pool_next_service
```

## Privacy and security

- The key is shown once in the app and stored only as a hash.
- A key sees the pools on your own account and nothing else.
- Diagnostics downloads never include the key, names or report links.

## For developers

Tests run against a mocked API: `pip install -r requirements_test.txt && pytest`.
