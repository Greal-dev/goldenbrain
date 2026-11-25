# Guía de GoldenBrain

Actualizado el 2026-11-24.

GoldenBrain es un puesto de mando: usted confía tareas a agentes de IA (Claude Code, Codex, OpenCode, Copilot, Antigravity), cada una guardada en su lugar dentro de su vault (una carpeta de notas en Markdown). GoldenBrain organiza y supervisa; el agente trabaja en su propia conversación, que usted puede retomar en cualquier momento.

Esta guía se lee en la aplicación (botón «?» arriba a la derecha), en la carpeta del código (`docs/GUIDE.md`) o por medio de un agente (`python orch.py guide`). Cada sección responde a tres preguntas: para qué sirve, cómo se hace, qué conviene saber. En la aplicación, el campo «Buscar en la guía» solo conserva las secciones que contienen la palabra; el «?» junto al título de Ajustes, Equipo y Decisiones abre directamente su sección; una sección se comparte mediante su enlace (`#guide=reglages`).

## Instalar {#installer}

Hay dos vías: **con un clic** (sin símbolo del sistema ni Python que instalar: todo viene incluido), o **a mano** desde el código (Linux y Windows, más abajo). En ambos casos hace falta después un vault (una carpeta de notas en Markdown, con Obsidian o sin él; GoldenBrain arranca sin vault) y al menos un asistente de IA (véase «Conectar los asistentes de IA»).

### Con un clic {#en-un-clic}

Para qué sirve: instalar GoldenBrain como una aplicación corriente. Python, sus componentes y (en Windows) Git van incluidos; no se modifica nada más en el ordenador y no se piden derechos de administrador (salvo el paquete .deb, que instala la tienda de software).

- **Windows**: descargue `GoldenBrain-installation.exe` (página de versiones de GoldenBrain en GitHub), haga doble clic y siga las tres pantallas. GoldenBrain se inicia al terminar y después desde el menú Inicio. Windows puede advertir «editor desconocido» (instalador sin firmar): pulse «Más información» y luego «Ejecutar de todas formas».
- **Linux (Debian, Ubuntu)**: descargue `goldenbrain_<versión>_amd64.deb`, haga doble clic (tienda de software) o ejecute `sudo apt install ./goldenbrain_*.deb`. GoldenBrain aparece en el menú de aplicaciones y también se inicia con el comando `goldenbrain`.
- **Linux (otras distribuciones) y macOS**: copie y pegue en un símbolo del sistema (Terminal en macOS), una sola vez:
  `curl -fsSL https://github.com/Greal-dev/goldenbrain/raw/main/installation/installer.sh | bash`
  La instalación dura dos o tres minutos, crea la entrada de menú (Linux) o `GoldenBrain` en la carpeta Aplicaciones de su cuenta (macOS) y después inicia GoldenBrain. Se necesita Git: en macOS, acepte las herramientas que proponga el sistema y vuelva a ejecutar el comando.
- **macOS, sin símbolo del sistema**: descargue `GoldenBrain-macos-arm64.zip` (Mac recientes; `x86_64` para los Mac Intel), ábralo y arrastre GoldenBrain a Aplicaciones. Como la aplicación no está firmada, el primer inicio se hace con clic derecho → Abrir (o Ajustes del Sistema → Privacidad y seguridad → «Abrir igualmente»).

Cómo funciona: cada inicio abre el navegador en GoldenBrain, arrancando GoldenBrain en este ordenador si aún no está en marcha (un segundo clic no arranca un segundo GoldenBrain). En el primer inicio, la aplicación se copia en su carpeta personal (`~/.local/share/goldenbrain/app`, `~/Library/Application Support/GoldenBrain/app` o `%LOCALAPPDATA%\GoldenBrain\app`): esa copia es la que hace avanzar la «Actualización con un clic», y conserva sus ajustes (`config.toml`).

Conviene saber: la instalación habla el idioma del sistema (francés, inglés, alemán o español; inglés para cualquier otro idioma) y, en el primer inicio, lo anota en `config.toml` (`[interface] langue`) para que GoldenBrain se abra en el mismo idioma; un `config.toml` existente nunca se modifica. Reinstalar o desinstalar nunca toca esa copia ni el vault. El registro del arranque es `lancement.log`, en la carpeta de datos (Linux, macOS). Para construir usted mismo los instaladores: `python scripts/construire_deb.py`, `construire_windows.py` (Inno Setup bajo wine), `construire_macos.py`; cada componente descargado se verifica por su huella (`installation/versions.txt`). Cada versión publicada en la página de versiones incluye los cuatro instaladores, reconstruidos cada vez, y una nota en inglés, francés, español y alemán (`python scripts/publier_version.py`, lanzado por la publicación).

### Linux {#linux}

A mano, desde el código (desarrolladores). Se necesitan Git y Python 3.12 o posterior.


1. Requisitos previos (Debian, Ubuntu): `sudo apt install git python3 python3-venv`
2. Obtener el código: `git clone https://github.com/Greal-dev/goldenbrain.git ~/goldenbrain && cd ~/goldenbrain`
3. Python dedicado: `python3 -m venv ~/.venvs/goldenbrain`
4. Dependencias: `~/.venvs/goldenbrain/bin/pip install fastapi uvicorn pyyaml` (desarrolladores, para las pruebas: `pip install ".[test]"`)
5. Designar ese Python: `echo ~/.venvs/goldenbrain/bin/python > python.local`
6. Primer inicio: `./lancer.sh`, y después abrir http://127.0.0.1:8300

El primer inicio crea `config.toml`, que solo contiene sus diferencias (todo lo demás viene de `config.exemple.toml`).

### Windows {#windows}

A mano, desde el código (desarrolladores).

1. Instalar Git y Python 3.12 (python.org); anotar la ruta de `python.exe`.
2. Obtener el código: `git clone https://github.com/Greal-dev/goldenbrain.git goldenbrain`
3. Dependencias: `python -m pip install fastapi uvicorn pyyaml` (desarrolladores, para las pruebas: `pip install ".[test]"`)
4. Si el `python` del PATH no es el intérprete correcto, escribir su ruta completa en la primera línea de un archivo `python.local` en la raíz de la carpeta.
5. Primer inicio: doble clic en `lancer.cmd`. Se abre la página http://127.0.0.1:8300.

### Dónde está el vault

Por defecto: `~/Documents/Vault`. Si está en otro sitio, escríbalo en `config.toml`:

```toml
[vault]
racine = "~/chemin/vers/mon-vault"
```

**Sin tocar ese archivo**: en el primer inicio, antes de cualquier otra pantalla, GoldenBrain abre «Configure su segundo cerebro» a pantalla completa. Allí elige la carpeta (escribirla o «Examinar» para recorrer sus carpetas): un vault Markdown u Obsidian existente se usa en su sitio, sin copia; una carpeta inexistente o vacía se convierte en un segundo cerebro nuevo, creado solo al validar. Una carpeta inexistente, no escribible o relativa, o ya servida por otra instancia, se rechaza con el motivo. Cambiar de carpeta reescribe solo la clave `[vault] racine` de `config.toml`; luego GoldenBrain se reinicia solo sobre el nuevo vault, y si conserva la carpeta actual no se reinicia nada. Siguen la elección del asistente de IA y la propuesta de roles y proyectos (o la demostración); nada se escribe antes de su validación. «Más tarde» deja un aviso «Segundo cerebro por configurar». Para reabrirlo: Ajustes → «Instalación y versión» → «Reconfigurar mi segundo cerebro».

Un vault de Obsidian existente sirve tal cual: apunte `racine` hacia él (véase «Organizar su segundo cerebro»). Una carpeta vacía o inexistente recibe, en la bienvenida y tras su aprobación, una clasificación inicial.

Puerto ocupado: `[serveur]` y luego `port = 8301`. Reinicie tras cada cambio de `config.toml`.

### Servicio al arrancar (Linux) {#service-au-demarrage-linux}

GoldenBrain arranca solo con la sesión y se reinicia tras una actualización.

```bash
mkdir -p ~/.config/systemd/user
cat > ~/.config/systemd/user/goldenbrain.service <<'FIN'
[Unit]
Description=GoldenBrain

[Service]
WorkingDirectory=%h/goldenbrain
ExecStart=/bin/bash lancer.sh
Restart=on-failure

[Install]
WantedBy=default.target
FIN
systemctl --user daemon-reload
systemctl --user enable --now goldenbrain
```

- Arrancar incluso sin abrir sesión: `loginctl enable-linger "$USER"`.
- Registro: `journalctl --user -u goldenbrain -f`. Parada: `systemctl --user stop goldenbrain`.
- `WorkingDirectory` debe designar la carpeta del código (`%h` = su carpeta personal).

### Conectar los asistentes de IA {#connecter-les-harnais}

Un asistente de IA es el programa, usado desde un símbolo del sistema, que hace trabajar al agente. GoldenBrain lo busca en el PATH; hace falta al menos uno, instalado **y conectado**.

| Asistente de IA | Instalar | Iniciar sesión |
|---|---|---|
| Claude Code | `curl -fsSL https://claude.ai/install.sh \| bash` (macOS, Linux) · `irm https://claude.ai/install.ps1 \| iex` (Windows) | `claude`, y después `/login` |
| Codex | `npm install -g @openai/codex` | `codex login` |
| GitHub Copilot CLI | `npm install -g @github/copilot` | `copilot login` |
| OpenCode | `npm install -g opencode-ai` | véase su documentación |
| Antigravity (`agy`) | véase su documentación | desde la aplicación |

Conviene saber: un asistente de IA ausente aparece como «no disponible», con el motivo, en la elección del «Motor» de una tarea. Su ruta o sus argumentos se ajustan en `config.toml`, sección `[harnais.<nombre>]` (modelo: `config.exemple.toml`).

Conviene saber: Node.js hace falta para las instalaciones con `npm`; la aplicación propone instalarlos (pantalla de inicio) y nunca inicia sesión por usted.

**Atención — sin confirmación**: por defecto GoldenBrain lanza los agentes con los argumentos que suprimen toda petición de permiso (`--dangerously-skip-permissions` para Claude Code y Antigravity, `--dangerously-bypass-approvals-and-sandbox` para Codex, `--auto` para OpenCode, `--allow-all-tools --no-ask-user` para Copilot), desde su carpeta personal salvo que la tarea indique otra. Un agente puede, pues, leer, modificar o borrar sus archivos sin preguntar. Pruebe primero con una instrucción inocua; estos argumentos se cambian en `config.toml` (`[harnais.<nombre>]`, modelo: `config.exemple.toml`); véase `SECURITY.md`.

## Primeros pasos {#premiers-pas}

Diez minutos, sin configurar nada más.

0. **En el primerísimo inicio**, se abre una ventana «Bienvenido a GoldenBrain» en dos pasos. *Su asistente de IA*: la lista de los asistentes de IA reconocidos (Claude Code, Codex, Copilot, OpenCode, Antigravity), cada uno «listo», «instalado, falta iniciar sesión» o «no instalado». Para un asistente ausente, «Cómo instalarlo» da la página oficial y el comando que hay que copiar en un símbolo del sistema (botón «Copiar»); instálelo y luego pulse «Comprobar de nuevo». GoldenBrain no instala nada por sí mismo. *Primera tarea*: «Iniciar la demostración» crea e inicia una pequeña tarea (el asistente se presenta y propone tres ideas, sin modificar nada en el equipo); la respuesta suele llegar en uno o dos minutos. «Omitir» o «Más tarde» cierra la ventana y abre la bienvenida. Para volver a verla: Ajustes → «Instalación y versión» → «Repetir los primeros pasos».
1. **Crear una tarea**: «Nueva tarea» (arriba). Basta un título; la descripción ayuda al agente. Al principio del formulario hay **plantillas listas para usar** (crear un pequeño sitio web, analizar una hoja de Excel o CSV, redactar una carta, automatizar una tarea repetitiva, resumir documentos, aprender un concepto): un clic rellena el título y la descripción, que quedan por completar en los lugares marcados «[por completar]»; no se crea nada antes de «Crear». Para añadir una plantilla: deposite un archivo `.md` en la carpeta `modeles/` de GoldenBrain (encabezado `titre`, `resume`, `ordre`; el texto de debajo es la misión). Para adaptar una plantilla incluida, cópiela con otro nombre: una actualización puede reemplazar los archivos incluidos. Proyecto: deje «Entrada (por defecto)» si no sabe dónde guardarla. Mientras escribe, se muestran las tareas abiertas parecidas: «Completar esta» añade su petición a la existente en lugar de crear otra; si ya existe una tarea muy parecida, la creación se rechaza con suavidad y «Crear de todos modos» la fuerza.
2. **Iniciarla**: marque «Iniciar de inmediato» al crearla, o escriba un primer mensaje al pie de la tarea (Ctrl+Intro lo envía).
3. **Seguir la conversación**: la tarea se abre a la derecha; las respuestas del agente aparecen en directo. La barra superior enumera las sesiones de trabajo en curso y en cola.
4. **Responder o corregir**: escriba al pie; la misma conversación continúa.
5. **Aprobar**: cuando el agente se declara «Terminada», la tarea espera su «Validar» o «Devolver…» (con un motivo que se transmite al agente).
6. **Decisiones**: el botón «Decisiones» (arriba) reúne todo lo que espera su gesto: tareas por aprobar, preguntas de los agentes, propuestas de organización y de enlaces, incluidas las del jardinero (la revisión de coherencia: solo propone, nunca escribe por su cuenta; `plafond` en `[jardinage]` limita su número por pasada, 7 por defecto).

Conviene saber: una instalación nueva está en modo **Simple** (proyectos, tareas, conversación, estado, aprobar). Ajustes → «Avanzado» muestra todo lo demás.

## Organizar su segundo cerebro {#organiser-votre-second-cerveau}

El vault es su **segundo cerebro**: notas corrientes (archivos Markdown) que GoldenBrain, usted y la IA leen y enriquecen. Se ordena en tres niveles: **roles → proyectos → tareas**.

- **Roles («casquettes»)**: sus grandes ámbitos de vida, pocos y duraderos. Ejemplo: «Trabajo», «Familia», «Asociación del barrio».
- **Proyectos**: un resultado que lograr dentro de un rol, con un final. Ejemplo: bajo «Familia», «Mudanza»; bajo «Trabajo», «Sitio web del despacho». Varios proyectos de un mismo rol se agrupan, si hace falta, en una **operación** («Curso 2027»).
- **Tareas**: una acción concreta dentro de un proyecto, confiada a la IA o a usted mismo. Ejemplo: «Comparar tres presupuestos de empresas de mudanzas». Una tarea que crece se convierte en proyecto.

**Las carpetas del vault inicial** (las crea la bienvenida si el vault está vacío, tras su aprobación; la tarea de demostración de los primeros pasos, guardada en `_meta/`, no cuenta): `Casquettes/` (los roles y sus proyectos), `Projets/` (proyectos nacidos de una tarea), `Inbox/` (la bandeja de entrada), `Ressources/` (lo que sirve a varios proyectos: fichas prácticas, plantillas, contactos), `Archives/` (lo que está terminado o en reposo), y la nota `Lisez-moi.md` que resume el método.

**Cómo la usa la IA**:
- **Antes de cada tarea**, el agente lee la ficha `contexte.md` del proyecto (objetivo, referencias, instrucciones para la IA): unas pocas líneas acertadas valen más que una instrucción larga repetida en cada tarea.
- Las **notas** del proyecto (`notes/`) y las que usted enlaza con `[[Nombre de la nota]]` le dan el fondo del asunto.
- El **grafo** (pestaña «Notas», botón «Grafo») muestra lo que está enlazado y lo que queda aislado.
- El **jardinero de IA** propone enlaces y reordenaciones; no escribe nada sin su conformidad.

**Buenas prácticas**:
1. **Capturar deprisa, ordenar después**: en caso de duda, todo va a `Inbox/`; basta una clasificación por semana.
2. **Una tarea = un resultado esperado** («Redactar la carta al ayuntamiento»), nunca un tema («Ayuntamiento»).
3. **Mantener `contexte.md` al día**: dos o tres líneas, revisadas cuando el proyecto cambia de rumbo.
4. **Archivar en lugar de borrar**: `Archives/` conserva el historial sin estorbar.

**Ya tiene un vault de Obsidian**: apunte `[vault] racine` hacia él (véase «Dónde está el vault»), inicie después la bienvenida y marque «Mi vault de Markdown existente». Se retoma en su sitio, tal cual: no se añade ninguna carpeta, no se reescribe ninguna nota, la carpeta `.obsidian` se ignora y los enlaces `[[…]]` funcionan en las dos herramientas.

## Funciones por pantalla {#fonctions-par-ecran}

### Importar sus proyectos {#reprise-de-vos-projets}

- **Para qué sirve**: en el primer inicio, retomar lo existente (proyectos, conversaciones de agentes, vault) en lugar de partir de un árbol vacío.
- **Cómo se hace**: tres pasos, «Elegir», «Revisar», «Validar». Marque las fuentes deseadas (unas preguntas, una carpeta designada, sus conversaciones de Claude Code o Codex, su vault de Markdown) y luego «Proponer una estructura»; renombre, desmarque o arrastre los elementos propuestos; «Validar» escribe, «Abrir mi árbol» termina. «Más tarde» cierra sin escribir nada.
- **Vault vacío**: las preguntas vienen marcadas de oficio («Sus roles principales (separados por comas)», «Sus proyectos en curso (separados por comas)»); el paso «Revisar» propone además una «Clasificación inicial» (carpetas `Casquettes/`, `Projets/`, `Inbox/`, `Ressources/`, `Archives/` y la nota `Lisez-moi.md`), que se puede desmarcar. Cada proyecto recibe una ficha `contexte.md` por completar (objetivo, referencias, instrucciones para la IA). El botón «?» abre «Organizar su segundo cerebro» en una pestaña nueva.
- **Conviene saber**: lectura solo local, nada sale del equipo y no se llama a ningún modelo. No se sobrescribe nada; una tarea retomada continúa su conversación de origen. Ajustes → «Reiniciar la bienvenida» solo propone lo que falta. En el primer inicio, la bienvenida sigue los primeros pasos (véase «Primeros pasos»); si ha iniciado la demostración, ya no se abre por sí sola: «Reiniciar la bienvenida» la reabre.

### Árbol y listas {#arbre-et-listes}

- **Para qué sirve**: ver todas las tareas en su lugar (roles, operaciones, proyectos, tareas) y su estado.
- **Cómo se hace**: panel izquierdo, pestaña «Tareas»; «Abiertas» o «Todas». En el centro, la vista de conjunto en cascada (estado, actividad, vencimiento, prioridad); un clic en un contador de estado filtra. «Para mí» solo conserva lo que espera su gesto. La búsqueda (tecla `/`) encuentra tareas y notas.
- **Integración atrasada**: una tarea terminada cuya ficha cita una versión `gb/*` que aún no se ha integrado en la versión principal, varias horas después de su último guardado, lleva una etiqueta naranja. Versión principal y retraso tolerado: Ajustes → «Integración de versiones».
- **Ordenar**: arrastre una tarea o un proyecto bajo otro elemento; «Subir un nivel» (Mayús+←); tecla `m` para mover con el teclado; todo gesto se puede deshacer durante 10 s.
- **Conviene saber**: la carpeta manda. Mover un proyecto mueve realmente su carpeta, tras un plan que usted debe aprobar («Aplicar») y un punto de restauración del vault (git).

### Tarea {#tache}

- **Para qué sirve**: la conversación de un agente sobre un trabajo concreto, y su ficha (lo que está hecho, resultado, cómo probarlo, lo que queda).
- **Apertura aligerada**: la cabecera cabe en una línea (título, estado, estado de ejecución, «Resultado», «Validar» / «Devolver» o «Detener» / «Relanzar» según el caso) y el hilo de la conversación ocupa el resto de la pantalla. El botón «Detalles» despliega todo lo demás: ruta y tarea madre, Yo / IA, motor, fecha límite, economía, líneas, enlaces, revisiones, ficha, cuerpo, acciones. Su elección (plegado por defecto) se recuerda. Una alerta (incidente, pausa, control fallido) aparece como una sola pastilla, las demás como «+N»; un clic abre «Detalles».
- **Cómo se hace**: encabezado de la tarea: estado, asistente de IA y modelo (el próximo mensaje sale con ellos), vencimiento, prioridad. Al pie, escriba y luego Ctrl+Intro. «Detener» interrumpe la sesión de trabajo; «Interfaz propia del asistente de IA» abre la misma conversación en un símbolo del sistema, con la interfaz propia del asistente; «Consola de GoldenBrain» la sigue desde un símbolo del sistema.
- **Renombrar**: haga clic en el título de la tarea, se convierte en un campo; Intro guarda, Escape cancela. Solo cambia el título: el identificador, el archivo del vault, los vínculos y la conversación siguen iguales, y el nuevo título aparece en todas partes (árbol, búsqueda, Telegram, panel). Un agente hace lo mismo con `orch renommer <id> "<título>"`. Salir del campo («Hecho» del teclado del teléfono, tocar fuera) también guarda.
- **Yo / IA**: el selector del encabezado indica quién lleva la tarea. «👤 Yo»: ningún agente trabaja en ella (conversación atenuada, ni revisión ni aprobación automática); la tarea lleva una etiqueta en el árbol. «🤖 IA»: «Confiar el resto» devuelve el mando al agente, que recibe sus notas.
- **Notas**: panel junto a la conversación (cada uno se contrae). Notas fechadas, en Markdown, que solo usted añade y modifica; el agente las lee sin escribirlas. Botón de IA: «Resumir», «Corregir» o «Sintetizar», con una propuesta que puede aplicar o deshacer. En el teléfono, los dos paneles se apilan.
- **Ver el resultado**: el botón abre lo que el asistente ha producido, con la aplicación habitual de su ordenador: archivo citado en la ficha o escrito durante la última sesión de trabajo, sitio web (dirección local citada en la ficha, o `index.html` de la carpeta de trabajo) o carpeta de trabajo. Un solo resultado: se abre al instante; varios: una lista para elegir. Si no se encuentra nada, un mensaje se lo indica. Disponible solo en el equipo (rechazado desde un teléfono); un programa o un script nunca se ejecuta: en su lugar se abre su carpeta.
- **Aprender**: el menú «Aprender» del encabezado hace que el asistente de IA explique (o no) lo que hace, solo para esta tarea; por defecto sigue los Ajustes. Las explicaciones aparecen en recuadros azules de la conversación, y la ficha termina con «Lo que puede retener» (tres puntos).
- **Otros gestos**: «Vincular…» (requisito previo, alimenta, ver también), «Crear a partir de esta» (tarea vecina), «Promover a proyecto», «Consultar…» (opinión de un experto del equipo).
- **Conviene saber**: estados: Sin empezar → En curso → En espera (hace falta una persona) o Terminada → Validada. «Bloqueada» señala el fallo técnico de una sesión de trabajo. Un proyecto puede exigir una comprobación (`controle:` en su `contexte.md`) antes de que una tarea pase a «Terminada». En el vault, «En espera» se escribe `statut: retour-humain`; un vault que emplee otro nombre lo declara en `config.toml`: `[vault]` y luego `statut_retour = "<nombre>"`.

### Modo conversación {#mode-discussion}

- **Para qué sirve**: en cuanto se abre una tarea, la conversación ocupa la mayor parte de la pantalla (más del 70 % de una pantalla de 1366×768). No se elimina nada: todo queda a un gesto.
- **Cómo se hace**: la barra superior cabe en una fila (logotipo, contadores, búsqueda, «En curso», «Nueva tarea», «Menú»). «Menú» (cursor encima o clic, Alt+M) despliega Equipo, Revisión de coherencia, Rutina, Cadenas, Ajustes, Manager y la guía. El árbol de tareas se pliega en un carril a la izquierda: pasar el cursor muestra una vista previa y un clic lo fija (Alt+T). Las notas se pliegan en una pestaña a la derecha con su número: un clic las despliega (Alt+N). «Mostrar todo» (en «Menú», Alt+D) restablece la disposición completa; «Modo conversación» vuelve a ella. Cada elección se recuerda por equipo; un globo lo explica la primera vez. En el teléfono no cambia nada.
- **Conviene saber**: al abrir, aparecen primero los últimos intercambios y después el principio del historial. El aviso «Su segundo cerebro aún no está configurado» ya no aparece cuando el vault contiene notas.

### Decisiones {#decisions}

- **Para qué sirve**: un único lugar para resolver todo lo que espera a una persona.
- **Cómo se hace**: botón «Decisiones». Para cada elemento: «Validar», «Devolver…», responder al agente, aplazar (fecha), «Aceptar» o «Rechazar» una propuesta. El jardinero de IA (revisión de coherencia) y los agentes también proponen aquí **renombrar** una tarea cuyo título no dice de qué trata realmente («Renombrar «ventas del club» como «API/MCP ventas del club»», con su motivo): se aplica de oficio (gesto de rutina) y se deshace desde «Aplicado de oficio». Varias tareas marcadas se aprueban de una vez. Los gestos de rutina de los agentes (enlazar, colgar, mover, renombrar, fecha límite, tarea creada bajo la suya) ya no le esperan: se aplican de oficio, se anotan en las «Traces» de la tarea y se listan siete días en «Aplicado de oficio», al pie de la página, cada uno con «Deshacer». Lo que queda por decidir (cerrar, hacer un proyecto o una operación, cambiar un alcance) se agrupa por tarea emisora en una entrada plegada «Propuestas de …»: «Aceptar todo» o «Rechazar todo», o, desplegada, una línea por propuesta, motivo al pasar el ratón o al desplegar.
- **Conviene saber**: los cierres automáticos de los últimos 7 días figuran ahí bajo «Cerradas automáticamente», cada uno con «Reabrir». La etiqueta «¿evitable?» señala una pregunta o una aprobación que el agente habría podido resolver solo (mera información, no se modifica nada); Ajustes → Etiqueta «¿evitable?» la apaga o ajusta su umbral.

### Hoy {#aujourd-hui}

- **Para qué sirve**: saber qué hacer ahora.
- **Cómo se hace**: botón «Hoy» (con el número de tareas con retraso). Grupos: con retraso, para hoy, para dentro de siete días, para mí; cada uno ordenado por prioridad.
- **Conviene saber**: el vencimiento (`echeance: AAAA-MM-JJ`) y la prioridad (`priorite: haute | moyenne | basse`) se fijan en el encabezado de la tarea o al crearla.

### En curso {#en-cours}

- **Para qué sirve**: ver de un vistazo lo que hacen sus asistentes de IA en este momento, y lo que espera.
- **Cómo se hace**: pulse «En curso» (con el número de seguimiento), en la barra superior (dirección `#en-cours`). Para cada asistente en funcionamiento: la tarea y su proyecto, el asistente y su modelo, desde cuándo, lo que hace («ejecuta las pruebas», «escribe build.py», «ha modificado 3 archivos»), el avance de su lista de pasos cuando la lleva, y las ayudas que ha lanzado con su estado y su duración. Gestos: «Abrir», «Poner en pausa» y luego «Reanudar», «Detener» (se pide confirmación). Debajo: las tareas en espera y su motivo (memoria, crédito de uso, requisito previo, puesto en la cola), las rutinas próximas, las incidencias abiertas.
- **Conviene saber**: la pantalla se actualiza sola cuando un asistente avanza; nada se ejecuta cuando está cerrada. Las ayudas lanzadas se siguen para Claude Code y OpenCode; el avance, para Claude Code, OpenCode y Codex. Una pausa manual congela al asistente sin perder nada; solo se reanuda con «Reanudar» (la regulación de memoria no la toca).

### Compañero móvil {#compagnon}
- **Trabajo en curso**: toque la estrella ★ de una tarea (árbol o «En curso» en Inicio) para fijarla en este teléfono; el botón «Trabajo en curso» de Inicio (`#travail`) muestra solo esas tareas y cada una abre su chat: la conversación con el agente de la tarea y un cuadro de mensaje, enviado como desde la pantalla completa. Fijar es un ajuste del teléfono (no se escribe nada en el equipo); el chat requiere el equipo en línea. El estado y la estructura solo cambian con los gestos habituales.

- **Para qué sirve**: consultar desde el teléfono, de un vistazo, lo que espera su decisión, lo que está trabajando y el árbol de proyectos (solo lectura, salvo una acción: validar o devolver una tarea terminada por su agente, en línea y tras confirmación).
- **Cómo hacerlo**: el acceso pasa por la red privada Tailscale y un teléfono emparejado (Ajustes → Dispositivos; paso a paso: `docs/TELEPHONE.md`). En el teléfono, el botón « Inicio » de la barra inferior (dirección `#compagnon`): « Por decidir » (la pregunta de cada decisión), « En curso » (asistentes trabajando) y « Proyectos y tareas » (toque un proyecto para abrirlo, « ‹ » para subir). Tocar una decisión o una tarea la abre en la pantalla habitual. Instalada en la pantalla de inicio, la aplicación se abre directamente en este Inicio; una decisión por validar es una sola tarjeta, con sus botones «Validar» y «Devolver» en el mismo marco. Si el emparejamiento falla por falta de red, el botón «Reintentar» de la página lo repite sin volver a escanear el código. Opcional: `resume = true` en `[distant]` añade al teléfono un resumen de 140 caracteres del resultado de una tarea por validar; ese texto sale del equipo, nunca se guarda sin conexión y está desactivado por defecto. En pantallas pequeñas, la página «Decisiones» se apila: título a todo el ancho y botones más grandes. La franja «actualización disponible» no aparece en el teléfono (la actualización se hace desde el equipo).
- **Conviene saber**: la pantalla se actualiza sola mientras está abierta e indica si está conectada o si muestra datos de una hora dada. El modo sin conexión es opcional y está desactivado por defecto: ponga `hors_ligne = true` en `[distant]` de `config.toml` y marque « Guardar una vista previa sin conexión en este dispositivo »; solo se guardan títulos, estados y decisiones, 7 días, nunca el contenido de las fichas ni de las conversaciones. La vista previa se borra al revocar el dispositivo o con « Borrar los datos de este dispositivo ». Sin conexión, los gestos están desactivados: requieren el equipo. Sin conexión, la pantalla lo indica («Sin conexión · datos del …»); un gesto fallido precisa que nada ha cambiado.

### Notas {#notes}

- **Para qué sirve**: recorrer y modificar todo el vault sin salir de GoldenBrain.
- **Cómo se hace**: panel izquierdo, pestaña «Notas» (modo Avanzado). «Nueva nota»; «Modificar» (tecla `e`, Ctrl+S guarda); «Renombrar / mover…» reescribe los enlaces.
- **Conviene saber**: si la nota ha cambiado en otro sitio (Obsidian, un agente), el guardado se rechaza y se le ofrecen las dos versiones. Los bloques Dataview no se ejecutan.
- **Grafo**: botón «Grafo» de la pestaña «Notas» (grafo global: notas, tareas, carpetas y sus enlaces, filtros por rol, proyecto, tipo, etiqueta, período); botón «Grafo» de una tarea o «Grafo local» de una nota (profundidad ajustable). Un clic en un elemento abre la nota o la tarea.

### Rutinas {#routines}

- **Para qué sirve**: una instrucción que ejecuta un agente a hora fija (revisión diaria, informe semanal).
- **Cómo se hace**: botón «Rutina» (reloj, arriba). Título, instrucción, programa («chaque jour 08:00», «en semaine 18:00», «lundi,jeudi 09:30», «toutes les 2 h de 8 h à 20 h», o una expresión cron; la fórmula se escribe en francés), proyecto, conversación (la misma o una nueva en cada ejecución), recuperación de un vencimiento perdido. Dentro de la rutina: «Poner en pausa», «Ejecutar ahora», historial de ejecuciones. Una tarea existente se convierte en rutina en el sitio con «Convertir en rutina» (misma nota, misma conversación); «Quitar la rutina» vuelve a hacerla ordinaria.
- **Conviene saber**: una rutina lleva un reloj en el árbol; nunca se ejecuta dos veces a la vez y pasa por la misma cola que las tareas.

### Cadenas {#chaines}

- **Para qué sirve**: encadenar varias fases de trabajo confiadas a la IA sobre una misma carpeta (p. ej. responder a una licitación: análisis, propuesta de valor, solución, redacción, revisión), partiendo cada fase del resultado de la anterior.
- **Cómo se hace**: botón «Cadenas» (arriba): lista de modelos, incluidos («Réponse à un appel d'offres», «Article ou contenu») y personales, guardados en `_meta/chaines/` del vault; «Nueva cadena» o «Modificar»: título, resumen, contexto común, carpeta vigilada y proyecto (opcionales), y luego las fases (título, instrucciones, documentos de entrada, entregable esperado, asistente de IA, modelo de IA, casilla «Validación humana tras esta fase»), que se pueden añadir, eliminar y reordenar; «Quitar» (modelos personales, con confirmación). Inicio manual: «Iniciar» en la lista, o ⛓ en un proyecto: modelo, proyecto, carpeta a tratar, título opcional. Se crea una tarea madre, con una tarea por fase; su detalle muestra las fases numeradas con su estado, un enlace a cada una, el estado de la cadena y su posible error. «Validar y continuar» reanuda tras una fase con validación humana; «Reanudar» relanza la fase fallida.
- **Conviene saber**: las fases se suceden una a una, nunca en paralelo. Con una carpeta vigilada, cada nueva subcarpeta inicia la cadena, sin recuperar las que ya existían. La IA puede adaptar las fases pendientes a la carpeta real (omitir, añadir, duplicar, cambiar una instrucción): cada ajuste se señala en el detalle, con su motivo.

### Equipo {#equipe}

- **Para qué sirve**: expertos (miradas especializadas) que revisan las tareas terminadas.
- **Cómo se hace**: botón «Equipo» (modo Avanzado), «Nuevo experto»: nombre, mandato (lo que examina), foco (lo que comprueba primero), activación (siempre, con filtro, o bajo demanda), asistente de IA y modelo. Desde una tarea: «Consultar…».
- **Conviene saber**: un experto da una opinión; no aprueba, salvo con el ajuste `[validation] mode = "persona"`.

### Ajustes {#reglages}

- **Para qué sirve**: ajustar la interfaz y el motor sin editar ningún archivo.
- **Cómo se hace**: botón «Ajustes». Seis grupos desplegables, cada uno titulado con su estado en una línea: Pantalla (idioma, nivel de detalle, tema, invitación a la estrella), Funciones mostradas, Agentes y recursos (agentes a la vez, rendimiento o economía, resumen de las conversaciones largas, modo Aprender, asistentes de IA por rol), Aprobación y propuestas (propuestas de los agentes, etiquetas «¿evitable?» e «integración atrasada»), Conexiones (Telegram, teléfono y otros dispositivos, ordenadores de apoyo), Instalación y versión (actualización: canal y modo automático, informar de un problema, repetir los primeros pasos, reiniciar la bienvenida). Pulsar un título lo abre o lo cierra; los grupos abiertos se recuerdan de una visita a otra. El campo «Buscar un ajuste» abre el grupo correspondiente (p. ej. «memoria», «Telegram»). Enlace directo a una sección: `#reglages/telegram`, `#reglages/simultanes`, `#reglages/economie`, `#reglages/compactage`, `#reglages/appareils`, `#reglages/executeurs`, `#reglages/installation`, `#reglages/premiers-pas`…
- **Idioma**: français, English, Deutsch o español. En el primer inicio, GoldenBrain toma el del navegador; Ajustes → Pantalla → Idioma (o la primera pantalla de la bienvenida) lo cambia, y la página se recarga. Vale para las pantallas, los mensajes, la ayuda «?» (guía del idioma elegido) y las respuestas de los agentes; los nombres de carpetas, los estados del vault y los comandos no cambian.
- **Propuestas**: Ajustes → Validación y propuestas. Dos familias de gestos, para marcar: «Aplicados de oficio» (por defecto: enlazar, colgar, mover, renombrar, fecha límite, tarea creada bajo la del agente) y «Por decidir» (cerrar, proyecto, operación, alcance, tarea en otro lugar). Desmarcar un gesto lo devuelve a las decisiones; el ajuste «Gestos por decidir» (mostrar, aceptar, ignorar) solo vale para la segunda familia. El jardinero y el escaneo del sistema siempre proponen sin aplicar nada.
- **Modo Aprender**: Ajustes → Agentes y recursos → Modo Aprender. Activado, el asistente de IA explica en una o dos frases sencillas lo que hace y por qué en cada etapa, y concluye con «Lo que puede retener». Coste: algo más de texto en cada sesión de trabajo y, por tanto, algo más de crédito de uso consumido. Desactivado, nada cambia.
- **Reflejos del agente**: Ajustes → Agentes y recursos → Reflejos del agente (y al final de los primeros pasos). GoldenBrain propone añadir a las instrucciones de cada asistente de IA del equipo (`CLAUDE.md`, `AGENTS.md`, `GEMINI.md`…) algunos reflejos: vincular cada trabajo a una tarea (retomar primero, si no crear), anotar en la ficha los documentos creados o modificados, enlazar tareas, documentos y notas, dejar constancia del resultado. Para cada asistente: su estado (ausente, al día, versión antigua, modificado a mano), «Ver el cambio» (líneas añadidas o quitadas) y luego «Aceptar», «Más tarde» o «Quitar». No se escribe nada sin ese clic; el bloque está entre dos marcadores y el resto del archivo nunca se toca. Tras una actualización que cambie los reflejos, la propuesta vuelve.
- **Estrella de GitHub**: tras unas horas de uso, y solo si GoldenBrain es público en GitHub, una ventana única propone «Dar una estrella», «Más tarde» o «No volver a preguntar»; Ajustes → Pantalla la apaga.
- **Conviene saber**: la interfaz solo escribe en `config.toml`. Las demás claves (vault, asistentes de IA, instrucciones de los agentes) se ajustan en ese archivo, según `config.exemple.toml`. Lo que está escribiendo ya no se pierde cuando un agente trabaja en segundo plano. Los bordes de los campos y botones alcanzan un contraste de 3:1 contra el fondo en los dos temas (WCAG 1.4.11).

### Actualización con un clic {#mise-a-jour-d-un-clic}

- **Para qué sirve**: pasar a la última versión sin símbolo del sistema.
- **Cómo se hace**: cuando aparece la barra «Hay una actualización disponible», pulse «Actualizar»; la página espera el reinicio y luego se recarga. Sin la interfaz (Windows): doble clic en `mettre-a-jour.cmd`.
- **Conviene saber**: se rechaza mientras un agente trabaja (reintente después) o si se han modificado a mano archivos de GoldenBrain. La carpeta solo avanza, sin mezclar nunca modificaciones; `config.toml`, `etat`, `journal` y `equipe` nunca se tocan. Origen: la versión principal (`main`) de la carpeta del código pública https://github.com/Greal-dev/goldenbrain (el remoto `origin` de un clon), ajustable con `[mise_a_jour] branche` y `distant`.
- **Qué hay de nuevo**: la barra lleva «¿Qué hay de nuevo?»; un clic despliega las novedades de la versión pendiente, en lenguaje corriente. El registro de versiones es `CHANGELOG.md`, en la raíz de la carpeta del código (ausente de un clon del repositorio público; en francés); cada versión pública tiene además su nota en la página «Releases» de la carpeta del código público (para suscribirse: «Watch» → «Custom» → «Releases», o el canal https://github.com/Greal-dev/goldenbrain/releases.atom).
- **Notas de versión**: en la página «Releases», la nota va en el idioma de la página; sin traducción, las notas en inglés, español y alemán anuncian «notas en francés» en vez de presentar francés bajo un título extranjero.
- **Canal estable o beta**: Ajustes → «Instalación y versión» → «Actualización» → «Canal». «Beta» sigue la versión `beta` de la carpeta del código pública (versiones de prueba, antes que `main`); la barra propone entonces «pasar al canal beta» y el botón «Actualizar» cambia de versión y luego reinicia GoldenBrain. Volver a «Estable» se hace igual. Se rechaza si el código se ha modificado a mano, o desde una versión distinta de `main` o `beta`; el vault nunca se toca. Si la versión `beta` no existe (todavía) en la carpeta del código público, GoldenBrain lo dice en una frase, devuelve el canal a «Estable» y no toca nada. Para probar y dar su opinión: página «Hacerse probador» (`BETA.md`).
- **Informar de un problema o proponer una idea**: Ajustes → «Instalación y versión» → «Informar de un problema o proponer una idea». Los enlaces abren, en el navegador, el formulario de GitHub del proyecto público con la versión (huella, fecha, canal) y el sistema ya rellenados — nada más: ni nombre, ni ruta, ni contenido del vault. GoldenBrain no envía nada; usted lo revisa y lo envía (se necesita una cuenta de GitHub). «Hacer una pregunta» abre las Discussions.
- **Actualización automática**: Ajustes → «Instalación y versión» → «Actualización» → «Aplicar sola una actualización disponible» (desactivada por defecto). Ninguna sesión de trabajo nueva arranca durante la preparación; las sesiones en curso terminan, y una sesión que supera el plazo fijado solo se corta (y luego se reanuda) en un punto de reanudación seguro. Franja horaria opcional; la actualización también espera a que usted deje de tocar la interfaz. Un fallo se muestra en una barra, con el gesto que hay que hacer.
- **Reiniciar durante una sesión de trabajo**: si «Reiniciar» se rechaza porque hay sesiones de trabajo en curso, se ofrece «Reiniciar GoldenBrain en cuanto terminen las sesiones de trabajo» (solo GoldenBrain, nunca el ordenador); la espera se cancela desde la misma barra.

### Gestor {#manager}

- **Para qué sirve**: conversar con un agente general que dirige todas las tareas: «¿Qué me espera?», «¿Cómo va X?», confiarle un asunto (lo orienta hacia la tarea o el proyecto adecuado, o crea una), actualizar, relanzar, unir dos duplicados.
- **Cómo se hace**: botón «Gestor» de la barra superior; el panel se abre a la derecha, en todas las pantallas, y sigue abierto de una recarga a otra. Escriba y pulse Intro (Mayús+Intro: salto de línea). «×» lo cierra; en el teléfono ocupa la pantalla y «← Volver» lo cierra.
- **Conviene saber**: es el asistente de Telegram, en la misma conversación: lo que se escribe en un lado se lee en el otro (indicación «vía Telegram»), y `/nouveau` abre una conversación nueva para ambos. Un cambio de estado, fecha límite o prioridad espera su «Confirmar» (en el panel o en Telegram, una sola vez); una reorganización pasa por Decisiones. El panel funciona sin Telegram y no carga nada mientras está cerrado. El hilo conserva los últimos 200 mensajes y se recarga solo tras un corte; solo baja al último mensaje si ya estaba leyendo el final.

### Telegram {#telegram}

- **Para qué sirve**: enviar una idea, una foto o una nota de voz desde el teléfono; se convierte en una tarea ya ordenada.
- **Cómo se hace**: Ajustes → Conexiones → Telegram; un asistente le guía paso a paso. Cree un bot con @BotFather («Ya tengo mi bot y su clave de acceso»); introduzca su clave de acceso («Introducir la clave de acceso en un símbolo del sistema seguro», o en el navegador como solución de reserva); confirme el nombre del bot («Sí, es mi bot»); escriba al bot en Telegram, luego «Reconocerme» y marque su conversación; «Enviar el mensaje de prueba» y después «Sí, terminar y activar Telegram».
- **Conviene saber**: la clave de acceso se guarda en el llavero del ordenador y nunca se vuelve a mostrar. Un solo programa puede escuchar a un bot: detenga antes cualquier otro lector. Responder al mensaje «Tarea creada: …» escribe en esa tarea. Una orden que se parece a una tarea abierta hace proponer su actualización en lugar de una tarea nueva. «Responder» a un mensaje del asistente le transmite el texto citado (una cita, nunca una orden) y la tarea de la que hablaba.

### Ordenadores de apoyo {#executeurs-distants}

- **Para qué sirve**: hacer trabajar a los agentes en otros ordenadores; el vault y la interfaz permanecen en el ordenador principal.
- **Cómo se hace**: una los ordenadores con Tailscale; en el ordenador principal, en `config.toml`: `[executeurs]` y luego `ecoute = "<dirección Tailscale del ordenador principal>"`, y reinicie; Ajustes → Conexiones → «Ordenadores de apoyo» → «Emparejar un ordenador» da un código corto. En el otro ordenador: `python orch.py executeur --serveur http://<dirección del ordenador principal>:8300 --code <código>`, o Ajustes → «Convertir este ordenador en ordenador auxiliar».
- **Conviene saber**: detalle, averías y prueba: `docs/EXECUTEURS.md`. Nunca exponga GoldenBrain en Internet.

## Solución de problemas {#depannage}

| Síntoma | Causa probable | Gesto |
|---|---|---|
| La página http://127.0.0.1:8300 no responde | GoldenBrain detenido | Volver a ejecutar `./lancer.sh` o `lancer.cmd`; con systemd, `systemctl --user status goldenbrain` |
| `ModuleNotFoundError: fastapi` al iniciar | Python equivocado | Comprobar la primera línea de `python.local` y reinstalar las dependencias con ese Python |
| «Address already in use» | Puerto ocupado | `[serveur] port = 8301` en `config.toml` |
| El árbol está vacío | Vault no encontrado | `[vault] racine` en `config.toml`, y reiniciar |
| Asistente de IA «no disponible» | Programa ausente del PATH o sin sesión iniciada | Instalarlo e iniciar sesión (véase «Conectar los asistentes de IA») |
| Incidencia «Asistente de IA no instalado» | Un asistente de IA de `[credits]` no está instalado en este ordenador | Nada urgente: la sesión de trabajo se relanza una vez con el siguiente asistente de `[credits]`, y el equilibrado ya no elige al ausente. Instale el asistente (véase «Conectar los asistentes de IA») o quítelo de `[credits]` |
| Tarea «Bloqueada» | Fallo técnico de la sesión de trabajo | Leer la causa en la conversación y luego escribir un mensaje; una sesión interrumpida se retoma con «Relanzar». Los mensajes recibidos durante el bloqueo (Telegram, otros agentes) esperan en cola y salen en orden en cuanto se escribe, se cambia de motor o se cambia el estado (tarea cerrada: se descartan) |
| Tarea «A la espera del equipo» | Una prueba pesada ha reservado el equipo | Esperar (el puesto en la cola se muestra en la tarea y en la barra), o «Liberar» en la barra «Equipo reservado» |
| «Hay una actualización disponible» no se aplica | Agente trabajando, o archivo de GoldenBrain modificado | Reintentar tras la sesión de trabajo; `git status` en la carpeta |
| Barra «Reiniciar» | GoldenBrain se ha actualizado, pero sigue funcionando con la versión anterior | Pulsar «Reiniciar» |
| Un agente de Claude Code no ve sus servidores MCP (navegador…) | Por defecto, ningún servidor MCP por sesión de trabajo (ahorro de memoria) | `mcp: heritage` en el encabezado de la nota de la tarea, o `[harnais.claude] mcp = "heritage"` en `config.toml` |
| «Conexión perdida…» | GoldenBrain reiniciado o detenido | Esperar unos segundos; si no, volver a iniciarlo |

## Para un agente de IA {#pour-un-agent-ia}

Para leer por todo agente —Claude Code, Codex, OpenCode, Antigravity u otro— que dirija GoldenBrain o trabaje en su repositorio. GoldenBrain no se invoca mediante una biblioteca: se le habla con el comando `python orch.py` (desde la raíz del repositorio, nunca mediante un `.cmd`) o con su API local.

**1. Arrancar y verificar el servidor**

- Arrancar: `./lancer.sh` (Linux, macOS) o `lancer.cmd` (Windows), en la raíz del repositorio.
- Verificar: `curl -s http://127.0.0.1:8300/api/etat` responde con un objeto JSON (turnos en curso, cola, decisiones). Una conexión rechazada: el servidor no está iniciado.
- Otra dirección (puerto fijado en `config.toml`, servidor de prueba): variable `ORCH_URL`, por ejemplo `export ORCH_URL=http://127.0.0.1:8301`; `orch.py` la lee.
- Un agente lanzado por GoldenBrain recibe `ORCH_URL`, `ORCH_TACHE` (su tarea) y `ORCH_SAUTS`; `orch.py` los usa para firmar sus mensajes y acotar los relevos.

**2. Comandos `orch`**

| Comando | Efecto |
|---|---|
| `guide` | esta guía |
| `arbre` | árbol de las tareas abiertas |
| `chercher "<palabras>"` | tareas relacionadas |
| `lire <id>` | ficha, ruta, ubicación, estado, ejecución de una tarea |
| `conteneurs` | contenedores donde ordenar una tarea |
| `rapprochement ["<título>"]` | tareas cercanas a un título; sin título, creaciones evitadas |
| `creer "<título>" --description "<una frase como mínimo>"` | crear una tarea (`--conteneur`, `--parent`, `--lancer`, `--mission`); rechazada si existe una tarea abierta muy parecida: completarla (`dire`) o forzar (`--nouvelle`) |
| `dire <id> "<mensaje>"` | escribir a la tarea: su agente lo recibe en el próximo turno (lo lanza si está libre) |
| `renommer <id> "<título>"` | cambiar el título de una tarea (identificador y archivo sin cambios) |
| `relancer <id>` | relanzar una tarea fallida o interrumpida; una sesión cortada por la memoria del equipo, un reinicio o un error transitorio del servicio se reanuda sola (tres veces como máximo, «interrumpido (reanudación automática en la cola)»), luego la tarea vuelve a usted; una parada pedida por usted nunca se reanuda sola. Haga un commit de etapa en su rama en cada hito: la reanudación encuentra el árbol de trabajo y la rama |
| `arreter <id>` | detener el turno en curso |
| `deleguer "<título>" "<brief>"` | confiar un trabajo a una tarea hija lanzada por GoldenBrain |
| `proposer deplacer\|rattacher\|projet\|operation\|ticket\|tache\|lier\|perimetre\|echeance\|fermer\|renommer …` | proponer un cambio de estructura (`--motif`, obligatorio para `renommer`) ; `rattacher <id> <parent|racine> [--aussi <id>…]` ordena un lote de tareas bajo una tarea madre (o las desvincula hacia su proyecto) en UNA propuesta, rechazada si hay ciclo, tarea en curso, otro proyecto, tope de 10 o naturalezas mezcladas; la persona acepta con un clic. En modo simple, las propuestas se ignoran (Ajustes > Propuestas); un gesto cuyo efecto ya existe no se deposita, y si lo logra antes de aceptarlo se concluye como «ya hecho» sin error Los gestos de rutina (Ajustes > Propuestas) se aplican de oficio y se pueden deshacer desde Decisiones; una propuesta `tache` de un agente se convierte en una línea de su tarea. |
| `solliciter <persona> "<pregunta>"` | opinión de un persona del equipo |
| `telegram "<texto>"` | mensaje al usuario en Telegram (`--validation`, `--choix`); exige el bot configurado |
| `poste reserver "<motivo>"` / `poste liberer` | reservar el puesto durante una prueba pesada; si está ocupado, esperar turno (`--attente <min>`, por defecto 30) |
| `chaine plan\|sauter\|ajouter\|dedoubler\|consigne …` | adaptar la cadena de la tarea a la carpeta real: `plan` la muestra; omitir, añadir, duplicar una fase o cambiar su instrucción (solo fases pendientes), siempre con `--motif`: el ajuste se registra y se muestra al usuario |
| `feu-vert demander\|accorder\|refuser\|verifier <sha de 40 car.> [texto] [--a <tarea del controlador>] …` | luz verde ligada a una versión (huella completa de 40 caracteres); requiere `ORCH_TACHE` |
| `agents-cc [--relever]` | agrupar los agentes de Claude Code de este equipo y vincularlos a una tarea |
| `reevaluer` | volver a ejecutar la validación automática sobre las tareas |
| `console <id> [--url]` | seguir una tarea y escribirle desde el terminal |
| `rattacher <envoi> <id>` | vincular un envío de Telegram a una tarea existente (no confundir con `proposer rattacher`, que ordena tareas bajo un padre) |
| `m365 connecter\|demander\|contexte` | conocimiento de empresa de Microsoft 365 Copilot (si está activado) |
| `telegram-jeton [--pause]` | introducir el token del bot de Telegram sin mostrarlo (cofre del equipo) |
| `jeton-executeur <nom> [--revoquer]` | crear o revocar el token de un ordenador auxiliar |
| `executeur [installer]` | convertir este PC en ejecutor de un GoldenBrain jefe |
| `fiche` | ficha y estado propuesto de una ejecución agrupada |
| `natif <fichier>` | relevo de la interfaz nativa (lo lanza GoldenBrain, no a mano) |
| `poste etat` | ver quién tiene el puesto |

`python orch.py <comando> -h` da las opciones de cada uno.

**3. API REST** (http://127.0.0.1:8300, JSON). Toda escritura lleva el encabezado `X-Orchestrateur: 1`; sin él, el servidor responde 403 (protección contra una página web de terceros).

| Ruta | Efecto |
|---|---|
| `GET /api/etat` | estado del puesto: turnos en curso, cola, decisiones, propuestas |
| `GET /api/arbre` | árbol de las tareas |
| `GET /api/recherche?q=<palabras>` | buscar |
| `GET /api/taches/{id}` | una tarea (estado, ficha, notas, ejecución) |
| `POST /api/taches` | crear: `titre`, `description`, y a elección `conteneur`, `parent`, `lancer`, `mission`, `harnais`, `modele`, `echeance`, `priorite`, `forcer` (pasar por alto una tarea muy cercana), `groupe` |
| `POST /api/taches/{id}/messages` | escribir a la tarea: `texte` (y `de`: el id de la tarea que escribe) |
| `POST /api/taches/{id}/statut` | fijar un estado: `statut` — gesto humano, véanse las reglas |
| `POST /api/taches/{id}/notes` | añadir una nota de la persona: `texte` |
| `POST /api/taches/{id}/executant` | `executant`: `humain` (Yo) o `ia` |
| `POST /api/taches/{id}/relancer` | relanzar |
| `GET /api/propositions` · `POST /api/propositions` | listar · proponer: `type`, `tache`, `valeur`, `motif` |
| `POST /api/propositions/{n}/accepter` · `…/refuser` | resolver — gesto humano |
| `POST /api/propositions/{n}/annuler` | deshacer un gesto aplicado de oficio — gesto humano |
| `GET /api/guide[?langue=fr\|en\|de\|es]` | esta guía, en texto plano (`orch guide` solo sirve el francés) |
| `GET /api/evenements` | flujo de eventos (SSE) |

**4. Reglas**

- **Relacionar antes de crear**: primero `chercher` o `rapprochement "<título>"`; una tarea cercana se completa (`dire`) en lugar de duplicarse.
- **Integración**: en un proyecto que declara `integration:`, `creer` y `deleguer` enlazan de oficio la nueva tarea con la tarea de integración (`alimente`); en otro caso, una tarea que entrega una rama pone este enlace directamente (`proposer lier <id> alimente <integración>`): un enlace `alimente` hacia una tarea permanente es un gesto de rutina, aplicado de oficio y anotado en las «Traces» de la tarea, nunca en espera en Decisiones; los demás enlaces siguen la política de propuestas. Desde el 24/11, todo enlace propuesto es por defecto un gesto de rutina (Ajustes > Propuestas).
- **Nunca cambiar un estado sin conformidad humana**: un agente no fija `fait`, no acepta una propuesta, no aprueba una tarea; entrega su ficha y la persona aprueba. Las rutas `statut`, `valider`, `accepter` son gestos de la interfaz.
- **Tareas «Yo»** (`executant: humain`): la persona la lleva; GoldenBrain rechaza en ella todo turno y toda escritura de agente, salvo líneas y enlaces (un agente puede leerla y proponer); «Confiar el resto» es el gesto humano que la devuelve a la IA.
- El vault es la única base de datos; nunca reformatear el frontmatter de una nota.
- Nunca mover una carpeta por cuenta propia: proponer (`orch proposer`), la persona acepta.
- Ningún envío, publicación, pago ni borrado sin conformidad escrita del usuario.
- Un agente lanzado por GoldenBrain termina cada respuesta con el bloque `<fiche>` descrito en la instrucción recibida.

**5. Ejemplos de principio a fin**

Encontrar o crear una tarea y luego confiarla:

```bash
python orch.py rapprochement "Redactar la nota de versión"
python orch.py creer "Redactar la nota de versión" \
  --description "Resumir los cambios de la semana; prueba: la nota existe en el vault."
python orch.py lire 2026-11-19-redactar-la-nota-de-version
python orch.py dire 2026-11-19-redactar-la-nota-de-version "Empieza por el registro de git de la semana."
```

Lo mismo con la API:

```bash
curl -s http://127.0.0.1:8300/api/etat
curl -s -X POST http://127.0.0.1:8300/api/taches \
  -H 'X-Orchestrateur: 1' -H 'Content-Type: application/json' \
  -d '{"titre": "Redactar la nota de versión", "description": "Resumir los cambios de la semana; prueba: la nota existe en el vault."}'
curl -s "http://127.0.0.1:8300/api/recherche?q=nota%20de%20versi%C3%B3n"
curl -s -X POST http://127.0.0.1:8300/api/taches/2026-11-19-redactar-la-nota-de-version/notes \
  -H 'X-Orchestrateur: 1' -H 'Content-Type: application/json' -d '{"texte": "Mantener un tono sobrio."}'
```

Proponer una reordenación en lugar de hacerla:

```bash
python orch.py proposer deplacer 2026-11-19-redactar-la-nota-de-version Projets/C1-Site \
  --motif "la nota de versión corresponde al sitio web"
```

El identificador de una tarea lo devuelve `creer` (y también `arbre`, `chercher`): fecha del día y título en minúsculas.

**Continuación**: `docs/ARCHITECTURE.md` (módulos, invariantes `INV-*`, contratos), `docs/CODE_MAP.md` (mapa de los archivos), `CLAUDE.md` (reglas del repositorio).
