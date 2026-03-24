"""
server.py — MUD Multiplayer
============================
- TCP  puerto 4000  → terminal (client.py)
- WS   puerto 4001  → chat en navegador
- HTTP puerto 8080  → sirve chat.html

Uso:
  pip install websockets
  python3 server.py

Jugar:   python3 client.py <IP>
Chat UI: http://<IP>:8080/chat.html
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
import traceback

SAVES_DIR = "saves"
os.makedirs(SAVES_DIR, exist_ok=True)

# ── Supabase config (se activa si hay variables de entorno) ──
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
USAR_SUPABASE = bool(SUPABASE_URL and SUPABASE_KEY)
TABLA = "mud_saves"

def _sb_headers():
    return {
        "apikey":        SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type":  "application/json",
        "Prefer":        "return=representation",
    }

async def _sb_get(usuario: str) -> dict | None:
    """Lee una fila de Supabase. Devuelve el dict o None si no existe."""
    url = f"{SUPABASE_URL}/rest/v1/{TABLA}?usuario=eq.{usuario}&select=*"
    async with aiohttp.ClientSession() as s:
        async with s.get(url, headers=_sb_headers()) as r:
            if r.status == 200:
                rows = await r.json()
                return rows[0] if rows else None
    return None

async def _sb_upsert(row: dict):
    """Inserta o actualiza una fila en Supabase."""
    url = f"{SUPABASE_URL}/rest/v1/{TABLA}"
    headers = {**_sb_headers(), "Prefer": "resolution=merge-duplicates,return=minimal"}
    async with aiohttp.ClientSession() as s:
        await s.post(url, headers=headers, json=row)


async def get_leaderboard_async(limit: int = 20) -> list:
    """Ranking global ordenado por nivel desc."""
    if USAR_SUPABASE:
        # PostgREST: traemos todos y ordenamos en Python
        # (ordenar por campo JSONB anidado no es directo en PostgREST)
        url = f"{SUPABASE_URL}/rest/v1/{TABLA}?select=usuario,data&limit=200"
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(url, headers=_sb_headers()) as r:
                    if r.status == 200:
                        rows = await r.json()
                        result = []
                        for row in rows:
                            d = row.get("data") or {}
                            if isinstance(d, str):
                                try:
                                    d = json.loads(d)
                                except Exception:
                                    continue
                            if not d.get("nombre"):
                                continue
                            result.append({
                                "nombre":  d.get("nombre", row["usuario"]),
                                "clase":   d.get("personaje", {}).get("nombreClase", "?"),
                                "nivel":   int(d.get("nivel", 1)),
                                "usuario": row["usuario"],
                            })
                        result.sort(key=lambda x: x["nivel"], reverse=True)
                        return result[:limit]
                    else:
                        print(f"[LB] Supabase error {r.status}")
        except Exception as e:
            print(f"[LB] Error: {e}")
    # Fallback: ficheros locales
    result = []
    if os.path.isdir(SAVES_DIR):
        for fname in os.listdir(SAVES_DIR):
            if not fname.endswith(".json"):
                continue
            try:
                with open(os.path.join(SAVES_DIR, fname)) as f:
                    save_raw = json.load(f)
                d = save_raw.get("data", save_raw) or {}
                if not d.get("nombre"):
                    continue
                result.append({
                    "nombre":  d.get("nombre", fname),
                    "clase":   d.get("personaje", {}).get("nombreClase", "?"),
                    "nivel":   int(d.get("nivel", 1)),
                    "usuario": save_raw.get("usuario", fname),
                })
            except Exception:
                pass
    result.sort(key=lambda x: x["nivel"], reverse=True)
    return result[:limit]


async def broadcast_leaderboard():
    """Envía el leaderboard a todos los jugadores conectados."""
    lb = await get_leaderboard_async()
    payload = json.dumps({"type": "leaderboard", "ranking": lb})
    for p in jugadores_conectados:
        try:
            await p.ws.send_json({"type": "leaderboard", "ranking": lb})
        except Exception:
            pass

# ============================================================
# DATOS — CLASES COMPLETAS
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
# ENEMIGOS COMPLETOS
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
SALA_RESPAWN   = 33   # Oasis — sala segura, no hay enemigos
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
        self.salas_limpias    = set()   # salas donde el jugador ya derrotó a los enemigos
        self.duelo_pendiente  = None    # {"retador": Player, "monedas": int} — duelo recibido pendiente

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
        """Envía stats completas al cliente WebSocket del jugador."""
        if not self.personaje:
            return
        p = self.personaje
        payload = {
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
            "inventario":    self.inventario,
        }
        try:
            await self.ws.send_json(payload)
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
    """Empuja stats actualizadas al jugador (mismo WebSocket que usa para jugar)."""
    if not player.personaje:
        return
    await player.send_status()  # reutiliza send_status que ya tiene todo


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
    # Límite de seguridad
    mensaje = mensaje[:300]
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
    # Actualizar leaderboard global para todos
    asyncio.create_task(broadcast_leaderboard())


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
        await player.send_status()  # actualizar mochila y monedas en tiempo real


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
        await player.send_status()
        return True

    elif iid == "pocion_danio":
        if player.buff_danio:
            await player.send("  Buff ya activo.")
            return False
        player.buff_danio = True
        player.inventario[iid] -= 1
        msg = f"  {player.nombre} usa Pocion de Danio +30% este combate!"
        await broadcast_sala(combate.sala_id if combate else player.sala_id, msg)
        await player.send_status()
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
        await player.send_status()
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

    # Supabase guarda en columna "data", fichero local puede ser plano
    datos = row.get("data") or {}
    if not datos:
        datos = row  # fallback: fichero plano

    # Si data está vacío (cuenta recién creada sin personaje), usar defaults
    if not datos.get("personaje"):
        raise ValueError(f"Cuenta sin personaje inicializado: {usuario}")

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
    if getattr(player, 'combate', None) and player.combate and getattr(player.combate, 'estado', None) != EstadoCombate.FINALIZADO:
        await player.send("  No puedes huir del combate!")
        return
    sala_actual = SALAS.get(player.sala_id)
    if not sala_actual:
        return

    # ── Bloqueo por monstruos ────────────────────────────────
    tiene_enemigos = "bioma" in sala_actual or bool(sala_actual.get("encuentros"))
    if tiene_enemigos and player.sala_id not in player.salas_limpias:
        await player.send(
            "  ¡Hay enemigos bloqueando el paso!\n"
            "  Derrota a todos los monstruos de esta sala para poder avanzar.\n"
            "  Escribe 'atacar' para iniciar el combate."
        )
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

async def pedir_accion(player: Player, combate: Combate):
    """
    Pide acción al jugador. Si eres el único en la sala, resuelve inmediatamente.
    """
    if player.personaje["vidaActual"] <= 0:
        combate.acciones[player.id] = "3"
        return

    await player.send(
        " 1-Atacar 2-Especial 3-Pasar 4-Objeto\n"
        " decir <msg> | g <msg>"
    )

    while True:
        raw = await player.recv()
        if raw is None:                     # desconexión
            combate.acciones[player.id] = "3"
            return

        accion = raw.strip()
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
            await player.send(" Qué objeto usar? (vida / dano / gema):")
            n = await player.recv()
            if n and n.strip():
                await usar_item(player, n.strip(), combate=combate)
            await player.send(" 1-Atacar 2-Especial 3-Pasar 4-Objeto")
            continue

        if accion in ("1", "2", "3"):
            combate.acciones[player.id] = accion
            await broadcast_sala(combate.sala_id, f" {player.nombre} ha elegido.", excluir=player)

            # Si eres el único jugador → resolver inmediatamente
            if len(combate.jugadores_vivos()) <= 1:
                await player.send(" Eres el único jugador. Resolviendo turno...")
                asyncio.create_task(resolver_accion(player, accion, combate))

            return

        await player.send(" Elige 1, 2, 3 o 4.")



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
    enemigos_info = []
    for e in combate.enemigos:
        await broadcast_sala(sala_id, f"  {e['nombre']}  HP:{e['vida_actual']}/{e['vidaMax']}  [{e.get('tier','?')}]")
        enemigos_info.append({"nombre": e["nombre"], "hp": e["vida_actual"], "hpMax": e["vidaMax"], "tier": e.get("tier","?")})

    # Enviar popup de combate a todos los jugadores de la sala
    for p in jug:
        try:
            await p.ws.send_json({"type": "combat_start", "enemigos": enemigos_info})
        except Exception:
            pass

    asyncio.create_task(loop_combate(combate))

    async def loop_combate(combate: Combate):
    sala_id = combate.sala_id
    while combate.enemigos_vivos() and combate.jugadores_vivos():
        combate.turno += 1
        combate.acciones = {}
        combate.estado = EstadoCombate.ESPERANDO_ACCIONES

        # Regen mana
        for p in combate.jugadores_vivos():
            p.personaje["manaActual"] = min(
                p.personaje["manaActual"] + p.personaje.get("manaTurno", 0),
                p.personaje["manaMax"]
            )

        await broadcast_sala(sala_id, f"\n{'-'*52}\n TURNO {combate.turno}\n{'-'*52}")
        for e in combate.enemigos_vivos():
            await broadcast_sala(sala_id, f" {e['nombre']} HP:{e['vida_actual']}/{e['vidaMax']}")
        for p in combate.jugadores_vivos():
            await p.send(
                f" TU [{p.personaje['nombreClase']}] "
                f"HP:{p.personaje['vidaActual']}/{p.personaje['vidaMax']} "
                f"Mana:{p.personaje['manaActual']}/{p.personaje['manaMax']}"
            )

        await broadcast_sala(sala_id, " Esperando acciones de todos...")

        # FIX: Si solo hay 1 jugador, no esperamos a nadie más
        vivos = combate.jugadores_vivos()
        if len(vivos) == 1:
            await pedir_accion(vivos[0], combate)
        else:
            await asyncio.gather(*[
                asyncio.create_task(pedir_accion(p, combate))
                for p in vivos
            ])

        # Resolución
        combate.estado = EstadoCombate.RESOLVIENDO
        await broadcast_sala(sala_id, "\n --- RESOLUCION ---")
        for p in list(combate.jugadores_vivos()):
            await resolver_accion(p, combate.acciones.get(p.id, "3"), combate)
            if not combate.enemigos_vivos():
                break

        # Turno enemigos
        if combate.enemigos_vivos() and combate.jugadores_vivos():
            combate.estado = EstadoCombate.TURNO_ENEMIGO
            await broadcast_sala(sala_id, "\n --- TURNO ENEMIGOS ---")
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
                        f" {e['nombre']} golpea a {obj.nombre} -{d} "
                        f"({obj.personaje['vidaActual']}/{obj.personaje['vidaMax']})"
                    )

        # Detectar muertes
        for p in combate.jugadores:
            if p.personaje["vidaActual"] <= 0 and not p.muerto:
                await broadcast_sala(sala_id, f" {p.nombre} ha caido!")
                asyncio.create_task(respawn(p))

        # Actualizar stats
        for p in combate.jugadores:
            await p.send_status()

    # ── FIN DEL COMBATE ──
    combate.estado = EstadoCombate.FINALIZADO

    # Cerrar popup
    for p in combate.jugadores:
        try:
            await p.ws.send_json({"type": "combat_end"})
        except Exception:
            pass

    if combate.enemigos_vivos():
        await broadcast_sala(sala_id, "\n DERROTA.")
    else:
        await broadcast_sala(sala_id, "\n VICTORIA!")
        xp = sum(xp_de_tier(e.get("tier", "Base")) for e in combate.enemigos)
        await broadcast_sala(sala_id, f" {xp} XP para cada superviviente.")
        for p in combate.jugadores_vivos():
            await dar_xp(p, xp)
            p.personaje["vidaActual"] = min(p.personaje["vidaActual"] + 20, p.personaje["vidaMax"])
            p.salas_limpias.add(sala_id)
            await p.send_status()
        await broadcast_sala(sala_id, " +20 HP a cada superviviente.")
        await broadcast_sala(sala_id, " El camino está despejado. Puedes avanzar.")

    # Limpiar buffs
    for p in combate.jugadores:
        if p.buff_danio:
            p.buff_danio = False
            asyncio.create_task(p.send(" Pocion de Danio terminada."))

    # Limpiar combate
    del combates_activos[sala_id]
    for p in combate.jugadores:
        p.combate = None

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

                await broadcast_sala(sala_id, " Esperando acciones de todos...")

        # Si solo hay 1 jugador, no esperamos a nadie más
        vivos = combate.jugadores_vivos()
        if len(vivos) == 1:
            await pedir_accion(vivos[0], combate)
        else:
            await asyncio.gather(*[
                asyncio.create_task(pedir_accion(p, combate))
                for p in vivos
            ])

    while True:
        raw = await player.recv()
        if raw is None:                     # desconexión
            combate.acciones[player.id] = "3"
            return

        accion = raw.strip()
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
            await player.send(" Qué objeto usar? (vida / dano / gema):")
            n = await player.recv()
            if n and n.strip():
                await usar_item(player, n.strip(), combate=combate)
            await player.send(" 1-Atacar 2-Especial 3-Pasar 4-Objeto")
            continue

        if accion in ("1", "2", "3"):
            combate.acciones[player.id] = accion
            await broadcast_sala(combate.sala_id, f" {player.nombre} ha elegido.", excluir=player)

            # FIX: Si eres el único jugador → resolver inmediatamente
            if len(combate.jugadores_vivos()) <= 1:
                await player.send(" Eres el único jugador. Resolviendo turno...")
                asyncio.create_task(resolver_accion(player, accion, combate))

            return

        await player.send(" Elige 1, 2, 3 o 4.")
      
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

        # Actualizar stats en tiempo real (directo, sin create_task para evitar retrasos)
        for p in combate.jugadores:
            await p.send_status()

        # ── FIN DEL COMBATE ──
    combate.estado = EstadoCombate.FINALIZADO

    # Cerrar popup de combate en todos los jugadores
    for p in combate.jugadores:
        try:
            await p.ws.send_json({"type": "combat_end"})
        except Exception:
            pass

    if combate.enemigos_vivos():
        await broadcast_sala(sala_id, "\n DERROTA.")
    else:
        await broadcast_sala(sala_id, "\n VICTORIA!")
        xp = sum(xp_de_tier(e.get("tier", "Base")) for e in combate.enemigos)
        await broadcast_sala(sala_id, f" {xp} XP para cada superviviente.")
        for p in combate.jugadores_vivos():
            await dar_xp(p, xp)
            p.personaje["vidaActual"] = min(p.personaje["vidaActual"] + 20, p.personaje["vidaMax"])
            p.salas_limpias.add(sala_id)
            await p.send_status()
        await broadcast_sala(sala_id, " +20 HP a cada superviviente.")
        await broadcast_sala(sala_id, " El camino está despejado. Puedes avanzar.")

    # Limpiar buffs
    for p in combate.jugadores:
        if p.buff_danio:
            p.buff_danio = False
            asyncio.create_task(p.send(" Pocion de Danio terminada."))

    # Limpiar combate
    del combates_activos[sala_id]
    for p in combate.jugadores:
        p.combate = None   # ← Esta línea debe tener la misma indentación que el "for" de arriba


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

# ============================================================
# SISTEMA DE DUELOS (PvP)
# ============================================================

async def cmd_duelo(player: Player, args: str):
    """duelo <nombre> [monedas] — Reta a otro jugador."""
    partes = args.split()
    if not partes:
        await player.send("  Uso: duelo <nombre> [monedas a apostar]")
        return

    nombre_obj = partes[0]
    monedas_apuesta = 0
    if len(partes) >= 2:
        if not partes[1].isdigit():
            await player.send("  Las monedas deben ser un número.")
            return
        monedas_apuesta = int(partes[1])

    objetivo = next(
        (p for p in jugadores_conectados if p.nombre and p.nombre.lower() == nombre_obj.lower()),
        None
    )
    if not objetivo:
        await player.send(f"  Jugador '{nombre_obj}' no encontrado.")
        return
    if objetivo == player:
        await player.send("  No puedes retarte a ti mismo.")
        return
    if objetivo.duelo_pendiente:
        await player.send(f"  {objetivo.nombre} ya tiene un duelo pendiente.")
        return
    if player.combate:
        await player.send("  No puedes retar a duelo durante un combate.")
        return
    if monedas_apuesta > player.monedas:
        await player.send(f"  No tienes suficientes monedas (tienes {player.monedas}).")
        return

    objetivo.duelo_pendiente = {"retador": player, "monedas": monedas_apuesta}

    apuesta_txt = f" — Apuesta: {monedas_apuesta} 💰" if monedas_apuesta else ""
    await player.send(f"  Reto enviado a {objetivo.nombre}{apuesta_txt}. Esperando respuesta...")
    await objetivo.send(
        f"\n  ⚔ {player.nombre} te reta a duelo{apuesta_txt}.\n"
        f"  Escribe 'aceptar_duelo' o 'rechazar_duelo'."
    )
    # Popup visual para el retado
    try:
        await objetivo.ws.send_json({
            "type":    "pvp_challenge",
            "retador": player.nombre,
            "monedas": monedas_apuesta,
        })
    except Exception:
        pass


async def cmd_aceptar_duelo(player: Player):
    if not player.duelo_pendiente:
        await player.send("  No tienes ningún duelo pendiente.")
        return

    retador   = player.duelo_pendiente["retador"]
    monedas   = player.duelo_pendiente["monedas"]
    player.duelo_pendiente = None

    if retador not in jugadores_conectados:
        await player.send("  El retador ya no está conectado.")
        return
    if player.combate or retador.combate:
        await player.send("  Uno de los jugadores está en combate.")
        return
    if monedas > player.monedas:
        await player.send(f"  No tienes suficientes monedas para la apuesta ({monedas} necesarias).")
        await retador.send(f"  {player.nombre} no tiene monedas suficientes. Duelo cancelado.")
        return
    if monedas > retador.monedas:
        await player.send(f"  {retador.nombre} ya no tiene monedas suficientes. Duelo cancelado.")
        return

    await player.send(f"  ¡Duelo aceptado!")
    await retador.send(f"  {player.nombre} aceptó el duelo. ¡Prepárate!")
    asyncio.create_task(loop_duelo(retador, player, monedas))


async def cmd_rechazar_duelo(player: Player):
    if not player.duelo_pendiente:
        await player.send("  No tienes ningún duelo pendiente.")
        return
    retador = player.duelo_pendiente["retador"]
    player.duelo_pendiente = None
    await player.send(f"  Rechazaste el duelo de {retador.nombre}.")
    await retador.send(f"  {player.nombre} rechazó tu duelo.")


async def loop_duelo(p1: Player, p2: Player, monedas_apuesta: int):
    """Combate PvP 1v1 entre dos jugadores."""
    p1.combate = True   # marcador temporal para bloquear otros combates
    p2.combate = True

    await p1.send(f"\n{'='*52}\n  ⚔ DUELO: {p1.nombre} vs {p2.nombre}\n{'='*52}")
    await p2.send(f"\n{'='*52}\n  ⚔ DUELO: {p1.nombre} vs {p2.nombre}\n{'='*52}")
    if monedas_apuesta:
        await p1.send(f"  Apuesta: {monedas_apuesta} 💰 por jugador")
        await p2.send(f"  Apuesta: {monedas_apuesta} 💰 por jugador")

    # Copias de stats para el duelo (no modificamos el personaje original durante el combate)
    hp1 = p1.personaje["vidaActual"]
    hp2 = p2.personaje["vidaActual"]
    turno = 0
    ganador = None
    perdedor = None

    while hp1 > 0 and hp2 > 0:
        turno += 1
        await p1.send(f"\n  --- TURNO {turno} ---  TÚ: {hp1} HP  |  {p2.nombre}: {hp2} HP")
        await p2.send(f"\n  --- TURNO {turno} ---  TÚ: {hp2} HP  |  {p1.nombre}: {hp1} HP")

        # Regen mana
        p1.personaje["manaActual"] = min(p1.personaje["manaActual"] + p1.personaje.get("manaTurno", 0), p1.personaje["manaMax"])
        p2.personaje["manaActual"] = min(p2.personaje["manaActual"] + p2.personaje.get("manaTurno", 0), p2.personaje["manaMax"])

        await p1.send("  1-Atacar  2-Especial  3-Pasar")
        await p2.send("  1-Atacar  2-Especial  3-Pasar")

        # Ambos eligen en paralelo
        acc1, acc2 = "3", "3"
        async def elegir(p):
            while True:
                r = await p.recv()
                if r is None:
                    return "3"
                r = r.strip()
                if r in ("1", "2", "3"):
                    return r
                await p.send("  Elige 1, 2 o 3.")
        acc1, acc2 = await asyncio.gather(elegir(p1), elegir(p2))

        # Resolver acción de p1 sobre p2
        async def aplicar(atacante, defensor, accion, hp_def):
            p = atacante.personaje
            if accion == "1":
                num = ataques_por_turno(p.get("ataquesTurno", 1))
                for _ in range(num):
                    d = calcular_danio(p["danioBase"])
                    hp_def = max(0, hp_def - d)
                    await atacante.send(f"  Atacas a {defensor.nombre} -{d} HP  ({hp_def} HP restante)")
                    await defensor.send(f"  {atacante.nombre} te ataca -{d} HP  ({hp_def} HP restante)")
            elif accion == "2":
                costo = p.get("costoEspecial", 0)
                if p["manaActual"] >= costo:
                    p["manaActual"] -= costo
                    d = calcular_danio(p.get("danioEspecial", p["danioBase"]))
                    hp_def = max(0, hp_def - d)
                    await atacante.send(f"  Usas especial en {defensor.nombre} -{d} HP  ({hp_def} HP restante)")
                    await defensor.send(f"  {atacante.nombre} usa especial -{d} HP  ({hp_def} HP restante)")
                else:
                    await atacante.send("  Sin mana. Pasas el turno.")
            elif accion == "3":
                await atacante.send("  Pasas el turno.")
            return hp_def

        hp2 = await aplicar(p1, p2, acc1, hp2)
        if hp2 > 0:
            hp1 = await aplicar(p2, p1, acc2, hp1)

    # Determinar ganador
    if hp1 <= 0 and hp2 <= 0:
        await p1.send("  ¡Empate!")
        await p2.send("  ¡Empate!")
    elif hp2 <= 0:
        ganador, perdedor = p1, p2
    else:
        ganador, perdedor = p2, p1

    if ganador:
        # Pérdida de XP: 15% del XP actual
        xp_perdido = max(10, int(perdedor.xp * 0.15))
        perdedor.xp = max(0, perdedor.xp - xp_perdido)

        # Transferir monedas apostadas
        if monedas_apuesta:
            monedas_reales = min(monedas_apuesta, perdedor.monedas)
            perdedor.monedas  -= monedas_reales
            ganador.monedas   += monedas_reales

        await ganador.send(
            f"\n  🏆 ¡VICTORIA!\n"
            f"  Derrotaste a {perdedor.nombre}."
            + (f"\n  +{monedas_apuesta} 💰 ganadas." if monedas_apuesta else "")
        )
        await perdedor.send(
            f"\n  💀 DERROTA — {ganador.nombre} te venció.\n"
            f"  -{xp_perdido} XP  (te quedan {perdedor.xp})"
            + (f"\n  -{monedas_apuesta} 💰 perdidas." if monedas_apuesta else "")
        )
        await broadcast_todos(f"  ⚔ {ganador.nombre} derrotó a {perdedor.nombre} en duelo.")

        # Actualizar HP real
        ganador.personaje["vidaActual"]  = max(1, hp1 if ganador == p1 else hp2)
        perdedor.personaje["vidaActual"] = 1

    # Liberar marcador de combate
    p1.combate = None
    p2.combate = None
    await notify_web_session(p1)
    await notify_web_session(p2)


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

    elif ac == "duelo":
        await cmd_duelo(player, cmd[len(ac):].strip())

    elif ac == "aceptar_duelo":
        await cmd_aceptar_duelo(player)

    elif ac == "rechazar_duelo":
        await cmd_rechazar_duelo(player)

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
            "           ⚠ Derrota los monstruos de la sala para avanzar\n"
            "  ACCION:   mirar | atacar\n"
            "  TIENDA:   tienda | mochila | usar <objeto>\n"
            "  HOSPITAL: hospital  (solo en salas con 🏥)\n"
            "  INFO:     stats | nivel | jugadores\n"
            "  CUENTA:   guardar\n"
            "  GRUPO:    invitar <nombre> | aceptar | rechazar\n"
            "            grupo | salirgrupo | gc <msg>\n"
            "  PvP:      duelo <nombre> [monedas] | aceptar_duelo | rechazar_duelo\n"
            "  CHAT:     decir <msg> (sala) | g <msg> (global)"
        )

    else:
        await player.send(f"  Desconocido: '{cmd}'. Escribe 'ayuda'.")


async def handle_game_ws(ws, usuario: str):
    player = Player(ws)
    player.usuario = usuario

    if len(jugadores_conectados) >= MAX_JUGADORES:
        await player.send("Servidor lleno (máx 5 jugadores).")
        await ws.close()
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
        print(f"[LOGIN] Cargando cuenta para {usuario}...")

        await cargar_cuenta_async(player, usuario)

        print(f"[LOGIN] Cuenta cargada OK: {usuario} - Nivel {player.nivel}")

        await player.send(
            f"\n Bienvenido de vuelta, {player.nombre}!\n"
            f" Nivel {player.nivel}  XP:{player.xp}/{XP_POR_NIVEL}  Monedas:{player.monedas}\n"
            f" HP:{player.personaje['vidaActual']}/{player.personaje['vidaMax']} "
            f"Mana:{player.personaje['manaActual']}/{player.personaje['manaMax']}"
        )

        await player.send_status()

        # Leaderboard
        lb = await get_leaderboard_async()
        try:
            await player.ws.send_json({"type": "leaderboard", "ranking": lb})
        except:
            pass

        await broadcast_todos(f"\n {player.nombre} se unió al dungeon!")
        await broadcast_players_to_web()
        await describir_sala(player)

        # Bucle principal
        while True:
            if getattr(player, 'combate', None) and player.combate and getattr(player.combate, 'estado', None) != EstadoCombate.FINALIZADO:
                await asyncio.sleep(0.05)
                continue

            raw = await player.recv()
            if raw is None:
                break
            if not raw.strip():
                continue

            await procesar_comando(player, raw.strip())

    except Exception as e:
        print(f"[GAME ERROR] Usuario {usuario}: {e}")
        import traceback
        traceback.print_exc()
        try:
            await player.send(f"\n Error al cargar tu cuenta:\n {str(e)}\n\nContacta con el administrador.")
        except:
            pass

    finally:
        if player.usuario and player.personaje:
            await guardar_cuenta_async(player)

        if player.grupo:
            asyncio.create_task(cmd_salirgrupo(player))

        for p in jugadores_conectados[:]:
            if p.invitacion_de == player:
                p.invitacion_de = None

        rt.cancel()

        if player in jugadores_conectados:
            jugadores_conectados.remove(player)

        if player.nombre:
            await broadcast_todos(f"\n {player.nombre} abandonó el dungeon.")
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
                "inventario": player_online.inventario,
                "online": True,
            }
        else:
            # Cargar desde Supabase o fichero local
            if USAR_SUPABASE:
                row = await _sb_get(usuario)
                save_raw = row or {}
                save = save_raw.get("data", save_raw) or {}
            else:
                save_raw = _leer_fichero(usuario) or {}
                save = save_raw.get("data", save_raw) or {}
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
                "inventario": save.get("inventario", {}),
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


# ============================================================
# HTML EMBEBIDO
# ============================================================

def get_html() -> str:
    return r"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>The Return to Highdown</title>
<style>
*{margin:0;padding:0;box-sizing:border-box;}
:root{
  --bg:#0d0d0d;--bg2:#141414;--bg3:#1c1c1c;--bg4:#222;
  --border:#272727;--border2:#333;
  --gold:#c9a84c;--gold2:#e8c55c;
  --green:#43a047;--red:#e53935;--red2:#ff1744;
  --blue:#42a5f5;--mana:#5c6bc0;--purple:#8e44ad;
  --orange:#f39c12;--teal:#00bcd4;
  --text:#d0d0d0;--dim:#4a4a4a;--dim2:#222;
}
body{background:var(--bg);color:var(--text);font-family:"Courier New",monospace;
     height:100vh;overflow:hidden;display:flex;flex-direction:column;}

/* LOGIN */
#lo{position:fixed;inset:0;background:rgba(0,0,0,.94);display:flex;
    align-items:center;justify-content:center;z-index:999;}
#lb{background:var(--bg2);border:1px solid var(--gold);border-radius:8px;
    padding:28px 36px;text-align:center;min-width:290px;max-width:360px;width:90%;}
#lb h1{color:var(--gold);font-size:17px;margin-bottom:3px;}
#lb p{color:var(--dim);font-size:10px;margin-bottom:13px;}
.li{width:100%;background:var(--bg3);border:1px solid var(--border);color:var(--text);
    padding:7px 10px;font-family:monospace;font-size:12px;border-radius:3px;
    outline:none;margin-bottom:6px;transition:border-color .15s;}
.li:focus{border-color:var(--gold);}
.li::placeholder{color:var(--dim);}
.abtn{width:100%;background:var(--gold);border:none;color:#000;padding:8px;
      font-weight:bold;font-size:12px;cursor:pointer;border-radius:3px;font-family:monospace;}
.abtn:hover{background:var(--gold2);}
#lerr{color:var(--red);font-size:10px;margin-top:6px;min-height:14px;}
.tabs{display:flex;gap:4px;margin-bottom:10px;}
.tab{flex:1;padding:4px;border:1px solid var(--border);border-radius:3px;cursor:pointer;
     font-family:monospace;font-size:10px;color:var(--dim);background:var(--bg3);}
.tab.active{background:var(--gold);color:#000;border-color:var(--gold);}
#reg-p{display:none;}

/* TOPBAR */
#topbar{background:var(--bg2);border-bottom:1px solid var(--border);
        padding:3px 10px;display:flex;align-items:center;gap:8px;flex-shrink:0;height:26px;}
#tb-title{color:var(--gold);font-weight:bold;font-size:11px;}
#tb-player{color:var(--text);font-size:10px;}
#tb-player span{color:var(--gold);}
#cdot{margin-left:auto;width:6px;height:6px;border-radius:50%;background:var(--red);}
#cdot.on{background:var(--green);}

/* MAIN GRID */
#app{flex:1;display:grid;overflow:hidden;
     grid-template-columns:155px 1fr 195px;
     grid-template-rows:1fr 38px;
     gap:1px;background:var(--border);}

/* LEFT */
#left{background:var(--bg2);grid-column:1;grid-row:1;
      display:flex;flex-direction:column;overflow:hidden;}
#stats-pane{padding:7px 8px;overflow-y:auto;flex:1;min-height:0;}
.sp-name{font-size:12px;color:var(--gold);font-weight:bold;text-align:center;
         white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.sp-cls{font-size:9px;color:var(--dim);text-align:center;margin-bottom:5px;}
.sh{color:var(--gold);font-size:9px;text-transform:uppercase;letter-spacing:1px;
    border-bottom:1px solid var(--border);padding-bottom:2px;margin:5px 0 3px;}
.lvr{display:flex;justify-content:space-between;align-items:center;
     font-size:9px;margin-bottom:3px;}
.lvb{background:var(--gold);color:#000;padding:1px 5px;border-radius:5px;
     font-weight:bold;font-size:9px;}
.bl{display:flex;justify-content:space-between;font-size:9px;margin-bottom:1px;}
.bl-n{color:var(--dim);}
.bw{width:100%;height:8px;background:var(--bg3);border-radius:4px;
    overflow:hidden;border:1px solid var(--border);margin-bottom:4px;}
.bf{height:100%;border-radius:4px;transition:width .35s,background .35s;}
.bf-hp{background:var(--red);}
.bf-mp{background:var(--mana);}
.xw{width:100%;height:3px;background:var(--bg3);border-radius:2px;
    overflow:hidden;margin-bottom:4px;}
.bf-xp{background:var(--purple);}
.sr{display:flex;justify-content:space-between;padding:2px 0;
    border-bottom:1px solid var(--dim2);font-size:9px;}
.sr:last-child{border-bottom:none;}
.sr-l{color:var(--dim);}
.sr-v{font-weight:bold;}

/* Mochila */
#bag-pane{padding:5px 8px;border-top:1px solid var(--border);flex-shrink:0;}
.bag-title{color:var(--gold);font-size:9px;text-transform:uppercase;letter-spacing:1px;margin-bottom:3px;}
.bag-coins{font-size:11px;color:var(--gold);margin-bottom:3px;}
.bag-item{font-size:9px;color:var(--text);padding:1px 0;}
.bag-empty{font-size:9px;color:var(--dim);}

/* Servicios */
#services-pane{padding:4px 8px;border-top:1px solid var(--border);
               flex-shrink:0;display:flex;gap:3px;}
.svc-btn{flex:1;background:var(--bg3);border:1px solid var(--border);
         color:var(--dim);padding:3px 2px;font-size:9px;cursor:pointer;
         border-radius:3px;font-family:monospace;text-align:center;
         display:none;transition:all .15s;}
.svc-btn.visible{display:block;}
.svc-btn.hosp{border-color:#1a4a1a;color:var(--green);}
.svc-btn.shop{border-color:#4a3a0a;color:var(--orange);}

/* CENTER */
#center{background:var(--bg);grid-column:2;grid-row:1;
        display:flex;flex-direction:column;overflow:hidden;position:relative;}
#minimap-btn{position:absolute;top:6px;right:6px;width:85px;height:60px;
             background:var(--bg2);border:1px solid var(--orange);
             border-radius:3px;cursor:pointer;z-index:10;overflow:hidden;}
#minimap-btn:hover{border-color:var(--gold2);}
#minimap-label{position:absolute;bottom:2px;left:0;right:0;text-align:center;
               font-size:7px;color:var(--orange);pointer-events:none;}
#glog{flex:1;overflow-y:auto;padding:7px 10px;font-size:12px;line-height:1.6;padding-right:96px;}
#glog::-webkit-scrollbar{width:3px;}
#glog::-webkit-scrollbar-thumb{background:var(--border);}
.gm{margin-bottom:1px;white-space:pre-wrap;word-break:break-word;}
.gg{color:var(--text);}
.gp2{color:var(--blue);}
.gc{color:#e67e22;}
.gv{color:var(--gold);font-weight:bold;}
.gd{color:var(--red);}
.gi{color:var(--teal);}
.gs{color:var(--dim);font-style:italic;}
.gl{color:var(--gold);background:#1a1300;border:1px solid var(--gold);
    padding:2px 5px;border-radius:2px;display:inline-block;margin:2px 0;}

/* RIGHT */
#right{background:var(--bg2);grid-column:3;grid-row:1;
       display:flex;flex-direction:column;overflow:hidden;}

/* Leaderboard */
#lb-pane{flex:0 0 auto;max-height:45%;display:flex;flex-direction:column;overflow:hidden;
         border-bottom:1px solid var(--border);}
#lb-hdr{padding:4px 8px;font-size:9px;color:var(--gold);text-transform:uppercase;
        letter-spacing:1px;flex-shrink:0;border-bottom:1px solid var(--border);}
#lb-list{flex:1;overflow-y:auto;padding:3px;}
#lb-list::-webkit-scrollbar{width:3px;}
.lbi{display:flex;align-items:center;gap:4px;padding:2px 4px;
     border-bottom:1px solid var(--dim2);font-size:9px;}
.lbi:last-child{border-bottom:none;}
.lbi-pos{color:var(--dim);width:14px;flex-shrink:0;text-align:right;}
.lbi-pos.gold{color:#ffd700;font-weight:bold;}
.lbi-pos.silver{color:#c0c0c0;font-weight:bold;}
.lbi-pos.bronze{color:#cd7f32;font-weight:bold;}
.lbi-name{color:var(--text);flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
.lbi-name.me{color:var(--gold);font-weight:bold;}
.lbi-info{color:var(--dim);flex-shrink:0;font-size:8px;}
.lbi-lvl{color:var(--green);font-weight:bold;font-size:9px;flex-shrink:0;}

/* Chat */
#chat-pane{flex:1;display:flex;flex-direction:column;overflow:hidden;}
#chat-tabs{display:flex;padding:3px 5px;gap:2px;border-bottom:1px solid var(--border);flex-shrink:0;}
.ctab{flex:1;background:none;border:1px solid var(--border);color:var(--dim);
      padding:2px 3px;border-radius:2px;cursor:pointer;font-size:9px;font-family:monospace;}
.ctab.cs{background:#0d1f0d;color:var(--green);border-color:var(--green);}
.ctab.cg{background:#1f1500;color:var(--orange);border-color:var(--orange);}
.ctab.cgr{background:#0d0d1f;color:var(--mana);border-color:var(--mana);}
#chat-log{flex:1;overflow-y:auto;padding:3px 6px;font-size:10px;line-height:1.5;}
#chat-log::-webkit-scrollbar{width:3px;}
#chat-log::-webkit-scrollbar-thumb{background:var(--border);}
.cm{display:flex;gap:3px;align-items:baseline;margin-bottom:1px;}
.cm-t{color:var(--dim);font-size:8px;flex-shrink:0;}
.cm-n{font-weight:bold;font-size:9px;flex-shrink:0;}
.cm-tx{color:var(--text);font-size:10px;word-break:break-word;}
.cn-s{color:var(--green);}
.cn-g{color:var(--orange);}
.cn-gr{color:var(--mana);}
#chat-in-row{display:flex;gap:3px;padding:4px 5px;border-top:1px solid var(--border);flex-shrink:0;}
#chat-in{flex:1;background:var(--bg3);border:1px solid var(--border);color:var(--text);
         padding:3px 6px;font-family:monospace;font-size:10px;border-radius:3px;outline:none;}
#chat-in:focus{border-color:var(--gold);}
#chat-in:disabled{opacity:.4;}
#chat-send{background:var(--gold);border:none;color:#000;padding:3px 7px;
           font-weight:bold;cursor:pointer;border-radius:3px;font-family:monospace;font-size:10px;}
#chat-send:disabled{opacity:.4;cursor:default;}

/* BOTTOM CONTROLS */
#controls{background:var(--bg2);grid-column:1/4;grid-row:2;
          display:flex;align-items:center;gap:2px;padding:0 6px;
          border-top:1px solid var(--border);}
.cb{background:var(--bg3);border:1px solid var(--border);color:var(--dim);
    padding:3px 6px;font-size:9px;cursor:pointer;border-radius:3px;
    font-family:monospace;white-space:nowrap;flex-shrink:0;}
.cb:hover{color:var(--text);border-color:var(--gold);}
.cb.dir{border-color:#1a2a3a;color:var(--blue);}
.cb.dir:hover{background:#08101a;}
.cb.atk{border-color:#1a3a1a;color:var(--green);}
.cb.atk:hover{background:#081408;}
.cb.pvp{border-color:#3a1a1a;color:var(--red);}
.cb.pvp:hover{background:#180808;}
.cb.gold-btn{background:var(--gold);color:#000;border-color:var(--gold);font-weight:bold;margin-left:auto;}
.cb.gold-btn:hover{background:var(--gold2);}
.cb-sep{width:1px;height:16px;background:var(--border);flex-shrink:0;margin:0 1px;}
#input-bar{display:flex;gap:2px;flex:1;min-width:0;max-width:220px;margin:0 4px;}
#cmd{flex:1;background:var(--bg3);border:1px solid var(--border);color:var(--text);
     padding:3px 7px;font-family:"Courier New",monospace;font-size:11px;
     border-radius:3px;outline:none;min-width:0;}
#cmd:focus{border-color:var(--gold);}
#cmd:disabled{opacity:.4;}
#cmd::placeholder{color:var(--dim);}
#sbtn{background:var(--gold);border:none;color:#000;padding:3px 7px;
      font-weight:bold;cursor:pointer;border-radius:3px;font-family:monospace;font-size:11px;}
#sbtn:disabled{opacity:.4;cursor:default;}

/* MAP MODAL */
#map-modal{display:none;position:fixed;inset:0;background:rgba(0,0,0,.88);
           z-index:500;align-items:center;justify-content:center;}
#map-modal.open{display:flex;}
#map-inner{background:var(--bg2);border:1px solid var(--gold);border-radius:6px;
           padding:10px;position:relative;}
#map-close{position:absolute;top:5px;right:8px;background:none;border:none;
           color:var(--dim);font-size:15px;cursor:pointer;font-family:monospace;}
#map-close:hover{color:var(--text);}

/* HELP MODAL */
#help-modal{display:none;position:fixed;inset:0;background:rgba(0,0,0,.88);
            z-index:500;align-items:center;justify-content:center;}
#help-modal.open{display:flex;}
#help-inner{background:var(--bg2);border:1px solid var(--border);border-radius:6px;
            padding:14px 18px;max-width:460px;width:90%;max-height:80vh;overflow-y:auto;}
#help-inner h2{color:var(--gold);font-size:12px;margin-bottom:8px;}
.hr{display:flex;gap:8px;margin-bottom:4px;font-size:10px;}
.hk{color:var(--gold);width:150px;flex-shrink:0;}
.hv{color:var(--text);}
.hclose{margin-top:10px;background:var(--bg3);border:1px solid var(--border);
        color:var(--dim);padding:4px 10px;cursor:pointer;border-radius:3px;
        font-family:monospace;font-size:10px;}

/* COMBAT POPUP */
#combat-popup{display:none;position:fixed;bottom:50px;left:50%;transform:translateX(-50%);
              background:var(--bg2);border:1px solid var(--green);border-radius:6px;
              padding:10px 14px;z-index:400;min-width:280px;box-shadow:0 4px 20px rgba(0,0,0,.6);}
#combat-popup.open{display:block;}
#cp-title{color:var(--green);font-size:11px;font-weight:bold;margin-bottom:6px;text-align:center;}
#cp-enemies{font-size:10px;color:var(--text);margin-bottom:8px;}
.cp-enemy{display:flex;justify-content:space-between;padding:1px 0;border-bottom:1px solid var(--dim2);}
.cp-enemy:last-child{border-bottom:none;}
#cp-btns{display:flex;gap:5px;justify-content:center;}
.cp-btn{padding:5px 12px;border:none;border-radius:4px;cursor:pointer;
        font-family:monospace;font-size:11px;font-weight:bold;}
#cp-atk{background:var(--green);color:#000;}
#cp-esp{background:var(--mana);color:#fff;}
#cp-pas{background:var(--bg3);color:var(--dim);border:1px solid var(--border);}
#cp-obj{background:var(--orange);color:#000;}

/* PVP CHALLENGE POPUP */
#pvp-popup{display:none;position:fixed;top:50%;left:50%;
           transform:translate(-50%,-50%);
           background:var(--bg2);border:2px solid var(--red);border-radius:8px;
           padding:20px 24px;z-index:600;min-width:260px;text-align:center;
           box-shadow:0 6px 30px rgba(0,0,0,.7);}
#pvp-popup.open{display:block;}
#pvp-title{color:var(--red);font-size:14px;font-weight:bold;margin-bottom:6px;}
#pvp-info{color:var(--text);font-size:11px;margin-bottom:14px;}
#pvp-btns{display:flex;gap:8px;justify-content:center;}
#pvp-accept{background:var(--green);color:#000;border:none;padding:7px 18px;
            border-radius:4px;cursor:pointer;font-weight:bold;font-family:monospace;font-size:12px;}
#pvp-reject{background:var(--red);color:#fff;border:none;padding:7px 18px;
            border-radius:4px;cursor:pointer;font-weight:bold;font-family:monospace;font-size:12px;}
</style>
</head>
<body>

<!-- LOGIN -->
<div id="lo">
  <div id="lb">
    <h1>⚔ The Return to Highdown</h1>
    <p>MUD Multiplayer</p>
    <div class="tabs">
      <button class="tab active" onclick="showTab('login')">Iniciar sesión</button>
      <button class="tab" onclick="showTab('register')">Crear cuenta</button>
    </div>
    <div id="login-p">
      <input class="li" id="lu" type="text" placeholder="Usuario" autocomplete="off">
      <input class="li" id="lp" type="password" placeholder="Contraseña">
      <button class="abtn" onclick="doLogin()">ENTRAR</button>
    </div>
    <div id="reg-p">
      <input class="li" id="ru"  type="text"     placeholder="Usuario (mín. 3 chars)" autocomplete="off">
      <input class="li" id="rp1" type="password" placeholder="Contraseña (mín. 4 chars)">
      <input class="li" id="rp2" type="password" placeholder="Repetir contraseña">
      <input class="li" id="rn"  type="text"     placeholder="Nombre en el juego">
      <button class="abtn" onclick="doRegister()">CREAR CUENTA</button>
    </div>
    <div id="lerr"></div>
  </div>
</div>

<!-- MAP MODAL -->
<div id="map-modal" onclick="if(event.target===this)closeMapBtn()">
  <div id="map-inner">
    <button id="map-close" onclick="closeMapBtn()">✕</button>
    <svg id="map-svg-full" viewBox="0 0 520 760" width="460" height="640" xmlns="http://www.w3.org/2000/svg">
      <defs><filter id="glowf"><feGaussianBlur stdDeviation="4" result="b"/>
        <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter></defs>
      <rect x="10" y="10" width="500" height="205" rx="5" fill="#080f08" stroke="#1a3a1a" stroke-width="1"/>
      <text x="16" y="23" fill="#2d5a2d" font-size="8" font-family="monospace">❄ NIEVE</text>
      <rect x="10" y="222" width="500" height="48" rx="4" fill="#080f08" stroke="#1a2a1a" stroke-width="1"/>
      <text x="16" y="234" fill="#2e7d32" font-size="8" font-family="monospace">⚓ PUERTO</text>
      <rect x="10" y="277" width="500" height="200" rx="5" fill="#060810" stroke="#10103a" stroke-width="1"/>
      <text x="16" y="290" fill="#1040a0" font-size="8" font-family="monospace">🌊 MAR</text>
      <rect x="10" y="484" width="500" height="48" rx="4" fill="#080f08" stroke="#1a2a1a" stroke-width="1"/>
      <text x="16" y="497" fill="#2e7d32" font-size="8" font-family="monospace">🌴 OASIS</text>
      <rect x="10" y="539" width="500" height="210" rx="5" fill="#100800" stroke="#302000" stroke-width="1"/>
      <text x="16" y="552" fill="#6b5010" font-size="8" font-family="monospace">🏜 DESIERTO</text>
      <g id="map-conn-full"></g><g id="map-rooms-full"></g>
    </svg>
  </div>
</div>

<!-- HELP MODAL -->
<div id="help-modal" onclick="if(event.target===this)closeHelpBtn()">
  <div id="help-inner">
    <h2>❓ Comandos</h2>
    <div class="hr"><span class="hk">n / s / e / o</span><span class="hv">Moverse</span></div>
    <div class="hr"><span class="hk">atacar</span><span class="hv">Iniciar combate</span></div>
    <div class="hr"><span class="hk">1/2/3/4</span><span class="hv">Combate: Atacar/Especial/Pasar/Objeto</span></div>
    <div class="hr"><span class="hk">mirar</span><span class="hv">Describir sala actual</span></div>
    <div class="hr"><span class="hk">stats</span><span class="hv">Ver estadísticas</span></div>
    <div class="hr"><span class="hk">tienda / hospital</span><span class="hv">Servicios (si disponibles)</span></div>
    <div class="hr"><span class="hk">mochila</span><span class="hv">Ver inventario</span></div>
    <div class="hr"><span class="hk">usar vida/dano/gema</span><span class="hv">Usar objeto</span></div>
    <div class="hr"><span class="hk">invitar &lt;nombre&gt;</span><span class="hv">Invitar a grupo</span></div>
    <div class="hr"><span class="hk">aceptar / rechazar</span><span class="hv">Responder invitación</span></div>
    <div class="hr"><span class="hk">grupo / salirgrupo</span><span class="hv">Ver/Abandonar grupo</span></div>
    <div class="hr"><span class="hk">duelo &lt;nombre&gt; [monedas]</span><span class="hv">Retar a PvP</span></div>
    <div class="hr"><span class="hk">guardar</span><span class="hv">Guardar progreso</span></div>
    <button class="hclose" onclick="closeHelpBtn()">Cerrar</button>
  </div>
</div>

<!-- COMBAT POPUP -->
<div id="combat-popup">
  <div id="cp-title">⚔ COMBATE EN CURSO</div>
  <div id="cp-enemies"></div>
  <div id="cp-btns">
    <button class="cp-btn" id="cp-atk" onclick="send('1')">① Atacar</button>
    <button class="cp-btn" id="cp-esp" onclick="send('2')">② Especial</button>
    <button class="cp-btn" id="cp-pas" onclick="send('3')">③ Pasar</button>
    <button class="cp-btn" id="cp-obj" onclick="send('4')">④ Objeto</button>
  </div>
</div>

<!-- PVP CHALLENGE POPUP -->
<div id="pvp-popup">
  <div id="pvp-title">⚔ RETO A DUELO</div>
  <div id="pvp-info"></div>
  <div id="pvp-btns">
    <button id="pvp-accept" onclick="acceptDuelo()">✓ Aceptar</button>
    <button id="pvp-reject" onclick="rejectDuelo()">✗ Rechazar</button>
  </div>
</div>

<!-- TOPBAR -->
<div id="topbar">
  <div id="tb-title">⚔ MUD</div>
  <div id="tb-player">—</div>
  <div id="cdot"></div>
</div>

<!-- APP GRID -->
<div id="app">

  <!-- LEFT -->
  <div id="left">
    <div id="stats-pane">
      <div class="sp-name" id="s-nm">—</div>
      <div class="sp-cls"  id="s-cl">—</div>
      <div>
        <div class="lvr">
          <span style="color:var(--dim);font-size:9px">Nivel</span>
          <span class="lvb" id="s-nv">1</span>
        </div>
        <div class="bl"><span class="bl-n">XP</span><span id="s-xp">0/150</span></div>
        <div class="xw"><div class="bf bf-xp" id="b-xp" style="width:0%"></div></div>
      </div>
      <div class="sh">Vida &amp; Mana</div>
      <div>
        <div class="bl"><span class="bl-n">❤ HP</span><span id="s-hp">—</span></div>
        <div class="bw"><div class="bf bf-hp" id="b-hp" style="width:100%"></div></div>
        <div class="bl"><span class="bl-n">✦ Mana</span><span id="s-mp">—</span></div>
        <div class="bw"><div class="bf bf-mp" id="b-mp" style="width:100%"></div></div>
      </div>
      <div class="sh">Combate</div>
      <div>
        <div class="sr"><span class="sr-l">Daño</span><span class="sr-v" id="s-dmg">—</span></div>
        <div class="sr"><span class="sr-l">Ataques</span><span class="sr-v" id="s-atq" style="color:var(--green)">—</span></div>
        <div class="sr"><span class="sr-l">Especial</span><span class="sr-v" id="s-mc" style="color:var(--mana)">—</span></div>
      </div>
    </div>
    <div id="bag-pane">
      <div class="bag-title">🎒 Mochila</div>
      <div class="bag-coins" id="bag-coins">0 💰</div>
      <div id="bag-items"><div class="bag-empty">Vacía</div></div>
    </div>
    <div id="services-pane">
      <button class="svc-btn hosp" id="btn-hosp" onclick="send('hospital')">🏥 Hospital</button>
      <button class="svc-btn shop" id="btn-shop" onclick="send('tienda')">🏪 Tienda</button>
    </div>
  </div>

  <!-- CENTER -->
  <div id="center">
    <div id="minimap-btn" onclick="openMap()" title="Clic para ampliar">
      <svg id="map-svg-mini" viewBox="0 0 520 760" xmlns="http://www.w3.org/2000/svg">
        <rect x="10" y="10"  width="500" height="205" rx="4" fill="#080f08" stroke="#1a3a1a" stroke-width="2"/>
        <rect x="10" y="222" width="500" height="48"  rx="3" fill="#080f08" stroke="#1a2a1a" stroke-width="2"/>
        <rect x="10" y="277" width="500" height="200" rx="4" fill="#060810" stroke="#10103a" stroke-width="2"/>
        <rect x="10" y="484" width="500" height="48"  rx="3" fill="#080f08" stroke="#1a2a1a" stroke-width="2"/>
        <rect x="10" y="539" width="500" height="210" rx="4" fill="#100800" stroke="#302000" stroke-width="2"/>
        <g id="map-conn-mini"></g><g id="map-rooms-mini"></g>
      </svg>
      <div id="minimap-label">🗺 MAPA</div>
    </div>
    <div id="glog"></div>
  </div>

  <!-- RIGHT -->
  <div id="right">
    <div id="lb-pane">
      <div id="lb-hdr">🏆 Ranking Global</div>
      <div id="lb-list"><div style="color:var(--dim);font-size:9px;padding:5px">Cargando...</div></div>
    </div>
    <div id="chat-pane">
      <div id="chat-tabs">
        <button class="ctab cs" id="ct-sala"   onclick="setChatTab('sala')">Sala</button>
        <button class="ctab"    id="ct-global" onclick="setChatTab('global')">Global</button>
        <button class="ctab"    id="ct-grupo"  onclick="setChatTab('grupo')">Grupo</button>
      </div>
      <div id="chat-log"></div>
      <div id="chat-in-row">
        <input id="chat-in" type="text" placeholder="Mensaje..." disabled
               onkeydown="if(event.key==='Enter')sendChat()">
        <button id="chat-send" onclick="sendChat()" disabled>↵</button>
      </div>
    </div>
  </div>

  <!-- CONTROLS -->
  <div id="controls">
    <button class="cb dir" onclick="send('n')">N</button>
    <button class="cb dir" onclick="send('s')">S</button>
    <button class="cb dir" onclick="send('e')">E</button>
    <button class="cb dir" onclick="send('o')">O</button>
    <div class="cb-sep"></div>
    <button class="cb atk" onclick="send('atacar')">⚔ Atacar</button>
    <div class="cb-sep"></div>
    <button class="cb pvp" onclick="promptDuelo()">☠ Duelo</button>
    <div class="cb-sep"></div>
    <button class="cb" onclick="send('mirar')">👁</button>
    <button class="cb" onclick="send('guardar')">💾</button>
    <button class="cb" onclick="send('stats')">📊</button>
    <div id="input-bar">
      <input id="cmd" type="text" placeholder="Comando..." disabled
             autocomplete="off" spellcheck="false"
             onkeydown="if(event.key==='Enter')doSend()">
      <button id="sbtn" onclick="doSend()" disabled>↵</button>
    </div>
    <button class="cb gold-btn" onclick="openHelp()">❓</button>
  </div>

</div>

<script>
/* MAP */
const RPOS={
  44:{x:260,y:38,n:"Cumbre Alpha",boss:true,b:"nieve"},
  41:{x:105,y:95,n:"Bosque Hielo",boss:false,b:"nieve"},
  43:{x:415,y:95,n:"Trono Hielo",boss:false,b:"nieve"},
  40:{x:105,y:165,n:"Tundra Helada",boss:false,b:"nieve"},
  42:{x:415,y:165,n:"Fortaleza Cristal",boss:false,b:"nieve"},
  39:{x:260,y:246,n:"Puerto",boss:false,b:"safe"},
  38:{x:260,y:298,n:"Abismo Kraken",boss:true,b:"mar"},
  35:{x:105,y:360,n:"Aguas Profundas",boss:false,b:"mar"},
  37:{x:415,y:360,n:"Naufragio",boss:false,b:"mar"},
  34:{x:105,y:435,n:"Costa Tormentosa",boss:false,b:"mar"},
  36:{x:415,y:435,n:"Cueva Submarina",boss:false,b:"mar"},
  33:{x:260,y:508,n:"Oasis",boss:false,b:"safe"},
   6:{x:200,y:570,n:"Viento Susurrante",boss:false,b:"desierto"},
   1:{x:105,y:630,n:"North Mass",boss:false,b:"desierto"},
   3:{x:415,y:630,n:"Ruinas",boss:false,b:"desierto"},
  12:{x:260,y:680,n:"Altar Soberano",boss:true,b:"desierto"},
  13:{x:105,y:720,n:"Extensión Azhar",boss:false,b:"desierto"},
};
const CONNS=[[1,6],[3,6],[6,33],[33,34],[34,35],[34,36],[35,38],[36,37],[37,38],[38,39],[38,40],[39,40],[40,41],[40,42],[41,44],[42,43],[43,44]];
const BC={desierto:"#8b6914",mar:"#1565c0",nieve:"#546e7a",safe:"#2e7d32"};
const SNAMES={1:"North Mass",2:"Dunas Norte",3:"Ruinas",4:"Ciudad Abrasada",5:"Valle Muerto",6:"Viento Susurrante",7:"Oasis Oculto",8:"Sol Eterno",9:"Cripta",10:"Caravana Fantasma",11:"Fosa Titanes",12:"Altar Soberano",13:"Extensión Azhar",33:"Oasis",34:"Costa Tormentosa",35:"Aguas Profundas",36:"Cueva Submarina",37:"Naufragio",38:"Abismo Kraken",39:"Puerto",40:"Tundra Helada",41:"Bosque Hielo",42:"Fortaleza Cristal",43:"Trono Hielo",44:"Cumbre Alpha"};

function buildMap(connId,roomId){
  const ns="http://www.w3.org/2000/svg";
  const cg=document.getElementById(connId),rg=document.getElementById(roomId);
  if(!cg||!rg)return;
  CONNS.forEach(([a,b])=>{
    const pa=RPOS[a],pb=RPOS[b];if(!pa||!pb)return;
    const l=document.createElementNS(ns,"line");
    l.setAttribute("x1",pa.x);l.setAttribute("y1",pa.y);
    l.setAttribute("x2",pb.x);l.setAttribute("y2",pb.y);
    l.setAttribute("stroke","#252525");l.setAttribute("stroke-width","2");
    cg.appendChild(l);
  });
  Object.entries(RPOS).forEach(([id,r])=>{
    const g=document.createElementNS(ns,"g");
    g.setAttribute("id",roomId+"-r"+id);g.setAttribute("data-sid",id);
    const W=r.boss?56:48,H=18;
    const rect=document.createElementNS(ns,"rect");
    rect.setAttribute("x",r.x-W/2);rect.setAttribute("y",r.y-H/2);
    rect.setAttribute("width",W);rect.setAttribute("height",H);rect.setAttribute("rx",2);
    rect.setAttribute("fill",r.boss?"#150000":"#0d0d0d");
    rect.setAttribute("stroke",r.boss?"#7a1a1a":(BC[r.b]||"#2a2a2a"));
    rect.setAttribute("stroke-width","1");
    const txt=document.createElementNS(ns,"text");
    txt.setAttribute("x",r.x);txt.setAttribute("y",r.y+1);
    txt.setAttribute("text-anchor","middle");txt.setAttribute("dominant-baseline","middle");
    txt.setAttribute("fill",r.boss?"#cc3333":(BC[r.b]||"#555"));
    txt.setAttribute("font-size","7");txt.setAttribute("font-family","monospace");
    txt.textContent=id;
    g.appendChild(rect);g.appendChild(txt);
    if(roomId==="map-rooms-full"){
      let tt=null;
      g.addEventListener("mouseenter",e=>{
        tt=document.createElement("div");
        tt.style.cssText="position:fixed;background:#1a1a1a;border:1px solid #444;padding:3px 7px;border-radius:3px;font-size:10px;color:#ccc;pointer-events:none;z-index:600;white-space:nowrap;font-family:monospace";
        tt.textContent="["+id+"] "+r.n;document.body.appendChild(tt);
      });
      g.addEventListener("mousemove",e=>{if(tt){tt.style.left=(e.clientX+10)+"px";tt.style.top=(e.clientY-5)+"px";}});
      g.addEventListener("mouseleave",()=>{if(tt){tt.remove();tt=null;}});
    }
    rg.appendChild(g);
  });
}

function highlightRoom(id){
  ["mini","full"].forEach(suf=>{
    const pfx=suf==="mini"?"map-rooms-mini":"map-rooms-full";
    document.querySelectorAll("[id^='"+pfx+"-r']").forEach(g=>{
      const rid=parseInt(g.getAttribute("data-sid")),r=RPOS[rid];if(!r)return;
      const rect=g.querySelector("rect");if(!rect)return;
      rect.setAttribute("fill",r.boss?"#150000":"#0d0d0d");
      rect.setAttribute("stroke",r.boss?"#7a1a1a":(BC[r.b]||"#2a2a2a"));
      rect.setAttribute("stroke-width","1");rect.removeAttribute("filter");
    });
    const g=document.getElementById(pfx+"-r"+id);
    if(g){const rect=g.querySelector("rect");if(rect){
      rect.setAttribute("fill","#1f1200");rect.setAttribute("stroke","#c9a84c");
      rect.setAttribute("stroke-width","2");
      if(suf==="full")rect.setAttribute("filter","url(#glowf)");
    }}
  });
}

/* STATE */
let ws=null,hist=[],hidx=-1,chatTab="sala",myStats=null;

/* LOGIN */
function showTab(t){
  document.getElementById("login-p").style.display=t==="login"?"block":"none";
  document.getElementById("reg-p").style.display=t==="register"?"block":"none";
  document.querySelectorAll(".tab").forEach((el,i)=>el.classList.toggle("active",(i===0&&t==="login")||(i===1&&t==="register")));
}
showTab("login");

function getWsUrl(){const l=window.location;return(l.protocol==="https:"?"wss:":"ws:")+"//"+l.host+"/ws";}

function doLogin(){
  const u=document.getElementById("lu").value.trim();
  const p=document.getElementById("lp").value;
  const err=document.getElementById("lerr");
  if(!u||!p){err.textContent="Rellena usuario y contraseña.";return;}
  err.textContent="Conectando...";
  connect({type:"game_auth",usuario:u,password:p});
}
function doRegister(){
  const u=document.getElementById("ru").value.trim();
  const p1=document.getElementById("rp1").value;
  const p2=document.getElementById("rp2").value;
  const nom=document.getElementById("rn").value.trim()||u;
  const err=document.getElementById("lerr");
  if(!u||!p1||!p2){err.textContent="Rellena todos los campos.";return;}
  if(u.length<3){err.textContent="Usuario: mín 3 chars.";return;}
  if(p1.length<4){err.textContent="Contraseña: mín 4 chars.";return;}
  if(p1!==p2){err.textContent="Contraseñas no coinciden.";return;}
  err.textContent="Creando...";
  connect({type:"game_register",usuario:u,password:p1,nombre:nom});
}
function connect(authMsg){
  ws=new WebSocket(getWsUrl());
  ws.onopen=()=>ws.send(JSON.stringify(authMsg));
  ws.onmessage=e=>{try{handle(JSON.parse(e.data));}catch(_){}};
  ws.onclose=()=>{setConn(false);appendLog("Conexión cerrada.","gd");disableUI();};
  ws.onerror=()=>{document.getElementById("lerr").textContent="No se pudo conectar.";ws=null;};
}
["lu","lp"].forEach(id=>document.getElementById(id).addEventListener("keydown",e=>{if(e.key==="Enter")doLogin();}));
["ru","rp1","rp2","rn"].forEach(id=>document.getElementById(id).addEventListener("keydown",e=>{if(e.key==="Enter")doRegister();}));

/* MSG HANDLER */
function handle(m){
  if(m.type==="auth_ok"){
    document.getElementById("lo").style.display="none";
    setConn(true);enableUI();
    if(m.stats)updateStats(m.stats);
    document.getElementById("cmd").focus();
  } else if(m.type==="auth_fail"){
    document.getElementById("lerr").textContent=m.msg||"Error";ws=null;
  } else if(m.type==="game"){
    appendLog(m.text,classify(m.text));
  } else if(m.type==="prompt"){
    appendLog(m.text,"gp2");
  } else if(m.type==="levelup"){
    appendLog(m.text,"gl");
  } else if(m.type==="status"||m.type==="stats"){
    updateStats(m);
  } else if(m.type==="chat"){
    const tag=m.scope==="sala"?"[Sala]":m.scope==="global"?"[Global]":"[Grupo]";
    appendLog(tag+" "+(m.nombre||"")+(m.nombre?": ":"")+(m.text||m.mensaje||""),"gi");
    appendChat(m.nombre,m.scope,m.text||m.mensaje||"");
  } else if(m.type==="leaderboard"){
    renderLeaderboard(m.ranking);
  } else if(m.type==="combat_start"){
    openCombatPopup(m.enemigos);
  } else if(m.type==="combat_end"){
    closeCombatPopup();
  } else if(m.type==="pvp_challenge"){
    openPvpPopup(m.retador,m.monedas);
  }
}

function classify(t){
  if(!t)return "gg";
  const l=t.toLowerCase();
  if(l.includes("victoria")||l.includes("🏆"))return "gv";
  if(l.includes("caido")||l.includes("derrota")||l.includes("muerto")||l.includes("💀"))return "gd";
  if(l.includes("turno")||l.includes("combate")||l.includes("ataca")||l.includes("golpea")||l.includes("especial"))return "gc";
  if(l.includes("+")&&(l.includes("xp")||l.includes("hp")||l.includes("mana")))return "gi";
  if(l.includes("╔")||l.includes("║")||l.includes("╚"))return "gl";
  return "gg";
}

/* GAME LOG */
function appendLog(text,cls){
  if(!text)return;
  const log=document.getElementById("glog");
  text.split("\n").forEach(line=>{
    const d=document.createElement("div");d.className="gm "+cls;d.textContent=line;log.appendChild(d);
  });
  log.scrollTop=log.scrollHeight;
}

/* STATS — actualización en tiempo real */
function updateStats(s){
  myStats=s;
  set("s-nm",s.nombre||"—");
  set("s-cl",s.clase?(s.clase[0].toUpperCase()+s.clase.slice(1)):"—");
  set("s-nv","Nv."+s.nivel);
  document.getElementById("tb-player").innerHTML="<span>"+esc(s.nombre)+"</span> ["+esc(s.clase)+"] Nv."+s.nivel;

  /* XP */
  const xpPct=s.xpMax>0?Math.min(100,s.xp/s.xpMax*100):0;
  document.getElementById("b-xp").style.width=xpPct+"%";
  set("s-xp",s.xp+"/"+s.xpMax);

  /* HP */
  const hpPct=s.hpMax>0?Math.min(100,s.hp/s.hpMax*100):0;
  const bh=document.getElementById("b-hp");
  bh.style.width=hpPct+"%";
  bh.style.background=hpPct<25?"var(--red2)":hpPct<50?"#e67e22":"var(--red)";
  set("s-hp",s.hp+"/"+s.hpMax);

  /* Mana */
  const mpPct=s.manaMax>0?Math.min(100,s.mana/s.manaMax*100):0;
  document.getElementById("b-mp").style.width=mpPct+"%";
  set("s-mp",s.mana+"/"+s.manaMax);

  /* Combate */
  const atqs=s.ataquesTurno;
  set("s-dmg",s.danioBase||"—");
  set("s-atq",Array.isArray(atqs)?atqs[0]+"-"+atqs[1]:String(atqs||"—"));
  set("s-mc",(s.costoEspecial||0)+" mana");

  /* Mochila */
  set("bag-coins",(s.monedas||0)+" 💰");
  if(s.inventario!==undefined)renderBag(s.inventario);

  /* Servicios */
  if(s.sala_id!==undefined)updateServices(s.sala_id);

  /* Mapa */
  if(s.sala_id)highlightRoom(s.sala_id);
}

function renderBag(inv){
  const N={"pocion_vida":"🧪 Poción Vida","pocion_danio":"⚗️ Poc. Daño","gema_teleporte":"💎 Gema Tele."};
  const div=document.getElementById("bag-items");
  const items=Object.entries(inv||{}).filter(([k,v])=>v>0);
  if(!items.length){div.innerHTML='<div class="bag-empty">Vacía</div>';return;}
  div.innerHTML=items.map(([k,v])=>`<div class="bag-item">${N[k]||k} x${v}</div>`).join("");
}

const SALAS_SVC={33:{h:true,s:true},39:{h:true,s:true},4:{h:true,s:false}};
function updateServices(sid){
  const sv=SALAS_SVC[sid]||{};
  document.getElementById("btn-hosp").classList.toggle("visible",!!sv.h);
  document.getElementById("btn-shop").classList.toggle("visible",!!sv.s);
}

/* LEADERBOARD */
function renderLeaderboard(ranking){
  const div=document.getElementById("lb-list");
  if(!ranking||!ranking.length){div.innerHTML='<div style="color:var(--dim);font-size:9px;padding:5px">Sin datos</div>';return;}
  const myName=myStats?myStats.nombre:"";
  div.innerHTML=ranking.map((p,i)=>{
    const pos=i+1;
    const pc=pos===1?"gold":pos===2?"silver":pos===3?"bronze":"";
    const medal=pos===1?"🥇":pos===2?"🥈":pos===3?"🥉":"";
    const isMe=p.nombre===myName;
    return `<div class="lbi" ${isMe?"style='background:#1a1500'":''}>`+
      `<span class="lbi-pos ${pc}">${medal||pos}</span>`+
      `<span class="lbi-name ${isMe?"me":""}">${esc(p.nombre)}</span>`+
      `<span class="lbi-info">${esc(p.clase||"?")}</span>`+
      `<span class="lbi-lvl">Nv.${p.nivel}</span>`+
      `</div>`;
  }).join("");
}

/* CHAT */
function setChatTab(t){
  chatTab=t;
  document.getElementById("ct-sala").className  ="ctab"+(t==="sala"  ?" cs":"");
  document.getElementById("ct-global").className="ctab"+(t==="global"?" cg":"");
  document.getElementById("ct-grupo").className ="ctab"+(t==="grupo" ?" cgr":"");
  const el=document.getElementById("ct-"+t);if(el)el.style.boxShadow="";
}
function appendChat(nombre,scope,texto){
  const log=document.getElementById("chat-log");
  const now=new Date();
  const t=now.getHours().toString().padStart(2,"0")+":"+now.getMinutes().toString().padStart(2,"0");
  const nc=scope==="sala"?"cn-s":scope==="global"?"cn-g":"cn-gr";
  const d=document.createElement("div");d.className="cm";
  d.innerHTML=`<span class="cm-t">${t}</span><span class="cm-n ${nc}">${esc(nombre||"")}</span><span class="cm-tx">${esc(texto)}</span>`;
  log.appendChild(d);log.scrollTop=log.scrollHeight;
  if(scope!==chatTab){const el=document.getElementById("ct-"+scope);if(el)el.style.boxShadow="0 0 0 1px var(--gold)";}
}
function sendChat(){
  const inp=document.getElementById("chat-in");
  const msg=inp.value.trim();
  if(!msg||!ws||ws.readyState!==WebSocket.OPEN)return;
  const cmd=chatTab==="sala"?"decir "+msg:chatTab==="global"?"g "+msg:"gc "+msg;
  ws.send(cmd);
  appendChat(myStats?myStats.nombre:"Tú",chatTab,msg);
  inp.value="";
  const el=document.getElementById("ct-"+chatTab);if(el)el.style.boxShadow="";
}

/* COMBAT POPUP */
function openCombatPopup(enemigos){
  const popup=document.getElementById("combat-popup");
  const div=document.getElementById("cp-enemies");
  div.innerHTML=(enemigos||[]).map(e=>`<div class="cp-enemy"><span>${esc(e.nombre)}</span><span style="color:var(--red)">${e.hp}/${e.hpMax} HP</span></div>`).join("");
  popup.classList.add("open");
}
function closeCombatPopup(){
  document.getElementById("combat-popup").classList.remove("open");
}

/* PVP POPUP */
function openPvpPopup(retador,monedas){
  document.getElementById("pvp-info").textContent=
    retador+" te reta a duelo"+(monedas?" - Apuesta: "+monedas+" monedas":"")+". Aceptas?";
  document.getElementById("pvp-popup").classList.add("open");
}
function acceptDuelo(){
  send("aceptar_duelo");
  document.getElementById("pvp-popup").classList.remove("open");
}
function rejectDuelo(){
  send("rechazar_duelo");
  document.getElementById("pvp-popup").classList.remove("open");
}

/* PVP PROMPT */
function promptDuelo(){
  const nom=prompt("Nombre del jugador a retar:");
  if(!nom)return;
  const mon=prompt("Monedas a apostar (0 = sin apuesta):");
  if(mon===null)return;
  send("duelo "+nom+" "+(parseInt(mon)||0));
}

/* MAP */
function openMap(){document.getElementById("map-modal").classList.add("open");}
function closeMapBtn(){document.getElementById("map-modal").classList.remove("open");}
function openHelp(){document.getElementById("help-modal").classList.add("open");}
function closeHelpBtn(){document.getElementById("help-modal").classList.remove("open");}

/* SEND */
function send(text){if(!ws||ws.readyState!==WebSocket.OPEN)return;ws.send(text);}
function doSend(){
  const inp=document.getElementById("cmd");
  const cmd=inp.value.trim();
  if(!cmd)return;
  hist.unshift(cmd);if(hist.length>60)hist.pop();hidx=-1;
  send(cmd);appendLog("> "+cmd,"gs");inp.value="";
}
document.addEventListener("DOMContentLoaded",()=>{
  document.getElementById("cmd").addEventListener("keydown",e=>{
    if(e.key==="ArrowUp"){hidx=Math.min(hidx+1,hist.length-1);e.target.value=hist[hidx]||"";e.preventDefault();}
    else if(e.key==="ArrowDown"){hidx=Math.max(hidx-1,-1);e.target.value=hidx===-1?"":hist[hidx];e.preventDefault();}
  });
});

/* UI */
function enableUI(){
  ["cmd","chat-in"].forEach(id=>{const el=document.getElementById(id);if(el)el.disabled=false;});
  ["sbtn","chat-send"].forEach(id=>{const el=document.getElementById(id);if(el)el.disabled=false;});
}
function disableUI(){
  ["cmd","chat-in"].forEach(id=>{const el=document.getElementById(id);if(el)el.disabled=true;});
  ["sbtn","chat-send"].forEach(id=>{const el=document.getElementById(id);if(el)el.disabled=true;});
  closeCombatPopup();
}
function setConn(on){document.getElementById("cdot").className=on?"on":"";}
function set(id,val){const el=document.getElementById(id);if(el)el.textContent=val;}
function esc(s){return String(s||"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");}

buildMap("map-conn-mini","map-rooms-mini");
buildMap("map-conn-full","map-rooms-full");
</script>
</body>
</html>"""

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
