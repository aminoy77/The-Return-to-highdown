"""
THE RETURN TO HIGHDOWN - MUD Game Server
=========================================
Optimized for: Render 512MB RAM, 0.1 CPU

Features:
- Single UI with all functionality
- 3 Chat types: Global, Sala, Group
- Ranking system
- Stats screen
- Combat with buttons (auto-attack)
- Group system for multiplayer combat
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
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
USAR_SUPABASE = bool(SUPABASE_URL and SUPABASE_KEY)
SAVES_DIR = "saves"
os.makedirs(SAVES_DIR, exist_ok=True)

# ==================== GAME CONSTANTS ====================
XP_POR_NIVEL = 150
MONEDAS_SUBIDA = 20
SALA_RESPAWN = 6
TIEMPO_RESPAWN = 5
MAX_JUGADORES = 10
COMBAT_TURN_TIME = 5

# ==================== CLASES ====================
CLASES = {
    "guerrero": {"vidaMax": 90, "danioBase": 40, "manaMax": 30, "manaTurno": 10, "danioEspecial": 70, "ataquesTurno": 1, "costoEspecial": 30, "habilidad": "golpe_tanque"},
    "mago": {"vidaMax": 50, "danioBase": 30, "manaMax": 70, "manaTurno": 20, "danioEspecial": 60, "ataquesTurno": 1, "costoEspecial": 60, "habilidad": "magia_antigua"},
    "arquero": {"vidaMax": 40, "danioBase": 10, "manaMax": 40, "manaTurno": 15, "danioEspecial": 10, "ataquesTurno": [1, 4], "costoEspecial": 40, "habilidad": "flecha_ignea", "danioEfecto": 10, "duracionEfecto": 2},
    "curandero": {"vidaMax": 50, "danioBase": 20, "manaMax": 50, "manaTurno": 20, "danioEspecial": 20, "ataquesTurno": 1, "costoEspecial": 30, "habilidad": "absorcion", "curacionEspecial": 20},
    "nigromante": {"vidaMax": 50, "danioBase": 10, "manaMax": 80, "manaTurno": 20, "danioEspecial": 60, "ataquesTurno": [1, 5], "costoEspecial": 60, "habilidad": "maldicion_tiempo"},
    "hechicero": {"vidaMax": 50, "danioBase": 30, "manaMax": 70, "manaTurno": 30, "danioEspecial": 70, "ataquesTurno": 1, "costoEspecial": 70, "habilidad": "invocar_esqueleto"},
    "caballero": {"vidaMax": 70, "danioBase": 50, "manaMax": 40, "manaTurno": 10, "danioEspecial": 60, "ataquesTurno": 1, "costoEspecial": 40, "habilidad": "embestida"},
    "cazador": {"vidaMax": 60, "danioBase": 50, "manaMax": 30, "manaTurno": 10, "danioEspecial": 30, "ataquesTurno": 1, "costoEspecial": 30, "habilidad": "inmovilizar"},
    "asesino": {"vidaMax": 50, "danioBase": 20, "manaMax": 20, "manaTurno": 10, "danioEspecial": 60, "ataquesTurno": [1, 3], "costoEspecial": 20, "habilidad": "muerte_garantizada"},
    "barbaro": {"vidaMax": 60, "danioBase": 50, "manaMax": 30, "manaTurno": 5, "danioEspecial": 70, "ataquesTurno": 1, "costoEspecial": 30, "habilidad": "abocajarro"},
}

# ==================== ENEMIGOS ====================
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
    "ciclope": {"vidaMax": 80, "danioBase": 40, "ataquesTurno": 1, "tier": "Especial"},
    "hombreLobo": {"vidaMax": 90, "danioBase": 30, "ataquesTurno": [1, 3], "tier": "Especial"},
    "quimera": {"vidaMax": 80, "danioBase": 20, "ataquesTurno": 1, "tier": "Especial"},
    "demonioInferior": {"vidaMax": 90, "danioBase": 20, "ataquesTurno": [1, 2], "tier": "Especial"},
    "tiburon": {"vidaMax": 80, "danioBase": 30, "ataquesTurno": 1, "tier": "Especial"},
    "vampiro": {"vidaMax": 125, "danioBase": 20, "ataquesTurno": [1, 2], "tier": "Superior"},
    "altoOrco": {"vidaMax": 150, "danioBase": 50, "ataquesTurno": 1, "tier": "Superior"},
    "golem": {"vidaMax": 180, "danioBase": 50, "ataquesTurno": 1, "tier": "Superior"},
    "elfoOscuro": {"vidaMax": 150, "danioBase": 60, "ataquesTurno": 1, "tier": "Superior"},
    "demonioSuperior": {"vidaMax": 150, "danioBase": 60, "ataquesTurno": 1, "tier": "Superior"},
    "leviatan": {"vidaMax": 250, "danioBase": 80, "ataquesTurno": 1, "tier": "Elite"},
    "reyEsqueleto": {"vidaMax": 230, "danioBase": 80, "ataquesTurno": 1, "tier": "Elite"},
    "dragon": {"vidaMax": 250, "danioBase": 80, "ataquesTurno": 1, "tier": "Elite"},
    "reyDemonio": {"vidaMax": 250, "danioBase": 70, "ataquesTurno": 1, "tier": "Boss"},
    "kraken": {"vidaMax": 400, "danioBase": 70, "ataquesTurno": 1, "tier": "Boss"},
    "alpha": {"vidaMax": 500, "danioBase": 90, "ataquesTurno": 1, "tier": "Boss"},
}

XP_POR_TIER = {"Base": 10, "Especial": 30, "Superior": 50, "Elite": 100, "Boss": 250}

# ==================== TIENDA ====================
CATALOGO = {
    "pocion_vida": {"nombre": "Pocion de Vida", "emoji": "🧪", "descripcion": "Restaura toda tu vida", "precio": 30, "usable_combate": True},
    "pocion_danio": {"nombre": "Pocion de Danio", "emoji": "⚗️", "descripcion": "+30% dano durante 1 combate", "precio": 40, "usable_combate": True},
    "gema_teleporte": {"nombre": "Gema de Teletransporte", "emoji": "💎", "descripcion": "Teleporta a cualquier sala", "precio": 50, "usable_combate": False},
}

# ==================== BIOMAS ====================
BIOMAS = {
    "desierto": {"emoji": "🏜", "descripcion": "Calor abrasador. Arena en todas partes.", "enemigos": ["bandido", "duende", "esqueleto", "zombie", "lobo", "demonioInferior", "quimera"]},
    "mar": {"emoji": "🌊", "descripcion": "Humedad salada. Se escucha el oleaje.", "enemigos": ["tiburon", "slime", "hombreLobo", "orco", "ogro", "vampiro", "troll"]},
    "nieve": {"emoji": "❄️", "descripcion": "Frio glacial. El viento corta como un cuchillo.", "enemigos": ["gigante", "ciclope", "golem", "elfoOscuro", "altoOrco", "demonioSuperior", "reyEsqueleto"]},
}

# ==================== ACERTIJOS ====================
ACERTIJOS = [
    {"pregunta": "Si me nombras, desaparezco. ¿Qué soy?", "opciones": ["A) El secreto", "B) El silencio", "C) La sombra", "D) El pensamiento"], "respuesta": "b", "letra_correcta": "B"},
    {"pregunta": "¿Qué número falta? 2 – 6 – 7 – 21 – 22 – 66 – ?", "opciones": ["A) 67", "B) 132", "C) 198", "D) 68"], "respuesta": "a", "letra_correcta": "A"},
    {"pregunta": "Un monje copia: 11/11/1111. ¿Es la primera vez con todos los números iguales?", "opciones": ["A) Sí", "B) No", "C) Solo en calendario juliano", "D) Solo si cuenta los ceros"], "respuesta": "b", "letra_correcta": "B"},
    {"pregunta": "3 interruptores, 3 bombillas, 1 solo intento. ¿Cómo saber cuál controla cada una?", "opciones": ["A) Enciende uno, espera, cambia al segundo y entra", "B) Enciende dos, espera, apaga uno y entra", "C) Enciende uno, espera, luego enciende el segundo y entra", "D) No hay manera"], "respuesta": "b", "letra_correcta": "B"},
]

SALAS_ACERTIJOS = {33: [0, 1, 2], 37: [1, 2, 3]}

# ==================== LORE ====================
LORE_INICIAL = """Hace ya 15 años de la gran tragedia. Highdown era un pueblo conocido por que todos los nacidos ahí poseían habilidades sobrehumanas. Eso no contentaba a Alpha, el actual rey de la destrucción. Todo lo que encontraba a su paso, ardía en un mar de llamas y sangre.

Alpha esperó a la noche, que todos estuvieran durmiendo, reunió a sus mejores hombres y aniquiló a todos sus habitantes. O eso pensaba él, pues uno de los soldados del pueblo pudo salvar a algunos de los niños con futuros más prometedores.

El soldado les dijo: "Huid lejos de aquí y vengad a vuestro pueblo."

Uno de los chicos eres tú. Ahora empezarás a estudiar en la escuela más prestigiosa de todo el país, si llegas con vida."""

LORE_SALAS = {
    1: ("MISIÓN 1 — El Rey Demonio", "Tu misión comienza cuando descubres que la llave del Rey Demonio es necesaria para evitar que el mundo caiga en una era de oscuridad por culpa de Alpha. Necesitarás 2 llaves. Una la tiene el Rey Demonio, la otra... el Kraken."),
    16: ("El Dominio Oscuro", "Para llegar al Rey Demonio, debes atravesar tres sellos antiguos, cada uno custodiado por entidades que representan el miedo, la desesperación y el odio."),
    33: ("MISIÓN 2 — El Kraken", "Tras volver victorioso del Desierto, eres recompensado. Ahora debes hacerte con la segunda llave que guarda el Kraken."),
    72: ("Las Bermudas — El Kraken Despierta", "Un tentáculo gigantesco emerge de las profundidades y rompe el mástil principal del barco."),
    73: ("MISIÓN 3 — Alpha", "Ahora tienes las dos llaves. Tu misión: Highdown. Tu objetivo es asesinar a Alpha y recuperar el dominio de tu pueblo."),
    148: ("La Caída de Alpha — FIN", "Tras la muerte de Alpha vuelves al pueblo victorioso. Mañana te coronarán como rey."),
}

LORE_POST_COMBATE = {
    32: ("El Rey Demonio Cae", "Antes de desaparecer, deja la llave en tus manos. Comprendes entonces que no has derrotado a un tirano, sino a un guardián."),
    72: ("Victoria sobre el Kraken", "Habéis derrotado a la leyenda más temida de los 7 mares. Poco a poco te estás convirtiendo en un gran guerrero."),
    148: ("La Caída de Alpha — FIN", "Un verdadero enemigo no tiene enemigos. Si entiendes eso, serás capaz de reinar como un verdadero guerrero."),
}

# ==================== BOSS ====================
BOSS_SALAS = {15: ("El Gran Bandido", 300), 30: ("Señor de los Muertos", 420), 50: ("Leviatán del Mar", 600), 75: ("Rey del Hielo", 900), 100: ("El Demonio Supremo", 1200), 148: ("Alpha", 1800)}

# ==================== SALAS ====================
SALAS = {
    0.1: {"nombre": "Como combatir", "descripcion": "El soldado te da una espada corta.", "conexiones": {"norte": 0.2}, "encuentros": [("bandido", 1)]},
    0.2: {"nombre": "Hospital y Tienda", "descripcion": "Aqui puedes curarte y comprar objetos.", "conexiones": {"sur": 0.1, "norte": 0.3}, "hospital": True, "tienda": True},
    0.3: {"nombre": "Objetos", "descripcion": "Usa pocion_vida, pocion_danio, gema_teleporte", "conexiones": {"sur": 0.2, "norte": 0.4}, "encuentros": [("duende", 1)]},
    0.4: {"nombre": " UI", "descripcion": "Usa los botones o escribe comandos.", "conexiones": {"sur": 0.3, "norte": 1}},
    1: {"nombre": "North Mass", "descripcion": "Arena caliente bajo tus pies.", "conexiones": {"norte": 2, "este": 13, "sur": 6}, "bioma": "desierto", "cantidad": 1, "hospital": True},
    2: {"nombre": "Dunas del Norte", "descripcion": "Dunas interminables.", "conexiones": {"sur": 1, "norte": 3}, "bioma": "desierto", "cantidad": 2},
    3: {"nombre": "Ruinas del Desierto", "descripcion": "Columnas rotas.", "conexiones": {"oeste": 4, "norte": 5, "este": 16}, "bioma": "desierto", "cantidad": 2},
    4: {"nombre": "Ciudad abrasada", "descripcion": "Una ciudad quemada.", "conexiones": {"este": 3}, "encuentros": [("demonioSuperior", 1)], "hospital": True},
    5: {"nombre": "Valle muerto", "descripcion": "Cuerpos muertos por doquier.", "conexiones": {"sur": 3}, "bioma": "desierto", "cantidad": 2, "hospital": True},
    6: {"nombre": "Oasis tranquilo", "descripcion": "Un pequeno oasis.", "conexiones": {"sur": 10, "oeste": 7, "norte": 1}, "hospital": True, "tienda": True},
    7: {"nombre": "Sala del Viento Susurrante", "descripcion": "Voces del pasado.", "conexiones": {"oeste": 8, "este": 6, "sur": 9}, "encuentros": [("elfoOscuro", 1)]},
    8: {"nombre": "Cámara del Oasis Oculto", "descripcion": "Un lago magico.", "conexiones": {"oeste": 9, "este": 7}, "bioma": "desierto", "cantidad": 1},
    9: {"nombre": "Salón del Sol Eterno", "descripcion": "Un sol artificial.", "conexiones": {"sur": 8, "este": 7}, "bioma": "desierto", "cantidad": 2, "hospital": True, "tienda": True},
    10: {"nombre": "Cripta de las Dunas Vivas", "descripcion": "Cuerpos que se mueven.", "conexiones": {"norte": 7}, "bioma": "desierto", "cantidad": 2},
    11: {"nombre": "Caravana fantasma", "descripcion": "Viajeros espectrales.", "conexiones": {"este": 12, "norte": 6}, "encuentros": [("demonioInferior", 2)]},
    12: {"nombre": "Fosa de Titanes", "descripcion": "Restos colosales.", "conexiones": {"norte": 13, "este": 17}, "bioma": "desierto", "cantidad": 2},
    13: {"nombre": "Templo Olvidado", "descripcion": "Un templo en el desierto.", "conexiones": {"sur": 12, "este": 18, "norte": 14}, "encuentros": [("reyEsqueleto", 1)], "tienda": True},
    14: {"nombre": "Extensión de Azhar", "descripcion": "El suelo arde.", "conexiones": {"norte": 15, "este": 19, "oeste": 1}, "bioma": "desierto", "cantidad": 1},
    15: {"nombre": "Mar de Dunas Susurrantes", "descripcion": "Las dunas susurran.", "conexiones": {"norte": 16, "sur": 14}, "bioma": "desierto", "cantidad": 2},
    16: {"nombre": "Vestigios Enterrados", "descripcion": "Ruinas antiguas.", "conexiones": {"norte": 17, "sur": 15}, "bioma": "desierto", "cantidad": 1},
    17: {"nombre": "Santuario Carmesí", "descripcion": "Simbolos sangrientos.", "conexiones": {"sur": 16, "este": 22, "oeste": 3}, "encuentros": [("demonioInferior", 2)], "tienda": True},
    18: {"nombre": "Sepulcro de Colosos", "descripcion": "Huesos gigantescos.", "conexiones": {"oeste": 11}, "bioma": "desierto", "cantidad": 2, "tienda": True},
    19: {"nombre": "Trono del Abismo", "descripcion": "Estructura de hueso y sombra.", "conexiones": {"oeste": 12, "este": 27}, "bioma": "desierto", "cantidad": 1},
    20: {"nombre": "Llanura de Fuego Blanco", "descripcion": "Luz intensa.", "conexiones": {"norte": 21, "este": 26, "este": 13}, "bioma": "desierto", "cantidad": 1},
    21: {"nombre": "Dunas del Murmullo Eterno", "descripcion": "Algo se mueve bajo la arena.", "conexiones": {"sur": 20, "este": 25}, "bioma": "desierto", "cantidad": 2},
    22: {"nombre": "Columnas del Olvido", "descripcion": "Pilares erosionados.", "conexiones": {"este": 15}, "bioma": "desierto", "cantidad": 2, "hospital": True, "tienda": True},
    23: {"nombre": "Templo de la Sangre Antigua", "descripcion": "Inscripciones vivas.", "conexiones": {"este": 24, "oeste": 16}, "encuentros": [("demonioInferior", 2)]},
    24: {"nombre": "Abismo de los Caídos", "descripcion": "Restos antiguos.", "conexiones": {"sur": 25, "norte": 23, "este": 32}, "bioma": "desierto", "cantidad": 2},
    25: {"nombre": "Trono del Devastador", "descripcion": "Asiento de poder olvidado.", "conexiones": {"sur": 30, "norte": 23, "este": 32}, "bioma": "desierto", "cantidad": 4, "tesoro": True},
    26: {"nombre": "Horizonte Quebrado", "descripcion": "El aire distorsiona.", "conexiones": {"oeste": 20, "sur": 27}, "bioma": "desierto", "cantidad": 1, "tienda": True, "hospital": True},
    27: {"nombre": "Dunas del Hambre", "descripcion": "La arena se mueve.", "conexiones": {"oeste": 19, "norte": 25}, "bioma": "desierto", "cantidad": 2},
    28: {"nombre": "Ruinas del Eco Silente", "descripcion": "Cada paso resuena.", "conexiones": {"oeste": 18, "este": 29}, "bioma": "desierto", "cantidad": 2},
    29: {"nombre": "Santuario de la Marca Roja", "descripcion": "Antiguos rituales.", "conexiones": {"oeste": 28, "norte": 30}, "encuentros": [("demonioInferior", 2)], "tesoro": True},
    30: {"nombre": "Campos de Huesos Errantes", "descripcion": "Restos que cambian.", "conexiones": {"sur": 29, "norte": 31}, "bioma": "desierto", "cantidad": 2},
    31: {"nombre": "Trono del Último Señor", "descripcion": "Dominio absoluto.", "conexiones": {"oeste": 25, "norte": 32}, "encuentros": [("reyEsqueleto", 1)]},
    32: {"nombre": "Falla de los Antiguos", "descripcion": "Grieta con reliquias.", "conexiones": {"sur": 31}, "bioma": "desierto", "cantidad": 2, "hospital": True},
    33: {"nombre": "Trono de Ceniza Viva", "descripcion": "El asiento aun deshuele.", "conexiones": {"este": 34, "norte": 37}, "encuentros": [("reyDemonio", 1)], "acertijos": True},
    34: {"nombre": "Embarcadero 1", "descripcion": "La marea calmada.", "conexiones": {"norte": 38, "este": 39, "sur": 35}, "bioma": "mar"},
    35: {"nombre": "Abismo Coralino", "descripcion": "Corales brillantes.", "conexiones": {"este": 36}, "bioma": "mar", "cantidad": 1, "hospital": True},
    36: {"nombre": "Trono del Oceano", "descripcion": "Un trono erodedo.", "conexiones": {"este": 37}, "bioma": "mar", "cantidad": 2, "tesoro": True},
    37: {"nombre": "Embarcadero 2", "descripcion": "El puerto rebosante.", "conexiones": {"norte": 42}, "bioma": "mar", "acertijos": True},
    38: {"nombre": "Fosa de las Sombras Marinas", "descripcion": "Profundidad oscura.", "conexiones": {"norte": 43, "este": 39}, "bioma": "mar", "cantidad": 2, "hospital": True},
    39: {"nombre": "Arrecife Susurrante", "descripcion": "Coral con sonidos.", "conexiones": {"norte": 44, "este": 40}, "bioma": "mar", "cantidad": 1, "tesoro": True},
    40: {"nombre": "Caverna de la Bruma Salina", "descripcion": "Niebla con olor a sal.", "conexiones": {"este": 41, "sur": 36}, "bioma": "mar", "cantidad": 2},
    41: {"nombre": "Templo de las Olas Eternas", "descripcion": "Estructuras antiguas.", "conexiones": {"norte": 46, "este": 40}, "bioma": "mar", "cantidad": 3},
    42: {"nombre": "Laguna de los Naufragos", "descripcion": "Restos de barcos.", "conexiones": {"norte": 52, "este": 43}, "bioma": "mar", "cantidad": 1},
    43: {"nombre": "Pantano del Silencio", "descripcion": "Un pantano inmóvil.", "conexiones": {"norte": 51, "este": 44}, "bioma": "mar", "cantidad": 2},
    44: {"nombre": "Refugio de las Medusas", "descripcion": "Crias translucidas.", "conexiones": {"norte": 50, "este": 45}, "bioma": "mar", "cantidad": 3, "hospital": True, "tienda": True},
    45: {"nombre": "Camara del Pulpo Antiguo", "descripcion": "Tentaculos gigantes.", "conexiones": {"oeste": 44}, "bioma": "mar", "cantidad": 1},
    46: {"nombre": "Bosque de Manglares Oscuros", "descripcion": "Raices retorcidas.", "conexiones": {"este": 47, "norte": 48}, "bioma": "mar", "cantidad": 2},
    47: {"nombre": "Isla de la Lluvia Perpetua", "descripcion": "Nunca deja de llover.", "conexiones": {"norte": 48}, "bioma": "mar", "cantidad": 3},
    48: {"nombre": "Grieta Abisal", "descripcion": "Fisura profunda.", "conexiones": {"norte": 59}, "bioma": "mar", "cantidad": 1},
    49: {"nombre": "Playa de los Ecos Hundidos", "descripcion": "Las olas traen voces.", "conexiones": {"norte": 56, "este": 50}, "bioma": "mar", "cantidad": 2},
    50: {"nombre": "Torre del Vigia Marino", "descripcion": "Una torre solitaria.", "conexiones": {"sur": 44, "este": 49, "norte": 55}, "bioma": "mar", "cantidad": 1},
    51: {"nombre": "Gruta de las Mareas Silentes", "descripcion": "El agua sin ruido.", "conexiones": {"norte": 54, "este": 50}, "bioma": "mar", "cantidad": 2, "tesoro": True},
    52: {"nombre": "Pantano de las Raices Hundidas", "descripcion": "Raices gigantes.", "conexiones": {"norte": 53, "este": 51}, "bioma": "mar", "cantidad": 3},
    53: {"nombre": "Caverna del Coral Luminoso", "descripcion": "Coral con luz.", "conexiones": {"este": 54}, "bioma": "mar", "cantidad": 1, "hospital": True},
    54: {"nombre": "Estuario del Viento Humedo", "descripcion": "Aire humedo.", "conexiones": {"este": 55, "sur": 50}, "bioma": "mar", "cantidad": 2, "tesoro": True},
    55: {"nombre": "Pozo de Agua Estancada", "descripcion": "Agua quieta.", "conexiones": {"sur": 50}, "bioma": "mar", "cantidad": 1},
    56: {"nombre": "Acantilado de la Lluvia Fina", "descripcion": "Llovizna constante.", "conexiones": {"sur": 49}, "bioma": "mar", "cantidad": 3},
    57: {"nombre": "Laguna de las Sombras Flotantes", "descripcion": "Figuras oscuras.", "conexiones": {"norte": 58, "este": 59}, "bioma": "mar", "cantidad": 2},
    58: {"nombre": "Bosque Inundado Antiguo", "descripcion": "Arboles muertos.", "conexiones": {"este": 60}, "bioma": "mar", "cantidad": 1, "tienda": True, "tesoro": True},
    59: {"nombre": "Camara de las Corrientes Ocultas", "descripcion": "Agua invisible.", "conexiones": {"norte": 60, "este": 62}, "bioma": "mar", "cantidad": 3},
    60: {"nombre": "Isla del Horizonte Gris", "descripcion": "Cielo y mar fusionados.", "conexiones": {"este": 61}, "bioma": "mar", "cantidad": 2},
    61: {"nombre": "Fosa de la Marea Negra", "descripcion": "Agua oscura.", "conexiones": {"este": 64}, "bioma": "mar", "cantidad": 1},
    62: {"nombre": "Playa de la Arena Humeda", "descripcion": "Arena siempre humeda.", "conexiones": {"este": 63}, "bioma": "mar", "cantidad": 2, "tesoro": True},
    63: {"nombre": "Gruta del Agua Resonante", "descripcion": "Gotas con ecos.", "conexiones": {"este": 66}, "bioma": "mar", "cantidad": 3},
    64: {"nombre": "Delta de los Canales Perdidos", "descripcion": "Laberinto de agua.", "conexiones": {"este": 65}, "bioma": "mar", "cantidad": 1, "tesoro": True},
    65: {"nombre": "Arrecife de las Espinas Blancas", "descripcion": "Formaciones afiladas.", "conexiones": {"este": 67, "sur": 66}, "bioma": "mar", "cantidad": 2},
    66: {"nombre": "Pantano de la Lluvia Eterna", "descripcion": "Lluvia sin descanso.", "conexiones": {"este": 68, "sur": 63}, "bioma": "mar", "cantidad": 3},
    67: {"nombre": "Caverna del Vapor Salino", "descripcion": "Aire caliente.", "conexiones": {"este": 65}, "bioma": "mar", "cantidad": 1},
    68: {"nombre": "Laguna de los Reflejos Rotos", "descripcion": "Superficie distorsionada.", "conexiones": {"este": 69}, "bioma": "mar", "cantidad": 2},
    69: {"nombre": "Sendero del Lodo Profundo", "descripcion": "Terreno blando.", "conexiones": {"este": 70}, "bioma": "mar", "cantidad": 1},
    70: {"nombre": "Bahia de la Niebla Densa", "descripcion": "Niebla espesa.", "conexiones": {"este": 71}, "bioma": "mar", "cantidad": 3, "hospital": True},
    71: {"nombre": "Cumbre del Leviatan", "descripcion": "Acantilado imposible.", "conexiones": {"este": 72}, "bioma": "mar", "cantidad": 1},
    72: {"nombre": "Cumbre del Kraken", "descripcion": "Una sombra colosal.", "conexiones": {"este": 73}, "bioma": "mar", "cantidad": 1, "encuentros": [("kraken", 1)]},
    73: {"nombre": "Ventisca Eterna", "descripcion": "El viento ruge.", "conexiones": {"este": 74, "oeste": 72}, "bioma": "nieve", "cantidad": 1},
    74: {"nombre": "Bosque de Hielo Negro", "descripcion": "Arboles oscuros.", "conexiones": {"este": 76}, "bioma": "nieve", "cantidad": 2},
    75: {"nombre": "Grieta del Frio Abisal", "descripcion": "Aire que quema.", "conexiones": {"este": 76}, "bioma": "nieve", "cantidad": 2},
    76: {"nombre": "Llanura del Silencio Blanco", "descripcion": "Extension infinita.", "conexiones": {"sur": 77}, "bioma": "nieve", "cantidad": 1},
    77: {"nombre": "Cementerio Congelado", "descripcion": "Cuerpos en hielo.", "conexiones": {"norte": 78, "este": 78}, "bioma": "nieve", "cantidad": 2},
    78: {"nombre": "Tormenta Errante", "descripcion": "Ventisca viva.", "conexiones": {"norte": 79}, "bioma": "nieve", "cantidad": 2},
    79: {"nombre": "Picos del Desgarro", "descripcion": "Montanas afiladas.", "conexiones": {"norte": 98, "este": 80}, "bioma": "nieve", "cantidad": 2},
    80: {"nombre": "Hondonada del Eco Helado", "descripcion": "Sonido distort.", "conexiones": {"norte": 97}, "bioma": "nieve", "cantidad": 1},
    81: {"nombre": "Rio de Hielo Muerto", "descripcion": "Rio congelado.", "conexiones": {"este": 82}, "bioma": "nieve", "cantidad": 2},
    82: {"nombre": "Fauces de la Tormenta", "descripcion": "Paso estrecho.", "conexiones": {"norte": 83}, "bioma": "nieve", "cantidad": 2},
    83: {"nombre": "Campo de Estatuas Heladas", "descripcion": "Figuras congeladas.", "conexiones": {"norte": 96, "este": 84}, "bioma": "nieve", "cantidad": 2},
    84: {"nombre": "Abismo Nevado", "descripcion": "Vacio oculto.", "conexiones": {"norte": 95, "sur": 85}, "bioma": "nieve", "cantidad": 1},
    85: {"nombre": "Cumbre del Viento Cortante", "descripcion": "Aire cortante.", "conexiones": {"norte": 84}, "bioma": "nieve", "cantidad": 2},
    86: {"nombre": "Valle de las Sombras Blancas", "descripcion": "Siluetas.", "conexiones": {"norte": 87, "este": 89}, "bioma": "nieve", "cantidad": 2},
    87: {"nombre": "Ruinas Congeladas", "descripcion": "Estructuras en hielo.", "conexiones": {"sur": 86}, "bioma": "nieve", "cantidad": 2, "hospital": True},
    88: {"nombre": "Paso del Susurro Gelido", "descripcion": "Voces heladas.", "conexiones": {"sur": 89}, "bioma": "nieve", "cantidad": 1},
    89: {"nombre": "Glaciar Viviente", "descripcion": "Hielo que respira.", "conexiones": {"norte": 88}, "bioma": "nieve", "cantidad": 2},
    90: {"nombre": "Fosa del Olvido Blanco", "descripcion": "Sin rastro.", "conexiones": {"norte": 91}, "bioma": "nieve", "cantidad": 2},
    91: {"nombre": "Torres de Escarcha", "descripcion": "Columnas de hielo.", "conexiones": {"norte": 92}, "bioma": "nieve", "cantidad": 2},
    92: {"nombre": "Velo de Nieve Infinita", "descripcion": "Visibilidad cero.", "conexiones": {"norte": 101, "este": 93}, "bioma": "nieve", "cantidad": 1},
    93: {"nombre": "Lago de Cristal Helado", "descripcion": "Superficie transparente.", "conexiones": {"norte": 102}, "bioma": "nieve", "cantidad": 2},
    94: {"nombre": "Bosque de Agujas Gelidas", "descripcion": "Espinas de hielo.", "conexiones": {"norte": 103}, "bioma": "nieve", "cantidad": 2, "hospital": True},
    95: {"nombre": "Furia Blanca", "descripcion": "Tormenta con voluntad.", "conexiones": {"norte": 104, "este": 94}, "bioma": "nieve", "cantidad": 2},
    96: {"nombre": "Caverna de Escarcha Viva", "descripcion": "Hielo con energia.", "conexiones": {"norte": 105}, "bioma": "nieve", "cantidad": 2},
    97: {"nombre": "Paso del Ultimo Aliento", "descripcion": "Aire que duele.", "conexiones": {"norte": 80}, "bioma": "nieve", "cantidad": 1},
    98: {"nombre": "Colmillos del Invierno", "descripcion": "Formaciones puntiagudas.", "conexiones": {"norte": 107, "este": 99}, "bioma": "nieve", "cantidad": 2},
    99: {"nombre": "Valle del Sueno Helado", "descripcion": "Frio mortal.", "conexiones": {"norte": 108}, "bioma": "nieve", "cantidad": 2},
    100: {"nombre": "Niebla Blanca", "descripcion": "Bruma espesa.", "conexiones": {"norte": 109}, "bioma": "nieve", "cantidad": 1},
    101: {"nombre": "Cumbre Quebrada", "descripcion": "Hielo cae constantemente.", "conexiones": {"norte": 118}, "bioma": "nieve", "cantidad": 2},
    102: {"nombre": "Territorio del Frio Antiguo", "descripcion": "Energia ancestral.", "conexiones": {"norte": 117}, "bioma": "nieve", "cantidad": 2},
    103: {"nombre": "Sendero del Hielo Negro", "descripcion": "Camino oscuro.", "conexiones": {"norte": 104}, "bioma": "nieve", "cantidad": 2},
    104: {"nombre": "Vigilantes de Escarcha", "descripcion": "Figuras inmoviles.", "conexiones": {"norte": 115, "este": 103}, "bioma": "nieve", "cantidad": 2},
    105: {"nombre": "Desierto Blanco", "descripcion": "Dunas de nieve.", "conexiones": {"norte": 106}, "bioma": "nieve", "cantidad": 1, "hospital": True},
    106: {"nombre": "Garganta del Viento Helado", "descripcion": "Corientes cortantes.", "conexiones": {"este": 107}, "bioma": "nieve", "cantidad": 2},
    107: {"nombre": "Ruinas del Invierno Eterno", "descripcion": "Civilizacion congelada.", "conexiones": {"norte": 112, "este": 108}, "bioma": "nieve", "cantidad": 2},
    108: {"nombre": "Campo de Fragmentos Gelidos", "descripcion": "Cristales afilados.", "conexiones": {"norte": 111, "este": 109}, "bioma": "nieve", "cantidad": 2},
    109: {"nombre": "Pozo de Escarcha", "descripcion": "Agujero profundo.", "conexiones": {"norte": 110}, "bioma": "nieve", "cantidad": 1},
    110: {"nombre": "Travesia del Frio Mortal", "descripcion": "Drena vida.", "conexiones": {"norte": 111}, "bioma": "nieve", "cantidad": 2},
    111: {"nombre": "Tormenta Estatica", "descripcion": "Aire cargado.", "conexiones": {"este": 112}, "bioma": "nieve", "cantidad": 2},
    112: {"nombre": "Cascada Congelada", "descripcion": "Agua atrapada.", "conexiones": {"norte": 125}, "bioma": "nieve", "cantidad": 1},
    113: {"nombre": "Circulo de Hielo Antiguo", "descripcion": "Formaciones perfectas.", "conexiones": {"este": 114}, "bioma": "nieve", "cantidad": 2},
    114: {"nombre": "Bosque de Sombras Heladas", "descripcion": "Sombras sin origen.", "conexiones": {"norte": 123}, "bioma": "nieve", "cantidad": 2, "hospital": True},
    115: {"nombre": "Frontera del Frio Absoluto", "descripcion": "Nada sobrevive.", "conexiones": {"norte": 122, "este": 116}, "bioma": "nieve", "cantidad": 2},
    116: {"nombre": "Vertice Nevado", "descripcion": "Viento converge.", "conexiones": {"norte": 121}, "bioma": "nieve", "cantidad": 2},
    117: {"nombre": "Hogar de la Escarcha", "descripcion": "El frio se origina aqui.", "conexiones": {"norte": 120}, "bioma": "nieve", "cantidad": 1},
    118: {"nombre": "Sendero de los Perdidos", "descripcion": "Huellas que aparecen.", "conexiones": {"norte": 119}, "bioma": "nieve", "cantidad": 2},
    119: {"nombre": "Falla Glacial", "descripcion": "Grietas heladas.", "conexiones": {"norte": 128}, "bioma": "nieve", "cantidad": 2},
    120: {"nombre": "Campo de Huesos Congelados", "descripcion": "Restos en hielo.", "conexiones": {"norte": 129, "este": 121}, "bioma": "nieve", "cantidad": 2},
    121: {"nombre": "Tormenta Silenciosa", "descripcion": "Nieve sin sonido.", "conexiones": {"norte": 130, "este": 120}, "bioma": "nieve", "cantidad": 1},
    122: {"nombre": "Nucleo de Hielo Vivo", "descripcion": "Energia helada.", "conexiones": {"norte": 131, "este": 121}, "bioma": "nieve", "cantidad": 2},
    123: {"nombre": "Paso de los Colosos Helados", "descripcion": "Sombras gigantes.", "conexiones": {"norte": 132}, "bioma": "nieve", "cantidad": 2},
    124: {"nombre": "Mar de Escarcha", "descripcion": "Hielo solido.", "conexiones": {"norte": 133}, "bioma": "nieve", "cantidad": 2},
    125: {"nombre": "Colina del Ultimo Suspiro", "descripcion": "El frio roba aliento.", "conexiones": {"norte": 134}, "bioma": "nieve", "cantidad": 1},
    126: {"nombre": "Catedral de Hielo Roto", "descripcion": "Templo destruido.", "conexiones": {"norte": 135}, "bioma": "nieve", "cantidad": 2},
    127: {"nombre": "Velo del Olvido", "descripcion": "La memoria se desvanece.", "conexiones": {"norte": 136}, "bioma": "nieve", "cantidad": 2},
    128: {"nombre": "Fauces Heladas", "descripcion": "Grieta devoradora.", "conexiones": {"norte": 145}, "bioma": "nieve", "cantidad": 2},
    129: {"nombre": "Bosque del Frio Susurrante", "descripcion": "Viento que habla.", "conexiones": {"norte": 144}, "bioma": "nieve", "cantidad": 2},
    130: {"nombre": "Campo de Escarcha Oscura", "descripcion": "Luz enfermiza.", "conexiones": {"norte": 143}, "bioma": "nieve", "cantidad": 2},
    131: {"nombre": "Trampa de Nieve Profunda", "descripcion": "El suelo cede.", "conexiones": {"norte": 142}, "bioma": "nieve", "cantidad": 1, "hospital": True},
    132: {"nombre": "Cumbre del Olvido", "descripcion": "Olvidas por que viniste.", "conexiones": {"norte": 142}, "bioma": "nieve", "cantidad": 2},
    133: {"nombre": "Rugido Blanco", "descripcion": "Viento ensordecedor.", "conexiones": {"norte": 140}, "bioma": "nieve", "cantidad": 2},
    134: {"nombre": "Valle del Frio Eterno", "descripcion": "Nunca deja de nevar.", "conexiones": {"norte": 139}, "bioma": "nieve", "cantidad": 2},
    135: {"nombre": "Sombras Bajo el Hielo", "descripcion": "Figuras oscuras.", "conexiones": {"norte": 134}, "bioma": "nieve", "cantidad": 2},
    136: {"nombre": "Paso de la Escarcha Mortal", "descripcion": "Cada segundo es riesgo.", "conexiones": {"sur": 127}, "bioma": "nieve", "cantidad": 2},
    137: {"nombre": "Caverna del Viento Helado", "descripcion": "Corrientes internas.", "conexiones": {"este": 138}, "bioma": "nieve", "cantidad": 2},
    138: {"nombre": "Campos del Silencio", "descripcion": "El mundo detenido.", "conexiones": {"este": 139}, "bioma": "nieve", "cantidad": 1},
    139: {"nombre": "Colapso Glacial", "descripcion": "Terreno inestable.", "conexiones": {"este": 140, "sur": 134}, "bioma": "nieve", "cantidad": 2},
    140: {"nombre": "Tormenta del Norte", "descripcion": "Ventisca eternal.", "conexiones": {"este": 141}, "bioma": "nieve", "cantidad": 2},
    141: {"nombre": "Grieta del Ultimo Invierno", "descripcion": "Frio ancestral.", "conexiones": {"norte": 146, "este": 142}, "bioma": "nieve", "cantidad": 2},
    142: {"nombre": "Altar de Hielo Antiguo", "descripcion": "Lugar olvidado.", "conexiones": {"este": 143}, "bioma": "nieve", "cantidad": 2, "hospital": True},
    143: {"nombre": "Sendero del Frio Infinito", "descripcion": "Camino sin final.", "conexiones": {"sur": 130}, "bioma": "nieve", "cantidad": 2},
    144: {"nombre": "Cupula de Escarcha", "descripcion": "Formacion cerrada.", "conexiones": {"norte": 145}, "bioma": "nieve", "cantidad": 1},
    145: {"nombre": "Ruinas del Viento Blanco", "descripcion": "Restos arrasados.", "conexiones": {"norte": 146}, "bioma": "nieve", "cantidad": 2},
    146: {"nombre": "Frontera del Vacio Helado", "descripcion": "Solo frio y nada.", "conexiones": {"norte": 148, "este": 145}, "bioma": "nieve", "cantidad": 2},
    147: {"nombre": "Crater de Hielo Vivo", "descripcion": "Impacto antiguo.", "conexiones": {"norte": 148}, "bioma": "nieve", "cantidad": 2, "hospital": True, "tienda": True},
    148: {"nombre": "Trono del Invierno", "descripcion": "Alpha te espera.", "conexiones": {"sur": 146, "este": 147}, "encuentros": [("alpha", 1)]},
    149: {"nombre": "Oasis del Desierto", "descripcion": "Prepara para la batalla final.", "conexiones": {"sur": 24}, "hospital": True, "tienda": True},
    150: {"nombre": "Trono del Invierno", "descripcion": "Asiento de poder.", "conexiones": {"sur": 71}, "hospital": True, "tienda": True},
}

# ==================== GLOBALS ====================
jugadores_conectados = []
combates_activos = {}
grupos = {}
boss_vivo = {s: True for s in BOSS_SALAS}

# Leaderboard cache
_lb_cache = []
_lb_cache_time = 0

# ==================== HELPERS ====================
def xp_para_subir(nivel):
    return XP_POR_NIVEL * nivel

def ataques_por_turno(val):
    if isinstance(val, list):
        return random.randint(val[0], val[1])
    return val

def calcular_danio(base):
    var = random.randint(-3, 3)
    return max(1, base + var)

# ==================== PLAYER CLASS ====================
class Player:
    _id_counter = 0
    
    def __init__(self, ws):
        Player._id_counter += 1
        self.id = self._id_counter
        self.ws = ws
        self.nombre = None
        self.personaje = None
        self.sala_id = 1
        self.combate = None
        self.nivel = 1
        self.xp = 0
        self.monedas = 0
        self.muerto = False
        self.buff_danio = False
        self.inventario = {}
        self.usuario = None
        self.grupo = None
        self.salas_limpias = set()
        self.acertijos_completados = set()
        self.lore_mostrado = False
        self.salas_lore = set()
        self.lore_post = set()
        self.kills = 0
        
    async def send(self, data):
        try:
            await self.ws.send_json(data)
        except:
            pass

# ==================== CHAT SYSTEM ====================
async def broadcast_global(msg, exclude=None):
    for p in jugadores_conectados:
        if p != exclude and p.nombre:
            await p.send({"type": "chat", "scope": "global", "text": msg, "from": exclude.nombre if exclude else "Sistema"})

async def broadcast_sala(sala_id, msg, exclude=None):
    for p in jugadores_conectados:
        if p.sala_id == sala_id and p != exclude and p.nombre:
            await p.send({"type": "chat", "scope": "sala", "text": msg, "from": exclude.nombre if exclude else "Sistema"})

async def broadcast_grupo(grupo, msg, exclude=None):
    for p in grupo["miembros"]:
        if p != exclude and p.nombre:
            await p.send({"type": "chat", "scope": "grupo", "text": msg, "from": exclude.nombre if exclude else "Sistema"})

# ==================== COMBAT SYSTEM ====================
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
            seleccionados = random.choices(pool, k=cantidad)
            for i, tipo in enumerate(seleccionados):
                base = deepcopy(ENEMIGOS[tipo])
                self.enemigos.append({"nombre": f"{tipo.capitalize()}", "tipo": tipo, "vida_actual": base["vidaMax"], **base})
        
        for tipo, cantidad in sala.get("encuentros", []):
            for i in range(cantidad):
                base = deepcopy(ENEMIGOS[tipo])
                self.enemigos.append({"nombre": f"{tipo.capitalize()}", "tipo": tipo, "vida_actual": base["vidaMax"], **base})
    
    def enemigos_vivos(self):
        return [e for e in self.enemigos if e["vida_actual"] > 0]
    
    def jugadores_vivos(self):
        return [p for p in self.jugadores if p.personaje and p.personaje.get("vidaActual", 0) > 0]

async def iniciar_combate(sala_id, jugadores):
    if not jugadores:
        return
    
    combate = Combate(sala_id, jugadores)
    combate.cargar_enemigos()
    
    for p in jugadores:
        p.combate = combate
    
    combates_activos[sala_id] = combate
    
    await broadcast_sala(sala_id, f"⚔️ COMBATE! {len(combate.enemigos)} enemigos aparecen!")
    
    for p in jugadores:
        await p.send({"type": "combat_start", "enemigos": [{"nombre": e["nombre"], "hp": e["vida_actual"], "hpMax": e["vidaMax"]} for e in combate.enemigos]})
    
    asyncio.create_task(loop_combate(combate))

async def loop_combate(combate):
    sala_id = combate.sala_id
    
    while combate.enemigos_vivos() and combate.jugadores_vivos():
        combate.turno += 1
        await broadcast_sala(sala_id, f"\n=== TURNO {combate.turno} ===")
        
        # Mana regen
        for p in combate.jugadores_vivos():
            if p.personaje:
                p.personaje["manaActual"] = min(p.personaje["manaActual"] + p.personaje.get("manaTurno", 0), p.personaje["manaMax"])
        
        # Player actions
        for p in combate.jugadores_vivos():
            if not p.personaje or p.personaje["vidaActual"] <= 0:
                continue
            
            accion = combate.acciones.get(p.id, "1")
            await resolver_accion(p, accion, combate)
            
            if not combate.enemigos_vivos():
                break
        
        if not combate.enemigos_vivos():
            break
        
        # Enemy attacks
        for e in combate.enemigos_vivos():
            objetivos = combate.jugadores_vivos()
            if not objetivos:
                break
            obj = random.choice(objetivos)
            if obj.personaje:
                dmg = calcular_danio(e["danioBase"])
                obj.personaje["vidaActual"] = max(0, obj.personaje["vidaActual"] - dmg)
                await broadcast_sala(sala_id, f"  {e['nombre']} ataca a {obj.nombre} por {dmg} dmg")
        
        # Send stats
        for p in combate.jugadores:
            if p.ws:
                await p.send({"type": "status", "hp": p.personaje.get("vidaActual", 0) if p.personaje else 0, "hpMax": p.personaje.get("vidaMax", 1) if p.personaje else 1, "mana": p.personaje.get("manaActual", 0) if p.personaje else 0, "manaMax": p.personaje.get("manaMax", 1) if p.personaje else 1})
        
        # Check deaths
        for p in combate.jugadores:
            if p.personaje and p.personaje["vidaActual"] <= 0 and not p.muerto:
                p.muerto = True
                await broadcast_sala(sala_id, f"💀 {p.nombre} ha caido!")
                await p.send({"type": "combat_end", "victory": False})
                asyncio.create_task(respawn(p))
        
        await asyncio.sleep(COMBAT_TURN_TIME)
        combate.acciones = {}
    
    # Victory
    if not combate.enemigos_vivos():
        xp = sum(XP_POR_TIER.get(e.get("tier", "Base"), 10) for e in combate.enemigos)
        await broadcast_sala(sala_id, f"\n🎉 VICTORIA! +{xp} XP")
        
        for p in combate.jugadores_vivos():
            if p.personaje and p.personaje["vidaActual"] > 0:
                p.xp += xp
                p.personaje["vidaActual"] = min(p.personaje["vidaActual"] + 20, p.personaje["vidaMax"])
                p.salas_limpias.add(sala_id)
                p.kills += len(combate.enemigos)
                
                while p.xp >= xp_para_subir(p.nivel):
                    p.xp -= xp_para_subir(p.nivel)
                    p.nivel += 1
                    await p.send({"type": "level_up", "nivel": p.nivel})
                
                await p.send({"type": "combat_end", "victory": True, "xp": xp})
                
                if sala_id in BOSS_SALAS:
                    boss_vivo[sala_id] = False
                    delay = BOSS_SALAS[sala_id][1]
                    asyncio.create_task(boss_respawn(sala_id, delay))
    else:
        await broadcast_sala(sala_id, "\n💀 DERROTA. Intentalo de nuevo.")
        for p in combate.jugadores:
            await p.send({"type": "combat_end", "victory": False})
    
    # Cleanup
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
    
    if accion == "1":  # Attack
        num = ataques_por_turno(p.get("ataquesTurno", 1))
        for _ in range(num):
            if obj["vida_actual"] <= 0:
                break
            dmg = calcular_danio(p["danioBase"])
            if player.buff_danio:
                dmg = int(dmg * 1.3)
                player.buff_danio = False
            obj["vida_actual"] = max(0, obj["vida_actual"] - dmg)
            await broadcast_sala(sala_id, f"⚔️ {player.nombre} ataca a {obj['nombre']} por {dmg} dmg")
    
    elif accion == "2":  # Special
        costo = p.get("costoEspecial", 0)
        if p["manaActual"] < costo:
            await player.send({"type": "message", "text": f"No tienes mana (necesitas {costo})"})
            return
        
        p["manaActual"] -= costo
        clase = p["nombreClase"]
        
        if clase == "curandero":
            cur = p.get("curacionEspecial", 20)
            p["vidaActual"] = min(p["vidaActual"] + cur, p["vidaMax"])
            await broadcast_sala(sala_id, f"💚 {player.nombre} se cura {cur} HP")
        else:
            dmg = calcular_danio(p.get("danioEspecial", p["danioBase"]))
            if player.buff_danio:
                dmg = int(dmg * 1.3)
                player.buff_danio = False
            obj["vida_actual"] = max(0, obj["vida_actual"] - dmg)
            await broadcast_sala(sala_id, f"✨ {player.nombre} usa habilidad especial en {obj['nombre']} por {dmg} dmg")
    
    elif accion == "3":  # Pass
        await broadcast_sala(sala_id, f"💤 {player.nombre} pasa el turno")

async def boss_respawn(sala_id, delay):
    await asyncio.sleep(delay)
    boss_vivo[sala_id] = True
    await broadcast_sala(sala_id, f"👹 {BOSS_SALAS[sala_id][0]} ha reaparecido!")

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
    await describe_sala(player)

# ==================== SALA NAVIGATION ====================
async def describe_sala(player):
    sala = SALAS.get(player.sala_id)
    if not sala:
        return
    
    bioma_info = ""
    if "bioma" in sala:
        bioma = BIOMAS.get(sala["bioma"], {})
        bioma_info = f" [{bioma.get('emoji', '')} {sala['bioma']}]"
    
    tiene_enemigos = False
    if player.sala_id not in player.salas_limpias:
        if "bioma" in sala or sala.get("encuentros"):
            tiene_enemigos = True
    
    enemy_msg = " ⚠️ ENEMIGOS! Escribe 'atacar' para luchar" if tiene_enemigos else ""
    
    # Players in room
    others = [p.nombre for p in jugadores_conectados if p.sala_id == player.sala_id and p != player and p.nombre]
    others_msg = f" 👥 Jugadores: {', '.join(others)}" if others else ""
    
    # Group
    grupo_msg = ""
    if player.grupo:
        grupo_msg = f" 👥 Grupo: {', '.join([p.nombre for p in player.grupo['miembros']])}"
    
    msg = {
        "type": "sala",
        "sala_id": player.sala_id,
        "nombre": sala["nombre"],
        "descripcion": sala["descripcion"] + bioma_info,
        "conexiones": sala.get("conexiones", {}),
        "hospital": sala.get("hospital", False),
        "tienda": sala.get("tienda", False),
        "enemigos": tiene_enemigos,
        "others": others_msg,
        "grupo": grupo_msg
    }
    await player.send(msg)

# ==================== MOVE ====================
async def move_player(player, direction):
    if player.combate:
        await player.send({"type": "message", "text": "No puedes moverte en combate!"})
        return
    
    if player.muerto:
        await player.send({"type": "message", "text": "Estas muerto. Espera el respawn."})
        return
    
    sala = SALAS.get(player.sala_id)
    if not sala:
        return
    
    # Check enemies
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
    
    # Auto-join combat
    if player.sala_id in combates_activos:
        c = combates_activos[player.sala_id]
        if player not in c.jugadores and not player.muerto:
            c.jugadores.append(player)
            player.combate = c

# ==================== ATTACK ====================
async def attack_player(player):
    if player.combate:
        await player.send({"type": "message", "text": "Ya estas en combate!"})
        return
    
    if player.muerto:
        await player.send({"type": "message", "text": "Estas muerto."})
        return
    
    sala = SALAS.get(player.sala_id)
    if not sala:
        return
    
    if player.sala_id in player.salas_limpias:
        await player.send({"type": "message", "text": "No hay enemigos aqui."})
        return
    
    if "bioma" not in sala and not sala.get("encuentros"):
        await player.send({"type": "message", "text": "No hay enemigos aqui."})
        return
    
    # Join existing combat or start new
    if player.sala_id in combates_activos:
        c = combates_activos[player.sala_id]
        if player not in c.jugadores:
            c.jugadores.append(player)
    else:
        await iniciar_combate(player.sala_id, [player])

# ==================== COMMANDS ====================
async def process_command(player, cmd):
    cmd = cmd.strip().lower()
    
    if not cmd:
        return
    
    # Combat actions
    if player.combate:
        if cmd in ["1", "2", "3"]:
            player.combate.acciones[player.id] = cmd
            await player.send({"type": "message", "text": f"Accion {cmd} seleccionada."})
            return
        elif cmd == "4" and player.inventario:
            await player.send({"type": "message", "text": "Usa: usar <objeto>"})
            return
    
    # Movement
    if cmd in ["n", "norte"]:
        await move_player(player, "norte")
    elif cmd in ["s", "sur"]:
        await move_player(player, "sur")
    elif cmd in ["e", "este"]:
        await move_player(player, "este")
    elif cmd in ["o", "oeste"]:
        await move_player(player, "oeste")
    
    # Actions
    elif cmd in ["atacar", "attack", "luchar"]:
        await attack_player(player)
    
    elif cmd == "mirar":
        await describe_sala(player)
    
    elif cmd == "stats":
        if player.personaje:
            await player.send({
                "type": "stats",
                "nombre": player.nombre,
                "clase": player.personaje.get("nombreClase", "?"),
                "nivel": player.nivel,
                "xp": player.xp,
                "xpMax": xp_para_subir(player.nivel),
                "hp": player.personaje.get("vidaActual", 0),
                "hpMax": player.personaje.get("vidaMax", 1),
                "mana": player.personaje.get("manaActual", 0),
                "manaMax": player.personaje.get("manaMax", 1),
                "danio": player.personaje.get("danioBase", 0),
                "monedas": player.monedas,
                "inventario": player.inventario
            })
    
    elif cmd.startswith("decir "):
        msg = cmd[6:]
        await broadcast_sala(player.sala_id, f"[Sala] {player.nombre}: {msg}", exclude=player)
    
    elif cmd.startswith("g ") or cmd.startswith("global "):
        msg = cmd[2:] if cmd.startswith("g ") else cmd[7:]
        await broadcast_global(f"[Global] {player.nombre}: {msg}", exclude=player)
    
    elif cmd.startswith("gc ") or cmd.startswith("grup "):
        msg = cmd[3:] if cmd.startswith("gc ") else cmd[5:]
        if player.grupo:
            await broadcast_grupo(player.grupo, f"[Grupo] {player.nombre}: {msg}", exclude=player)
        else:
            await player.send({"type": "message", "text": "No estas en un grupo."})
    
    elif cmd == "hospital":
        sala = SALAS.get(player.sala_id)
        if sala and sala.get("hospital"):
            if player.personaje:
                player.personaje["vidaActual"] = player.personaje["vidaMax"]
                player.personaje["manaActual"] = player.personaje["manaMax"]
            await player.send({"type": "message", "text": "🏥 Te han curado completamente!"})
            await player.send({"type": "status", "hp": player.personaje.get("vidaActual", 0), "hpMax": player.personaje.get("vidaMax", 1), "mana": player.personaje.get("manaActual", 0), "manaMax": player.personaje.get("manaMax", 1)})
        else:
            await player.send({"type": "message", "text": "No hay hospital aqui."})
    
    elif cmd == "tienda":
        sala = SALAS.get(player.sala_id)
        if sala and sala.get("tienda"):
            items = []
            for iid, item in CATALOGO.items():
                qty = player.inventario.get(iid, 0)
                items.append({"id": iid, "nombre": item["nombre"], "emoji": item["emoji"], "precio": item["precio"], "qty": qty})
            await player.send({"type": "tienda", "items": items, "monedas": player.monedas})
        else:
            await player.send({"type": "message", "text": "No hay tienda aqui."})
    
    elif cmd.startswith("comprar "):
        item_id = cmd[8:].strip()
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
    
    elif cmd.startswith("usar "):
        item_id = cmd[5:].strip()
        if item_id in player.inventario and player.inventario[item_id] > 0:
            if item_id == "pocion_vida" and player.personaje:
                player.personaje["vidaActual"] = player.personaje["vidaMax"]
                player.inventario[item_id] -= 1
                await player.send({"type": "message", "text": "🧪 Has usado Pocion de Vida!"})
                await player.send({"type": "status", "hp": player.personaje["vidaActual"], "hpMax": player.personaje["vidaMax"]})
            elif item_id == "pocion_danio":
                player.buff_danio = True
                player.inventario[item_id] -= 1
                await player.send({"type": "message", "text": "⚗️ +30% dano por este combate!"})
            elif item_id == "gema_teleporte":
                player.inventario[item_id] -= 1
                await player.send({"type": "message", "text": "💎 Elige una sala (1-150):"})
                # Simplified: just go to spawn
                player.sala_id = SALA_RESPAWN
                await describe_sala(player)
        else:
            await player.send({"type": "message", "text": "No tienes ese objeto."})
    
    elif cmd == "mochila":
        items = []
        for iid, qty in player.inventario.items():
            if qty > 0:
                item = CATALOGO.get(iid, {"nombre": iid, "emoji": "📦"})
                items.append(f"{item.get('emoji', '📦')} {item['nombre']} x{qty}")
        if items:
            await player.send({"type": "message", "text": "🎒 Tu inventario:\n" + "\n".join(items)})
        else:
            await player.send({"type": "message", "text": "🎒 Inventario vacio."})
    
    # Group commands
    elif cmd == "invitar" or cmd.startswith("invitar "):
        if player.grupo and player.grupo["lider"] != player:
            await player.send({"type": "message", "text": "No eres lider del grupo."})
            return
        
        target_name = cmd.split(" ", 1)[1] if " " in cmd else None
        if not target_name:
            await player.send({"type": "message", "text": "Uso: invitar <nombre>"})
            return
        
        target = next((p for p in jugadores_conectados if p.nombre and p.nombre.lower() == target_name.lower()), None)
        if not target:
            await player.send({"type": "message", "text": "Jugador no encontrado."})
            return
        
        if target.grupo:
            await player.send({"type": "message", "text": f"{target.nombre} ya esta en un grupo."})
            return
        
        if not player.grupo:
            player.grupo = {"lider": player, "miembros": [player]}
            grupos[id(player)] = player.grupo
        
        target.grupo = player.grupo
        player.grupo["miembros"].append(target)
        await player.send({"type": "message", "text": f"Invitacion enviada a {target.nombre}"})
        await target.send({"type": "message", "text": f"{player.nombre} te ha inviteado al grupo. Escribe 'aceptar' para unirse."})
    
    elif cmd == "aceptar":
        if player.grupo:
            await player.send({"type": "message", "text": "Ya estas en un grupo."})
        # Simplified - auto-accept for demo
    
    elif cmd == "salirgrupo":
        if player.grupo:
            player.grupo["miembros"].remove(player)
            if len(player.grupo["miembros"]) == 0:
                grupos.pop(id(player.grupo), None)
            player.grupo = None
            await player.send({"type": "message", "text": "Has dejado el grupo."})
        else:
            await player.send({"type": "message", "text": "No estas en un grupo."})
    
    elif cmd == "grupo":
        if player.grupo:
            miembros = [p.nombre for p in player.grupo["miembros"]]
            lider = player.grupo["lider"].nombre
            await player.send({"type": "message", "text": f"👥 Grupo (Lider: {lider}): {', '.join(miembros)}"})
        else:
            await player.send({"type": "message", "text": "No estas en un grupo. Usa 'invitar <nombre>' para crear uno."})
    
    elif cmd == "ranking":
        await send_ranking(player)
    
    elif cmd == "ayuda":
        ayuda = """
COMANDOS:
  Moverse: n, s, e, o (norte, sur, este, oeste)
  Acciones: atacar, mirar, stats
  Chat: decir <msg>, g <msg>, gc <msg>
  Grupo: invitar, aceptar, salirgrupo, grupo
  Tienda: tienda, comprar <item>, usar <item>, mochila
  General: hospital, ranking, ayuda
COMBATE:
  1 - Atacar (auto)
  2 - Habilidad especial
  3 - Pasar
  4 - Usar objeto
"""
        await player.send({"type": "message", "text": ayuda})
    
    else:
        await player.send({"type": "message", "text": f"Comando '{cmd}' desconocido. Escribe 'ayuda'."})

async def send_ranking(player):
    global _lb_cache, _lb_cache_time
    
    if time.time() - _lb_cache_time > 60:
        # Rebuild cache
        _lb_cache = []
        for p in jugadores_conectados:
            if p.nombre and p.nivel:
                _lb_cache.append({"nombre": p.nombre, "nivel": p.nivel, "clase": p.personaje.get("nombreClase", "?") if p.personaje else "?"})
        _lb_cache.sort(key=lambda x: x["nivel"], reverse=True)
        _lb_cache_time = time.time()
    
    ranking = _lb_cache[:10]
    if ranking:
        text = "🏆 RANKING\n" + "-"*20 + "\n"
        for i, r in enumerate(ranking, 1):
            text += f"{i}. {r['nombre']} - Nivel {r['nivel']} ({r['clase']})\n"
        await player.send({"type": "ranking", "ranking": ranking})
    else:
        await player.send({"type": "message", "text": "No hay jugadores en linea."})

# ==================== WEBSOCKET HANDLER ====================
async def websocket_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    
    player = Player(ws)
    jugadores_conectados.append(player)
    
    try:
        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                    
                    if data.get("type") == "login":
                        player.nombre = data.get("nombre", "Jugador")
                        player.usuario = data.get("usuario", player.nombre)
                        
                        # Create character
                        clase = data.get("clase", "guerrero")
                        if clase not in CLASES:
                            clase = "guerrero"
                        
                        base = deepcopy(CLASES[clase])
                        player.personaje = {
                            "nombre": player.nombre,
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
                        
                        await player.send({
                            "type": "login_ok",
                            "nombre": player.nombre,
                            "clase": clase,
                            "nivel": player.nivel,
                            "hp": player.personaje["vidaActual"],
                            "hpMax": player.personaje["vidaMax"],
                            "mana": player.personaje["manaActual"],
                            "manaMax": player.personaje["manaMax"]
                        })
                        
                        # Send lore
                        if not player.lore_mostrado:
                            await player.send({"type": "lore", "titulo": "EL RETORNO A HIGHDOWN", "text": LORE_INICIAL})
                            player.lore_mostrado = True
                        
                        await describe_sala(player)
                        await send_ranking(player)
                    
                    elif data.get("type") == "command":
                        await process_command(player, data.get("cmd", ""))
                    
                    elif data.get("type") == "action":
                        if player.combate:
                            action = data.get("action", "1")
                            player.combate.acciones[player.id] = action
                            await player.send({"type": "message", "text": f"Accion {action} seleccionada"})
                    
                    elif data.get("type") == "chat":
                        msg_text = data.get("message", "").strip()
                        if msg_text:
                            scope = data.get("scope", "sala")
                            if scope == "sala":
                                await broadcast_sala(player.sala_id, f"[Sala] {player.nombre}: {msg_text}", exclude=player)
                            elif scope == "global":
                                await broadcast_global(f"[Global] {player.nombre}: {msg_text}", exclude=player)
                            elif scope == "grupo" and player.grupo:
                                await broadcast_grupo(player.grupo, f"[Grupo] {player.nombre}: {msg_text}", exclude=player)
                    
                    elif data.get("type") == "ranking":
                        await send_ranking(player)
                
                except json.JSONDecodeError:
                    await process_command(player, msg.data)
            
            elif msg.type in (aiohttp.WSMsgType.ERROR, aiohttp.WSMsgType.CLOSE):
                break
    
    finally:
        if player in jugadores_conectados:
            jugadores_conectados.remove(player)
        if player.grupo and player in player.grupo.get("miembros", []):
            player.grupo["miembros"].remove(player)
    
    return ws

# ==================== HTTP HANDLER ====================
async def index(request):
    return web.Response(text=HTML, content_type="text/html")

# ==================== HTML ====================
HTML = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>The Return to Highdown</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
:root{
  --bg:#0a0a0f;--bg2:#13131a;--bg3:#1a1a24;--bg4:#222230;
  --text:#e8e8f0;--text2:#a0a0b0;--accent:#d4af37;--accent2:#c084fc;
  --danger:#ef4444;--success:#10b981;--info:#3b82f6;
  --hp:#ef4444;--mana:#3b82f6;
}
body{font-family:'Segoe UI',Tahoma,sans-serif;background:radial-gradient(circle at center, #1a1a24 0%, #0a0a0f 100%);color:var(--text);min-height:100vh}
::selection{background:var(--accent);color:#000}

/* Main Layout */
#app{max-width:1400px;margin:0 auto;padding:15px;min-height:100vh}
#main{flex:1;display:flex;flex-direction:column;gap:12px;max-width:900px;margin:0 auto}
#sidebar{display:flex;flex-direction:column;gap:12px;width:320px}

/* Login */
#login-screen{position:fixed;inset:0;background:radial-gradient(circle, #1a1a24 0%, #0a0a0f 100%);display:flex;align-items:center;justify-content:center;z-index:1000}
.login-box{background:linear-gradient(145deg, #1a1a24, #13131a);padding:40px;border-radius:20px;border:2px solid var(--accent);box-shadow:0 0 40px rgba(212, 175, 55, 0.2);width:400px;text-align:center}
.login-box h1{color:var(--accent);margin-bottom:30px;font-size:28px;font-weight:bold;letter-spacing:2px}
.login-box input{width:100%;padding:15px;margin:12px 0;background:var(--bg);border:1px solid var(--accent);color:var(--text);border-radius:10px;font-size:14px;transition:all 0.3s}
.login-box input:focus{outline:none;box-shadow:0 0 15px rgba(212, 175, 55, 0.4)}
.login-box select{width:100%;padding:15px;margin:12px 0;background:var(--bg);border:1px solid var(--accent);color:var(--text);border-radius:10px;font-size:14px}
.login-box button{width:100%;padding:15px;margin:12px 0;background:var(--accent);color:#000;border:none;border-radius:10px;cursor:pointer;font-weight:bold;font-size:16px;transition:all 0.3s}
.login-box button:hover{transform: translateY(-2px);box-shadow:0 5px 20px rgba(212, 175, 55, 0.6)}
.login-box button.secondary{background:var(--bg3);color:var(--text);border:1px solid var(--accent)}
.login-box button.secondary:hover{background:var(--accent);color:#000}

/* Header */
header{background:var(--bg2);padding:15px;border-radius:15px;display:flex;justify-content:space-between;align-items:center;box-shadow:0 4px 15px rgba(0,0,0,0.3)}
header h1{color:var(--accent);font-size:20px;font-weight:bold}
#player-info{display:flex;gap:12px;align-items:center}
.stat{background:var(--bg);padding:8px 15px;border-radius:8px;min-width:100px;text-align:center;transition:all 0.3s}
.stat.hp{color:var(--hp);border:1px solid var(--hp);box-shadow:0 0 10px rgba(239, 68, 68, 0.2)}
.stat.mana{color:var(--mana);border:1px solid var(--mana);box-shadow:0 0 10px rgba(59, 130, 246, 0.2)}
.stat.gold{color:var(--accent);border:1px solid var(--accent);box-shadow:0 0 10px rgba(212, 175, 55, 0.2)}

/* Room */
#room{background:var(--bg2);padding:20px;border-radius:15px;min-height:300px;box-shadow:0 4px 15px rgba(0,0,0,0.3);flex:1}
#room-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:15px}
#room-name{color:var(--accent);font-size:22px;font-weight:bold}
#room-desc{color:var(--text2);font-size:15px;margin:15px 0;line-height:1.8}
#room-features{display:flex;gap:10px;flex-wrap:wrap;margin:15px 0}
.feature{background:var(--bg);padding:8px 16px;border-radius:8px;font-size:13px;transition:all 0.3s}
.feature.hospital{border-left:3px solid var(--success);color:var(--success)}
.feature.enemy{border-left:3px solid var(--danger);color:var(--danger)}
.feature.store{border-left:3px solid var(--accent);color:var(--accent)}
#exits{display:flex;gap:10px;flex-wrap:wrap;margin:20px 0}
.exit-btn{background:var(--bg);border:1px solid var(--accent);padding:12px 20px;border-radius:10px;color:var(--text);cursor:pointer;font-weight:bold;transition:all 0.2s}
.exit-btn:hover{background:var(--accent);color:#000;transform:scale(1.05)}
#room-actions{display:flex;gap:10px;flex-wrap:wrap;margin:20px 0}
.attack-btn{background:var(--danger);padding:15px 30px;border-radius:10px;color:#fff;font-weight:bold;animation:pulse 1.5s infinite}
@keyframes pulse{0%,100%{box-shadow:0 0 0 0 rgba(239,68,68,0.7)}50%{box-shadow:0 0 0 12px rgba(239,68,68,0)}}

/* Log */
#log{background:var(--bg2);padding:20px;border-radius:15px;min-height:250px;box-shadow:0 4px 15px rgba(0,0,0,0.3)}
#log-entries{font-size:14px;line-height:1.7;max-height:200px;overflow-y:auto;min-height:100px}
.log-entry{margin:8px 0;padding:8px 12px;background:var(--bg);border-left:3px solid var(--text2);border-radius:4px}
.log-entry.error{border-color:var(--danger);color:var(--danger)}
.log-entry.success{border-color:var(--success);color:var(--success)}
.log-entry.combat{border-color:var(--danger);color:var(--danger)}
.log-entry.loot{border-color:var(--accent);color:var(--accent)}
.log-input{display:flex;gap:8px;margin-top:15px}
.log-input input{flex:1;padding:10px;background:var(--bg);border:1px solid var(--accent);color:var(--text);border-radius:8px}
.log-input button{padding:10px 20px;border:1px solid var(--accent);background:var(--bg);color:var(--text);border-radius:8px;cursor:pointer;transition:0.2s}
.log-input button:hover{background:var(--accent);color:#000}

/* Combat */
#combat{background:linear-gradient(135deg, #1a1a24, #13131a);padding:20px;border-radius:15px;border-left:5px solid var(--danger);box-shadow:0 0 30px rgba(239, 68, 68, 0.3);margin:10px 0;animation:combatShake 0.3s}
@keyframes combatShake{0%{transform:translateX(0)}25%{transform:translateX(-3px)}50%{transform:translateX(3px)}75%{transform:translateX(-3px)}100%{transform:translateX(0)}}
#combat-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:20px}
#combat-title{color:var(--danger);font-size:24px;font-weight:bold}
#combat-turn{color:var(--text2);font-size:14px}
#enemies{background:var(--bg3);padding:15px;border-radius:10px;margin-bottom:20px}
.enemy-row{display:flex;justify-content:space-between;align-items:center;padding:12px;background:var(--bg);margin:8px 0;border-radius:8px}
.enemy-name{color:var(--danger);font-weight:bold;font-size:16px}
.enemy-hp-bar{width:150px;height:10px;background:var(--bg);border-radius:5px;overflow:hidden;margin-top:5px}
.enemy-hp-fill{height:100%;background:linear-gradient(90deg, #ef4444, #dc2626);transition:width 0.3s}
#combat-actions{display:grid;grid-template-columns:1fr 1fr 1fr 1fr;gap:12px}
.combat-btn{background:var(--bg);border:2px solid var(--accent);padding:20px 10px;border-radius:12px;color:var(--text);cursor:pointer;font-weight:bold;font-size:14px;transition:all 0.2s}
.combat-btn:hover{background:var(--accent);color:#000;border-color:var(--accent)}
.combat-btn:active{transform:scale(0.98)}

/* Sidebar */
#sidebar{background:var(--bg2);padding:15px;border-radius:15px;box-shadow:0 4px 15px rgba(0,0,0,0.3)}
#stats-panel h3,#chat h3,#ranking h3{color:var(--accent);font-size:16px;margin-bottom:12px;text-transform:uppercase;letter-spacing:1px}
.stats-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px;border-top:1px solid var(--bg4)}
.stat-row{display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid var(--bg4)}
.stat-label{color:var(--text2);font-size:13px}
.stat-value{font-weight:bold;color:var(--text);font-size:13px}
#char-class{color:var(--accent)}

/* Chat */
#chat{background:var(--bg3);padding:15px;border-radius:10px}
#chat-tabs{display:flex;gap:8px;margin-bottom:10px}
.chat-tab{background:var(--bg);border:1px solid var(--accent);padding:8px 12px;border-radius:6px;color:var(--text2);cursor:pointer;font-size:12px;flex:1}
.chat-tab.active{background:var(--accent);color:#000}
#chat-messages{background:var(--bg);padding:10px;border-radius:8px;flex:1;overflow-y:auto;max-height:200px;min-height:100px}
.chat-msg{margin:8px 0;padding:8px 12px;background:var(--bg3);border-radius:6px;font-size:13px}
.chat-msg .from{color:var(--accent);font-weight:bold;display:block;margin-bottom:3px}
.chat-msg.global .from{color:var(--info)}
.chat-msg.grupo .from{color:var(--accent2)}
.chat-input{display:flex;gap:8px;margin-top:8px}
.chat-input input{flex:1;background:var(--bg);border:1px solid var(--accent);padding:8px;border-radius:6px;color:var(--text)}
.chat-input button{background:var(--accent);border:none;padding:8px 15px;border-radius:6px;color:#000;cursor:pointer;font-weight:bold}

/* Ranking */
#ranking{background:var(--bg3);padding:15px;border-radius:10px}
.ranking-row{display:flex;justify-content:space-between;padding:10px 8px;background:var(--bg);margin:5px 0;border-radius:6px;transition:all 0.2s}
.ranking-row:hover{background:var(--bg4)}
.ranking-row:nth-child(1){background:var(--accent);color:#000;font-weight:bold}
.ranking-row:nth-child(2){background:var(--bg4)}
.ranking-row:nth-child(3){background:var(--bg4)}
.ranking-pos{color:var(--text2);font-weight:bold}
.ranking-name{font-weight:bold}
.ranking-nivel{color:var(--accent)}

/* Modal */
.modal{position:fixed;inset:0;background:rgba(0,0,0,0.8);display:none;align-items:center;justify-content:center;z-index:500;padding:20px}
.modal.active{display:flex}
.modal-content{background:var(--bg2);padding:30px;border-radius:20px;max-width:600px;max-height:80vh;overflow-y:auto;border:2px solid var(--accent);box-shadow:0 0 50px rgba(0,0,0,0.8)}
.modal-title{color:var(--accent);font-size:24px;margin-bottom:20px;text-align:center}
.modal-text{line-height:1.8;white-space:pre-wrap;color:var(--text2);font-size:15px}
.modal-close{width:100%;padding:12px;background:var(--accent);border:none;border-radius:10px;color:#000;cursor:pointer;font-weight:bold;font-size:16px;transition:0.3s}

/* Shop */
.shop-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:12px;margin-top:15px}
.shop-item{background:var(--bg);padding:15px;border-radius:10px;text-align:center;transition:all 0.2s;cursor:pointer}
.shop-item:hover{transform:translateY(-3px);box-shadow:0 5px 20px rgba(0,0,0,0.4)}
.shop-item.emoji{font-size:40px;margin-bottom:10px}
.shop-item-name{font-size:14px;color:var(--text);font-weight:bold}
.shop-item-price{color:var(--accent);font-size:13px;margin-top:10px;display:block}

/* Buttons */
.btn{background:var(--accent);border:none;padding:10px 20px;border-radius:8px;color:#000;cursor:pointer;font-weight:bold;transition:all 0.2s}
.btn:hover{transform:scale(1.05);box-shadow:0 5px 15px rgba(212, 175, 55, 0.4)}
.btn.secondary{background:var(--bg);color:var(--text);border:1px solid var(--accent)}
.btn.secondary:hover{background:var(--bg4)}

/* Popups */
.popup{position:fixed;inset:0;background:rgba(0,0,0,0.95);display:none;align-items:center;justify-content:center;z-index:500;padding:20px}
.popup.active{display:flex}
.popup-content{background:linear-gradient(145deg, #1a1a24, #13131a);padding:30px;border-radius:20px;max-width:600px;max-height:80vh;overflow-y:auto;border:2px solid var(--accent);box-shadow:0 0 40px rgba(212, 175, 55, 0.3)}
.popup-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:20px}
.popup-title{color:var(--accent);font-size:24px;text-align:center}
.popup-close{background:var(--bg4);color:var(--text);border:1px solid var(--accent);padding:8px 16px;border-radius:8px;cursor:pointer}
.popup-close:hover{background:var(--danger);color:#fff}

/* Responsive */
@media(max-width:768px){
  #app{padding:5px}
  #main{max-width:none}
  .login-box{width:95%}
  #sidebar{width:100%;max-width:320px;margin:0 auto}
  #room-actions{justify-content:space-between}
}
</style>
</head>
<body>
<div id="app">
  <!-- Login Modal -->
  <div id="login-screen">
    <div class="login-box">
      <h1>⚔️ THE RETURN TO HIGHDOWN</h1>
      <input type="text" id="username" placeholder="Usuario">
      <input type="password" id="password" placeholder="Contrasena">
      <input type="text" id="char-name" placeholder="Nombre de personaje">
      <select id="char-class">
        <option value="guerrero">⚔️ Guerrero - Alta vida, dano medio</option>
        <option value="mago">🔮 Mago - Baja vida, magia poderosa</option>
        <option value="arquero">🏹 Arquero - Dano bajo, ataques rapidos</option>
        <option value="curandero">💚 Curandero - Pode curarse</option>
        <option value="nigromante">💀 Nigromante - Mucho mana, ataques multiples</option>
        <option value="hechicero">✨ Hechicero - Magia avanzada</option>
        <option value="caballero">🛡️ Caballero - Equilibrado</option>
        <option value="cazador">🎯 Cazador - Alto dano fisico</option>
        <option value="asesino">🗡️ Asesino - Criticos letales</option>
        <option value="barbaro">🔥 Barbaro - Dano brutal</option>
      </select>
      <button onclick="login()">🎮 JUGAR</button>
      <button class="secondary" onclick="register()">➕ Crear cuenta</button>
      <div style="margin-top:20px;font-size:13px;color:var(--text2);padding:10px;background:var(--bg);border-radius:8px">
        🌐 <strong>Multijugador en vivo</strong> - <span id="online-count">0</span> jugadores online
      </div>
      <div id="login-error" style="color:var(--danger);font-size:13px;margin-top:10px;display:none"></div>
    </div>
  </div>
  
  <div id="main">
    <!-- Header -->
    <header>
      <h1>⚔️ THE RETURN TO HIGHDOWN</h1>
      <div id="player-info">
        <span class="stat" id="stat-level">⭐ Nv 1</span>
        <span class="stat hp" id="stat-hp">❤️ 0/0</span>
        <span class="stat mana" id="stat-mana">💧 0/0</span>
        <span class="stat gold" id="stat-medas">💰 0</span>
      </div>
    </header>
    
    <!-- Room Info -->
    <div id="room">
      <div id="room-header">
        <span id="room-name">Cargando...</span>
        <button class="btn" onclick="refreshRoom()">🔄 Ver</button>
      </div>
      <div id="room-desc"></div>
      <div id="room-features"></div>
      <div id="room-actions"></div>
      <div id="exits"></div>
      <div id="players-in-room" style="margin:15px 0;color:var(--text2);font-size:14px"></div>
      <div id="group-info" style="margin:15px 0;color:var(--accent2);font-size:14px"></div>
    </div>
    
    <!-- Combat Section -->
    <div id="combat" style="display:none">
      <div id="combat-header">
        <span id="combat-title">⚔️ COMBATE - <span id="enemy-count">0</span> enemigos</span>
        <span id="combat-turn">Turno 1</span>
      </div>
      <div id="enemies"></div>
      <div id="combat-actions">
        <button class="combat-btn" onclick="sendAction('1')">⚔️ ATACAR</button>
        <button class="combat-btn" onclick="sendAction('2')">✨ ESPECIAL</button>
        <button class="combat-btn" onclick="sendAction('3')">💤 PASAR</button>
        <button class="combat-btn" onclick="openInventory()">🎒 OBJETO</button>
      </div>
    </div>
    
    <!-- Log -->
    <div id="log">
      <div id="log-entries"></div>
      <div class="log-input">
        <input type="text" id="cmd-input" placeholder="Escribe un comando o mensaje..." onkeypress="if(event.key==='Enter')sendCmd()">
        <button onclick="sendCmd()">➤</button>
        <button class="secondary" onclick="sendCmd('stats')">Stats</button>
        <button class="secondary" onclick="sendCmd('ranking')">🏆</button>
        <button class="secondary" onclick="sendCmd('ayuda')">?</button>
      </div>
    </div>
  </div>
  
  <div id="sidebar">
    <!-- Stats -->
    <div id="stats-panel">
      <h3>📊 ESTADISTICAS</h3>
      <div class="stats-grid">
        <div class="stat-row"><span class="stat-label">Nombre:</span><span class="stat-value" id="sp-nombre">-</span></div>
        <div class="stat-row"><span class="stat-label">Clase:</span><span class="stat-value" id="sp-clase">-</span></div>
        <div class="stat-row"><span class="stat-label">Nivel:</span><span class="stat-value" id="sp-nivel">1</span></div>
        <div class="stat-row"><span class="stat-label">XP:</span><span class="stat-value" id="sp-xp">0/150</span></div>
        <div class="stat-row"><span class="stat-label">Habilidades:</span><span class="stat-value" id="sp-habilidades">-</span></div>
      </div>
    </div>
    
    <!-- Chat -->
    <div id="chat">
      <h3>💬 CHAT</h3>
      <div id="chat-tabs">
        <button class="chat-tab active" onclick="setChat('sala')">🏠</button>
        <button class="chat-tab" onclick="setChat('global')">🌍</button>
        <button class="chat-tab" onclick="setChat('grupo')">👥</button>
      </div>
      <div id="chat-messages"></div>
      <div class="chat-input">
        <input type="text" id="chat-msg" placeholder="Escribe un mensaje..." onkeypress="if(event.key==='Enter')sendChat()">
        <button onclick="sendChat()">➤</button>
      </div>
    </div>
    
    <!-- Ranking -->
    <div id="ranking">
      <h3>🏆 RANKING</h3>
      <div id="ranking-list"></div>
    </div>
  </div>
</div>

<!-- Lore Modal -->
<div id="lore-modal" class="modal">
  <div class="modal-content">
    <h2 class="modal-title" id="lore-title"></h2>
    <div class="modal-text" id="lore-text"></div>
    <button class="modal-close" onclick="closeModal()">CONTINUAR</button>
  </div>
</div>

<!-- Shop Modal -->
<div id="shop-modal" class="modal">
  <div class="modal-content">
    <h2 class="modal-title">🏪 TIENDA</h2>
    <p style="text-align:center;color:var(--accent);margin-bottom:15px" id="shop-money">💰 0 monedas</p>
    <div class="shop-grid" id="shop-grid"></div>
    <button class="modal-close" onclick="closeModal()">cerrar</button>
  </div>
</div>

<script>
let ws = null;
let currentChat = 'sala';
let inCombat = false;
let currentAction = '1';

function log(msg, type='info'){
  const el = document.getElementById('log-entries');
  const div = document.createElement('div');
  div.className = 'log-entry ' + type;
  div.textContent = msg;
  el.appendChild(div);
  el.scrollTop = el.scrollHeight;
}

function login(){
  const usuario = document.getElementById('username').value.trim();
  const password = document.getElementById('password').value;
  const nombre = document.getElementById('char-name').value.trim() || usuario;
  const clase = document.getElementById('char-class').value;
  
  if(!usuario){showLoginError('Introduce tu usuario');return;}
  if(!password){showLoginError('Introduce tu contrasena');return;}
  
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  ws = new WebSocket(protocol + '//' + window.location.host + '/ws');
  
  ws.onopen = () => {
    ws.send(JSON.stringify({type:'login', usuario, password, nombre, clase}));
  };
  
  ws.onmessage = (e) => {
    const data = JSON.parse(e.data);
    handleMessage(data);
  };
  
  ws.onclose = () => {
    log('Conexion perdida','error');
  };
}

function register(){
  const usuario = document.getElementById('username').value.trim();
  const password = document.getElementById('password').value;
  const nombre = document.getElementById('char-name').value.trim() || usuario;
  const clase = document.getElementById('char-class').value;
  
  if(!usuario){showLoginError('Introduce tu usuario');return;}
  if(!password || password.length < 4){showLoginError('Contrasena minimo 4 caracteres');return;}
  
  ws = new WebSocket(window.location.protocol === 'https:' ? 'wss:' + '//' + window.location.host + '/ws' : 'ws:' + '//' + window.location.host + '/ws');
  
  ws.onopen = () => {
    ws.send(JSON.stringify({type:'register', usuario, password, nombre, clase}));
  };
  
  ws.onmessage = (e) => {
    const data = JSON.parse(e.data);
    handleMessage(data);
  };
}

function showLoginError(msg){
  const el = document.getElementById('login-error');
  el.textContent = msg;
  el.style.display = 'block';
  setTimeout(()=>el.style.display = 'none', 3000);
}

function handleMessage(data){
  if(data.type === 'login_ok' || data.type === 'register_ok'){
    document.getElementById('login-screen').classList.add('hidden');
    log('Bienvenido a The Return to Highdown!','success');
  }
  else if(data.type === 'login_error'){
    showLoginError(data.text || 'Error de login');
  }
  else if(data.type === 'online_count'){
    document.getElementById('online-count').textContent = data.count;
  }
  else if(data.type === 'message'){
    log(data.text, data.text.includes('!') ? 'success' : 'info');
  }
  else if(data.type === 'sala'){
    updateRoom(data);
  }
  else if(data.type === 'status'){
    updateStats(data);
  }
  else if(data.type === 'combat_start'){
    showCombat(data.enemigos);
  }
  else if(data.type === 'combat_end'){
    hideCombat();
  }
  else if(data.type === 'combat_update'){
    updateEnemies(data.enemigos);
    document.getElementById('combat-turn').textContent = 'Turno ' + data.turno;
  }
  else if(data.type === 'chat'){
    addChatMessage(data.scope, data.from, data.text);
  }
  else if(data.type === 'ranking'){
    updateRanking(data.ranking);
  }
  else if(data.type === 'lore'){
    showModal('lore-modal', data.titulo, data.text);
  }
  else if(data.type === 'shop'){
    showShop(data.items, data.monedas);
  }
  else if(data.type === 'level_up'){
    log('🎉 SUBISTE AL NIVEL ' + data.nivel + '!', 'success');
  }
  else if(data.type === 'inventory'){
    showInventoryModal(data.items);
  }
  else if(data.type === 'respawn'){
    refreshRoom();
  }
}

function updateRoom(data){
  document.getElementById('room-name').textContent = data.nombre;
  document.getElementById('room-desc').textContent = data.descripcion;
  
  let exits = '';
  for(let dir in data.conexiones){
    exits += `<button class="exit-btn" onclick="move('${dir}')">${dir.toUpperCase()}</button>`;
  }
  document.getElementById('exits').innerHTML = exits;
  
  let features = '';
  if(data.hospital) features += '<span class="feature hospital">🏥 Hospital</span>';
  if(data.tienda) features += '<span class="feature store">🏪 Tienda</span>';
  if(data.enemigos) features += '<span class="feature enemy">⚠️ ENEMIGOS</span>';
  document.getElementById('room-features').innerHTML = features;
  
  let actions = '';
  if(data.enemigos) actions += `<button class="btn attack-btn" onclick="attack()">⚔️ ATACAR</button>`;
  if(data.hospital) actions += `<button class="btn secondary" onclick="hospital()">🏥 Hospital</button>`;
  if(data.tienda) actions += `<button class="btn secondary" onclick="openTienda()">🏪 Tienda</button>`;
  document.getElementById('room-actions').innerHTML = actions;
  
  if(data.others) document.getElementById('players-in-room').innerHTML = '👥 Jugadores: ' + data.others;
  else document.getElementById('players-in-room').innerHTML = '';
  
  if(data.grupo) document.getElementById('group-info').innerHTML = '👥 ' + data.grupo;
  else document.getElementById('group-info').innerHTML = '';
}

function updateStats(data){
  document.getElementById('stat-level').textContent = '⭐ Nv ' + (data.nivel || 1);
  document.getElementById('stat-hp').textContent = '❤️ ' + (data.hp || 0) + '/' + (data.hpMax || 1);
  document.getElementById('stat-medas').textContent = '💰 ' + (data.monedas || 0);
  document.getElementById('stat-mana').textContent = '💧 ' + (data.mana || 0) + '/' + (data.manaMax || 1);
  
  document.getElementById('sp-nombre').textContent = data.nombre || '-';
  document.getElementById('sp-clase').textContent = data.clase || '-';
  document.getElementById('sp-nivel').textContent = data.nivel || 1;
  document.getElementById('sp-xp').textContent = (data.xp || 0) + '/' + (data.xpMax || 150);
  document.getElementById('sp-habilidades').textContent = data.habilidades || '-';
}

function showCombat(enemies){
  inCombat = true;
  document.getElementById('combat').style.display = 'block';
  document.getElementById('enemy-count').textContent = enemies.length;
  updateEnemies(enemies);
  log('⚔️ COMBATE INICIADO!','combat');
}

function hideCombat(){
  inCombat = false;
  document.getElementById('combat').style.display = 'none';
  log('Combate finalizado','info');
}

function updateEnemies(enemies){
  const el = document.getElementById('enemies');
  let html = '';
  enemies.forEach(e => {
    const pct = (e.hp / e.hpMax) * 100;
    html += `<div class="enemy-row">
      <div>
        <span class="enemy-name">${e.nombre}</span>
        <div class="enemy-hp-bar">
          <div class="enemy-hp-fill" style="width:${pct}%"></div>
        </div>
      </div>
      <span class="enemy-hp">${e.hp}/${e.hpMax}</span>
    </div>`;
  });
  el.innerHTML = html;
}

function sendAction(action){
  currentAction = action;
  document.querySelectorAll('.combat-btn').forEach((btn,i) => {
    btn.classList.toggle('selected', (i+1).toString() === action);
  });
  ws.send(JSON.stringify({type:'action', action}));
}

function move(dir){
  ws.send(JSON.stringify({type:'command', cmd:dir}));
}

function attack(){
  ws.send(JSON.stringify({type:'command', cmd:'atacar'}));
}

function hospital(){
  ws.send(JSON.stringify({type:'command', cmd:'hospital'}));
}

function openTienda(){
  ws.send(JSON.stringify({type:'command', cmd:'tienda'}));
}

function refreshRoom(){
  ws.send(JSON.stringify({type:'command', cmd:'mirar'}));
}

function setChat(scope){
  currentChat = scope;
  document.querySelectorAll('.chat-tab').forEach(t => t.classList.remove('active'));
  event.target.classList.add('active');
}

function sendChat(){
  const input = document.getElementById('chat-msg');
  const msg = input.value.trim();
  if(!msg) return;
  ws.send(JSON.stringify({type:'chat', scope:currentChat, message:msg}));
  input.value = '';
}

function addChatMessage(scope, from, text){
  const el = document.getElementById('chat-messages');
  const div = document.createElement('div');
  div.className = 'chat-msg ' + scope;
  div.innerHTML = `<span class="from">[${scope.toUpperCase()} ${from}]</span> ${text}`;
  el.appendChild(div);
  el.scrollTop = el.scrollHeight;
}

function updateRanking(ranking){
  const el = document.getElementById('ranking-list');
  let html = '';
  ranking.forEach((r,i) => {
    html += `<div class="ranking-row">
      <span><span class="ranking-pos">${i+1}.</span> <span class="ranking-name">${r.nombre}</span></span>
      <span class="ranking-nivel">Nv.${r.nivel} (${r.clase})</span>
    </div>`;
  });
  el.innerHTML = html;
}

function showModal(id, title, text){
  document.getElementById(id + '-title').textContent = title;
  document.getElementById(id + '-text').textContent = text;
  document.getElementById(id).classList.add('active');
  document.body.style.overflow = 'hidden';
}

function closeModal(){
  document.querySelectorAll('.modal').forEach(m => m.classList.remove('active'));
  document.body.style.overflow = 'auto';
}

function showShop(items, money){
  document.getElementById('shop-money').textContent = '💰 ' + money + ' monedas';
  const grid = document.getElementById('shop-grid');
  grid.innerHTML = '';
  items.forEach(item => {
    const div = document.createElement('div');
    div.className = 'shop-item';
    div.innerHTML = `
      <div class="shop-item-emoji">${item.emoji}</div>
      <div class="shop-item-name">${item.nombre}</div>
      <span class="shop-item-price">${item.precio}💰</span>
      <div style="font-size:11px;color:var(--text2);margin-top:5px">x${item.qty}</div>
    `;
    div.onclick = () => buyItem(item.id);
    grid.appendChild(div);
  });
  showModal('shop-modal', 'Tienda', '');
}

function buyItem(id){
  ws.send(JSON.stringify({type:'command', cmd:'comprar ' + id}));
}

function showInventoryModal(items){
  // Simplified
  log('🎒 Inventario:', 'info');
  items.forEach(i => log(`- ${i.name} x${i.qty}`, 'info'));
}

function sendCmd(cmd){
  if(!cmd){
    const input = document.getElementById('cmd-input');
    cmd = input.value.trim();
    if(!cmd) return;
    input.value = '';
  }
  ws.send(JSON.stringify({type:'command', cmd}));
}

// Keyboard shortcuts
document.addEventListener('keydown', (e) => {
  if(!inCombat) return;
  if(e.key === '1') sendAction('1');
  if(e.key === '2') sendAction('2');
  if(e.key === '3') sendAction('3');
  if(e.key === '4') sendAction('4');
  if(e.key === 'n') move('norte');
  if(e.key === 's') move('sur');
  if(e.key === 'e') move('este');
  if(e.key === 'o') move('oeste');
});
</script>
</body>
</html>
"""

# ==================== APP ====================
app = web.Application()
app.router.add_get('/', index)
app.router.add_get('/ws', websocket_handler)

if __name__ == '__main__':
    print(f"🚀 Server starting on port {PORT}")
    web.run_app(app, host='0.0.0.0', port=PORT)
