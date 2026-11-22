# OnlineFix Linux Launcher (Python port)

A Python port of the DevelNext/JPHP **OnlineFix Linux Launcher** (v2.7.1).
It keeps the original feature set, configuration files and window sizes.

## 🎨 New web UI (default)

The launcher now opens in a **frameless native window** driven by a local
HTTP server + WebKit (via `pywebview`), with a design cloned from the
reference mockup:

* **Font** — [Outfit](https://fonts.google.com/specimen/Outfit) (bundled, offline)
* **Colors** — `#141415` · `#df040a` · `#ff6b27` · `#ffffff`
* Featured-game **hero carousel** with tag chips and an info card
  (price + *Available now*), crossfades, ken-burns and auto-advance
* **Special offers** grid — the reference catalog, with your own games
  added in front as soon as they exist
* Every control drives the project's own `Games.ini` / `Launcher.ini`:

  | Page | What it does |
  | --- | --- |
  | **Game store** | Hero carousel + offers grid, play/stop and game settings for your games |
  | **Library** | Everything in `Games.ini`, empty state, add-a-game entry |
  | **Add a Game** | Native folder picker (zenity/kdialog), folder scan for `.exe`/`.vbs`/`.bat`, `.rar`/`.zip`/`.7z` extraction, name it and add |
  | **Game settings** | Name/rename, executable, folders, Proton version, launch arguments, DLL overrides, environment variables (`KEY=value` lines), WineD3D/Wayland/Steam-overlay switches, fake AppID, banner/icon upload, desktop & menu shortcut, open folder, remove |
  | **Runners** | Installed GE-Proton builds, mark latest, download the newest release with live progress and cancel |
  | **Settings** | Folders (games/Protons/prefixes), default runner/Proton/fix, behaviour switches, config folder, classic-UI escape hatch |
  | **Help** | SteamDB / ProtonDB / Proton GE links |

* Live search, launch/stop, page transitions, staggered entrance
  animations, hover lifts and glows everywhere
* Works even on machines without Tk (the classic UI needs `tk`)

Run modes:

```sh
./onlinefix-linux-launcher                # new web UI (pywebview window)
./onlinefix-linux-launcher --tk           # classic Tk UI
./onlinefix-linux-launcher --add-game     # just the add-game wizard
./onlinefix-linux-launcher --game-settings "Game Name"
./onlinefix-linux-launcher "Game Name"    # launch a game directly
```

If `pywebview`/WebKit is unavailable, the UI opens in a Chrome
`--app` window instead.

## Running

```sh
./onlinefix-linux-launcher                 # open the game library
./onlinefix-linux-launcher "Game Name"     # launch a game directly (desktop shortcut)
```

Requirements: Python 3.10+ with Tk 8.6, Pillow and `vdf`:

```sh
pip install -r requirements.txt
```

Optional external tools used by individual features: `7z`, `unrar`, `ffmpeg`,
`icoextract`, `winetricks`, Steam and GE-Proton.

## What is included

- Game library with banner/icon cards, slide-out detail panel and time tracking
- Add-game wizard: binary scan, filters, FreeTP/RAR installers, icon/banner lookup
- Per-game settings: Proton version, Wine overrides, environment variables,
  graphics options, Steam ID, launch arguments, banners/icons, prefixes
- Launch/stop with Proton + Steam Runtime, debug logging, log viewer/saver
- Proton download manager (GitHub releases, aria2c/wget/curl fallback)
- Desktop and application-menu shortcuts, Wine utilities, SteamDB/ProtonDB links
- Launcher settings (paths, protons, graphics, launcher, about), English/Russian UI

## Files and compatibility

- Games: `~/.config/OFME-Linux/Games.ini`
- Launcher: `~/.config/OFME-Linux/Launcher.ini`
- Banners/icons: `~/.config/OFME-Linux/{banners,icons}/`
- Proton downloads: `~/Downloads/protons/` (configurable)
- Prefixes: `~/.local/share/OnlineFix Linux Launcher/prefixes/`
- Single-instance PID file: `/tmp/ofllpid`

Environment variables are stored as `KEY====value` entries joined by backslashes,
as in the original application. Both the older two-backslash and current
four-backslash separators are read.

## Layout

```
main.py                  entry point (styles, PID guard, startup modes)
app/
  core.py                Application, forms registry, Proton/update workers
  main_form.py etc.      UI forms (one module per original form)
  files_worker.py        process generation, Proton/Steam lookup, shortcuts
  fix_parser.py          DLL overrides, banner/icon extraction, FreeTP patches
  rar_extractor.py       RAR listing/extraction with password fallback
  ftp_installer.py       silent FreeTP installer via Proton
  storage.py             Games.ini / Launcher.ini wrapper
  i18n.py                en/ru translations from locale/
  theme.py, widgets.py   dark theme and reusable Tk widgets
webui/
  index.html             sidebar, hero, offers, library, wizard, settings
  css/styles.css         cloned design tokens, layout and animations
  js/app.js              catalog, carousel, grids, wizard, all API calls
  assets/                Outfit font, Steam logo, game artwork
app/
  webbridge.py           headless backend: games, launch, settings, runners
  webserver.py           static server + JSON API + window controls
  webapp.py              pywebview window, single instance, browser fallback
assets/, locale/         copied from the original project's src/.data and src/locale
```


## Install

One line — no clone needed:

```bash
curl -fsSL https://raw.githubusercontent.com/nizar2004/onlinefix-project/main/install.sh | bash
```

This installs the launcher to `~/.local/share/onlinefix-launcher`, adds an
`onlinefix-launcher` command, a menu entry and the application icon.

Uninstall:

```bash
curl -fsSL https://raw.githubusercontent.com/nizar2004/onlinefix-project/main/uninstall.sh | bash
```

Your games and settings (`~/.config/OFME-Linux`) are always kept.

### From a clone

```bash
./install.sh              # user install (default)
sudo ./install.sh --system
./uninstall.sh
```

### Requirements

* Python 3 with Tkinter (`python3-tk`)
* Wine / Proton for running games
