import random

#Constatnts

#Personaje__________________________________________________________________________________________________________________________________________________

# Guerrero/a
GUERRERO_VIDA_MAX           = 90
GUERRERO_DANIO_BASE         = 40
GUERRERO_MANA_MAX           = 30
GUERRERO_MANA_POR_TURNO     = 10
GUERRERO_DANIO_ESPECIAL     = 70
GUERRERO_ATAQUES_POR_TURNO  = 1
GUERRERO_COSTO_ESPECIAL     = 30
GUERRERO_ARMAS              = ["Espada", "Escudo", "Hacha"]
GUERRERO_HABILIDAD          = "Tanquea el 10% de los ataques que recibe"  # reduce 10% daño recibido

# Mago/a
MAGO_VIDA_MAX               = 50
MAGO_DANIO_BASE             = 30
MAGO_MANA_MAX               = 70
MAGO_MANA_POR_TURNO         = 20
MAGO_DANIO_ESPECIAL         = 60
MAGO_ATAQUES_POR_TURNO      = 1
MAGO_COSTO_ESPECIAL         = 60
MAGO_ARMAS                  = ["Vara"]
MAGO_HABILIDAD              = "Magia antigua: La potencia es mayor cuanto menos vida tenga el personaje"

# Arquero/a
ARQUERO_VIDA_MAX            = 40
ARQUERO_DANIO_BASE          = 10
ARQUERO_MANA_MAX            = 40
ARQUERO_MANA_POR_TURNO      = 15
ARQUERO_DANIO_ESPECIAL      = 10
ARQUERO_EFECTO_ESPECIAL     = "quemadura/veneno"
ARQUERO_DANIO_EFECTO_POR_TURNO = 10     # valor sugerido - ajusta según quieras
ARQUERO_DURACION_EFECTO     = 2
ARQUERO_ATAQUES_POR_TURNO   = "randint(1,4)"   # calcular con random cada turno
ARQUERO_COSTO_ESPECIAL      = 40
ARQUERO_ARMAS               = ["Arco", "Ballesta"]
ARQUERO_HABILIDAD           = "Flecha ígnea + Siempre ataca primero"

# Curandero/a
CURANDERO_VIDA_MAX          = 50
CURANDERO_DANIO_BASE        = 20
CURANDERO_MANA_MAX          = 50
CURANDERO_MANA_POR_TURNO    = 20
CURANDERO_DANIO_ESPECIAL    = 20        # daño al enemigo
CURANDERO_CURACION_ESPECIAL = 20        # se cura a sí mismo (estilo absorción)
CURANDERO_ATAQUES_POR_TURNO = 1
CURANDERO_COSTO_ESPECIAL    = 30
CURANDERO_ARMAS             = ["Espada Corta"]
CURANDERO_HABILIDAD         = "Ataque especial como absorción Pokémon (daño + cura igual)"

# Nigromante
NIGROMANTE_VIDA_MAX             = 50
NIGROMANTE_DANIO_BASE           = 10
NIGROMANTE_MANA_MAX             = 80
NIGROMANTE_MANA_POR_TURNO       = 20
NIGROMANTE_DANIO_ESPECIAL       = 60
NIGROMANTE_ATAQUES_POR_TURNO    = "randint(1,5)"
NIGROMANTE_COSTO_ESPECIAL       = 60
NIGROMANTE_ARMAS                = ["Vara", "Varita"]
NIGROMANTE_MAX_ESQUELETOS       = 5
NIGROMANTE_ATAQUE_ESPECIAL_NOMBRE = "Death End"
NIGROMANTE_HABILIDAD            = "Si no le bajas el 25% de la vida en X tiempo → pierdes"

# Hechicero/a
HECHICERO_VIDA_MAX          = 50
HECHICERO_DANIO_BASE        = 30
HECHICERO_MANA_MAX          = 70
HECHICERO_MANA_POR_TURNO    = 30
HECHICERO_DANIO_ESPECIAL    = 70
HECHICERO_ATAQUES_POR_TURNO = 1
HECHICERO_COSTO_ESPECIAL    = 70
HECHICERO_ARMAS             = ["Grimorio"]
HECHICERO_HABILIDAD         = "Invoca un esqueleto gigante que aporta +50 de vida"

# Caballero/a
CABALLERO_VIDA_MAX          = 70
CABALLERO_DANIO_BASE        = 50
CABALLERO_MANA_MAX          = 40
CABALLERO_MANA_POR_TURNO    = 10
CABALLERO_DANIO_ESPECIAL    = 60
CABALLERO_ATAQUES_POR_TURNO = 1
CABALLERO_COSTO_ESPECIAL    = 40
CABALLERO_ARMAS             = ["Espada", "Lanza"]
CABALLERO_HABILIDAD         = "Embestida con la espada + Puede copiar estadísticas del rival"

# Cazador/a
CAZADOR_VIDA_MAX            = 60
CAZADOR_DANIO_BASE          = 50
CAZADOR_MANA_MAX            = 30
CAZADOR_MANA_POR_TURNO      = 10
CAZADOR_DANIO_ESPECIAL      = 30
CAZADOR_EFECTO_ESPECIAL     = "represalia"
CAZADOR_DURACION_REPRESALIA = 1
CAZADOR_ATAQUES_POR_TURNO   = 1
CAZADOR_COSTO_ESPECIAL      = 30
CAZADOR_ARMAS               = ["Escopeta"]
CAZADOR_HABILIDAD           = "Retiene al oponente e inhabilita su ataque 1 turno"

# Asesino/a
ASESINO_VIDA_MAX            = 50
ASESINO_DANIO_BASE          = 20
ASESINO_MANA_MAX            = 20
ASESINO_MANA_POR_TURNO      = 10
ASESINO_DANIO_ESPECIAL      = 60
ASESINO_ATAQUES_POR_TURNO   = "randint(1,3)"
ASESINO_COSTO_ESPECIAL      = 20
ASESINO_ARMAS               = ["Daga", "Espada Corta"]
ASESINO_HABILIDAD           = "Concede la muerte + Daño básico ×2 si rival está paralizado"

# Bárbaro/a
BARBARO_VIDA_MAX            = 60
BARBARO_DANIO_BASE          = 50
BARBARO_MANA_MAX            = 30
BARBARO_MANA_POR_TURNO      = 5
BARBARO_DANIO_ESPECIAL      = 70
BARBARO_ATAQUES_POR_TURNO   = 1
BARBARO_COSTO_ESPECIAL      = 30
BARBARO_ARMAS               = ["Espada", "Escudo", "Hacha", "Maza"]
BARBARO_HABILIDAD           = "Abocajarro + Triplica su carga de mana"




# Enemigos_____________________________________________________________________________________________________________________

# Bandido
BANDIDO_VIDA_MAX          = 60
BANDIDO_DANIO_BASE        = 20
BANDIDO_TIER              = "Base"
BANDIDO_ATAQUES_POR_TURNO = 1
BANDIDO_DANIO_ESPECIAL    = 0       # no tiene
BANDIDO_COOLDOWN_ESPECIAL = 0       # no tiene
BANDIDO_HABILIDAD_ESPECIAL = None

# Slime
SLIME_VIDA_MAX          = 90
SLIME_DANIO_BASE        = 5
SLIME_TIER              = "Base"
SLIME_ATAQUES_POR_TURNO = 2
SLIME_DANIO_ESPECIAL    = 0
SLIME_COOLDOWN_ESPECIAL = 0
SLIME_HABILIDAD_ESPECIAL = None

# Duende
DUENDE_VIDA_MAX          = 50
DUENDE_DANIO_BASE        = 15
DUENDE_TIER              = "Base"
DUENDE_ATAQUES_POR_TURNO = 2
DUENDE_DANIO_ESPECIAL    = 0
DUENDE_COOLDOWN_ESPECIAL = 0
DUENDE_HABILIDAD_ESPECIAL = None

# Esqueleto
ESQUELETO_VIDA_MAX          = 70
ESQUELETO_DANIO_BASE        = 25
ESQUELETO_TIER              = "Base"
ESQUELETO_ATAQUES_POR_TURNO = 1
ESQUELETO_DANIO_ESPECIAL    = 0
ESQUELETO_COOLDOWN_ESPECIAL = 0
ESQUELETO_HABILIDAD_ESPECIAL = None

# Zombie
ZOMBIE_VIDA_MAX          = 80
ZOMBIE_DANIO_BASE        = 10
ZOMBIE_TIER              = "Base"
ZOMBIE_ATAQUES_POR_TURNO = 1
ZOMBIE_DANIO_ESPECIAL    = 0
ZOMBIE_COOLDOWN_ESPECIAL = 0
ZOMBIE_HABILIDAD_ESPECIAL = None

# Orco
ORCO_VIDA_MAX          = 70
ORCO_DANIO_BASE        = 30
ORCO_TIER              = "Base"
ORCO_ATAQUES_POR_TURNO = 1
ORCO_DANIO_ESPECIAL    = 0
ORCO_COOLDOWN_ESPECIAL = 0
ORCO_HABILIDAD_ESPECIAL = None

# Lobo
LOBO_VIDA_MAX          = 60
LOBO_DANIO_BASE        = 15
LOBO_TIER              = "Base"
LOBO_ATAQUES_POR_TURNO = "randint(1,2)"   # se calcula cada turno
LOBO_DANIO_ESPECIAL    = 0
LOBO_COOLDOWN_ESPECIAL = 0
LOBO_HABILIDAD_ESPECIAL = None

# Oso
OSO_VIDA_MAX          = 75
OSO_DANIO_BASE        = 35
OSO_TIER              = "Base"
OSO_ATAQUES_POR_TURNO = 1
OSO_DANIO_ESPECIAL    = 0
OSO_COOLDOWN_ESPECIAL = 0
OSO_HABILIDAD_ESPECIAL = None

# Ogro
OGRO_VIDA_MAX          = 90
OGRO_DANIO_BASE        = 30
OGRO_TIER              = "Especial"
OGRO_ATAQUES_POR_TURNO = 1
OGRO_DANIO_ESPECIAL    = 0   # (puedes poner valor si decides agregarlo después)
OGRO_COOLDOWN_ESPECIAL = 0
OGRO_HABILIDAD_ESPECIAL = None

# Troll
TROLL_VIDA_MAX          = 100
TROLL_DANIO_BASE        = 35
TROLL_TIER              = "Especial"
TROLL_ATAQUES_POR_TURNO = 1
TROLL_DANIO_ESPECIAL    = 0
TROLL_COOLDOWN_ESPECIAL = 0
TROLL_HABILIDAD_ESPECIAL = None

# Gigante
GIGANTE_VIDA_MAX          = 110
GIGANTE_DANIO_BASE        = 45
GIGANTE_TIER              = "Especial"
GIGANTE_ATAQUES_POR_TURNO = 1
GIGANTE_DANIO_ESPECIAL    = 0
GIGANTE_COOLDOWN_ESPECIAL = 0
GIGANTE_HABILIDAD_ESPECIAL = None

# Cíclope
CLOPE_VIDA_MAX          = 80
CLOPE_DANIO_BASE        = 40
CLOPE_TIER              = "Especial"
CLOPE_ATAQUES_POR_TURNO = 1
CLOPE_DANIO_ESPECIAL    = 0
CLOPE_COOLDOWN_ESPECIAL = 0
CLOPE_HABILIDAD_ESPECIAL = None

# Golem
GOLEM_VIDA_MAX             = 180
GOLEM_DANIO_BASE           = 50
GOLEM_TIER                 = "Superior"
GOLEM_ATAQUES_POR_TURNO    = 1
GOLEM_DANIO_ESPECIAL       = 10     # ejemplo (puedes cambiar)
GOLEM_COOLDOWN_ESPECIAL    = 3
GOLEM_HABILIDAD_ESPECIAL   = "paraliza 1 turno"
GOLEM_HABILIDAD_DESC       = "Saca un diamante brillante y paraliza al rival 1 turno"

# Hombre Lobo
HOMBRE_LOBO_VIDA_MAX          = 90
HOMBRE_LOBO_DANIO_BASE        = 30
HOMBRE_LOBO_TIER              = "Especial"
HOMBRE_LOBO_ATAQUES_POR_TURNO = "randint(1,3)"
HOMBRE_LOBO_DANIO_ESPECIAL    = 0
HOMBRE_LOBO_COOLDOWN_ESPECIAL = 0
HOMBRE_LOBO_HABILIDAD_ESPECIAL = None

# Vampiro
VAMPIRO_VIDA_MAX             = 125
VAMPIRO_DANIO_BASE           = 20
VAMPIRO_TIER                 = "Superior"
VAMPIRO_ATAQUES_POR_TURNO    = "randint(1,2)"
VAMPIRO_DANIO_ESPECIAL       = 60
VAMPIRO_COOLDOWN_ESPECIAL    = 3
VAMPIRO_HABILIDAD_ESPECIAL   = "chupa vida"

# Alto Orco
ALTO_ORCO_VIDA_MAX          = 150
ALTO_ORCO_DANIO_BASE        = 50
ALTO_ORCO_TIER              = "Superior"
ALTO_ORCO_ATAQUES_POR_TURNO = 1
ALTO_ORCO_DANIO_ESPECIAL    = 70
ALTO_ORCO_COOLDOWN_ESPECIAL = 4
ALTO_ORCO_HABILIDAD_ESPECIAL = "mazazo"

# Quimera
QUIMERA_VIDA_MAX          = 80
QUIMERA_DANIO_BASE        = 20
QUIMERA_TIER              = "Especial"
QUIMERA_ATAQUES_POR_TURNO = 1
QUIMERA_DANIO_ESPECIAL    = 0
QUIMERA_COOLDOWN_ESPECIAL = 0
QUIMERA_HABILIDAD_ESPECIAL = None

# Elfo Oscuro
ELFO_OSCURO_VIDA_MAX             = 150
ELFO_OSCURO_DANIO_BASE           = 60
ELFO_OSCURO_TIER                 = "Superior"
ELFO_OSCURO_ATAQUES_POR_TURNO    = 1
ELFO_OSCURO_DANIO_ESPECIAL       = 90
ELFO_OSCURO_COOLDOWN_ESPECIAL    = 3
ELFO_OSCURO_HABILIDAD_ESPECIAL   = "parálisis (1 turno) + golpe"

# Demonio Inferior
DEMONIO_INFERIOR_VIDA_MAX          = 90
DEMONIO_INFERIOR_DANIO_BASE        = 20
DEMONIO_INFERIOR_TIER              = "Especial"
DEMONIO_INFERIOR_ATAQUES_POR_TURNO = "randint(1,2)"
DEMONIO_INFERIOR_DANIO_ESPECIAL    = 0
DEMONIO_INFERIOR_COOLDOWN_ESPECIAL = 0
DEMONIO_INFERIOR_HABILIDAD_ESPECIAL = None

# Demonio Superior
DEMONIO_SUPERIOR_VIDA_MAX             = 150
DEMONIO_SUPERIOR_DANIO_BASE           = 60
DEMONIO_SUPERIOR_TIER                 = "Superior"
DEMONIO_SUPERIOR_ATAQUES_POR_TURNO    = 1
DEMONIO_SUPERIOR_DANIO_ESPECIAL       = 60
DEMONIO_SUPERIOR_COOLDOWN_ESPECIAL    = 3
DEMONIO_SUPERIOR_HABILIDAD_ESPECIAL   = "reduce capacidad de absorber mana por turno del rival"

# Rey Demonio
REY_DEMONIO_VIDA_MAX             = 350
REY_DEMONIO_DANIO_BASE           = 70
REY_DEMONIO_TIER                 = "Boss"
REY_DEMONIO_ATAQUES_POR_TURNO    = 1
REY_DEMONIO_DANIO_ESPECIAL       = 100
REY_DEMONIO_COOLDOWN_ESPECIAL    = 3
REY_DEMONIO_HABILIDAD_ESPECIAL   = "invoca demonios (cada 3 inferiores invoca 1 superior)"

# Leviatan
LEVIATAN_VIDA_MAX             = 250
LEVIATAN_DANIO_BASE           = 80
LEVIATAN_TIER                 = "Élite"
LEVIATAN_ATAQUES_POR_TURNO    = 1
LEVIATAN_DANIO_ESPECIAL       = 0     # o valor si lo defines
LEVIATAN_COOLDOWN_ESPECIAL    = 3
LEVIATAN_HABILIDAD_ESPECIAL   = "grito ensordecedor (50% parálisis)"

# Rey Esqueleto
REY_ESQUELETO_VIDA_MAX             = 230
REY_ESQUELETO_DANIO_BASE           = 80
REY_ESQUELETO_TIER                 = "Élite"
REY_ESQUELETO_ATAQUES_POR_TURNO    = 1
REY_ESQUELETO_DANIO_ESPECIAL       = 0
REY_ESQUELETO_COOLDOWN_ESPECIAL    = 2
REY_ESQUELETO_HABILIDAD_ESPECIAL   = "invoca esqueletos randint(1,3)"

# Kraken
KRAKEN_VIDA_MAX             = 400
KRAKEN_DANIO_BASE           = 70
KRAKEN_TIER                 = "Boss"
KRAKEN_ATAQUES_POR_TURNO    = 1
KRAKEN_DANIO_ESPECIAL       = 120   # ejemplo
KRAKEN_COOLDOWN_ESPECIAL    = 3
KRAKEN_HABILIDAD_ESPECIAL   = "tentaclazo"

# Dragón
DRAGON_VIDA_MAX             = 250
DRAGON_DANIO_BASE           = 80
DRAGON_TIER                 = "Élite"
DRAGON_ATAQUES_POR_TURNO    = 1
DRAGON_DANIO_ESPECIAL       = 60
DRAGON_COOLDOWN_ESPECIAL    = 3
DRAGON_HABILIDAD_ESPECIAL   = "quemadura"

# Monarca de los Dragones
MONARCA_DRAGONES_VIDA_MAX             = 500
MONARCA_DRAGONES_DANIO_BASE           = 90
MONARCA_DRAGONES_TIER                 = "Final Boss"
MONARCA_DRAGONES_ATAQUES_POR_TURNO    = 1
MONARCA_DRAGONES_DANIO_ESPECIAL       = 150  # ejemplo
MONARCA_DRAGONES_COOLDOWN_ESPECIAL    = 5
MONARCA_DRAGONES_HABILIDAD_ESPECIAL   = "invoca dragones"


#Graphics_________________________________
print("Welcome")