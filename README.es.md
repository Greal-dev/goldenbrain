# GoldenBrain

[English](README.md) · [Français](README.fr.md) · [Deutsch](README.de.md) · Español

GoldenBrain es una aplicación que funciona en su ordenador: usted confía tareas a asistentes de IA y las sigue todas desde una sola pantalla. Cada tarea es una nota Markdown de su vault (una simple carpeta de notas, con Obsidian o sin él) y su ejecución es una conversación ordinaria de un asistente de IA que ya usa en el terminal — Claude Code, Codex, OpenCode, GitHub Copilot CLI o Antigravity — que puede retomar en cualquier momento. GoldenBrain coloca, pone en cola, supervisa y enlaza estas conversaciones; el agente entrega una ficha breve en la nota, y usted valida.

![Árbol de tareas en cascada, con estado, actividad en directo y motor](docs/captures/arbre-es.png)

![Una tarea: conversación con el agente y notas personales lado a lado](docs/captures/tache-es.png)

![En curso: qué hace cada agente, sus subagentes y su avance](docs/captures/travaux-es.png)

![Segundo cerebro: notas y tareas enlazadas en un grafo](docs/captures/graphe-es.png)

[▶ Vídeo de demostración (unos 40 s)](docs/captures/demo-es.webm)

Las claves de configuración y los documentos de diseño están en francés; este README, la guía de contribución y la política de seguridad existen en cuatro idiomas. Las capturas y el vídeo proceden de un vault de demostración ficticio (`python scripts/captures.py`).

## Instalación rápida

**En un clic — sin terminal ni Python que instalar**

- **Windows**: descargue `GoldenBrain-installation.exe` desde las [versiones](https://github.com/Greal-dev/goldenbrain/releases) y haga doble clic; GoldenBrain se abre al final y después desde el menú Inicio.
- **Debian, Ubuntu**: descargue `goldenbrain_<version>_amd64.deb` y haga doble clic (o `sudo apt install ./goldenbrain_*.deb`); GoldenBrain aparece en el menú de aplicaciones.
- **macOS y otros Linux**: un comando para pegar en un terminal (requiere Git):
  `curl -fsSL https://github.com/Greal-dev/goldenbrain/raw/main/installation/installer.sh | bash`
  En Mac sin terminal: `GoldenBrain-macos-arm64.zip` (Intel: `x86_64`), arrástrelo a Aplicaciones; primera apertura con clic derecho → Abrir (aplicación sin firmar).

Python y sus componentes van incluidos; cada inicio abre GoldenBrain en el navegador y la actualización en un clic sigue activa. Después necesita un vault (basta una carpeta vacía) y un asistente de IA conectado (tabla abajo). Detalles: [guía, « Con un clic »](docs/GUIDE.es.md#en-un-clic).

**Desde el código (desarrolladores)**

Requisitos: Git, Python 3.12 o posterior, un vault Markdown (por defecto `~/Documents/Vault`; basta una carpeta vacía) y al menos un arnés de agente instalado **y con sesión iniciada** (tabla más abajo).

**Linux y macOS**

```bash
git clone https://github.com/Greal-dev/goldenbrain.git goldenbrain && cd goldenbrain
python3 -m venv .venv
.venv/bin/pip install ".[test]"
echo "$PWD/.venv/bin/python" > python.local
./lancer.sh
```

**Windows (PowerShell)**

```powershell
git clone https://github.com/Greal-dev/goldenbrain.git goldenbrain; cd goldenbrain
py -3.12 -m venv .venv
.venv\Scripts\pip install ".[test]"
Set-Content python.local "$PWD\.venv\Scripts\python.exe" -Encoding ascii
.\lancer.cmd
```

Abra después http://127.0.0.1:8300 (quédese en esta dirección: `localhost` también responde, pero el navegador guarda datos distintos por dirección; `lancer.cmd` la abre por usted). El primer arranque crea `config.toml`, que solo contiene sus diferencias; todo lo demás viene de `config.exemple.toml`. Otro vault: en `config.toml`, `[vault]` y luego `racine = "~/ruta/al/vault"`. Otro puerto: `[serveur]` y luego `port = 8301`. El primer inicio abre «Configure su segundo cerebro»: elija la carpeta del vault en la interfaz (un vault de Obsidian existente se usa en su sitio), sin editar ningún archivo.

| Asistente de IA | Instalación (la aplicación puede hacerla) | Inicio de sesión |
|---|---|---|
| Claude Code | `curl -fsSL https://claude.ai/install.sh \| bash` (macOS, Linux) · `irm https://claude.ai/install.ps1 \| iex` (Windows) | `claude`, luego `/login` |
| Codex | `npm install -g @openai/codex` | `codex login` |
| GitHub Copilot CLI | `npm install -g @github/copilot` | `copilot login` |
| OpenCode | `npm install -g opencode-ai` | ver su documentación |
| Antigravity (`agy`) | ver su documentación | desde la aplicación |

La guía completa — primeros pasos, cada pantalla, resolución de problemas, arranque al iniciar sesión con systemd — es [`docs/GUIDE.es.md`](docs/GUIDE.es.md), también en la aplicación (botón « ? ») y con `python orch.py guide`.

## Funciones clave

- **Tareas confiadas a asistentes de IA**: « Nouvelle tâche » (Nueva tarea), un título, « Lancer tout de suite » (Lanzar ya). Asistente y modelo se eligen por tarea; cola, prioridades, requisitos previos y un límite de agentes simultáneos (fijo, o según la memoria libre).
- **Paneles Conversación y Notas**: la tarea muestra la conversación en directo del agente junto a sus notas fechadas, que el agente lee pero nunca escribe. « Interface native du harnais » reabre la misma conversación en un terminal.
- **Yo / IA**: un interruptor en la cabecera de la tarea indica quién la lleva. « Moi » (Yo): ningún agente trabaja en ella; « IA »: « Confier la suite » (Ceder) se la devuelve al agente, con sus notas como contexto.
- **Segundo cerebro y grafo**: recorrer, buscar y editar todo el vault; retroenlaces, menciones no enlazadas, grafo local y global de notas, tareas y proyectos. Un agente jardinero propone movimientos y enlaces; nada cambia sin su clic.
- **Decisiones**: una pantalla para todo lo que le espera — tareas por validar, preguntas de los agentes, propuestas de estructura.
- **Telegram**: envíe un texto, una foto o una nota de voz a su bot; se convierte en una tarea archivada en el lugar adecuado, y el bot puede hacerle preguntas.
- **Teléfono y otros PC**: solo a través de una red privada Tailscale, un teléfono emparejado por código QR accede a la interfaz; otros PC pueden ejecutar agentes para el puesto principal.
- **Rutinas**: una instrucción que un agente ejecuta según un horario (« cada día 08:00 », cron), con historial, pausa y recuperación.
- **Actualización automática**: actualización en un clic que sigue `main` de [github.com/Greal-dev/goldenbrain](https://github.com/Greal-dev/goldenbrain) (solo avance rápido, nunca una fusión), automática si se desea, con vuelta atrás en caso de fallo.

## Pilotar GoldenBrain desde un agente

Cualquier asistente de IA de línea de comandos (Claude Code, Codex, OpenCode…) puede pilotar GoldenBrain mediante `python orch.py` o la API REST local. Lea [`AGENTS.md`](AGENTS.md) y la sección « Pour un agent IA » de la guía: comandos, rutas, reglas y ejemplos de principio a fin.

## Limitaciones conocidas

- Por defecto, los agentes trabajan **sin pedir confirmación** (`--dangerously-skip-permissions` para Claude Code y Antigravity, `--dangerously-bypass-approvals-and-sandbox` para Codex, `--auto` para OpenCode, `--allow-all-tools --no-ask-user` Copilot), desde su carpeta personal salvo que la tarea indique otra: un agente puede leer, modificar o borrar sus archivos. Pruebe primero con una instrucción inocua y lea [SECURITY.md](SECURITY.md) antes de confiarle trabajo real; los argumentos están en `config.exemple.toml`.
- Un solo usuario, un solo puesto: el servidor escucha en `127.0.0.1` sin autenticación. No lo exponga nunca a Internet; el acceso remoto pasa solo por Tailscale.
- Interfaz en francés, inglés, alemán y español; las claves de configuración y los documentos de diseño siguen en francés.
- Windows y Linux (Debian) se usan a diario; macOS debería funcionar pero no se ha probado.
- Usted debe iniciar la sesión del asistente de IA, con su suscripción o clave: GoldenBrain puede ofrecer instalarlo, pero nunca inicia sesión ni paga por usted. Node.js hace falta para los que usan `npm`. El adaptador de Copilot CLI aún no se ha probado con una suscripción real.
- Las pruebas de interfaz (Playwright) no se ejecutan en integración continua; allí solo se ejecuta `python scripts/check.py`.
- GoldenBrain guarda sus datos en la máquina. Solo contacta con GitHub (comprobar actualizaciones y, una vez, ofrecer una estrella), y con Telegram o Microsoft 365 si usted los activa; los asistentes que lanza hablan con sus propios proveedores.

## Para desarrolladores

`CLAUDE.md` (contrato de sesión), `docs/ARCHITECTURE.md` (módulos, invariantes `INV-*`), `docs/CODE_MAP.md`, [`CONTRIBUTING.es.md`](CONTRIBUTING.es.md). Puerta: `python scripts/check.py`; interfaz: `python scripts/check_ui.py`.

## Licencia

GoldenBrain es software de código abierto bajo la [Licencia Apache 2.0](LICENSE); véase también [NOTICE](NOTICE). Las contribuciones son bienvenidas: véanse [CONTRIBUTING.es.md](CONTRIBUTING.es.md) y la [hoja de ruta](ROADMAP.es.md).
