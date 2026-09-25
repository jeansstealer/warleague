"use strict";

// Renders league.json (built by scripts/ingest.py) into the round report.
// All guild names go in through textContent.

const MY_GUILD_ID = "0d554976-a191-4691-8af5-d1481f417203";  // highlighted in the table
const WARS_PER_SEASON = 6;
const METALS = ["iron", "bronze", "silver", "gold", "diamond"];
const TIERS = ["I", "II", "III", "IV"];

const app = document.getElementById("app");
const roundsNav = document.getElementById("rounds");
const updated = document.getElementById("updated");

const league = n => ({ metal: METALS[Math.min(4, Math.floor(n / 4))], tier: n >= 16 ? "I" : TIERS[n % 4] });
const leagueName = n => { const l = league(n); return l.metal[0].toUpperCase() + l.metal.slice(1) + " " + l.tier; };
const count = n => Number(n).toLocaleString("en-US");
const signed = n => (n > 0 ? "+" : n < 0 ? "−" : "±") + Math.abs(n);
const tone = n => n > 0 ? "up" : n < 0 ? "down" : "flat";
function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined && text !== null) e.textContent = String(text);
  return e;
}
function emb(n) {
  const l = league(n);
  const e = el("span", "emb " + l.metal, l.tier);
  e.title = leagueName(n);
  return e;
}
function section(title, aside) {
  const s = el("section");
  const h = el("div", "head");
  h.append(el("h2", "", title));
  if (aside) h.append(el("span", "", aside));
  s.append(h);
  return s;
}

// ---------- round navigation ----------
function nav(data, cur) {
  roundsNav.replaceChildren();
  const seasons = data.seasons || [];
  if (seasons.length > 1) {
    const sel = el("select", "seasons");
    sel.setAttribute("aria-label", "Season");
    seasons.forEach(s => {
      const o = el("option", "", "Season " + s.season);
      o.value = s.season;
      if (s.season === cur.season) o.selected = true;
      sel.append(o);
    });
    sel.onchange = () => {
      const s = seasons.find(x => String(x.season) === sel.value);
      go(s.season, s.rounds[s.rounds.length - 1]);
    };
    roundsNav.append(sel);
  }
  const have = new Set(((seasons.find(s => s.season === cur.season) || {}).rounds) || []);
  for (let i = 1; i <= WARS_PER_SEASON; i++) {
    const b = el("button", "", "R" + i);
    b.type = "button";
    b.setAttribute("aria-pressed", String(i === cur.round));
    b.disabled = !have.has(i);
    b.title = have.has(i) ? `Season ${cur.season}, round ${i}` : "No capture for this round";
    b.onclick = () => go(cur.season, i);
    roundsNav.append(b);
  }
}
function go(season, round) {
  const u = new URL(location.href);
  u.searchParams.set("season", season);
  u.searchParams.set("round", round);
  history.pushState(null, "", u);
  show(window.__league);
}

// ---------- sections ----------
function hero(r) {
  const s = el("section", "hero");
  const label = r.round === 0 ? `Season ${r.season} · before round 1` : `Season ${r.season} · Round ${r.round} results`;
  s.append(el("p", "kicker", label), el("h1", "", "War League"));
  const p = el("p", "summary");
  (r.summary || []).forEach(part => p.append(part.b ? el("b", "", part.t) : document.createTextNode(part.t)));
  s.append(p);
  if (r.comparedWith) {
    const st = r.stats || {};
    const chips = el("div", "chips");
    [[st.won, "Won", "up"], [st.lost, "Lost", "down"], [st.promoted, "Promoted", "gold"], [st.entered, "New in top 50", "gold"]]
      .forEach(([v, l, c]) => { const x = el("div", "chip " + c); x.append(el("strong", "num", v || 0), el("span", "", l)); chips.append(x); });
    s.append(chips);
  }
  if (r.covers) s.append(el("p", "covers", `No capture after round ${r.covers[1] - 1}, so these changes cover rounds ${r.covers[0]}–${r.covers[1]}.`));
  return s;
}

function summit(r) {
  const s = section("The summit", "Top 3 by trophies");
  const g = el("div", "podium");
  [1, 0, 2].forEach(i => {
    const row = r.table[i];
    if (!row) return;
    const c = el("div", "pod p" + (i + 1));
    c.append(el("div", "place", "#" + (i + 1)), emb(row.league), el("div", "gname", row.name),
      el("div", "tro num", count(row.trophies)),
      el("div", "delta " + tone(row.dT || 0), row.dT == null ? (r.comparedWith ? "new" : "") : signed(row.dT) + " this round"));
    g.append(c);
  });
  s.append(g);
  return s;
}

function leagueChanges(r) {
  const rows = (r.promoted || []).concat(r.demoted || []);
  if (!rows.length) return null;
  const s = section("League changes", "Promotions and demotions");
  const g = el("div", "grid2");
  rows.forEach(row => {
    const c = el("div", "promo");
    const f = el("div", "from"); f.append(emb(row.prevLeague), el("span", "", leagueName(row.prevLeague)));
    const t = el("div", "to"); t.append(el("span", "", leagueName(row.league)), emb(row.league));
    const up = row.league > row.prevLeague;
    const a = el("span", "arrow", up ? "▲" : "▼");
    if (!up) a.style.color = "var(--down)";
    c.append(el("div", "who", row.name), f, a, t);
    g.append(c);
  });
  s.append(g);
  return s;
}

function listCard(title, items, right, empty) {
  const c = el("div", "card");
  c.append(el("h3", "", title));
  const ul = el("ul", "list");
  items.forEach(row => {
    const li = el("li");
    const n = el("span", "name", row.name);
    n.append(el("span", "sub", `#${row.rank} · ${leagueName(row.league)}`));
    li.append(emb(row.league), n, right(row));
    ul.append(li);
  });
  if (!items.length) { const li = el("li", "sub", empty); li.style.display = "block"; ul.append(li); }
  c.append(ul);
  return c;
}

function results(r) {
  if (!r.comparedWith) return null;
  const s = section("Round results", "From each guild's trophy change");
  const g = el("div", "grid2");
  const d = (row, cls, text) => el("span", "delta num " + cls, text);
  g.append(
    listCard("Lost their war", r.lost, row => d(row, "down", signed(row.dT)), "No top-50 guild lost"),
    listCard("Biggest wins", r.won.slice(0, 5), row => d(row, "up", signed(row.dT)), "No wins recorded"),
    listCard("Climbers", r.climbers, row => d(row, "up", "▲ " + row.dR), "No rank changes"),
    listCard("Top 50 in and out", r.entered.map(x => Object.assign({ tag_: "new" }, x)).concat(r.left.map(x => Object.assign({ tag_: "left" }, x))),
      row => d(row, row.tag_ === "new" ? "up" : "down", row.tag_), "No change"),
  );
  s.append(g);
  return s;
}

// Trophy line for one guild across every captured round.
function sparkline(hist) {
  const NS = "http://www.w3.org/2000/svg";
  const W = 600, H = 70, P = 16;
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  svg.setAttribute("class", "spark");
  const vals = hist.map(h => h.trophies);
  const lo = Math.min(...vals), hi = Math.max(...vals), span = Math.max(1, hi - lo);
  const x = i => hist.length === 1 ? W / 2 : P + i * (W - 2 * P) / (hist.length - 1);
  const y = v => H - 20 - (v - lo) / span * (H - 34);
  const mk = (tag, attrs, text) => { const e = document.createElementNS(NS, tag); Object.entries(attrs).forEach(([k, v]) => e.setAttribute(k, v)); if (text != null) e.textContent = text; return e; };
  svg.append(mk("polyline", { class: "line", points: hist.map((h, i) => `${x(i)},${y(h.trophies)}`).join(" ") }));
  hist.forEach((h, i) => {
    svg.append(mk("circle", { class: "dot", cx: x(i), cy: y(h.trophies), r: 3 }));
    svg.append(mk("text", { x: x(i), y: H - 4, "text-anchor": "middle" }, `S${h.season} R${h.round}`));
    svg.append(mk("text", { x: x(i), y: y(h.trophies) - 7, "text-anchor": "middle" }, count(h.trophies)));
  });
  return svg;
}

function topTable(r, history) {
  const s = section("Top 50", r.comparedWith ? `${r.idleCount} guilds did not fight this round` : "As captured");
  const filters = el("div", "filters");
  const present = new Set(r.table.map(x => league(x.league).metal));
  let only = "all";
  ["all"].concat(METALS.slice().reverse().filter(m => present.has(m))).forEach(k => {
    const b = el("button", k === "all" ? "on" : "", k === "all" ? "All leagues" : k[0].toUpperCase() + k.slice(1));
    b.type = "button";
    b.onclick = () => { only = k; filters.querySelectorAll("button").forEach(x => x.classList.toggle("on", x === b)); paint(); };
    filters.append(b);
  });
  if (present.size > 1) s.append(filters);
  const table = el("table", "num");
  const head = el("tr");
  [["#", ""], ["Move", "hide-sm"], ["Guild", ""], ["Trophies", "r"], ["Round", "r"], ["Country", "hide-sm"]]
    .forEach(([t, c]) => head.append(el("th", c, t)));
  const thead = el("thead"); thead.append(head);
  const tb = el("tbody");
  table.append(thead, tb);
  s.append(table, el("p", "covers", "Click a guild to see its trophies over every round."));

  function paint() {
    tb.replaceChildren();
    r.table.filter(row => only === "all" || league(row.league).metal === only).forEach(row => {
      const tr = el("tr", row.guildId === MY_GUILD_ID ? "mine" : "");
      const g = el("td");
      g.append(emb(row.league), document.createTextNode(row.name));
      if (row.isNew && r.comparedWith) g.append(el("span", "new", "NEW"));
      if (row.prevName) g.append(el("span", "renamed", "was " + row.prevName));
      const mv = el("td", "hide-sm");
      mv.append(el("span", "move delta " + tone(row.dR || 0), row.dR == null ? "—" : row.dR > 0 ? "▲" + row.dR : row.dR < 0 ? "▼" + (-row.dR) : "·"));
      tr.append(el("td", "", row.rank), mv, g, el("td", "r", count(row.trophies)),
        el("td", "r delta " + tone(row.dT || 0), row.dT == null ? (r.comparedWith ? "new" : "—") : signed(row.dT)),
        el("td", "hide-sm", row.country || ""));
      tr.onclick = () => {
        const open = tr.nextElementSibling && tr.nextElementSibling.classList.contains("history-row");
        tb.querySelectorAll(".history-row").forEach(x => x.remove());
        if (open) return;
        const hist = history[row.guildId || ("name:" + row.name)] || [];
        const hr = el("tr", "history-row");
        const td = el("td");
        td.colSpan = 6;
        td.append(sparkline(hist), el("p", "history-meta",
          hist.map(h => `S${h.season} R${h.round}: #${h.rank} · ${leagueName(h.league)}`).join("   ·   ")));
        hr.append(td);
        tr.after(hr);
      };
      tb.append(tr);
    });
  }
  paint();
  return s;
}

// ---------- page ----------
function show(data) {
  const q = new URLSearchParams(location.search);
  const key = q.get("season") && q.get("round") ? `${q.get("season")}-${q.get("round")}` : data.latest;
  const r = data.reports[key] || data.reports[data.latest];
  nav(data, r);
  app.replaceChildren(...[hero(r), summit(r), leagueChanges(r), results(r), topTable(r, data.history || {})].filter(Boolean));
  document.title = `War League · Season ${r.season}` + (r.round ? ` · Round ${r.round}` : "");
  updated.textContent = "Captured " + new Date(r.capturedAt).toLocaleString();
}

window.addEventListener("popstate", () => window.__league && show(window.__league));
fetch("./league.json", { cache: "no-store" })
  .then(res => { if (!res.ok) throw new Error("HTTP " + res.status); return res.json(); })
  .then(data => {
    if (!data.latest) { app.replaceChildren(el("p", "empty", "No capture yet. The first round report appears after the leaderboard is captured.")); return; }
    window.__league = data;
    show(data);
  })
  .catch(() => app.replaceChildren(el("p", "empty", "The report is temporarily unavailable. Try again later.")));
