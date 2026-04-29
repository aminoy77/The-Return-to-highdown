"""
THE RETURN TO HIGHDOWN - GAME SERVER
===============================
Servei de joc: lògica, stats, saves, leaderboard
Executa a: Render (512MB RAM, 0.1 CPU)

Per despertar: crida a /wake
Per jugar: WebSocket a /ws
"""

import asyncio
import hashlib
import json
import os
import random
from copy import deepcopy
from aiohttp import web
import aiohttp
import time

# ==================== CONFIG ====================
PORT = int(os.environ.get("PORT", 8080))
SAVES_DIR = "saves"
os.makedirs(SAVES_DIR, exist_ok=True)

# Supabase config
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
USAR_SUPABASE = bool(SUPABASE_URL and SUPABASE_KEY)

if USAR_SUPABASE:
    import aiohttp
    _sb_session = None
    def _get_sb_session():
        global _sb_session
        if _sb_session is None or _sb_session.closed:
            _sb_session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10))
        return _sb_session
    
    async def _sb_get(usuario):
        try:
            s = _get_sb_session()
            url = f"{SUPABASE_URL}/rest/v1/mud_saves?usuario=eq.{usuario}&select=*"
            headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
            async with s.get(url, headers=headers) as r:
                if r.status == 200:
                    rows = await r.json()
                    return rows[0] if rows else None
        except Exception as e:
            print(f"[SB] GET error: {e}")
        return None
    
    async def _sb_upsert(row):
        try:
            s = _get_sb_session()
            url = f"{SUPABASE_URL}/rest/v1/mud_saves"
            headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json", "Prefer": "resolution=merge-duplicates"}
            async with s.post(url, headers=headers, json=row) as r:
                status = r.status
                if status >= 400:
                    text = await r.text()
                    print(f"[SB] UPSERT error {status}: {text[:100]}")
                else:
                    print(f"[SB] UPSERT OK: {row.get('usuario')}")
        except Exception as e:
            print(f"[SB] UPSERT error: {e}")

# ==================== CONSTANTS ====================
XP_POR_NIVEL = 150
MONEDAS_SUBIDA = 20
SALA_RESPAWN = 6
TIEMPO_RESPAWN = 5
COMBAT_TURN_TIME = 1

# ==================== CLASES ====================
CLASES = {
    "guerrero": {"vidaMax": 90, "danioBase": 40, "manaMax": 30, "manaTurno": 10, "danioEspecial": 70, "ataquesTurno": 1, "costoEspecial": 30},
    "mago": {"vidaMax": 50, "danioBase": 30, "manaMax": 70, "manaTurno": 20, "danioEspecial": 60, "ataquesTurno": 1, "costoEspecial": 60},
    "arquero": {"vidaMax": 40, "danioBase": 10, "manaMax": 40, "manaTurno": 15, "danioEspecial": 10, "ataquesTurno": [1, 4], "costoEspecial": 40},
    "curandero": {"vidaMax": 50, "danioBase": 20, "manaMax": 50, "manaTurno": 20, "danioEspecial": 20, "ataquesTurno": 1, "costoEspecial": 30, "curacionEspecial": 20},
    "nigromante": {"vidaMax": 50, "danioBase": 10, "manaMax": 80, "manaTurno": 20, "danioEspecial": 60, "ataquesTurno": [1, 5], "costoEspecial": 60},
    "hechicero": {"vidaMax": 50, "danioBase": 30, "manaMax": 70, "manaTurno": 30, "danioEspecial": 70, "ataquesTurno": 1, "costoEspecial": 70},
    "caballero": {"vidaMax": 70, "danioBase": 50, "manaMax": 40, "manaTurno": 10, "danioEspecial": 60, "ataquesTurno": 1, "costoEspecial": 40},
    "cazador": {"vidaMax": 60, "danioBase": 50, "manaMax": 30, "manaTurno": 10, "danioEspecial": 30, "ataquesTurno": 1, "costoEspecial": 30},
    "asesino": {"vidaMax": 50, "danioBase": 20, "manaMax": 20, "manaTurno": 10, "danioEspecial": 60, "ataquesTurno": [1, 3], "costoEspecial": 20},
    "barbaro": {"vidaMax": 60, "danioBase": 50, "manaMax": 30, "manaTurno": 5, "danioEspecial": 70, "ataquesTurno": 1, "costoEspecial": 30},
}

ENEMIGOS = {
    "bandido": {"vidaMax": 60, "danioBase": 20, "ataquesTurno": 1, "tier": "Base"},
    "slime": {"vidaMax": 90, "danioBase": 5, "ataquesTurno": 2, "tier": "Base"},
    "duende": {"vidaMax": 50, "danioBase": 15, "ataquesTurno": 2, "tier": "Base"},
    "esqueleto": {"vidaMax": 70, "danioBase": 25, "ataquesTurno": 1, "tier": "Base"},
    "zombie": {"vidaMax": 80, "danioBase": 10, "ataquesTurno": 1, "tier": "Base"},
    "lobo": {"vidaMax": 60, "danioBase": 15, "ataquesTurno": [1, 2], "tier": "Base"},
    "oso": {"vidaMax": 75, "danioBase": 35, "ataquesTurno": 1, "tier": "Base"},
    "orco": {"vidaMax": 70, "danioBase": 30, "ataquesTurno": 1, "tier": "Especial"},
    "ogro": {"vidaMax": 90, "danioBase": 30, "ataquesTurno": 1, "tier": "Especial"},
    "troll": {"vidaMax": 100, "danioBase": 35, "ataquesTurno": 1, "tier": "Especial"},
    "gigante": {"vidaMax": 110, "danioBase": 45, "ataquesTurno": 1, "tier": "Especial"},
    "vampiro": {"vidaMax": 125, "danioBase": 20, "ataquesTurno": [1, 2], "tier": "Superior"},
    "elfoOscuro": {"vidaMax": 150, "danioBase": 60, "ataquesTurno": 1, "tier": "Superior"},
    "demonedasnioSuperior": {"vidaMax": 150, "danioBase": 60, "ataquesTurno": 1, "tier": "Superior"},
    "leviatan": {"vidaMax": 250, "danioBase": 80, "ataquesTurno": 1, "tier": "Elite"},
    "reyEsqueleto": {"vidaMax": 230, "danioBase": 80, "ataquesTurno": 1, "tier": "Elite"},
    "reyDemonedasnio": {"vidaMax": 250, "danioBase": 70, "ataquesTurno": 1, "tier": "Boss"},
    "kraken": {"vidaMax": 400, "danioBase": 70, "ataquesTurno": 1, "tier": "Boss"},
    "alpha": {"vidaMax": 500, "danioBase": 90, "ataquesTurno": 1, "tier": "Boss"},
}

XP_POR_TIER = {"Base": 10, "Especial": 30, "Superior": 50, "Elite": 100, "Boss": 250}

CATALOGO = {
    "pocion_vida": {"nombre": "Pocion de Vida", "emonedasji": "🧪", "precio": 30},
    "pocion_danio": {"nombre": "Pocion de Danio", "emonedasji": "⚗️", "precio": 40},
    "gema_teleporte": {"nombre": "Gema de Teletransporte", "emonedasji": "💎", "precio": 50},
}

BIOMAS = {
    "desierto": {"emonedasji": "🏜", "enemigos": ["bandido", "duende", "esqueleto", "zombie", "lobo"]},
    "mar": {"emonedasji": "🌊", "enemigos": ["slime", "troll", "vampiro"]},
    "nieve": {"emonedasji": "❄️", "enemigos": ["gigante", "elfoOscuro", "demonedasnioSuperior"]},
}

# ==================== SALAS ====================
SALAS = {
    # ── TUTORIAL (salas 010-050) ──────────────────────────────────
    0.1: {"nombre": "Como combatir",
          "descripcion": "Usa los comandos que aparecen para atacar",
          "conexiones": {"norte": 0.2},
          "encuentros": [("bandido", 1)] },
 
    0.2: {"nombre": "Objetos",
          "descripcion": "Como usar objetos",
          "conexiones": {"sur": 0.1, "norte": 0.3},
          "encuentros": [("duende", 1)] },
 
    0.3: {"nombre": "estructuras basicas",
          "descripcion": "hospital y tienda",
          "conexiones": {"sur": 0.2, "norte": 0.40},
         "hospital": True, "tienda": True},
 
    0.4: {"nombre": "Como funciona UI",
          "descripcion": "UI",
          "conexiones": {"sur": 0.3, "norte": 1}},

    # ── DESIERTO (salas 1-32) ──────────────────────────────────
    1:  {"nombre": "North Mass",
         "descripcion": "Arena caliente bajo tus pies. El sol abrasa sin piedad.",
         "conexiones": {"norte": 2, "este": 13, "sur": 6},
         "bioma": "desierto", "cantidad": 1},

    2:  {"nombre": "Dunas del Norte",
         "descripcion": "Dunas interminables. Algo se mueve entre la arena.",
         "conexiones": {"sur": 1, "norte": 3},
         "bioma": "desierto", "cantidad": 2},

    3:  {"nombre": "Ruinas del Desierto",
         "descripcion": "Columnas rotas a medias enterradas. Silencio inquietante.",
         "conexiones": {"oeste": 4, "norte": 5, "este": 16},
         "bioma": "desierto", "cantidad": 2},

    4:  {"nombre": "Ciudad abrasada",
         "descripcion": "Una ciudad abrasada se alza entre cenizas eternas, donde las calles aún respiran calor y las sombras tiemblan como brasas vivas.",
         "descripcion": "Sus torres, negras y agrietadas, susurran historias de un fuego que nunca se apaga,",
         "descripcion": "mientras un cielo rojizo arde sin descanso sobre los últimos vestigios de vida.",
         "descripcion": "Un demonio superior aguarda, tenéis que derrotarlo!",
         "conexiones": {"este": 3},
         "encuentros": [("demonioSuperior", 1)],
         "hospital": True},

    5:  {"nombre": "Valle muerto",
         "descripcion": "Centenares de cuerpos muertos, esqueletos más grandes que buques navales.",
         "conexiones": {"sur": 3},
         "bioma": "desierto", "cantidad": 2},

    6:  {"nombre": "Sala del Viento Susurrante",
         "descripcion": "Columnas de arena giran lentamente y traen voces del pasado.",
         "conexiones": {"sur": 10, "oeste": 7, "norte": 1},
         "encuentros": [("elfoOscuro", 1)]},

    7:  {"nombre": "Cámara del Oasis Oculto",
         "descripcion": "Un pequeño lago mágico que concede visiones o recuerdos.",
         "conexiones": {"oeste": 8, "este": 6, "sur": 9},
         "bioma": "desierto", "cantidad": 1},

    8:  {"nombre": "Salón del Sol Eterno",
         "descripcion": "Un techo abierto donde un sol artificial quema sin piedad.",
         "conexiones": {"sur": 9, "este": 7},
         "bioma": "desierto", "cantidad": 2,
         "hospital": True, "tienda": True},

    9:  {"nombre": "Cripta de las Dunas Vivas",
         "descripcion": "Personas enterradas que se mueven bajo la arena.",
         "conexiones": {"norte": 7},
         "bioma": "desierto", "cantidad": 2},

    10: {"nombre": "Caravana fantasma",
         "descripcion": "Viajeros espectrales repiten eternamente su última travesía.",
         "conexiones": {"este": 11, "norte": 6},
         "encuentros": [("demonioInferior", 2)]},

    11: {"nombre": "Fosa de Titanes",
         "descripcion": "Restos colosales emergen de la arena, como si antiguos gigantes hubieran caído aquí.",
         "conexiones": {"norte": 12, "oeste": 10, "este": 17},
         "bioma": "desierto", "cantidad": 2},

    12: {"nombre": "Altar del Soberano Abisal",
         "descripcion": "Un trono oscuro tallado en huesos ennegrecidos irradia una presencia opresiva.",
         "conexiones": {"sur": 11, "este": 18, "norte": 13},
         "encuentros": [("reyEsqueleto", 1)]},

    13: {"nombre": "Extensión de Azhar",
         "descripcion": "El suelo arde bajo tus pies mientras el horizonte tiembla por el calor.",
         "conexiones": {"norte": 14, "este": 19, "oeste": 1},
         "bioma": "desierto", "cantidad": 1},

    14: {"nombre": "Mar de Dunas Susurrantes",
         "descripcion": "Las dunas se extienden sin fin, emitiendo murmullos cuando el viento las roza.",
         "conexiones": {"norte": 15, "sur": 13},
         "bioma": "desierto", "cantidad": 2},

    15: {"nombre": "Vestigios Enterrados",
         "descripcion": "Ruinas antiguas asoman entre la arena, como recuerdos que se niegan a desaparecer.",
         "conexiones": {"norte": 16, "sur": 14},
         "bioma": "desierto", "cantidad": 1},

    16: {"nombre": "Santuario Carmesí",
         "descripcion": "Muros cubiertos de símbolos sangrientos laten con una energía inquietante.",
         "conexiones": {"sur": 15, "este": 22, "oeste": 3},
         "encuentros": [("demonioInferior", 2)]},

    17: {"nombre": "Sepulcro de Colosos",
         "descripcion": "Huesos gigantescos yacen dispersos, devorados lentamente por el desierto.",
         "conexiones": {"oeste": 11},
         "bioma": "desierto", "cantidad": 2,
         "tienda": True},

    18: {"nombre": "Trono del Abismo",
         "descripcion": "Una estructura de hueso y sombra domina el lugar, como si aún esperara a su dueño.",
         "conexiones": {"oeste": 12, "este": 27},
         "bioma": "desierto", "cantidad": 1},

    19: {"nombre": "Llanura de Fuego Blanco",
         "descripcion": "La luz del sol es tan intensa que todo parece arder en un resplandor pálido.",
         "conexiones": {"norte": 20, "este": 26, "oeste": 13},
         "bioma": "desierto", "cantidad": 1},

    20: {"nombre": "Dunas del Murmullo Eterno",
         "descripcion": "Algo invisible se desliza bajo la arena, siguiendo cada paso que das.",
         "conexiones": {"sur": 19, "este": 25},
         "bioma": "desierto", "cantidad": 2},

    21: {"nombre": "Columnas del Olvido",
         "descripcion": "Pilares erosionados se alzan torcidos, marcando un lugar que el tiempo quiso borrar.",
         "conexiones": {"este": 15},
         "bioma": "desierto", "cantidad": 2,
         "hospital": True, "tienda": True},

    22: {"nombre": "Templo de la Sangre Antigua",
         "descripcion": "Inscripciones vivas recorren las paredes, como si observaran a los intrusos.",
         "conexiones": {"este": 23, "oeste": 16},
         "encuentros": [("demonioInferior", 2)]},

    23: {"nombre": "Abismo de los Caídos",
         "descripcion": "Un campo de restos antiguos donde incluso el viento parece evitar pasar.",
         "conexiones": {"sur": 24, "oeste": 22},
         "bioma": "desierto", "cantidad": 2},

    24: {"nombre": "Trono del Devastador",
         "descripcion": "Un asiento de poder olvidado, rodeado de una oscuridad que respira.",
         "conexiones": {"sur": 30, "norte": 23, "este": 32},
         "bioma": "desierto", "cantidad": 4,
         "tesoro": True},

    25: {"nombre": "Horizonte Quebrado",
         "descripcion": "El aire distorsiona la vista, haciendo que la distancia pierda todo sentido.",
         "conexiones": {"oeste": 20, "sur": 26},
         "bioma": "desierto", "cantidad": 1},

    26: {"nombre": "Dunas del Hambre",
         "descripcion": "La arena se mueve de forma antinatural, como si buscara devorar a los vivos.",
         "conexiones": {"oeste": 19, "norte": 25},
         "bioma": "desierto", "cantidad": 2},

    27: {"nombre": "Ruinas del Eco Silente",
         "descripcion": "Cada paso resuena demasiado fuerte, como si algo escuchara desde abajo.",
         "conexiones": {"oeste": 18, "este": 28},
         "bioma": "desierto", "cantidad": 2},

    28: {"nombre": "Santuario de la Marca Roja",
         "descripcion": "Antiguos rituales dejaron su huella, aún palpable en el aire seco.",
         "conexiones": {"oeste": 27, "norte": 29},
         "encuentros": [("demonioInferior", 2)]},

    29: {"nombre": "Campos de Huesos Errantes",
         "descripcion": "Restos que cambian de lugar con el tiempo, formando patrones desconocidos.",
         "conexiones": {"sur": 28, "norte": 30},
         "bioma": "desierto", "cantidad": 2},

    30: {"nombre": "Trono del Último Señor",
         "descripcion": "Un lugar de dominio absoluto, ahora envuelto en un silencio antinatural.",
         "conexiones": {"oeste": 24, "norte": 31},
         "encuentros": [("reyEsqueleto", 1)]},

    31: {"nombre": "Falla de los Antiguos",
         "descripcion": "Una grieta llena de restos y reliquias de una civilización olvidada.",
         "conexiones": {"sur": 30},
         "bioma": "desierto", "cantidad": 2},

    32: {"nombre": "Trono de Ceniza Viva",
         "descripcion": "El asiento aún desprende calor, como si su antiguo rey no se hubiera ido del todo.",
         "conexiones": {"oeste": 24, "este": 33, "norte": 37},
         "encuentros": [("reyDemonio", 1)]},

    # ── Mar (salas 33-72) ──────────────────────────────────
    33: {"nombre": "Embarcadero 1",
         "descripcion": "La marea está calmada y la gente emocionada.",
         "conexiones": {"oeste": 32, "norte": 38, "este": 39, "sur": 34},
         "bioma": "mar"},

    34: {"nombre": "Abismo Coralino",
         "descripcion": "Corales brillantes cubren una grieta que parece no tener fin.",
         "conexiones": {"oeste": 33, "este": 35},
         "bioma": "mar", "cantidad": 1,
         "hospital": True},

    35: {"nombre": "Trono del Oceano",
         "descripcion": "Un trono erosionado por el tiempo, rodeado de corrientes poderosas.",
         "conexiones": {"oeste": 34, "este": 36},
         "bioma": "mar", "cantidad": 2,
         "tesoro": True},

    36: {"nombre": "Cripta de las Algas",
         "descripcion": "Columnas cubiertas de algas esconden secretos olvidados.",
         "conexiones": {"sur": 35, "norte": 41, "oeste": 40},
         "bioma": "mar", "cantidad": 1},

    37: {"nombre": "Embarcadero 2",
         "descripcion": "El puerto de embarcación esta rebosante de gente.",
         "conexiones": {"sur": 32, "este": 38, "norte": 42},
         "bioma": "mar"},

    38: {"nombre": "Fosa de las Sombras Marinas",
         "descripcion": "Una profundidad oscura donde nada debería sobrevivir.",
         "conexiones": {"oeste": 37, "norte": 44, "este": 39, "sur": 33},
         "bioma": "mar", "cantidad": 2,
         "hospital": True},

    39: {"nombre": "Arrecife Susurrante",
         "descripcion": "El coral emite sonidos extraños al moverse con la corriente.",
         "conexiones": {"norte": 44, "sur": 33, "oeste": 38, "este": 40},
         "bioma": "mar", "cantidad": 1,
         "tesoro": True},

    40: {"nombre": "Caverna de la Bruma Salina",
         "descripcion": "Una cueva húmeda llena de niebla con olor a sal.",
         "conexiones": {},
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
         "conexiones": {"oeste": 70, "este": 72},
         "bioma": "mar", "cantidad": 1},

    72: {"nombre": "Cumbre del Kraken",
         "descripcion": "Un pico rocoso azotado por tormentas donde una sombra colosal se agita bajo las olas.",
         "conexiones": {"oeste": 71, "este": 73},
         "bioma": "mar", "cantidad": 1,
         "encuentros": [("kraken", 1)]},

    # ── Nieve (salas 73-149) ──────────────────────────────────
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
          "bioma": "nieve", "cantidad": 2},

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
          "bioma": "nieve", "cantidad": 2},

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
          "bioma": "nieve", "cantidad": 1},

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
          "bioma": "nieve", "cantidad": 2},

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
          "bioma": "nieve", "cantidad": 1},

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
          "bioma": "nieve", "cantidad": 2},

    143: {"nombre": "Sendero del Frío Infinito",
          "descripcion": "Un camino que parece no tener final.",
          "conexiones": {"sur": 130, "oeste": 142},
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
          "bioma": "nieve", "cantidad": 2},

    148: {"nombre": "Trono del Invierno",
          "descripcion": "Un asiento de poder donde el frío gobierna todo.",
          "conexiones": {"sur": 146, "oeste": 147},
          "encuentros": [("alpha", 1)]}, 
}           
# ==================== GLOBALS ====================
jugadores_conectados = []
combates_activos = {}
_lb_cache = []
_lb_cache_time = 0

# ==================== HELPERS ====================
def xp_para_subir(n):
    return XP_POR_NIVEL * n

def ataques_por_turno(val):
    return random.randint(val[0], val[1]) if isinstance(val, list) else val

def calcular_danio(base):
    return max(1, base + random.randint(-3, 3))

def _hash_password(password, salt):
    return hashlib.sha256((password + salt).encode()).hexdigest()

# ==================== ACCOUNT SYSTEM (local files) ====================
USUARIOS = {}

def load_usuarios():
    global USUARIOS
    USUARIOS = {}
    if not os.path.exists(SAVES_DIR):
        os.makedirs(SAVES_DIR, exist_ok=True)
    for f in os.listdir(SAVES_DIR):
        if f.endswith('.json'):
            usuario = f[:-5]
            try:
                with open(os.path.join(SAVES_DIR, f)) as fp:
                    USUARIOS[usuario] = json.load(fp)
            except:
                pass
    print(f"[USERS] Cargados {len(USUARIOS)} usuarios")

load_usuarios()

async def crear_cuenta(usuario, password, nombre, clase):
    print(f"[CREAR] Creando cuenta: {usuario}")
    
    if usuario in USUARIOS:
        print(f"[CREAR] Usuario ya existe: {usuario}")
        return None
    
    salt = hashlib.sha256(os.urandom(16)).hexdigest()[:16]
    hashed = _hash_password(password, salt)
    
    data = {
        "usuario": usuario,
        "password_hash": hashed,
        "salt": salt,
        "nombre": nombre,
        "clase": clase,
        "nivel": 1,
        "xp": 0,
        "monedas": 50,
        "sala_id": 1,
        "salas_limpias": [],
        "inventario": {},
        "misiones": {}
    }
    
    # Save locally first
    USUARIOS[usuario] = data
    ruta = os.path.join(SAVES_DIR, f"{usuario}.json")
    with open(ruta, "w") as f:
        json.dump(data, f)
    
    print(f"[CREAR] Cuenta creada local: {usuario}")
    
    # Also save to Supabase
    if USAR_SUPABASE:
        print(f"[CREAR] Guardando a Supabase: {usuario}")
        await _sb_upsert(data)
    
    return data

async def verificar_login(usuario, password):
    if usuario not in USUARIOS:
        return None
    
    u = USUARIOS[usuario]
    hashed = u.get("password_hash", "")
    salt = u.get("salt", "")
    
    if _hash_password(password, salt) == hashed:
        return u
    return None

async def cargar_cuenta(usuario):
    if usuario in USUARIOS:
        return USUARIOS[usuario]
    return None

async def guardar_cuenta(usuario, data):
    if usuario not in USUARIOS:
        return
    
    USUARIOS[usuario].update(data)
    ruta = os.path.join(SAVES_DIR, f"{usuario}.json")
    with open(ruta, "w") as f:
        json.dump(USUARIOS[usuario], f)
    
    if USAR_SUPABASE:
        await _sb_upsert(USUARIOS[usuario])

# ==================== PLAYER CLASS =================###
class Player:
    _id_counter = 0
    
    def __init__(self, ws, client_id):
        Player._id_counter += 1
        self.id = self._id_counter
        self.ws = ws
        self.client_id = client_id
        self.nombre = None
        self.usuario = None
        self.personaje = None
        self.sala_id = 1
        self.combate = None
        self.nivel = 1
        self.xp = 0
        self.monedas = 0
        self.muerto = False
        self.buff_danio = False
        self.inventario = {}
        self.grupo = None
        self.salas_limpias = set()
        self.lore_monedasstrado = False
        self.kills = 0
    
    async def send(self, data):
        try:
            await self.ws.send_json(data)
        except:
            pass

# ==================== BROADCAST ====================
async def broadcast_sala(sala_id, msg, exclude=None):
    for p in jugadores_conectados:
        if p.sala_id == sala_id and p != exclude:
            await p.send({"type": "chat", "scope": "sala", "text": msg})

async def broadcast_global(msg, exclude=None):
    for p in jugadores_conectados:
        if p != exclude:
            await p.send({"type": "chat", "scope": "global", "text": msg})

async def broadcast_ranking():
    ranking = []
    seen = set()
    for p in jugadores_conectados:
        if p.nombre and p.nombre not in seen:
            seen.add(p.nombre)
            clase = p.personaje.get("nombreClase", "?") if p.personaje else "?"
            ranking.append([p.nombre, p.nivel, clase])
    ranking.sort(key=lambda x: x[1], reverse=True)
    for p in jugadores_conectados:
        await p.send({"type": "ranking", "ranking": ranking})

async def broadcast_stats(player):
    if player.personaje:
        await player.send({
            "type": "status",
            "nombre": player.nombre,
            "clase": player.personaje.get("nombreClase", "?"),
            "nivel": player.nivel,
            "xp": player.xp,
            "xpMax": xp_para_subir(player.nivel),
            "hp": player.personaje.get("vidaActual", 0),
            "hpMax": player.personaje.get("vidaMax", 1),
            "mana": player.personaje.get("manaActual", 0),
            "manaMax": player.personaje.get("manaMax", 1),
            "monedas": player.monedas,
            "danio": player.personaje.get("danioBase", 0),
            "sala_id": player.sala_id,
        })

# ==================== COMBAT ====================
class Combate:
    def __init__(self, sala_id, jugadores):
        self.sala_id = sala_id
        self.jugadores = list(jugadores)
        self.enemigos = []
        self.acciones = {}
        self.turno = 0
    
    def cargar_enemigos(self):
        sala = SALAS.get(self.sala_id, {})
        self.enemigos = []
        if "bioma" in sala:
            pool = BIOMAS.get(sala["bioma"], {}).get("enemigos", [])
            cantidad = sala.get("cantidad", 1)
            for i, tipo in enumerate(random.choices(pool, k=cantidad)):
                base = deepcopy(ENEMIGOS[tipo])
                self.enemigos.append({"nombre": f"{tipo.capitalize()}", "tipo": tipo, "hp": base["vidaMax"], "vidaMax": base["vidaMax"], **base})
        for tipo, cantidad in sala.get("encuentros", []):
            for i in range(cantidad):
                base = deepcopy(ENEMIGOS[tipo])
                self.enemigos.append({"nombre": f"{tipo.capitalize()}", "tipo": tipo, "hp": base["vidaMax"], "vidaMax": base["vidaMax"], **base})
    
    def enemigos_vivos(self):
        return [e for e in self.enemigos if e["hp"] > 0]
    
    def jugadores_vivos(self):
        return [p for p in self.jugadores if p.personaje and p.personaje.get("vidaActual", 0) > 0]

async def loop_combate(combate):
    sala_id = combate.sala_id
    
    while combate.enemigos_vivos() and combate.jugadores_vivos():
        combate.turno += 1
        await broadcast_sala(sala_id, f"\n=== TURNO {combate.turno} ===")
        
        for p in combate.jugadores_vivos():
            if p.personaje:
                p.personaje["manaActual"] = min(p.personaje["manaActual"] + p.personaje.get("manaTurno", 0), p.personaje["manaMax"])
        
        for p in combate.jugadores_vivos():
            if not p.personaje or p.personaje["vidaActual"] <= 0:
                continue
            accion = combate.acciones.get(p.id, "1")
            await resolver_accion(p, accion, combate)
            if not combate.enemigos_vivos():
                break
        
        if not combate.enemigos_vivos():
            break
        
        for e in combate.enemigos_vivos():
            objetivos = combate.jugadores_vivos()
            if not objetivos:
                break
            obj = random.choice(objetivos)
            if obj.personaje:
                dmg = calcular_danio(e["danioBase"])
                obj.personaje["vidaActual"] = max(0, obj.personaje["vidaActual"] - dmg)
                await broadcast_sala(sala_id, f"  {e['nombre']} ataca a {obj.nombre} por {dmg}")
        
        for p in combate.jugadores:
            await broadcast_stats(p)
            pdata = {}
            if p.personaje:
                pdata = {"hp": p.personaje["vidaActual"], "hpMax": p.personaje["vidaMax"], "mana": p.personaje["manaActual"], "manaMax": p.personaje["manaMax"]}
            otros = []
            for o in combate.jugadores:
                if o != p and o.personaje:
                    otros.append({"nombre": o.nombre, "hp": o.personaje["vidaActual"], "hpMax": o.personaje["vidaMax"]})
            await p.send({"type": "combat_update", "enemigos": [{"nombre": e["nombre"], "hp": e["hp"], "hpMax": e["vidaMax"]} for e in combate.enemigos_vivos()], "turno": combate.turno, "player": pdata, "otros": otros})
        
        for p in combate.jugadores:
            if p.personaje and p.personaje["vidaActual"] <= 0 and not p.muerto:
                p.muerto = True
                await broadcast_sala(sala_id, f"💀 {p.nombre} ha caido!")
                await p.send({"type": "combat_end", "victory": False})
                asyncio.create_task(respawn(p))
        
        await asyncio.sleep(COMBAT_TURN_TIME)
        combate.acciones = {}
    
    if not combate.enemigos_vivos():
        xp = sum(XP_POR_TIER.get(e.get("tier", "Base"), 10) for e in combate.enemigos)
        oro = xp // 2
        await broadcast_sala(sala_id, f"\n🎉 VICTORIA! +{xp} XP, +{oro} monedas")
        for p in combate.jugadores_vivos():
            if p.personaje and p.personaje["vidaActual"] > 0:
                p.xp += xp
                p.misiones = getattr(p, 'misiones', {})
                for e in combate.enemigos:
                    tipo = e.get("tipo", "")
                    if tipo:
                        p.misiones[tipo] = p.misiones.get(tipo, 0) + 1
                p.personaje["vidaActual"] = min(p.personaje["vidaActual"] + 20, p.personaje["vidaMax"])
                p.salas_limpias.add(sala_id)
                p.kills += len(combate.enemigos)
                while p.xp >= xp_para_subir(p.nivel):
                    p.xp -= xp_para_subir(p.nivel)
                    p.nivel += 1
                    await p.send({"type": "level_up", "nivel": p.nivel})
                await p.send({"type": "combat_end", "victory": True, "xp": xp, "oro": oro})
                await broadcast_stats(p)
                await guardar_cuenta(p.usuario, {
                    "nombre": p.nombre,
                    "clase": p.personaje.get("nombreClase", "guerrero"),
                    "nivel": p.nivel,
                    "xp": p.xp,
                    "monedas": p.monedas
                })
        await broadcast_ranking()
    else:
        await broadcast_sala(sala_id, "\n💀 DERROTA. Intentalo de nuevo.")
        for p in combate.jugadores:
            await p.send({"type": "combat_end", "victory": False})
    
    for p in combate.jugadores:
        p.combate = None
    combates_activos.pop(sala_id, None)

async def resolver_accion(player, accion, combate):
    sala_id = combate.sala_id
    enemigos = combate.enemigos_vivos()
    if not enemigos:
        return
    obj = enemigos[0]
    p = player.personaje
    if not p:
        return
    
    if accion == "1":
        num = ataques_por_turno(p.get("ataquesTurno", 1))
        for _ in range(num):
            if obj["hp"] <= 0:
                break
            dmg = calcular_danio(p["danioBase"])
            if player.buff_danio:
                dmg = int(dmg * 1.3)
                player.buff_danio = False
            obj["hp"] = max(0, obj["hp"] - dmg)
            await broadcast_sala(sala_id, f"⚔️ {player.nombre} ataca a {obj['nombre']} por {dmg}")
    
    elif accion == "2":
        costo = p.get("costoEspecial", 0)
        if p["manaActual"] < costo:
            await player.send({"type": "message", "text": f"No tienes mana (necesitas {costo})"})
            return
        p["manaActual"] -= costo
        if p.get("nombreClase") == "curandero":
            cur = p.get("curacionEspecial", 20)
            p["vidaActual"] = min(p["vidaActual"] + cur, p["vidaMax"])
            await broadcast_sala(sala_id, f"💚 {player.nombre} se cura {cur} HP")
        else:
            dmg = calcular_danio(p.get("danioEspecial", p["danioBase"]))
            if player.buff_danio:
                dmg = int(dmg * 1.3)
                player.buff_danio = False
            obj["hp"] = max(0, obj["hp"] - dmg)
            await broadcast_sala(sala_id, f"✨ {player.nombre} usa habilidad especial en {obj['nombre']} por {dmg}")
    
    elif accion == "3":
        await broadcast_sala(sala_id, f"💤 {player.nombre} pasa el turno")

async def respawn(player):
    player.muerto = True
    await player.send({"type": "message", "text": f"Has muerto. Reapareces en {TIEMPO_RESPAWN}s..."})
    await asyncio.sleep(TIEMPO_RESPAWN)
    if player.personaje:
        player.personaje["vidaActual"] = max(1, player.personaje["vidaMax"] // 2)
        player.personaje["manaActual"] = player.personaje["manaMax"]
    player.sala_id = SALA_RESPAWN
    player.muerto = False
    await player.send({"type": "respawn", "sala_id": SALA_RESPAWN})
    await broadcast_stats(player)

# ==================== WEB HANDLER ====================
async def websocket_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    
    player = Player(ws, request.remote)
    jugadores_conectados.append(player)
    
    try:
        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                    
                    if data.get("type") == "login":
                        usuario = data.get("usuario", "")
                        password = data.get("password", "")
                        
                        result = await verificar_login(usuario, password)
                        if result:
                            player.usuario = usuario
                            player.nombre = result.get("nombre", usuario)
                            clase = result.get("clase", "guerrero")
                            player.nivel = result.get("nivel", 1)
                            player.xp = result.get("xp", 0)
                            player.monedas = result.get("monedas", 0)
                            player.sala_id = result.get("sala_id", 1)
                            player.salas_limpias = set(result.get("salas_limpias", []))
                            player.inventario = result.get("inventario", {})
                        else:
                            await player.send({"type": "login_error", "text": "Usuario o contrasena incorrectos"})
                            continue
                        
                        base = CLASES[clase]
                        player.personaje = {
                            "nombreClase": clase,
                            "vidaMax": base["vidaMax"],
                            "vidaActual": base["vidaMax"],
                            "manaMax": base["manaMax"],
                            "manaActual": base["manaMax"],
                            "danioBase": base["danioBase"],
                            "manaTurno": base.get("manaTurno", 0),
                            "ataquesTurno": base.get("ataquesTurno", 1),
                            "costoEspecial": base.get("costoEspecial", 0),
                            "danioEspecial": base.get("danioEspecial", base["danioBase"]),
                            "curacionEspecial": base.get("curacionEspecial", 0),
                        }
                        
                        await player.send({"type": "login_ok"})
                        await broadcast_stats(player)
                        await broadcast_ranking()
                    
                    elif data.get("type") == "register":
                        usuario = data.get("usuario", "")
                        password = data.get("password", "")
                        nombre = data.get("nombre", usuario)
                        clase = data.get("clase", "guerrero")
                        
                        if clase not in CLASES:
                            clase = "guerrero"
                        
                        result = await crear_cuenta(usuario, password, nombre, clase)
                        if not result:
                            await player.send({"type": "login_error", "text": "El usuario ya existe"})
                            continue
                        print(f"[ACCOUNT] Created: {usuario}, users in memory: {len(USUARIOS)}")
                        player.usuario = usuario
                        player.nombre = nombre
                        player.clase = clase
                        player.clase = clase
                        
                        base = CLASES[clase]
                        player.personaje = {
                            "nombreClase": clase,
                            "vidaMax": base["vidaMax"],
                            "vidaActual": base["vidaMax"],
                            "manaMax": base["manaMax"],
                            "manaActual": base["manaMax"],
                            "danioBase": base["danioBase"],
                            "manaTurno": base.get("manaTurno", 0),
                            "ataquesTurno": base.get("ataquesTurno", 1),
                            "costoEspecial": base.get("costoEspecial", 0),
                            "danioEspecial": base.get("danioEspecial", base["danioBase"]),
                            "curacionEspecial": base.get("curacionEspecial", 0),
                        }
                        
                        await player.send({"type": "register_ok"})
                        await broadcast_stats(player)
                        await broadcast_ranking()
                    
                    elif data.get("type") == "command":
                        await process_command(player, data.get("cmd", ""))
                    
                    elif data.get("type") == "action":
                        if player.combate:
                            player.combate.acciones[player.id] = data.get("action", "1")
                    
                    elif data.get("type") == "chat":
                        msg_text = data.get("message", "").strip()
                        if msg_text and player.nombre:
                            scope = data.get("scope", "sala")
                            if scope == "sala":
                                await broadcast_sala(player.sala_id, f"[Sala] {player.nombre}: {msg_text}", exclude=player)
                            elif scope == "global":
                                await broadcast_global(f"[Global] {player.nombre}: {msg_text}", exclude=player)
                            elif scope == "grupo" and player.grupo:
                                for p in player.grupo["miembros"]:
                                    if p != player:
                                        await p.send({"type": "chat", "scope": "grupo", "from": player.nombre, "text": msg_text})
                
                except:
                    pass
            
            elif msg.type in (aiohttp.WSMsgType.ERROR, aiohttp.WSMsgType.CLOSE):
                break
    
    finally:
        if player in jugadores_conectados:
            jugadores_conectados.remonedasve(player)
        if player.usuario and player.personaje:
            await guardar_cuenta(player.usuario, {
                "nombre": player.nombre,
                "clase": player.personaje.get("nombreClase", "guerrero"),
                "nivel": player.nivel,
                "xp": player.xp,
                "monedas": player.monedas,
                "sala_id": player.sala_id,
                "salas_limpias": list(player.salas_limpias),
                "inventario": getattr(player, 'inventario', {}),
                "misiones": getattr(player, 'misiones', {}),
            })
    
    return ws

# ==================== COMMANDS ====================
async def process_command(player, cmd):
    cmd = cmd.strip().lower()
    if not cmd:
        return
    
    if player.combate:
        if cmd in ["1", "2", "3"]:
            player.combate.acciones[player.id] = cmd
            return
    
    if cmd in ["n", "norte"]:
        await monedasve(player, "norte")
    elif cmd in ["s", "sur"]:
        await monedasve(player, "sur")
    elif cmd in ["e", "este"]:
        await monedasve(player, "este")
    elif cmd in ["o", "oeste"]:
        await monedasve(player, "oeste")
    elif cmd == "atacar":
        await attack(player)
    elif cmd == "mirar":
        await describe_sala(player)
    elif cmd == "stats":
        await broadcast_stats(player)
    elif cmd.startswith("decir "):
        msg = cmd[6:]
        await broadcast_sala(player.sala_id, f"[Sala] {player.nombre}: {msg}", exclude=player)
    elif cmd.startswith("g "):
        msg = cmd[2:]
        await broadcast_global(f"[Global] {player.nombre}: {msg}", exclude=player)
    elif cmd == "hospital":
        await hospital(player)
    elif cmd == "tienda":
        await tienda(player)
    elif cmd.startswith("comprar "):
        item = cmd[8:].strip()
        await comprar(player, item)
    elif cmd.startswith("usar "):
        item = cmd[5:].strip()
        await usar(player, item)
    elif cmd == "monedaschila":
        await monedaschila(player)
    elif cmd == "ranking":
        await broadcast_ranking()
    elif cmd == "ayuda":
        await player.send({"type": "message", "text": "Comandos: n/s/e/o (monedasver), atacar, stats, hospital, tienda, comprar <item>, usar <item>, monedaschila, ranking"})
    else:
        await player.send({"type": "message", "text": f"Comando '{cmd}' desconocido. Escribe 'ayuda'"})

async def monedasve(player, direction):
    if player.combate:
        await player.send({"type": "message", "text": "No puedes monedasverte en combate!"})
        return
    if player.muerto:
        await player.send({"type": "message", "text": "Estas muerto."})
        return
    
    sala = SALAS.get(player.sala_id)
    if not sala:
        return
    
    if player.sala_id not in player.salas_limpias:
        if "bioma" in sala or sala.get("encuentros"):
            await player.send({"type": "message", "text": "Hay enemigos! Derrotalos primero."})
            return
    
    nueva = sala.get("conexiones", {}).get(direction)
    if nueva is None:
        await player.send({"type": "message", "text": f"No puedes ir al {direction}"})
        return
    
    await broadcast_sala(player.sala_id, f"🚪 {player.nombre} se va al {direction}.", exclude=player)
    player.sala_id = nueva
    await broadcast_sala(player.sala_id, f"🚪 {player.nombre} ha llegado.", exclude=player)
    await describe_sala(player)
    await guardar_cuenta(player.usuario, {"nombre": player.nombre, "clase": player.personaje.get("nombreClase", "guerrero"), "nivel": player.nivel, "xp": player.xp, "monedas": player.monedas, "sala_id": player.sala_id, "salas_limpias": list(player.salas_limpias)})

async def describe_sala(player):
    sala = SALAS.get(player.sala_id, {})
    
    bioma_info = ""
    if "bioma" in sala:
        bioma = BIOMAS.get(sala["bioma"], {})
        bioma_info = f" [{bioma.get('emonedasji', '')} {sala['bioma']}]"
    
    tiene_enemigos = player.sala_id not in player.salas_limpias and ("bioma" in sala or sala.get("encuentros"))
    
    others = [p.nombre for p in jugadores_conectados if p.sala_id == player.sala_id and p != player and p.nombre]
    others_str = f" 👥 Jugadores: {', '.join(others)}" if others else ""
    
    await player.send({
        "type": "sala",
        "sala_id": player.sala_id,
        "nombre": sala.get("nombre", "?"),
        "descripcion": sala.get("descripcion", "") + bioma_info,
        "conexiones": sala.get("conexiones", {}),
        "hospital": sala.get("hospital", False),
        "tienda": sala.get("tienda", False),
        "enemigos": tiene_enemigos,
        "others": others_str,
    })

async def attack(player):
    if player.combate:
        await player.send({"type": "message", "text": "Ya estas en combate!"})
        return
    if player.muerto:
        await player.send({"type": "message", "text": "Estas muerto."})
        return
    
    if player.sala_id in player.salas_limpias:
        await player.send({"type": "message", "text": "No hay enemigos aqui."})
        return
    
    sala = SALAS.get(player.sala_id)
    if not sala or ("bioma" not in sala and not sala.get("encuentros")):
        await player.send({"type": "message", "text": "No hay enemigos aqui."})
        return
    
    if player.sala_id in combates_activos:
        c = combates_activos[player.sala_id]
        if player not in c.jugadores:
            c.jugadores.append(player)
            player.combate = c
            await player.send({"type": "combat_start", "enemigos": [{"nombre": e["nombre"], "hp": e["hp"], "hpMax": e["vidaMax"]} for e in c.enemigos], "joined": True})
    else:
        combate = Combate(player.sala_id, [player])
        combate.cargar_enemigos()
        player.combate = combate
        combates_activos[player.sala_id] = combate
        asyncio.create_task(loop_combate(combate))
        
        for p in jugadores_conectados:
            if p.sala_id == player.sala_id and p != player and p.personaje and p.personaje["vidaActual"] > 0:
                await p.send({"type": "combat_join_request", "from": player.nombre})
    
    await player.send({"type": "combat_start", "enemigos": [{"nombre": e["nombre"], "hp": e["hp"], "hpMax": e["vidaMax"]} for e in combate.enemigos]})
    await broadcast_sala(player.sala_id, f"⚔️ COMBATE! {player.nombre} ataca!")

async def hospital(player):
    sala = SALAS.get(player.sala_id)
    if sala and sala.get("hospital"):
        if player.personaje:
            player.personaje["vidaActual"] = player.personaje["vidaMax"]
            player.personaje["manaActual"] = player.personaje["manaMax"]
        await player.send({"type": "message", "text": "🏥 Te han curado completamente!"})
        await broadcast_stats(player)
    else:
        await player.send({"type": "message", "text": "No hay hospital aqui."})

async def tienda(player):
    items = [{"id": k, **v} for k, v in CATALOGO.items()]
    await player.send({"type": "shop", "items": items, "monedas": player.monedas})

async def comprar(player, item_id):
    if item_id in CATALOGO:
        precio = CATALOGO[item_id]["precio"]
        if player.monedas >= precio:
            player.monedas -= precio
            player.inventario[item_id] = player.inventario.get(item_id, 0) + 1
            await player.send({"type": "message", "text": f"Comprado: {CATALOGO[item_id]['nombre']}!"})
        else:
            await player.send({"type": "message", "text": "No tienes suficientes monedas."})
    else:
        await player.send({"type": "message", "text": "Item no encontrado."})

async def usar(player, item_id):
    if item_id in player.inventario and player.inventario[item_id] > 0:
        if item_id == "pocion_vida" and player.personaje:
            player.personaje["vidaActual"] = player.personaje["vidaMax"]
            player.inventario[item_id] -= 1
            await player.send({"type": "message", "text": "🧪 Has usado Pocion de Vida!"})
            await broadcast_stats(player)
        elif item_id == "pocion_danio":
            player.buff_danio = True
            player.inventario[item_id] -= 1
            await player.send({"type": "message", "text": "⚗️ +30% dano por este combate!"})
        elif item_id == "gema_teleporte":
            player.inventario[item_id] -= 1
            player.sala_id = SALA_RESPAWN
            await player.send({"type": "message", "text": "💎 Te has teleportado al oasis!"})
            await describe_sala(player)
        else:
            await player.send({"type": "message", "text": "No puedes usar este item."})
    else:
        await player.send({"type": "message", "text": "No tienes ese objeto."})

async def monedaschila(player):
    items = []
    for iid, qty in player.inventario.items():
        if qty > 0:
            item = CATALOGO.get(iid, {"nombre": iid, "emonedasji": "📦"})
            items.append(f"{item.get('emonedasji', '📦')} {item['nombre']} x{qty}")
    if items:
        await player.send({"type": "message", "text": "🎒 Inventario:\n" + "\n".join(items)})
    else:
        await player.send({"type": "message", "text": "🎒 Inventario vacio."})

# ==================== WAKE / HEALTH ====================
async def health_check(request):
    return web.json_response({"status": "ok", "players": len(jugadores_conectados)})

async def wake(request):
    return web.json_response({"status": "awake", "players": len(jugadores_conectados)})

# ==================== HTTP HANDLER (client web) ====================
async def index(request):
    with open(os.path.join(os.path.dirname(__file__), "client.html")) as f:
        html = f.read()
    return web.Response(text=html, content_type="text/html")

# ==================== APP ====================
app = web.Application()
app.router.add_get('/', index)
app.router.add_get('/health', health_check)
app.router.add_get('/wake', wake)
app.router.add_get('/ws', websocket_handler)

if __name__ == '__main__':
    print(f"🎮 Game Server starting on port {PORT}")
    print(f"💾 Using local saves: {SAVES_DIR}")
    web.run_app(app, host='0.0.0.0', port=PORT)
