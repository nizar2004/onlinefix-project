/* OnlineFix Launcher · web UI logic
   Demo catalog mirrors the reference design exactly; real games from
   Games.ini take over the hero + grid as soon as they exist. */
"use strict";

/* ── demo catalog (the reference design's content) ─────────────────────── */
const IMG = "/assets/img/";
const DEMO = [
  {
    title: "Stray",
    desc: "Lost, alone and separated from family, a stray cat must untangle " +
          "an ancient mystery to escape a long-forgotten cybercity and find " +
          "their way home.",
    price: "$16.99 USD",
    hero: IMG + "stray-hero.jpg",
    cover: IMG + "stray-hero.jpg",
    tags: ["Cats", "Adventure", "Cyberpunk", "Atmospheric"],
    thumbs: [IMG + "stray-thumb1.jpg", IMG + "stray-thumb2.jpg"],
    demo: true,
  },
  {
    title: "Hogwarts Legacy",
    desc: "Experience the wizarding world in the 1800s — learn spells, brew " +
          "potions and face a hidden truth that threatens the magic all around.",
    price: "$59.99 USD",
    hero: IMG + "hogwarts.jpg",
    cover: IMG + "hogwarts-p.jpg",
    tags: ["Adventure", "Magic", "Open World"],
    thumbs: [IMG + "hogwarts.jpg"],
    demo: true,
  },
  {
    title: "Call of Duty: Infinite Warfare",
    desc: "Take to the stars in a war beyond Earth — dogfights, zero-g " +
          "combat and a fight for the survival of humanity.",
    price: "$49.99 USD",
    hero: IMG + "cod.jpg",
    cover: IMG + "cod-p.jpg",
    tags: ["FPS", "Action", "Sci-Fi"],
    thumbs: [IMG + "cod.jpg"],
    demo: true,
  },
  {
    title: "FIFA 23",
    desc: "The world's game — hyper-realistic football with the biggest " +
          "clubs, players and tournaments on the planet.",
    price: "$69.99 USD",
    hero: IMG + "fifa.jpg",
    cover: IMG + "fifa-p.jpg",
    tags: ["Sports", "Football", "Multiplayer"],
    thumbs: [IMG + "fifa.jpg"],
    demo: true,
  },
  {
    title: "Mass Effect Andromeda",
    desc: "Lead humanity's fight for a new home in the Andromeda galaxy — " +
          "a journey to the next frontier of space.",
    price: "$19.99 USD",
    hero: IMG + "masseffect.jpg",
    cover: IMG + "masseffect.jpg",
    tags: ["RPG", "Sci-Fi", "Space"],
    thumbs: [IMG + "masseffect.jpg"],
    demo: true,
  },
];

/* ── tiny helpers ──────────────────────────────────────────────────────── */
const $  = (sel) => document.querySelector(sel);
const $$ = (sel) => [...document.querySelectorAll(sel)];

let toastTimer = null;
function toast(msg) {
  const el = $("#toast");
  el.textContent = msg;
  el.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove("show"), 2600);
}

async function api(path, body) {
  const res = await fetch(path, body ? {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  } : undefined);
  return res.json();
}

const fmtTime = (s) => {
  if (!s) return "";
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60);
  return h ? `${h}h ${m}m` : `${m}m`;
};

/* ── state ─────────────────────────────────────────────────────────────── */
let slides = [];            // hero slides
let slideIndex = 0;
let heroTimer = null;
let realGames = [];         // games from Games.ini
let runningName = null;

/* ── nav ───────────────────────────────────────────────────────────────── */
function setIndicator(item) {
  const ind = $("#navIndicator");
  const app = $("#app");
  const appR = app.getBoundingClientRect();
  const r = item.getBoundingClientRect();
  const top = r.top - appR.top + r.height / 2;
  ind.style.transform = `translateY(${top - 13}px)`;
  ind.style.height = "26px";
  app.classList.add("indicator-on");
}

function switchPage(name, item) {
  $$(".nav-item").forEach((n) => n.classList.toggle("active", n === item));
  setIndicator(item);
  $$(".page").forEach((p) =>
    p.classList.toggle("active", p.id === "page-" + name));
}

function initNav() {
  // the floating indicator lives at the app container's left edge
  $("#app").appendChild($("#navIndicator"));
  const items = $$(".nav-item");
  items.forEach((item) => {
    item.addEventListener("click", (e) => {
      e.preventDefault();
      switchPage(item.dataset.page, item);
    });
  });
  const first = items.find((i) => i.classList.contains("active")) || items[0];
  requestAnimationFrame(() => setIndicator(first));
  window.addEventListener("resize", () => {
    const active = $$(".nav-item").find((i) => i.classList.contains("active"));
    if (active) setIndicator(active);
  });
}

/* ── hero carousel ─────────────────────────────────────────────────────── */
function renderSlide(i) {
  const s = slides[i];
  if (!s) return;
  slideIndex = i;

  $$(".hero-layer").forEach((l, li) => {
    const active = li === i;
    l.classList.toggle("is-active", active);
    const img = l.querySelector("img");
    if (active && img && img.dataset.src !== s.hero) {
      img.src = s.hero;
      img.dataset.src = s.hero;
      img.style.animation = "none";
      void img.offsetWidth;               // restart ken-burns
      img.style.animation = "kenburns 9s var(--ease) both";
    }
  });

  const bg = $("#infoBg");
  bg.style.opacity = "0";
  setTimeout(() => { bg.src = s.hero; bg.style.opacity = "1"; }, 180);
  $("#infoTitle").textContent = s.title;
  $("#infoDesc").textContent = s.desc;
  $("#infoPrice").textContent = s.price || "";

  const chips = $("#heroChips");
  chips.innerHTML = "";
  (s.tags || []).forEach((t) => {
    const c = document.createElement("span");
    c.className = "chip";
    c.textContent = t;
    chips.appendChild(c);
  });
  const plus = document.createElement("button");
  plus.className = "chip chip-plus";
  plus.textContent = "+";
  plus.addEventListener("click", () => toast("Custom filters are coming soon"));
  chips.appendChild(plus);

  const th = s.thumbs && s.thumbs.length ? s.thumbs : [s.cover];
  $("#thumb1").src = th[0] || s.cover;
  $("#thumb2").src = th[1] || th[0] || s.cover;

  $$("#dots .dot").forEach((d, di) => d.classList.toggle("active", di === i));
  updatePlayButton();
}

function buildDots() {
  const dots = $("#dots");
  dots.innerHTML = "";
  slides.forEach((s, i) => {
    const d = document.createElement("button");
    d.className = "dot" + (i === slideIndex ? " active" : "");
    d.setAttribute("aria-label", s.title);
    d.addEventListener("click", () => { renderSlide(i); restartTimer(); });
    dots.appendChild(d);
  });
}

function restartTimer() {
  clearInterval(heroTimer);
  heroTimer = setInterval(() => {
    renderSlide((slideIndex + 1) % slides.length);
  }, 6500);
}

function buildHeroLayers() {
  const hero = $("#hero");
  hero.querySelectorAll(".hero-layer").forEach((l, i) => {
    if (i > 0) l.remove();
  });
  slides.forEach((s, i) => {
    if (i === 0) {
      const img = hero.querySelector(".hero-layer img");
      img.src = s.hero;
      img.dataset.src = s.hero;
      return;
    }
    const div = document.createElement("div");
    div.className = "hero-layer";
    const img = document.createElement("img");
    img.className = "hero-img";
    img.src = s.hero;
    img.alt = s.title || "";
    div.appendChild(img);
    hero.insertBefore(div, hero.querySelector(".hero-shade"));
  });
  buildDots();
}

function initHero() { buildHeroLayers(); renderSlide(0); restartTimer(); }

/* ── play / stop ───────────────────────────────────────────────────────── */
function updatePlayButton() {
  const s = slides[slideIndex];
  if (!s) return;
  const btn = $("#playBtn");
  const runningNow = !!s.real && s.name === runningName;
  btn.textContent = runningNow ? "Stop" : "Available now";
  btn.classList.toggle("stop", runningNow);
}

$("#playBtn").addEventListener("click", async () => {
  const s = slides[slideIndex];
  if (!s) return;
  if (!s.real) {
    toast("This is a demo game — add your own games to launch them");
    return;
  }
  if (runningName === s.name) {
    await api("/api/stop", {});
    toast(`Stopping ${s.name}…`);
  } else {
    const res = await api("/api/launch", { name: s.name });
    toast(res.ok ? `Launching ${s.name}…` : (res.error || "Could not launch"));
  }
  refreshState();
});

/* ── game cards ────────────────────────────────────────────────────────── */
function cardHTML(game, idx) {
  const art = game.banner
    ? `/api/banner?path=${encodeURIComponent(game.banner)}`
    : (game.cover || "");
  const playing = game.name === runningName;
  return `
  <div class="card ${playing ? "running" : ""}"
       data-name="${game.name.replace(/"/g, "&quot;")}"
       style="animation-delay:${0.28 + idx * 0.06}s">
    <img src="${art}" alt="" loading="lazy" onerror="this.style.display='none'">
    <span class="card-badge">${playing ? "RUNNING" : (game.demo ? "DEMO" : "INSTALLED")}</span>
    <span class="card-title">${game.title}</span>
    <div class="card-actions">
      ${game.real ? `
      <button data-act="settings" title="Game settings">
        <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="2.4"/><path d="M12 5.2v2M12 16.8v2M5.2 12h2M16.8 12h2M7.4 7.4l1.4 1.4M15.2 15.2l1.4 1.4M16.6 7.4l-1.4 1.4M8.8 15.2l-1.4 1.4"/></svg>
      </button>
      <button data-act="play" title="Play">
        <svg viewBox="0 0 24 24"><path d="M8.5 6.5l9 5.5-9 5.5z"/></svg>
      </button>` : ""}
    </div>
  </div>`;
}

function renderGrid(el, list) {
  el.innerHTML = list.map(cardHTML).join("");
  el.querySelectorAll(".card").forEach((card) => {
    const name = card.dataset.name;
    const game = list.find((g) => g.name === name);
    card.addEventListener("click", (e) => {
      const act = e.target.closest("[data-act]");
      if (act) {
        e.stopPropagation();
        if (act.dataset.act === "play") {
          if (game.real) {
            api("/api/launch", { name: game.name })
              .then((r) => toast(r.ok ? `Launching ${game.name}…`
                                      : (r.error || "Could not launch")));
          } else {
            toast("This is a demo game");
          }
        } else {
          api("/api/game-settings", { name: game.name })
            .then((r) => toast(r.ok ? `Opening settings for ${game.name}…`
                                   : (r.error || "Cannot open settings")));
        }
        return;
      }
      // clicking a card features it in the hero
      const idx = slides.findIndex((s) => s.name === game.name);
      if (idx >= 0) { renderSlide(idx); restartTimer(); }
      else if (game.demo) toast("Demo game — add your own games to launch them");
    });
  });
}

function demoAsGames() {
  return DEMO.map((d) => ({
    name: d.title, title: d.title, demo: true, cover: d.cover, banner: "",
  }));
}

function realAsSlides() {
  return realGames.map((g) => {
    const played = g.timeSpent ? `Played ${fmtTime(g.timeSpent)}` : "Never played";
    return {
      name: g.name, title: g.name, real: true,
      hero: g.banner ? `/api/banner?path=${encodeURIComponent(g.banner)}` : "",
      cover: g.banner ? `/api/banner?path=${encodeURIComponent(g.banner)}` : "",
      banner: g.banner,
      tags: ["Installed", g.proton ? "Proton " + g.proton.replace(/^Proton-?/, "") : "Proton"],
      desc: `Installed on your machine · ${played}`,
      price: "In your library",
      thumbs: g.banner ? [g.cover] : [],
    };
  });
}

function renderAll() {
  const real = realGames;
  slides = real.length ? realAsSlides()
                       : DEMO.map((d) => ({ ...d, name: d.title }));
  buildHeroLayers();
  renderSlide(0);
  restartTimer();

  const gridList = real.length
    ? (real.length > 1 ? realAsSlides().slice(1) : realAsSlides())
    : demoAsGames().filter((g) => g.name !== slides[0].name);
  renderGrid($("#offers"), gridList);
  renderGrid($("#libraryGrid"), real.map((g) => ({
    ...g, title: g.name, real: true,
    cover: g.banner ? `/api/banner?path=${encodeURIComponent(g.banner)}` : "",
  })));

  $("#libraryEmpty").style.display = real.length ? "none" : "flex";
  $("#libraryGrid").style.display = real.length ? "grid" : "none";
}

/* ── search ────────────────────────────────────────────────────────────── */
function applyFilter(q) {
  q = q.toLowerCase().trim();
  ["#offers", "#libraryGrid"].forEach((sel) => {
    const grid = $(sel);
    if (!grid) return;
    grid.querySelectorAll(".card").forEach((card) => {
      const name = (card.dataset.name || "").toLowerCase();
      card.style.display = !q || name.includes(q) ? "" : "none";
    });
  });
}
$("#searchInput").addEventListener("input", (e) => applyFilter(e.target.value));

/* ── polling: state + games ────────────────────────────────────────────── */
async function refreshState() {
  try {
    const st = await api("/api/state");
    runningName = st.running || null;
    if (st.mode === "pywebview") $("#winControls").hidden = false;
    updatePlayButton();
    $$("#offers .card, #libraryGrid .card").forEach((c) => {
      const isRunning = c.dataset.name === runningName;
      c.classList.toggle("running", isRunning);
      const badge = c.querySelector(".card-badge");
      const isReal = realGames.some((g) => g.name === c.dataset.name);
      if (badge) badge.textContent = isRunning ? "RUNNING"
                                  : (isReal ? "INSTALLED" : "DEMO");
    });
  } catch (_) { /* backend gone */ }
}

let lastGameCount = -1;
async function refreshGames(silent) {
  try {
    const games = await api("/api/games");
    if (games.length !== lastGameCount) {
      const changed = lastGameCount !== -1 && games.length !== lastGameCount;
      lastGameCount = games.length;
      realGames = games;
      renderAll();
      if (changed && !silent) toast("Library updated ✔");
    }
  } catch (_) { /* ignore */ }
}

/* ── window controls (pywebview frameless) ─────────────────────────────── */
$("#winControls").addEventListener("click", (e) => {
  const btn = e.target.closest("[data-win]");
  if (!btn) return;
  api("/api/window", { action: btn.dataset.win });
});

/* ── misc buttons ──────────────────────────────────────────────────────── */
$("#bellBtn").addEventListener("click", () => toast("No new notifications"));
$("#cartBtn").addEventListener("click", () => toast("Your cart is empty"));
$("#learnMore").addEventListener("click", () => toast("Special offers refresh every week"));

$$(".thumb").forEach((t) =>
  t.addEventListener("click", () => toast("Screenshot viewer is coming soon")));

const openAddGame = () => {
  api("/api/add-game", {})
    .then((r) => toast(r.ok ? "The add-game wizard has opened"
                           : (r.error || "Cannot open the wizard")));
};
$("#addBtn").addEventListener("click", openAddGame);
$("#addBtn2").addEventListener("click", openAddGame);
$("#addBtn3").addEventListener("click", openAddGame);

$("#openSettingsBtn").addEventListener("click", () => {
  api("/api/open-settings", {})
    .then((r) => toast(r.ok ? "Classic settings opened"
                            : (r.error || "Cannot open settings")));
});
$("#openFolderBtn").addEventListener("click", async () => {
  const st = await api("/api/state");
  if (st.configDir) await api("/api/open", { kind: "path", target: st.configDir });
});
$$("[data-url]").forEach((b) => b.addEventListener("click", () => {
  api("/api/open", { kind: "url", target: b.dataset.url });
}));

/* ── boot ──────────────────────────────────────────────────────────────── */
(async function boot() {
  initNav();
  try {
    const st = await api("/api/state");
    if (st.mode === "pywebview") $("#winControls").hidden = false;
    if (st.configDir) $("#configDirText").textContent = st.configDir;
    if (st.version) $("#versionText").textContent =
      `OnlineFix Linux Launcher v${st.version}`;
  } catch (_) {}

  await refreshGames(true);
  setInterval(refreshState, 2500);
  setInterval(() => refreshGames(false), 5000);
})();
