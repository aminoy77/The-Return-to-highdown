"""
server.py — MUD Multiplayer
============================
- TCP puerto 4000 → terminal (client.py)
- WS puerto 4001 → chat en navegador
- HTTP puerto 8080 → sirve chat.html
Uso:
  pip install websockets aiohttp
  python3 server.py
Jugar: python3 client.py <IP>
Chat UI: http://<IP>:8080/
"""

import asyncio
import hashlib
import json
import os
import random
from copy import deepcopy
from enum import Enum
from aiohttp import web
import aiohttp

# ────────────────────────────────────────────────────────────────
#  HTML DE LA INTERFAZ WEB — debe estar ANTES de cualquier uso
# ────────────────────────────────────────────────────────────────

def get_html() -> str:
    """Devuelve el HTML completo de la interfaz web"""
    return r"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>MUD — The Return to Highdown</title>
<style>
*{margin:0;padding:0;box-sizing:border-box;}
:root{
  --bg:#0a0a0a;--bg2:#111;--bg3:#181818;--border:#252525;
  --gold:#c9a84c;--gold2:#e8c55c;--green:#4caf50;--red:#e53935;
  --red2:#ff1744;--blue:#42a5f5;--mana:#5c6bc0;--purple:#ab47bc;
  --orange:#ff9800;--text:#ccc;--dim:#555;--dim2:#222;
}
body{background:var(--bg);color:var(--text);font-family:'Courier New',monospace;height:100vh;overflow:hidden;display:flex;flex-direction:column;}
/* ... (el resto del CSS y HTML que ya tenías, lo mantengo abreviado aquí por longitud) ... */
</style>
</head>
<body>
<!-- Aquí iría todo el contenido del body, login, topbar, views, scripts, etc. -->
<!-- Mantengo solo el esqueleto para que quepa; pega tu HTML completo aquí -->
</body>
</html>"""

# ────────────────────────────────────────────────────────────────
#  CONFIGURACIÓN GENERAL
# ────────────────────────────────────────────────────────────────

SAVES_DIR = "saves"
os.makedirs(SAVES_DIR, exist_ok=True)

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
USAR_SUPABASE = bool(SUPABASE_URL and SUPABASE_KEY)
TABLA = "mud_saves"

def _sb_headers():
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }

async def _sb_get(usuario: str) -> dict | None:
    """Lee una fila de Supabase. Devuelve el dict o None si no existe."""
    if not USAR_SUPABASE:
        return None
    url = f"{SUPABASE_URL}/rest/v1/{TABLA}?usuario=eq.{usuario}&select=*"
    async with aiohttp.ClientSession() as s:
        async with s.get(url, headers=_sb_headers()) as r:
            if r.status == 200:
                rows = await r.json()
                return rows[0] if rows else None
    return None

async def _sb_upsert(row: dict):
    """Inserta o actualiza una fila en Supabase."""
    if not USAR_SUPABASE:
        return
    url = f"{SUPABASE_URL}/rest/v1/{TABLA}"
    headers = {**_sb_headers(), "Prefer": "resolution=merge-duplicates,return=minimal"}
    async with aiohttp.ClientSession() as s:
        await s.post(url, headers=headers, json=row)

# ============================================================
# CLASES
# ============================================================
CLASES = {
    "guerrero": {
        "vidaMax": 90, "danioBase": 40, "manaMax": 30, "manaTurno": 10,
        "danioEspecial": 70, "ataquesTurno": 1, "costoEspecial": 30,
        "habilidad": "golpe_tanque"
    },
    "mago": {
        "vidaMax": 50, "danioBase": 30, "manaMax": 70, "manaTurno": 20,
        "danioEspecial": 60, "ataquesTurno": 1, "costoEspecial": 60,
        "habilidad": "magia_antigua"
    },
    "arquero": {
        "vidaMax": 40, "danioBase": 10, "manaMax": 40, "manaTurno": 15,
        "danioEspecial": 10, "ataquesTurno": [1, 4], "costoEspecial": 40,
        "habilidad": "flecha_ignea", "danioEfecto": 10, "duracionEfecto": 2
    },
    "curandero": {
        "vidaMax": 50, "danioBase": 20, "manaMax": 50, "manaTurno": 20,
        "danioEspecial": 20, "ataquesTurno": 1, "costoEspecial": 30,
        "habilidad": "absorcion", "curacionEspecial": 20
    },
    "nigromante": {
        "vidaMax": 50, "danioBase": 10, "manaMax": 80, "manaTurno": 20,
        "danioEspecial": 60, "ataquesTurno": [1, 5], "costoEspecial": 60,
        "habilidad": "maldicion_tiempo"
    },
    "hechicero": {
        "vidaMax": 50, "danioBase": 30, "manaMax": 70, "manaTurno": 30,
        "danioEspecial": 70, "ataquesTurno": 1, "costoEspecial": 70,
        "habilidad": "invocar_esqueleto"
    },
    "caballero": {
        "vidaMax": 70, "danioBase": 50, "manaMax": 40, "manaTurno": 10,
        "danioEspecial": 60, "ataquesTurno": 1, "costoEspecial": 40,
        "habilidad": "embestida"
    },
    "cazador": {
        "vidaMax": 60, "danioBase": 50, "manaMax": 30, "manaTurno": 10,
        "danioEspecial": 30, "ataquesTurno": 1, "costoEspecial": 30,
        "habilidad": "inmovilizar"
    },
    "asesino": {
        "vidaMax": 50, "danioBase": 20, "manaMax": 20, "manaTurno": 10,
        "danioEspecial": 60, "ataquesTurno": [1, 3], "costoEspecial": 20,
        "habilidad": "muerte_garantizada"
    },
    "barbaro": {
        "vidaMax": 60, "danioBase": 50, "manaMax": 30, "manaTurno": 5,
        "danioEspecial": 70, "ataquesTurno": 1, "costoEspecial": 30,
        "habilidad": "abocajarro"
    },
}

# ============================================================
# ENEMIGOS
# ============================================================
# ============================================================
ENEMIGOS = {
    # ── Tier Base ──
    "bandido":       {"vidaMax": 60,  "danioBase": 20, "ataquesTurno": 1,      "tier": "Base"},
    "slime":         {"vidaMax": 90,  "danioBase": 5,  "ataquesTurno": 2,      "tier": "Base"},
    "duende":        {"vidaMax": 50,  "danioBase": 15, "ataquesTurno": 2,      "tier": "Base"},
    "esqueleto":     {"vidaMax": 70,  "danioBase": 25, "ataquesTurno": 1,      "tier": "Base"},
    "zombie":        {"vidaMax": 80,  "danioBase": 10, "ataquesTurno": 1,      "tier": "Base"},
    "lobo":          {"vidaMax": 60,  "danioBase": 15, "ataquesTurno": [1, 2], "tier": "Base"},
    "oso":           {"vidaMax": 75,  "danioBase": 35, "ataquesTurno": 1,      "tier": "Base"},
    # ── Tier Especial ──
    "orco":          {"vidaMax": 70,  "danioBase": 30, "ataquesTurno": 1,      "tier": "Especial"},
    "ogro":          {"vidaMax": 90,  "danioBase": 30, "ataquesTurno": 1,      "tier": "Especial"},
    "troll":         {"vidaMax": 100, "danioBase": 35, "ataquesTurno": 1,      "tier": "Especial"},
    "gigante":       {"vidaMax": 110, "danioBase": 45, "ataquesTurno": 1,      "tier": "Especial"},
    "ciclope":       {"vidaMax": 80,  "danioBase": 40, "ataquesTurno": 1,      "tier": "Especial"},
    "hombreLobo":    {"vidaMax": 90,  "danioBase": 30, "ataquesTurno": [1, 3], "tier": "Especial"},
    "quimera":       {"vidaMax": 80,  "danioBase": 20, "ataquesTurno": 1,      "tier": "Especial"},
    "demonioInferior":{"vidaMax": 90, "danioBase": 20, "ataquesTurno": [1, 2], "tier": "Especial"},
    "tiburon":       {"vidaMax": 80,  "danioBase": 30, "ataquesTurno": 1,      "tier": "Especial"},
    # ── Tier Superior ──
    "vampiro":       {"vidaMax": 125, "danioBase": 20, "ataquesTurno": [1, 2], "tier": "Superior"},
    "altoOrco":      {"vidaMax": 150, "danioBase": 50, "ataquesTurno": 1,      "tier": "Superior"},
    "golem":         {"vidaMax": 180, "danioBase": 50, "ataquesTurno": 1,      "tier": "Superior"},
    "elfoOscuro":    {"vidaMax": 150, "danioBase": 60, "ataquesTurno": 1,      "tier": "Superior"},
    "demonioSuperior":{"vidaMax": 150,"danioBase": 60, "ataquesTurno": 1,      "tier": "Superior"},
    # ── Tier Elite ──
    "leviatan":      {"vidaMax": 250, "danioBase": 80, "ataquesTurno": 1,      "tier": "Elite"},
    "reyEsqueleto":  {"vidaMax": 230, "danioBase": 80, "ataquesTurno": 1,      "tier": "Elite"},
    "dragon":        {"vidaMax": 250, "danioBase": 80, "ataquesTurno": 1,      "tier": "Elite"},
    # ── Tier Boss ──
    "reyDemonio":    {"vidaMax": 250, "danioBase": 70, "ataquesTurno": 1,      "tier": "Boss"},
    "kraken":        {"vidaMax": 400, "danioBase": 70, "ataquesTurno": 1,      "tier": "Boss"},
    "alpha":         {"vidaMax": 500, "danioBase": 90, "ataquesTurno": 1,      "tier": "Boss"},
}

XP_POR_TIER = {
    "Base": 10, "Especial": 30, "Superior": 50, "Elite": 100, "Boss": 250
}
XP_POR_NIVEL   = 150
MONEDAS_SUBIDA = 20
SALA_RESPAWN   = 1
TIEMPO_RESPAWN = 5
MAX_JUGADORES  = 5

# ============================================================
# TIENDA
# ============================================================
CATALOGO = {
    "pocion_vida":    {"nombre": "Pocion de Vida",         "emoji": "🧪",
                       "descripcion": "Restaura toda tu vida.",
                       "precio": 30, "usable_combate": True},
    "pocion_danio":   {"nombre": "Pocion de Danio",        "emoji": "⚗️",
                       "descripcion": "+30% dano durante 1 combate.",
                       "precio": 40, "usable_combate": True},
    "gema_teleporte": {"nombre": "Gema de Teletransporte", "emoji": "💎",
                       "descripcion": "Teleporta a cualquier sala.",
                       "precio": 50, "usable_combate": False},
}
ALIAS_ITEMS = {
    "vida":     "pocion_vida",
    "danio":    "pocion_danio",
    "dano":     "pocion_danio",
    "gema":     "gema_teleporte",
    "teleport": "gema_teleporte",
}

# ============================================================
# BIOMAS
# Cada bioma define un pool de enemigos aleatorios.
# Desierto = fácil (Base/Especial)
# Mar      = medio (Especial/Superior)
# Nieve    = difícil (Superior/Elite)
# Los bosses siempre van como encuentros fijos.
# ============================================================
BIOMAS = {
    "desierto": {
        "emoji":       "🏜",
        "descripcion": "Calor abrasador. Arena en todas partes.",
        "enemigos":    ["bandido", "duende", "esqueleto", "zombie", "lobo", "demonioInferior", "quimera"],
    },
    "mar": {
        "emoji":       "🌊",
        "descripcion": "Humedad salada. Se escucha el oleaje.",
        "enemigos":    ["tiburon", "slime", "hombreLobo", "orco", "ogro", "vampiro", "troll"],
    },
    "nieve": {
        "emoji":       "❄️",
        "descripcion": "Frio glacial. El viento corta como un cuchillo.",
        "enemigos":    ["gigante", "ciclope", "golem", "elfoOscuro", "altoOrco", "demonioSuperior", "reyEsqueleto"],
    },
}

# ============================================================
# SALAS
# ============================================================
# Dos sintaxis disponibles:
#
#   A) Enemigos fijos:
#      "encuentros": [("bandido", 2), ("orco", 1)]
#
#   B) Bioma aleatorio:
#      "bioma": "desierto", "cantidad": 2
#      (en cada combate se eligen enemigos aleatorios del pool del bioma)
#
#   Si la sala no tiene ni "encuentros" ni "bioma" → sala segura (sin combate)
# ============================================================
SALAS = {
    # ── DESIERTO (salas 1-5) ──────────────────────────────────
    1:  {"nombre": "Entrada del Desierto",
         "descripcion": "Arena caliente bajo tus pies. El sol abrasa sin piedad.",
         "conexiones": {"norte": 2, "este": 3},
         "bioma": "desierto", "cantidad": 1},

    2:  {"nombre": "Dunas del Norte",
         "descripcion": "Dunas interminables. Algo se mueve entre la arena.",
         "conexiones": {"sur": 1, "norte": 5},
         "bioma": "desierto", "cantidad": 2},

    3:  {"nombre": "Ruinas del Desierto",
         "descripcion": "Columnas rotas a medias enterradas. Silencio inquietante.",
         "conexiones": {"oeste": 1, "norte": 4},
         "bioma": "desierto", "cantidad": 2},

    4:  {"nombre": "Templo Maldito",
         "descripcion": "Un templo cubierto de jeroglificos de sangre.",
         "conexiones": {"sur": 3, "norte": 5},
         "encuentros": [("demonioInferior", 2)]},

    5:  {"nombre": "Trono del Rey Demonio",
         "descripcion": "El trono de huesos del Rey Demonio domina la sala.",
         "conexiones": {"sur": 2, "oeste": 4, "norte": 10},
         "encuentros": [("reyDemonio", 1)]},

    # ── OASIS (sala segura de transicion) ─────────────────────
    6:  {"nombre": "Oasis",
         "descripcion": "Agua fresca y palmeras. Un respiro antes del mar.",
         "conexiones": {"sur": 5, "norte": 10},
         "encuentros": [],
         "tienda": True, "hospital": True},

    # ── MAR (salas 10-14) ────────────────────────────────────
    10: {"nombre": "Costa Tormentosa",
         "descripcion": "Olas furiosas rompen contra las rocas.",
         "conexiones": {"sur": 6, "norte": 11, "este": 12},
         "bioma": "mar", "cantidad": 1},

    11: {"nombre": "Aguas Profundas",
         "descripcion": "El mar se vuelve oscuro e insondable.",
         "conexiones": {"sur": 10, "norte": 14},
         "bioma": "mar", "cantidad": 2},

    12: {"nombre": "Cueva Submarina",
         "descripcion": "Una gruta bajo el mar. Bioluminiscencia en las paredes.",
         "conexiones": {"oeste": 10, "norte": 13},
         "bioma": "mar", "cantidad": 2},

    13: {"nombre": "Naufragio del Leviatán",
         "descripcion": "Restos de un barco gigante. Algo enorme se mueve.",
         "conexiones": {"sur": 12, "norte": 14},
         "encuentros": [("vampiro", 1), ("tiburon", 2)]},

    14: {"nombre": "Abismo del Kraken",
         "descripcion": "El Kraken emerge de las profundidades. Todo tiembla.",
         "conexiones": {"sur": 11, "oeste": 13, "norte": 20},
         "encuentros": [("kraken", 1)]},

    # ── PUERTO (sala segura de transicion) ───────────────────
    15: {"nombre": "Puerto Abandonado",
         "descripcion": "Barcos viejos y redes podridas. Camino a las nieves.",
         "conexiones": {"sur": 14, "norte": 20},
         "encuentros": [],
         "tienda": True, "hospital": True},

    # ── NIEVE (salas 20-24) ──────────────────────────────────
    20: {"nombre": "Tundra Helada",
         "descripcion": "Nieve hasta las rodillas. El viento aulla sin parar.",
         "conexiones": {"sur": 15, "norte": 21, "este": 22},
         "bioma": "nieve", "cantidad": 1},

    21: {"nombre": "Bosque de Hielo",
         "descripcion": "Arboles congelados como estatuas. Todo cruje.",
         "conexiones": {"sur": 20, "norte": 24},
         "bioma": "nieve", "cantidad": 2},

    22: {"nombre": "Fortaleza de Cristal",
         "descripcion": "Una fortaleza construida enteramente de hielo negro.",
         "conexiones": {"oeste": 20, "norte": 23},
         "bioma": "nieve", "cantidad": 2},

    23: {"nombre": "Sala del Trono de Hielo",
         "descripcion": "El trono vacio de un rey muerto. Guardianes aun vigilan.",
         "conexiones": {"sur": 22, "norte": 24},
         "encuentros": [("elfoOscuro", 1), ("golem", 1)]},

    24: {"nombre": "Cumbre del Alpha",
         "descripcion": "La cima del mundo. Alpha aguarda. No hay vuelta atras.",
         "conexiones": {"sur": 21, "oeste": 23},
         "encuentros": [("alpha", 1)]},
}

# ============================================================
# ESTADO GLOBAL
# ============================================================
jugadores_conectados = []
combates_activos = {}
chat_ws_clients = set()
web_sessions = {}  # usuario → websocket (navegadores autenticados)
grupos = {}  # grupo_id → Grupo

# ============================================================
# ESTADO GLOBAL
# ============================================================
jugadores_conectados = []
combates_activos     = {}
chat_ws_clients      = set()
web_sessions         = {}   # usuario → websocket (navegadores autenticados)
grupos               = {}   # grupo_id → Grupo


class Grupo:
    """Grupo de jugadores. El líder es quien lo creó."""
    _id_counter = 0

    def __init__(self, lider: "Player"):
        Grupo._id_counter += 1
        self.id      = Grupo._id_counter
        self.lider   = lider
        self.miembros: list["Player"] = [lider]

    def nombre_lider(self):
        return self.lider.nombre

    def lista_nombres(self):
        return [p.nombre for p in self.miembros]

    def tiene(self, player: "Player"):
        return player in self.miembros

    def quitar(self, player: "Player"):
        if player in self.miembros:
            self.miembros.remove(player)
        # Si se va el líder, el siguiente pasa a ser líder
        if player == self.lider and self.miembros:
            self.lider = self.miembros[0]


class EstadoCombate(Enum):
    ESPERANDO_ACCIONES = "esperando_acciones"
    RESOLVIENDO        = "resolviendo"
    TURNO_ENEMIGO      = "turno_enemigo"
    FINALIZADO         = "finalizado"


class Combate:
    def __init__(self, sala_id, jugadores):
        self.sala_id   = sala_id
        self.jugadores = list(jugadores)
        self.enemigos  = []
        self.estado    = EstadoCombate.ESPERANDO_ACCIONES
        self.acciones  = {}
        self.turno     = 1

    def cargar_enemigos(self, sala_id):
        sala = SALAS.get(sala_id, {})
        self.enemigos = []

        # ── Opción A: bioma aleatorio ──
        if "bioma" in sala:
            bioma_nombre = sala["bioma"]
            cantidad     = sala.get("cantidad", 1)
            pool = BIOMAS.get(bioma_nombre, {}).get("enemigos", [])
            if pool:
                seleccionados = random.choices(pool, k=cantidad)
                for i, tipo in enumerate(seleccionados):
                    base = deepcopy(ENEMIGOS[tipo])
                    self.enemigos.append({
                        "nombre":      f"{tipo.capitalize()} {i+1}",
                        "tipo":        tipo,
                        "vida_actual": base["vidaMax"],
                        **base,
                    })
            return

        # ── Opción B: encuentros fijos ──
        for tipo, cantidad in sala.get("encuentros", []):
            for i in range(cantidad):
                base = deepcopy(ENEMIGOS[tipo])
                self.enemigos.append({
                    "nombre":      f"{tipo.capitalize()} {i+1}",
                    "tipo":        tipo,
                    "vida_actual": base["vidaMax"],
                    **base,
                })

    def enemigos_vivos(self):
        return [e for e in self.enemigos if e["vida_actual"] > 0]

    def jugadores_vivos(self):
        return [p for p in self.jugadores if p.personaje["vidaActual"] > 0]


class Player:
    _id_counter = 0

    def __init__(self, ws):
        Player._id_counter += 1
        self.id          = Player._id_counter
        self.ws          = ws   # aiohttp WebSocketResponse
        self.nombre      = None
        self.personaje   = None
        self.sala_id     = 1
        self.combate     = None
        self.nivel       = 1
        self.xp          = 0
        self.monedas     = 0
        self.muerto      = False
        self.buff_danio  = False
        self.inventario  = {}
        self.usuario     = None
        self.input_queue = asyncio.Queue()
        self.addr        = None
        self.grupo            = None
        self.invitacion_de    = None

    async def send(self, texto: str, tipo: str = "game"):
        try:
            await self.ws.send_json({"type": tipo, "text": texto})
        except Exception:
            pass

    async def send_chat(self, texto: str, scope: str):
        try:
            await self.ws.send_json({"type": "chat", "scope": scope, "text": texto})
        except Exception:
            pass

    async def send_status(self):
        if not self.personaje:
            return
        p = self.personaje
        try:
            await self.ws.send_json({
                "type":          "status",
                "hp":            p["vidaActual"],  "hpMax":   p["vidaMax"],
                "mana":          p["manaActual"],  "manaMax": p["manaMax"],
                "nivel":         self.nivel,       "xp":      self.xp,
                "xpMax":         XP_POR_NIVEL,     "monedas": self.monedas,
                "clase":         p["nombreClase"], "nombre":  self.nombre,
                "sala_id":       self.sala_id,
                "danioBase":     p["danioBase"],
                "ataquesTurno":  p.get("ataquesTurno", 1),
                "costoEspecial": p.get("costoEspecial", 0),
            })
        except Exception:
            pass

    async def recv(self):
        try:
            msg = await asyncio.wait_for(self.input_queue.get(), timeout=300)
            return msg
        except asyncio.TimeoutError:
            return None

    async def send_prompt(self, prompt: str) -> str:
        await self.send(prompt, tipo="prompt")
        while True:
            r = await self.recv()
            if r is None:
                return ""
            if r.strip():
                return r.strip()


# ============================================================
# BROADCAST
# ============================================================

def jugadores_en_sala(sala_id):
    return [p for p in jugadores_conectados if p.sala_id == sala_id]

async def broadcast_sala(sala_id, texto, excluir=None):
    for p in jugadores_conectados:
        if p.sala_id == sala_id and p != excluir:
            await p.send(texto)

async def broadcast_todos(texto):
    for p in jugadores_conectados:
        await p.send(texto)

async def broadcast_chat_ws(scope: str, nombre: str, mensaje: str):
    if not chat_ws_clients:
        return
    payload = {"type": "chat", "scope": scope, "nombre": nombre, "mensaje": mensaje}
    muertos = set()
    for ws in chat_ws_clients:
        try:
            await ws.send_json(payload)
        except Exception:
            muertos.add(ws)
    chat_ws_clients.difference_update(muertos)


async def notify_web_session(player: "Player"):
    ws = web_sessions.get(player.usuario)
    if not ws or not player.personaje:
        return
    p = player.personaje
    try:
        await ws.send_json({
            "type":          "stats",
            "hp":            p["vidaActual"],  "hpMax":   p["vidaMax"],
            "mana":          p["manaActual"],  "manaMax": p["manaMax"],
            "nivel":         player.nivel,     "xp":      player.xp,
            "xpMax":         XP_POR_NIVEL,     "monedas": player.monedas,
            "clase":         p["nombreClase"], "nombre":  player.nombre,
            "sala_id":       player.sala_id,
            "danioBase":     p["danioBase"],
            "ataquesTurno":  p.get("ataquesTurno", 1),
            "costoEspecial": p.get("costoEspecial", 0),
        })
    except Exception:
        web_sessions.pop(player.usuario, None)


async def broadcast_players_to_web():
    """Envía la lista de jugadores conectados a todos los dashboards."""
    if not web_sessions:
        return
    players_data = [
        {
            "nombre":      p.nombre,
            "clase":       p.personaje["nombreClase"],
            "nivel":       p.nivel,
            "sala_id":     p.sala_id,
            "sala_nombre": SALAS.get(p.sala_id, {}).get("nombre", "?"),
            "muerto":      p.muerto,
            "grupo_id":    p.grupo.id    if p.grupo else None,
            "grupo_lider": p.grupo.lider.nombre if p.grupo else None,
        }
        for p in jugadores_conectados if p.nombre and p.personaje
    ]
    payload = {"type": "players", "list": players_data}
    dead = []
    for usuario, ws in list(web_sessions.items()):
        try:
            await ws.send_json(payload)
        except Exception:
            dead.append(usuario)
    for u in dead:
        web_sessions.pop(u, None)


# ============================================================
# CHAT
# ============================================================

async def cmd_chat(player: Player, mensaje: str, sala_solo: bool):
    if not mensaje.strip():
        await player.send("  Que quieres decir?")
        return
    if sala_solo:
        texto = f"  [Sala] {player.nombre}: {mensaje}"
        await broadcast_sala(player.sala_id, texto)
        await broadcast_chat_ws("sala", player.nombre, mensaje)
    else:
        texto = f"  [Global] {player.nombre}: {mensaje}"
        await broadcast_todos(texto)
        await broadcast_chat_ws("global", player.nombre, mensaje)


# ============================================================
# XP Y NIVELES
# ============================================================

def xp_de_tier(tier: str) -> int:
    t = tier.upper()
    if "BOSS" in t:
        return XP_POR_TIER["Boss"]
    for k in XP_POR_TIER:
        if k.upper() in t:
            return XP_POR_TIER[k]
    return XP_POR_TIER["Base"]

def ataques_por_turno(v):
    return random.randint(v[0], v[1]) if isinstance(v, list) else v

def calcular_danio(base):
    return max(1, int(base * random.uniform(0.85, 1.15)))

async def dar_xp(player: Player, cantidad: int):
    player.xp += cantidad
    await player.send(f"  +{cantidad} XP  ({player.xp}/{XP_POR_NIVEL})")
    while player.xp >= XP_POR_NIVEL:
        player.xp      -= XP_POR_NIVEL
        player.nivel   += 1
        player.monedas += MONEDAS_SUBIDA
        p = player.personaje
        p["vidaMax"]   += 10
        p["danioBase"] += 5
        p["manaMax"]   += 5
        p["vidaActual"] = p["vidaMax"]
        await player.send(
            f"\n  ╔══════════════════════════════╗\n"
            f"  ║  SUBISTE AL NIVEL {player.nivel:>2}!        ║\n"
            f"  ║  +{MONEDAS_SUBIDA} monedas  Total:{player.monedas:<5}      ║\n"
            f"  ║  HP:{p['vidaMax']}  Dano:{p['danioBase']}  Mana:{p['manaMax']}   ║\n"
            f"  ╚══════════════════════════════╝"
        )
        await broadcast_todos(f"  {player.nombre} subio al nivel {player.nivel}!")
    await notify_web_session(player)


# ============================================================
# RESPAWN  — FIX: restaura 50% de vida, no 100%
# ============================================================

async def respawn(player: Player):
    player.muerto = True
    await player.send(f"  Has muerto. Reapareces en {TIEMPO_RESPAWN}s...")
    await asyncio.sleep(TIEMPO_RESPAWN)
    p = player.personaje
    p["vidaActual"] = max(1, p["vidaMax"] // 2)   # ← FIX: era p["vidaMax"]
    p["manaActual"] = p["manaMax"]
    player.sala_id  = SALA_RESPAWN
    player.muerto   = False
    await player.send(f"  Reapareces en sala de entrada. HP:{p['vidaActual']}/{p['vidaMax']}")
    await broadcast_sala(SALA_RESPAWN, f"  {player.nombre} reaparece.", excluir=player)
    await notify_web_session(player)
    await describir_sala(player)


# ============================================================
# TIENDA
# ============================================================

async def cmd_tienda(player: Player):
    items = list(CATALOGO.items())
    lineas = [f"\n  TIENDA  ({player.monedas} monedas)\n  " + "-"*30]
    for i, (iid, item) in enumerate(items, 1):
        n = player.inventario.get(iid, 0)
        lineas.append(f"  {i}. {item['emoji']} {item['nombre']} - {item['precio']}  (tienes:{n})")
        lineas.append(f"     {item['descripcion']}")
    lineas.append("\n  Numero para comprar, 0 para salir.")
    await player.send("\n".join(lineas))
    while True:
        r = (await player.send_prompt("  Comprar: ")).strip()
        if r == "0" or r.lower() == "salir":
            await player.send("  Tienda cerrada.")
            return
        if not r.isdigit() or not (1 <= int(r) <= len(items)):
            await player.send(f"  Elige 1-{len(items)} o 0.")
            continue
        iid, item = items[int(r) - 1]
        if player.monedas < item["precio"]:
            await player.send(f"  Sin monedas ({item['precio']} necesarias).")
            continue
        player.monedas -= item["precio"]
        player.inventario[iid] = player.inventario.get(iid, 0) + 1
        await player.send(f"  Compraste {item['emoji']} {item['nombre']}. Quedan {player.monedas}.")


async def cmd_mochila(player: Player):
    items_str = [
        f"  {CATALOGO[k]['emoji']} {CATALOGO[k]['nombre']} x{v}"
        for k, v in player.inventario.items() if v > 0 and k in CATALOGO
    ]
    await player.send("  Mochila vacia." if not items_str else "  MOCHILA:\n" + "\n".join(items_str))


async def usar_item(player: Player, nombre: str, combate=None) -> bool:
    iid = ALIAS_ITEMS.get(nombre.lower(), nombre.lower())
    if iid not in CATALOGO:
        await player.send(f"  Objeto '{nombre}' no existe. (vida / dano / gema)")
        return False
    if player.inventario.get(iid, 0) <= 0:
        await player.send(f"  No tienes {CATALOGO[iid]['nombre']}.")
        return False
    item = CATALOGO[iid]
    if combate and not item["usable_combate"]:
        await player.send("  No usable en combate.")
        return False
    p = player.personaje

    if iid == "pocion_vida":
        curado = p["vidaMax"] - p["vidaActual"]
        p["vidaActual"] = p["vidaMax"]
        player.inventario[iid] -= 1
        msg = f"  {player.nombre} usa Pocion de Vida +{curado} HP! ({p['vidaActual']}/{p['vidaMax']})"
        await broadcast_sala(combate.sala_id if combate else player.sala_id, msg)
        return True

    elif iid == "pocion_danio":
        if player.buff_danio:
            await player.send("  Buff ya activo.")
            return False
        player.buff_danio = True
        player.inventario[iid] -= 1
        msg = f"  {player.nombre} usa Pocion de Danio +30% este combate!"
        await broadcast_sala(combate.sala_id if combate else player.sala_id, msg)
        return True

    elif iid == "gema_teleporte":
        if combate and combate.estado != EstadoCombate.FINALIZADO:
            await player.send("  No usable en combate.")
            return False
        lineas = ["  GEMA - Salas disponibles:"]
        for sid, sala in SALAS.items():
            lineas.append(f"  {sid}. {sala['nombre']}")
        await player.send("\n".join(lineas))
        destino_id = None
        while True:
            d = await player.send_prompt("  Numero de sala: ")
            if d.isdigit() and int(d) in SALAS:
                destino_id = int(d)
                break
            await player.send("  Sala invalida.")
        player.inventario[iid] -= 1
        await broadcast_sala(player.sala_id, f"  {player.nombre} desaparece en un destello azul.")
        player.sala_id = destino_id
        await player.send(f"  Llegas a: {SALAS[destino_id]['nombre']}")
        await broadcast_sala(destino_id, f"  {player.nombre} aparece en un destello azul.", excluir=player)
        await describir_sala(player)
        return True

    return False


# ============================================================
# SISTEMA DE CUENTAS — guardar / cargar / autenticar
# ============================================================

def _ruta_cuenta(usuario: str) -> str:
    seguro = "".join(c for c in usuario.lower() if c.isalnum() or c == "_")
    return os.path.join(SAVES_DIR, f"{seguro}.json")

def _hash_password(password: str, salt: str) -> str:
    return hashlib.sha256((salt + password).encode()).hexdigest()

# ── Versiones síncronas (ficheros locales, fallback) ──────────

def _leer_fichero(usuario: str) -> dict | None:
    ruta = _ruta_cuenta(usuario)
    if not os.path.isfile(ruta):
        return None
    with open(ruta, "r", encoding="utf-8") as f:
        return json.load(f)

def _escribir_fichero(datos: dict):
    seguro = "".join(c for c in datos["usuario"].lower() if c.isalnum() or c == "_")
    ruta = os.path.join(SAVES_DIR, f"{seguro}.json")
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=2)

# ── API unificada (async, Supabase si disponible) ─────────────

async def cuenta_existe_async(usuario: str) -> bool:
    if USAR_SUPABASE:
        row = await _sb_get(usuario)
        return row is not None
    return _leer_fichero(usuario) is not None

async def verificar_password_async(usuario: str, password: str) -> bool:
    if USAR_SUPABASE:
        row = await _sb_get(usuario)
    else:
        row = _leer_fichero(usuario)
    if not row:
        return False
    return _hash_password(password, row.get("salt", "")) == row.get("password_hash", "")

async def guardar_cuenta_async(player: "Player"):
    if not player.usuario or not player.personaje:
        return
    # Leer salt/hash previos
    if USAR_SUPABASE:
        prev = await _sb_get(player.usuario)
    else:
        prev = _leer_fichero(player.usuario)
    prev = prev or {}

    datos = {
        "usuario":       player.usuario,
        "password_hash": prev.get("password_hash", ""),
        "salt":          prev.get("salt", ""),
        "data": {
            "nombre":     player.nombre,
            "nivel":      player.nivel,
            "xp":         player.xp,
            "monedas":    player.monedas,
            "inventario": player.inventario,
            "sala_id":    player.sala_id,
            "personaje": {
                "nombreClase": player.personaje["nombreClase"],
                "vidaMax":     player.personaje["vidaMax"],
                "vidaActual":  player.personaje["vidaActual"],
                "manaMax":     player.personaje["manaMax"],
                "manaActual":  player.personaje["manaActual"],
                "danioBase":   player.personaje["danioBase"],
            },
        }
    }
    if USAR_SUPABASE:
        await _sb_upsert(datos)
    else:
        merged = {**datos, **datos["data"]}  # fichero plano para compatibilidad
        merged["nombre"] = datos["data"]["nombre"]
        _escribir_fichero(merged)

async def cargar_cuenta_async(player: "Player", usuario: str):
    if USAR_SUPABASE:
        row = await _sb_get(usuario)
    else:
        row = _leer_fichero(usuario)
    if not row:
        raise ValueError(f"Cuenta no encontrada: {usuario}")

    # Supabase guarda en columna "data", fichero local es plano
    datos = row.get("data", row)

    player.usuario    = usuario
    player.nombre     = datos.get("nombre", usuario)
    player.nivel      = datos.get("nivel", 1)
    player.xp         = datos.get("xp", 0)
    player.monedas    = datos.get("monedas", 0)
    player.inventario = datos.get("inventario", {})
    player.sala_id    = datos.get("sala_id", 1)

    clase = datos.get("personaje", {}).get("nombreClase", "guerrero")
    base  = deepcopy(CLASES[clase])
    pg    = datos.get("personaje", {})
    player.personaje = {
        "nombre":      player.nombre,
        "nombreClase": clase,
        "vidaMax":     pg.get("vidaMax",    base["vidaMax"]),
        "vidaActual":  pg.get("vidaActual", base["vidaMax"]),
        "manaMax":     pg.get("manaMax",    base["manaMax"]),
        "manaActual":  pg.get("manaActual", base["manaMax"]),
        "danioBase":   pg.get("danioBase",  base["danioBase"]),
        **base,
    }
    player.personaje["vidaMax"]    = pg.get("vidaMax",    base["vidaMax"])
    player.personaje["vidaActual"] = pg.get("vidaActual", base["vidaMax"])
    player.personaje["manaMax"]    = pg.get("manaMax",    base["manaMax"])
    player.personaje["manaActual"] = pg.get("manaActual", base["manaMax"])
    player.personaje["danioBase"]  = pg.get("danioBase",  base["danioBase"])

async def crear_cuenta_async(usuario: str, password: str):
    salt   = hashlib.sha256(os.urandom(16)).hexdigest()[:16]
    hashed = _hash_password(password, salt)
    row    = {"usuario": usuario, "password_hash": hashed, "salt": salt, "data": {}}
    if USAR_SUPABASE:
        await _sb_upsert(row)
    else:
        _escribir_fichero({**row, "nombre": usuario})

# ── Alias síncronos para compatibilidad con código existente ──
# (los llamamos con await en los handlers ya async)
cuenta_existe      = lambda u: None   # no usar directamente
verificar_password = lambda u, p: None
guardar_cuenta     = lambda player: None
cargar_cuenta      = lambda player, u: None
crear_cuenta_en_disco = lambda u, p: None


# ============================================================
# FLUJO DE AUTENTICACIÓN
# ============================================================

async def flujo_auth(player: "Player") -> bool:
    """
    Muestra el menú de login/registro.
    Devuelve True si el jugador quedó autenticado, False si se desconectó.
    """
    await player.send("=" * 52)
    await player.send("       BIENVENIDO AL MUD MULTIPLAYER")
    await player.send("=" * 52)

    while True:
        opcion = await player.send_prompt(
            "\n  1. Crear cuenta nueva\n"
            "  2. Iniciar sesion\n"
            "  Elige (1/2): "
        )
        if opcion == "":       # desconexión durante auth
            return False
        if opcion in ("1", "2"):
            break
        await player.send("  Escribe 1 o 2.")

    if opcion == "1":
        return await flujo_registro(player)
    else:
        return await flujo_login(player)


async def flujo_registro(player: "Player") -> bool:
    """Crea una cuenta nueva y construye el personaje."""
    await player.send("\n  --- CREAR CUENTA ---")

    # Usuario
    while True:
        usuario = (await player.send_prompt("  Nombre de usuario: ")).strip()
        if not usuario:
            return False
        if len(usuario) < 3:
            await player.send("  Minimo 3 caracteres.")
            continue
        if await cuenta_existe_async(usuario):
            await player.send("  Ese usuario ya existe. Elige otro.")
            continue
        break

    # Contraseña
    while True:
        pw1 = (await player.send_prompt("  Contrasena: ")).strip()
        if not pw1:
            return False
        if len(pw1) < 4:
            await player.send("  Minimo 4 caracteres.")
            continue
        pw2 = (await player.send_prompt("  Repite contrasena: ")).strip()
        if pw1 != pw2:
            await player.send("  Las contrasenas no coinciden.")
            continue
        break

    # Nombre visible en el juego
    nombre = (await player.send_prompt("  Como te llamaras en el juego? ")).strip()
    if not nombre:
        nombre = usuario

    # Elegir clase
    lineas = ["\n  CLASES DISPONIBLES:"]
    for i, (clase, s) in enumerate(CLASES.items(), 1):
        atqs = s["ataquesTurno"]
        atq_str = f"{atqs[0]}-{atqs[1]}" if isinstance(atqs, list) else str(atqs)
        lineas.append(
            f"  {i:2}. {clase:<12}  HP:{s['vidaMax']:>3}  "
            f"Dano:{s['danioBase']:>3}  Mana:{s['manaMax']:>3}  Atqs:{atq_str}"
        )
    await player.send("\n".join(lineas))

    while True:
        el = (await player.send_prompt("\n  Elige clase (nombre o numero): ")).strip().lower()
        if el.isdigit() and 0 <= int(el) - 1 < len(CLASES):
            clase_elegida = list(CLASES.keys())[int(el) - 1]
            break
        elif el in CLASES:
            clase_elegida = el
            break
        await player.send("  Clase no encontrada.")

    # Crear cuenta en disco
    await crear_cuenta_async(usuario, pw1)

    # Inicializar player
    player.usuario = usuario
    player.nombre  = nombre
    base = deepcopy(CLASES[clase_elegida])
    player.personaje = {
        "nombre":      nombre,
        "nombreClase": clase_elegida,
        "vidaActual":  base["vidaMax"],
        "manaActual":  base["manaMax"],
        **base,
    }

    # Guardar inmediatamente con los datos del personaje
    await guardar_cuenta_async(player)

    await player.send(
        f"\n  Cuenta creada! Bienvenido, {nombre} el {clase_elegida.capitalize()}.\n"
        f"  HP:{player.personaje['vidaActual']}  "
        f"Mana:{player.personaje['manaActual']}  "
        f"Dano:{player.personaje['danioBase']}"
    )
    return True


async def flujo_login(player: "Player") -> bool:
    """Autentica una cuenta existente y carga sus datos."""
    await player.send("\n  --- INICIAR SESION ---")

    intentos = 0
    while intentos < 3:
        usuario = (await player.send_prompt("  Usuario: ")).strip()
        if not usuario:
            return False

        if not await cuenta_existe_async(usuario):
            await player.send("  Usuario no encontrado.")
            intentos += 1
            continue

        # Comprobar si ya está conectado
        ya_conectado = any(
            p.usuario == usuario for p in jugadores_conectados if hasattr(p, "usuario")
        )
        if ya_conectado:
            await player.send("  Ese jugador ya esta conectado.")
            return False

        pw = (await player.send_prompt("  Contrasena: ")).strip()
        if not pw:
            return False

        if not await verificar_password_async(usuario, pw):
            await player.send("  Contrasena incorrecta.")
            intentos += 1
            continue

        # Autenticado — cargar datos
        await cargar_cuenta_async(player, usuario)
        await player.send(
            f"\n  Bienvenido de vuelta, {player.nombre}!\n"
            f"  Nivel {player.nivel}  XP:{player.xp}/{XP_POR_NIVEL}  Monedas:{player.monedas}\n"
            f"  HP:{player.personaje['vidaActual']}/{player.personaje['vidaMax']}  "
            f"Mana:{player.personaje['manaActual']}/{player.personaje['manaMax']}"
        )
        return True

    await player.send("  Demasiados intentos fallidos. Desconectando.")
    return False


# ============================================================
# SETUP PERSONAJE (ahora solo delega a flujo_auth)
# ============================================================

async def setup_personaje(player: "Player") -> bool:
    """Punto de entrada de autenticación. Devuelve True si el jugador está listo."""
    return await flujo_auth(player)


# ============================================================
# SALAS
# ============================================================

async def describir_sala(player: Player):
    sala = SALAS.get(player.sala_id)
    if not sala:
        return
    otros   = [p.nombre for p in jugadores_en_sala(player.sala_id) if p != player]
    salidas = ", ".join(sala["conexiones"].keys())

    lineas = [
        f"\n{'=' * 52}",
        f"  [{player.sala_id}] {sala['nombre']}",
        f"{'=' * 52}",
        f"  {sala['descripcion']}",
    ]

    # Mostrar bioma si la sala lo tiene
    if "bioma" in sala:
        bioma = BIOMAS.get(sala["bioma"], {})
        lineas.append(f"  {bioma.get('emoji','🌍')} Bioma: {sala['bioma'].capitalize()}  —  {bioma.get('descripcion','')}")

    if otros:
        lineas.append(f"  Aqui tambien: {', '.join(otros)}")
    lineas.append(f"  Salidas: {salidas}")

    # Servicios disponibles en la sala
    servicios = []
    if sala.get("tienda"):
        servicios.append("🏪 Tienda (escribe 'tienda')")
    if sala.get("hospital"):
        servicios.append("🏥 Hospital (escribe 'hospital')")
    if servicios:
        lineas.append(f"  Servicios: {' | '.join(servicios)}")

    # Indicar si hay peligro
    tiene_enemigos = "bioma" in sala or sala.get("encuentros")
    if tiene_enemigos:
        lineas.append("  Hay enemigos aqui. Escribe 'atacar' para combatir.")

    await player.send("\n".join(lineas))


async def mover_jugador(player: Player, direccion: str):
    if player.muerto:
        await player.send("  Estas muerto. Espera el respawn.")
        return
    if player.combate and player.combate.estado != EstadoCombate.FINALIZADO:
        await player.send("  No puedes huir del combate!")
        return
    sala_actual = SALAS.get(player.sala_id)
    if not sala_actual:
        return
    nueva = sala_actual["conexiones"].get(direccion)
    if nueva is None:
        await player.send(f"  No puedes ir al {direccion}.")
        return
    await broadcast_sala(player.sala_id, f"  {player.nombre} se va hacia el {direccion}.", excluir=player)
    player.sala_id = nueva
    await broadcast_sala(player.sala_id, f"  {player.nombre} ha llegado.", excluir=player)
    await notify_web_session(player)
    await broadcast_players_to_web()
    await describir_sala(player)


# ============================================================
# COMBATE
# ============================================================

async def iniciar_combate(sala_id: int):
    if sala_id in combates_activos:
        return
    sala = SALAS.get(sala_id)
    if not sala:
        return

    # La sala tiene combate si tiene bioma O encuentros no vacíos
    tiene_combate = "bioma" in sala or bool(sala.get("encuentros"))
    if not tiene_combate:
        return

    jug = [p for p in jugadores_en_sala(sala_id) if not p.muerto]
    if not jug:
        return

    combate = Combate(sala_id, jug)
    combate.cargar_enemigos(sala_id)

    if not combate.enemigos:   # pool vacío (no debería pasar, pero por si acaso)
        return

    combates_activos[sala_id] = combate
    for p in jug:
        p.combate = combate

    await broadcast_sala(sala_id, "\n" + "=" * 52)
    await broadcast_sala(sala_id, "  COMBATE!")
    await broadcast_sala(sala_id, "=" * 52)
    for e in combate.enemigos:
        await broadcast_sala(sala_id, f"  {e['nombre']}  HP:{e['vida_actual']}/{e['vidaMax']}  [{e.get('tier','?')}]")

    asyncio.create_task(loop_combate(combate))


async def loop_combate(combate: Combate):
    sala_id = combate.sala_id

    while combate.enemigos_vivos() and combate.jugadores_vivos():
        combate.turno   += 1
        combate.acciones = {}
        combate.estado   = EstadoCombate.ESPERANDO_ACCIONES

        # Regen mana
        for p in combate.jugadores_vivos():
            p.personaje["manaActual"] = min(
                p.personaje["manaActual"] + p.personaje.get("manaTurno", 0),
                p.personaje["manaMax"]
            )

        # Mostrar estado del turno
        await broadcast_sala(sala_id, f"\n{'-'*52}\n  TURNO {combate.turno}\n{'-'*52}")
        for e in combate.enemigos_vivos():
            await broadcast_sala(sala_id, f"  {e['nombre']}  HP:{e['vida_actual']}/{e['vidaMax']}")
        for p in combate.jugadores_vivos():
            await p.send(
                f"  TU [{p.personaje['nombreClase']}]  "
                f"HP:{p.personaje['vidaActual']}/{p.personaje['vidaMax']}  "
                f"Mana:{p.personaje['manaActual']}/{p.personaje['manaMax']}"
            )

        await broadcast_sala(sala_id, "  Esperando acciones de todos...")

        # Todos los jugadores vivos eligen en paralelo
        await asyncio.gather(*[
            asyncio.create_task(pedir_accion(p, combate))
            for p in combate.jugadores_vivos()
        ])

        # Resolución
        combate.estado = EstadoCombate.RESOLVIENDO
        await broadcast_sala(sala_id, "\n  --- RESOLUCION ---")
        for p in list(combate.jugadores_vivos()):
            await resolver_accion(p, combate.acciones.get(p.id, "3"), combate)
            if not combate.enemigos_vivos():
                break

        # Turno enemigos
        if combate.enemigos_vivos() and combate.jugadores_vivos():
            combate.estado = EstadoCombate.TURNO_ENEMIGO
            await broadcast_sala(sala_id, "\n  --- TURNO ENEMIGOS ---")
            for e in combate.enemigos_vivos():
                vivos_jug = combate.jugadores_vivos()
                if not vivos_jug:
                    break
                obj = random.choice(vivos_jug)
                for _ in range(ataques_por_turno(e.get("ataquesTurno", 1))):
                    if obj.personaje["vidaActual"] <= 0:
                        break
                    d = calcular_danio(e["danioBase"])
                    obj.personaje["vidaActual"] = max(0, obj.personaje["vidaActual"] - d)
                    await broadcast_sala(
                        sala_id,
                        f"  {e['nombre']} golpea a {obj.nombre} -{d}  "
                        f"({obj.personaje['vidaActual']}/{obj.personaje['vidaMax']})"
                    )

        # Detectar muertes
        for p in combate.jugadores:
            if p.personaje["vidaActual"] <= 0 and not p.muerto:
                await broadcast_sala(sala_id, f"  {p.nombre} ha caido!")
                asyncio.create_task(respawn(p))

        # Actualizar dashboards web de todos los jugadores del combate
        for p in combate.jugadores:
            asyncio.create_task(notify_web_session(p))

    # ── FIN DEL COMBATE ──
    combate.estado = EstadoCombate.FINALIZADO

    if combate.enemigos_vivos():
        await broadcast_sala(sala_id, "\n  DERROTA.")
    else:
        await broadcast_sala(sala_id, "\n  VICTORIA!")
        xp = sum(xp_de_tier(e.get("tier", "Base")) for e in combate.enemigos)
        await broadcast_sala(sala_id, f"  {xp} XP para cada superviviente.")
        for p in combate.jugadores_vivos():
            await dar_xp(p, xp)
            p.personaje["vidaActual"] = min(p.personaje["vidaActual"] + 20, p.personaje["vidaMax"])
        await broadcast_sala(sala_id, "  +20 HP a cada superviviente.")

    # Limpiar buffs
    for p in combate.jugadores:
        if p.buff_danio:
            p.buff_danio = False
            asyncio.create_task(p.send("  Pocion de Danio terminada."))

    del combates_activos[sala_id]
    for p in combate.jugadores:
        p.combate = None


async def pedir_accion(player: Player, combate: Combate):
    """
    Consume del input_queue EXCLUSIVAMENTE.
    FIX: Enter vacío → ignora y repite. None → pasa turno (desconexión).
    """
    if player.personaje["vidaActual"] <= 0:
        combate.acciones[player.id] = "3"
        return

    await player.send(
        "  1-Atacar  2-Especial  3-Pasar  4-Objeto\n"
        "  decir <msg>  |  g <msg>"
    )

    while True:
        raw = await player.recv()

        # Desconexión durante combate → pasar turno automáticamente
        if raw is None:
            combate.acciones[player.id] = "3"
            return

        accion = raw.strip()

        # FIX: Enter vacío → ignorar, no romper
        if not accion:
            continue

        if accion.lower().startswith("decir "):
            await cmd_chat(player, accion[6:], sala_solo=True)
            continue
        if accion.lower().startswith("g "):
            await cmd_chat(player, accion[2:], sala_solo=False)
            continue
        if accion == "4":
            await cmd_mochila(player)
            await player.send("  Que objeto usar? (Enter=cancelar, o escribe vida/dano/gema):")
            n = await player.recv()
            if n and n.strip():
                await usar_item(player, n.strip(), combate=combate)
            await player.send("  1-Atacar  2-Especial  3-Pasar  4-Objeto")
            continue
        if accion in ("1", "2", "3"):
            combate.acciones[player.id] = accion
            await broadcast_sala(combate.sala_id, f"  {player.nombre} ha elegido.", excluir=player)
            return

        await player.send("  Elige 1, 2, 3 o 4.")


async def resolver_accion(player: Player, accion: str, combate: Combate):
    sala_id = combate.sala_id
    vivos   = combate.enemigos_vivos()
    if not vivos:
        return
    obj = vivos[0]
    p   = player.personaje

    if accion == "1":
        num = ataques_por_turno(p.get("ataquesTurno", 1))
        for _ in range(num):
            if obj["vida_actual"] <= 0:
                break
            base = calcular_danio(p["danioBase"])
            d    = int(base * 1.3) if player.buff_danio else base
            sfx  = " (+30%)" if player.buff_danio else ""
            obj["vida_actual"] = max(0, obj["vida_actual"] - d)
            await broadcast_sala(sala_id,
                f"  {player.nombre} ataca {obj['nombre']} -{d}{sfx}  "
                f"({obj['vida_actual']}/{obj['vidaMax']})")

    elif accion == "2":
        costo = p.get("costoEspecial", 0)
        if p["manaActual"] < costo:
            await player.send(f"  Sin mana (necesitas {costo}, tienes {p['manaActual']}).")
            return
        p["manaActual"] -= costo
        clase = p["nombreClase"]

        if clase == "curandero":
            cur = p.get("curacionEspecial", 20)
            p["vidaActual"] = min(p["vidaActual"] + cur, p["vidaMax"])
            await broadcast_sala(sala_id,
                f"  {player.nombre} se cura +{cur} HP ({p['vidaActual']}/{p['vidaMax']})")
        else:
            base = calcular_danio(p.get("danioEspecial", p["danioBase"]))
            d    = int(base * 1.3) if player.buff_danio else base
            sfx  = " (+30%)" if player.buff_danio else ""
            obj["vida_actual"] = max(0, obj["vida_actual"] - d)
            nombre_hab = {
                "guerrero":   "Golpe de Tanque",
                "mago":       "Magia Antigua",
                "arquero":    "Flecha Ignea",
                "nigromante": "Maldicion del Tiempo",
                "hechicero":  "Invocar Esqueleto",
                "caballero":  "Embestida",
                "cazador":    "Inmovilizar",
                "asesino":    "Muerte Garantizada",
                "barbaro":    "A Bocajarro",
            }.get(clase, "Habilidad Especial")
            await broadcast_sala(sala_id,
                f"  {player.nombre} usa {nombre_hab} en {obj['nombre']} -{d}{sfx}  "
                f"({obj['vida_actual']}/{obj['vidaMax']})")

    elif accion == "3":
        await broadcast_sala(sala_id, f"  {player.nombre} pasa el turno.")


# ============================================================
# COMANDOS
# ============================================================

async def cmd_hospital(player: Player):
    """Cura toda la vida y el mana. Solo disponible en salas con hospital."""
    p = player.personaje
    hp_faltaba   = p["vidaMax"]   - p["vidaActual"]
    mana_faltaba = p["manaMax"]   - p["manaActual"]

    if hp_faltaba == 0 and mana_faltaba == 0:
        await player.send("  Ya tienes la vida y el mana al maximo. No necesitas curacion.")
        return

    p["vidaActual"] = p["vidaMax"]
    p["manaActual"] = p["manaMax"]

    await player.send(
        f"\n  🏥 El medico te atiende.\n"
        f"  HP restaurado:   +{hp_faltaba}  ({p['vidaActual']}/{p['vidaMax']})\n"
        f"  Mana restaurado: +{mana_faltaba}  ({p['manaActual']}/{p['manaMax']})\n"
        f"  Estas listo para continuar."
    )
    await broadcast_sala(player.sala_id, f"  {player.nombre} sale del hospital completamente curado.", excluir=player)
    await notify_web_session(player)


# ============================================================
# SISTEMA DE GRUPOS
# ============================================================

async def broadcast_grupo(grupo: Grupo, texto: str, excluir: Player = None):
    """Envía un mensaje a todos los miembros del grupo."""
    for p in grupo.miembros:
        if p != excluir:
            await p.send(texto)


async def cmd_invitar(player: Player, nombre_objetivo: str):
    """Invita a otro jugador al grupo."""
    if not nombre_objetivo:
        await player.send("  Uso: invitar <nombre>")
        return

    # Buscar jugador por nombre (case-insensitive)
    objetivo = next(
        (p for p in jugadores_conectados
         if p.nombre and p.nombre.lower() == nombre_objetivo.lower()),
        None
    )

    if objetivo is None:
        await player.send(f"  Jugador '{nombre_objetivo}' no encontrado. Escribe 'jugadores' para ver quién está conectado.")
        return

    if objetivo == player:
        await player.send("  No puedes invitarte a ti mismo.")
        return

    if objetivo.grupo and objetivo.grupo == player.grupo:
        await player.send(f"  {objetivo.nombre} ya está en tu grupo.")
        return

    if objetivo.invitacion_de is not None:
        await player.send(f"  {objetivo.nombre} ya tiene una invitación pendiente.")
        return

    if objetivo.grupo is not None:
        await player.send(f"  {objetivo.nombre} ya pertenece a otro grupo.")
        return

    # Si el que invita no tiene grupo, crea uno
    if player.grupo is None:
        nuevo_grupo = Grupo(player)
        grupos[nuevo_grupo.id] = nuevo_grupo
        player.grupo = nuevo_grupo

    # Guardar invitación pendiente en el objetivo
    objetivo.invitacion_de = player

    await player.send(f"  Invitación enviada a {objetivo.nombre}.")
    await objetivo.send(
        f"\n  ✉ {player.nombre} te ha invitado a su grupo.\n"
        f"  Escribe 'aceptar' o 'rechazar'."
    )


async def cmd_aceptar(player: Player):
    """Acepta la invitación de grupo pendiente."""
    if player.invitacion_de is None:
        await player.send("  No tienes ninguna invitación pendiente.")
        return

    invitador = player.invitacion_de
    player.invitacion_de = None

    # Comprobar que el invitador sigue conectado y tiene grupo
    if invitador not in jugadores_conectados:
        await player.send("  El jugador que te invitó ya no está conectado.")
        return

    if invitador.grupo is None:
        await player.send("  El grupo ya no existe.")
        return

    grupo = invitador.grupo
    grupo.miembros.append(player)
    player.grupo = grupo

    await player.send(
        f"  Te has unido al grupo de {invitador.nombre}.\n"
        f"  Miembros: {', '.join(grupo.lista_nombres())}"
    )
    await broadcast_grupo(grupo, f"  👥 {player.nombre} se ha unido al grupo.", excluir=player)
    await broadcast_players_to_web()


async def cmd_rechazar(player: Player):
    """Rechaza la invitación de grupo pendiente."""
    if player.invitacion_de is None:
        await player.send("  No tienes ninguna invitación pendiente.")
        return

    invitador = player.invitacion_de
    player.invitacion_de = None

    await player.send(f"  Has rechazado la invitación de {invitador.nombre}.")
    await invitador.send(f"  {player.nombre} ha rechazado tu invitación.")

    # Si el grupo del invitador quedó solo, disolverlo
    if invitador.grupo and len(invitador.grupo.miembros) <= 1:
        await _disolver_grupo(invitador.grupo)


async def cmd_grupo(player: Player):
    """Muestra la información del grupo actual."""
    if player.grupo is None:
        await player.send("  No perteneces a ningún grupo. Usa 'invitar <nombre>' para crear uno.")
        return

    grupo = player.grupo
    lineas = [
        f"\n  👥 GRUPO (id:{grupo.id})",
        f"  Lider: {grupo.lider.nombre}",
        f"  Miembros ({len(grupo.miembros)}):",
    ]
    for m in grupo.miembros:
        sala_nombre = SALAS.get(m.sala_id, {}).get("nombre", "?")
        es_lider    = " 👑" if m == grupo.lider else ""
        lineas.append(f"    - {m.nombre} [Nv.{m.nivel} {m.personaje['nombreClase']}] en {sala_nombre}{es_lider}")
    await player.send("\n".join(lineas))


async def cmd_salirgrupo(player: Player):
    """El jugador abandona su grupo."""
    if player.grupo is None:
        await player.send("  No perteneces a ningún grupo.")
        return

    grupo = player.grupo
    await broadcast_grupo(grupo, f"  👥 {player.nombre} ha abandonado el grupo.", excluir=player)

    grupo.quitar(player)
    player.grupo = None

    await player.send("  Has abandonado el grupo.")

    # Si queda un solo miembro, disolver
    if len(grupo.miembros) <= 1:
        await _disolver_grupo(grupo)
    else:
        await broadcast_grupo(grupo,
            f"  El nuevo líder es {grupo.lider.nombre}."
            if grupo.lider != grupo.miembros[0] else ""
        )

    await broadcast_players_to_web()


async def cmd_gchat(player: Player, mensaje: str):
    """Chat de grupo."""
    if player.grupo is None:
        await player.send("  No perteneces a ningún grupo. Usa 'invitar' para crear uno.")
        return
    if not mensaje.strip():
        await player.send("  Que quieres decir al grupo?")
        return
    texto = f"  [Grupo] {player.nombre}: {mensaje}"
    await broadcast_grupo(player.grupo, texto)


async def _disolver_grupo(grupo: Grupo):
    """Disuelve un grupo vacío o de un solo miembro."""
    for m in grupo.miembros:
        m.grupo = None
        await m.send("  El grupo se ha disuelto.")
    grupos.pop(grupo.id, None)

async def procesar_comando(player: Player, cmd: str):
    partes = cmd.lower().strip().split()
    if not partes:
        return
    ac = partes[0]

    if ac in ("norte", "sur", "este", "oeste", "n", "s", "e", "o"):
        dirs = {"n": "norte", "s": "sur", "e": "este", "o": "oeste"}
        await mover_jugador(player, dirs.get(ac, ac))

    elif ac in ("mirar", "look", "l"):
        await describir_sala(player)

    elif ac in ("stats", "estado"):
        p  = player.personaje
        xf = XP_POR_NIVEL - player.xp
        await player.send(
            f"\n  {player.nombre} [{p['nombreClase']}]  Nv.{player.nivel}\n"
            f"  HP:      {p['vidaActual']}/{p['vidaMax']}\n"
            f"  Mana:    {p['manaActual']}/{p['manaMax']}\n"
            f"  Dano:    {p['danioBase']}\n"
            f"  XP:      {player.xp}/{XP_POR_NIVEL}  (faltan {xf})\n"
            f"  Monedas: {player.monedas}"
        )

    elif ac in ("jugadores", "who"):
        lineas = ["\n  Jugadores conectados:"]
        for p in jugadores_conectados:
            st     = "MUERTO" if p.muerto else f"Sala {p.sala_id}"
            grp    = f" [Grupo {p.grupo.id}]" if p.grupo else ""
            lineas.append(f"  - {p.nombre} [Nv.{p.nivel} {p.personaje['nombreClase']}] ({st}){grp}")
        await player.send("\n".join(lineas))

    elif ac == "invitar":
        nombre_obj = cmd[len(ac):].strip()
        await cmd_invitar(player, nombre_obj)

    elif ac == "aceptar":
        await cmd_aceptar(player)

    elif ac == "rechazar":
        await cmd_rechazar(player)

    elif ac in ("grupo", "party"):
        await cmd_grupo(player)

    elif ac in ("salirgrupo", "salirparty", "kickme"):
        await cmd_salirgrupo(player)

    elif ac in ("gc", "gchat"):
        await cmd_gchat(player, cmd[len(ac):].strip())

    elif ac == "atacar":
        if player.muerto:
            await player.send("  Estas muerto. Espera el respawn.")
            return
        sala = SALAS.get(player.sala_id)
        tiene_combate = sala and ("bioma" in sala or bool(sala.get("encuentros")))
        if not tiene_combate:
            await player.send("  No hay enemigos en esta sala.")
        elif player.sala_id in combates_activos:
            await player.send("  Ya hay un combate en curso aqui.")
        else:
            await iniciar_combate(player.sala_id)

    elif ac in ("decir", "d"):
        await cmd_chat(player, cmd[len(ac):].strip(), sala_solo=True)

    elif ac == "g":
        await cmd_chat(player, cmd[2:].strip(), sala_solo=False)

    elif ac in ("tienda", "shop"):
        if player.muerto:
            await player.send("  Estas muerto.")
        elif player.combate:
            await player.send("  No puedes abrir la tienda en combate.")
        elif not SALAS.get(player.sala_id, {}).get("tienda"):
            await player.send("  No hay tienda en esta sala.")
        else:
            await cmd_tienda(player)

    elif ac in ("hospital", "curar", "heal"):
        if player.muerto:
            await player.send("  Estas muerto. Espera el respawn.")
        elif player.combate:
            await player.send("  No puedes usar el hospital en combate.")
        elif not SALAS.get(player.sala_id, {}).get("hospital"):
            await player.send("  No hay hospital en esta sala.")
        else:
            await cmd_hospital(player)

    elif ac in ("mochila", "inv", "inventario"):
        await cmd_mochila(player)

    elif ac == "usar":
        if len(partes) < 2:
            await player.send("  Uso: usar <objeto>  (vida / dano / gema)")
            return
        await usar_item(player, " ".join(partes[1:]))

    elif ac in ("nivel", "level"):
        await player.send(
            f"  Nivel {player.nivel}  XP:{player.xp}/{XP_POR_NIVEL}  Monedas:{player.monedas}")

    elif ac in ("guardar", "save"):
        await guardar_cuenta_async(player)
        await player.send("  Progreso guardado.")

    elif ac == "ayuda":
        await player.send(
            "\n  MOVER:    n s e o  (norte sur este oeste)\n"
            "  ACCION:   mirar | atacar\n"
            "  TIENDA:   tienda | mochila | usar <objeto>\n"
            "  HOSPITAL: hospital  (solo en salas con 🏥)\n"
            "  INFO:     stats | nivel | jugadores\n"
            "  CUENTA:   guardar\n"
            "  GRUPO:    invitar <nombre> | aceptar | rechazar\n"
            "            grupo | salirgrupo | gc <msg>\n"
            "  CHAT:     decir <msg> (sala) | g <msg> (global)\n"
            "  CHAT WEB: http://localhost:8080/chat.html"
        )

    else:
        await player.send(f"  Desconocido: '{cmd}'. Escribe 'ayuda'.")


# ============================================================
# HANDLE GAME WS
# ============================================================

async def handle_game_ws(ws, usuario: str):
    player = Player(ws)
    player.usuario = usuario

    if len(jugadores_conectados) >= MAX_JUGADORES:
        await player.send("Servidor lleno (max 5 jugadores).")
        return

    jugadores_conectados.append(player)

    async def reader_task():
        try:
            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    await player.input_queue.put(msg.data)
                elif msg.type in (aiohttp.WSMsgType.ERROR, aiohttp.WSMsgType.CLOSE):
                    break
        except Exception:
            pass
        finally:
            await player.input_queue.put(None)

    rt = asyncio.create_task(reader_task())

    try:
        await cargar_cuenta_async(player, usuario)
        await player.send(
            f"\n  Bienvenido de vuelta, {player.nombre}!\n"
            f"  Nivel {player.nivel}  XP:{player.xp}/{XP_POR_NIVEL}  Monedas:{player.monedas}\n"
            f"  HP:{player.personaje['vidaActual']}/{player.personaje['vidaMax']}  "
            f"Mana:{player.personaje['manaActual']}/{player.personaje['manaMax']}"
        )
        await player.send_status()
        await broadcast_todos(f"\n  {player.nombre} se unio al dungeon!")
        await broadcast_players_to_web()
        await describir_sala(player)

        while True:
            if player.combate and player.combate.estado != EstadoCombate.FINALIZADO:
                await asyncio.sleep(0.05)
                continue
            raw = await player.recv()
            if raw is None:
                break
            if not raw.strip():
                continue
            await procesar_comando(player, raw.strip())

    except Exception as e:
        print(f"[GAME] Error: {e}")
    finally:
        if player.usuario and player.personaje:
            await guardar_cuenta_async(player)
            print(f"[SAVE] {player.usuario}")
        if player.grupo:
            asyncio.create_task(cmd_salirgrupo(player))
        for p in jugadores_conectados:
            if p.invitacion_de == player:
                p.invitacion_de = None
                asyncio.create_task(p.send(f"  La invitacion de {player.nombre} expiro."))
        rt.cancel()
        if player in jugadores_conectados:
            jugadores_conectados.remove(player)
        if player.nombre:
            await broadcast_todos(f"\n  {player.nombre} abandono el dungeon.")
            await broadcast_players_to_web()
        print(f"[GAME] Desconectado: {usuario}")


# ============================================================
# HANDLE DASHBOARD WS
# ============================================================

async def handle_dashboard_ws(ws, usuario: str):
    chat_ws_clients.add(ws)
    web_sessions[usuario] = ws
    print(f"[DASH] {usuario} conectado")

    try:
        player_online = next((p for p in jugadores_conectados if p.usuario == usuario), None)
        if player_online and player_online.personaje:
            p = player_online.personaje
            stats = {
                "hp": p["vidaActual"],        "hpMax":         p["vidaMax"],
                "mana": p["manaActual"],      "manaMax":       p["manaMax"],
                "nivel": player_online.nivel, "xp":            player_online.xp,
                "xpMax": XP_POR_NIVEL,        "monedas":       player_online.monedas,
                "clase": p["nombreClase"],    "nombre":        player_online.nombre,
                "sala_id": player_online.sala_id,
                "danioBase": p["danioBase"],
                "ataquesTurno": p.get("ataquesTurno", 1),
                "costoEspecial": p.get("costoEspecial", 0),
                "online": True,
            }
        else:
            ruta = _ruta_cuenta(usuario)
            with open(ruta) as f:
                save = json.load(f)
            p_save = save.get("personaje", {})
            clase  = p_save.get("nombreClase", "guerrero")
            base_c = CLASES.get(clase, {})
            stats = {
                "hp": p_save.get("vidaActual", 0),   "hpMax":   p_save.get("vidaMax", 0),
                "mana": p_save.get("manaActual", 0), "manaMax": p_save.get("manaMax", 0),
                "nivel": save.get("nivel", 1),        "xp":     save.get("xp", 0),
                "xpMax": XP_POR_NIVEL,                "monedas":save.get("monedas", 0),
                "clase": clase,                        "nombre": save.get("nombre", usuario),
                "sala_id": save.get("sala_id", 1),
                "danioBase": p_save.get("danioBase", 0),
                "ataquesTurno": base_c.get("ataquesTurno", 1),
                "costoEspecial": base_c.get("costoEspecial", 0),
                "online": False,
            }

        await ws.send_json({"type": "auth_ok", "stats": stats})

        map_data = {}
        for s_id, s in SALAS.items():
            tiene_boss = any(
                ENEMIGOS.get(tipo, {}).get("tier") in ("Boss", "Elite")
                for tipo, _ in s.get("encuentros", [])
            )
            map_data[str(s_id)] = {
                "nombre": s["nombre"],    "bioma":    s.get("bioma"),
                "tienda": s.get("tienda", False),
                "hospital": s.get("hospital", False),
                "boss": tiene_boss,
                "segura": not ("bioma" in s or bool(s.get("encuentros"))),
            }
        await ws.send_json({"type": "map", "salas": map_data, "player_sala": stats["sala_id"]})
        await broadcast_players_to_web()

        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                try:
                    d = json.loads(msg.data)
                    if d.get("type") == "chat":
                        mensaje = d.get("mensaje", "").strip()
                        scope   = d.get("scope", "global")
                        nombre  = stats["nombre"]
                        if not mensaje:
                            continue
                        await broadcast_chat_ws(scope, nombre, mensaje)
                        tag = "[Global-Web]" if scope == "global" else "[Web-Sala]"
                        await broadcast_todos(f"  {tag} {nombre}: {mensaje}")
                except json.JSONDecodeError:
                    pass
            elif msg.type in (aiohttp.WSMsgType.ERROR, aiohttp.WSMsgType.CLOSE):
                break

    except Exception as e:
        print(f"[DASH] Error: {e}")
    finally:
        chat_ws_clients.discard(ws)
        web_sessions.pop(usuario, None)
        print(f"[DASH] {usuario} desconectado")



# ============================================================
# AIOHTTP HANDLERS
# ============================================================

async def http_handler(request: web.Request) -> web.Response:
    """Sirve el HTML para cualquier petición HTTP (GET, HEAD, etc.)."""
    html = get_html().encode("utf-8")
    return web.Response(
        body=html,
        content_type="text/html",
        charset="utf-8",
    )


async def ws_handler(request: web.Request) -> web.WebSocketResponse:
    """Maneja conexiones WebSocket."""
    ws = web.WebSocketResponse(heartbeat=30)
    await ws.prepare(request)

    print(f"[WS] Conexion: {request.remote}")

    try:
        # Primer mensaje: auth
        msg = await asyncio.wait_for(ws.__anext__(), timeout=30)
    except (asyncio.TimeoutError, StopAsyncIteration):
        return ws

    if msg.type != aiohttp.WSMsgType.TEXT:
        return ws

    try:
        data = json.loads(msg.data)
    except json.JSONDecodeError:
        return ws

    msg_type = data.get("type", "")
    usuario  = data.get("usuario", "").strip().lower()
    password = data.get("password", "").strip()

# ── Auth ──────────────────────────────────────────────────
    if msg_type == "game_register":
        # Registro nuevo
        nombre   = data.get("nombre", "").strip() or usuario
        if len(usuario) < 3:
            await ws.send_json({"type": "auth_fail", "msg": "Usuario: minimo 3 caracteres."})
            return ws
        if len(password) < 4:
            await ws.send_json({"type": "auth_fail", "msg": "Contrasena: minimo 4 caracteres."})
            return ws
        if await cuenta_existe_async(usuario):
            await ws.send_json({"type": "auth_fail", "msg": "Ese usuario ya existe."})
            return ws

        await crear_cuenta_async(usuario, password)
        tmp = Player(ws)
        tmp.usuario = usuario
        tmp.nombre  = nombre

        async def reg_reader():
            try:
                async for m in ws:
                    if m.type == aiohttp.WSMsgType.TEXT:
                        await tmp.input_queue.put(m.data)
                    elif m.type in (aiohttp.WSMsgType.ERROR, aiohttp.WSMsgType.CLOSE):
                        break
            except Exception:
                pass
            finally:
                await tmp.input_queue.put(None)

        rt = asyncio.create_task(reg_reader())
        await ws.send_json({"type": "auth_ok"})
        lineas = ["\nCLASES DISPONIBLES:"]
        for i, (clase, s) in enumerate(CLASES.items(), 1):
            atqs = s["ataquesTurno"]
            atq_str = f"{atqs[0]}-{atqs[1]}" if isinstance(atqs, list) else str(atqs)
            lineas.append(f"  {i:2}. {clase:<12}  HP:{s['vidaMax']:>3}  Dano:{s['danioBase']:>3}  Mana:{s['manaMax']:>3}  Atqs:{atq_str}")
        await tmp.send("\n".join(lineas))

        clase_elegida = None
        while True:
            el = (await tmp.send_prompt("\nElige clase (nombre o numero): ")).strip().lower()
            if el.isdigit() and 0 <= int(el)-1 < len(CLASES):
                clase_elegida = list(CLASES.keys())[int(el)-1]
                break
            elif el in CLASES:
                clase_elegida = el
                break
            await tmp.send("  Clase no encontrada.")

        base = deepcopy(CLASES[clase_elegida])
        tmp.personaje = {
            "nombre": nombre, "nombreClase": clase_elegida,
            "vidaActual": base["vidaMax"], "manaActual": base["manaMax"], **base,
        }
        await guardar_cuenta_async(tmp)
        rt.cancel()
        await tmp.send(f"\nCuenta creada! {nombre} el {clase_elegida.capitalize()}")
        await handle_game_ws(ws, usuario)

    elif msg_type == "game_auth":
        if not await cuenta_existe_async(usuario) or not await verificar_password_async(usuario, password):
            await ws.send_json({"type": "auth_fail", "msg": "Usuario o contrasena incorrectos"})
            return ws
        ya = any(p.usuario == usuario for p in jugadores_conectados)
        if ya:
            await ws.send_json({"type": "auth_fail", "msg": "Ya estas jugando en otra ventana."})
            return ws
        await ws.send_json({"type": "auth_ok"})
        await handle_game_ws(ws, usuario)

    elif msg_type == "auth":
        if not await cuenta_existe_async(usuario) or not await verificar_password_async(usuario, password):
            await ws.send_json({"type": "auth_fail", "msg": "Usuario o contrasena incorrectos"})
            return ws
        await handle_dashboard_ws(ws, usuario)

    else:
        await ws.send_json({"type": "auth_fail", "msg": "Tipo desconocido"})

    return ws


# ============================================================
# MAIN
# ============================================================

async def main():
    port = int(os.environ.get("PORT", 8080))

    app = web.Application()
    app.router.add_route("*", "/ws", ws_handler)
    app.router.add_route("*", "/{tail:.*}", http_handler)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

    print(f"[SERVER] Puerto: {port}")
    print(f"[SERVER] Abre http://localhost:{port} para jugar")
    print(f"[SERVER] Clases: {len(CLASES)}  Enemigos: {len(ENEMIGOS)}  Max: {MAX_JUGADORES}")
    print("[SERVER] Listo.\n")

    await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())
