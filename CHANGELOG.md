# Cambios

Qué cambia en cada versión y en qué fuente se apoya. Las citas son literales: si una
regla y la norma discrepan, la norma tiene razón y la regla es un bug.

Las versiones anteriores a 0.4.1 se describen en sus
[releases](https://github.com/easybytehub/verifactu-lint/releases).

## [0.4.1] — 2026-10-03

Correcciones a partir del estudio **S1** de EasyxLab, que pasó la herramienta por 195
ficheros de registros publicados en repositorios abiertos. No encontró ningún `ERROR`
falso (0 de 22); sí seis problemas de diagnóstico, severidad y cobertura (I-1 a I-6),
que son los que se corrigen aquí. Sobre ese mismo corpus, 0.4.1 cambia el resultado de
9 ficheros: añade los hallazgos nuevos que se describen abajo y pasa uno de `aviso` a
`incompleto` (I-5). No quita ningún hallazgo.

### Reglas nuevas

**`RRSIF053` — `FechaHoraHusoGenRegistro` lleva huso horario (I-1).** `ERROR` si
falta el huso, si el valor no es una fecha y hora en el formato exigido o si el campo
no se informa; `AVISO` si lleva fracciones de segundo.

La exigencia es de la propia orden, no sólo de los ejemplos:

- Orden HAC/1177/2024, **art. 7.g)** (BOE núm. 260, 28-10-2024, pág. 137534): «La
  fecha y hora de generación de cada registro de facturación deberá incluir el huso
  horario aplicado en el momento de la generación del registro, todo ello de acuerdo
  con lo especificado en los artículos 10.c) y 11.c).»
- Su **anexo, ap. 2.3** (bloque «RegistroAlta», pág. 137548) **y 2.4** («RegistroAnulacion»,
  pág. 137550), campo `FechaHoraHusoGenRegistro`, campo obligatorio: «Fecha, hora y huso
  horario de generación del registro de facturación. El huso horario es el que está
  usando el sistema informático de facturación en el momento de generación del registro
  de facturación.» Formato: «DateTime. Formato: YYYY-MM-DDThh:mm:ssTZD (ej:
  2024-01-01T19:20:30+01:00) (ISO 8601)».
- AEAT, **Diseños de registro de facturación v1.0** (`DsRegistroVeriFactu.xlsx`), mismo
  campo, mismo texto: «DateTime. Formato: YYYY-MM-DDThh:mm:ssTZD (ej:
  2024-01-01T19:20:30+01:00) (ISO 8601)».
- El campo entra en la huella: art. 13.1.a), «8.º Fecha, hora y huso horario de
  generación del registro.»

Lo que **no** lo exige, y por eso el hallazgo lo dice en vez de presentarlo como un
rechazo de la AEAT:

- El XSD tipa el campo como `xs:dateTime`, que admite el valor sin huso:
  `<element name="FechaHoraHusoGenRegistro" type="dateTime"/>`.
- AEAT, **Validaciones y errores v1.2.2** (la vigente el 2026-10-03), §3.1.3.20 y
  §3.1.4.6, sólo comprueban esto: «Se validará que la FechaHoraHusoGenRegistro sea menor
  o igual que la fecha del sistema de la AEAT, admitiéndose un margen de error. En caso
  de superar el umbral, se devolverá un aviso de error (no generará rechazo).»

Severidad: la orden dice «deberá incluir», y un valor sin huso contradice el texto
citado. Eso es `ERROR` en esta herramienta («lo que hay en el fichero contradice la
norma citada»), aunque una remisión pueda no rechazarse. Las fracciones de segundo son
otra cosa: el formato del anexo no las incluye, pero `xs:dateTime` las admite y nada en
la norma dice que invaliden el registro, así que no se afirma el incumplimiento:
`AVISO`. `Z` se acepta como huso (es el designador de UTC de ISO 8601).

Fuera de alcance por ahora: los campos de fecha y hora de los registros de **evento**
(`FechaHoraHusoGenEvento` y los de los datos propios), que el anexo (ap. 2.5) define con
el mismo formato pero que no forman parte de la incidencia I-1.

**`RRSIF050` — los elementos del registro están donde el esquema los prevé (I-2).**
`ERROR`. Un solo hallazgo por fichero que nombra cada ruta inesperada
(`RegistroAlta/Factura`, `RegistroAlta/Huella/Hash`…), en cuántos registros aparece y,
cuando el elemento inventado lleva dentro datos que el esquema espera en el bloque
padre, cuáles son («Lleva dentro TipoFactura, Desglose, CuotaTotal y ImporteTotal»).
Va **el primero** del informe, y los demás hallazgos de esos registros llevan una nota
que remite a él. Se anotan, no se suprimen: un elemento de más no debe esconder una
cadena rota de verdad.

- Orden HAC/1177/2024, **arts. 10.c) y 11.c)** (pág. 137537): «Estructura, contenido y
  formato según se describe en el apartado 3 del anexo.» Y el **anexo, ap. 3** (pág.
  137556): el fichero «tendrá la estructura, contenido y formato de campos que se
  describen a continuación», con el bloque 3 «RegistroAlta» o el 4 «RegistroAnulacion».
- `SuministroInformacion.xsd`, `RegistroFacturacionAltaType` y
  `RegistroFacturacionAnulacionType`: secuencias cerradas, sin `xs:any`. La lista de
  hijos admitidos se contrasta con el XSD versionado en un test.

No es una validación XSD: no comprueba orden ni obligatoriedad, sólo los bloques que
leen las reglas, que son los que pueden provocar la cascada engañosa.

**`RRSIF051` — la anulación identifica la factura con sus tres campos (I-3).** `ERROR`.
Es el equivalente, para la anulación, de lo que `RRSIF030` comprueba en el alta. Si el
`IDFactura` de una anulación usa los nombres del alta (`IDEmisorFactura`,
`NumSerieFactura`, `FechaExpedicionFactura`), lo dice con esas palabras; hasta 0.4.0 lo
único visible era `RRSIF001` (la huella no cuadra), que ahora lleva una nota con la
causa.

- Orden HAC/1177/2024, **anexo, ap. 2.4** (pág. 137549), agrupación `IDFactura`:
  `IDEmisorFacturaAnulada`, `NumSerieFacturaAnulada` y `FechaExpedicionFacturaAnulada`,
  los tres marcados como obligatorios («Fuente estilo subrayado o 1(superíndice). Campo
  obligatorio.», ap. 7, pág. 137562).
- `SuministroInformacion.xsd`, `IDFacturaExpedidaBajaType`: los tres elementos, sin
  `minOccurs="0"`.
- Art. 13.1.b): los tres entran en la huella de la anulación.

**`RRSIF052` — las fechas de expedición van en `dd-mm-aaaa` (I-4).** `ERROR`, en
`IDFactura/FechaExpedicionFactura`, `IDFactura/FechaExpedicionFacturaAnulada` y
`Encadenamiento/RegistroAnterior/FechaExpedicionFactura`. Distingue la fecha ISO (y dice
cómo se escribe) de la que tiene la forma pero no es una fecha del calendario.

- Orden HAC/1177/2024, **anexo, ap. 2.3** (pág. 137546) y **2.4** (pág. 137549):
  «Fecha (dd-mm-yyyy)».
- `SuministroInformacion.xsd`, tipo `fecha`: `<length value="10"/>` y
  `<pattern value="\d{2,2}-\d{2,2}-\d{4,4}"/>`.
- AEAT, **Validaciones y errores v1.2.2**, §3.1: «Validaciones sintácticas: en ellas se
  valida el formato, longitud, obligatoriedad del contenido […]. Cuando estos errores se
  hayan producido a nivel de registro (agrupaciones RegistroAlta o RegistroAnulacion
  dentro del bloque RegistroFactura), provocarán el rechazo del registro».

### Cambios en reglas existentes

**`RRSIF027`: un fin sin el origen de la cadena en el fichero es `INCOMPLETO` (I-5).**
Un evento 02 sin 01 previo sigue siendo `AVISO` cuando el 01 tendría que estar en el
fichero: porque contiene el origen de la cadena (un evento con `PrimerEvento=S`) o
porque antes del fin ya hubo otro 01 o 02. Si no, el 01 puede estar en un fichero
anterior y aquí no se puede determinar: `INCOMPLETO`, como ya hacía `RRSIF028` en el
mismo caso.
Es la regla de la casa: afirmar un incumplimiento que no existe es peor que callar uno
que sí. El caso de S1 era un fichero de un solo evento cuyo `EventoAnterior` era,
precisamente, un 01.

**`RRSIF001`: la «Calculada» es la de los importes tal como están escritos (I-6).** La
orden admite `21.4` y `21.40` como el mismo importe y cada forma da una huella distinta;
la herramienta las prueba todas antes de afirmar nada, y eso no cambia. Lo que cambia
es qué enseña: hasta 0.4.0, la primera variante (`21.4` para un `21.40` escrito), y
quien comparaba con su propio cálculo sobre el valor literal veía un tercer hash. Ahora
la «Calculada» es la de los importes tal como están escritos, con la cadena canónica
que la produce, y debajo las demás formas admisibles con su huella.

### Compatibilidad

- **API pública**: sin cambios incompatibles. Se añaden `Registro.fuera_de_esquema`
  (con valor por defecto), `registros.ElementoInesperado`, `registros.ID_FACTURA` y el
  módulo `reglas/estructura.py`. `lee`, `lee_eventos`, `audita`, `audita_eventos` y
  `cli.main` mantienen su firma.
- **Salida**: JSON y SARIF mantienen sus campos. Cambian el texto del `detalle` de
  `RRSIF001`, el orden de los hallazgos (las causas raíz `RRSIF050` y `RRSIF051`, primero)
  y la severidad descrita de `RRSIF027`.
- **Paquete**: sigue siendo Python puro, sin dependencias en tiempo de ejecución
  (`py3-none-any`).
