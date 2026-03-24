Aquí tienes el README actualizado con la licencia personalizada:

```markdown
# 🗡️ The Return to Highdown
### Un MUD Multiplayer en Tiempo Real

[![Jugar Ahora](https://img.shields.io/badge/JUGAR%20AHORA-En%20Render-brightgreen?style=for-the-badge)](https://the-return-to-highdown.onrender.com)
[![Python](https://img.shields.io/badge/Python-3.11-blue?style=for-the-badge&logo=python)](https://python.org)
[![WebSocket](https://img.shields.io/badge/Real--Time-WebSocket-orange?style=for-the-badge)](https://developer.mozilla.org/es/docs/Web/API/WebSocket)

---

## 🎮 ¿Qué es?

**The Return to Highdown** es un MUD (Multi-User Dungeon) multiplayer donde exploras un mundo de fantasía peligroso, luchas contra monstruos épicos, subes de nivel y formas grupos con otros jugadores en tiempo real.

Explora tres reinos mortales: el **Desierto Ardiente**, el **Mar Tormentoso** y las **Tierras de Hielo Eterno**. Enfréntate al **Rey Demonio**, el **Kraken** y el temible **Alpha** en la cumbre del mundo.

---

## 🚀 Cómo Jugar

### Opción 1: Navegador Web (Recomendado)
👉 **[Haz clic aquí para jugar](https://the-return-to-highdown.onrender.com)**

- Interfaz gráfica con chat en tiempo real
- Inventario visual
- Barras de HP/Mana en vivo
- Sistema de combate interactivo

### Opción 2: Terminal (Cliente Python)
```bash
git clone https://github.com/tu-usuario/the-return-to-highdown.git
cd the-return-to-highdown
pip install websockets
python client.py the-return-to-highdown.onrender.com
```

---

## 🕹️ Controles y Comandos

### Movimiento
- `norte`, `sur`, `este`, `oeste` - Moverse entre salas
- `mapa` - Ver mapa de la zona actual

### Combate
- `1` - Atacar
- `2` - Ataque Especial (consume mana)
- `3` - Pasar turno
- `4` - Usar objeto

### Comunicación
- `decir <mensaje>` - Hablar en la sala actual
- `g <mensaje>` - Chat global (todos los jugadores)
- `grupo <mensaje>` - Hablar con tu grupo/party

### Sistema de Grupos
- `grupo crear` - Crear un grupo
- `grupo invitar <jugador>` - Invitar a un jugador
- `grupo unirse <líder>` - Unirse a un grupo
- `grupo salir` - Abandonar grupo
- `grupo disolver` - Disolver el grupo (líder)

### Inventario y Tienda
- `inventario` - Ver objetos
- `usar <objeto>` - Usar ítem
- `comprar <objeto>` - Comprar en tienda (solo en Oasis/Puerto)
- `tienda` - Ver catálogo

### Información
- `estado` - Ver HP, Mana, Nivel, XP
- `limpiar` - Limpiar pantalla
- `salir` - Desconectar

---

## ⚔️ Clases Disponibles

| Clase | HP | Daño | Mana | Especial | Estilo |
|-------|-----|------|------|----------|---------|
| **🛡️ Guerrero** | 90 | 40 | 30 | Golpe Tanque | Tanque/DPS |
| **🔥 Mago** | 50 | 30 | 70 | Magia Antigua | DPS Mágico |
| **🏹 Arquero** | 40 | 10 | 40 | Flecha Ígnea | DPS Rango/Múltiples ataques |
| **💚 Curandero** | 50 | 20 | 50 | Absorción | Soporte/Sanación |
| **💀 Nigromante** | 50 | 10 | 80 | Maldición Tiempo | DPS/Múltiples ataques |
| **👁️ Hechicero** | 50 | 30 | 70 | Invocar Esqueleto | Invocador |
| **⚔️ Caballero** | 70 | 50 | 40 | Embestida | DPS/Tanque |
| **🎯 Cazador** | 60 | 50 | 30 | Inmovilizar | Control/DPS |
| **🗡️ Asesino** | 50 | 20 | 20 | Muerte Garantizada | Alto daño crítico |
| **🪓 Bárbaro** | 60 | 50 | 30 | Abocajarro | DPS Bruto |

---

## 🌍 El Mundo

### 🏜️ Desierto (Salas 1-5)
- **Dificultad:** Fácil/Base
- **Enemigos:** Bandidos, Duendes, Esqueletos, Demonios Inferiores
- **Boss:** 👹 **Rey Demonio** (Sala 5)
- **Transición:** Oasis (Sala 6) - Zona segura con tienda

### 🌊 Mar (Salas 10-14)
- **Dificultad:** Media/Especial
- **Enemigos:** Tiburones, Hombres Lobo, Vampiros, Trolls
- **Boss:** 🐙 **Kraken** (Sala 14)
- **Transición:** Puerto Abandonado (Sala 15) - Zona segura

### ❄️ Nieve (Salas 20-24)
- **Dificultad:** Difícil/Superior-Élite
- **Enemigos:** Gigantes, Golems, Elfos Oscuros, Reyes Esqueleto
- **Boss Final:** 🐺 **Alpha** (Sala 24) - ¡El desafío definitivo!

---

## 💡 Tips para Sobrevivir

1. **Agrúpate:** Los combates en grupo son más fáciles y todos reciben XP
2. **Gestiona tu mana:** Los ataques especiales son poderosos pero costosos
3. **Usa pociones:** La Poción de Daño (+30% daño) es clave para bosses
4. **Descansa en Oasis:** Recupera HP gratis en las salas seguras (6 y 15)
5. **Limpia salas:** Una vez derrotados los enemigos de una sala, queda limpia para siempre
6. **Estrategia de clases:** Los tanques (Guerrero/Caballero) absorben daño mientras los DPS (Mago/Arquero) atacan desde atrás

---

## 🏆 Sistema de Progresión

- **XP por combate:** Depende del tier de los enemigos (Base: 10, Especial: 30, Superior: 50, Élite: 100, Boss: 250)
- **Subida de nivel:** Cada nivel requiere más XP (base 150 + 20 por nivel)
- **Recompensas:** +20 monedas y full HP al subir de nivel
- **Post-combate:** +20 HP automático para sobrevivientes

---

## 🛠️ Tecnologías

- **Backend:** Python 3.11 + asyncio
- **Web:** aiohttp (HTTP) + websockets (WS)
- **Frontend:** HTML5 + CSS3 + JavaScript vanilla
- **Base de datos:** Supabase (PostgreSQL) o JSON local
- **Deploy:** Render

---

## 📜 Licencia

**The Return to Highdown – Licencia personalizada (propietaria)**

Copyright © 2025–2026 Marcel Verhoeven Corella, Daniel Serrano Saz, Arnau Moyano Forné

### Se permite:
• Descargar el proyecto  
• Ejecutarlo para uso personal o privado  
• Modificarlo para uso personal o privado (sin compartirlo)

### Obligaciones:
• Mantener intactos los créditos y copyright original en todo momento  
• Indicar siempre que el trabajo original fue creado por Marcel Verhoeven Corella, Daniel Serrano Saz y Arnau Moyano Forné

### Está estrictamente prohibido:
• Distribuir, compartir, subir a internet, publicar o entregar copias (originales o modificadas) a terceros sin permiso escrito expreso de los autores  
• Vender, licenciar comercialmente, monetizar o usar el proyecto (o derivados) con fines comerciales  
• Eliminar, ocultar o modificar los créditos de los autores originales

EL SOFTWARE SE PROPORCIONA "TAL CUAL", SIN NINGUNA GARANTÍA.
LOS AUTORES NO SERÁN RESPONSABLES DE NINGÚN DAÑO O PROBLEMA DERIVADO DE SU USO.

---

**🎮 [Jugar Ahora - The Return to Highdown](https://the-return-to-highdown.onrender.com)**

*¡Que los dioses antiguos te acompañen en tu viaje!*
```
