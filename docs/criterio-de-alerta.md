# Criterio de alerta acordado

Actualizado el 26 de octubre de 2026 por indicación del usuario: **no hace falta comprobar disponibilidad de butacas; alcanza con detectar entradas a la venta a través de funciones publicadas y seleccionables.**

El monitor considera venta habilitada cuando la API pública que usa Showcase devuelve:

- Una película cuyo nombre coincide con una variante explícita de Dune: Part Three.
- Cine `id=18` y nombre IMAX Theatre (Norcenter), consultado mediante `house_id=3250`.
- Un formato identificado como IMAX.
- Una o más funciones con `performanceId`, `showId`, fecha actual o futura y horario válido.

La sola ficha, el título en cartelera, una etiqueta de anticipada o `days: {}` no generan avisos. Tampoco funciones del Norcenter común o de formato 2D.

No se inspecciona stock, no se inicia sesión en Showcase y no se reserva ninguna entrada. No se necesita la captura de DevTools que se había solicitado para el requisito anterior de butacas.

Los avisos incluyen fecha, hora publicada y enlace público a la película filtrada por IMAX. Indican que no se consultaron butacas. Las funciones ya notificadas no se repiten salvo una decisión explícita de recuperación o un cambio de ID por parte del sitio.
