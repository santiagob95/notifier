> **Actualización de alcance, 26/10/2026:** el usuario confirmó que alcanza con detectar funciones publicadas para comprar, sin consultar butacas. La captura de stock indicada en esta investigación histórica ya no es un requisito ni un bloqueo. Ver [criterio vigente](criterio-de-alerta.md) y [README](../README.md) para la implementación. El documento siguiente conserva los hallazgos y el contexto de la fase inicial.
# Investigación técnica: IMAX Norcenter Ticket Monitor

Fecha: 26 de octubre de 2026, Argentina. La consulta final desde Python fue a las 19:37 ART (22:37 UTC).

**Resultado:** existe una consulta JSON pública que utiliza el propio sitio para mostrar fechas, cines, formatos y funciones. Se pudo consultar directamente desde Python sin navegador, cookies ni autenticación. Esto permite detectar funciones publicadas y seleccionables. **No se validó todavía disponibilidad real de butacas:** la respuesta no contiene stock ni estado de agotado, y el flujo de compra probado requiere iniciar sesión.

No se implementó el monitor, no se configuró GitHub Actions y no se enviaron mensajes de Telegram.

## 1. Método y alcance de la verificación

Se descargaron páginas públicas y el JavaScript enlazado por ellas. La URL de la API se obtuvo del HTML de la ficha, y el método HTTP del JavaScript que la consume. Después se hicieron consultas reales, limitadas a películas identificadas en el sitio. No se enumeraron identificadores ni se buscaron rutas por fuerza bruta.

Se verificó acceso HTTP primero con PowerShell y luego con Python `urllib.request`. La prueba de Python devolvió HTTP 200 y JSON válido. No se ejecutó una prueba específica con `requests`: el entorno no trae ese paquete y no se completó su instalación. El protocolo observado es un GET ordinario; `requests` es la opción recomendada para implementarlo. No se necesitó Playwright ni una sesión de navegador.

Las capturas de JSON adjuntas son respuestas reales, no ejemplos inventados. Son una fotografía del momento de consulta; los horarios pueden cambiar.

## 2. URLs y métodos

| Recurso | Método | Parámetros y resultado observado |
|---|---|---|
| https://www.todoshowcase.com/ | GET | HTTP 200, HTML con títulos y enlaces que contienen `filmid`, incluida cartelera IMAX y venta anticipada. |
| https://entradas.todoshowcase.com/showcase/ | GET | HTTP 200, catálogo HTML con enlaces `pelicula.aspx?filmid=...` y títulos en `h3.name`. |
| https://entradas.todoshowcase.com/showcase/pelicula?filmid=6234&house_id=3250 | GET | HTTP 200. Ficha de Godzilla Minus Zero. Incluye la URL de la API y llama a `LoadFilmTree(6234)`. |
| https://entradas.todoshowcase.com/templates/vac/js/pelicula.js?v=639198170282685613 | GET | HTTP 200. Define la petición AJAX GET, renderiza fechas y funciones y construye el enlace de selección. El parámetro `v` fue el observado; no debe fijarse como contrato permanente. |
| https://api.voyalcine.net/films/6234/tree/3250 | GET | HTTP 200, `application/json; charset=utf-8`. Fechas, IMAX Norcenter, formato y tres funciones. Sin cuerpo ni credenciales. |
| https://api.voyalcine.net/films/6016/tree/3250 | GET | HTTP 200. Película identificada, pero `days` vacío. Es un control negativo de funciones IMAX, no un ejemplo confirmado de película futura anunciada. |
| https://api.voyalcine.net/films/6234/tree/3204 | GET | HTTP 200. Misma película en Showcase Norcenter común, formatos 2D y otras funciones. |
| https://entradas.todoshowcase.com/showcase/boleteria_plus?filmid=6234&house_id=3250 | GET | HTTP 200. Formulario ASP.NET con IMAX Norcenter seleccionado y selector de formato IMAX-Subtitulado. |
| https://entradas.todoshowcase.com/showcase/pelicula.aspx?filmid=6234&perf=572772&cinema=18&date=2026-11-03&show=87639A | GET | Enlace construido exactamente como lo hace el JavaScript, con valores de la respuesta. La navegación termina en `https://entradas.todoshowcase.com/showcase/ingresar.aspx#heading1`, HTTP final 200. No se llegó a asientos. |

La ruta general **observada** de funciones es `https://api.voyalcine.net/films/{filmid}/tree/{house_id}`. Se validaron las tres combinaciones de la tabla; no se afirma que cualquier ID sea válido. No se encontró ni se verificó un endpoint JSON de catálogo general.

La boletería alternativa declara formularios POST y manejadores `__doPostBack` para sus selectores. Esas declaraciones se observaron en el HTML; **no se ejecutaron los POST ni se validó su respuesta**. Reproducirlos requeriría preservar los campos ocultos y la sesión de ASP.NET. El GET JSON es más simple para obtener funciones.

## 3. Confirmación del complejo e identificadores

`house_id=3250` corresponde a **IMAX Theatre (Norcenter)** en el flujo consultado. Evidencias independientes dentro del sitio:

- El bloque IMAX de la portada enlaza fichas con ese parámetro.
- El GET de funciones filtrado por 3250 devuelve `name: "IMAX Theatre (Norcenter)"` e `id: 18`.
- La boletería con `house_id=3250` devuelve el selector de cine con `value="18"` y el mismo nombre.

| Identificador | Valor observado | Uso |
|---|---:|---|
| `house_id` | 3250 | Filtro IMAX en la ficha y último segmento de `/tree/3250`. |
| `cinema.id` | 18 | Cine IMAX en JSON; se envía como `cinema=18` al seleccionar una función. |
| `ewaveId` | 3204 | También aparece en IMAX. No equivale al filtro IMAX ni sirve para distinguirlo del cine común. |
| `cinema.id` de Norcenter común | 13 | La consulta `/tree/3204` devuelve Showcase Norcenter con formatos 2D. |
| ID HTML del bloque IMAX | `cartelera_cine_40219` | Identificador de interfaz de la portada, no parámetro para la API. |

Para evitar falsos positivos, verificar el filtro 3250, el `cinema.id=18`, el nombre del cine y un formato IMAX. Si cambian o se contradicen, registrar anomalía y no notificar automáticamente.

## 4. Estructura real de respuesta

Fragmento de la respuesta positiva; se omiten otras dos funciones:

```json
{
  "id": 6234,
  "name": "Godzilla Minus Zero",
  "days": {
    "2026-11-03": [
      {
        "id": 18,
        "name": "IMAX Theatre (Norcenter)",
        "ewaveId": 3204,
        "formats": [
          {
            "formatDescription": "IMAX-Subtitulado",
            "showId": "87639A",
            "performances": [
              {"performanceId": 572772, "showTime": "13:50"}
            ]
          }
        ]
      }
    ]
  }
}
```

Respuesta negativa real completa:

```json
{
  "id": 6016,
  "name": "Avengers Endgame: Bonus - INFINITY VISION",
  "days": {}
}
```

`days` contiene fechas; cada fecha contiene cines, cada cine formatos y cada formato funciones. Cambiar la fecha en la interfaz lee ese árbol ya descargado: no hace falta consultar cada día por separado. El frontend limita a 120 botones de fecha; conviene recorrer todas las fechas devueltas por la API.

El código contempla horarios con prefijo `N ` para trasnoche. No se obtuvo una respuesta real con ese caso, por lo que la interpretación de su fecha efectiva deberá verificarse antes de filtrar horarios de madrugada.

## 5. Descubrimiento de Dune 3

Los dos catálogos consultados traen los títulos y enlaces en el HTML inicial. En la portada, cambiar de complejo muestra u oculta bloques precargados; no requiere otra consulta de películas. En la copia descargada no apareció texto Dune/Duna. Esto describe esas dos fuentes, no prueba ausencia en todos los sistemas de Showcase.

Procedimiento recomendado:

1. Consultar una portada cada 30 minutos mientras no haya candidato. La portada principal incluye cartelera general, anticipadas e IMAX. El catálogo de entradas puede servir como segunda fuente si cambia la primera.
2. Leer tarjetas y sus enlaces con BeautifulSoup; obtener el ID con `urllib.parse`, sin buscar números en texto arbitrario. Deduplicar enlaces porque una película aparece en varios bloques.
3. Normalizar mayúsculas, acentos y puntuación; buscar un conjunto explícito de nombres posibles, como Dune: Part Three y Duna: Parte Tres. Estas son variantes propuestas, no títulos observados en Showcase. No aceptar simplemente cualquier título que contenga Dune: podría ser una reposición de las partes anteriores.
4. Validar el candidato con el nombre que devuelve la ficha/API y, si hay ambigüedad, con metadatos de la ficha. Conservar más de un ID si el sitio separa versiones; no asumir una correspondencia única para siempre.
5. Consultar `/films/{filmid}/tree/3250`. La aparición del título o de una ficha **nunca** dispara el aviso.

No se identificó hoy el `filmid` de Dune 3. El enlace de “Próximos Estrenos” observado apunta a `/#aEstrenar`; no se verificó un catálogo independiente y completo asociado a ese fragmento. Por eso no se propone como fuente fiable adicional.

## 6. Qué significa disponibilidad y qué falta validar

Se pueden distinguir estos estados con la evidencia actual:

- **No descubierto:** no se encontró candidato en un catálogo descargado correctamente.
- **Ficha sin funciones IMAX:** película válida y `days: {}` o ausencia de funciones del cine/formato objetivo.
- **Funciones IMAX publicadas:** existen fecha, cine 18, formato IMAX, `performanceId` y `showId`. El frontend convierte esas funciones en botones seleccionables.
- **Disponibilidad de asientos confirmada:** todavía no verificable con la respuesta pública observada.
- **Consulta fallida:** timeout, HTTP de error, HTML inesperado o esquema inválido. Debe ser un error de diagnóstico, no “sin entradas”. El frontend actual usa el mismo mensaje visual tanto para error AJAX como para ausencia de datos; no conviene copiar esa conducta.

El JSON no incluye campos de asientos libres, agotado, inicio de venta ni compra habilitada. El código genera un botón para cada función sin comprobar esos estados. Que una función aparezca allí es evidencia de publicación en el flujo de venta, **no garantía de stock**. Tampoco una redirección a login confirma stock.

Para cumplir literalmente “funciones efectivamente disponibles para comprar”, falta verificar la siguiente etapa con una sesión iniciada. No se necesita compartir usuario ni contraseña.

### Captura manual exacta, si se exige confirmar butacas

En Chrome o Edge, con sesión propia iniciada en Showcase:

1. Abrir DevTools → Network, activar Preserve log, limpiar el listado y abrir la ficha de una película IMAX con horarios.
2. Elegir fecha, formato y horario; llegar hasta selección de precio/asiento, sin reservar butacas ni pagar.
3. Revisar Fetch/XHR y también Doc: ASP.NET puede usar POST de documento o postbacks parciales.
4. Para la solicitud que devuelva disponibilidad, compartir: Request URL, Request Method, Status Code, Content-Type, nombres de parámetros de query/form/payload y el cuerpo de respuesta relevante. Mantener los valores de película, cine, fecha, formato y función; quitar datos personales, cookies, Authorization, tokens, IDs de sesión, campos de autenticación y datos de pago. Si un campo es sensible, conservar el nombre y sustituir su valor por `[REDACTADO]`.
5. Si no hay una respuesta separada, compartir el fragmento de HTML que indique agotado, precios o asientos disponibles y los nombres de los campos del POST que lo produjo.
6. Idealmente repetir con una función agotada, si existe de forma natural, para comparar estados. No generar reservas para provocar agotamiento.

No hace falta un HAR completo ni “Copy as cURL” sin limpiar: pueden incluir secretos. Con esa evidencia se puede decidir si hay un GET público de disponibilidad o si el requisito requiere una sesión autenticada.

## 7. Alternativas y recomendación

| Alternativa | Ventajas | Costos o límites |
|---|---|---|
| HTML de catálogo + GET JSON de funciones | Pocas solicitudes, sencillo de probar, no requiere navegador ni sesión para lo verificado. | API interna sin contrato público; no informa stock. |
| Formularios de `boleteria_plus` | Acceso al flujo alternativo real del sitio. | Postbacks, campos ocultos y posible login; más mantenimiento. No se validó disponibilidad con ellos. |
| Playwright | Permite observar la interfaz y solicitudes tras ejecutar JS. | Más dependencias y tiempo de ejecución; no elimina login ni asegura acceso al stock. Hoy no hace falta para catálogo/funciones. |

**Recomendación:** `requests` + BeautifulSoup para descubrir IDs y `requests` + JSON para consultar funciones. No implementar Playwright por anticipado. Resolver primero si basta alertar “funciones IMAX publicadas” o completar la verificación de stock para conservar el requisito estricto.

Una vez cerrado ese punto, el diseño puede usar una consulta de catálogo por ejecución mientras no haya ID y una de funciones por ID conocido; refrescar el catálogo periódicamente para detectar variantes nuevas. Evitar consultar cada función individualmente salvo que sea indispensable para verificar stock.

Para la segunda fase: persistir identificadores de funciones ya notificadas en almacenamiento durable de GitHub, serializar ejecuciones y registrar el envío solo tras una respuesta satisfactoria de Telegram. Una clave propuesta es `(filmid, cinema.id, performanceId)` con fecha/formato guardados como metadatos. Debe confirmarse la estabilidad de esos IDs. El plan todavía no valida permisos, persistencia ni ejecución desde un runner de GitHub.

Los tests deberán cubrir ficha sin funciones, otro cine, formato no IMAX, respuesta inválida, errores HTTP, funciones repetidas y nuevas funciones. Si se valida un campo de stock, agregar casos disponible/agotado. La definición de trasnoche y los cambios de identificadores también necesitan cobertura.

## 8. Evidencia adjunta

- `evidencia/funciones-imax-6234.json`: respuesta positiva completa obtenida desde Python.
- `evidencia/sin-funciones-imax-6016.json`: respuesta con `days` vacío.
- `evidencia/funciones-norcenter-6234.json`: comparación con Norcenter común.
- `evidencia/consulta-python.json`: método, URL, estado, hora y cabeceras seleccionadas de la prueba Python. Sin cookies ni credenciales.

Repositorio y Telegram: para continuar alcanza con la URL del repositorio. El token no es necesario para esta investigación; en implementación se configurará directamente en GitHub Secrets, junto con el destino de Telegram, sin almacenarlo en código ni archivos versionados.
