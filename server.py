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
import json
import random
import threading
from copy import deepcopy
from enum import Enum
from http.server import HTTPServer, SimpleHTTPRequestHandler

import websockets

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
# SALAS
# ============================================================
SALAS = {
    1: {"nombre": "Entrada del Dungeon",
        "descripcion": "Sala fria y humeda. Antorchas parpadean en las paredes.",
        "conexiones": {"norte": 2, "este": 3},
        "encuentros": [("bandido", 1)]},
    2: {"nombre": "Pasillo del Norte",
        "descripcion": "Pasillo largo. Se escuchan grunidos al fondo.",
        "conexiones": {"sur": 1, "norte": 4},
        "encuentros": [("orco", 1)]},
    3: {"nombre": "Sala del Tesoro",
        "descripcion": "Cofres abiertos y saqueados. Alguien llego antes.",
        "conexiones": {"oeste": 1},
        "encuentros": []},
    4: {"nombre": "Guarida del Dragon",
        "descripcion": "El suelo esta quemado. Un dragon duerme en el centro.",
        "conexiones": {"sur": 2},
        "encuentros": [("dragon", 1)]},
}

# ============================================================
# ESTADO GLOBAL
# ============================================================
jugadores_conectados = []
combates_activos     = {}
chat_ws_clients      = set()


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
        for tipo, cantidad in sala.get("encuentros", []):
            for i in range(cantidad):
                base = deepcopy(ENEMIGOS[tipo])
                self.enemigos.append({
                    "nombre": f"{tipo.capitalize()} {i+1}",
                    "tipo": tipo, "vida_actual": base["vidaMax"], **base,
                })

    def enemigos_vivos(self):
        return [e for e in self.enemigos if e["vida_actual"] > 0]

    def jugadores_vivos(self):
        return [p for p in self.jugadores if p.personaje["vidaActual"] > 0]


class Player:
    _id_counter = 0

    def __init__(self, reader, writer):
        Player._id_counter += 1
        self.id          = Player._id_counter
        self.reader      = reader
        self.writer      = writer
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
        self.input_queue = asyncio.Queue()
        self.addr        = writer.get_extra_info("peername")

    async def send(self, texto: str):
        try:
            self.writer.write((texto + "\n").encode())
            await self.writer.drain()
        except Exception:
            pass

    async def recv(self):
        """
        Devuelve:
          None  → desconexión real (reader cerró)
          ""    → Enter vacío (el jugador pulsó Enter sin escribir nada)
          str   → mensaje con contenido
        """
        try:
            msg = await asyncio.wait_for(self.input_queue.get(), timeout=300)
            return msg  # None = desconexión, "" o str = input
        except asyncio.TimeoutError:
            return None  # timeout → tratar como desconexión

    async def send_prompt(self, prompt: str) -> str:
        """Envía prompt y espera respuesta. Ignora Enters vacíos."""
        await self.send(prompt)
        while True:
            r = await self.recv()
            if r is None:
                return ""   # desconexión durante prompt
            if r.strip():   # tiene contenido
                return r.strip()
            # Enter vacío → volver a pedir silenciosamente


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
    payload = json.dumps({"scope": scope, "nombre": nombre, "mensaje": mensaje})
    muertos = set()
    for ws in chat_ws_clients:
        try:
            await ws.send(payload)
        except Exception:
            muertos.add(ws)
    chat_ws_clients.difference_update(muertos)


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
# SETUP PERSONAJE
# ============================================================

async def setup_personaje(player: Player):
    await player.send("=" * 52)
    await player.send("       BIENVENIDO AL MUD MULTIPLAYER")
    await player.send("=" * 52)
    player.nombre = (await player.send_prompt("Como te llamas? ")).strip() or f"Aventurero_{player.id}"

    lineas = ["\nCLASES DISPONIBLES:"]
    for i, (clase, s) in enumerate(CLASES.items(), 1):
        atqs = s["ataquesTurno"]
        atq_str = f"{atqs[0]}-{atqs[1]}" if isinstance(atqs, list) else str(atqs)
        lineas.append(
            f"  {i:2}. {clase:<12}  HP:{s['vidaMax']:>3}  "
            f"Dano:{s['danioBase']:>3}  Mana:{s['manaMax']:>3}  Atqs:{atq_str}"
        )
    await player.send("\n".join(lineas))

    while True:
        el = (await player.send_prompt("\nElige clase (nombre o numero): ")).strip().lower()
        if el.isdigit() and 0 <= int(el) - 1 < len(CLASES):
            clase_elegida = list(CLASES.keys())[int(el) - 1]
            break
        elif el in CLASES:
            clase_elegida = el
            break
        await player.send("  Clase no encontrada. Intenta de nuevo.")

    base = deepcopy(CLASES[clase_elegida])
    player.personaje = {
        "nombre": player.nombre, "nombreClase": clase_elegida,
        "vidaActual": base["vidaMax"], "manaActual": base["manaMax"], **base,
    }
    await player.send(
        f"\n  Listo! {player.nombre} el {clase_elegida.capitalize()}\n"
        f"  HP:{player.personaje['vidaActual']}  "
        f"Mana:{player.personaje['manaActual']}  "
        f"Dano:{player.personaje['danioBase']}"
    )


# ============================================================
# SALAS
# ============================================================

async def describir_sala(player: Player):
    sala = SALAS.get(player.sala_id)
    if not sala:
        return
    otros   = [p.nombre for p in jugadores_en_sala(player.sala_id) if p != player]
    salidas = ", ".join(sala["conexiones"].keys())
    lineas  = [
        f"\n{'=' * 52}",
        f"  [{player.sala_id}] {sala['nombre']}",
        f"{'=' * 52}",
        f"  {sala['descripcion']}",
    ]
    if otros:
        lineas.append(f"  Aqui tambien: {', '.join(otros)}")
    lineas.append(f"  Salidas: {salidas}")
    if sala["encuentros"]:
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
    await describir_sala(player)


# ============================================================
# COMBATE
# ============================================================

async def iniciar_combate(sala_id: int):
    # Verificaciones silenciosas — los errores se manejan en procesar_comando
    if sala_id in combates_activos:
        return
    sala = SALAS.get(sala_id)
    if not sala or not sala.get("encuentros"):
        return
    jug = [p for p in jugadores_en_sala(sala_id) if not p.muerto]
    if not jug:
        return

    combate = Combate(sala_id, jug)
    combate.cargar_enemigos(sala_id)
    combates_activos[sala_id] = combate
    for p in jug:
        p.combate = combate

    await broadcast_sala(sala_id, "\n" + "=" * 52)
    await broadcast_sala(sala_id, "  COMBATE!")
    await broadcast_sala(sala_id, "=" * 52)
    for e in combate.enemigos:
        await broadcast_sala(sala_id, f"  {e['nombre']}  HP:{e['vida_actual']}/{e['vidaMax']}")

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
            st = "MUERTO" if p.muerto else f"Sala {p.sala_id}"
            lineas.append(f"  - {p.nombre} [Nv.{p.nivel} {p.personaje['nombreClase']}] ({st})")
        await player.send("\n".join(lineas))

    elif ac == "atacar":
        if player.muerto:
            await player.send("  Estas muerto. Espera el respawn.")
            return
        sala = SALAS.get(player.sala_id)
        if not sala or not sala.get("encuentros"):
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
        else:
            await cmd_tienda(player)

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

    elif ac == "ayuda":
        await player.send(
            "\n  MOVER:    n s e o  (norte sur este oeste)\n"
            "  ACCION:   mirar | atacar\n"
            "  TIENDA:   tienda | mochila | usar <objeto>\n"
            "  INFO:     stats | nivel | jugadores\n"
            "  CHAT:     decir <msg>  (sala)  |  g <msg>  (global)\n"
            "  CHAT WEB: http://localhost:8080/chat.html"
        )

    else:
        await player.send(f"  Desconocido: '{cmd}'. Escribe 'ayuda'.")


# ============================================================
# HANDLE PLAYER (TCP)  — FIX PRINCIPAL: Enter vacío no desconecta
# ============================================================

async def handle_player(reader, writer):
    player = Player(reader, writer)
    print(f"[TCP] Conexion: {player.addr}")

    if len(jugadores_conectados) >= MAX_JUGADORES:
        await player.send("Servidor lleno (max 5 jugadores). Intentalo mas tarde.")
        writer.close()
        return

    jugadores_conectados.append(player)

    # Reader task: UNICO lector del TCP — alimenta input_queue
    # Pone el string (incluyendo "") en la cola, y None solo al cerrar
    async def reader_task():
        try:
            while True:
                data = await reader.readline()
                if not data:          # conexión TCP cerrada
                    break
                await player.input_queue.put(data.decode().strip())
        except Exception:
            pass
        finally:
            await player.input_queue.put(None)  # señal de desconexión real

    rt = asyncio.create_task(reader_task())

    try:
        await setup_personaje(player)
        await broadcast_todos(f"\n  {player.nombre} se unio al dungeon!")
        await describir_sala(player)

        while True:
            # Durante combate, pedir_accion consume el queue.
            # handle_player NO llama recv() aqui → fix race condition.
            if player.combate and player.combate.estado != EstadoCombate.FINALIZADO:
                await asyncio.sleep(0.05)
                continue

            raw = await player.recv()

            # None = desconexión real → salir del loop
            if raw is None:
                break

            # FIX: Enter vacío → ignorar completamente, no desconectar
            if not raw.strip():
                continue

            await procesar_comando(player, raw.strip())

    except Exception as e:
        print(f"[TCP] Error {player.addr}: {e}")
    finally:
        rt.cancel()
        if player in jugadores_conectados:
            jugadores_conectados.remove(player)
        if player.nombre:
            await broadcast_todos(f"\n  {player.nombre} abandono el dungeon.")
        try:
            writer.close()
        except Exception:
            pass
        print(f"[TCP] Desconectado: {player.addr}")


# ============================================================
# HANDLE CHAT WS (navegador)
# ============================================================

async def handle_chat_ws(websocket):
    chat_ws_clients.add(websocket)
    print(f"[WS] Navegador conectado: {websocket.remote_address}")

    jugadores_info = [
        {"nombre": p.nombre, "clase": p.personaje["nombreClase"], "nivel": p.nivel}
        for p in jugadores_conectados if p.nombre
    ]
    try:
        await websocket.send(json.dumps({
            "scope": "sistema", "nombre": "Servidor",
            "mensaje": f"{len(jugadores_info)} jugadores conectados",
            "jugadores": jugadores_info
        }))
    except Exception:
        pass

    try:
        async for msg in websocket:
            try:
                data    = json.loads(msg)
                nombre  = data.get("nombre", "Anonimo")
                mensaje = data.get("mensaje", "").strip()
                scope   = data.get("scope", "global")
                if not mensaje:
                    continue
                await broadcast_chat_ws(scope, nombre, mensaje)
                prefijo = "[Global-Web]" if scope == "global" else "[Web]"
                await broadcast_todos(f"  {prefijo} {nombre}: {mensaje}")
            except json.JSONDecodeError:
                pass
    except Exception:
        pass
    finally:
        chat_ws_clients.discard(websocket)
        print(f"[WS] Navegador desconectado: {websocket.remote_address}")


# ============================================================
# HTTP
# ============================================================

def iniciar_http():
    class SilentHandler(SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass
    httpd = HTTPServer(("0.0.0.0", 8080), SilentHandler)
    print("[HTTP]  :8080  ->  http://localhost:8080/chat.html")
    httpd.serve_forever()


# ============================================================
# MAIN
# ============================================================

async def main():
    threading.Thread(target=iniciar_http, daemon=True).start()

    tcp_server = await asyncio.start_server(handle_player, "0.0.0.0", 4000)
    ws_server  = await websockets.serve(handle_chat_ws, "0.0.0.0", 4001)

    print("[TCP]   :4000  ->  python3 client.py <IP>")
    print("[WS]    :4001  ->  navegador chat")
    print(f"[INFO]  Max {MAX_JUGADORES} jugadores  |  {len(CLASES)} clases  |  {len(ENEMIGOS)} enemigos")
    print("[INFO]  Ctrl+C para parar\n")

    async with tcp_server:
        async with ws_server:
            await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())
