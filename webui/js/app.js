/* OnlineFix Launcher · web UI logic
   The store page shows only the games the launcher actually manages; every
   control is wired to the project's own storage (Games.ini / Launcher.ini)
   through the local JSON API served by app/webserver.py. */
"use strict";

/* ── tiny helpers ──────────────────────────────────────────────────────── */
const $  = (sel) => document.querySelector(sel);
const $$ = (sel) => [...document.querySelectorAll(sel)];

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
  "&#" + c.charCodeAt(0) + ";");

let toastTimer = null;
function toast(msg) {
  const el = $("#toast");
  el.textContent = msg;
  el.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove("show"), 3000);
}

async function api(path, body) {
  try {
    const res = await fetch(path, body ? {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    } : undefined);
    return await res.json();
  } catch (err) {
    return { ok: false, error: String(err && err.message ? err.message : err) };
  }
}

/* human playtime — same wording as the classic launcher */
const fmtTime = (s) => {
  s = Math.floor(Number(s) || 0);
  if (s <= 0) return "Never played";
  if (s < 60) return "Less than a minute";
  const minutes = Math.floor(s / 60);
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(s / 3600);
  const rem = Math.floor((s % 3600) / 60);
  if (hours < 24) return rem ? `${hours} h ${rem} min` : `${hours} h`;
  const days = Math.floor(hours / 24);
  const restHours = hours % 24;
  return restHours ? `${days} d ${restHours} h` : `${days} d`;
};

const fmtSize = (b) => {
  if (!b) return "";
  const units = ["B", "KB", "MB", "GB"];
  let i = 0, n = b;
  while (n >= 1024 && i < units.length - 1) { n /= 1024; i++; }
  return `${n.toFixed(n < 10 && i > 0 ? 1 : 0)} ${units[i]}`;
};

const artUrl = (path, kind) => path
  ? `/api/${kind || "banner"}?path=${encodeURIComponent(path)}`
  : "";

/* ── state ─────────────────────────────────────────────────────────────── */
let slides = [];            // hero slides
let slideIndex = 0;
let heroTimer = null;
let realGames = [];         // games from Games.ini
let runningName = null;
let launchStatus = null;    // "preparing" | "running"
let currentGame = null;     // game open in the settings page
let launcherCfg = null;     // launcher preferences cache
let protonPoll = null;      // proton download poller

/* ── nav ───────────────────────────────────────────────────────────────── */
function setIndicator(item) {
  if (!item) return;
  const ind = $("#navIndicator");
  const app = $("#app");
  const appR = app.getBoundingClientRect();
  const r = item.getBoundingClientRect();
  const top = r.top - appR.top + r.height / 2;
  ind.style.transform = `translateY(${top - 13}px)`;
  ind.style.height = "26px";
  app.classList.add("indicator-on");
}

function navItem(page) {
  return $$(".nav-item").find((n) => n.dataset.page === page);
}

function switchPage(name, item) {
  const target = item || navItem(name);
  $$(".nav-item").forEach((n) => n.classList.toggle("active", n === target));
  if (target) setIndicator(target);
  $$(".page").forEach((p) =>
    p.classList.toggle("active", p.id === "page-" + name));
}

function initNav() {
  // the floating indicator lives at the app container's left edge
  $("#app").appendChild($("#navIndicator"));
  $$(".nav-item").forEach((item) => {
    item.addEventListener("click", (e) => {
      e.preventDefault();
      switchPage(item.dataset.page, item);
      if (item.dataset.page === "library") refreshGames(false);
      if (item.dataset.page === "runners") loadProtons();
      if (item.dataset.page === "settings") renderSettings();
    });
  });
  const first = $$(".nav-item").find((i) => i.classList.contains("active"))
                || $$(".nav-item")[0];
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

  // the game's own icon (avatar) next to the name
  const avatar = $("#infoAvatar");
  if (s.avatar) {
    avatar.src = s.avatar;
    avatar.hidden = false;
    avatar.alt = s.title || "";
  } else {
    avatar.removeAttribute("src");
    avatar.hidden = true;
  }

  // play time
  $("#infoPlaytime").innerHTML = s.playTime
    ? `<svg viewBox="0 0 24 24" aria-hidden="true">
         <circle cx="12" cy="12" r="8.4"/><path d="M12 7.6V12l3 1.8"/>
       </svg><span>${esc(s.playTime)}</span>`
    : "";

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

  const th = (s.thumbs && s.thumbs.length) ? s.thumbs : [s.cover];
  const thumbsRow = $("#thumb1").parentElement;
  $("#thumb1").src = th[0] || s.cover;
  $("#thumb2").src = th[1] || th[0] || s.cover;
  // hide a single lonely thumbnail instead of repeating the same art
  $("#thumb2").style.display = th.length > 1 ? "" : "none";
  thumbsRow.style.justifyContent = th.length > 1 ? "" : "flex-start";

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
  if (slides.length < 2) return;
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
  btn.textContent = runningNow ? "Stop"
    : (s.real ? "Play" : "Available now");
  btn.classList.toggle("stop", runningNow);
  btn.disabled = launchStatus === "preparing" || launchStatus === "stopping";
  if (launchStatus === "stopping") btn.textContent = "Stopping…";
}

async function launchGame(name) {
  const res = await api("/api/launch", { name });
  if (res.ok) {
    toast(res.cancelling ? "Cancelling…" : (res.note || `Launching ${name}…`));
    launchStatus = res.status || "preparing";
  } else {
    toast(res.error || "Could not launch");
  }
  refreshState();
}

async function stopGame() {
  const name = runningName || (currentGame && currentGame.name) || "";
  const res = await api("/api/stop", { name });
  toast(res.ok ? "Stopping game…" : (res.error || "Nothing is running"));
  if (res.ok) launchStatus = "stopping";
  refreshState();
}

$("#playBtn").addEventListener("click", async () => {
  const s = slides[slideIndex];
  if (!s) return;
  if (runningName === s.name) await stopGame();
  else await launchGame(s.name);
});

/* ── game cards ────────────────────────────────────────────────────────── */
function cardHTML(game, idx) {
  const art = game.banner ? artUrl(game.banner, "banner")
                          : (game.icon ? artUrl(game.icon, "icon") : (game.cover || ""));
  const playing = game.name === runningName;
  const badge = playing ? "RUNNING" : "INSTALLED";
  return `
  <div class="card ${playing ? "running" : ""}"
       data-name="${esc(game.name)}"
       style="animation-delay:${0.28 + idx * 0.06}s">
    <img src="${esc(art)}" alt="" loading="lazy" onerror="this.style.display='none'">
    <span class="card-badge">${badge}</span>
    <span class="card-time">${esc(game.timeSpent ? `Played ${fmtTime(game.timeSpent)}` : "")}</span>
    <span class="card-title">${esc(game.title || game.name)}</span>
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
  if (!el) return;
  el.innerHTML = list.map(cardHTML).join("");
  el.querySelectorAll(".card").forEach((card) => {
    const name = card.dataset.name;
    const game = list.find((g) => g.name === name);
    if (!game) return;
    card.addEventListener("click", (e) => {
      const act = e.target.closest("[data-act]");
      if (act) {
        e.stopPropagation();
        if (act.dataset.act === "play") {
          if (runningName === game.name) stopGame();
          else launchGame(game.name);
        } else {
          openGameSettings(game.name);
        }
        return;
      }
      // clicking a card features it in the hero
      const idx = slides.findIndex((s) => s.name === game.name);
      if (idx >= 0) { renderSlide(idx); restartTimer(); }
    });
  });
}

function realAsSlides() {
  return realGames.map((g) => {
    const played = g.timeSpent ? `Played ${fmtTime(g.timeSpent)}` : "Never played";
    const bannerUrl = g.banner ? artUrl(g.banner, "banner") : "";
    const iconUrl = g.icon ? artUrl(g.icon, "icon") : "";
    // the two slots under the info card: banner first, icon as the second
    const thumbs = [bannerUrl, iconUrl].filter(Boolean);
    return {
      name: g.name, title: g.name, real: true,
      hero: bannerUrl || iconUrl,
      cover: bannerUrl || iconUrl,
      banner: g.banner,
      icon: g.icon,
      avatar: iconUrl,
      thumbs,
      tags: ["Installed",
             g.proton ? "Proton " + g.proton.replace(/^Proton-?/, "") : "Proton"],
      desc: `Installed on your machine · ${played}`,
      price: "In your library",
      playTime: played,
    };
  });
}

function renderAll() {
  // Only the games the launcher manages — no demo catalogue.
  slides = realAsSlides();
  buildHeroLayers();
  renderSlide(0);
  restartTimer();

  const hasGames = realGames.length > 0;
  $("#storeEmpty").hidden = hasGames;
  $("#page-store .hero-row").style.display = hasGames ? "" : "none";
  $("#dots").style.display = hasGames ? "" : "none";
  $("#page-store .offers-head").style.display = hasGames ? "" : "none";
  $("#offers").style.display = hasGames ? "" : "none";

  renderGrid($("#offers"), realGames.map((g) => ({
    ...g, title: g.name, real: true,
    cover: artUrl(g.banner || g.icon, "banner"),
  })));

  renderLibrary();
  applyFilter($("#searchInput").value);
}

function renderLibrary() {
  const grid = $("#libraryGrid");
  const empty = $("#libraryEmpty");
  const list = realGames.map((g) => ({
    ...g, title: g.name, real: true,
    cover: artUrl(g.banner || g.icon, "banner"),
  }));
  renderGrid(grid, list);
  empty.style.display = list.length ? "none" : "flex";
  grid.style.display = list.length ? "grid" : "none";
}

/* ── search ────────────────────────────────────────────────────────────── */
function applyFilter(q) {
  q = (q || "").toLowerCase().trim();
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

/* ── ADD A GAME wizard ─────────────────────────────────────────────────── */
let wzSelection = null;      // { path, dir, type }

function resetWizard() {
  wzSelection = null;
  $("#wz-folder").value = "";
  $("#wz-scanList").innerHTML = "";
  $("#wz-scanWrap").hidden = true;
  $("#wz-nameCard").hidden = true;
  $("#wz-name").value = "";
}

function openAddGame() {
  resetWizard();
  switchPage("addgame", navItem("library"));
}

function renderScanList(files) {
  const list = $("#wz-scanList");
  list.innerHTML = "";
  if (!files.length) {
    list.innerHTML = `<div class="empty-note">No .exe, .vbs, .bat or .rar files
      found in that folder.</div>`;
    return;
  }
  files.forEach((f) => {
    const row = document.createElement("div");
    row.className = "scan-row";
    row.innerHTML = `
      <span class="scan-radio"></span>
      <span class="scan-name">${esc(f.name)}</span>
      <span class="scan-path" title="${esc(f.path)}">${esc(f.path)}</span>
      <span class="scan-badge ${f.type === "archive" ? "arc" : "exe"}">
        ${f.type === "archive" ? "ARCHIVE" : "EXE"}</span>
      <span class="scan-path">${fmtSize(f.size)}</span>`;
    row.addEventListener("click", () => selectScannedFile(f, row));
    list.appendChild(row);
  });
}

async function selectScannedFile(f, row) {
  $$("#wz-scanList .scan-row").forEach((r) => r.classList.remove("selected"));
  row.classList.add("selected");
  wzSelection = f;
  if (f.type === "archive") {
    const name = f.name.replace(/\.(rar|zip|7z)$/i, "");
    $("#wz-name").value = name;
    $("#wz-nameCard").hidden = false;
    toast("Archive selected — it will be extracted when you add it");
  } else {
    $("#wz-name").value = f.name.replace(/\.(exe|vbs|bat)$/i, "");
    $("#wz-nameCard").hidden = false;
  }
}

async function scanFolder() {
  const path = $("#wz-folder").value.trim();
  if (!path) { toast("Enter or pick a folder first"); return; }
  const res = await api("/api/scan", { path });
  if (!res.ok) { toast(res.error || "Could not read that folder"); return; }
  $("#wz-scanWrap").hidden = false;
  renderScanList(res.files || []);
  toast(`Found ${(res.files || []).length} file(s)`);
}

async function addScannedGame() {
  if (!wzSelection) { toast("Pick a file first"); return; }
  const name = $("#wz-name").value.trim();
  if (!name) { toast("Give the game a name"); return; }
  let executable = wzSelection.path;
  let mainPath = wzSelection.dir;

  if (wzSelection.type === "archive") {
    toast("Extracting archive…");
    const ex = await api("/api/extract", { archive: wzSelection.path, name });
    if (!ex.ok) { toast(ex.error || "Extraction failed"); return; }
    const exe = (ex.files || []).find((f) => f.type === "executable");
    if (!exe) {
      toast("No executable found inside the archive");
      return;
    }
    executable = exe.path;
    mainPath = exe.dir;
    $("#wz-folder").value = ex.dest;
  }

  const res = await api("/api/add-game",
    { name, executable, mainPath });
  if (!res.ok) { toast(res.error || "Could not add the game"); return; }
  const fix = res.fix || {};
  toast(fix.found ? `${name} added · OnlineFix detected`
                  : `${name} added to your library`);
  resetWizard();
  await refreshGames(true);
  switchPage("library", navItem("library"));
}

$("#wz-browse").addEventListener("click", async () => {
  const res = await api("/api/pick-folder", { path: $("#wz-folder").value.trim() });
  if (res.ok) $("#wz-folder").value = res.path;
  else toast(res.error || "Folder picker unavailable — type the path instead");
});
$("#wz-scanBtn").addEventListener("click", scanFolder);
$("#wz-addBtn").addEventListener("click", addScannedGame);
$("#wzBack").addEventListener("click", () => {
  resetWizard();
  switchPage("library", navItem("library"));
});
$("#wz-folder").addEventListener("keydown", (e) => {
  if (e.key === "Enter") scanFolder();
});

/* ── GAME SETTINGS page ────────────────────────────────────────────────── */
function envToText(env) {
  return Object.entries(env || {}).map(([k, v]) => `${k}=${v}`).join("\n");
}

function textToEnv(text) {
  const out = {};
  String(text || "").split("\n").forEach((line) => {
    const t = line.trim();
    if (!t || t.startsWith("#")) return;
    const idx = t.indexOf("=");
    if (idx <= 0) return;
    out[t.slice(0, idx).trim()] = t.slice(idx + 1).trim();
  });
  return out;
}

function setSwitch(el, on) { el.classList.toggle("on", !!on); }

function renderFixState(g) {
  const overrides = (g.overrides || "").split(";").map((s) => s.trim()).filter(Boolean);
  const state = $("#gs-fixState");
  const detail = $("#gs-fixDetail");
  if (g.fixPath) state.textContent = "OnlineFix detected";
  else if (overrides.length) state.textContent = "DLL overrides active";
  else state.textContent = "No OnlineFix files found";

  const lines = [];
  if (g.fixPath) lines.push(`Fix folder: ${g.fixPath}`);
  if (overrides.length) lines.push(`Overrides: ${overrides.join("  ")}`);
  if (g.steamID) lines.push(`Steam app ${g.steamID}`);
  lines.push(g.steamOverlay
    ? `Spacewar ${g.fakeSteamID || "480"} registered by the Steam overlay`
    : "Steam overlay off — no Spacewar session");
  if (g.fakeSteamActive) lines.push("fake steam DLLs active");
  detail.textContent = lines.join(" · ");

  const fake = $("#gs-fakeSteam");
  setSwitch(fake, g.fakeSteamActive);
  fake.classList.toggle("disabled", !g.hasSteamfix);
  fake.title = g.hasSteamfix ? "" : "this fix ships no steamfix32/64.dll to swap";
}

async function openGameSettings(name) {
  const g = await api("/api/game", { name });
  if (!g || !g.name) { toast("Game not found"); return; }
  currentGame = g;
  $("#gsTitle").textContent = `${g.name} — Settings`;
  $("#gs-name").value = g.name || "";
  $("#gs-executable").value = g.executable || "";
  $("#gs-mainPath").value = g.mainPath || "";
  $("#gs-prefixPath").value = g.prefixPath || "";
  $("#gs-argsBefore").value = g.argsBefore || "";
  $("#gs-argsAfter").value = g.argsAfter || "";
  $("#gs-overrides").value = g.overrides || "";
  $("#gs-env").value = envToText(g.environment);
  $("#gs-fakeSteamID").value = g.fakeSteamID || "";
  setSwitch($("#gs-wined3d"), g.wined3d);
  setSwitch($("#gs-nativeWayland"), g.nativeWayland);
  setSwitch($("#gs-steamOverlay"), g.steamOverlay);
  setSwitch($("#gs-steamRuntime"), g.steamRuntime);
  renderFixState(g);

  const banner = $("#gs-bannerPreview");
  banner.src = g.banner ? artUrl(g.banner, "banner") : "";
  banner.style.visibility = g.banner ? "visible" : "hidden";
  const icon = $("#gs-iconPreview");
  icon.src = g.icon ? artUrl(g.icon, "icon") : "";
  icon.style.visibility = g.icon ? "visible" : "hidden";

  const pl = await api("/api/protons");
  const sel = $("#gs-proton");
  sel.innerHTML = "";
  const values = ["GE-Proton Latest", ...(pl.installed || [])];
  if (g.proton && !values.includes(g.proton)) values.push(g.proton);
  values.forEach((v) => {
    const o = document.createElement("option");
    o.value = v;
    o.textContent = v;
    if (v === g.proton) o.selected = true;
    sel.appendChild(o);
  });
  if (!g.proton) sel.value = "GE-Proton Latest";

  switchPage("gamesettings", navItem("library"));
}

async function saveGameSettings() {
  if (!currentGame) return;
  const data = {
    executable: $("#gs-executable").value.trim(),
    mainPath: $("#gs-mainPath").value.trim(),
    prefixPath: $("#gs-prefixPath").value.trim(),
    proton: $("#gs-proton").value,
    argsBefore: $("#gs-argsBefore").value.trim(),
    argsAfter: $("#gs-argsAfter").value.trim(),
    overrides: $("#gs-overrides").value.trim(),
    fakeSteamID: $("#gs-fakeSteamID").value.trim(),
    environment: textToEnv($("#gs-env").value),
    steamOverlay: $("#gs-steamOverlay").classList.contains("on"),
    steamRuntime: $("#gs-steamRuntime").classList.contains("on"),
    wined3d: $("#gs-wined3d").classList.contains("on"),
    nativeWayland: $("#gs-nativeWayland").classList.contains("on"),
  };
  const newName = $("#gs-name").value.trim();
  const res = await api("/api/game-save", {
    name: currentGame.name, data,
    newName: newName && newName !== currentGame.name ? newName : null,
  });
  if (!res.ok) { toast(res.error || "Could not save"); return; }
  toast("Settings saved");
  currentGame.name = res.name || currentGame.name;
  await refreshGames(true);
  switchPage("library", navItem("library"));
}

function readFileAsDataURL(file) {
  return new Promise((resolve, reject) => {
    const fr = new FileReader();
    fr.onload = () => resolve(fr.result);
    fr.onerror = () => reject(new Error("could not read the file"));
    fr.readAsDataURL(file);
  });
}

async function uploadArt(kind, input) {
  const file = input.files && input.files[0];
  if (!file || !currentGame) return;
  try {
    const data = await readFileAsDataURL(file);
    const res = await api("/api/game-art",
      { name: currentGame.name, kind, image: data });
    if (!res.ok) { toast(res.error || "Upload failed"); return; }
    toast(kind === "banner" ? "Banner updated" : "Icon updated");
    input.value = "";
    await refreshGames(true);
    openGameSettings(currentGame.name);
  } catch (err) {
    toast(String(err.message || err));
  }
}

$("#gs-saveBtn").addEventListener("click", saveGameSettings);
$("#gs-cancelBtn").addEventListener("click", () => {
  switchPage("library", navItem("library"));
});
$("#gsBack").addEventListener("click", () => {
  switchPage("library", navItem("library"));
});
$("#gs-bannerFile").addEventListener("change", (e) => uploadArt("banner", e.target));
$("#gs-iconFile").addEventListener("change", (e) => uploadArt("icon", e.target));
$("#gs-shortcutBtn").addEventListener("click", async () => {
  if (!currentGame) return;
  const res = await api("/api/shortcut", { name: currentGame.name });
  toast(res.ok ? "Shortcut created" : (res.error || "Could not create shortcut"));
});
$("#gs-folderBtn").addEventListener("click", async () => {
  if (!currentGame) return;
  const path = currentGame.mainPath || currentGame.executable;
  if (!path) { toast("No folder set"); return; }
  await api("/api/open", { kind: "path", target: path });
});
$("#gs-removeBtn").addEventListener("click", async () => {
  if (!currentGame) return;
  if (!confirm(`Remove “${currentGame.name}” from your library?`)) return;
  const res = await api("/api/game-remove", { name: currentGame.name });
  if (!res.ok) { toast(res.error || "Could not remove"); return; }
  toast("Game removed");
  currentGame = null;
  await refreshGames(true);
  switchPage("library", navItem("library"));
});
$$("#page-gamesettings .switch:not(#gs-fakeSteam)").forEach((sw) => {
  sw.addEventListener("click", () => sw.classList.toggle("on"));
});

/* OnlineFix card */
$("#gs-fixDetect").addEventListener("click", async () => {
  if (!currentGame) return;
  toast("Scanning the game folder for OnlineFix files…");
  const res = await api("/api/game-fix", { name: currentGame.name });
  if (!res.ok) { toast(res.error || "Detection failed"); return; }
  toast(res.found ? "OnlineFix files applied" : "No OnlineFix files found");
  await refreshGames(true);
  openGameSettings(currentGame.name);
});

$("#gs-fakeSteam").addEventListener("click", async () => {
  if (!currentGame) return;
  const el = $("#gs-fakeSteam");
  if (el.classList.contains("disabled")) {
    toast("This fix ships no steamfix DLLs to swap");
    return;
  }
  const enabled = !el.classList.contains("on");
  const res = await api("/api/game-fake-steam",
    { name: currentGame.name, enabled });
  if (!res.ok) { toast(res.error || "Could not switch"); return; }
  setSwitch(el, res.fakeSteamActive);
  toast(res.fakeSteamActive
    ? "Fake Steam enabled — the fix boots as Spacewar"
    : "Real steamfix DLLs restored");
});

/* ── RUNNERS page ──────────────────────────────────────────────────────── */
async function loadProtons() {
  const res = await api("/api/protons");
  const installed = res.installed || [];
  const list = $("#runnerList");
  if (!installed.length) {
    list.innerHTML = `<div class="empty-note">No Proton versions installed yet.
      Download the latest GE-Proton to run Windows games.</div>`;
    return;
  }
  const def = launcherCfg ? launcherCfg.defaultProton : "";
  list.innerHTML = installed.map((p) => `
    <div class="runner-row">
      <div>
        <div class="runner-name">${esc(p)}</div>
        <div class="runner-sub">${p === "GE-Proton Latest" ? "Always resolves to the newest build"
          : "Installed runner"}</div>
      </div>
      <div style="display:flex;gap:8px;align-items:center">
        ${p === res.latestName ? `<span class="scan-badge exe tag-latest">LATEST</span>` : ""}
        ${def === p ? `<span class="scan-badge tag-default">DEFAULT</span>` : ""}
      </div>
    </div>`).join("");
}

async function downloadLatestProton() {
  const latest = await api("/api/protons/latest");
  if (!latest.ok) { toast(latest.error || "Could not find a release"); return; }
  toast(`Downloading ${latest.name}…`);
  await downloadProton(latest.name, latest.url, latest.size);
}

async function downloadProton(name, url, size) {
  const res = await api("/api/protons/download", { name, url, size: size || 0 });
  if (!res.ok) { toast(res.error || "Download failed"); return; }
  $("#runnerProgress").hidden = false;
  $("#runnerTitle").textContent = `Downloading ${name}`;
  $("#runnerStatus").textContent = "0%";
  $("#runnerBar").classList.add("pulsing");
  $("#runnerBar").querySelector(".bar").style.width = "0%";
  $("#runnerAddBtn").disabled = true;
  $("#runnerVersionsBtn").disabled = true;
  startProtonPolling();
}

/* list every published GE-Proton release so a specific one can be picked */
async function toggleProtonVersions() {
  const card = $("#runnerVersions");
  if (!card.hidden) { card.hidden = true; return; }
  card.hidden = false;
  await loadProtonVersions();
}

async function loadProtonVersions() {
  const list = $("#runnerVersionsList");
  list.innerHTML = `<div class="empty-note">Loading releases…</div>`;
  const res = await api("/api/protons/releases");
  if (!res.ok) {
    list.innerHTML = `<div class="empty-note">${esc(res.error || "Could not load the release list")}</div>`;
    return;
  }
  const releases = res.releases || [];
  if (!releases.length) {
    list.innerHTML = `<div class="empty-note">No releases found.</div>`;
    return;
  }
  list.innerHTML = releases.map((r) => `
    <div class="set-row">
      <div>
        <div class="set-title">${esc(r.name)}</div>
        <div class="set-sub">${esc(r.filename || "")}${r.size ? " · " + fmtSize(r.size) : ""}</div>
      </div>
      <div style="display:flex;gap:8px;align-items:center">
        ${r.name === res.latest ? `<span class="scan-badge exe tag-latest">LATEST</span>` : ""}
        ${r.installed
          ? `<span class="scan-badge tag-default">INSTALLED</span>`
          : `<button class="btn btn-ghost" data-proton-name="${esc(r.name)}" data-proton-url="${esc(r.url)}" data-proton-size="${r.size || 0}">Download</button>`}
      </div>
    </div>`).join("");
  list.querySelectorAll("[data-proton-url]").forEach((btn) => {
    btn.addEventListener("click", () => {
      toast(`Downloading ${btn.dataset.protonName}…`);
      downloadProton(btn.dataset.protonName, btn.dataset.protonUrl,
                     Number(btn.dataset.protonSize || 0));
    });
  });
}

function startProtonPolling() {
  clearInterval(protonPoll);
  protonPoll = setInterval(async () => {
    const p = await api("/api/protons/progress");
    const bar = $("#runnerBar");
    const fill = bar.querySelector(".bar");
    if (p.extracting) {
      $("#runnerTitle").textContent = "Extracting…";
      $("#runnerStatus").textContent = "unpacking the archive";
      bar.classList.add("pulsing");
    } else {
      const pct = Math.round((p.fraction || 0) * 100);
      bar.classList.remove("pulsing");
      fill.style.width = `${pct}%`;
      $("#runnerTitle").textContent = p.name ? `Downloading ${p.name}` : "Downloading…";
      $("#runnerStatus").textContent = `${pct}% · ${fmtSize(p.bytes)}` +
        (p.total ? ` / ${fmtSize(p.total)}` : "");
    }
    if (!p.busy) {
      clearInterval(protonPoll);
      $("#runnerAddBtn").disabled = false;
      $("#runnerVersionsBtn").disabled = false;
      if (p.error) {
        $("#runnerProgress").hidden = true;
        toast(p.error);
      } else {
        $("#runnerProgress").hidden = true;
        toast("Runner installed ✔");
        loadProtons();
        if (!$("#runnerVersions").hidden) loadProtonVersions();
      }
    }
  }, 600);
}

$("#runnerAddBtn").addEventListener("click", downloadLatestProton);
$("#runnerVersionsBtn").addEventListener("click", toggleProtonVersions);
$("#runnerCancelBtn").addEventListener("click", async () => {
  await api("/api/protons/cancel", {});
  clearInterval(protonPoll);
  $("#runnerProgress").hidden = true;
  $("#runnerAddBtn").disabled = false;
  $("#runnerVersionsBtn").disabled = false;
  toast("Download cancelled");
});

/* ── SETTINGS page ─────────────────────────────────────────────────────── */
async function renderSettings() {
  const s = await api("/api/launcher");
  launcherCfg = s;
  const body = $("#settingsBody");
  const protons = s.protons || [];
  const protonOptions = ["", ...protons];
  if (s.defaultProton && !protonOptions.includes(s.defaultProton)) {
    protonOptions.push(s.defaultProton);
  }

  body.innerHTML = `
    <div class="form-card">
      <h3>Folders</h3>
      <div class="hint">Where installs, runners and wine prefixes live.</div>
      ${folderRow("installsPath", "Games folder", s.installsPath)}
      ${folderRow("protonsPath", "Proton versions", s.protonsPath)}
      ${folderRow("prefixesPath", "Wine prefixes", s.prefixesPath)}
    </div>

    <div class="form-card">
      <h3>Defaults</h3>
      <div class="hint">Used when adding new games.</div>
      <div class="field">
        <label>Default runner</label>
        <select id="set-runner">
          <option value="proton"${s.defaultRunner === "proton" ? " selected" : ""}>Proton</option>
          <option value="wine"${s.defaultRunner === "wine" ? " selected" : ""}>Wine</option>
        </select>
      </div>
      <div class="field">
        <label>Default Proton</label>
        <select id="set-proton">
          ${protonOptions.map((p) => `<option value="${esc(p)}"${p === s.defaultProton ? " selected" : ""}>${p || "(newest installed)"}</option>`).join("")}
        </select>
      </div>
      <div class="field">
        <label>Default fix</label>
        <select id="set-fix">
          ${[["onlinefix", "OnlineFix"], ["freetp", "FreeTP"], ["custom", "Custom"], ["none", "No fix"]]
            .map(([v, l]) => `<option value="${v}"${s.defaultFixType === v ? " selected" : ""}>${l}</option>`).join("")}
        </select>
      </div>
    </div>

    <div class="form-card">
      <h3>Behaviour</h3>
      <div class="hint">How games are started.</div>
      <div class="switch ${s.fullscreen ? "on" : ""}" data-set="fullscreen">
        <span class="switch-label">Start games fullscreen</span>
        <span class="switch-track"><span class="switch-thumb"></span></span>
      </div>
      <br>
      <div class="switch ${s.noSteamRequest ? "on" : ""}" data-set="noSteamRequest">
        <span class="switch-label">Skip the “is Steam running?” check</span>
        <span class="switch-track"><span class="switch-thumb"></span></span>
      </div>
      <br>
      <div class="switch ${s.gamesUsesWined3d ? "on" : ""}" data-set="gamesUsesWined3d">
        <span class="switch-label">Use WineD3D</span>
        <span class="switch-track"><span class="switch-thumb"></span></span>
      </div>
      <br>
      <div class="switch ${s.gamesUsesWayland ? "on" : ""}" data-set="gamesUsesWayland">
        <span class="switch-label">Native Wayland</span>
        <span class="switch-track"><span class="switch-thumb"></span></span>
      </div>
    </div>

    <div class="form-card">
      <h3>About</h3>
      <div class="hint">OnlineFix Linux Launcher · v${esc(s.version || "2.7.1")}</div>
      <div class="field">
        <label>Configuration folder</label>
        <input type="text" id="set-config" value="${esc(s.configDir || "")}" readonly>
      </div>
      <div class="btn-row">
        <button class="btn btn-ghost" id="set-open-config">Open folder</button>
        <button class="btn btn-ghost" id="set-open-classic">Open classic desktop UI</button>
      </div>
    </div>`;

  // switches save immediately
  body.querySelectorAll(".switch[data-set]").forEach((sw) => {
    sw.addEventListener("click", async () => {
      sw.classList.toggle("on");
      const res = await api("/api/launcher-set",
        { key: sw.dataset.set, value: sw.classList.contains("on") });
      if (!res.ok) { toast(res.error || "Could not save"); return; }
      toast("Saved");
    });
  });

  // selects
  [["#set-runner", "defaultRunner"], ["#set-proton", "defaultProton"],
   ["#set-fix", "defaultFixType"]].forEach(([sel, key]) => {
    const el = $(sel);
    if (!el) return;
    el.addEventListener("change", async () => {
      const res = await api("/api/launcher-set", { key, value: el.value });
      toast(res.ok ? "Saved" : (res.error || "Could not save"));
    });
  });

  // folder pickers
  body.querySelectorAll("[data-folder]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const key = btn.dataset.folder;
      const res = await api("/api/pick-folder", { path: s[key] });
      if (!res.ok) { toast(res.error || "Folder picker unavailable"); return; }
      const saved = await api("/api/launcher-set", { key, value: res.path });
      if (!saved.ok) { toast(saved.error || "Could not save"); return; }
      toast("Folder updated");
      renderSettings();
    });
  });

  $("#set-open-config").addEventListener("click", async () => {
    const st = await api("/api/state");
    if (st.configDir) await api("/api/open", { kind: "path", target: st.configDir });
  });
  $("#set-open-classic").addEventListener("click", async () => {
    const res = await api("/api/open-settings", {});
    toast(res.ok ? "Classic UI opened"
                 : (res.error || "Classic UI unavailable (install tk)"));
  });
}

function folderRow(key, label, value) {
  return `
    <div class="set-row">
      <div>
        <div class="set-title">${label}</div>
        <div class="set-sub" title="${esc(value || "")}">${esc(value || "—")}</div>
      </div>
      <button class="btn btn-ghost" data-folder="${key}">Change</button>
    </div>`;
}

/* ── polling: state + games ────────────────────────────────────────────── */
async function refreshState() {
  try {
    const st = await api("/api/state");
    const wasRunning = runningName;
    runningName = st.running || null;
    launchStatus = st.status || null;
    if (st.mode === "pywebview") $("#winControls").hidden = false;
    updatePlayButton();
    $$("#offers .card, #libraryGrid .card").forEach((c) => {
      const isRunning = c.dataset.name === runningName;
      c.classList.toggle("running", isRunning);
      const badge = c.querySelector(".card-badge");
      if (badge) badge.textContent = isRunning ? "RUNNING" : "INSTALLED";
    });
    if (wasRunning && !runningName && st.lastError) {
      toast(st.lastError);
    }
  } catch (_) { /* backend gone */ }
}

let lastGameSig = "";
async function refreshGames(silent) {
  try {
    const games = await api("/api/games");
    // signature catches renames, new artwork and play-time changes too
    const sig = JSON.stringify(games.map((g) =>
      [g.name, g.banner, g.icon, g.proton, g.timeSpent, g.running]));
    if (sig === lastGameSig) return;
    const changed = lastGameSig !== "";
    lastGameSig = sig;
    realGames = games;
    renderAll();
    if (changed && !silent) toast("Library updated ✔");
  } catch (_) { /* ignore */ }
}

/* ── window controls (pywebview frameless) ─────────────────────────────── */
$("#winControls").addEventListener("click", (e) => {
  const btn = e.target.closest("[data-win]");
  if (!btn) return;
  api("/api/window", { action: btn.dataset.win });
});

/* ── misc buttons ──────────────────────────────────────────────────────── */
$("#cartBtn").addEventListener("click", () => {
  api("/api/open", { kind: "url", target: "https://online-fix.me" });
});
$("#learnMore").addEventListener("click", () => toast("Every game you add shows up here"));
$("#addBtnStore").addEventListener("click", openAddGame);

$$(".thumb").forEach((t) =>
  t.addEventListener("click", () => toast("Screenshot viewer is coming soon")));

$("#addBtn").addEventListener("click", openAddGame);
$("#addBtn2").addEventListener("click", openAddGame);

$$("[data-url]").forEach((b) => b.addEventListener("click", () => {
  api("/api/open", { kind: "url", target: b.dataset.url });
}));

/* ── boot ──────────────────────────────────────────────────────────────── */
(async function boot() {
  initNav();
  try {
    const st = await api("/api/state");
    if (st.mode === "pywebview") $("#winControls").hidden = false;
  } catch (_) {}

  await refreshGames(true);
  setInterval(refreshState, 2500);
  setInterval(() => refreshGames(false), 5000);
})();
