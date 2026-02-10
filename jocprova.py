# vida.py
import pgzrun

WIDTH = 900
HEIGHT = 600

vida = 100

# Diccionario con todos los sprites
corazones = {
    100: Actor("pixil-frame-0"),
     95: Actor("pixil-frame-1"),
     90: Actor("pixil-frame-2"),
     85: Actor("pixil-frame-3"),
     80: Actor("pixil-frame-4"),
     75: Actor("pixil-frame-5"),
     70: Actor("pixil-frame-6"),
     65: Actor("pixil-frame-7"),
     60: Actor("pixil-frame-8"),
     55: Actor("pixil-frame-9"),
     50: Actor("pixil-frame-10"),
     45: Actor("pixil-frame-11"),
     40: Actor("pixil-frame-12"),
     35: Actor("pixil-frame-13"),
     30: Actor("pixil-frame-14"),
     25: Actor("pixil-frame-15"),
     20: Actor("pixil-frame-16"),
     15: Actor("pixil-frame-17"),
     10: Actor("pixil-frame-18"),
      5: Actor("pixil-frame-19"),      # versión normal (amarillo/naranja/etc)
      0: Actor("pixil-frame-21"),
}

# El sprite especial rojo para cuando vida == 5
corazon_rojo = Actor("pixil-frame-20")

# Posición central para TODOS
POS_X = WIDTH // 2
POS_Y = HEIGHT // 2

for actor in corazones.values():
    actor.pos = (POS_X, POS_Y)
corazon_rojo.pos = (POS_X, POS_Y)


def draw():
    screen.clear()                 # ¡Siempre limpiar primero!

    if vida == 5:
        corazon_rojo.draw()
    elif vida == 0:
        corazones[0].draw()
    else:
        # Buscamos el valor más cercano por debajo o igual
        valores = sorted([k for k in corazones.keys() if k != 5 and k != 0], reverse=True)
        for v in valores:
            if vida >= v:
                corazones[v].draw()
                break
        else:
            # Por si vida < 5 pero > 0 (ej: 3,4,2,1)
            corazones[0].draw()   # o puedes poner corazon_rojo si prefieres

    # Texto para ver el valor exacto (muy útil)
    color_texto = "red" if vida <= 10 else "white"
    screen.draw.text(
        f"VIDA: {vida}",
        center=(WIDTH//2, 80),
        fontsize=48,
        color=color_texto,
        shadow=(1,1),
        scolor="black"
    )


def on_key_down(key):
    global vida
    
    if key == keys.UP:
        vida += 5
    elif key == keys.DOWN:
        vida -= 5
        
    vida = max(0, min(100, vida))


pgzrun.go()