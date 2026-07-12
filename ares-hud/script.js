/**
 * Ares HUD — Core Script (Performance Edition)
 *
 * Refresh tiers:
 *   Critical (CPU / RAM / GPU / Network) → every 2 s
 *   Disk                                 → every 30 s  (backend caches)
 *   Weather                              → every 10 min (backend caches)
 *
 * DOM writes are guarded by change-detection (oldVal !== newVal).
 * Visual updates are batched inside requestAnimationFrame so they never
 * block the main thread between fetch cycles.
 * Defensive programming applied: All DOM queries check for null.
 */

// ─── Constants ────────────────────────────────────────────────────────────────
const CIRCUMFERENCE = 2 * Math.PI * 40;
const API_URL       = 'http://localhost:5001/api/data';

// ─── State (previous values for change-detection) ────────────────────────────
const _prev = {
    cpu: null, ram: null, gpu: null,
    diskPct: null, diskFree: null, diskUsed: null, diskTotal: null,
    weatherCity: null, weatherTemp: null, weatherIcon: null,
    weatherCond: null, weatherHumidity: null, weatherWind: null,
};

// ─── Color Interpolation (pure function, no DOM) ──────────────────────────────
function colorFor(pct) {
    const p = Math.max(0, Math.min(100, pct));
    const r = p < 50 ? Math.floor((p / 50) * 255) : 255;
    const g = p < 50 ? 255 : Math.floor(255 - ((p - 50) / 50) * 255);
    return `rgb(${r}, ${g}, 0)`;
}

// ─── DOM helpers (write only if value changed) ────────────────────────────────
function setText(id, value, prevKey) {
    if (_prev[prevKey] === value) return;
    _prev[prevKey] = value;
    const el = document.getElementById(id);
    if (el) el.textContent = value;
}

function setCircle(circleEl, pct, prevKey) {
    if (!circleEl) return;
    const rounded = Math.round(pct);
    if (_prev[prevKey] === rounded) return;
    _prev[prevKey] = rounded;
    const arc   = (pct / 100) * CIRCUMFERENCE;
    const color = colorFor(pct);
    circleEl.style.strokeDasharray = `${arc} ${CIRCUMFERENCE}`;
    circleEl.style.stroke          = color;
    circleEl.style.filter          = `drop-shadow(0 0 4px ${color})`;
}

// ─── Hardware update (batched in rAF) ─────────────────────────────────────────
function applyHardware(data) {
    requestAnimationFrame(() => {
        // CPU
        setCircle(document.querySelector('#cpu-stat .fg'), data.cpu, 'cpu');
        setText('cpu-value', `${Math.round(data.cpu)}%`, 'cpuText'); // value span

        // RAM
        setCircle(document.querySelector('#ram-stat .fg'), data.ram, 'ram');
        setText('ram-value', `${Math.round(data.ram)}%`, 'ramText');

        // GPU
        const gpuCircle  = document.querySelector('#gpu-stat .fg');
        const gpuValueEl = document.getElementById('gpu-value');
        if (data.gpu !== null && data.gpu !== undefined) {
            setCircle(gpuCircle, data.gpu, 'gpu');
            const gpuRounded = `${Math.round(data.gpu)}%`;
            if (_prev.gpuText !== gpuRounded) {
                _prev.gpuText = gpuRounded;
                if (gpuValueEl) gpuValueEl.textContent = gpuRounded;
            }
        } else {
            if (_prev.gpu !== 'nd') {
                _prev.gpu = 'nd';
                if (gpuCircle) {
                    gpuCircle.style.strokeDasharray = `0 ${CIRCUMFERENCE}`;
                    gpuCircle.style.stroke          = 'rgba(255,26,26,0.3)';
                    gpuCircle.style.filter          = 'none';
                }
                if (gpuValueEl) gpuValueEl.textContent = 'N/D';
            }
        }

        // Disk (value may be unchanged — change-detection handles it)
        if (_prev.diskPct !== Math.round(data.disk.percent)) {
            _prev.diskPct = Math.round(data.disk.percent);
            const diskColor = colorFor(data.disk.percent);
            const diskBar   = document.getElementById('disk-bar');
            if (diskBar) {
                diskBar.style.width           = `${data.disk.percent}%`;
                diskBar.style.backgroundColor = diskColor;
                diskBar.style.boxShadow       = `0 0 10px ${diskColor}`;
            }
        }
        setText('disk-free',  data.disk.free,  'diskFree');
        setText('disk-total', data.disk.total, 'diskTotal');
        setText('disk-used',  data.disk.used,  'diskUsed');
    });
}

// ─── Weather update (batched in rAF) ──────────────────────────────────────────
function applyWeather(data) {
    requestAnimationFrame(() => {
        setText('weather-city',     data.city,      'weatherCity');
        setText('weather-temp',     data.temp === 'N/D' ? 'N/D' : `${data.temp}°C`, 'weatherTemp');
        setText('weather-icon',     data.icon,      'weatherIcon');
        setText('weather-cond',     data.condition, 'weatherCond');
        setText('weather-humidity', data.humidity  === 'N/D' ? 'N/D' : `${data.humidity}%`,   'weatherHumidity');
        setText('weather-wind',     data.windSpeed === 'N/D' ? 'N/D' : `${data.windSpeed} km/h`, 'weatherWind');
    });
}

// ─── Network canvas ───────────────────────────────────────────────────────────
const _netData = {
    'canvas-download': new Array(50).fill(0),
    'canvas-upload':   new Array(50).fill(0),
};

function initCanvas(id) {
    const canvas = document.getElementById(id);
    if (!canvas) return; // Defensive check
    
    const ctx = canvas.getContext('2d');

    const resize = () => {
        if (!canvas.parentElement) return;
        canvas.width  = canvas.parentElement.clientWidth;
        canvas.height = canvas.parentElement.clientHeight - 20;
    };
    window.addEventListener('resize', resize);
    resize();

    const draw = () => {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        const pts = _netData[id];
        const w   = canvas.width / (pts.length - 1);
        const h   = canvas.height;
        // Pre-compute colors once per frame
        const colors = pts.map(v => colorFor(100 - v));

        for (let i = 0; i < pts.length - 1; i++) {
            const x0 = i * w,       x1 = (i + 1) * w;
            const y0 = h - (pts[i] / 100) * h;
            const y1 = h - (pts[i + 1] / 100) * h;
            const toAlpha = c => c.replace('rgb', 'rgba').replace(')', ', 0.2)');

            const lineG = ctx.createLinearGradient(x0, 0, x1, 0);
            lineG.addColorStop(0, colors[i]);
            lineG.addColorStop(1, colors[i + 1]);

            const fillG = ctx.createLinearGradient(x0, 0, x1, 0);
            fillG.addColorStop(0, toAlpha(colors[i]));
            fillG.addColorStop(1, toAlpha(colors[i + 1]));

            ctx.beginPath();
            ctx.moveTo(x0, h); ctx.lineTo(x0, y0);
            ctx.lineTo(x1, y1); ctx.lineTo(x1, h);
            ctx.closePath();
            ctx.fillStyle = fillG; ctx.fill();

            ctx.beginPath();
            ctx.moveTo(x0, y0); ctx.lineTo(x1, y1);
            ctx.strokeStyle = lineG; ctx.lineWidth = 1.5; ctx.stroke();
        }
        requestAnimationFrame(draw);
    };
    draw();
}

function pushNet(id, value) {
    if (!_netData[id]) return;
    _netData[id].shift();
    _netData[id].push(value);
    const labelId = id === 'canvas-download' ? 'net-dl-speed' : 'net-up-speed';
    const labelEl = document.getElementById(labelId);
    if (labelEl) labelEl.textContent = (value / 10).toFixed(1);
}

// ─── Timeline & Clock ─────────────────────────────────────────────────────────
function renderTimeline() {
    const ruler = document.getElementById('top-ruler');
    if (!ruler) return;
    ruler.innerHTML = '';
    const today = new Date().getDate();
    for (let i = 1; i <= 30; i++) {
        const tick = document.createElement('div');
        tick.className = 'ruler-tick';
        if (i === today) tick.classList.add('active');
        tick.textContent = i.toString().padStart(2, '0');
        ruler.appendChild(tick);
    }
}

function startClock() {
    const elTime = document.getElementById('time-display');
    const elDate = document.getElementById('date-display');
    if (!elTime || !elDate) return;
    
    const tick   = () => {
        const now = new Date();
        const t   = now.toLocaleTimeString('it-IT', { hour12: false });
        const d   = now.toLocaleDateString('it-IT', { year: 'numeric', month: 'long', day: 'numeric' }).toUpperCase();
        if (elTime.textContent !== t) elTime.textContent = t;
        if (elDate.textContent !== d) elDate.textContent = d;
    };
    setInterval(tick, 1000);
    tick();
}

// ─── Drag & Resize dei widget (tieni premuto 3s per sbloccare) ────────────────
const GRID        = 20;   // px di griglia per lo snap di posizione e dimensione
const MIN_W       = 200;  // larghezza minima di un widget
const MIN_H       = 100;  // altezza minima di un widget
const HOLD_MS     = 3000; // durata della pressione per sbloccare
const MOVE_TOLERANCE = 6; // px di tolleranza: oltre, la pressione lunga viene annullata
const STORAGE_KEY = 'ares-widget-layout-v2';

// Posizioni/dimensioni di partenza, calcolate dinamicamente in base allo
// spazio realmente disponibile in .hud-main, così i riquadri riempiono
// sempre perfettamente lo schermo (qualunque sia la risoluzione).
function computeDefaultLayout() {
    const container = document.querySelector('.hud-main');
    const gap  = 20;   // spaziatura verticale tra i widget di una colonna
    const colW = 280;  // larghezza colonne, invariata

    const rect   = container ? container.getBoundingClientRect() : { width: window.innerWidth, height: window.innerHeight - 110 };
    const availW = rect.width;
    const availH = rect.height - gap; // margine anche in fondo, simmetrico a quello in cima

    const leftX  = 0;
    const rightX = availW - colW;

    // Colonna sinistra: STATO SISTEMA sopra, ARCHIVIAZIONE sotto.
    // ANALISI EMAIL sta di fianco a STATO SISTEMA, alla sua destra, stessa altezza.
    const cpuRamH = Math.round(availH * 0.62);
    const diskH   = availH - cpuRamH - gap;
    const emailX  = leftX + colW + gap;

    // Colonna destra: METEO sopra, FLUSSO DI RETE sotto.
    // UTILIZZO API sta di fianco al meteo, alla sua sinistra, stessa altezza.
    // networkH lascia RESET_BTN_CLEARANCE px liberi in fondo, così non tocca
    // mai il pulsante "RESET LAYOUT" ancorato in basso a destra dello schermo.
    const RESET_BTN_CLEARANCE = 50;
    const weatherH = Math.round(availH * 0.38);
    const networkH = availH - weatherH - gap - RESET_BTN_CLEARANCE;
    const apiUsageX = rightX - colW - gap;

    const clockW = 280;

    // Riquadro chat: in basso al centro, tra le due colonne
    const chatW = Math.min(600, availW - (colW * 2) - (gap * 2));
    const chatH = 150;

    return {
        'module-cpu-ram': { x: leftX,  y: 0,               w: colW,  h: cpuRamH },
        'module-disk':    { x: leftX,  y: cpuRamH + gap,    w: colW,  h: diskH },
        'module-clock':   { x: Math.round(availW / 2 - clockW / 2), y: 0, w: clockW, h: 110 },
        'module-weather': { x: rightX, y: 0,                w: colW,  h: weatherH },
        'module-network': { x: rightX, y: weatherH + gap,   w: colW,  h: networkH },
        'module-api-usage': { x: apiUsageX, y: 0, w: colW, h: weatherH },
        'module-app-control': { x: apiUsageX, y: weatherH + gap, w: colW, h: networkH },
        'module-email':     { x: emailX, y: 0, w: colW, h: cpuRamH },
        'module-chat':    { x: Math.round(availW / 2 - chatW / 2), y: availH - chatH, w: chatW, h: chatH },
    };
}

function snapToGrid(v) { return Math.round(v / GRID) * GRID; }

function loadSavedLayout() {
    try {
        return JSON.parse(localStorage.getItem(STORAGE_KEY)) || {};
    } catch {
        return {};
    }
}

function saveWidgetLayout(widget) {
    const layout = loadSavedLayout();
    layout[widget.id] = {
        x: parseFloat(widget.dataset.x) || 0,
        y: parseFloat(widget.dataset.y) || 0,
        w: widget.offsetWidth,
        h: widget.offsetHeight,
    };
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(layout)); } catch { /* storage pieno o non disponibile: ignora */ }
}

function applyLayout() {
    const saved    = loadSavedLayout();
    const defaults = computeDefaultLayout();
    document.querySelectorAll('.widget').forEach(widget => {
        const pos = saved[widget.id] || defaults[widget.id] || { x: 20, y: 20, w: 280, h: 200 };
        widget.dataset.x = pos.x;
        widget.dataset.y = pos.y;
        widget.style.width  = `${pos.w}px`;
        widget.style.height = `${pos.h}px`;
        widget.style.transform = `translate(${pos.x}px, ${pos.y}px)`;
    });
}

function anyWidgetUnlocked() {
    return !!document.querySelector('.widget.drag-unlocked');
}

function setEditBannerVisible(visible) {
    const banner = document.getElementById('edit-mode-banner');
    if (banner) banner.classList.toggle('visible', visible);
}

function lockAllWidgets() {
    document.querySelectorAll('.widget.drag-unlocked').forEach(w => w.classList.remove('drag-unlocked'));
    setEditBannerVisible(false);
}

function unlockWidget(widget) {
    widget.classList.add('drag-unlocked');
    setEditBannerVisible(true);
}

function initWidgetDragResize() {
    document.querySelectorAll('.widget').forEach(widget => {
        // ── Maniglia di ridimensionamento (creata dinamicamente, angolo in basso a destra) ──
        const resizeHandle = document.createElement('div');
        resizeHandle.className = 'resize-handle';
        widget.appendChild(resizeHandle);

        // ── Pressione lunga (3s) per sbloccare il widget ──
        let holdTimer  = null;
        let holdStartX = 0;
        let holdStartY = 0;

        const clearHold = () => { if (holdTimer) { clearTimeout(holdTimer); holdTimer = null; } };

        widget.addEventListener('pointerdown', (e) => {
            if (widget.classList.contains('drag-unlocked')) return; // già sbloccato: gestito sotto
            if (e.target === resizeHandle) return;

            holdStartX = e.clientX;
            holdStartY = e.clientY;
            holdTimer = setTimeout(() => {
                holdTimer = null;
                unlockWidget(widget);
            }, HOLD_MS);
        });

        const cancelHoldIfMoved = (e) => {
            if (!holdTimer) return;
            if (Math.abs(e.clientX - holdStartX) > MOVE_TOLERANCE || Math.abs(e.clientY - holdStartY) > MOVE_TOLERANCE) {
                clearHold();
            }
        };
        widget.addEventListener('pointermove',  cancelHoldIfMoved);
        widget.addEventListener('pointerup',    clearHold);
        widget.addEventListener('pointerleave', clearHold);

        // ── Trascinamento (sposta), attivo solo da sbloccato ──
        widget.addEventListener('pointerdown', (e) => {
            if (!widget.classList.contains('drag-unlocked')) return;
            if (e.target === resizeHandle) return; // il resize ha la sua gestione dedicata

            e.preventDefault();
            widget.classList.add('dragging');
            widget.setPointerCapture(e.pointerId);

            const origX = parseFloat(widget.dataset.x) || 0;
            const origY = parseFloat(widget.dataset.y) || 0;
            const startPX = e.clientX;
            const startPY = e.clientY;

            const onMove = (ev) => {
                const x = snapToGrid(origX + (ev.clientX - startPX));
                const y = snapToGrid(origY + (ev.clientY - startPY));
                widget.dataset.x = x;
                widget.dataset.y = y;
                widget.style.transform = `translate(${x}px, ${y}px)`;
            };
            const onUp = () => {
                widget.classList.remove('dragging');
                widget.removeEventListener('pointermove', onMove);
                widget.removeEventListener('pointerup', onUp);
                saveWidgetLayout(widget);
            };
            widget.addEventListener('pointermove', onMove);
            widget.addEventListener('pointerup', onUp, { once: true });
        });

        // ── Ridimensionamento tramite la maniglia, attivo solo da sbloccato ──
        resizeHandle.addEventListener('pointerdown', (e) => {
            if (!widget.classList.contains('drag-unlocked')) return;

            e.preventDefault();
            e.stopPropagation();
            widget.classList.add('resizing');
            resizeHandle.setPointerCapture(e.pointerId);

            const startW  = widget.offsetWidth;
            const startH  = widget.offsetHeight;
            const startPX = e.clientX;
            const startPY = e.clientY;

            const onMove = (ev) => {
                const w = Math.max(MIN_W, snapToGrid(startW + (ev.clientX - startPX)));
                const h = Math.max(MIN_H, snapToGrid(startH + (ev.clientY - startPY)));
                widget.style.width  = `${w}px`;
                widget.style.height = `${h}px`;
            };
            const onUp = () => {
                widget.classList.remove('resizing');
                resizeHandle.removeEventListener('pointermove', onMove);
                resizeHandle.removeEventListener('pointerup', onUp);
                saveWidgetLayout(widget);
            };
            resizeHandle.addEventListener('pointermove', onMove);
            resizeHandle.addEventListener('pointerup', onUp, { once: true });
        });
    });

    // Un click fuori da qualsiasi widget blocca tutto (esce dalla modalità modifica)
    document.addEventListener('pointerdown', (e) => {
        if (!anyWidgetUnlocked()) return;
        if (e.target.closest('.widget')) return;
        lockAllWidgets();
    });

    const resetBtn = document.getElementById('btn-reset-layout');
    if (resetBtn) {
        resetBtn.addEventListener('click', () => {
            localStorage.removeItem(STORAGE_KEY);
            applyLayout();
        });
    }
}

// ─── Fetch loop (tiered) ──────────────────────────────────────────────────────
async function fetchData() {
    try {
        const res  = await fetch(API_URL);
        if (!res.ok) throw new Error(res.status);
        const json = await res.json();

        applyHardware(json.hardware);
        applyWeather(json.weather);          // no-ops if nothing changed

        // Network canvas (simulated, critical tier)
        const dl = Math.random() > 0.8 ? 50 + Math.random() * 50 : Math.random() * 20;
        const ul = Math.random() > 0.9 ? 40 + Math.random() * 40 : Math.random() * 10;
        pushNet('canvas-download', dl);
        pushNet('canvas-upload',   ul);
    } catch (e) {
        console.error('Fetch error:', e);
    }
}

// ─── Chat / Comandi ───────────────────────────────────────────────────────────
function appendChatMessage(role, text) {
    const log = document.getElementById('chat-log');
    if (!log) return;
    const msg = document.createElement('div');
    msg.className = `chat-msg chat-${role}`;
    msg.textContent = text;
    log.appendChild(msg);
    log.scrollTop = log.scrollHeight;
}

function initChat() {
    const form  = document.getElementById('chat-form');
    const input = document.getElementById('chat-input');
    if (!form || !input) return;

    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const message = input.value.trim();
        if (!message) return;

        appendChatMessage('user', message);
        input.value = '';
        input.disabled = true;

        try {
            const res = await fetch('http://localhost:5001/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message }),
            });
            const data = await res.json();

            appendChatMessage('ares', data.reply || 'Errore: nessuna risposta dal server.');

            if (data.weather) {
                applyWeather(data.weather);
            }

            if (data.audio) {
                const audio = new Audio(`data:audio/mpeg;base64,${data.audio}`);
                audio.play().catch(err => console.error('Errore riproduzione audio:', err));
            }
        } catch (err) {
            console.error('Errore chat:', err);
            appendChatMessage('ares', 'Errore di connessione al server Ares.');
        } finally {
            input.disabled = false;
            input.focus();
        }
    });
}

// ─── Sfondo: grafo di nodi animato (stessa palette rosso/oro di Ares) ────────
function initNetworkBackground() {
    const canvas = document.getElementById('bg-network');
    if (!canvas) return; // Defensive check
    const ctx = canvas.getContext('2d');

    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    const COLOR_NODE = '255, 26, 26';  // --primary
    const COLOR_HUB  = '255, 204, 0';  // --secondary, riservato ai nodi "hub" più grandi
    const MAX_DIST   = 150;            // oltre questa distanza due nodi non si collegano
    const HUB_RATIO  = 0.15;           // quota di nodi "hub"

    let nodes  = [];
    let width  = 0;
    let height = 0;
    const dpr  = Math.min(window.devicePixelRatio || 1, 2);

    function countFor(w, h) {
        return Math.max(45, Math.min(95, Math.round((w * h) / 13000)));
    }

    function makeNodes() {
        const count = countFor(width, height);
        nodes = Array.from({ length: count }, () => {
            const isHub = Math.random() < HUB_RATIO;
            return {
                x:  Math.random() * width,
                y:  Math.random() * height,
                vx: (Math.random() - 0.5) * 0.25,
                vy: (Math.random() - 0.5) * 0.25,
                r:  isHub ? 2.5 + Math.random() * 2 : 1 + Math.random() * 1.5,
                hub: isHub,
            };
        });
    }

    function resize() {
        const parent = canvas.parentElement;
        width  = (parent ? parent.clientWidth  : window.innerWidth)  || window.innerWidth;
        height = (parent ? parent.clientHeight : window.innerHeight) || window.innerHeight;
        canvas.width  = width  * dpr;
        canvas.height = height * dpr;
        canvas.style.width  = `${width}px`;
        canvas.style.height = `${height}px`;
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        makeNodes();
        if (reduceMotion) draw(); // ridisegna il singolo frame statico dopo un resize
    }

    function step() {
        for (const n of nodes) {
            n.x += n.vx;
            n.y += n.vy;
            if (n.x < 0 || n.x > width)  n.vx *= -1;
            if (n.y < 0 || n.y > height) n.vy *= -1;
            n.x = Math.max(0, Math.min(width,  n.x));
            n.y = Math.max(0, Math.min(height, n.y));
        }
    }

    function draw() {
        ctx.clearRect(0, 0, width, height);

        // Collegamenti tra nodi vicini
        for (let i = 0; i < nodes.length; i++) {
            for (let j = i + 1; j < nodes.length; j++) {
                const dx = nodes[i].x - nodes[j].x;
                const dy = nodes[i].y - nodes[j].y;
                const dist = Math.sqrt(dx * dx + dy * dy);
                if (dist >= MAX_DIST) continue;
                const alpha = (1 - dist / MAX_DIST) * 0.35;
                ctx.strokeStyle = `rgba(${COLOR_NODE}, ${alpha})`;
                ctx.lineWidth = 1;
                ctx.beginPath();
                ctx.moveTo(nodes[i].x, nodes[i].y);
                ctx.lineTo(nodes[j].x, nodes[j].y);
                ctx.stroke();
            }
        }

        // Nodi (i "hub" sono più grandi, dorati e con un bagliore più intenso)
        for (const n of nodes) {
            const color = n.hub ? COLOR_HUB : COLOR_NODE;
            ctx.beginPath();
            ctx.arc(n.x, n.y, n.r, 0, Math.PI * 2);
            ctx.fillStyle   = `rgba(${color}, ${n.hub ? 0.9 : 0.6})`;
            ctx.shadowColor = `rgba(${color}, 0.8)`;
            ctx.shadowBlur  = n.hub ? 8 : 3;
            ctx.fill();
        }
        ctx.shadowBlur = 0;
    }

    function frame() {
        step();
        draw();
        requestAnimationFrame(frame);
    }

    window.addEventListener('resize', resize);
    resize();

    // Rispetta la preferenza di sistema "riduci animazioni": in tal caso un
    // solo frame statico, senza loop di animazione continuo.
    if (reduceMotion) {
        draw();
    } else {
        frame();
    }
}

// ─── Utilizzo API (widget interattivo) ────────────────────────────────────────
let _apiUsageExpandedRow = null; // nome del provider con dettaglio aperto, se presente

function relativeTime(isoString) {
    if (!isoString) return 'mai usato';
    const diffMs = Date.now() - new Date(isoString).getTime();
    const diffMin = Math.floor(diffMs / 60000);
    if (diffMin < 1)  return 'proprio ora';
    if (diffMin < 60) return `${diffMin} min fa`;
    const diffH = Math.floor(diffMin / 60);
    if (diffH < 24) return `${diffH} ${diffH === 1 ? 'ora' : 'ore'} fa`;
    const diffD = Math.floor(diffH / 24);
    return `${diffD} ${diffD === 1 ? 'giorno' : 'giorni'} fa`;
}

function renderApiUsage(providers) {
    const list = document.getElementById('api-usage-list');
    if (!list) return;

    if (!providers || !providers.length) {
        list.innerHTML = '<div class="api-usage-empty">Nessun provider configurato</div>';
        return;
    }

    list.innerHTML = '';
    providers.forEach(p => {
        const row = document.createElement('div');
        row.className = 'api-usage-row';
        if (!p.enabled || !p.has_key) row.classList.add('disabled');
        if (_apiUsageExpandedRow === p.name) row.classList.add('expanded');

        let dotClass = 'idle';
        if (p.last_status === 'success') dotClass = 'ok';
        else if (p.last_status === 'error') dotClass = 'err';

        const countLabel = p.calls_total > 0
            ? `${p.calls_success}/${p.calls_total} · ${p.tokens_total} tok`
            : (p.has_key ? 'mai usato' : 'nessuna chiave');

        const main = document.createElement('div');
        main.className = 'api-usage-row-main';
        main.innerHTML = `
            <span class="api-usage-dot ${dotClass}"></span>
            <span class="api-usage-label">${p.label}</span>
            <span class="api-usage-count">${countLabel}</span>
            <span class="api-usage-toggle ${p.enabled ? 'on' : ''}" data-provider="${p.name}">
                <span class="api-usage-toggle-knob"></span>
            </span>
        `;
        row.appendChild(main);

        const detail = document.createElement('div');
        detail.className = 'api-usage-detail';
        const lastUsedLine = `Ultimo utilizzo: ${relativeTime(p.last_used)}`;
        const errorLine = p.last_error ? `<div class="err-line">Ultimo errore: ${p.last_error}</div>` : '';
        detail.innerHTML = `<div>${lastUsedLine}</div>${errorLine}`;
        row.appendChild(detail);

        // Click sulla riga (fuori dall'interruttore) espande/comprime il dettaglio
        row.addEventListener('click', (e) => {
            if (e.target.closest('.api-usage-toggle')) return;
            _apiUsageExpandedRow = (_apiUsageExpandedRow === p.name) ? null : p.name;
            renderApiUsage(providers);
        });

        // Click sull'interruttore attiva/disattiva il provider
        const toggleEl = main.querySelector('.api-usage-toggle');
        toggleEl.addEventListener('click', async (e) => {
            e.stopPropagation();
            const newEnabled = !p.enabled;
            toggleEl.classList.toggle('on', newEnabled); // feedback ottimistico immediato
            try {
                const res = await fetch('http://localhost:5001/api/llm_usage/toggle', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name: p.name, enabled: newEnabled }),
                });
                const data = await res.json();
                if (data.status === 'success' && data.providers) {
                    renderApiUsage(data.providers);
                }
            } catch (err) {
                console.error('Errore toggle provider:', err);
                toggleEl.classList.toggle('on', p.enabled); // ripristina in caso di errore
            }
        });

        list.appendChild(row);
    });
}

async function fetchApiUsage() {
    try {
        const res = await fetch('http://localhost:5001/api/llm_usage');
        if (!res.ok) throw new Error(res.status);
        const data = await res.json();
        renderApiUsage(data.providers);
    } catch (e) {
        console.error('Errore fetch utilizzo API:', e);
    }
}

// ─── Analisi Email (widget interattivo) ─────────────────────────────────────
let _emailExpandedRow = null; // indice della email con dettaglio aperto, se presente

function extractSenderName(sender) {
    if (!sender) return '(mittente sconosciuto)';
    const beforeBracket = sender.split('<')[0].trim();
    return beforeBracket || sender;
}

function renderEmailList(cache) {
    const list = document.getElementById('email-list');
    if (!list) return;

    const status = cache ? cache.status : null;

    if (status === 'not_configured' || !status) {
        list.innerHTML = '<div class="email-empty">Analisi email non configurata.<br>Compila email_config.json con le tue credenziali IMAP.</div>';
        return;
    }
    if (status === 'error') {
        list.innerHTML = `<div class="email-empty">Errore nel controllare la posta:<br>${cache.error || 'motivo sconosciuto'}</div>`;
        return;
    }
    if (status === 'empty') {
        list.innerHTML = '<div class="email-empty">Nessuna email nella casella.</div>';
        return;
    }

    const emails = cache.emails || [];
    if (!emails.length) {
        list.innerHTML = '<div class="email-empty">Nessuna email da mostrare.</div>';
        return;
    }

    list.innerHTML = '';
    emails.forEach((e, idx) => {
        const row = document.createElement('div');
        row.className = 'email-row';
        if (_emailExpandedRow === idx) row.classList.add('expanded');

        const urgencyClass = `urgenza-${e.urgency || 'media'}`;

        const main = document.createElement('div');
        main.className = 'email-row-main';
        main.innerHTML = `
            <span class="email-dot ${urgencyClass}"></span>
            <span class="email-sender">${extractSenderName(e.sender)}</span>
            <span class="email-time">${relativeTime(e.date)}</span>
        `;
        row.appendChild(main);

        const summary = document.createElement('div');
        summary.className = 'email-summary';
        summary.textContent = e.summary || '';
        row.appendChild(summary);

        const detail = document.createElement('div');
        detail.className = 'email-detail';
        const keyInfoLine = e.key_info ? `<div class="key-info-line">${e.key_info}</div>` : '';
        detail.innerHTML = `<div class="subject-line">${e.subject || '(nessun oggetto)'}</div>${keyInfoLine}`;
        row.appendChild(detail);

        row.addEventListener('click', () => {
            _emailExpandedRow = (_emailExpandedRow === idx) ? null : idx;
            renderEmailList(cache);
        });

        list.appendChild(row);
    });
}

async function fetchEmailSummary() {
    try {
        const res = await fetch('http://localhost:5001/api/email_summary');
        if (!res.ok) throw new Error(res.status);
        const data = await res.json();
        renderEmailList(data);
    } catch (e) {
        console.error('Errore fetch analisi email:', e);
    }
}

function initEmailRefreshButton() {
    const btn = document.getElementById('email-refresh-btn');
    if (!btn) return;

    btn.addEventListener('click', async () => {
        if (btn.classList.contains('spinning')) return; // aggiornamento già in corso
        btn.classList.add('spinning');
        try {
            const res = await fetch('http://localhost:5001/api/email_summary/refresh', { method: 'POST' });
            const data = await res.json();
            renderEmailList(data);
        } catch (e) {
            console.error('Errore aggiornamento email:', e);
        } finally {
            btn.classList.remove('spinning');
        }
    });
}

// ─── Controllo App (widget interattivo: pulsanti diretti) ──────────────────
function initAppControl() {
    const buttons = document.querySelectorAll('.app-control-btn');
    const statusEl = document.getElementById('app-control-status');
    if (!buttons.length) return;

    let statusTimer = null;
    function showStatus(text, isError) {
        if (!statusEl) return;
        statusEl.textContent = text;
        statusEl.classList.toggle('error', !!isError);
        statusEl.classList.toggle('success', !isError);
        if (statusTimer) clearTimeout(statusTimer);
        statusTimer = setTimeout(() => { statusEl.textContent = ''; statusEl.classList.remove('error', 'success'); }, 3500);
    }

    buttons.forEach(btn => {
        btn.addEventListener('click', async () => {
            const app = btn.dataset.app;
            const action = btn.dataset.action;
            btn.disabled = true;
            try {
                const res = await fetch('http://localhost:5001/api/app_control', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ app, action }),
                });
                const data = await res.json();
                showStatus(data.message || (data.status === 'success' ? 'Fatto.' : 'Errore.'), data.status !== 'success');
            } catch (e) {
                console.error('Errore controllo app:', e);
                showStatus('Errore di connessione ad Ares.', true);
            } finally {
                btn.disabled = false;
            }
        });
    });
}

// ─── Bootstrap ────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    renderTimeline();
    startClock();
    initCanvas('canvas-download');
    initCanvas('canvas-upload');
    initNetworkBackground();

    applyLayout();
    initWidgetDragResize();
    initChat();

    const cityEl = document.getElementById('weather-city');
    if (cityEl) {
        cityEl.style.cursor = 'pointer';
        cityEl.title = 'Clicca per cambiare città';

        function promptCityCustom() {
            return new Promise((resolve) => {
                const modal = document.getElementById('city-modal');
                const input = document.getElementById('city-input');
                const btnSubmit = document.getElementById('city-submit');
                const btnCancel = document.getElementById('city-cancel');
                
                if (!modal || !input || !btnSubmit || !btnCancel) {
                    resolve(prompt('Inserisci il nome della nuova città:'));
                    return;
                }

                input.value = '';
                modal.classList.remove('hidden');
                input.focus();

                const cleanup = () => {
                    modal.classList.add('hidden');
                    btnSubmit.removeEventListener('click', onSubmit);
                    btnCancel.removeEventListener('click', onCancel);
                    input.removeEventListener('keydown', onKeydown);
                };

                const onSubmit = () => { cleanup(); resolve(input.value); };
                const onCancel = () => { cleanup(); resolve(null); };
                const onKeydown = (e) => {
                    if (e.key === 'Enter') onSubmit();
                    if (e.key === 'Escape') onCancel();
                };

                btnSubmit.addEventListener('click', onSubmit);
                btnCancel.addEventListener('click', onCancel);
                input.addEventListener('keydown', onKeydown);
            });
        }

        cityEl.addEventListener('click', async () => {
            const newCity = await promptCityCustom();
            if (newCity && newCity.trim()) {
                try {
                    const res = await fetch('http://localhost:5001/api/update_city', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ city: newCity.trim() })
                    });
                    
                    const data = await res.json();
                    if (res.ok && data.status === 'success' && data.weather) {
                        applyWeather(data.weather);
                    } else {
                        alert(`ERRORE ARES: ${data.message || 'Città non trovata'}`);
                    }
                } catch (e) {
                    console.error('Errore aggiornamento città:', e);
                    alert('ERRORE ARES: Errore di connessione al server radar');
                }
            }
        });
    }

    setInterval(fetchData, 2000);
    fetchData();

    setInterval(fetchApiUsage, 5000);
    fetchApiUsage();

    initEmailRefreshButton();
    setInterval(fetchEmailSummary, 30000);
    fetchEmailSummary();

    initAppControl();
});
