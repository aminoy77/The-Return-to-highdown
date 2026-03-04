import random
from copy import deepcopy

# ==============================================================================
# CLASES DE HÉROES
# ==============================================================================
CLASES = {
    "guerrero": {
        "vidaMax": 90,
        "danioBase": 40,
        "manaMax": 30,
        "manaTurno": 10,
        "danioEspecial": 70,
        "ataquesTurno": 1,
        "costoEspecial": 30,
        "armas": ["Espada", "Escudo", "Hacha"],
        "habilidad": "tanque_10"
    },
    "mago": {
        "vidaMax": 50,
        "danioBase": 30,
        "manaMax": 70,
        "manaTurno": 20,
        "danioEspecial": 60,
        "ataquesTurno": 1,
        "costoEspecial": 60,
        "armas": ["Vara"],
        "habilidad": "magia_antigua"
    },
    "arquero": {
        "vidaMax": 40,
        "danioBase": 10,
        "manaMax": 40,
        "manaTurno": 15,
        "danioEspecial": 10,
        "ataquesTurno": [1, 4],
        "costoEspecial": 40,
        "armas": ["Arco", "Ballesta"],
        "habilidad": "flecha_ignea",
        "efectoEspecial": "quemadura/veneno",
        "danioEfecto": 10,
        "duracionEfecto": 2
    },
    "curandero": {
        "vidaMax": 50,
        "danioBase": 20,
        "manaMax": 50,
        "manaTurno": 20,
        "danioEspecial": 20,
        "ataquesTurno": 1,
        "costoEspecial": 30,
        "armas": ["Espada Corta"],
        "habilidad": "absorcion",
        "curacionEspecial": 20
    },
    "nigromante": {
        "vidaMax": 50,
        "danioBase": 10,
        "manaMax": 80,
        "manaTurno": 20,
        "danioEspecial": 60,
        "ataquesTurno": [1, 5],
        "costoEspecial": 60,
        "armas": ["Vara", "Varita"],
        "habilidad": "maldicion_tiempo",
        "maxEskeletos": 5
    },
    "hechicero": {
        "vidaMax": 50,
        "danioBase": 30,
        "manaMax": 70,
        "manaTurno": 30,
        "danioEspecial": 70,
        "ataquesTurno": 1,
        "costoEspecial": 70,
        "armas": ["Grimorio"],
        "habilidad": "invocar_esqueleto"
    },
    "caballero": {
        "vidaMax": 70,
        "danioBase": 50,
        "manaMax": 40,
        "manaTurno": 10,
        "danioEspecial": 60,
        "ataquesTurno": 1,
        "costoEspecial": 40,
        "armas": ["Espada", "Lanza"],
        "habilidad": "embestida_copia"
    },
    "cazador": {
        "vidaMax": 60,
        "danioBase": 50,
        "manaMax": 30,
        "manaTurno": 10,
        "danioEspecial": 30,
        "ataquesTurno": 1,
        "costoEspecial": 30,
        "armas": ["Escopeta"],
        "habilidad": "inmovilizar",
        "efectoEspecial": "represalia",
        "duracionEfecto": 1
    },
    "asesino": {
        "vidaMax": 50,
        "danioBase": 20,
        "manaMax": 20,
        "manaTurno": 10,
        "danioEspecial": 60,
        "ataquesTurno": [1, 3],
        "costoEspecial": 20,
        "armas": ["Daga", "Espada Corta"],
        "habilidad": "muerte_garantizada"
    },
    "barbaro": {
        "vidaMax": 60,
        "danioBase": 50,
        "manaMax": 30,
        "manaTurno": 5,
        "danioEspecial": 70,
        "ataquesTurno": 1,
        "costoEspecial": 30,
        "armas": ["Espada", "Escudo", "Hacha", "Maza"],
        "habilidad": "abocajarro"
    }
}

# ==============================================================================
# ENEMIGOS
# ==============================================================================
ENEMIGOS = {
    "bandido": {
        "vidaMax": 60,
        "danioBase": 20,
        "tier": "Base",
        "ataquesTurno": 1,
        "danioEspecial": 0,
        "cooldownEspecial": 0,
        "habilidadEspecial": None
    },
    "slime": {
        "vidaMax": 90,
        "danioBase": 5,
        "tier": "Base",
        "ataquesTurno": 2,
        "danioEspecial": 0,
        "cooldownEspecial": 0,
        "habilidadEspecial": None
    },
    "duende": {
        "vidaMax": 50,
        "danioBase": 15,
        "tier": "Base",
        "ataquesTurno": 2,
        "danioEspecial": 0,
        "cooldownEspecial": 0,
        "habilidadEspecial": None
    },
    "esqueleto": {
        "vidaMax": 70,
        "danioBase": 25,
        "tier": "Base",
        "ataquesTurno": 1,
        "danioEspecial": 0,
        "cooldownEspecial": 0,
        "habilidadEspecial": None
    },
    "zombie": {
        "vidaMax": 80,
        "danioBase": 10,
        "tier": "Base",
        "ataquesTurno": 1,
        "danioEspecial": 0,
        "cooldownEspecial": 0,
        "habilidadEspecial": None
    },
    "orco": {
        "vidaMax": 70,
        "danioBase": 30,
        "tier": "Base",
        "ataquesTurno": 1,
        "danioEspecial": 0,
        "cooldownEspecial": 0,
        "habilidadEspecial": None
    },
    "lobo": {
        "vidaMax": 60,
        "danioBase": 15,
        "tier": "Base",
        "ataquesTurno": [1, 2],
        "danioEspecial": 0,
        "cooldownEspecial": 0,
        "habilidadEspecial": None
    },
    "oso": {
        "vidaMax": 75,
        "danioBase": 35,
        "tier": "Base",
        "ataquesTurno": 1,
        "danioEspecial": 0,
        "cooldownEspecial": 0,
        "habilidadEspecial": None
    },
    "ogro": {
        "vidaMax": 90,
        "danioBase": 30,
        "tier": "Especial",
        "ataquesTurno": 1,
        "danioEspecial": 0,
        "cooldownEspecial": 0,
        "habilidadEspecial": None
    },
    "troll": {
        "vidaMax": 100,
        "danioBase": 35,
        "tier": "Especial",
        "ataquesTurno": 1,
        "danioEspecial": 0,
        "cooldownEspecial": 0,
        "habilidadEspecial": None
    },
    "gigante": {
        "vidaMax": 110,
        "danioBase": 45,
        "tier": "Especial",
        "ataquesTurno": 1,
        "danioEspecial": 0,
        "cooldownEspecial": 0,
        "habilidadEspecial": None
    },
    "ciclope": {
        "vidaMax": 80,
        "danioBase": 40,
        "tier": "Especial",
        "ataquesTurno": 1,
        "danioEspecial": 0,
        "cooldownEspecial": 0,
        "habilidadEspecial": None
    },
    "golem": {
        "vidaMax": 180,
        "danioBase": 50,
        "tier": "Superior",
        "ataquesTurno": 1,
        "danioEspecial": 10,
        "cooldownEspecial": 3,
        "habilidadEspecial": "diamante_brillante"
    },
    "hombreLobo": {
        "vidaMax": 90,
        "danioBase": 30,
        "tier": "Especial",
        "ataquesTurno": [1, 3],
        "danioEspecial": 0,
        "cooldownEspecial": 0,
        "habilidadEspecial": None
    },
    "vampiro": {
        "vidaMax": 125,
        "danioBase": 20,
        "tier": "Superior",
        "ataquesTurno": [1, 2],
        "danioEspecial": 60,
        "cooldownEspecial": 3,
        "habilidadEspecial": "sanguivampirismo"
    },
    "altoOrco": {
        "vidaMax": 150,
        "danioBase": 50,
        "tier": "Superior",
        "ataquesTurno": 1,
        "danioEspecial": 70,
        "cooldownEspecial": 4,
        "habilidadEspecial": "golpe_devastador"
    },
    "quimera": {
        "vidaMax": 80,
        "danioBase": 20,
        "tier": "Especial",
        "ataquesTurno": 1,
        "danioEspecial": 0,
        "cooldownEspecial": 0,
        "habilidadEspecial": None
    },
    "elfoOscuro": {
        "vidaMax": 150,
        "danioBase": 60,
        "tier": "Superior",
        "ataquesTurno": 1,
        "danioEspecial": 90,
        "cooldownEspecial": 3,
        "habilidadEspecial": "paralisis_golpe"
    },
    "demonioInferior": {
        "vidaMax": 90,
        "danioBase": 20,
        "tier": "Especial",
        "ataquesTurno": [1, 2],
        "danioEspecial": 0,
        "cooldownEspecial": 0,
        "habilidadEspecial": None
    },
    "demonioSuperior": {
        "vidaMax": 150,
        "danioBase": 60,
        "tier": "Superior",
        "ataquesTurno": 1,
        "danioEspecial": 60,
        "cooldownEspecial": 3,
        "habilidadEspecial": "absorcion_mana"
    },
    "reyDemonio": {
        "vidaMax": 250,
        "danioBase": 70,
        "tier": "Boss(1)",
        "ataquesTurno": 1,
        "danioEspecial": 100,
        "cooldownEspecial": 3,
        "habilidadEspecial": "invoca_demonios"
    },
    "leviatan": {
        "vidaMax": 250,
        "danioBase": 80,
        "tier": "Élite",
        "ataquesTurno": 1,
        "danioEspecial": 0,
        "cooldownEspecial": 3,
        "habilidadEspecial": "grito_ensordecedor"
    },
    "reyEsqueleto": {
        "vidaMax": 230,
        "danioBase": 80,
        "tier": "Élite",
        "ataquesTurno": 1,
        "danioEspecial": 0,
        "cooldownEspecial": 2,
        "habilidadEspecial": "invoca_esqueletos"
    },
    "kraken": {
        "vidaMax": 400,
        "danioBase": 70,
        "tier": "Boss(2)",
        "ataquesTurno": 1,
        "danioEspecial": 100,
        "cooldownEspecial": 3,
        "habilidadEspecial": "tentaclazo"
    },
    "dragon": {
        "vidaMax": 250,
        "danioBase": 80,
        "tier": "Élite",
        "ataquesTurno": 1,
        "danioEspecial": 60,
        "cooldownEspecial": 3,
        "habilidadEspecial": "quemadura"
    },
    "alpha": {
        "vidaMax": 500,
        "danioBase": 90,
        "tier": "(Final)Boss",
        "ataquesTurno": 1,
        "danioEspecial": 150,
        "cooldownEspecial": 4,
        "habilidadEspecial": "invoca_dragones"
    },
    "tiburon": {
        "vidaMax": 80,
        "danioBase": 30,
        "tier": "Especial",
        "ataquesTurno": 1,
        "danioEspecial": 0,
        "cooldownEspecial": 0,
        "habilidadEspecial": None
    }
}

# ==============================================================================
# FUNCIONES DE COMBATE
# ==============================================================================

def ataques_por_turno(valor):
    """Retorna el número de ataques por turno (soporta rango o valor fijo)."""
    if isinstance(valor, list):
        return random.randint(valor[0], valor[1])
    return valor


def crear_enemigo(nombre_enemigo):
    """Crea una instancia independiente de un enemigo."""
    if nombre_enemigo not in ENEMIGOS:
        raise ValueError(f"Enemigo no existe: {nombre_enemigo}")
    
    base = deepcopy(ENEMIGOS[nombre_enemigo])
    
    enemigo = {
        "nombre": nombre_enemigo.capitalize(),
        "vida_actual": base["vidaMax"],
        **base
    }
    
    return enemigo


def atacar(atacante, defensor, danio):
    """Aplica daño al defensor."""
    # Detectar si es jugador o enemigo por la clave disponible
    if "vidaActual" in defensor:
        defensor["vidaActual"] -= danio
        if defensor["vidaActual"] < 0:
            defensor["vidaActual"] = 0
        print(f"  {atacante.get('nombre', atacante.get('nombreClase', 'Unknown'))} ataca por {danio} de daño!")
        print(f"    {defensor.get('nombre', defensor.get('nombreClase', 'Unknown'))} tiene {defensor['vidaActual']}/{defensor.get('vidaMax', defensor.get('vidaActual'))} HP restantes.")
    else:
        # Es enemigo
        defensor["vida_actual"] -= danio
        if defensor["vida_actual"] < 0:
            defensor["vida_actual"] = 0
        print(f"  {atacante.get('nombre', atacante.get('nombreClase', 'Unknown'))} ataca por {danio} de daño!")
        print(f"    {defensor.get('nombre', defensor.get('nombreClase', 'Unknown'))} tiene {defensor['vida_actual']}/{defensor.get('vidaMax', defensor.get('vida_actual'))} HP restantes.")


def especial(jugador, enemigo):
    """Ejecuta el ataque especial del jugador."""
    clase = jugador["nombreClase"]
    danio = jugador.get("danioEspecial", 0)
    costo = jugador.get("costoEspecial", 0)
    
    if jugador["manaActual"] < costo:
        print(f"  No tienes suficiente mana para el ataque especial (necesitas {costo}).")
        return False
    
    # Gastar mana
    jugador["manaActual"] -= costo
    
    # Aplicar efecto especial segun clase
    if clase == "arquero":
        print(f"  Flecha ignea! Causas {danio} de dano y efecto de quemadura.")
        enemigo["vida_actual"] -= danio
        if "efecto" not in enemigo:
            enemigo["efecto"] = {"tipo": "quemadura", "danio": jugador.get("danioEfecto", 10), "turnos": jugador.get("duracionEfecto", 2)}
    elif clase == "curandero":
        curacion = jugador.get("curacionEspecial", 20)
        jugador["vidaActual"] = min(jugador["vidaActual"] + curacion, jugador["vidaMax"])
        print(f"  Sanacion! Te curas {curacion} HP. Ahora tienes {jugador['vidaActual']}/{jugador['vidaMax']} HP.")
        return True
    elif clase == "nigromante":
        print(f"  Maldicion del tiempo! Causas {danio} de dano.")
        enemigo["vida_actual"] -= danio
    elif clase == "hechicero":
        print(f"  Invocar esqueleto! Causas {danio} de dano.")
        enemigo["vida_actual"] -= danio
    elif clase == "caballero":
        print(f"  Embestida! Causas {danio} de dano.")
        enemigo["vida_actual"] -= danio
    elif clase == "cazador":
        print(f"  Inmovilizar! Causas {danio} de dano y efecto de represalia.")
        enemigo["vida_actual"] -= danio
    elif clase == "asesino":
        print(f"  Muerte garantizada! Causas {danio} de dano critico!")
        enemigo["vida_actual"] -= danio
    elif clase == "barbaro":
        print(f"  A bocajarro! Causas {danio} de dano brutal!")
        enemigo["vida_actual"] -= danio
    elif clase == "guerrero":
        print(f"  Golpe de tanque! Causas {danio} de dano.")
        enemigo["vida_actual"] -= danio
    elif clase == "mago":
        print(f"  Magia antigua! Causas {danio} de dano arcano.")
        enemigo["vida_actual"] -= danio
    else:
        print(f"  Ataque especial! Causas {danio} de dano.")
        enemigo["vida_actual"] -= danio
    
    if enemigo["vida_actual"] < 0:
        enemigo["vida_actual"] = 0
    
    print(f"    {enemigo['nombre']} tiene {enemigo['vida_actual']}/{enemigo['vidaMax']} HP restantes.")
    return True


def turno_enemigo(enemigo, jugador):
    """El enemigo ataca al jugador."""
    num_ataques = ataques_por_turno(enemigo.get("ataquesTurno", 1))
    print(f"\n  Turno de {enemigo['nombre']} ({num_ataques} ataque(s)):")
    
    for i in range(num_ataques):
        if jugador["vidaActual"] <= 0:
            break
        danio = enemigo.get("danioBase", 10)
        danio = int(danio * random.uniform(0.8, 1.2))
        atacar(enemigo, jugador, danio)
    
    if "efecto" in enemigo:
        efecto = enemigo["efecto"]
        print(f"  {enemigo['nombre']} sufre {efecto['danio']} de dano por {efecto['tipo']}!")
        jugador["vidaActual"] -= efecto["danio"]
        efecto["turnos"] -= 1
        if efecto["turnos"] <= 0:
            del enemigo["efecto"]


def mostrar_menu_combate():
    """Muestra el menu de opciones de combate."""
    print("\n" + "="*40)
    print("           MENU DE COMBATE           ")
    print("="*40)
    print("1. ATACAR")
    print("2. ESPECIAL")
    print("3. PASAR / HUIR")
    print("="*40)


def combate(jugador, nombre_enemigo):
    """Sistema de combate por turnos."""
    enemigo = crear_enemigo(nombre_enemigo)
    
    print("\n" + "="*20)
    print(f"APARECE UN {enemigo['nombre'].upper()}!")
    print(f"   Vida: {enemigo['vida_actual']}/{enemigo['vidaMax']}")
    print(f"   Dano: {enemigo['danioBase']}")
    print(f"   Ataques/turno: {enemigo.get('ataquesTurno', 1)}")
    print("="*20)
    
    turno = 1
    
    while jugador["vidaActual"] > 0 and enemigo["vida_actual"] > 0:
        print(f"\n--- TURNO {turno} ---")
        print(f"  {jugador['nombre']} (Tu): {jugador['vidaActual']}/{jugador['vidaMax']} HP | {jugador['manaActual']}/{jugador['manaMax']} Mana")
        print(f"  {enemigo['nombre']}: {enemigo['vida_actual']}/{enemigo['vidaMax']} HP")
        
        jugador["manaActual"] = min(jugador["manaActual"] + jugador.get("manaTurno", 0), jugador["manaMax"])
        
        mostrar_menu_combate()
        accion = input("\nElige tu accion (1-3): ").strip()
        
        if accion == "1":
            num_ataques = ataques_por_turno(jugador.get("ataquesTurno", 1))
            print(f"\n  Atacas {num_ataques} vez(es)!")
            for i in range(num_ataques):
                if enemigo["vida_actual"] <= 0:
                    break
                danio = jugador.get("danioBase", 10)
                danio = int(danio * random.uniform(0.8, 1.2))
                atacar(jugador, enemigo, danio)
        
        elif accion == "2":
            especial(jugador, enemigo)
        
        elif accion == "3":
            print("\n  Huye del combate!")
            return False
        
        else:
            print("\n  Accion invalida. Pasas el turno.")
        
        if enemigo["vida_actual"] > 0:
            turno_enemigo(enemigo, jugador)
        
        turno += 1
    
    print("\n" + "="*40)
    if jugador["vidaActual"] > 0:
        print(f"  VICTORIA! Has derrotado a {enemigo['nombre']}!")
        print(f"  Has ganado experiencia y posibles tesoros.")
        return True
    else:
        print("  DERROTA! Has sido derrotado...")
        return False


# ==============================================================================
# FUNCIONES
# ==============================================================================

def crearPersonaje(nombrePersonaje, nombreClase):
    if nombreClase not in CLASES:
        raise ValueError(f"Clase no existe: {nombreClase}")

    base = deepcopy(CLASES[nombreClase])
    
    personaje = {
        "nombre": nombrePersonaje.strip() or "Heroe sin nombre",
        "nombreClase": nombreClase,
        "vidaActual": base["vidaMax"],
        "manaActual": base["manaMax"],
        "vidaMax": base["vidaMax"],
        "manaMax": base["manaMax"],
        **base,
    }
    
    return personaje


def mostrarClases():
    print("\n" + "="*60)
    print("               CLASES DISPONIBLES                ")
    print("="*60)
    
    for i, clase in enumerate(CLASES.keys(), 1):
        stats = CLASES[clase]
        ataques = stats["ataquesTurno"]
        ataquesStr = f"{ataques[0]}-{ataques[1]} (aleatorio)" if isinstance(ataques, list) else str(ataques)
            
        print(f"{i:2d}. {clase.capitalize():<12} "
              f" Vida: {stats['vidaMax']:>3}   "
              f" Dano: {stats['danioBase']:>3}   "
              f" Ataques: {ataquesStr:<14} "
              f" Mana: {stats['manaMax']:>3}")
    
    print("="*60)


def elegirClase():
    while True:
        mostrarClases()
        eleccion = input("\nElige una clase (nombre o numero): ").strip().lower()
        
        if eleccion.isdigit():
            num = int(eleccion)
            if 1 <= num <= len(CLASES):
                return list(CLASES.keys())[num - 1]
            print("Numero fuera de rango.")
            continue
        
        if eleccion in CLASES:
            return eleccion
        
        print("Clase no encontrada. Intenta de nuevo.")


def main():
    print("Bienvenido al Juego de Combate por Turnos!\n")
    
    nombre = input("Como te llamas, valiente aventurero? ").strip()
    if not nombre:
        nombre = "Aventurero Annimo"
    
    print(f"\nEncantado, {nombre}.")
    
    claseElegida = elegirClase()
    
    jugador = crearPersonaje(nombre, claseElegida)
    
    print("\n" + "="*50)
    print(" PERSONAJE CREADO ")
    print("="*50)
    print(f"Nombre:      {jugador['nombre']}")
    print(f"Clase:       {jugador['nombreClase'].capitalize()}")
    print(f"Vida:        {jugador['vidaActual']}/{jugador['vidaMax']}")
    print(f"Mana:        {jugador['manaActual']}/{jugador['manaMax']}")
    print(f"Ataques/turno: {jugador['ataquesTurno']}")
    print(f"Dano base:   {jugador['danioBase']}")
    print("="*50)
    
    # Combate automatico al crear el personaje
    print("\n  Te dispones a salir al mundo... y un enemigo aparece!")
    input("Presiona Enter para continuar...")
    
    # Elegir un enemigo aleatorio (solo tier Base)
    enemigos_base = [k for k, v in ENEMIGOS.items() if v.get("tier") == "Base"]
    enemigo_aleatorio = random.choice(enemigos_base)
    
    resultado = combate(jugador, enemigo_aleatorio)
    
    if resultado and jugador["vidaActual"] > 0:
        print("\n  Continuara...")


if __name__ == "__main__":
    main()

