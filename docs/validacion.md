# Validación de la implementación

Fecha: 26 de octubre de 2026.

- Python 3.12 en Windows, dependencias fijadas en requirements.txt y requirements-dev.txt.
- **63 tests unitarios pasaron**. Se probaron detección y deduplicación, catálogo alternativo, separación de Norcenter común e IMAX, coincidencia de títulos, respuestas vacías/inválidas, errores HTTP, control de SHA en persistencia y envíos Telegram confirmados/rechazados/inciertos.
- Simulación real con `python -m imax_notifier --mode dry-run`: catálogo descargado correctamente; 0 películas candidatas para Dune 3, 0 funciones nuevas. No se envió ningún mensaje ni se escribió estado.
- Prueba HTTP directa usando requests y el cliente de funciones de la implementación: película de referencia 6234 / Godzilla Minus Zero; se validaron 3 funciones en el cine IMAX 18. Se usó una configuración de referencia sólo en esa prueba, sin cambiar config.toml y sin conectar Telegram.
- Ambos workflows se pudieron leer como YAML. Los tests verifican cron, concurrencia y uso de Secrets. Las referencias fijadas de actions/checkout y actions/setup-python se resolvieron desde los tags oficiales v7 de GitHub.

No se ejecutó un workflow real en la cuenta del usuario ni se probó su token de Telegram: no están disponibles para esta sesión. Las llamadas de persistencia GitHub y envío Telegram se probaron con respuestas simuladas, incluidos errores y conflictos. La activación requiere publicar los archivos, cargar Secrets y ejecutar los modos de prueba descritos en README.md.

No se verifican butacas: el criterio aceptado es la publicación de funciones seleccionables. El cron de GitHub es periódico y puede sufrir retrasos.
