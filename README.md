# IMAX Norcenter Ticket Monitor

Detecta **funciones publicadas para comprar de Dune: Part Three en IMAX Theatre (Norcenter)** y avisa por Telegram con fechas, horarios y enlace de compra. Corre en GitHub Actions cada 30 minutos, sin servidor propio ni PC encendida.

**Criterio acordado:** alcanza con que Showcase publique funciones seleccionables. No se consulta el stock de butacas. La aparición de una ficha o un anuncio sin funciones no dispara avisos.

## Cómo funciona

1. Consulta el catálogo público y descubre `filmid` por los títulos configurados en `config.toml`. Acepta variantes explícitas de Dune/Duna, Part Three/Parte Tres/3/III y sufijos de formato; no confunde la película con Dune o Part Two.
2. Consulta `GET https://api.voyalcine.net/films/{filmid}/tree/3250` para los IDs descubiertos y los ya conocidos.
3. Valida título, `cinema.id=18`, nombre IMAX Theatre (Norcenter), formato IMAX y funciones con identificadores y horarios válidos. Omite fechas anteriores al día actual en Argentina.
4. Compara `(filmid, cinema.id, performanceId)` con lo ya notificado y envía solamente funciones nuevas. Agrupa hasta 15 funciones por mensaje.
5. Guarda el estado en `monitor-state`, una rama separada del mismo repositorio, usando el `GITHUB_TOKEN` automático de Actions.

Habitualmente hace una consulta al catálogo por ejecución mientras no aparece la película. Una vez descubierta, agrega una consulta de funciones por ID. Sólo usa el catálogo alternativo si falla el principal. No descarga imágenes ni consulta cada día o función por separado.

## Activación en GitHub

El código debe estar en la **rama predeterminada** del repositorio. El ZIP entregado contiene una carpeta `imax_notifier`: sus archivos, incluida `.github`, deben quedar en la raíz del repositorio, no dentro de otra carpeta.

Si el repositorio sigue vacío, desde la carpeta extraída:

```sh
git init -b main
git add .
git commit -m "Add IMAX ticket monitor"
git remote add origin https://github.com/santiagob95/imax_notifier.git
git push -u origin main
```

Estos comandos usan tu autenticación habitual de GitHub; no introduzcas tokens en la URL remota. El paquete descargable no contiene `.git`.

Después:

1. En Telegram, abrí tu bot y enviá `/start`. Si todavía no tenés bot, crealo mediante [BotFather](https://t.me/BotFather).
2. En GitHub → **Settings → Secrets and variables → Actions**, agregá estos dos **Repository secrets**:

   | Nombre | Valor |
   |---|---|
   | `TELEGRAM_BOT_TOKEN` | Token entregado por BotFather. |
   | `TELEGRAM_CHAT_ID` | ID numérico del chat que recibirá los avisos. |

3. Habilitá Actions si GitHub lo solicita. El workflow declara `contents: write` para persistir el estado; si una política de la cuenta/organización lo impide, deberá permitirlo para este workflow y la rama `monitor-state`. No hace falta un PAT adicional.
4. Verificá que el workflow **Tests** termine correctamente.
5. En **Actions → Monitor IMAX → Run workflow**, elegí `test-telegram` para comprobar el bot y el destino. Envía un mensaje de prueba identificado como tal.
6. Ejecutá `dry-run`: consulta el sitio y el estado, pero no envía ni escribe. Después ejecutá `monitor` una vez y revisá los logs. El cron continuará automáticamente.

`monitor-state` se crea cuando hay estado nuevo que guardar. Antes de descubrir Dune 3 puede no existir. No la borres ni la fusiones con `main`: allí está el historial que evita duplicados. Si un envío termina con resultado incierto, seguí el apartado de recuperación.

**Estado de entrega:** el código fue probado localmente, pero la publicación, los Secrets y la ejecución real en tu cuenta de GitHub requieren completar los pasos anteriores. No hay un monitor activado por el simple hecho de descargar este proyecto.

## Obtener TELEGRAM_CHAT_ID

Usá el comando local siguiente con el token cargado en una variable de entorno. Sólo imprime IDs de chats presentes en las actualizaciones pendientes del bot, sin mostrar contenido de mensajes ni el token:

```sh
python -m imax_notifier --mode chat-id
```

Debe existir un mensaje reciente `/start`. Si el bot ya utiliza un webhook o hay otro programa consumiendo sus actualizaciones, usá un bot dedicado o el ID que ya tenga esa integración. No se elimina ningún webhook automáticamente. No publiques la salida ni capturas que contengan secretos.

## Instalación y ejecución local

Requiere **Python 3.12 o superior**. Para Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m imax_notifier --mode dry-run
```

En Linux/macOS, reemplazá el ejecutable de la venv por `.venv/bin/python`.

La simulación no necesita credenciales. Para consultar el chat ID o enviar mensajes localmente, podés cargar las variables sin escribir el token en el historial de comandos:

```powershell
$botTokenSeguro = Read-Host 'Token de Telegram' -AsSecureString
$env:TELEGRAM_BOT_TOKEN = [System.Net.NetworkCredential]::new('', $botTokenSeguro).Password
.\.venv\Scripts\python.exe -m imax_notifier --mode chat-id
$env:TELEGRAM_CHAT_ID = Read-Host 'ID del chat'
.\.venv\Scripts\python.exe -m imax_notifier --mode test-telegram
.\.venv\Scripts\python.exe -m imax_notifier --mode monitor
```

Al terminar podés quitar esas variables de la sesión de PowerShell:

```powershell
Remove-Item Env:TELEGRAM_BOT_TOKEN
Remove-Item Env:TELEGRAM_CHAT_ID
```

El modo local hace **una consulta completa y termina**. Guarda estado en `.local/state.json`, ignorado por Git. No ejecutar dos procesos simultáneamente con ese mismo archivo. Para usar otra ruta: `--state ruta/estado.json`. No combines un monitor local que envía y otro de Actions con estados independientes: cada uno tiene su propio historial y podría avisar la misma función.

## Configuración

`config.toml` contiene variantes del título. Si Showcase utiliza otra denominación, agregá su nombre exacto tras verificar que corresponde a la tercera película. No se usa un simple substring “Dune”. Un nuevo ID se valida de nuevo contra el nombre que devuelve la API antes de notificar.

Los identificadores del cine están fijados y validados para este proyecto:

| Campo | Valor | Significado |
|---|---:|---|
| `house_id` | 3250 | Filtro público IMAX. |
| `cinema.id` | 18 | IMAX Theatre (Norcenter) en la API. |
| `ewaveId` | 3204 | También aparece en el Norcenter común; no sirve para distinguir IMAX. |

No configurar `filmid=6234`: es Godzilla Minus Zero y sólo se usa como evidencia histórica en los tests. El monitor descubre el ID de Dune 3 automáticamente.

## Persistencia, errores y recuperación

La rama `monitor-state` contiene `state/monitor.json` con IDs descubiertos, funciones notificadas y, excepcionalmente, un envío pendiente. No contiene tokens, cookies ni el chat ID. Las escrituras utilizan el SHA de la versión anterior; un conflicto falla en vez de sobrescribir otro proceso. GitHub Actions serializa las ejecuciones con `concurrency` y no cancela una ejecución activa para iniciar otra.

Antes de enviar un aviso se guarda una reserva de sus funciones. Después de que Telegram confirma el envío, se marcan como notificadas. Si Telegram rechaza explícitamente el mensaje, se libera la reserva para el siguiente intento. Los HTTP 429 se reintentan hasta dos veces respetando esperas de hasta 60 segundos.

Si un timeout, una interrupción o un fallo al guardar la confirmación deja el resultado incierto, el monitor **no vuelve a enviar automáticamente**. El workflow falla con un mensaje de diagnóstico y los siguientes envíos quedan detenidos hasta resolverlo. Esto evita duplicados en el intervalo entre Telegram y GitHub, que no comparten una transacción.

Para recuperar:

1. Revisá el chat de Telegram y el campo `pending` en `monitor-state/state/monitor.json`.
2. Ejecutá **Run workflow** con `resolve-sent` si el aviso llegó. Marca esas funciones como enviadas.
3. Si confirmaste que no llegó, ejecutá `resolve-retry`. Libera la reserva para que `monitor` pueda avisar las funciones que sigan publicadas.
4. Ninguna resolución envía mensajes. Ejecutá `monitor` o esperá el siguiente cron.

No elijas `resolve-retry` si el mensaje sí llegó: habilitaría un duplicado. La prueba manual `test-telegram` no usa el historial del monitor.

Los GET públicos y de estado tienen timeouts de 5 s de conexión y 25 s de lectura, con hasta 3 intentos para fallos de red/429/5xx. Un `Retry-After` superior a 60 s difiere el trabajo a otra ejecución. Las escrituras de estado y los envíos ambiguos no se repiten a ciegas. Errores de esquema o de estado no se interpretan como “sin funciones”. No se imprimen excepciones HTTP crudas ni URLs con el token.

Si falla el catálogo pero ya se conocen IDs, se siguen consultando esos IDs y se reporta el fallo al final. Si una respuesta de funciones es inválida, se detiene la detección sin enviar resultados parciales de esa consulta.

## Frecuencia y límites

- El cron es `7,37 * * * *` (UTC): cada 30 minutos, evitando el inicio de la hora. GitHub puede retrasar o descartar ejecuciones bajo carga; no es una garantía de aviso en exactamente 30 minutos. [Documentación de GitHub](https://docs.github.com/en/actions/how-tos/troubleshoot-workflows).
- En repositorios públicos, GitHub puede desactivar el cron tras 60 días sin actividad. Revisá Actions si el seguimiento dura mucho. [Workflows inactivos](https://docs.github.com/en/actions/managing-workflow-runs-and-deployments/managing-workflow-runs/disabling-and-enabling-a-workflow).
- El consumo depende de tu plan y cuota de GitHub Actions. El monitor no crea servidores ni un servicio de pago externo.
- La API utilizada es interna del sitio, sin contrato público. Los validadores y tests detectan cambios de estructura, pero cambios de títulos o IDs pueden requerir mantenimiento.
- Se confía en las funciones publicadas por Showcase. No se comprueban butacas, precios ni reserva final. Se conserva la hora que publica el sitio, incluido el prefijo `N ` de trasnoche; no se inventa su fecha efectiva. Se excluyen días anteriores a hoy, no horas dentro del día actual.
- La deduplicación depende de que Showcase conserve el `performanceId` de cada función. Si reemplaza un ID por otro, se considera una función nueva. Los IDs notificados se conservan aunque desaparezcan temporalmente del sitio.

## Investigación y pruebas

- [Criterio de alerta aceptado](docs/criterio-de-alerta.md).
- [Investigación original](docs/investigacion.md), con URLs y ejemplos de respuestas.
- [Evidencia IMAX real](docs/evidencia/funciones-imax-6234.json), [sin funciones IMAX](docs/evidencia/sin-funciones-imax-6016.json) y [Norcenter común](docs/evidencia/funciones-norcenter-6234.json).

Los tests usan respuestas históricas reales y datos sintéticos de Dune claramente identificados. Cubren detección, catálogo alternativo, cine/formato incorrectos, ausencia de funciones, títulos parecidos, deduplicación, hora de Argentina, persistencia, conflicto de SHA, errores HTTP y envíos confirmados/rechazados/inciertos. No consultan Internet ni envían Telegram.

Referencias de integración: [Telegram Bot API](https://core.telegram.org/bots/api), [GitHub Contents API](https://docs.github.com/en/rest/repos/contents), [GitHub Git refs](https://docs.github.com/en/rest/git/refs).
