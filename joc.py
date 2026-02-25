import random
<<<<<<< HEAD
from copy import deepcopy
=======
import math 


# ==============================================================================
# CLASES DE HÉROES (corregidas: ataques_turno como lista [min, max] donde aplica)
# ==============================================================================
CLASES = {
    "guerrero": {
        "vida_max": 90,
        "danio_base": 40,
        "mana_max": 30,
        "mana_turno": 10,
        "danio_especial": 70,
        "ataques_turno": 1,
        "costo_especial": 30,
        "armas": ["Espada", "Escudo", "Hacha"],
        "habilidad": "tanque_10"
    },
    "mago": {
        "vida_max": 50,
        "danio_base": 30,
        "mana_max": 70,
        "mana_turno": 20,
        "danio_especial": 60,
        "ataques_turno": 1,
        "costo_especial": 60,
        "armas": ["Vara"],
        "habilidad": "magia_antigua"
    },
    "arquero": {
        "vida_max": 40,
        "danio_base": 10,
        "mana_max": 40,
        "mana_turno": 15,
        "danio_especial": 10,
        "ataques_turno": [1, 4],           # aleatorio entre 1 y 4
        "costo_especial": 40,
        "armas": ["Arco", "Ballesta"],
        "habilidad": "flecha_ignea",
        "efecto_especial": "quemadura/veneno",
        "danio_efecto": 10,
        "duracion_efecto": 2
    },
    "curandero": {
        "vida_max": 50,
        "danio_base": 20,
        "mana_max": 50,
        "mana_turno": 20,
        "danio_especial": 20,
        "ataques_turno": 1,
        "costo_especial": 30,
        "armas": ["Espada Corta"],
        "habilidad": "absorcion",
        "curacion_especial": 20
    },
    "nigromante": {
        "vida_max": 50,
        "danio_base": 10,
        "mana_max": 80,
        "mana_turno": 20,
        "danio_especial": 60,
        "ataques_turno": [1, 5],           # aleatorio entre 1 y 5
        "costo_especial": 60,
        "armas": ["Vara", "Varita"],
        "habilidad": "maldicion_tiempo",
        "max_eskeletos": 5
    },
    "hechicero": {
        "vida_max": 50,
        "danio_base": 30,
        "mana_max": 70,
        "mana_turno": 30,
        "danio_especial": 70,
        "ataques_turno": 1,
        "costo_especial": 70,
        "armas": ["Grimorio"],
        "habilidad": "invocar_esqueleto"
    },
    "caballero": {
        "vida_max": 70,
        "danio_base": 50,
        "mana_max": 40,
        "mana_turno": 10,
        "danio_especial": 60,
        "ataques_turno": 1,
        "costo_especial": 40,
        "armas": ["Espada", "Lanza"],
        "habilidad": "embestida_copia"
    },
    "cazador": {
        "vida_max": 60,
        "danio_base": 50,
        "mana_max": 30,
        "mana_turno": 10,
        "danio_especial": 30,
        "ataques_turno": 1,
        "costo_especial": 30,
        "armas": ["Escopeta"],
        "habilidad": "inmovilizar",
        "efecto_especial": "represalia",
        "duracion_efecto": 1
    },
    "asesino": {
        "vida_max": 50,
        "danio_base": 20,
        "mana_max": 20,
        "mana_turno": 10,
        "danio_especial": 60,
        "ataques_turno": [1, 3],           # aleatorio entre 1 y 3
        "costo_especial": 20,
        "armas": ["Daga", "Espada Corta"],
        "habilidad": "muerte_garantizada"
    },
    "barbaro": {
        "vida_max": 60,
        "danio_base": 50,
        "mana_max": 30,
        "mana_turno": 5,
        "danio_especial": 70,
        "ataques_turno": 1,
        "costo_especial": 30,
        "armas": ["Espada", "Escudo", "Hacha", "Maza"],
        "habilidad": "abocajarro"
    }
}

# ==============================================================================
# ENEMIGOS (completado el "oso" y añadido cierre)
# ==============================================================================
ENEMIGOS = {
    "bandido": {
        "vida_max": 60,
        "danio_base": 20,
        "tier": "Base",
        "ataques_turno": 1,
        "danio_especial": 0,
        "cooldown_especial": 0,
        "habilidad_especial": None
    },
    "slime": {
        "vida_max": 90,
        "danio_base": 5,
        "tier": "Base",
        "ataques_turno": 2,
        "danio_especial": 0,
        "cooldown_especial": 0,
        "habilidad_especial": None
    },
    "duende": {
        "vida_max": 50,
        "danio_base": 15,
        "tier": "Base",
        "ataques_turno": 2,
        "danio_especial": 0,
        "cooldown_especial": 0,
        "habilidad_especial": None
    },
    "esqueleto": {
        "vida_max": 70,
        "danio_base": 25,
        "tier": "Base",
        "ataques_turno": 1,
        "danio_especial": 0,
        "cooldown_especial": 0,
        "habilidad_especial": None
    },
    "zombie": {
        "vida_max": 80,
        "danio_base": 10,
        "tier": "Base",
        "ataques_turno": 1,
        "danio_especial": 0,
        "cooldown_especial": 0,
        "habilidad_especial": None
    },
    "orco": {
        "vida_max": 70,
        "danio_base": 30,
        "tier": "Base",
        "ataques_turno": 1,
        "danio_especial": 0,
        "cooldown_especial": 0,
        "habilidad_especial": None
    },
    "lobo": {
        "vida_max": 60,
        "danio_base": 15,
        "tier": "Base",
        "ataques_turno": [1, 2],
        "danio_especial": 0,
        "cooldown_especial": 0,
        "habilidad_especial": None
    },
    "oso": {
        "vida_max": 75,
        "danio_base": 35,
        "tier": "Base",
        "ataques_turno": 1,
        "danio_especial": 0,
        "cooldown_especial": 0,
        "habilidad_especial": None
    }
}

# ==============================================================================
# FUNCIONES DEL JUEGO
# ==============================================================================

def crear_personaje(nombre_clase):
    if nombre_clase not in CLASES:
        raise ValueError(f"Clase no existe: {nombre_clase}")

    base = deepcopy(CLASES[nombre_clase])
    
    personaje = {
        "nombre_clase": nombre_clase,
        "vida_actual": base["vida_max"],
        "mana_actual": base["mana_max"],
        "vida_max": base["vida_max"],
        "mana_max": base["mana_max"],
        **base,  # copia el resto de stats
    }
    
    return personaje


def mostrar_clases():
    print("\n" + "="*60)
    print("               CLASES DISPONIBLES                ")
    print("="*60)
    
    for i, clase in enumerate(CLASES.keys(), 1):
        stats = CLASES[clase]
        ataques = stats["ataques_turno"]
        if isinstance(ataques, list):
            ataques_str = f"{ataques[0]}-{ataques[1]} (aleatorio)"
        else:
            ataques_str = str(ataques)
            
        print(f"{i:2d}. {clase.capitalize():<12} "
              f" Vida: {stats['vida_max']:>3}   "
              f" Daño: {stats['danio_base']:>3}   "
              f" Ataques: {ataques_str:<14} "
              f" Mana: {stats['mana_max']:>3}")
    
    print("="*60)


def elegir_clase():
    while True:
        mostrar_clases()
        eleccion = input("\nElige una clase (nombre o número): ").strip().lower()
        
        # Si es número
        if eleccion.isdigit():
            num = int(eleccion)
            if 1 <= num <= len(CLASES):
                return list(CLASES.keys())[num - 1]
            print("Número inválido. Intenta otra vez.")
            continue
        
        # Si es nombre
        if eleccion in CLASES:
            return eleccion
        
        print("Clase no encontrada. Escribe el nombre o el número.")


def main():
    print("¡Bienvenido al Juego de Combate por Turnos!\n")
    
    clase_elegida = elegir_clase()
    jugador = crear_personaje(clase_elegida)
    
    print("\n" + "-"*40)
    print(" TU PERSONAJE HA SIDO CREADO ")
    print("-"*40)
    print(f"Clase:       {jugador['nombre_clase'].capitalize()}")
    print(f"Vida:        {jugador['vida_actual']}/{jugador['vida_max']}")
    print(f"Mana:        {jugador['mana_actual']}/{jugador['mana_max']}")
    print(f"Ataques/turno: {jugador['ataques_turno']}")
    print(f"Daño base:   {jugador['danio_base']}")
    print(f"Daño especial: {jugador.get('danio_especial', '—')}")
    print("-"*40)
    
    # Aquí iría el resto del juego: elegir enemigo, combate, etc.
    print("\n(El combate aún no está implementado. ¡Podemos seguir añadiéndolo!)")


if __name__ == "__main__":
    main()