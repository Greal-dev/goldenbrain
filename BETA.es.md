# Hacerse probador

[English](BETA.md) · [Français](BETA.fr.md) · [Deutsch](BETA.de.md) · [Español](BETA.es.md)

Las versiones beta llegan a la rama `beta` antes que a `main`. Los probadores detectan lo que escapa a las pruebas automáticas: un vault real, un harness de agente real, una máquina real.

## Unirse
1. Instalación con git (la instalación habitual): abra *Ajustes → Instalación y versión → Actualización*, ponga **Canal** en *Beta*.
2. Pulse **Actualizar** en el aviso: GoldenBrain pasa a la rama `beta` y se reinicia. Un cambio local en el código bloquea el paso; no se sobrescribe nada.
3. Para volver, elija *Estable*: el cambio se hace en la siguiente actualización.

Un cambio de canal nunca toca su vault: solo cambia el código de la aplicación.

## Escenarios a probar
Pruebe los que pueda, en un vault de prueba o en el suyo (con copia de seguridad previa).
1. **Instalar y arrancar** en una máquina limpia; se abre la pantalla de inicio.
2. **Crear una tarea**, darle un contenedor, abrir su ficha.
3. **Ejecutar un turno de agente** con su harness habitual; la ficha vuelve rellenada.
4. **Validar** una tarea terminada; sale de la lista de tareas abiertas.
5. **Actualizar**: pasar de estable a beta y volver; el servidor se reinicia cada vez.
6. **Notas**: abrir el segundo cerebro, seguir un enlace, mirar el grafo.
7. **Informar**: *Ajustes → Informar de un problema* abre un formulario rellenado.

## Comunicar un resultado
- **Algo falla**: formulario *Bug report* (el botón de la aplicación rellena la versión, con el canal, y el sistema). Indique el escenario, lo que vio y lo que esperaba.
- **Todo bien**: un mensaje breve en Discussions, categoría *Beta*, con la versión probada.
- No pegue nunca datos personales: nombres, rutas de su máquina, extractos del vault, tokens.
