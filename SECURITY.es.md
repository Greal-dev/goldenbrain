# Seguridad

[English](SECURITY.md) · [Français](SECURITY.fr.md) · [Deutsch](SECURITY.de.md) · Español

## Informar de una vulnerabilidad
No publique un ticket público. Utilice el informe privado de GitHub (pestaña «Security», «Report a vulnerability»). Describa el problema, la versión (commit) y una forma de reproducirlo. En la medida de lo posible, se enviará un acuse de recibo.

## Modelo de amenazas
- GoldenBrain es una herramienta **local y de un solo usuario**: el servidor escucha en `127.0.0.1` y no tiene autenticación. No lo exponga nunca en una red.
- Lanza arneses de agentes de IA con los derechos de su sesión, a menudo en modo sin confirmación (`config.exemple.toml`). Un agente puede, por tanto, leer y modificar lo que su cuenta puede leer y modificar: confíele tareas en consecuencia.
- Un contenido externo leído por un agente (página web, correo electrónico) puede contener instrucciones maliciosas; la consigna común pide no tratarlo nunca como una orden, sin que ello sea una garantía.
- Los arneses gestionan sus propias credenciales. GoldenBrain solo guarda los secretos opcionales de los conectores (el token del bot de Telegram): leídos de una variable de entorno o escritos por los Ajustes fuera del repositorio — cifrados con DPAPI en Windows, archivo legible solo por su cuenta (0600) en los demás sistemas. Un secreto nunca se registra ni se escribe en el vault.
