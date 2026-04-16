"""
server.py — MUD Multiplayer
============================
- WS   /ws?u=<user>  → joc WebSocket (navegador + client.py)
- HTTP /             → serveix la interfície HTML del joc

Uso:
  pip install aiohttp
  python3 server.py

Jugar (navegador): http://<IP>:PORT/
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

# Sessió global reutilitzable (evita crear/destruir una sessió per cada petició)
_sb_session: aiohttp.ClientSession | None = None

def _get_sb_session() -> aiohttp.ClientSession:
    global _sb_session
    if _sb_session is None or _sb_session.closed:
        _sb_session = aiohttp.ClientSession()
    return _sb_session

async def _sb_get(usuario: str) -> dict | None:
    """Lee una fila de Supabase. Devuelve el dict o None si no existe."""
    url = f"{SUPABASE_URL}/rest/v1/{TABLA}?usuario=eq.{usuario}&select=*"
    try:
        s = _get_sb_session()
        async with s.get(url, headers=_sb_headers()) as r:
            if r.status == 200:
                rows = await r.json()
                return rows[0] if rows else None
    except Exception as e:
        print(f"[SB] Error _sb_get({usuario}): {e}")
    return None

async def _sb_upsert(row: dict):
    """Inserta o actualiza una fila en Supabase."""
    url = f"{SUPABASE_URL}/rest/v1/{TABLA}"
    headers = {**_sb_headers(), "Prefer": "resolution=merge-duplicates,return=minimal"}
    try:
        s = _get_sb_session()
        await s.post(url, headers=headers, json=row)
    except Exception as e:
        print(f"[SB] Error _sb_upsert: {e}")


# Leaderboard cache (30s TTL)
_lb_cache: list = []
_lb_cache_ts: float = 0.0
_LB_CACHE_TTL = 30

async def get_leaderboard_async(limit: int = 20) -> list:
    """Ranking global ordenado por nivel desc (cached 30s)."""
    global _lb_cache, _lb_cache_ts
    import time as _time
    now = _time.monotonic()
    if _lb_cache and (now - _lb_cache_ts) < _LB_CACHE_TTL:
        return _lb_cache[:limit]
    if USAR_SUPABASE:
        # PostgREST: traemos todos y ordenamos en Python
        # (ordenar por campo JSONB anidado no es directo en PostgREST)
        url = f"{SUPABASE_URL}/rest/v1/{TABLA}?select=usuario,data&limit=200"
        try:
            s = _get_sb_session()
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
                        _lb_cache = result[:limit]
                        _lb_cache_ts = _time.monotonic()
                        return _lb_cache
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
    _lb_cache = result[:limit]
    _lb_cache_ts = _time.monotonic()
    return _lb_cache


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
SALA_RESPAWN   = 6    # Oasis — sala segura, no hay enemigos
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
# ACERTIJOS
# ============================================================
ACERTIJOS = [
    {
        "pregunta": "Si me nombras, desaparezco. ¿Qué soy?",
        "opciones": ["A) El secreto", "B) El silencio", "C) La sombra", "D) El pensamiento"],
        "respuesta": "b",
        "letra_correcta": "B"
    },
    {
        "pregunta": "¿Qué número falta en la serie? 2 – 6 – 7 – 21 – 22 – 66 – ?",
        "opciones": ["A) 67", "B) 132", "C) 198", "D) 68"],
        "respuesta": "a",
        "letra_correcta": "A"
    },
    {
        "pregunta": "Un monje copia manuscritos. Un día escribe: 11/11/1111. ¿Dice la verdad que es la primera vez con todos los números iguales?",
        "opciones": ["A) Sí", "B) No", "C) Solo en calendario juliano", "D) Solo si cuenta los ceros"],
        "respuesta": "b",
        "letra_correcta": "B"
    },
    {
        "pregunta": "3 interruptores, 3 bombillas, 1 solo intento. ¿Cómo saber cuál controla cada una?",
        "opciones": [
            "A) Enciende uno, espera, cambia al segundo y entra",
            "B) Enciende dos, espera, apaga uno y entra",
            "C) Enciende uno, espera, luego enciende el segundo y entra",
            "D) No hay manera"
        ],
        "respuesta": "b",
        "letra_correcta": "B"
    }
]

# Salas con acertijos: 33 y 37 (3 acertijos cada una, diferentes)
SALAS_ACERTIJOS = {
    33: [0, 1, 2],  # Primeros 3 acertijos
    37: [1, 2, 3]   # Últimos 3 acertijos (solapamiento para variación)
}

# ============================================================
# SALAS
# ============================================================
SALAS = {
    # ── TUTORIAL (salas 0.1-0.4) ──────────────────────────────────
    0.1: {"nombre": "Como combatir",
          "descripcion": "Hace ya 15 años de la gran tragedia. Ya habían pasado 15 años de la masacre del pueblo de Highdown.",
          "conexiones": {"norte": 0.2},
          "encuentros": [("bandido", 1)]},
 
    0.2: {"nombre": "estructuras basicas",
          "descripcion": "hospital y tienda",
          "conexiones": {"sur": 0.1, "norte": 0.3},
         "hospital": True, "tienda": True},

    0.3: {"nombre": "Objetos",
          "descripcion": "Como usar objetos",
          "conexiones": {"sur": 0.2, "norte": 0.4},
          "encuentros": [("duende", 1)]},
 
    0.4: {"nombre": "Como funciona UI",
          "descripcion": "UI",
          "conexiones": {"sur": 0.3, "norte": 1}},

    # ── DESIERTO (salas 1-32) ──────────────────────────────────
    1:  {"nombre": "North Mass",
         "descripcion": "Arena caliente bajo tus pies. El sol abrasa sin piedad.",
         "conexiones": {"norte": 2, "este": 13, "sur": 6},
         "bioma": "desierto", "cantidad": 1,
         "hospital": True},

    2:  {"nombre": "Dunas del Norte",
         "descripcion": "Dunas interminables. Algo se mueve entre la arena.",
         "conexiones": {"sur": 1, "norte": 3},
         "bioma": "desierto", "cantidad": 2},

    3:  {"nombre": "Ruinas del Desierto",
         "descripcion": "Columnas rotas a medias enterradas. Silencio inquietante.",
         "conexiones": {"oeste": 4, "norte": 5, "este": 16},
         "bioma": "desierto", "cantidad": 2},

    4:  {"nombre": "Ciudad abrasada",
         "descripcion": "Una ciudad abrasada se alza entre cenizas eternas...",
         "conexiones": {"este": 3},
         "encuentros": [("demonioSuperior", 1)],
         "hospital": True},

    5:  {"nombre": "Valle muerto",
         "descripcion": "Centenares de cuerpos muertos, esqueletos más grandes que buques navales.",
         "conexiones": {"sur": 3},
         "bioma": "desierto", "cantidad": 2,
         "hospital": True},

    6:  {"nombre": "Oasis tranquilo",
         "descripcion": "Un pequeño oasis en medio del desierto. Aquí puedes descansar.",
         "conexiones": {"sur": 10, "oeste": 7, "norte": 1},
         "hospital": True, "tienda": True},

    7:  {"nombre": "Sala del Viento Susurrante",
         "descripcion": "Columnas de arena giran lentamente y traen voces del pasado.",
         "conexiones": {"oeste": 8, "este": 6, "sur": 9},
         "encuentros": [("elfoOscuro", 1)]},

    8:  {"nombre": "Cámara del Oasis Oculto",
         "descripcion": "Un pequeño lago mágico que concede visiones o recuerdos.",
         "conexiones": {"oeste": 9, "este": 7},
         "bioma": "desierto", "cantidad": 1},

    9:  {"nombre": "Salón del Sol Eterno",
         "descripcion": "Un techo abierto donde un sol artificial quema sin piedad.",
         "conexiones": {"sur": 8, "este": 7},
         "bioma": "desierto", "cantidad": 2,
         "hospital": True, "tienda": True},

    10: {"nombre": "Cripta de las Dunas Vivas",
         "descripcion": "Personas enterradas que se mueven bajo la arena.",
         "conexiones": {"norte": 7},
         "bioma": "desierto", "cantidad": 2},

    11: {"nombre": "Caravana fantasma",
         "descripcion": "Viajeros espectrales repiten eternamente su última travesía.",
         "conexiones": {"este": 12, "norte": 6},
         "encuentros": [("demonioInferior", 2)]},

    12: {"nombre": "Fosa de Titanes",
         "descripcion": "Restos colosales emergen de la arena, como si antiguos gigantes hubieran caído aquí.",
         "conexiones": {"norte": 13, "oeste": 11, "este": 17},
         "bioma": "desierto", "cantidad": 2},

    13: {"nombre": "Altar del Soberano Abisal",
         "descripcion": "Un trono oscuro tallado en huesos ennegrecidos irradia una presencia opresiva.",
         "conexiones": {"sur": 12, "este": 18, "norte": 14},
         "encuentros": [("reyEsqueleto", 1)],
         "tienda": True},

    14: {"nombre": "Extensión de Azhar",
         "descripcion": "El suelo arde bajo tus pies mientras el horizonte tiembla por el calor.",
         "conexiones": {"norte": 15, "este": 19, "oeste": 1},
         "bioma": "desierto", "cantidad": 1},

    15: {"nombre": "Mar de Dunas Susurrantes",
         "descripcion": "Las dunas se extienden sin fin, emitiendo murmullos cuando el viento las roza.",
         "conexiones": {"norte": 16, "sur": 14},
         "bioma": "desierto", "cantidad": 2},

    16: {"nombre": "Vestigios Enterrados",
         "descripcion": "Ruinas antiguas asoman entre la arena, como recuerdos que se niegan a desaparecer.",
         "conexiones": {"norte": 17, "sur": 15},
         "bioma": "desierto", "cantidad": 1},

    17: {"nombre": "Santuario Carmesí",
         "descripcion": "Muros cubiertos de símbolos sangrientos laten con una energía inquietante.",
         "conexiones": {"sur": 16, "este": 22, "oeste": 3},
         "encuentros": [("demonioInferior", 2)],
         "tienda": True},

    18: {"nombre": "Sepulcro de Colosos",
         "descripcion": "Huesos gigantescos yacen dispersos, devorados lentamente por el desierto.",
         "conexiones": {"oeste": 11},
         "bioma": "desierto", "cantidad": 2,
         "tienda": True},

    19: {"nombre": "Trono del Abismo",
         "descripcion": "Una estructura de hueso y sombra domina el lugar, como si aún esperara a su dueño.",
         "conexiones": {"oeste": 12, "este": 27},
         "bioma": "desierto", "cantidad": 1},

    20: {"nombre": "Llanura de Fuego Blanco",
         "descripcion": "La luz del sol es tan intensa que todo parece arder en un resplandor pálido.",
         "conexiones": {"norte": 21, "este": 26, "oeste": 13},
         "bioma": "desierto", "cantidad": 1},

    21: {"nombre": "Dunas del Murmullo Eterno",
         "descripcion": "Algo invisible se desliza bajo la arena, siguiendo cada paso que das.",
         "conexiones": {"sur": 20, "este": 25},
         "bioma": "desierto", "cantidad": 2},

    22: {"nombre": "Columnas del Olvido",
         "descripcion": "Pilares erosionados se alzan torcidos, marcando un lugar que el tiempo quiso borrar.",
         "conexiones": {"este": 15},
         "bioma": "desierto", "cantidad": 2,
         "hospital": True, "tienda": True},

    23: {"nombre": "Templo de la Sangre Antigua",
         "descripcion": "Inscripciones vivas recorren las paredes, como si observaran a los intrusos.",
         "conexiones": {"este": 24, "oeste": 16},
         "encuentros": [("demonioInferior", 2)]},

    24: {"nombre": "Abismo de los Caídos",
         "descripcion": "Un campo de restos antiguos donde incluso el viento parece evitar pasar.",
         "conexiones": {"sur": 25, "norte": 23, "este": 32, "oeste": 149},
         "bioma": "desierto", "cantidad": 2},

    25: {"nombre": "Trono del Devastador",
         "descripcion": "Un asiento de poder olvidado, rodeado de una oscuridad que respira.",
         "conexiones": {"sur": 30, "norte": 23, "este": 32, "oeste": 149},
         "bioma": "desierto", "cantidad": 4,
         "tesoro": True},

    26: {"nombre": "Horizonte Quebrado",
         "descripcion": "El aire distorsiona la vista, haciendo que la distancia pierda todo sentido.",
         "conexiones": {"oeste": 20, "sur": 27},
         "bioma": "desierto", "cantidad": 1,
         "tienda": True,
         "hospital": True},

    27: {"nombre": "Dunas del Hambre",
         "descripcion": "La arena se mueve de forma antinatural, como si buscara devorar a los vivos.",
         "conexiones": {"oeste": 19, "norte": 25},
         "bioma": "desierto", "cantidad": 2},

    28: {"nombre": "Ruinas del Eco Silente",
         "descripcion": "Cada paso resuena demasiado fuerte, como si algo escuchara desde abajo.",
         "conexiones": {"oeste": 18, "este": 29},
         "bioma": "desierto", "cantidad": 2},

    29: {"nombre": "Santuario de la Marca Roja",
         "descripcion": "Antiguos rituales dejaron su huella, aún palpable en el aire seco.",
         "conexiones": {"oeste": 28, "norte": 30},
         "encuentros": [("demonioInferior", 2)],
         "tesoro": True},

    30: {"nombre": "Campos de Huesos Errantes",
         "descripcion": "Restos que cambian de lugar con el tiempo, formando patrones desconocidos.",
         "conexiones": {"sur": 29, "norte": 31},
         "bioma": "desierto", "cantidad": 2},

    31: {"nombre": "Trono del Último Señor",
         "descripcion": "Un lugar de dominio absoluto, ahora envuelto en un silencio antinatural.",
         "conexiones": {"oeste": 25, "norte": 32},
         "encuentros": [("reyEsqueleto", 1)]},

    32: {"nombre": "Falla de los Antiguos",
         "descripcion": "Una grieta llena de restos y reliquias de una civilización olvidada.",
         "conexiones": {"sur": 31},
         "bioma": "desierto", "cantidad": 2,
         "hospital": True},

    33: {"nombre": "Trono de Ceniza Viva",
         "descripcion": "El asiento aún desprende calor, como si su antiguo rey no se hubiera ido del todo.",
         "conexiones": {"oeste": 24, "este": 34, "norte": 37},
         "encuentros": [("reyDemonio", 1)],
         "acertijos": True},  # ← NUEVO: Sala de acertijos

    # ── Mar (salas 33-72) ──────────────────────────────────
    34: {"nombre": "Embarcadero 1",
         "descripcion": "La marea está calmada y la gente emocionada.",
         "conexiones": {"oeste": 32, "norte": 38, "este": 39, "sur": 35},
         "bioma": "mar"},

    35: {"nombre": "Abismo Coralino",
         "descripcion": "Corales brillantes cubren una grieta que parece no tener fin.",
         "conexiones": {"oeste": 33, "este": 36},
         "bioma": "mar", "cantidad": 1,
         "hospital": True},

    36: {"nombre": "Trono del Oceano",
         "descripcion": "Un trono erosionado por el tiempo, rodeado de corrientes poderosas.",
         "conexiones": {"oeste": 34, "este": 37},
         "bioma": "mar", "cantidad": 2,
         "tesoro": True},

    37: {"nombre": "Embarcadero 2",
         "descripcion": "El puerto de embarcación esta rebosante de gente.",
         "conexiones": {"sur": 32, "este": 38, "norte": 42},
         "bioma": "mar",
         "acertijos": True},  # ← NUEVO: Sala de acertijos

    38: {"nombre": "Fosa de las Sombras Marinas",
         "descripcion": "Una profundidad oscura donde nada debería sobrevivir.",
         "conexiones": {"oeste": 37, "norte": 43, "este": 39, "sur": 33},
         "bioma": "mar", "cantidad": 2,
         "hospital": True},

    39: {"nombre": "Arrecife Susurrante",
         "descripcion": "El coral emite sonidos extraños al moverse con la corriente.",
         "conexiones": {"norte": 44, "sur": 33, "oeste": 38, "este": 40},
         "bioma": "mar", "cantidad": 1,
         "tesoro": True},

    40: {"nombre": "Caverna de la Bruma Salina",
         "descripcion": "Una cueva húmeda llena de niebla con olor a sal.",
         "conexiones": {"oeste": 39, "este": 41, "sur": 36},
         "bioma": "mar", "cantidad": 2},

    41: {"nombre": "Templo de las Olas Eternas",
         "descripcion": "Estructuras antiguas golpeadas sin cesar por el mar.",
         "conexiones": {"sur": 36, "norte": 46, "oeste": 40},
         "bioma": "mar", "cantidad": 3},

    42: {"nombre": "Laguna de los Naufragos",
         "descripcion": "Restos de barcos descansan bajo aguas quietas.",
         "conexiones": {"sur": 37, "norte": 52, "este": 43},
         "bioma": "mar", "cantidad": 1},

    43: {"nombre": "Pantano del Silencio",
         "descripcion": "Un pantano inmóvil donde ni los insectos se atreven a sonar.",
         "conexiones": {"oeste": 42, "norte": 51, "este": 44, "sur": 39},
         "bioma": "mar", "cantidad": 2},

    44: {"nombre": "Refugio de las Medusas",
         "descripcion": "Criaturas translúcidas iluminan la oscuridad acuática.",
         "conexiones": {"norte": 50, "sur": 39, "oeste": 43, "este": 45},
         "bioma": "mar", "cantidad": 3,
         "hospital": True, "tienda": True},

    45: {"nombre": "Camara del Pulpo Antiguo",
         "descripcion": "Tentáculos gigantes dejaron marcas en las paredes.",
         "conexiones": {"oeste": 44},
         "bioma": "mar", "cantidad": 1},

    46: {"nombre": "Bosque de Manglares Oscuros",
         "descripcion": "Raíces retorcidas emergen del agua turbia.",
         "conexiones": {"sur": 41, "este": 47, "norte": 48},
         "bioma": "mar", "cantidad": 2},

    47: {"nombre": "Isla de la Lluvia Perpetua",
         "descripcion": "Nunca deja de llover en esta isla perdida.",
         "conexiones": {"oeste": 46, "norte": 48},
         "bioma": "mar", "cantidad": 3},

    48: {"nombre": "Grieta Abisal",
         "descripcion": "Una fisura profunda que emite un frío inquietante.",
         "conexiones": {"oeste": 46, "sur": 47, "norte": 59},
         "bioma": "mar", "cantidad": 1},

    49: {"nombre": "Playa de los Ecos Hundidos",
         "descripcion": "Las olas traen voces del pasado.",
         "conexiones": {"norte": 56, "oeste": 50},
         "bioma": "mar", "cantidad": 2},

    50: {"nombre": "Torre del Vigia Marino",
         "descripcion": "Una torre solitaria que vigila el horizonte infinito.",
         "conexiones": {"sur": 44, "oeste": 51, "este": 49, "norte": 55},
         "bioma": "mar", "cantidad": 1},

    51: {"nombre": "Gruta de las Mareas Silentes",
         "descripcion": "El agua entra y sale sin hacer ruido, como si el sonido estuviera prohibido.",
         "conexiones": {"norte": 54, "sur": 43, "oeste": 52, "este": 50},
         "bioma": "mar", "cantidad": 2,
         "tesoro": True},

    52: {"nombre": "Pantano de las Raices Hundidas",
         "descripcion": "Raices gigantes se entrelazan bajo aguas oscuras.",
         "conexiones": {"sur": 42, "norte": 53, "este": 51},
         "bioma": "mar", "cantidad": 3},

    53: {"nombre": "Caverna del Coral Luminoso",
         "descripcion": "El coral emite una tenue luz azul en la oscuridad.",
         "conexiones": {"sur": 52, "este": 54},
         "bioma": "mar", "cantidad": 1,
         "hospital": True},

    54: {"nombre": "Estuario del Viento Humedo",
         "descripcion": "El aire cargado de humedad sopla con fuerza constante.",
         "conexiones": {"oeste": 53, "este": 55, "sur": 50},
         "bioma": "mar", "cantidad": 2,
         "tesoro": True},

    55: {"nombre": "Pozo de Agua Estancada",
         "descripcion": "Un pozo profundo donde el agua no se mueve desde hace siglos.",
         "conexiones": {"oeste": 54, "sur": 50},
         "bioma": "mar", "cantidad": 1},

    56: {"nombre": "Acantilado de la Lluvia Fina",
         "descripcion": "Una llovizna constante cubre la roca resbaladiza.",
         "conexiones": {"sur": 49},
         "bioma": "mar", "cantidad": 3},

    57: {"nombre": "Laguna de las Sombras Flotantes",
         "descripcion": "Figuras oscuras parecen moverse bajo la superficie.",
         "conexiones": {"norte": 58, "este": 59},
         "bioma": "mar", "cantidad": 2},

    58: {"nombre": "Bosque Inundado Antiguo",
         "descripcion": "Arboles muertos sobresalen de aguas tranquilas.",
         "conexiones": {"sur": 57, "este": 60},
         "bioma": "mar", "cantidad": 1,
         "tienda": True, "tesoro": True},

    59: {"nombre": "Camara de las Corrientes Ocultas",
         "descripcion": "El agua fluye por caminos invisibles bajo tus pies.",
         "conexiones": {"norte": 60, "sur": 48, "oeste": 57, "este": 62},
         "bioma": "mar", "cantidad": 3},

    60: {"nombre": "Isla del Horizonte Gris",
         "descripcion": "El cielo y el mar se funden en un tono apagado.",
         "conexiones": {"oeste": 58, "sur": 59, "este": 61},
         "bioma": "mar", "cantidad": 2},

    61: {"nombre": "Fosa de la Marea Negra",
         "descripcion": "El agua adquiere un tono oscuro y denso.",
         "conexiones": {"oeste": 60, "sur": 62, "este": 64},
         "bioma": "mar", "cantidad": 1},

    62: {"nombre": "Playa de la Arena Humeda",
         "descripcion": "La arena nunca llega a secarse, incluso bajo el sol.",
         "conexiones": {"oeste": 59, "norte": 61, "este": 63},
         "bioma": "mar", "cantidad": 2,
         "tesoro": True},

    63: {"nombre": "Gruta del Agua Resonante",
         "descripcion": "Cada gota crea ecos prolongados en la cueva.",
         "conexiones": {"oeste": 62, "este": 66},
         "bioma": "mar", "cantidad": 3},

    64: {"nombre": "Delta de los Canales Perdidos",
         "descripcion": "Un laberinto de agua donde es facil desorientarse.",
         "conexiones": {"oeste": 61, "este": 65},
         "bioma": "mar", "cantidad": 1,
         "tesoro": True},

    65: {"nombre": "Arrecife de las Espinas Blancas",
         "descripcion": "Formaciones afiladas sobresalen entre las olas.",
         "conexiones": {"oeste": 64, "este": 67, "sur": 66},
         "bioma": "mar", "cantidad": 2},

    66: {"nombre": "Pantano de la Lluvia Eterna",
         "descripcion": "La lluvia cae sin descanso sobre aguas fangosas.",
         "conexiones": {"oeste": 63, "norte": 65, "este": 68},
         "bioma": "mar", "cantidad": 3},

    67: {"nombre": "Caverna del Vapor Salino",
         "descripcion": "El aire caliente y salado dificulta la respiracion.",
         "conexiones": {"oeste": 65},
         "bioma": "mar", "cantidad": 1},

    68: {"nombre": "Laguna de los Reflejos Rotos",
         "descripcion": "La superficie muestra imagenes distorsionadas.",
         "conexiones": {"oeste": 66, "este": 69},
         "bioma": "mar", "cantidad": 2},

    69: {"nombre": "Sendero del Lodo Profundo",
         "descripcion": "Cada paso se hunde lentamente en el terreno blando.",
         "conexiones": {"oeste": 68, "este": 70},
         "bioma": "mar", "cantidad": 1},

    70: {"nombre": "Bahia de la Niebla Densa",
         "descripcion": "Una niebla espesa cubre completamente la vision.",
         "conexiones": {"oeste": 69, "este": 71},
         "bioma": "mar", "cantidad": 3,
         "hospital": True},

    71: {"nombre": "Cumbre del Leviatan",
         "descripcion": "Un acantilado imposible desde donde emerge el eco de una bestia ancestral.",
         "conexiones": {"oeste": 70, "este": 72, "norte": 150},
         "bioma": "mar", "cantidad": 1},

    72: {"nombre": "Cumbre del Kraken",
         "descripcion": "Un pico rocoso azotado por tormentas donde una sombra colosal se agita bajo las olas.",
         "conexiones": {"oeste": 71, "este": 73, "sur": 150},
         "bioma": "mar", "cantidad": 1,
         "encuentros": [("kraken", 1)]},

    # ── NIEVE (salas 73-149) ──────────────────────────────────
    73:  {"nombre": "Ventisca Eterna",
          "descripcion": "El viento ruge sin descanso, levantando cuchillas de nieve que desgarran la piel.",
          "conexiones": {"este": 74, "oeste": 72},
          "bioma": "nieve", "cantidad": 1},

    74:  {"nombre": "Bosque de Hielo Negro",
          "descripcion": "Árboles oscuros cubiertos de escarcha absorben la luz y el calor.",
          "conexiones": {"oeste": 76, "sur": 75, "este": 76},
          "bioma": "nieve", "cantidad": 2},

    75:  {"nombre": "Grieta del Frío Abisal",
          "descripcion": "Una fisura profunda exhala un aire tan frío que quema.",
          "conexiones": {"norte": 74},
          "bioma": "nieve", "cantidad": 2},

    76:  {"nombre": "Llanura del Silencio Blanco",
          "descripcion": "Una extensión infinita donde ningún sonido logra sobrevivir.",
          "conexiones": {"sur": 77, "oeste": 74},
          "bioma": "nieve", "cantidad": 1},

    77:  {"nombre": "Cementerio Congelado",
          "descripcion": "Cuerpos atrapados en hielo parecen observar a los vivos.",
          "conexiones": {"NORTE": 76, "este": 78},
          "bioma": "nieve", "cantidad": 2},

    78:  {"nombre": "Tormenta Errante",
          "descripcion": "Una ventisca viva se desplaza sin rumbo, devorando todo a su paso.",
          "conexiones": {"sur": 77, "norte": 79},
          "bioma": "nieve", "cantidad": 2},

    79:  {"nombre": "Picos del Desgarro",
          "descripcion": "Montañas afiladas como cuchillas sobresalen entre la nieve.",
          "conexiones": {"sur": 78, "norte": 98, "este": 80},
          "bioma": "nieve", "cantidad": 2},

    80:  {"nombre": "Hondonada del Eco Helado",
          "descripcion": "Cada sonido regresa distorsionado, como si algo respondiera.",
          "conexiones": {"oeste": 79, "norte": 97},
          "bioma": "nieve", "cantidad": 1},

    81:  {"nombre": "Río de Hielo Muerto",
          "descripcion": "Un río congelado bajo el cual algo se mueve lentamente.",
          "conexiones": {"este": 82},
          "bioma": "nieve", "cantidad": 2},

    82:  {"nombre": "Fauces de la Tormenta",
          "descripcion": "Un paso estrecho donde el viento ruge como una bestia.",
          "conexiones": {"oeste": 81, "norte": 83},
          "bioma": "nieve", "cantidad": 2},

    83:  {"nombre": "Campo de Estatuas Heladas",
          "descripcion": "Figuras humanas congeladas en gestos de terror.",
          "conexiones": {"sur": 82, "norte": 96, "este": 84, "oeste": 80},
          "bioma": "nieve", "cantidad": 2},

    84:  {"nombre": "Abismo Nevado",
          "descripcion": "Un vacío oculto bajo la nieve, listo para tragar incautos.",
          "conexiones": {"sur": 85, "norte": 95, "oeste": 83},
          "bioma": "nieve", "cantidad": 1},

    85:  {"nombre": "Cumbre del Viento Cortante",
          "descripcion": "El aire corta como cuchillas invisibles.",
          "conexiones": {"este": 86, "norte": 84},
          "bioma": "nieve", "cantidad": 2},

    86:  {"nombre": "Valle de las Sombras Blancas",
          "descripcion": "Siluetas se mueven bajo la tormenta, pero nunca se acercan.",
          "conexiones": {"oeste": 85, "norte": 87, "este": 89},
          "bioma": "nieve", "cantidad": 2},

    87:  {"nombre": "Ruinas Congeladas",
          "descripcion": "Estructuras antiguas atrapadas en hielo eterno.",
          "conexiones": {"sur": 86},
          "bioma": "nieve", "cantidad": 2,
          "hospital": True},

    88:  {"nombre": "Paso del Susurro Gélido",
          "descripcion": "Voces heladas parecen guiarte… o perderte.",
          "conexiones": {"sur": 89},
          "bioma": "nieve", "cantidad": 1},

    89:  {"nombre": "Glaciar Viviente",
          "descripcion": "El hielo cruje y se desplaza como si respirara.",
          "conexiones": {"oeste": 86, "norte": 88},
          "bioma": "nieve", "cantidad": 2},

    90:  {"nombre": "Fosa del Olvido Blanco",
          "descripcion": "Quienes caen aquí desaparecen sin dejar rastro.",
          "conexiones": {"norte": 91},
          "bioma": "nieve", "cantidad": 2},

    91:  {"nombre": "Torres de Escarcha",
          "descripcion": "Columnas de hielo crecen hacia el cielo gris.",
          "conexiones": {"sur": 90, "norte": 92},
          "bioma": "nieve", "cantidad": 2},

    92:  {"nombre": "Velo de Nieve Infinita",
          "descripcion": "La visibilidad desaparece por completo.",
          "conexiones": {"sur": 91, "norte": 101, "oeste": 93},
          "bioma": "nieve", "cantidad": 1},

    93:  {"nombre": "Lago de Cristal Helado",
          "descripcion": "Superficie transparente que oculta profundidades oscuras.",
          "conexiones": {"este": 92, "norte": 102},
          "bioma": "nieve", "cantidad": 2},

    94:  {"nombre": "Bosque de Agujas Gélidas",
          "descripcion": "Espinas de hielo sobresalen del suelo como trampas.",
          "conexiones": {"oeste": 95, "norte": 103},
          "bioma": "nieve", "cantidad": 2,
          "hospital": True},

    95:  {"nombre": "Furia Blanca",
          "descripcion": "Una tormenta que parece tener voluntad propia.",
          "conexiones": {"sur": 84, "norte": 104, "este": 94},
          "bioma": "nieve", "cantidad": 2},

    96:  {"nombre": "Caverna de Escarcha Viva",
          "descripcion": "El hielo late con una energía inquietante.",
          "conexiones": {"sur": 83, "norte": 105, "oeste": 97},
          "bioma": "nieve", "cantidad": 2},

    97:  {"nombre": "Paso del Último Aliento",
          "descripcion": "El aire es tan frío que respirar duele.",
          "conexiones": {"sur": 80, "este": 96},
          "bioma": "nieve", "cantidad": 1},

    98:  {"nombre": "Colmillos del Invierno",
          "descripcion": "Formaciones de hielo puntiagudas rodean el camino.",
          "conexiones": {"sur": 79, "norte": 107, "oeste": 99},
          "bioma": "nieve", "cantidad": 2},

    99:  {"nombre": "Valle del Sueño Helado",
          "descripcion": "Un frío que induce un sueño mortal.",
          "conexiones": {"este": 98, "norte": 108},
          "bioma": "nieve", "cantidad": 2},

    100: {"nombre": "Niebla Blanca",
          "descripcion": "Una bruma espesa oculta todo peligro.",
          "conexiones": {"norte": 109},
          "bioma": "nieve", "cantidad": 1},

    101: {"nombre": "Cumbre Quebrada",
          "descripcion": "Fragmentos de hielo caen constantemente desde arriba.",
          "conexiones": {"sur": 92, "norte": 118},
          "bioma": "nieve", "cantidad": 2},

    102: {"nombre": "Territorio del Frío Antiguo",
          "descripcion": "Una energía ancestral congela todo lo que toca.",
          "conexiones": {"sur": 93, "norte": 117},
          "bioma": "nieve", "cantidad": 2},

    103: {"nombre": "Sendero del Hielo Negro",
          "descripcion": "Un camino oscuro que no refleja la luz.",
          "conexiones": {"sur": 94, "oeste": 104},
          "bioma": "nieve", "cantidad": 2},

    104: {"nombre": "Vigilantes de Escarcha",
          "descripcion": "Figuras inmóviles parecen seguir cada movimiento.",
          "conexiones": {"sur": 95, "norte": 115, "este": 103, "oeste": 105},
          "bioma": "nieve", "cantidad": 2},

    105: {"nombre": "Desierto Blanco",
          "descripcion": "Dunas de nieve reemplazan a la arena.",
          "conexiones": {"sur": 96, "este": 104, "oeste": 106},
          "bioma": "nieve", "cantidad": 1,
          "hospital": True},

    106: {"nombre": "Garganta del Viento Helado",
          "descripcion": "Corrientes de aire atraviesan como cuchillas.",
          "conexiones": {"este": 105, "oeste": 107},
          "bioma": "nieve", "cantidad": 2},

    107: {"nombre": "Ruinas del Invierno Eterno",
          "descripcion": "Restos de una civilización atrapada en hielo.",
          "conexiones": {"sur": 98, "norte": 112, "este": 106, "oeste": 108},
          "bioma": "nieve", "cantidad": 2},

    108: {"nombre": "Campo de Fragmentos Gélidos",
          "descripcion": "El suelo está cubierto de cristales afilados.",
          "conexiones": {"sur": 99, "norte": 111, "este": 107, "oeste": 109},
          "bioma": "nieve", "cantidad": 2},

    109: {"nombre": "Pozo de Escarcha",
          "descripcion": "Un agujero profundo que emana frío absoluto.",
          "conexiones": {"sur": 100, "norte": 110, "este": 108},
          "bioma": "nieve", "cantidad": 1},

    110: {"nombre": "Travesía del Frío Mortal",
          "descripcion": "Cada paso drena lentamente la vida.",
          "conexiones": {"sur": 109, "norte": 111},
          "bioma": "nieve", "cantidad": 2},

    111: {"nombre": "Tormenta Estática",
          "descripcion": "El aire está cargado de energía helada.",
          "conexiones": {"sur": 108, "este": 112},
          "bioma": "nieve", "cantidad": 2},

    112: {"nombre": "Cascada Congelada",
          "descripcion": "El agua quedó atrapada en pleno descenso.",
          "conexiones": {"sur": 107, "norte": 125, "oeste": 111},
          "bioma": "nieve", "cantidad": 1},

    113: {"nombre": "Círculo de Hielo Antiguo",
          "descripcion": "Formaciones perfectas rodean un centro vacío.",
          "conexiones": {"sur": 124, "este": 114},
          "bioma": "nieve", "cantidad": 2},

    114: {"nombre": "Bosque de Sombras Heladas",
          "descripcion": "Sombras que no pertenecen a nada visible.",
          "conexiones": {"oeste": 113, "norte": 123},
          "bioma": "nieve", "cantidad": 2,
          "hospital": True},

    115: {"nombre": "Frontera del Frío Absoluto",
          "descripcion": "Más allá de este punto, nada sobrevive.",
          "conexiones": {"sur": 104, "norte": 122, "este": 116},
          "bioma": "nieve", "cantidad": 2},

    116: {"nombre": "Vértice Nevado",
          "descripcion": "Un punto donde el viento converge violentamente.",
          "conexiones": {"oeste": 115, "norte": 121},
          "bioma": "nieve", "cantidad": 2},

    117: {"nombre": "Hogar de la Escarcha",
          "descripcion": "El frío parece originarse aquí.",
          "conexiones": {"sur": 102, "norte": 120},
          "bioma": "nieve", "cantidad": 1},

    118: {"nombre": "Sendero de los Perdidos",
          "descripcion": "Huellas que aparecen y desaparecen.",
          "conexiones": {"sur": 101, "norte": 119},
          "bioma": "nieve", "cantidad": 2},

    119: {"nombre": "Falla Glacial",
          "descripcion": "El suelo se abre en grietas heladas.",
          "conexiones": {"sur": 118, "norte": 128},
          "bioma": "nieve", "cantidad": 2},

    120: {"nombre": "Campo de Huesos Congelados",
          "descripcion": "Restos atrapados en hielo eterno.",
          "conexiones": {"sur": 117, "norte": 129, "oeste": 121},
          "bioma": "nieve", "cantidad": 2},

    121: {"nombre": "Tormenta Silenciosa",
          "descripcion": "La nieve cae sin hacer ningún sonido.",
          "conexiones": {"sur": 116, "norte": 130, "oeste": 122, "este": 120},
          "bioma": "nieve", "cantidad": 1},

    122: {"nombre": "Núcleo de Hielo Vivo",
          "descripcion": "Una fuente de energía helada palpita.",
          "conexiones": {"sur": 115, "norte": 131, "oeste": 123, "este": 121},
          "bioma": "nieve", "cantidad": 2},

    123: {"nombre": "Paso de los Colosos Helados",
          "descripcion": "Sombras gigantes se mueven entre la nieve.",
          "conexiones": {"sur": 114, "norte": 132, "oeste": 124, "este": 122},
          "bioma": "nieve", "cantidad": 2},

    124: {"nombre": "Mar de Escarcha",
          "descripcion": "Una extensión ondulante de hielo sólido.",
          "conexiones": {"sur": 113, "norte": 133, "oeste": 125, "este": 123},
          "bioma": "nieve", "cantidad": 2},

    125: {"nombre": "Colina del Último Suspiro",
          "descripcion": "El frío roba el aliento lentamente.",
          "conexiones": {"este": 124, "norte": 134},
          "bioma": "nieve", "cantidad": 1},

    126: {"nombre": "Catedral de Hielo Roto",
          "descripcion": "Estructuras que recuerdan a un templo destruido.",
          "conexiones": {"oeste": 127, "norte": 135},
          "bioma": "nieve", "cantidad": 2},

    127: {"nombre": "Velo del Olvido",
          "descripcion": "La memoria se desvanece entre la nieve.",
          "conexiones": {"este": 126, "norte": 136},
          "bioma": "nieve", "cantidad": 2},

    128: {"nombre": "Fauces Heladas",
          "descripcion": "Una grieta parece querer devorar el mundo.",
          "conexiones": {"sur": 119, "norte": 145},
          "bioma": "nieve", "cantidad": 2},

    129: {"nombre": "Bosque del Frío Susurrante",
          "descripcion": "El viento parece hablar entre las ramas congeladas.",
          "conexiones": {"sur": 120, "norte": 144},
          "bioma": "nieve", "cantidad": 2},

    130: {"nombre": "Campo de Escarcha Oscura",
          "descripcion": "El hielo refleja una luz enfermiza.",
          "conexiones": {"sur": 121, "norte": 143},
          "bioma": "nieve", "cantidad": 2},

    131: {"nombre": "Trampa de Nieve Profunda",
          "descripcion": "El suelo cede bajo el peso sin aviso.",
          "conexiones": {"sur": 122, "norte": 142},
          "bioma": "nieve", "cantidad": 1,
          "hospital": True},

    132: {"nombre": "Cumbre del Olvido",
          "descripcion": "Quienes llegan aquí olvidan por qué vinieron.",
          "conexiones": {"sur": 122, "norte": 142, "oeste": 133},
          "bioma": "nieve", "cantidad": 2},

    133: {"nombre": "Rugido Blanco",
          "descripcion": "El viento ensordece cualquier otro sonido.",
          "conexiones": {"sur": 124, "norte": 140, "este": 132},
          "bioma": "nieve", "cantidad": 2},

    134: {"nombre": "Valle del Frío Eterno",
          "descripcion": "Nunca deja de nevar en este lugar.",
          "conexiones": {"sur": 125, "norte": 139, "oeste": 135},
          "bioma": "nieve", "cantidad": 2},

    135: {"nombre": "Sombras Bajo el Hielo",
          "descripcion": "Figuras oscuras se mueven bajo la superficie.",
          "conexiones": {"sur": 126, "este": 134},
          "bioma": "nieve", "cantidad": 2},

    136: {"nombre": "Paso de la Escarcha Mortal",
          "descripcion": "Cada segundo expuesto es un riesgo.",
          "conexiones": {"sur": 127},
          "bioma": "nieve", "cantidad": 2},

    137: {"nombre": "Caverna del Viento Helado",
          "descripcion": "Corrientes internas recorren el interior sin cesar.",
          "conexiones": {"este": 138},
          "bioma": "nieve", "cantidad": 2},

    138: {"nombre": "Campos del Silencio",
          "descripcion": "El mundo parece detenido aquí.",
          "conexiones": {"oeste": 137, "este": 139},
          "bioma": "nieve", "cantidad": 1},

    139: {"nombre": "Colapso Glacial",
          "descripcion": "El terreno cruje y se derrumba constantemente.",
          "conexiones": {"oeste": 138, "este": 140, "sur": 134},
          "bioma": "nieve", "cantidad": 2},

    140: {"nombre": "Tormenta del Norte",
          "descripcion": "Una ventisca que nunca abandona esta zona.",
          "conexiones": {"sur": 133, "oeste": 139, "este": 141},
          "bioma": "nieve", "cantidad": 2},

    141: {"nombre": "Grieta del Último Invierno",
          "descripcion": "Un frío ancestral emana desde lo profundo.",
          "conexiones": {"sur": 132, "norte": 146, "este": 142, "oeste": 140},
          "bioma": "nieve", "cantidad": 2},

    142: {"nombre": "Altar de Hielo Antiguo",
          "descripcion": "Un lugar olvidado donde el frío es venerado.",
          "conexiones": {"sur": 131, "oeste": 141, "este": 143},
          "bioma": "nieve", "cantidad": 2,
          "hospital": True},

    143: {"nombre": "Sendero del Frío Infinito",
          "descripcion": "Un camino que parece no tener final.",
          "conexiones": {"sur":    130, "oeste": 142},
          "bioma": "nieve", "cantidad": 2},

    144: {"nombre": "Cúpula de Escarcha",
          "descripcion": "Una formación cerrada de hielo perfecto.",
          "conexiones": {"sur": 129, "este": 145},
          "bioma": "nieve", "cantidad": 1},

    145: {"nombre": "Ruinas del Viento Blanco",
          "descripcion": "Restos arrasados por tormentas eternas.",
          "conexiones": {"sur": 128, "norte": 146, "oeste": 144},
          "bioma": "nieve", "cantidad": 2},

    146: {"nombre": "Frontera del Vacío Helado",
          "descripcion": "Más allá solo hay frío y nada más.",
          "conexiones": {"sur": 141, "norte": 148, "este": 145, "oeste": 147},
          "bioma": "nieve", "cantidad": 2},

    147: {"nombre": "Cráter de Hielo Vivo",
          "descripcion": "Un impacto antiguo que aún emana energía.",
          "conexiones": {"este": 146, "norte": 148},
          "bioma": "nieve", "cantidad": 2,
          "hospital": True,
          "tienda": True},

    148: {"nombre": "Trono del Invierno",
          "descripcion": "Un asiento de poder donde el frío gobierna todo.",
          "conexiones": {"sur": 146, "oeste": 147},
          "encuentros": [("alpha", 1)]},

    149: {"nombre": "Oasis tranquilo",
          "descripcion": "Un sitio en el que descansar, prepàrate para la batalla final.",
         "conexiones": {"sur": 24, "oeste": 32},
         "hospital": True,
         "tienda": True},

    150: {"nombre": "Trono del Invierno",
          "descripcion": "Un asiento de poder donde el frío gobierna todo.",
          "conexiones": {"sur": 71, "norte": 72},
          "hospital": True,
          "tienda": True},
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
        self.acertijos_completados = set()  # salas con acertijos completados
        self.acertijo_actual = 0  # índice del acertijo actual en la sala

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
            "xpMax":         xp_para_subir(self.nivel), "monedas": self.monedas,
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
            msg = await asyncio.wait_for(self.input_queue.get(), timeout=60)
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
    for p in list(jugadores_conectados):
        if p.sala_id == sala_id and p != excluir:
            try:
                await p.send(texto)
            except Exception:
                pass

async def broadcast_todos(texto):
    for p in list(jugadores_conectados):
        try:
            await p.send(texto)
        except Exception:
            pass

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

def xp_para_subir(nivel: int) -> int:
    """XP necesaria para pasar del nivel dado al siguiente. +20 por nivel."""
    return 150 + (nivel - 1) * 20


async def dar_xp(player: Player, cantidad: int):
    player.xp += cantidad
    umbral = xp_para_subir(player.nivel)
    await player.send(f"  +{cantidad} XP  ({player.xp}/{umbral})")
    while player.xp >= xp_para_subir(player.nivel):
        umbral = xp_para_subir(player.nivel)
        player.xp      -= umbral
        player.nivel   += 1
        player.monedas += MONEDAS_SUBIDA
        p = player.personaje
        p["vidaMax"]   += 10
        p["danioBase"] += 5
        p["manaMax"]   += 5
        p["vidaActual"] = p["vidaMax"]
        proximo = xp_para_subir(player.nivel)
        await player.send(
            f"\n  ╔══════════════════════════════╗\n"
            f"  ║  SUBISTE AL NIVEL {player.nivel:>2}!        ║\n"
            f"  ║  +{MONEDAS_SUBIDA} monedas  Total:{player.monedas:<5}      ║\n"
            f"  ║  HP:{p['vidaMax']}  Dano:{p['danioBase']}  Mana:{p['manaMax']}   ║\n"
            f"  ║  Siguiente nivel: {proximo} XP          ║\n"
            f"  ╚══════════════════════════════╝"
        )
        await broadcast_todos(f"  {player.nombre} subio al nivel {player.nivel}!")
    await notify_web_session(player)
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
            f"  Nivel {player.nivel}  XP:{player.xp}/{xp_para_subir(player.nivel)}  Monedas:{player.monedas}\n"
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
# SISTEMA DE ACERTIJOS
# ============================================================

async def iniciar_acertijos(player: Player):
    """Inicia la secuencia de acertijos para el jugador en su sala actual."""
    sala_id = player.sala_id
    
    if sala_id not in SALAS_ACERTIJOS:
        return False
    
    # Verificar si ya completó esta sala de acertijos
    if sala_id in player.acertijos_completados:
        return False
    
    indices_acertijos = SALAS_ACERTIJOS[sala_id]
    player.acertijo_actual = 0
    
    await player.send("\n  🧩 Has entrado en una sala de acertijos!")
    await player.send("  Debes responder correctamente 3 acertijos para avanzar.")
    await player.send("  Si fallas, deberás volver a empezar desde el primero.\n")
    
    # Iniciar primer acertijo
    await mostrar_acertijo(player, indices_acertijos[0])
    return True


async def mostrar_acertijo(player: Player, indice_acertijo: int):
    """Muestra un acertijo específico al jugador vía popup."""
    acertijo = ACERTIJOS[indice_acertijo]
    
    # Enviar popup de acertijo al cliente
    try:
        await player.ws.send_json({
            "type": "acertijo",
            "pregunta": acertijo["pregunta"],
            "opciones": acertijo["opciones"],
            "indice": player.acertijo_actual,
            "total": 3
        })
    except Exception as e:
        print(f"[ACERTIJO] Error enviando popup: {e}")
        # Fallback: mostrar en texto plano
        await player.send(f"\n  🧩 ACERTIJO {player.acertijo_actual + 1}/3:")
        await player.send(f"  {acertijo['pregunta']}")
        for opt in acertijo["opciones"]:
            await player.send(f"    {opt}")
        await player.send("  Escribe la letra de tu respuesta (A, B, C o D):")


async def verificar_respuesta_acertijo(player: Player, respuesta: str) -> bool:
    """Verifica la respuesta del jugador al acertijo actual."""
    sala_id = player.sala_id
    
    if sala_id not in SALAS_ACERTIJOS:
        return False
    
    indices_acertijos = SALAS_ACERTIJOS[sala_id]
    indice_actual = indices_acertijos[player.acertijo_actual]
    acertijo = ACERTIJOS[indice_actual]
    
    respuesta_limpia = respuesta.strip().lower()
    
    # Verificar si la respuesta es válida (a, b, c, d)
    if respuesta_limpia not in ["a", "b", "c", "d"]:
        await player.send("  Responde con A, B, C o D.")
        return False
    
    if respuesta_limpia == acertijo["respuesta"]:
        # Respuesta correcta
        await player.send(f"  ✅ ¡Correcto! La respuesta era {acertijo['letra_correcta']}.")
        
        player.acertijo_actual += 1
        
        # ¿Completó todos los acertijos?
        if player.acertijo_actual >= 3:
            await player.send("\n  🎉 ¡Has completado todos los acertijos! El camino está despejado.")
            player.acertijos_completados.add(sala_id)
            player.salas_limpias.add(sala_id)  # Marcar sala como limpia para poder avanzar
            
            # Notificar a otros jugadores en la sala
            await broadcast_sala(sala_id, f"  {player.nombre} ha resuelto los acertijos y despejado el camino.")
            
            # Enviar señal de cierre de popup
            try:
                await player.ws.send_json({"type": "acertijo_end", "exito": True})
            except Exception:
                pass
            return True
        else:
            # Siguiente acertijo
            await player.send(f"\n  Siguiente acertijo...")
            await mostrar_acertijo(player, indices_acertijos[player.acertijo_actual])
            return False
    else:
        # Respuesta incorrecta - reiniciar
        await player.send(f"  ❌ ¡Incorrecto! La respuesta correcta era {acertijo['letra_correcta']}.")
        await player.send("  Debes volver a empezar desde el primer acertijo...\n")
        
        # Reiniciar progreso de acertijos en esta sala
        player.acertijo_actual = 0
        await mostrar_acertijo(player, indices_acertijos[0])
        return False


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

    # Indicar si hay peligro o acertijos
    if sala.get("acertijos"):
        lineas.append("  🧩 Esta sala tiene acertijos. Debes resolverlos para avanzar.")
        # Iniciar acertijos automáticamente al entrar
        asyncio.create_task(iniciar_acertijos(player))
    elif "bioma" in sala or sala.get("encuentros"):
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

    # ── Bloqueo por acertijos ────────────────────────────────
    if sala_actual.get("acertijos") and player.sala_id not in player.acertijos_completados:
        await player.send(
            "  🧩 ¡Debes resolver los acertijos de esta sala para poder avanzar!\n"
            "  Responde correctamente los 3 acertijos para despejar el camino."
        )
        # Reiniciar acertijos si no los ha completado
        if player.sala_id not in SALAS_ACERTIJOS or player.acertijo_actual >= 3:
            player.acertijo_actual = 0
        asyncio.create_task(iniciar_acertijos(player))
        return

    # ── Bloqueo por monstruos (solo si hay enemigos reales) ────────────────────────────────
    tiene_enemigos_reales = "bioma" in sala_actual or bool(sala_actual.get("encuentros"))
    if tiene_enemigos_reales and player.sala_id not in player.salas_limpias:
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
        await broadcast_sala(sala_id, "\n  DERROTA.")
    else:
        await broadcast_sala(sala_id, "\n  VICTORIA!")
        xp = sum(xp_de_tier(e.get("tier", "Base")) for e in combate.enemigos)
        await broadcast_sala(sala_id, f"  {xp} XP para cada superviviente.")
        for p in combate.jugadores_vivos():
            await dar_xp(p, xp)
            p.personaje["vidaActual"] = min(p.personaje["vidaActual"] + 20, p.personaje["vidaMax"])
            p.salas_limpias.add(sala_id)
            await p.send_status()   # actualizar HP tras +20
        await broadcast_sala(sala_id, "  +20 HP a cada superviviente.")
        await broadcast_sala(sala_id, "  El camino está despejado. Puedes avanzar.")

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
    Timeout de 60s por turno — si no responde, pasa turno automáticamente.
    """
    if player.personaje["vidaActual"] <= 0:
        combate.acciones[player.id] = "3"
        return

    await player.send(
        "  1-Atacar  2-Especial  3-Pasar  4-Objeto\n"
        "  decir <msg>  |  g <msg>"
    )

    deadline = asyncio.get_event_loop().time() + 60  # 60s por turno

    while True:
        tiempo_restante = max(0.1, deadline - asyncio.get_event_loop().time())
        try:
            raw = await asyncio.wait_for(player.recv(), timeout=tiempo_restante)
        except asyncio.TimeoutError:
            combate.acciones[player.id] = "3"
            await player.send("  ⏱ Tiempo agotado — turno pasado automáticamente.")
            return

        # Desconexión durante combate → pasar turno automáticamente
        if raw is None:
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
            await player.send("  Que objeto usar? (Enter=cancelar, o escribe vida/dano/gema):")
            try:
                n = await asyncio.wait_for(player.recv(), timeout=30)
            except asyncio.TimeoutError:
                n = None
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
    # Auto-cancelar el duelo si no es respon en 60s
    async def _timeout_duelo():
        await asyncio.sleep(60)
        if objetivo.duelo_pendiente and objetivo.duelo_pendiente.get("retador") is player:
            objetivo.duelo_pendiente = None
            asyncio.create_task(player.send(f"  El duelo con {objetivo.nombre} expiró (sin respuesta)."))
            asyncio.create_task(objetivo.send(f"  La invitación de duelo de {player.nombre} expiró."))
    asyncio.create_task(_timeout_duelo())

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


# Rate limiting: max 1 comando cada 0.5s per jugador
_last_cmd_time: dict = {}

async def procesar_comando(player: Player, cmd: str):
    # Rate limit
    now = asyncio.get_event_loop().time()
    last = _last_cmd_time.get(id(player), 0)
    if now - last < 0.5:
        return
    _last_cmd_time[id(player)] = now

    partes = cmd.lower().strip().split()
    if not partes:
        return
    ac = partes[0]

    # ── Verificar si está en modo acertijos ─────────────────────────
    sala = SALAS.get(player.sala_id, {})
    if sala.get("acertijos") and player.sala_id not in player.acertijos_completados:
        # El jugador está respondiendo a un acertijo
        if len(cmd.strip()) > 0 and cmd.strip().lower() in ["a", "b", "c", "d"]:
            await verificar_respuesta_acertijo(player, cmd.strip())
            return
        # Comandos permitidos durante acertijos
        if ac not in ["decir", "d", "g", "stats", "estado", "jugadores", "who", "ayuda"]:
            await player.send("  🧩 Estás resolviendo acertijos. Responde A, B, C o D, o usa 'decir' para hablar.")
            return

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
            acertijo_status = ""
            if p.sala_id in SALAS_ACERTIJOS and p.sala_id not in p.acertijos_completados:
                acertijo_status = " [🧩Acertijos]"
            lineas.append(f"  - {p.nombre} [Nv.{p.nivel} {p.personaje['nombreClase']}] ({st}){grp}{acertijo_status}")
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
            f"  Nivel {player.nivel}  XP:{player.xp}/{xp_para_subir(player.nivel)}  Monedas:{player.monedas}")

    elif ac in ("guardar", "save"):
        await guardar_cuenta_async(player)
        await player.send("  Progreso guardado.")

    elif ac == "ayuda":
        await player.send(
            "\n  MOVER:    n s e o  (norte sur este oeste)\n"
            "           ⚠ Derrota los monstruos de la sala para avanzar\n"
            "           🧩 Resuelve los acertijos en salas especiales\n"
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
    except ValueError as e:
        print(f"[GAME] Error cargando cuenta {usuario}: {e}")
        await player.send(f"  Error cargando tu cuenta: {e}\n  Contacta con el administrador.")
        jugadores_conectados.remove(player)
        rt.cancel()
        return

    await player.send(
        f"\n  Bienvenido de vuelta, {player.nombre}!\n"
        f"  Nivel {player.nivel}  XP:{player.xp}/{xp_para_subir(player.nivel)}  Monedas:{player.monedas}\n"
        f"  HP:{player.personaje['vidaActual']}/{player.personaje['vidaMax']}  "
        f"Mana:{player.personaje['manaActual']}/{player.personaje['manaMax']}"
    )
    await player.send_status()
    # Enviar leaderboard global al conectar
    lb = await get_leaderboard_async()
    try:
        await player.ws.send_json({"type": "leaderboard", "ranking": lb})
    except Exception:
        pass
    await broadcast_todos(f"\n  {player.nombre} se unio al dungeon!")
    await broadcast_players_to_web()
    await describir_sala(player)

    try:
        while True:
            if player.combate and player.combate.estado != EstadoCombate.FINALIZADO:
                await asyncio.sleep(0.05)
                continue
            raw = await player.recv()
            if raw is None:
                break
            if not raw.strip():
                continue
            try:
                await procesar_comando(player, raw.strip())
            except Exception as e:
                print(f"[CMD] Error en '{raw.strip()}': {e}")
                try:
                    await player.send("  Error procesando comando.")
                except Exception:
                    pass

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
                "xpMax": xp_para_subir(player_online.nivel), "monedas": player_online.monedas,
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
                "xpMax": xp_para_subir(save.get("nivel",1)), "monedas":save.get("monedas", 0),
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
            es_acertijos = s.get("acertijos", False)
            map_data[str(s_id)] = {
                "nombre": s["nombre"],    "bioma":    s.get("bioma"),
                "tienda": s.get("tienda", False),
                "hospital": s.get("hospital", False),
                "boss": tiene_boss,
                "acertijos": es_acertijos,
                "segura": not ("bioma" in s or bool(s.get("encuentros")) or es_acertijos),
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
.bf-hp{background:var(--red);}.bf-mp{background:var(--mana);}
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
.gg{color:var(--text);}.gp2{color:var(--blue);}.gc{color:#e67e22;}
.gv{color:var(--gold);font-weight:bold;}.gd{color:var(--red);}
.gi{color:var(--teal);}.gs{color:var(--dim);font-style:italic;}
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
.cn-s{color:var(--green);}.cn-g{color:var(--orange);}.cn-gr{color:var(--mana);}
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
.cb.dir{border-color:#1a2a3a;color:var(--blue);}.cb.dir:hover{background:#08101a;}
.cb.atk{border-color:#1a3a1a;color:var(--green);}.cb.atk:hover{background:#081408;}
.cb.pvp{border-color:#3a1a1a;color:var(--red);}.cb.pvp:hover{background:#180808;}
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
.hv{color:var(--text);}.hclose{margin-top:10px;background:var(--bg3);border:1px solid var(--border);
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

/* ACERTIJO POPUP */
#acertijo-popup{display:none;position:fixed;top:50%;left:50%;
                transform:translate(-50%,-50%);
                background:var(--bg2);border:2px solid var(--purple);border-radius:8px;
                padding:20px 24px;z-index:600;min-width:320px;max-width:400px;text-align:center;
                box-shadow:0 6px 30px rgba(0,0,0,.7);}
#acertijo-popup.open{display:block;}
#acertijo-title{color:var(--purple);font-size:14px;font-weight:bold;margin-bottom:10px;}
#acertijo-counter{color:var(--dim);font-size:10px;margin-bottom:8px;}
#acertijo-pregunta{color:var(--text);font-size:12px;margin-bottom:15px;line-height:1.4;}
#acertijo-opciones{display:flex;flex-direction:column;gap:6px;margin-bottom:15px;}
.acertijo-opt{background:var(--bg3);border:1px solid var(--border);color:var(--text);
              padding:8px 12px;font-size:11px;cursor:pointer;border-radius:4px;
              font-family:monospace;text-align:left;transition:all .15s;}
.acertijo-opt:hover{background:var(--border);border-color:var(--purple);}
.acertijo-opt.correct{background:#0d3a0d;border-color:var(--green);color:var(--green);}
.acertijo-opt.wrong{background:#3a0d0d;border-color:var(--red);color:var(--red);}
#acertijo-msg{font-size:10px;min-height:14px;margin-top:8px;}

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
    <svg id="map-svg-full" viewBox="0 0 860 820" width="740" height="820" xmlns="http://www.w3.org/2000/svg">
      <defs><filter id="glowf"><feGaussianBlur stdDeviation="4" result="b"/>
        <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter></defs>
      <!-- NIEVE -->
      <rect x="5" y="5" width="810" height="310" rx="5" fill="#06090f" stroke="#1a3a4a" stroke-width="1"/>
      <text x="14" y="20" fill="#4a6a7a" font-size="9" font-family="monospace">❄ NIEVE (73–148)</text>
      <!-- MAR -->
      <rect x="5" y="320" width="810" height="280" rx="5" fill="#06060f" stroke="#1a2a4a" stroke-width="1"/>
      <text x="14" y="335" fill="#1565c0" font-size="9" font-family="monospace">🌊 MAR (33–72)</text>
      <!-- OASIS -->
      <rect x="360" y="608" width="80" height="38" rx="3" fill="#081408" stroke="#2e7d32" stroke-width="1"/>
      <text x="400" y="631" fill="#2e7d32" font-size="8" font-family="monospace" text-anchor="middle">🌴 OASIS</text>
      <!-- TUTORIAL -->
      <rect x="650" y="608" width="160" height="38" rx="3" fill="#0d0d0d" stroke="#444" stroke-width="1"/>
      <text x="730" y="631" fill="#888" font-size="8" font-family="monospace" text-anchor="middle">📚 TUTORIAL</text>
      <!-- DESIERTO -->
      <rect x="5" y="650" width="810" height="255" rx="5" fill="#0f0700" stroke="#302000" stroke-width="1"/>
      <text x="14" y="666" fill="#8b6914" font-size="9" font-family="monospace">🏜 DESIERTO (1–32)</text>
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
    <div class="hr"><span class="hk">A/B/C/D</span><span class="hv">Responder acertijos</span></div>
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

<!-- ACERTIJO POPUP -->
<div id="acertijo-popup">
  <div id="acertijo-title">🧩 ACERTIJO</div>
  <div id="acertijo-counter"></div>
  <div id="acertijo-pregunta"></div>
  <div id="acertijo-opciones"></div>
  <div id="acertijo-msg"></div>
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
      <div class="sp-emoji" id="s-emoji" style="font-size:28px;text-align:center;margin-bottom:4px">⚔️</div>
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
      <svg id="map-svg-mini" viewBox="0 0 860 820" xmlns="http://www.w3.org/2000/svg">
        <rect x="5" y="5"   width="840" height="312" rx="4" fill="#06090f" stroke="#1a3a4a" stroke-width="1"/>
        <rect x="5" y="320" width="840" height="218" rx="4" fill="#06060f" stroke="#1a2a4a" stroke-width="1"/>
        <rect x="5" y="540" width="840" height="8"   rx="2" fill="#081408" stroke="#2e7d32" stroke-width="1"/>
        <rect x="5" y="552" width="840" height="205" rx="4" fill="#0f0700" stroke="#302000" stroke-width="1"/>
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
/* MAP DATA — 150 salas (Tutorial + Desierto + Mar + Nieve + Oasis) */
const RPOS={
 /* TUTORIAL */
 "0.1":{x:760,y:790,n:"Tutorial: Combate",b:"tutorial"},
 "0.2":{x:796,y:760,n:"Tutorial: Objetos",b:"tutorial"},
 "0.3":{x:760,y:730,n:"Tutorial: Estructuras",b:"tutorial"},
 "0.4":{x:796,y:730,n:"Tutorial: UI",b:"tutorial"},
 /* DESIERTO */
 1:{x:28,y:700,n:"North Mass",b:"desierto"},
 2:{x:80,y:700,n:"Dunas del Norte",b:"desierto"},
 3:{x:132,y:700,n:"Ruinas del Desierto",b:"desierto"},
 4:{x:184,y:700,n:"Ciudad Abrasada",b:"desierto",boss:true},
 5:{x:236,y:700,n:"Valle Muerto",b:"desierto"},
 6:{x:288,y:700,n:"Oasis",b:"safe"},
 7:{x:340,y:700,n:"Sala del Viento",b:"desierto"},
 8:{x:392,y:700,n:"Camara del Oasis",b:"desierto"},
 9:{x:444,y:700,n:"Salon del Sol",b:"desierto"},
 10:{x:496,y:700,n:"Cripta de las Dunas",b:"desierto"},
 11:{x:548,y:700,n:"Caravana Fantasma",b:"desierto"},
 12:{x:600,y:700,n:"Fosa de Titanes",b:"desierto"},
 13:{x:652,y:700,n:"Altar del Soberano",b:"desierto",boss:true},
 14:{x:704,y:700,n:"Extension de Azhar",b:"desierto"},
 15:{x:756,y:700,n:"Mar de Dunas",b:"desierto"},
 16:{x:808,y:700,n:"Vestigios Enterrados",b:"desierto"},
 17:{x:28,y:652,n:"Santuario Carmesi",b:"desierto"},
 18:{x:80,y:652,n:"Sepulcro de Colosos",b:"desierto"},
 19:{x:132,y:652,n:"Trono del Abismo",b:"desierto"},
 20:{x:184,y:652,n:"Llanura de Fuego",b:"desierto"},
 21:{x:236,y:652,n:"Dunas del Murmullo",b:"desierto"},
 22:{x:288,y:652,n:"Columnas del Olvido",b:"desierto"},
 23:{x:340,y:652,n:"Templo de Sangre",b:"desierto"},
 24:{x:392,y:652,n:"Abismo de los Caidos",b:"desierto"},
 25:{x:444,y:652,n:"Trono del Devastador",b:"desierto",boss:true},
 26:{x:496,y:652,n:"Horizonte Quebrado",b:"desierto"},
 27:{x:548,y:652,n:"Dunas del Hambre",b:"desierto"},
 28:{x:600,y:652,n:"Ruinas del Eco",b:"desierto"},
 29:{x:652,y:652,n:"Santuario de la Marca",b:"desierto"},
 30:{x:704,y:652,n:"Campos de Huesos",b:"desierto"},
 31:{x:756,y:652,n:"Trono Ultimo Senor",b:"desierto",boss:true},
 32:{x:808,y:652,n:"Falla de los Antiguos",b:"desierto"},
 149:{x:820,y:700,n:"Oasis Tranquilo",b:"safe"},
 /* MAR */
 33:{x:28,y:510,n:"Embarcadero 1",b:"mar",acertijos:true},
 34:{x:80,y:510,n:"Abismo Coralino",b:"mar"},
 35:{x:132,y:510,n:"Trono del Oceano",b:"mar",boss:true},
 36:{x:184,y:510,n:"Cripta de las Algas",b:"mar"},
 37:{x:236,y:510,n:"Embarcadero 2",b:"mar",acertijos:true},
 38:{x:288,y:510,n:"Fosa de Sombras",b:"mar"},
 39:{x:340,y:510,n:"Arrecife Susurrante",b:"mar"},
 40:{x:392,y:510,n:"Caverna de la Bruma",b:"mar"},
 41:{x:444,y:510,n:"Templo de las Olas",b:"mar"},
 42:{x:496,y:510,n:"Laguna de Naufragos",b:"mar"},
 43:{x:548,y:510,n:"Pantano del Silencio",b:"mar"},
 44:{x:600,y:510,n:"Refugio de las Medusas",b:"mar"},
 45:{x:652,y:510,n:"Camara del Pulpo",b:"mar"},
 46:{x:704,y:510,n:"Bosque de Manglares",b:"mar"},
 47:{x:756,y:510,n:"Isla de la Lluvia",b:"mar"},
 48:{x:808,y:510,n:"Grieta Abisal",b:"mar"},
 49:{x:28,y:462,n:"Playa de los Ecos",b:"mar"},
 50:{x:80,y:462,n:"Torre del Vigia",b:"mar"},
 51:{x:132,y:462,n:"Gruta de las Mareas",b:"mar"},
 52:{x:184,y:462,n:"Pantano de las Raices",b:"mar"},
 53:{x:236,y:462,n:"Caverna del Coral",b:"mar"},
 54:{x:288,y:462,n:"Estuario del Viento",b:"mar"},
 55:{x:340,y:462,n:"Pozo de Agua",b:"mar"},
 56:{x:392,y:462,n:"Acantilado Lluvia",b:"mar"},
 57:{x:444,y:462,n:"Laguna de Sombras",b:"mar"},
 58:{x:496,y:462,n:"Bosque Inundado",b:"mar"},
 59:{x:548,y:462,n:"Camara de Corrientes",b:"mar"},
 60:{x:600,y:462,n:"Isla del Horizonte",b:"mar"},
 61:{x:652,y:462,n:"Fosa de la Marea",b:"mar"},
 62:{x:704,y:462,n:"Playa de Arena Humeda",b:"mar"},
 63:{x:756,y:462,n:"Gruta del Agua",b:"mar"},
 64:{x:808,y:462,n:"Delta de Canales",b:"mar"},
 65:{x:28,y:414,n:"Arrecife de Espinas",b:"mar"},
 66:{x:80,y:414,n:"Pantano de Lluvia",b:"mar"},
 67:{x:132,y:414,n:"Caverna del Vapor",b:"mar"},
 68:{x:184,y:414,n:"Laguna de Reflejos",b:"mar"},
 69:{x:236,y:414,n:"Sendero del Lodo",b:"mar"},
 70:{x:288,y:414,n:"Bahia de la Niebla",b:"mar"},
 71:{x:340,y:414,n:"Cumbre del Leviatan",b:"mar",boss:true},
 72:{x:392,y:414,n:"Cumbre del Kraken",b:"mar",boss:true},
 150:{x:820,y:510,n:"Puerto Abandonado",b:"safe"},
 /* NIEVE */
 73:{x:28,y:295,n:"Ventisca Eterna",b:"nieve"},
 74:{x:80,y:295,n:"Bosque de Hielo Negro",b:"nieve"},
 75:{x:132,y:295,n:"Grieta del Frio",b:"nieve"},
 76:{x:184,y:295,n:"Llanura del Silencio",b:"nieve"},
 77:{x:236,y:295,n:"Cementerio Congelado",b:"nieve"},
 78:{x:288,y:295,n:"Tormenta Errante",b:"nieve"},
 79:{x:340,y:295,n:"Picos del Desgarro",b:"nieve"},
 80:{x:392,y:295,n:"Hondonada del Eco",b:"nieve"},
 81:{x:444,y:295,n:"Rio de Hielo",b:"nieve"},
 82:{x:496,y:295,n:"Fauces de la Tormenta",b:"nieve"},
 83:{x:548,y:295,n:"Campo de Estatuas",b:"nieve"},
 84:{x:600,y:295,n:"Abismo Nevado",b:"nieve"},
 85:{x:652,y:295,n:"Cumbre del Viento",b:"nieve"},
 86:{x:704,y:295,n:"Valle de Sombras",b:"nieve"},
 87:{x:756,y:295,n:"Ruinas Congeladas",b:"nieve"},
 88:{x:808,y:295,n:"Paso del Susurro",b:"nieve"},
 89:{x:28,y:247,n:"Glaciar Viviente",b:"nieve"},
 90:{x:80,y:247,n:"Fosa del Olvido",b:"nieve"},
 91:{x:132,y:247,n:"Torres de Escarcha",b:"nieve"},
 92:{x:184,y:247,n:"Velo de Nieve",b:"nieve"},
 93:{x:236,y:247,n:"Lago de Cristal",b:"nieve"},
 94:{x:288,y:247,n:"Bosque de Agujas",b:"nieve"},
 95:{x:340,y:247,n:"Furia Blanca",b:"nieve"},
 96:{x:392,y:247,n:"Caverna de Escarcha",b:"nieve"},
 97:{x:444,y:247,n:"Paso del Ultimo Aliento",b:"nieve"},
 98:{x:496,y:247,n:"Colmillos del Invierno",b:"nieve"},
 99:{x:548,y:247,n:"Valle del Sueno",b:"nieve"},
 100:{x:600,y:247,n:"Niebla Blanca",b:"nieve"},
 101:{x:652,y:247,n:"Cumbre Quebrada",b:"nieve"},
 102:{x:704,y:247,n:"Territorio del Frio",b:"nieve"},
 103:{x:756,y:247,n:"Sendero del Hielo",b:"nieve"},
 104:{x:808,y:247,n:"Vigilantes de Escarcha",b:"nieve"},
 105:{x:28,y:199,n:"Desierto Blanco",b:"nieve"},
 106:{x:80,y:199,n:"Garganta del Viento",b:"nieve"},
 107:{x:132,y:199,n:"Ruinas del Invierno",b:"nieve"},
 108:{x:184,y:199,n:"Campo de Fragmentos",b:"nieve"},
 109:{x:236,y:199,n:"Pozo de Escarcha",b:"nieve"},
 110:{x:288,y:199,n:"Travesia del Frio",b:"nieve"},
 111:{x:340,y:199,n:"Tormenta Estatica",b:"nieve"},
 112:{x:392,y:199,n:"Cascada Congelada",b:"nieve"},
 113:{x:444,y:199,n:"Circulo de Hielo",b:"nieve"},
 114:{x:496,y:199,n:"Bosque de Sombras",b:"nieve"},
 115:{x:548,y:199,n:"Frontera del Frio",b:"nieve"},
 116:{x:600,y:199,n:"Vertice Nevado",b:"nieve"},
 117:{x:652,y:199,n:"Hogar de la Escarcha",b:"nieve"},
 118:{x:704,y:199,n:"Sendero de los Perdidos",b:"nieve"},
 119:{x:756,y:199,n:"Falla Glacial",b:"nieve"},
 120:{x:808,y:199,n:"Campo de Huesos",b:"nieve"},
 121:{x:28,y:151,n:"Tormenta Silenciosa",b:"nieve"},
 122:{x:80,y:151,n:"Nucleo de Hielo",b:"nieve"},
 123:{x:132,y:151,n:"Paso de los Colosos",b:"nieve"},
 124:{x:184,y:151,n:"Mar de Escarcha",b:"nieve"},
 125:{x:236,y:151,n:"Colina del Ultimo Suspiro",b:"nieve"},
 126:{x:288,y:151,n:"Catedral de Hielo",b:"nieve"},
 127:{x:340,y:151,n:"Velo del Olvido",b:"nieve"},
 128:{x:392,y:151,n:"Fauces Heladas",b:"nieve"},
 129:{x:444,y:151,n:"Bosque del Frio",b:"nieve"},
 130:{x:496,y:151,n:"Campo de Escarcha Oscura",b:"nieve"},
 131:{x:548,y:151,n:"Trampa de Nieve",b:"nieve"},
 132:{x:600,y:151,n:"Cumbre del Olvido",b:"nieve"},
 133:{x:652,y:151,n:"Rugido Blanco",b:"nieve"},
 134:{x:704,y:151,n:"Valle del Frio Eterno",b:"nieve"},
 135:{x:756,y:151,n:"Sombras Bajo el Hielo",b:"nieve"},
 136:{x:808,y:151,n:"Paso de la Escarcha",b:"nieve"},
 137:{x:28,y:103,n:"Caverna del Viento",b:"nieve"},
 138:{x:80,y:103,n:"Campos del Silencio",b:"nieve"},
 139:{x:132,y:103,n:"Colapso Glacial",b:"nieve"},
 140:{x:184,y:103,n:"Tormenta del Norte",b:"nieve"},
 141:{x:236,y:103,n:"Grieta del Ultimo Invierno",b:"nieve"},
 142:{x:288,y:103,n:"Altar de Hielo",b:"nieve"},
 143:{x:340,y:103,n:"Sendero del Frio Infinito",b:"nieve"},
 144:{x:392,y:103,n:"Cupula de Escarcha",b:"nieve"},
 145:{x:444,y:103,n:"Ruinas del Viento Blanco",b:"nieve"},
 146:{x:496,y:103,n:"Frontera del Vacio",b:"nieve"},
 147:{x:548,y:103,n:"Crater de Hielo",b:"nieve"},
 148:{x:600,y:103,n:"Trono del Invierno",b:"nieve",boss:true},
};

const CONNS=[
 /* Tutorial */
 ["0.1","0.2"],["0.2","0.3"],["0.3","0.4"],
 /* Desierto */
 [1,2],[1,6],[1,13],[2,3],[3,4],[3,16],[4,5],[5,6],[6,7],[7,8],[7,9],[8,9],[10,11],[10,6],
 [11,12],[11,17],[12,13],[12,18],[13,14],[13,19],[14,15],[15,16],[16,22],[17,18],[18,27],
 [19,20],[20,21],[20,25],[21,22],[22,23],[23,24],[24,30],[24,32],[25,26],[26,19],[27,28],
 [28,29],[29,30],[30,31],[31,32],[32,33],[6,37],
 /* Mar */
 [33,34],[33,38],[33,39],[34,35],[35,36],[36,37],[36,41],[37,38],[37,42],[38,39],[38,44],
 [39,40],[39,44],[40,41],[41,46],[42,43],[42,52],[43,44],[43,51],[44,45],[44,50],[46,47],
 [46,48],[47,48],[48,59],[49,50],[49,56],[50,51],[50,55],[51,52],[51,54],[52,53],[53,54],
 [54,55],[56,49],[57,58],[57,59],[58,60],[59,60],[59,62],[60,61],[61,62],[61,64],[62,63],
 [63,66],[64,65],[65,66],[66,68],[68,69],[69,70],[70,71],[71,72],[72,73],
 /* Nieve */
 [73,74],[74,75],[74,76],[75,76],[76,77],[77,78],[77,83],[78,79],[79,80],[79,98],[80,83],
 [81,82],[82,83],[83,84],[83,96],[84,85],[84,95],[85,86],[86,87],[86,89],[88,89],[90,91],
 [91,92],[92,93],[92,101],[93,102],[94,95],[94,103],[95,96],[95,104],[96,97],[96,105],
 [98,99],[98,107],[99,108],[100,109],[101,118],[102,117],[103,104],[104,105],[104,115],
 [105,106],[106,107],[107,112],[108,109],[108,111],[109,110],[110,111],[111,112],[112,125],
 [113,114],[113,124],[114,123],[115,116],[115,122],[116,121],[117,120],[118,119],[119,128],
 [120,121],[120,129],[121,122],[122,123],[122,132],[123,133],[124,125],[125,134],[126,127],
 [126,135],[127,136],[128,145],[129,144],[130,143],[131,142],[132,141],[133,140],[134,135],
 [134,139],[137,138],[138,139],[139,140],[140,141],[141,142],[141,146],[142,143],[144,145],
 [145,146],[146,147],[146,148],[147,148],
 /* Oasis y extras */
 [24,149],[32,149],[71,150]
];

const BC={desierto:"#8b6914",mar:"#1565c0",nieve:"#546e7a",safe:"#2e7d32",tutorial:"#555"};

const SNAMES={
 1:"North Mass",2:"Dunas del Norte",3:"Ruinas del Desierto",4:"Ciudad Abrasada",
 5:"Valle Muerto",6:"Oasis",7:"Sala del Viento",8:"Camara del Oasis",
 9:"Salon del Sol",10:"Cripta de las Dunas",11:"Caravana Fantasma",12:"Fosa de Titanes",
 13:"Altar del Soberano",14:"Extension de Azhar",15:"Mar de Dunas",16:"Vestigios Enterrados",
 17:"Santuario Carmesi",18:"Sepulcro de Colosos",19:"Trono del Abismo",
 20:"Llanura de Fuego",21:"Dunas del Murmullo",22:"Columnas del Olvido",
 23:"Templo de Sangre",24:"Abismo de los Caidos",25:"Trono del Devastador",
 26:"Horizonte Quebrado",27:"Dunas del Hambre",28:"Ruinas del Eco",
 29:"Santuario de la Marca",30:"Campos de Huesos",31:"Trono del Ultimo Senor",
 32:"Falla de los Antiguos",33:"Embarcadero 1",34:"Abismo Coralino",
 35:"Trono del Oceano",36:"Cripta de las Algas",37:"Embarcadero 2",
 38:"Fosa de Sombras",39:"Arrecife Susurrante",40:"Caverna de la Bruma",
 41:"Templo de las Olas",42:"Laguna de Naufragos",43:"Pantano del Silencio",
 44:"Refugio de las Medusas",45:"Camara del Pulpo",46:"Bosque de Manglares",
 47:"Isla de la Lluvia",48:"Grieta Abisal",49:"Playa de los Ecos",
 50:"Torre del Vigia",51:"Gruta de las Mareas",52:"Pantano de las Raices",
 53:"Caverna del Coral",54:"Estuario del Viento",55:"Pozo de Agua",
 56:"Acantilado de la Lluvia",57:"Laguna de Sombras",58:"Bosque Inundado",
 59:"Camara de Corrientes",60:"Isla del Horizonte",61:"Fosa de la Marea",
 62:"Playa de Arena Humeda",63:"Gruta del Agua",64:"Delta de Canales",
 65:"Arrecife de Espinas",66:"Pantano de Lluvia",67:"Caverna del Vapor",
 68:"Laguna de Reflejos",69:"Sendero del Lodo",70:"Bahia de la Niebla",
 71:"Cumbre del Leviatan",72:"Cumbre del Kraken",73:"Ventisca Eterna",
 74:"Bosque de Hielo Negro",75:"Grieta del Frio",76:"Llanura del Silencio",
 77:"Cementerio Congelado",78:"Tormenta Errante",79:"Picos del Desgarro",
 80:"Hondonada del Eco",81:"Rio de Hielo",82:"Fauces de la Tormenta",
 83:"Campo de Estatuas",84:"Abismo Nevado",85:"Cumbre del Viento",
 86:"Valle de Sombras",87:"Ruinas Congeladas",88:"Paso del Susurro",
 89:"Glaciar Viviente",90:"Fosa del Olvido",91:"Torres de Escarcha",
 92:"Velo de Nieve",93:"Lago de Cristal",94:"Bosque de Agujas",
 95:"Furia Blanca",96:"Caverna de Escarcha",97:"Paso del Ultimo Aliento",
 98:"Colmillos del Invierno",99:"Valle del Sueno",100:"Niebla Blanca",
 101:"Cumbre Quebrada",102:"Territorio del Frio",103:"Sendero del Hielo",
 104:"Vigilantes de Escarcha",105:"Desierto Blanco",106:"Garganta del Viento",
 107:"Ruinas del Invierno",108:"Campo de Fragmentos",109:"Pozo de Escarcha",
 110:"Travesia del Frio",111:"Tormenta Estatica",112:"Cascada Congelada",
 113:"Circulo de Hielo",114:"Bosque de Sombras",115:"Frontera del Frio",
 116:"Vertice Nevado",117:"Hogar de la Escarcha",118:"Sendero de los Perdidos",
 119:"Falla Glacial",120:"Campo de Huesos",121:"Tormenta Silenciosa",
 122:"Nucleo de Hielo",123:"Paso de los Colosos",124:"Mar de Escarcha",
 125:"Colina del Ultimo Suspiro",126:"Catedral de Hielo",127:"Velo del Olvido",
 128:"Fauces Heladas",129:"Bosque del Frio",130:"Campo de Escarcha",
 131:"Trampa de Nieve",132:"Cumbre del Olvido",133:"Rugido Blanco",
 134:"Valle del Frio Eterno",135:"Sombras Bajo el Hielo",136:"Paso de la Escarcha",
 137:"Caverna del Viento",138:"Campos del Silencio",139:"Colapso Glacial",
 140:"Tormenta del Norte",141:"Grieta del Ultimo Invierno",142:"Altar de Hielo",
 143:"Sendero del Frio Infinito",144:"Cupula de Escarcha",145:"Ruinas del Viento",
 146:"Frontera del Vacio",147:"Crater de Hielo",148:"Trono del Invierno",
 149:"Oasis Tranquilo",150:"Trono del Invierno 2"
};

function buildMap(connId,roomId){
  const ns="http://www.w3.org/2000/svg";
  const cg=document.getElementById(connId),rg=document.getElementById(roomId);
  if(!cg||!rg)return;
  while(cg.firstChild)cg.removeChild(cg.firstChild);
  while(rg.firstChild)rg.removeChild(rg.firstChild);
  CONNS.forEach(([a,b])=>{
    const pa=RPOS[a],pb=RPOS[b];if(!pa||!pb)return;
    const l=document.createElementNS(ns,"line");
    l.setAttribute("x1",pa.x);l.setAttribute("y1",pa.y);
    l.setAttribute("x2",pb.x);l.setAttribute("y2",pb.y);
    l.setAttribute("stroke","#252525");l.setAttribute("stroke-width","1");
    cg.appendChild(l);
  });
  Object.entries(RPOS).forEach(([id,r])=>{
    const safeId=String(id).replace(".","_");
    const g=document.createElementNS(ns,"g");
    g.setAttribute("id",roomId+"-r"+safeId);g.setAttribute("data-sid",id);
    const W=r.boss?40:r.acertijos?36:32,H=14;
    const rect=document.createElementNS(ns,"rect");
    rect.setAttribute("x",r.x-W/2);rect.setAttribute("y",r.y-H/2);
    rect.setAttribute("width",W);rect.setAttribute("height",H);rect.setAttribute("rx",2);
    let fillColor="#0d0d0d";
    let strokeColor=BC[r.b]||"#2a2a2a";
    if(r.boss){fillColor="#150000";strokeColor="#7a1a1a";}
    else if(r.acertijos){fillColor="#150015";strokeColor="#8e44ad";}
    rect.setAttribute("fill",fillColor);
    rect.setAttribute("stroke",strokeColor);
    rect.setAttribute("stroke-width","1");
    const txt=document.createElementNS(ns,"text");
    txt.setAttribute("x",r.x);txt.setAttribute("y",r.y+1);
    txt.setAttribute("text-anchor","middle");txt.setAttribute("dominant-baseline","middle");
    let textColor=r.boss?"#cc3333":r.acertijos?"#8e44ad":(BC[r.b]||"#555");
    txt.setAttribute("fill",textColor);
    txt.setAttribute("font-size","6");txt.setAttribute("font-family","monospace");
    txt.textContent=id;
    g.appendChild(rect);g.appendChild(txt);
    if(roomId==="map-rooms-full"){
      let tt=null;
      g.addEventListener("mouseenter",e=>{
        tt=document.createElement("div");
        tt.style.cssText="position:fixed;background:#1a1a1a;border:1px solid #444;padding:3px 7px;border-radius:3px;font-size:10px;color:#ccc;pointer-events:none;z-index:600;white-space:nowrap;font-family:monospace";
        let extra=r.boss?" [BOSS]":r.acertijos?" [🧩ACERTIJOS]":"";
        tt.textContent="["+id+"] "+(SNAMES[id]||r.n)+extra;document.body.appendChild(tt);
      });
      g.addEventListener("mousemove",e=>{if(tt){tt.style.left=(e.clientX+10)+"px";tt.style.top=(e.clientY-5)+"px";}});
      g.addEventListener("mouseleave",()=>{if(tt){tt.remove();tt=null;}});
    }
    rg.appendChild(g);
  });
}

function highlightRoom(id){
  const safeId=String(id).replace(".","_");
  ["mini","full"].forEach(suf=>{
    const pfx=suf==="mini"?"map-rooms-mini":"map-rooms-full";
    document.querySelectorAll("[id^='"+pfx+"-r']").forEach(g=>{
      const rid=g.getAttribute("data-sid");
      const r=RPOS[rid]||RPOS[String(rid)];if(!r)return;
      const rect=g.querySelector("rect");if(!rect)return;
      let fillColor="#0d0d0d";
      let strokeColor=BC[r.b]||"#2a2a2a";
      if(r.boss){fillColor="#150000";strokeColor="#7a1a1a";}
      else if(r.acertijos){fillColor="#150015";strokeColor="#8e44ad";}
      rect.setAttribute("fill",fillColor);
      rect.setAttribute("stroke",strokeColor);
      rect.setAttribute("stroke-width","1");rect.removeAttribute("filter");
    });
    const g=document.getElementById(pfx+"-r"+safeId);
    if(g){const rect=g.querySelector("rect");if(rect){
      rect.setAttribute("fill","#1f1200");rect.setAttribute("stroke","#c9a84c");
      rect.setAttribute("stroke-width","2");
      if(suf==="full")rect.setAttribute("filter","url(#glowf)");
    }}
  });
}

/* STATE */
let ws=null,hist=[],hidx=-1,chatTab="sala",myStats=null,acertijoActivo=false;

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
  } else if(m.type==="acertijo"){
    openAcertijoPopup(m.pregunta,m.opciones,m.indice,m.total);
  } else if(m.type==="acertijo_end"){
    closeAcertijoPopup(m.exito);
  }
}

function classify(t){
  if(!t)return "gg";
  const l=t.toLowerCase();
  if(l.includes("victoria")||l.includes("🏆"))return "gv";
  if(l.includes("caido")||l.includes("derrota")||l.includes("muerto")||l.includes("💀"))return "gd";
  if(l.includes("turno")||l.includes("combate")||l.includes("ataca")||l.includes("golpea")||l.includes("especial"))return "gc";
  if(l.includes("acertijo")||l.includes("🧩"))return "gp2";
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

/* STATS */
const CLASE_EMOJI={
  "guerrero":"🛡️","mago":"🔥","arquero":"🏹","curandero":"💚",
  "nigromante":"💀","hechicero":"👁️","caballero":"⚔️","cazador":"🎯",
  "asesino":"🗡️","bárbaro":"🪓","barbaro":"🪓"
};
function updateStats(s){
  myStats=s;
  set("s-nm",s.nombre||"—");
  set("s-cl",s.clase?(s.clase[0].toUpperCase()+s.clase.slice(1)):"—");
  const emojiEl=document.getElementById("s-emoji");
  if(emojiEl)emojiEl.textContent=CLASE_EMOJI[(s.clase||"").toLowerCase()]||"⚔️";
  set("s-nv","Nv."+s.nivel);
  document.getElementById("tb-player").innerHTML="<span>"+esc(s.nombre)+"</span> ["+esc(s.clase)+"] Nv."+s.nivel;

  const xpPct=s.xpMax>0?Math.min(100,s.xp/s.xpMax*100):0;
  document.getElementById("b-xp").style.width=xpPct+"%";
  set("s-xp",s.xp+"/"+s.xpMax);

  const hpPct=s.hpMax>0?Math.min(100,s.hp/s.hpMax*100):0;
  const bh=document.getElementById("b-hp");
  bh.style.width=hpPct+"%";
  bh.style.background=hpPct<25?"var(--red2)":hpPct<50?"#e67e22":"var(--red)";
  set("s-hp",s.hp+"/"+s.hpMax);

  const mpPct=s.manaMax>0?Math.min(100,s.mana/s.manaMax*100):0;
  document.getElementById("b-mp").style.width=mpPct+"%";
  set("s-mp",s.mana+"/"+s.manaMax);

  const atqs=s.ataquesTurno;
  set("s-dmg",s.danioBase||"—");
  set("s-atq",Array.isArray(atqs)?atqs[0]+"-"+atqs[1]:String(atqs||"—"));
  set("s-mc",(s.costoEspecial||0)+" mana");

  set("bag-coins",(s.monedas||0)+" 💰");
  if(s.inventario!==undefined)renderBag(s.inventario);
  if(s.sala_id!==undefined)updateServices(s.sala_id);
  if(s.sala_id)highlightRoom(s.sala_id);
}

function renderBag(inv){
  const N={"pocion_vida":"🧪 Poción Vida","pocion_danio":"⚗️ Poc. Daño","gema_teleporte":"💎 Gema Tele."};
  const div=document.getElementById("bag-items");
  const items=Object.entries(inv||{}).filter(([k,v])=>v>0);
  if(!items.length){div.innerHTML='<div class="bag-empty">Vacía</div>';return;}
  div.innerHTML=items.map(([k,v])=>`<div class="bag-item">${N[k]||k} x${v}</div>`).join("");
}

const SALAS_SVC={
 "0.3":{h:true,s:true},4:{h:true,s:false},5:{h:true,s:false},6:{h:true,s:true},
 8:{h:true,s:true},13:{h:false,s:true},17:{h:false,s:false},21:{h:true,s:true},
 25:{h:true,s:true},34:{h:true,s:false},38:{h:true,s:false},39:{h:false,s:true},
 44:{h:true,s:true},53:{h:true,s:false},58:{h:false,s:true},70:{h:true,s:false},
 87:{h:true,s:false},94:{h:true,s:false},105:{h:true,s:false},131:{h:true,s:false},
 142:{h:true,s:false},147:{h:true,s:true},149:{h:true,s:true}
};
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

/* ACERTIJO POPUP */
function openAcertijoPopup(pregunta,opciones,indice,total){
  acertijoActivo=true;
  const popup=document.getElementById("acertijo-popup");
  document.getElementById("acertijo-title").textContent="🧩 ACERTIJO "+(indice+1)+"/"+total;
  document.getElementById("acertijo-counter").textContent="Progreso: "+indice+"/"+total+" completados";
  document.getElementById("acertijo-pregunta").textContent=pregunta;
  document.getElementById("acertijo-msg").textContent="";
  const div=document.getElementById("acertijo-opciones");
  div.innerHTML="";
  opciones.forEach((opt,idx)=>{
    const btn=document.createElement("button");
    btn.className="acertijo-opt";
    btn.textContent=opt;
    btn.onclick=()=>responderAcertijo(String.fromCharCode(97+idx)); // a, b, c, d
    div.appendChild(btn);
  });
  popup.classList.add("open");
  disableUI();
}
function responderAcertijo(letra){
  if(!acertijoActivo)return;
  send(letra);
}
function closeAcertijoPopup(exito){
  acertijoActivo=false;
  document.getElementById("acertijo-popup").classList.remove("open");
  enableUI();
  if(exito){
    appendLog("  🎉 ¡Acertijos completados! Puedes continuar.","gv");
  }
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
  if(!acertijoActivo)closeCombatPopup();
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
    print(f"[SERVER] Salas con acertijos: 33, 37")
    print("[SERVER] Listo.\n")

    await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())

