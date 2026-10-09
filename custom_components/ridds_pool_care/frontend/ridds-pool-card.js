/*
 * Ridd's Pool Card \u2014 served by the Ridd's Pool Care integration.
 *
 *   type: custom:ridds-pool-card
 *   device_id: <a Ridd's Pool Care pool device>   # optional: first pool if omitted
 *
 * Health score up top (the same number as the app's dashboard ring), the
 * readings that matter, and the last test / visit / maintenance / history as
 * sections that open on tap. Entities are found through the device and their
 * translation keys, so renamed entity IDs keep working.
 */

const DOMAIN = "ridds_pool_care";
const VERSION = "0.2.1";

const CHEM = [
  ["free_chlorine", "Chlorine"],
  ["ph", "pH"],
  ["alkalinity", "Alkalinity"],
  ["stabiliser", "Stabiliser"],
  ["salt", "Salt"],
  ["calcium_hardness", "Calcium"],
  ["total_chlorine", "Total Cl"],
  ["bromine", "Bromine"],
  ["iron", "Iron"],
  ["copper", "Copper"],
  ["tds", "TDS"],
  ["ammonia", "Ammonia"],
  ["nitrite", "Nitrite"],
  ["nitrate", "Nitrate"],
  ["kh", "KH"],
  ["gh", "GH"],
  ["dissolved_oxygen", "Oxygen"],
  ["water_temp", "Water temp"],
];

// Same bands and colours as the app's HealthScore ring.
function band(score) {
  if (score == null) return { label: "Awaiting test", from: "#5b6b7f", to: "#8a9bb0", color: "#8a9bb0" };
  if (score >= 85) return { label: "Healthy", from: "#21a878", to: "#4fe0a8", color: "#3ccf94" };
  if (score >= 70) return { label: "Stable", from: "#2e84d4", to: "#5be6ef", color: "#47b8e6" };
  if (score >= 50) return { label: "Attention", from: "#d98a1e", to: "#fbc15e", color: "#f2a93b" };
  return { label: "Action needed", from: "#e23a2e", to: "#ff7a6e", color: "#f2584c" };
}

const VERDICT_COLOR = { ok: "#2fbf84", fair: "#e9a23b", low: "#ef5b4f", high: "#ef5b4f" };

const esc = (v) =>
  String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

const safeUrl = (u) => (typeof u === "string" && /^https:\/\//i.test(u) ? u : null);

function parseDate(d) {
  if (!d || typeof d !== "string") return null;
  const t = new Date(d.length <= 10 ? `${d}T12:00:00` : d);
  return isNaN(t) ? null : t;
}

function shortDate(d) {
  const t = parseDate(d);
  return t ? t.toLocaleDateString(undefined, { day: "numeric", month: "short" }) : "";
}

function ago(d) {
  const t = parseDate(d);
  if (!t) return "";
  const days = Math.round((Date.now() - t.getTime()) / 86400000);
  if (days <= 0) return "today";
  if (days === 1) return "yesterday";
  if (days < 14) return `${days} days ago`;
  if (days < 60) return `${Math.round(days / 7)} weeks ago`;
  return shortDate(d);
}

function until(d) {
  const t = parseDate(d);
  if (!t) return "";
  const days = Math.round((t.getTime() - Date.now()) / 86400000);
  if (days < 0) return `${-days} day${days === -1 ? "" : "s"} overdue`;
  if (days === 0) return "today";
  if (days === 1) return "tomorrow";
  return `in ${days} days`;
}

// "7.2\u20137.6" \u2192 [7.2, 7.6]; "below 0.3" \u2192 [0, 0.3]
function parseIdeal(s) {
  if (typeof s !== "string") return null;
  const m = s.match(/^\s*([\d.]+)\s*[\u2013-]\s*([\d.]+)/);
  if (m) return [parseFloat(m[1]), parseFloat(m[2])];
  const b = s.match(/below\s*([\d.]+)/i);
  if (b) return [0, parseFloat(b[1])];
  return null;
}

function fmt(v) {
  const n = Number(v);
  if (!isFinite(n)) return "\u2014";
  if (Math.abs(n) >= 1000) return n.toLocaleString(undefined, { maximumFractionDigits: 0 });
  return String(Math.round(n * 100) / 100);
}

const ICONS = {
  test: "mdi:test-tube",
  visit: "mdi:account-wrench",
  maintenance: "mdi:broom",
  history: "mdi:history",
  calendar: "mdi:calendar-arrow-right",
  report: "mdi:file-pdf-box",
  alert: "mdi:alert-circle",
  chevron: "mdi:chevron-down",
};

class RiddsPoolCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._open = new Set();
    this._sig = "";
    this.shadowRoot.addEventListener("click", (ev) => this._onClick(ev));
  }

  static getConfigElement() {
    return document.createElement("ridds-pool-card-editor");
  }

  static getStubConfig(hass) {
    const dev = RiddsPoolCard.devices(hass)[0];
    return dev ? { device_id: dev.id } : {};
  }

  static devices(hass) {
    const ids = new Set();
    for (const e of Object.values(hass?.entities || {})) {
      if (e.platform === DOMAIN && e.device_id) ids.add(e.device_id);
    }
    return [...ids].map((id) => ({ id, name: hass.devices?.[id]?.name_by_user || hass.devices?.[id]?.name || "Pool" }));
  }

  setConfig(config) {
    this._config = {
      show_chemistry: true,
      show_test: true,
      show_visit: true,
      show_maintenance: true,
      show_history: true,
      history_count: 8,
      ...config,
    };
    if (this._config.expand) this._open.add(this._config.expand);
    this._sig = "";
    if (this._hass) this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._resolve();
    const sig = Object.values(this._map || {})
      .map((id) => hass.states[id]?.last_updated || "")
      .join("|") + (this._deviceName || "");
    if (sig !== this._sig) {
      this._sig = sig;
      this._render();
    }
  }

  getCardSize() {
    return 7;
  }

  getGridOptions() {
    return { columns: 12, min_columns: 6, rows: "auto" };
  }

  _resolve() {
    const hass = this._hass;
    let device = this._config?.device_id;
    if (!device) device = RiddsPoolCard.devices(hass)[0]?.id;
    this._device = device;
    const map = {};
    if (device) {
      for (const e of Object.values(hass.entities || {})) {
        if (e.device_id !== device || e.platform !== DOMAIN) continue;
        let key = e.translation_key;
        if (!key && hass.states[e.entity_id]?.attributes?.device_class === "ph") key = "ph";
        if (key) map[key] = e.entity_id;
      }
    }
    this._map = map;
    const d = device ? hass.devices?.[device] : null;
    this._deviceName = this._config?.title || d?.name_by_user || d?.name || "Pool";
  }

  _st(key) {
    const id = this._map?.[key];
    return id ? this._hass.states[id] : undefined;
  }

  _val(key) {
    const s = this._st(key);
    return s && !["unknown", "unavailable", ""].includes(s.state) ? s.state : null;
  }

  _onClick(ev) {
    const el = ev.composedPath().find((n) => n.dataset && (n.dataset.toggle || n.dataset.entity || n.dataset.url));
    if (!el) return;
    if (el.dataset.url) {
      const u = safeUrl(el.dataset.url);
      if (u) window.open(u, "_blank", "noopener");
      ev.stopPropagation();
      return;
    }
    if (el.dataset.toggle) {
      const k = el.dataset.toggle;
      this._open.has(k) ? this._open.delete(k) : this._open.add(k);
      this._render();
      return;
    }
    if (el.dataset.entity) {
      this.dispatchEvent(new CustomEvent("hass-more-info", { detail: { entityId: el.dataset.entity }, bubbles: true, composed: true }));
    }
  }

  // \u2500\u2500 pieces \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

  _ring(score, b) {
    const size = 132, stroke = 11, r = (size - stroke) / 2 - 2, c = 2 * Math.PI * r;
    const arc = c * 0.75, pct = score == null ? 0 : Math.max(0, Math.min(1, score / 100));
    return `
      <div class="ring" ${this._map.health_score ? `data-entity="${this._map.health_score}"` : ""}>
        <svg viewBox="0 0 ${size} ${size}" width="${size}" height="${size}">
          <defs><linearGradient id="rg" x1="0" y1="1" x2="1" y2="0">
            <stop offset="0" stop-color="${b.from}"/><stop offset="1" stop-color="${b.to}"/>
          </linearGradient></defs>
          <g transform="rotate(135 ${size / 2} ${size / 2})">
            <circle cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" stroke="rgba(255,255,255,.12)"
              stroke-width="${stroke}" stroke-dasharray="${arc} ${c}" stroke-linecap="round"/>
            <circle class="arc" cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" stroke="url(#rg)"
              stroke-width="${stroke}" stroke-dasharray="${arc * pct} ${c}" stroke-linecap="round"
              style="filter:drop-shadow(0 0 6px ${b.color})"/>
          </g>
        </svg>
        <div class="ring-num"><span>${score == null ? "\u2014" : Math.round(score)}</span><small>${score == null ? "" : "/ 100"}</small></div>
      </div>`;
  }

  _spark(trend) {
    const pts = (trend || []).filter((p) => typeof p.score === "number");
    if (pts.length < 2) return "";
    const w = 120, h = 30;
    const xs = (i) => (i / (pts.length - 1)) * (w - 6) + 3;
    const ys = (s) => h - 3 - ((Math.max(40, Math.min(100, s)) - 40) / 60) * (h - 6);
    const line = pts.map((p, i) => `${xs(i).toFixed(1)},${ys(p.score).toFixed(1)}`).join(" ");
    const last = pts[pts.length - 1];
    return `
      <div class="spark" title="Health score, last ${pts.length} tests">
        <svg viewBox="0 0 ${w} ${h}" width="${w}" height="${h}">
          <polyline points="${line}" fill="none" stroke="rgba(255,255,255,.75)" stroke-width="1.8" stroke-linejoin="round" stroke-linecap="round"/>
          <circle cx="${xs(pts.length - 1)}" cy="${ys(last.score)}" r="3" fill="${band(last.score).color}"/>
        </svg>
        <span>trend \u00b7 ${pts.length} tests</span>
      </div>`;
  }

  _tile(key, label, latestDate) {
    const s = this._st(key);
    if (!s) return "";
    const a = s.attributes || {};
    const has = this._val(key) !== null;
    const verdict = a.verdict;
    const color = has ? VERDICT_COLOR[verdict] || "var(--rp-neutral)" : "var(--rp-muted)";
    const unit = a.unit_of_measurement || "";
    const ideal = parseIdeal(a.ideal_range);
    let bar = "";
    if (has && ideal) {
      const [lo, hi] = ideal;
      const span = Math.max(hi - lo, hi * 0.5, 0.1);
      const min = Math.max(0, lo - span), max = hi + span;
      const pos = (v) => Math.max(0, Math.min(100, ((v - min) / (max - min)) * 100));
      const v = Number(s.state);
      bar = `<div class="bar"><i class="band" style="left:${pos(lo)}%;width:${Math.max(2, pos(hi) - pos(lo))}%"></i>
             <b style="left:${pos(v)}%;background:${color}"></b></div>`;
    } else {
      bar = `<div class="bar empty"></div>`;
    }
    const stale = has && a.tested_on && latestDate && a.tested_on !== latestDate;
    const note = !has ? "Not tested yet" : stale ? `${esc(a.status && a.status !== "-" ? a.status : "")}${a.status && a.status !== "-" ? " \u00b7 " : ""}${shortDate(a.tested_on)}` : esc(a.status && a.status !== "-" ? a.status : a.ideal_range ? "" : "Measured");
    return `
      <button class="tile ${has ? "" : "dim"}" data-entity="${s.entity_id}" style="--c:${color}">
        <div class="t-label">${esc(label)}</div>
        <div class="t-val">${has ? fmt(s.state) : "\u2014"}<small>${has && unit ? esc(unit) : ""}</small></div>
        ${bar}
        <div class="t-note">${note}</div>
      </button>`;
  }

  _section(id, icon, title, summary, meta, body, accent) {
    const open = this._open.has(id);
    return `
      <div class="sec ${open ? "open" : ""}" style="${accent ? `--accent:${accent}` : ""}">
        <button class="sec-head" data-toggle="${id}" aria-expanded="${open}">
          <span class="sec-icon"><ha-icon icon="${icon}"></ha-icon></span>
          <span class="sec-text">
            <span class="sec-title">${esc(title)}${meta ? `<em>${esc(meta)}</em>` : ""}</span>
            <span class="sec-sum">${esc(summary)}</span>
          </span>
          <ha-icon class="chev" icon="${ICONS.chevron}"></ha-icon>
        </button>
        ${open ? `<div class="sec-body">${body}</div>` : ""}
      </div>`;
  }

  _recordBody(a, skipAdvice = false) {
    const parts = [];
    if (a.by || a.date) parts.push(`<div class="by">${esc(a.by || "")}${a.by && a.date ? " \u00b7 " : ""}${esc(shortDate(a.date))}</div>`);
    const chips = [...(a.work || []), ...(a.conditions || []).map((c) => `Water: ${c}`)];
    if (chips.length) parts.push(`<div class="chips">${chips.map((c) => `<span>${esc(c)}</span>`).join("")}</div>`);
    if (a.readings) {
      parts.push(`<div class="mini">${Object.entries(a.readings)
        .filter(([, r]) => r && typeof r.value === "number")
        .map(([k, r]) => `<span><b>${esc((CHEM.find((c) => c[0] === k) || [k, k])[1])}</b> ${fmt(r.value)}${r.status && r.status !== "-" ? ` <i>${esc(r.status)}</i>` : ""}</span>`)
        .join("")}</div>`);
    }
    const details = (a.details || []).filter((d) => !/^Done: |^Water: |^Water looked: /.test(d) && !(skipAdvice && / \u2014 /.test(d)));
    if (details.length) parts.push(`<ul>${details.map((d) => `<li>${esc(d)}</li>`).join("")}</ul>`);
    if (a.spares?.length) parts.push(`<div class="by">Spares: ${esc(a.spares.join(", "))}</div>`);
    const url = safeUrl(a.report_url);
    if (url) parts.push(`<button class="report" data-url="${esc(url)}"><ha-icon icon="${ICONS.report}"></ha-icon>Open PDF report</button>`);
    return parts.join("") || `<div class="by">No further detail recorded.</div>`;
  }

  // \u2500\u2500 render \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

  _render() {
    if (!this._hass || !this._config) return;
    const cfg = this._config;

    if (!this._device || !Object.keys(this._map).length) {
      this.shadowRoot.innerHTML = `${STYLE}<ha-card><div class="empty-card">
        <ha-icon icon="mdi:pool"></ha-icon>
        <div><b>No Ridd's Pool Care pool found.</b><br>Add the Ridd's Pool Care integration, then pick a pool in this card's settings.</div>
      </div></ha-card>`;
      return;
    }

    const health = this._st("health_score");
    const score = this._val("health_score") !== null ? Number(health.state) : null;
    const b = band(score);
    const ha = health?.attributes || {};
    const test = this._st("last_water_test");
    const ta = test?.attributes || {};
    const visit = this._st("last_visit");
    const va = visit?.attributes || {};
    const maint = this._st("last_maintenance");
    const ma = maint?.attributes || {};
    const hist = this._st("service_history");
    const details = this._st("pool_details");
    const attention = this._val("needs_attention") === "on";
    const due = this._val("service_due") === "on";
    const next = this._val("next_service");
    const volume = this._val("volume");

    const metaBits = [details?.state && !["unknown", "unavailable"].includes(details.state) ? details.state : null,
      volume ? `${Number(volume).toLocaleString()} L` : null].filter(Boolean);
    const inRange = ha.measured ? `${ha.in_range} of ${ha.measured} in range` : "";

    // Readings: everything this pool has, in a sensible order.
    const tiles = cfg.show_chemistry
      ? CHEM.filter(([k]) => this._map[k]).map(([k, l]) => this._tile(k, l, ta.date)).join("")
      : "";

    // What needs doing, straight from the last test's advice.
    const advice = (ta.details || []).filter((d) => / \u2014 /.test(d));
    const offenders = CHEM.filter(([k]) => {
      const v = this._st(k)?.attributes?.verdict;
      return (v === "low" || v === "high") && this._st(k)?.attributes?.tested_on === ta.date;
    }).map(([k, l]) => `${l} ${String(this._st(k).attributes.status || "").toLowerCase()}`);

    const sections = [];
    if (cfg.show_test && test && test.state && !["unknown", "unavailable"].includes(test.state)) {
      // When the water needs work, the steps lead the section: what to do first, detail after.
      const todo = advice.length
        ? `<div class="todo"><div class="todo-h">What to do</div><ol>${advice.map((d) => `<li>${esc(d)}</li>`).join("")}</ol></div>`
        : "";
      const summary = attention && offenders.length ? `Needs attention: ${offenders.join(" \u00b7 ")}` : test.state;
      sections.push(this._section("test", ICONS.test, "Last water test", summary, ago(ta.date),
        todo + this._recordBody(ta, !!todo),
        ta.overall === "attention" ? VERDICT_COLOR.low : ta.overall === "fair" ? VERDICT_COLOR.fair : VERDICT_COLOR.ok));
    }
    if (cfg.show_visit && visit && visit.state && !["unknown", "unavailable"].includes(visit.state)) {
      sections.push(this._section("visit", ICONS.visit, "Last service visit", visit.state, ago(va.date), this._recordBody(va), "var(--rp-brand)"));
    }
    if (cfg.show_maintenance && maint && maint.state && !["unknown", "unavailable"].includes(maint.state)) {
      sections.push(this._section("maintenance", ICONS.maintenance, "Your maintenance", maint.state, ago(ma.date), this._recordBody(ma), "var(--rp-muted)"));
    }
    const records = (hist?.attributes?.history || []).slice(0, cfg.history_count || 8);
    if (cfg.show_history && records.length) {
      const body = `<div class="timeline">${records.map((r) => {
        const dot = r.overall === "attention" ? VERDICT_COLOR.low : r.overall === "fair" ? VERDICT_COLOR.fair : r.overall === "ok" ? VERDICT_COLOR.ok : "var(--rp-muted)";
        return `<div class="ev"><i style="background:${dot}"></i>
          <div><div class="ev-head"><ha-icon icon="${ICONS[r.kind] || ICONS.history}"></ha-icon>${esc(shortDate(r.date))} \u00b7 ${esc(r.by || "")}${typeof r.score === "number" ? `<span class="pill" style="--p:${band(r.score).color}">${r.score}</span>` : ""}</div>
          <div class="ev-sum">${esc(r.summary || "")}</div></div></div>`;
      }).join("")}</div>`;
      const a = hist.attributes;
      sections.push(this._section("history", ICONS.history, "History", `${a.tests ?? 0} tests \u00b7 ${a.visits ?? 0} visits \u00b7 ${a.maintenance ?? 0} maintenance`, "", body, "var(--rp-muted)"));
    }

    const status = attention
      ? `<span class="chip bad"><ha-icon icon="${ICONS.alert}"></ha-icon>Needs attention</span>`
      : `<span class="chip" style="--p:${b.color}">${esc(b.label)}</span>`;

    this.shadowRoot.innerHTML = `${STYLE}
      <ha-card>
        <div class="hero">
          <div class="waves" aria-hidden="true">
            <svg class="w1" viewBox="0 0 1200 60" preserveAspectRatio="none"><path d="M0 30 Q150 0 300 30 T600 30 T900 30 T1200 30 V60 H0Z"/></svg>
            <svg class="w2" viewBox="0 0 1200 60" preserveAspectRatio="none"><path d="M0 34 Q150 8 300 34 T600 34 T900 34 T1200 34 V60 H0Z"/></svg>
          </div>
          ${this._ring(score, b)}
          <div class="hero-text">
            <div class="name">${esc(this._deviceName)}</div>
            ${metaBits.length ? `<div class="meta">${esc(metaBits.join(" \u00b7 "))}</div>` : ""}
            <div class="status">${status}</div>
            ${ta.date ? `<div class="tested">Tested ${esc(ago(ta.date))}${ta.by ? ` \u00b7 ${esc(ta.by)}` : ""}${inRange ? ` \u00b7 ${esc(inRange)}` : ""}</div>` : ""}
            ${this._spark(ha.trend)}
          </div>
        </div>
        ${tiles ? `<div class="grid">${tiles}</div>` : ""}
        ${sections.length ? `<div class="secs">${sections.join("")}</div>` : ""}
        ${next || due ? `<div class="foot ${due ? "due" : ""}" ${this._map.next_service ? `data-entity="${this._map.next_service}"` : ""}>
          <ha-icon icon="${ICONS.calendar}"></ha-icon>
          <span>Next service <b>${esc(next ? shortDate(next) : "")}</b> ${esc(next ? until(next) : "")}</span>
          ${due ? `<span class="chip bad small">Due</span>` : ""}
        </div>` : ""}
      </ha-card>`;
  }
}

const STYLE = `<style>
  :host {
    --rp-brand: #2e6fd6;
    --rp-muted: var(--secondary-text-color, #8a9bb0);
    --rp-neutral: #4aa3df;
    --rp-surface: color-mix(in srgb, var(--primary-text-color, #000) 4%, transparent);
    --rp-line: var(--divider-color, rgba(127,127,127,.2));
  }
  ha-card { overflow: hidden; }
  button { font: inherit; color: inherit; background: none; border: 0; padding: 0; cursor: pointer; text-align: left; }
  .hero {
    position: relative; display: flex; gap: 14px; align-items: center;
    padding: 18px 18px 30px;
    background: radial-gradient(120% 140% at 0% 0%, #1d4f9e 0%, #0f2a52 45%, #0a1928 100%);
    color: #ecf3f8; overflow: hidden;
  }
  .waves { position: absolute; left: 0; right: 0; bottom: -2px; height: 34px; pointer-events: none; }
  .waves svg { position: absolute; bottom: 0; width: 200%; height: 100%; }
  .waves .w1 path { fill: rgba(79, 160, 240, .18); }
  .waves .w2 path { fill: rgba(31, 182, 198, .16); }
  .waves .w1 { animation: drift 14s linear infinite; }
  .waves .w2 { animation: drift 9s linear infinite reverse; }
  @keyframes drift { from { transform: translateX(0); } to { transform: translateX(-50%); } }
  .ring { position: relative; flex: 0 0 auto; width: 132px; height: 132px; cursor: pointer; z-index: 1; }
  .ring .arc { transition: stroke-dasharray 1s cubic-bezier(.2,.8,.2,1); }
  .ring-num { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; }
  .ring-num span { font-size: 40px; font-weight: 700; line-height: 1; font-variant-numeric: tabular-nums; letter-spacing: -1px; }
  .ring-num small { margin-top: 4px; font-size: 11px; opacity: .6; font-family: ui-monospace, monospace; }
  .hero-text { min-width: 0; flex: 1; z-index: 1; }
  .name { font-size: 20px; font-weight: 700; letter-spacing: -.2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .meta { font-size: 12px; opacity: .7; margin-top: 2px; }
  .status { margin-top: 8px; display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
  .status .band { font-size: 13px; font-weight: 600; }
  .chip { display: inline-flex; align-items: center; gap: 4px; font-size: 12px; font-weight: 700; padding: 4px 10px; border-radius: 999px;
          color: var(--p, #3ccf94); background: color-mix(in srgb, var(--p, #3ccf94) 18%, transparent);
          border: 1px solid color-mix(in srgb, var(--p, #3ccf94) 40%, transparent); }
  .chip.bad { --p: #ff7a6e; }
  .chip.small { padding: 2px 8px; font-size: 11px; }
  .chip ha-icon { --mdc-icon-size: 15px; }
  .tested { font-size: 12px; opacity: .75; margin-top: 8px; }
  .spark { display: flex; align-items: center; gap: 8px; margin-top: 8px; }
  .spark span { font-size: 10px; opacity: .55; text-transform: uppercase; letter-spacing: .6px; white-space: nowrap; }

  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(104px, 1fr)); gap: 8px; padding: 14px 14px 4px; }
  .tile { background: var(--rp-surface); border: 1px solid var(--rp-line); border-radius: 14px; padding: 10px 11px 9px;
          display: flex; flex-direction: column; gap: 3px; transition: transform .15s, border-color .15s; }
  .tile:hover { transform: translateY(-1px); border-color: color-mix(in srgb, var(--c) 55%, var(--rp-line)); }
  .tile.dim { opacity: .55; }
  .t-label { font-size: 12px; color: var(--secondary-text-color); font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .t-val { font-size: 22px; font-weight: 700; color: var(--primary-text-color); font-variant-numeric: tabular-nums; line-height: 1.15; }
  .t-val small { font-size: 11px; font-weight: 600; color: var(--secondary-text-color); margin-left: 3px; }
  .bar { position: relative; height: 6px; border-radius: 3px; background: var(--rp-line); margin: 4px 0 2px; }
  .bar.empty { opacity: .4; }
  .bar .band { position: absolute; top: 0; bottom: 0; border-radius: 3px; background: color-mix(in srgb, #2fbf84 45%, transparent); }
  .bar b { position: absolute; top: 50%; width: 10px; height: 10px; border-radius: 50%; transform: translate(-50%, -50%);
           box-shadow: 0 0 0 2px var(--ha-card-background, var(--card-background-color, #fff)); }
  .t-note { font-size: 11px; color: var(--c); font-weight: 600; min-height: 14px; line-height: 1.3; }
  .tile.dim .t-note { color: var(--secondary-text-color); font-weight: 500; }

  .secs { padding: 10px 14px 6px; display: flex; flex-direction: column; gap: 8px; }
  .sec { border: 1px solid var(--rp-line); border-radius: 14px; overflow: hidden; background: var(--rp-surface);
         border-left: 3px solid var(--accent, var(--rp-line)); }
  .sec-head { width: 100%; display: flex; align-items: center; gap: 10px; padding: 10px 12px; }
  .sec-icon { flex: 0 0 auto; width: 32px; height: 32px; border-radius: 10px; display: grid; place-items: center;
              background: color-mix(in srgb, var(--accent, var(--rp-brand)) 16%, transparent); color: var(--accent, var(--rp-brand)); }
  .sec-icon ha-icon { --mdc-icon-size: 18px; }
  .sec-text { flex: 1; min-width: 0; display: flex; flex-direction: column; }
  .sec-title { font-size: 13px; font-weight: 700; color: var(--primary-text-color); }
  .sec-title em { font-style: normal; font-weight: 500; color: var(--secondary-text-color); margin-left: 6px; font-size: 12px; }
  .sec-sum { font-size: 12.5px; color: var(--secondary-text-color); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .sec.open .sec-sum { white-space: normal; }
  .chev { color: var(--secondary-text-color); transition: transform .2s; --mdc-icon-size: 20px; }
  .sec.open .chev { transform: rotate(180deg); }
  .sec-body { padding: 0 12px 12px 54px; font-size: 13px; color: var(--primary-text-color); animation: open .2s ease-out; }
  @keyframes open { from { opacity: 0; transform: translateY(-4px); } to { opacity: 1; transform: none; } }
  .sec-body ul, .sec-body ol { margin: 6px 0 0; padding-left: 18px; }
  .todo { margin: 2px 0 10px; padding: 10px 12px 8px; border-radius: 10px;
          background: color-mix(in srgb, #ef5b4f 10%, transparent); border: 1px solid color-mix(in srgb, #ef5b4f 28%, transparent); }
  .todo-h { font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: .5px; color: #ef5b4f; }
  .todo ol { margin-top: 4px; }
  .sec-body li { margin: 4px 0; line-height: 1.4; }
  .by { font-size: 12px; color: var(--secondary-text-color); margin-top: 2px; }
  .chips { display: flex; flex-wrap: wrap; gap: 5px; margin-top: 8px; }
  .chips span { font-size: 11px; padding: 3px 8px; border-radius: 999px; background: color-mix(in srgb, var(--rp-brand) 14%, transparent); color: var(--primary-text-color); }
  .mini { display: flex; flex-wrap: wrap; gap: 4px 12px; margin-top: 8px; font-size: 12px; }
  .mini b { font-weight: 600; color: var(--secondary-text-color); }
  .mini i { font-style: normal; color: var(--secondary-text-color); }
  .report { display: inline-flex; align-items: center; gap: 6px; margin-top: 10px; padding: 7px 12px; border-radius: 10px;
            background: var(--rp-brand); color: #fff; font-size: 12.5px; font-weight: 600; }
  .report ha-icon { --mdc-icon-size: 17px; }
  .timeline { margin-top: 4px; display: flex; flex-direction: column; gap: 10px; position: relative; }
  .ev { display: flex; gap: 10px; }
  .ev > i { flex: 0 0 auto; width: 9px; height: 9px; border-radius: 50%; margin-top: 5px; }
  .ev-head { display: flex; align-items: center; gap: 5px; font-size: 12px; color: var(--secondary-text-color); font-weight: 600; }
  .ev-head ha-icon { --mdc-icon-size: 14px; }
  .ev-sum { font-size: 12.5px; line-height: 1.35; }
  .pill { margin-left: 4px; font-size: 10.5px; font-weight: 700; padding: 1px 6px; border-radius: 999px;
          color: var(--p); background: color-mix(in srgb, var(--p) 16%, transparent); }
  .foot { display: flex; align-items: center; gap: 8px; margin: 4px 14px 14px; padding: 10px 12px; border-radius: 12px;
          background: var(--rp-surface); border: 1px solid var(--rp-line); font-size: 13px; color: var(--secondary-text-color); cursor: pointer; }
  .foot b { color: var(--primary-text-color); }
  .foot ha-icon { color: var(--rp-brand); --mdc-icon-size: 18px; }
  .foot.due { border-color: color-mix(in srgb, #ef5b4f 45%, var(--rp-line)); }
  .foot .chip { margin-left: auto; }
  .empty-card { display: flex; gap: 12px; align-items: center; padding: 18px; color: var(--secondary-text-color); font-size: 13px; }
  .empty-card ha-icon { --mdc-icon-size: 32px; color: var(--rp-brand); }
  @media (max-width: 420px) {
    .hero { gap: 10px; padding: 14px 14px 28px; }
    .ring { width: 104px; height: 104px; } .ring svg { width: 104px; height: 104px; }
    .ring-num span { font-size: 32px; }
    .grid { grid-template-columns: repeat(auto-fill, minmax(92px, 1fr)); }
    .spark span { display: none; }
  }
  @media (prefers-reduced-motion: reduce) { .waves svg, .ring .arc, .sec-body { animation: none; transition: none; } }
</style>`;

// \u2500\u2500 Visual editor \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

const SCHEMA = [
  { name: "device_id", selector: { device: { integration: DOMAIN } } },
  { name: "title", selector: { text: {} } },
  {
    type: "grid", name: "", schema: [
      { name: "show_chemistry", selector: { boolean: {} } },
      { name: "show_test", selector: { boolean: {} } },
      { name: "show_visit", selector: { boolean: {} } },
      { name: "show_maintenance", selector: { boolean: {} } },
      { name: "show_history", selector: { boolean: {} } },
      { name: "history_count", selector: { number: { min: 1, max: 20, mode: "box" } } },
    ],
  },
  {
    name: "expand", selector: { select: { mode: "dropdown", options: [
      { value: "", label: "Nothing" },
      { value: "test", label: "Last water test" },
      { value: "visit", label: "Last service visit" },
      { value: "history", label: "History" },
    ] } },
  },
];

const LABELS = {
  device_id: "Pool",
  title: "Title (optional \u2014 defaults to the pool name)",
  show_chemistry: "Readings",
  show_test: "Last water test",
  show_visit: "Last service visit",
  show_maintenance: "Maintenance log",
  show_history: "History",
  history_count: "History entries",
  expand: "Open on load",
};

class RiddsPoolCardEditor extends HTMLElement {
  setConfig(config) {
    this._config = { show_chemistry: true, show_test: true, show_visit: true, show_maintenance: true, show_history: true, history_count: 8, ...config };
    this._render();
  }
  set hass(hass) {
    this._hass = hass;
    this._render();
  }
  _render() {
    if (!this._hass || !this._config) return;
    if (!this._form) {
      this._form = document.createElement("ha-form");
      this._form.computeLabel = (s) => LABELS[s.name] ?? s.name;
      this._form.addEventListener("value-changed", (ev) => {
        const config = { ...ev.detail.value };
        for (const k of ["title", "expand"]) if (!config[k]) delete config[k];
        this._config = config;
        this.dispatchEvent(new CustomEvent("config-changed", { detail: { config }, bubbles: true, composed: true }));
      });
      this.appendChild(this._form);
    }
    this._form.hass = this._hass;
    this._form.schema = SCHEMA;
    this._form.data = this._config;
  }
}

if (!customElements.get("ridds-pool-card")) customElements.define("ridds-pool-card", RiddsPoolCard);
if (!customElements.get("ridds-pool-card-editor")) customElements.define("ridds-pool-card-editor", RiddsPoolCardEditor);

window.customCards = window.customCards || [];
if (!window.customCards.some((c) => c.type === "ridds-pool-card")) {
  window.customCards.push({
    type: "ridds-pool-card",
    name: "Ridd's Pool Card",
    description: "Pool health score, readings, last test and visit, and service history from Ridd's Pool Care.",
    preview: true,
    documentationURL: "https://github.com/merv-gif/ha-ridds-pool-care",
  });
}

console.info(`%c RIDD'S POOL CARD %c ${VERSION} `, "background:#2e6fd6;color:#fff;font-weight:700;border-radius:3px 0 0 3px", "background:#0a1928;color:#5fb3f0;border-radius:0 3px 3px 0");
