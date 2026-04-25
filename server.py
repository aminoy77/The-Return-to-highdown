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
SERVER_URL = os.environ.get("SERVER_URL", "")  # URL del client per despertar
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
USAR_SUPABASE = bool(SUPABASE_URL and SUPABASE_KEY)
SAVES_DIR = "saves"
os.makedirs(SAVES_DIR, exist_ok=True)

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
    "demonioSuperior": {"vidaMax": 150, "danioBase": 60, "ataquesTurno": 1, "tier": "Superior"},
    "leviatan": {"vidaMax": 250, "danioBase": 80, "ataquesTurno": 1, "tier": "Elite"},
    "reyEsqueleto": {"vidaMax": 230, "danioBase": 80, "ataquesTurno": 1, "tier": "Elite"},
    "reyDemonio": {"vidaMax": 250, "danioBase": 70, "ataquesTurno": 1, "tier": "Boss"},
    "kraken": {"vidaMax": 400, "danioBase": 70, "ataquesTurno": 1, "tier": "Boss"},
    "alpha": {"vidaMax": 500, "danioBase": 90, "ataquesTurno": 1, "tier": "Boss"},
}

XP_POR_TIER = {"Base": 10, "Especial": 30, "Superior": 50, "Elite": 100, "Boss": 250}

CATALOGO = {
    "pocion_vida": {"nombre": "Pocion de Vida", "emoji": "🧪", "precio": 30},
    "pocion_danio": {"nombre": "Pocion de Danio", "emoji": "⚗️", "precio": 40},
    "gema_teleporte": {"nombre": "Gema de Teletransporte", "emoji": "💎", "precio": 50},
}

BIOMAS = {
    "desierto": {"emoji": "🏜", "enemigos": ["bandido", "duende", "esqueleto", "zombie", "lobo"]},
    "mar": {"emoji": "🌊", "enemigos": ["slime", "troll", "vampiro"]},
    "nieve": {"emoji": "❄️", "enemigos": ["gigante", "elfoOscuro", "demonioSuperior"]},
}

# ==================== SALAS ====================
SALAS = {
    1: {"nombre": "North Mass", "descripcion": "Arena caliente bajo tus pies.", "conexiones": {"norte": 2, "este": 13, "sur": 6}, "bioma": "desierto", "cantidad": 1, "hospital": True},
    2: {"nombre": "Dunas del Norte", "descripcion": "Dunas interminables.", "conexiones": {"sur": 1, "norte": 3}, "bioma": "desierto", "cantidad": 2},
    3: {"nombre": "Ruinas del Desierto", "descripcion": "Columnas rotas.", "conexiones": {"oeste": 4, "norte": 5, "este": 16}, "bioma": "desierto", "cantidad": 2},
    6: {"nombre": "Oasis tranquilo", "descripcion": "Un pequeno oasis.", "conexiones": {"sur": 10, "oeste": 7, "norte": 1}, "hospital": True, "tienda": True},
    13: {"nombre": "Templo Olvidado", "descripcion": "Un templo en el desierto.", "conexiones": {"sur": 12, "norte": 14}, "encuentros": [("reyEsqueleto", 1)], "tienda": True},
    16: {"nombre": "Vestigios Enterrados", "descripcion": "Ruinas antiguas.", "conexiones": {"norte": 17, "sur": 15}, "bioma": "desierto", "cantidad": 1},
    32: {"nombre": "Falla de los Antiguos", "descripcion": "Grieta con reliquias.", "conexiones": {"sur": 31}, "bioma": "desierto", "cantidad": 2, "hospital": True, "encuentros": [("reyDemonio", 1)]},
    72: {"nombre": "Cumbre del Kraken", "descripcion": "Una sombra colosal.", "conexiones": {"este": 73}, "bioma": "mar", "cantidad": 1, "encuentros": [("kraken", 1)]},
    73: {"nombre": "Ventisca Eterna", "descripcion": "El viento ruge.", "conexiones": {"este": 74}, "bioma": "nieve", "cantidad": 1},
    148: {"nombre": "Trono del Invierno", "descripcion": "Alpha te espera.", "conexiones": {"sur": 146}, "encuentros": [("alpha", 1)]},
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

def _sb_headers():
    return {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json", "Prefer": "return=representation"}

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
        async with s.get(url, headers=_sb_headers()) as r:
            if r.status == 200:
                rows = await r.json()
                return rows[0] if rows else None
    except:
        pass
    return None

async def _sb_upsert(row):
    try:
        s = _get_sb_session()
        url = f"{SUPABASE_URL}/rest/v1/mud_saves"
        headers = {**_sb_headers(), "Prefer": "resolution=merge-duplicates"}
        async with s.post(url, headers=headers, json=row) as r:
            pass
    except:
        pass

# ==================== ACCOUNT SYSTEM ====================
async def crear_cuenta(usuario, password, nombre, clase):
    existing = await verificar_login(usuario, password)
    if existing:
        return None
    
    salt = hashlib.sha256(os.urandom(16)).hexdigest()[:16]
    hashed = _hash_password(password, salt)
    data = {
        "usuario": usuario,
        "password_hash": hashed,
        "salt": salt,
        "data": {
            "nombre": nombre,
            "clase": clase,
            "nivel": 1,
            "xp": 0,
            "monedas": 50,
            "sala_id": 1,
            "salas_limpias": [],
        }
    }
    if USAR_SUPABASE:
        await _sb_upsert(data)
    else:
        with open(os.path.join(SAVES_DIR, f"{usuario}.json"), "w") as f:
            json.dump(data, f)
    return data["data"]

async def verificar_login(usuario, password):
    if USAR_SUPABASE:
        row = await _sb_get(usuario)
        if not row:
            return None
        data = row.get("data", {})
        hashed = row.get("password_hash", "")
        salt = row.get("salt", "")
        if _hash_password(password, salt) == hashed:
            return {"nombre": data.get("nombre", usuario), "clase": data.get("clase", "guerrero"), "nivel": data.get("nivel", 1), "xp": data.get("xp", 0), "monedas": data.get("monedas", 0), "sala_id": data.get("sala_id", 1), "salas_limpias": data.get("salas_limpias", [])}
        return None
    else:
        try:
            with open(os.path.join(SAVES_DIR, f"{usuario}.json")) as f:
                data = json.load(f)
            if _hash_password(password, data.get("salt", "")) == data.get("password_hash", ""):
                return data.get("data", {})
        except:
            pass
    return None

async def cargar_cuenta(usuario):
    if USAR_SUPABASE:
        row = await _sb_get(usuario)
        if row:
            return row.get("data", {})
    else:
        try:
            with open(os.path.join(SAVES_DIR, f"{usuario}.json")) as f:
                data = json.load(f)
            return data.get("data", {})
        except:
            pass
    return None

async def guardar_cuenta(usuario, data):
    if USAR_SUPABASE:
        row = {"usuario": usuario, "data": data}
        await _sb_upsert(row)
    else:
        with open(os.path.join(SAVES_DIR, f"{usuario}.json")) as f:
            json.dump({"usuario": usuario, "data": data}, f)

# ==================== PLAYER CLASS ====================
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
        self.lore_mostrado = False
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
    ranking = [[p.nombre, p.nivel, p.personaje.get("nombreClase", "?") if p.personaje else "?"] for p in jugadores_conectados if p.nombre]
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
                await broadcast_stats(p)
                await guardar_cuenta(p.usuario, {"nombre": p.nombre, "clase": p.personaje.get("nombreClase", "guerrero"), "nivel": p.nivel, "xp": p.xp, "monedas": p.monedas, "sala_id": p.sala_id, "salas_limpias": list(p.salas_limpias)})
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
                        nombre = data.get("nombre", usuario)
                        clase = data.get("clase", "guerrero")
                        
                        if clase not in CLASES:
                            clase = "guerrero"
                        
                        result = await verificar_login(usuario, password)
                        if result:
                            player.usuario = usuario
                            player.nombre = result.get("nombre", usuario)
                            player.nivel = result.get("nivel", 1)
                            player.xp = result.get("xp", 0)
                            player.monedas = result.get("monedas", 0)
                            player.sala_id = result.get("sala_id", 1)
                            player.salas_limpias = set(result.get("salas_limpias", []))
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
                        player.usuario = usuario
                        player.nombre = nombre
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
            jugadores_conectados.remove(player)
        if player.usuario:
            await guardar_cuenta(player.usuario, {
                "nombre": player.nombre,
                "clase": player.personaje.get("nombreClase", "guerrero"),
                "nivel": player.nivel,
                "xp": player.xp,
                "monedas": player.monedas,
                "sala_id": player.sala_id,
                "salas_limpias": list(player.salas_limpias),
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
        await move(player, "norte")
    elif cmd in ["s", "sur"]:
        await move(player, "sur")
    elif cmd in ["e", "este"]:
        await move(player, "este")
    elif cmd in ["o", "oeste"]:
        await move(player, "oeste")
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
    elif cmd == "mochila":
        await mochila(player)
    elif cmd == "ranking":
        await broadcast_ranking()
    elif cmd == "ayuda":
        await player.send({"type": "message", "text": "Comandos: n/s/e/o (mover), atacar, stats, hospital, tienda, comprar <item>, usar <item>, mochila, ranking"})
    else:
        await player.send({"type": "message", "text": f"Comando '{cmd}' desconocido. Escribe 'ayuda'"})

async def move(player, direction):
    if player.combate:
        await player.send({"type": "message", "text": "No puedes moverte en combate!"})
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
        bioma_info = f" [{bioma.get('emoji', '')} {sala['bioma']}]"
    
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

async def mochila(player):
    items = []
    for iid, qty in player.inventario.items():
        if qty > 0:
            item = CATALOGO.get(iid, {"nombre": iid, "emoji": "📦"})
            items.append(f"{item.get('emoji', '📦')} {item['nombre']} x{qty}")
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
    if USAR_SUPABASE:
        print(f"✅ Using Supabase: {SUPABASE_URL}")
    else:
        print(f"💾 Using local saves: {SAVES_DIR}")
    web.run_app(app, host='0.0.0.0', port=PORT)