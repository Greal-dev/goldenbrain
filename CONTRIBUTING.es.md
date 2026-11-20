# Contribuir

[English](CONTRIBUTING.md) · [Français](CONTRIBUTING.fr.md) · [Deutsch](CONTRIBUTING.de.md) · Español

Gracias por su interés. Una corrección pequeña puede ir directamente como solicitud de fusión; para cualquier cambio mayor, abra antes una incidencia para acordar el enfoque. La [hoja de ruta](ROADMAP.es.md) indica dónde la ayuda es más bienvenida.

## Antes de empezar
Leer, en este orden:
1. `CLAUDE.md` — el contrato de trabajo: comandos canónicos, reglas, zonas peligrosas.
2. `docs/ARCHITECTURE.md` — módulos, contratos y los invariantes `INV-*` que nunca deben romperse.
3. `docs/CODE_MAP.md` — cada archivo, su función, los invariantes que lleva y sus pruebas.

El código, los identificadores, las etiquetas de la interfaz y los documentos de diseño están en francés; las incidencias y solicitudes de fusión pueden redactarse en inglés, francés, alemán o español.

## Dónde contribuir
Los puntos de extensión preferidos añaden una capacidad sin tocar el núcleo:
- **Adaptador de arnés** — admitir un nuevo arnés de agente de línea de comandos: un módulo en `src/orchestrateur/harnais/` que implemente el contrato común de turno, más una entrada en el registro `HARNAIS`. Los adaptadores existentes y sus datos de prueba grabados (`tests/donnees/`) sirven de modelo.
- **Conectores** — traer tareas de otros lugares (mensajería, correo, escáner…) mediante la API HTTP local o el comando `orch`, nunca escribiendo en el vault a espaldas de GoldenBrain.
- **Traducciones** — los documentos de bienvenida (README, CONTRIBUTING, SECURITY, ROADMAP) existen en cuatro idiomas y deben mantenerse alineados; traducir la interfaz es un punto de la hoja de ruta.
- **Plantillas de tarea y de proyecto** — plantillas de frontmatter (`[vault.gabarit_tache]`) y ejemplos de `contexte.md` para tipos de proyectos habituales, con contenido ficticio.

## Reglas
- Ninguna dependencia nueva; interfaz sin paso de compilación (HTML, CSS, JS nativos).
- Un módulo ≤ 500 líneas con su cabecera (función, fronteras, invariantes que lleva); un comentario dice por qué y cita el invariante afectado.
- Las pruebas nunca escriben en un vault real (carpeta temporal) y nunca lanzan un arnés real (adaptador simulado).
- Cada corrección incluye su prueba de regresión; la documentación cambia en el mismo commit que el código.
- **Ningún dato personal** (INV-PUB-1): ni nombre, ni dirección de correo, ni ruta de su equipo, ni extracto de un vault o conversación reales, ni identificador de sesión, ni token. Solo datos de prueba ficticios. Copie `.sensible.exemple` en `.sensible` e inscriba sus propios patrones: la puerta los rechazará.

## El recorrido de una contribución
1. **Primero, un ticket.** Abra una incidencia con el formulario adecuado (*Bug report* o *Feature request*); una pregunta va a Discussions. En la aplicación, *Ajustes → Instalación y versión → Informar de un problema* abre el formulario con la versión y el sistema ya rellenados. Etiquetas: `bug`, `évolution` (mejora), `à trier` (por clasificar) y `bon premier ticket` (buen primer ticket) o `aide bienvenue` (ayuda bienvenida) para los tickets abiertos a recién llegados.
2. **Una rama.** Haga un *fork* del repositorio y trabaje en una rama con el nombre del ticket (`fix/123-titulo-corto`).
3. **Una solicitud de fusión** hacia `main` de este repositorio, vinculada al ticket (`Fixes #123`).
4. **Comprobaciones automáticas** (GitHub Actions): la puerta en Linux y en Windows, y la firma DCO. Ambas deben estar en verde.
5. **Revisión automática.** Un revisor de IA lee el diff (seguridad, invariantes `INV-*`, pruebas, alcance) y comenta en P1 (bloqueante), P2 (a corregir), P3 (opcional). Nunca ejecuta su código ni fusiona: informa a un mantenedor, que decide.
6. **Integración.** El proyecto se desarrolla en un repositorio de los mantenedores del que este es el espejo. Una vez aceptado, un mantenedor aplica allí su cambio, conservando autoría y firma; la siguiente versión en verde republica este repositorio, y su solicitud se cierra con un enlace al commit publicado. Se cierra, pues, en lugar de fusionarse — su contribución figura igualmente.

Los probadores siguen la rama `beta`: vea [BETA.es.md](BETA.es.md).

## Puerta
`python scripts/check.py` debe estar en verde antes del envío: pruebas, controles de estructura, mapa del código, guarda de publicación. La integración continua ejecuta la misma puerta en Linux y en Windows en cada solicitud de fusión. Los escenarios de interfaz (`python scripts/check_ui.py`, Playwright) se ejecutan solo en local.

## Firmar los commits (DCO)
Las contribuciones se aceptan bajo el [Developer Certificate of Origin](https://developercertificate.org/): al firmar, certifica que escribió el cambio o que tiene derecho a enviarlo bajo la licencia del proyecto. Añada la firma a cada commit con `git commit -s`, que agrega una línea `Signed-off-by: Su Nombre <su@direccion>`. No se pide ningún acuerdo de licencia de contribuidor (CLA). La integración continua rechaza una solicitud de fusión que contenga un commit sin firmar.

Una solicitud de fusión = un tema; mensajes de commit en imperativo. Un cambio visible añade al mensaje una línea `Nouveauté: <lo que cambia para el usuario, sin jerga>`: aparece en `CHANGELOG.md` y en las notas de versión.

## Licencia
GoldenBrain se publica bajo la Licencia Apache 2.0 (`LICENSE`). Sus contribuciones quedan bajo las mismas condiciones.
