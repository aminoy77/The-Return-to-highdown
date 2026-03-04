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
# FUNCIONES
# ==============================================================================

def crearPersonaje(nombrePersonaje, nombreClase):
    if nombreClase not in CLASES:
        raise ValueError(f"Clase no existe: {nombreClase}")

    base = deepcopy(CLASES[nombreClase])
    
    personaje = {
        "nombre": nombrePersonaje.strip() or "Héroe sin nombre",
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
              f" Daño: {stats['danioBase']:>3}   "
              f" Ataques: {ataquesStr:<14} "
              f" Mana: {stats['manaMax']:>3}")
    
    print("="*60)


def elegirClase():
    while True:
        mostrarClases()
        eleccion = input("\nElige una clase (nombre o número): ").strip().lower()
        
        if eleccion.isdigit():
            num = int(eleccion)
            if 1 <= num <= len(CLASES):
                return list(CLASES.keys())[num - 1]
            print("Número fuera de rango.")
            continue
        
        if eleccion in CLASES:
            return eleccion
        
        print("Clase no encontrada. Intenta de nuevo.")


def main():
    print("¡Bienvenido al Juego de Combate por Turnos!\n")
    
    nombre = input("¿Cómo te llamas, valiente aventurero? ").strip()
    if not nombre:
        nombre = "Aventurero Anónimo"
    
    print(f"\nEncantado, {nombre}.")
    
    claseElegida = elegirClase()
    
    jugador = crearPersonaje(nombre, claseElegida)
    
    print("\n" + "═"*50)
    print(" ¡PERSONAJE CREADO! ")
    print("═"*50)
    print(f"Nombre:      {jugador['nombre']}")
    print(f"Clase:       {jugador['nombreClase'].capitalize()}")
    print(f"Vida:        {jugador['vidaActual']}/{jugador['vidaMax']}")
    print(f"Mana:        {jugador['manaActual']}/{jugador['manaMax']}")
    print(f"Ataques/turno: {jugador['ataquesTurno']}")
    print(f"Daño base:   {jugador['danioBase']}")
    print("═"*50)
    
    print("\n(El sistema/lore de combate todavía no está implementado)")


if __name__ == "__main__":
    main()

