# vida.py
import pgzrun

WIDTH = 900
HEIGHT = 600

vida = 100

# Diccionario con los actores (barras de vida)
barras = {
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
      5: Actor("pixil-frame-19"),     # normal (no rojo)
      0: Actor("pixil-frame-21"),
}

# Actor especial para vida = 5 (rojo)
barra_roja = Actor("pixil-frame-20")

# Posición: esquina superior izquierda + pequeño margen
MARGEN_IZQ = 20
MARGEN_SUP = 20

for barra in barras.values():
    barra.topleft = (MARGEN_IZQ, MARGEN_SUP)

barra_roja.topleft = (MARGEN_IZQ, MARGEN_SUP)


def draw():
    screen.clear()
    
    # Elegimos qué barra mostrar
    if vida == 5:
        barra_roja.draw()
    elif vida == 0:
        barras[0].draw()
    else:
        # Buscamos la barra más cercana por debajo o igual (excepto 5 y 0)
        valores = sorted([k for k in barras if k not in (0,5)], reverse=True)
        for nivel in valores:
            if vida >= nivel:
                barras[nivel].draw()
                break
        else:
            # vida entre 1 y 4 → mostramos la de 0 (o podrías usar roja)
            barras[0].draw()

    # Texto informativo (opcional, pero útil)
    )


def on_key_down(key):
    global vida
    
    if key == keys.UP:
        vida += 5
    if key == keys.DOWN:
        vida -= 5
        
    vida = max(0, min(100, vida))


pgzrun.go()