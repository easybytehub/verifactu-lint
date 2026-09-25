# verifactu-lint

[![ci](https://github.com/easybytehub/verifactu-lint/actions/workflows/ci.yml/badge.svg)](https://github.com/easybytehub/verifactu-lint/actions/workflows/ci.yml)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/easybytehub/verifactu-lint/badge)](https://scorecard.dev/viewer/?uri=github.com/easybytehub/verifactu-lint)
[![PyPI](https://img.shields.io/pypi/v/verifactu-lint)](https://pypi.org/project/verifactu-lint/)
[![Python](https://img.shields.io/pypi/pyversions/verifactu-lint)](https://pypi.org/project/verifactu-lint/)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue)](LICENSE)

**Comprueba en tu CI que los registros de facturación que genera tu SIF cumplen el RRSIF** (RD 1007/2023 y Orden HAC/1177/2024), antes de que lleguen a un cliente o a la AEAT.

Le pasas el XML que produce tu código y te dice dónde incumple, citando el artículo o el código de error de la AEAT.

```console
$ verifactu-lint registros-generados.xml

verifactu-lint · 1.284 registros · registros-generados.xml

ERROR      RRSIF003 [#412 FA/2026/0412]: La cadena se rompe en este registro
           Declara como huella anterior 9F2C…A31B, y la huella de #411 FA/2026/0411 es 4D77…C0E9.
           Una cadena rota significa que la secuencia conservada no es la que se generó:
           falta un registro por medio, se reordenaron, o se modificó uno después de emitirlo.
           norma: Orden HAC/1177/2024, art. 13 y especificaciones técnicas de la huella

1 error · 0 avisos · 0 sin determinar
```

## Para quién es

**Para quien desarrolla o mantiene un sistema informático de facturación.** Ése tiene los XML por construcción: son los que su código genera antes de remitirlos o conservarlos, y puede pasarlos por aquí en cada cambio.

Es el caso que la herramienta cubre bien, y encaja con el calendario: la obligación de los usuarios llega en 2027, pero **la de los productores y comercializadores venció el 29 de julio de 2025**. Quien está peleándose con esto hoy es quien fabrica el software.

### Dónde existe el XML, y dónde no

Conviene decirlo claro antes de que te lo descargues:

| Situación | ¿Tienes el fichero? |
|---|---|
| **Desarrollas un SIF** — tus tests o tu entorno generan registros | ✅ Sí, siempre |
| Sistema **NO VERI\*FACTU** que exporta sus registros conservados | ⚠️ Sólo si exporta en el formato del registro |
| Requerimiento de la AEAT, o migración entre sistemas | ⚠️ Igual: depende de cómo exporte tu sistema |
| Usuario final de un sistema **VERI\*FACTU** | ❌ No |

Las dos razones, que son de la propia AEAT:

- **Un SIF VERI\*FACTU no está obligado a conservar** los registros que genera, porque ya se los ha remitido a la sede. No hay histórico que auditar.
- **La exportación sólo es obligatoria para los NO VERI\*FACTU**, y la norma no fija su formato: pide «formato electrónico legible» y nada más. Cada fabricante exporta como quiere, así que un fichero exportado puede no ser XML de registros.

Si tu sistema conserva o exporta en el formato del registro, esta herramienta te sirve igual. Si exporta en otra cosa, no — y es mejor saberlo ahora.

## Qué es, y qué no es

Existen ya varias librerías buenas para **generar** registros Verifactu. Ninguna responde a la otra pregunta: *¿lo que estoy generando cumple?*

Eso es lo que hace esta herramienta.

**No es un sistema informático de facturación.** No expide facturas, no genera registros, no los firma y no los remite a la AEAT. Sólo lee. Por tanto no le corresponde emitir declaración responsable alguna, ni la emite.

**Un resultado sin errores no acredita conformidad.** Significa que estas reglas, sobre esos registros, no han encontrado un incumplimiento. La declaración responsable del artículo 13 del RRSIF la emite el productor del SIF bajo su propia responsabilidad, y ninguna herramienta puede emitirla por él.

## Instalación

```bash
pip install verifactu-lint
```

Sin dependencias en tiempo de ejecución: sólo la biblioteca estándar de Python (3.11+).

## Uso

### En tu CI, que es donde tiene sentido

Si desarrollas un SIF, haz que tus tests escriban los registros que genera tu código y pásalos por aquí en cada cambio. Un fallo en el encadenamiento o en el cuadre se ve en el pull request, no en una inspección.

Con salida SARIF los hallazgos aparecen en la pestaña **Security** del repositorio, sin que nadie tenga que abrir un log:

```yaml
name: verifactu
on: [push, pull_request]

permissions:
  contents: read

jobs:
  auditar:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      security-events: write
    steps:
      - uses: actions/checkout@v4
      - uses: easybytehub/verifactu-lint@v0.3.0
        with:
          ficheros: "registros/*.xml"
          fallar: "false"      # que no aborte antes de subir el informe
      - uses: github/codeql-action/upload-sarif@v3
        with: { sarif_file: verifactu-lint.sarif }
```

`fallar: false` es deliberado: sin él, un hallazgo abortaría el job **antes** de subir el SARIF y verías que falla sin poder ver por qué. El fallo lo señala la pestaña Security, que es donde se puede leer.

| Entrada | Por defecto | |
|---|---|---|
| `ficheros` | — | Ficheros a auditar. Admite comodines. |
| `formato` | `sarif` | `texto`, `json` o `sarif`. |
| `estricto` | `false` | Que los avisos también hagan fallar. |
| `fallar` | `true` | Si `false`, el paso no falla aunque haya hallazgos. |
| `salida` | `verifactu-lint.sarif` | Fichero del informe. |
| `version` | la de la action | Versión de `verifactu-lint` a instalar. |

Salidas: `errores`, `avisos` (con `formato: json`) y `fichero-informe`.

La action **fija la versión** que instala en vez de coger la última: una action que instala «lo último» cambia de comportamiento sin que nadie haya tocado nada.

### En la línea de comandos

```bash
# informe legible
verifactu-lint registros.xml

# varios ficheros; cada uno se audita como su propia cadena
verifactu-lint enero.xml febrero.xml

# para tratarlo con jq, o para archivarlo
verifactu-lint registros.xml --formato json

# el mismo SARIF que produce la action, sin la action
verifactu-lint registros/*.xml --formato sarif > verifactu.sarif

# que los avisos también rompan la build
verifactu-lint registros.xml --estricto
```

**Códigos de salida:** `0` sin errores · `1` con errores (o con avisos si `--estricto`) · `2` si el fichero no se pudo leer **o si ninguno contenía registros** — apuntar al XML equivocado no es lo mismo que estar conforme.

### Como librería

```python
from verifactu_lint.registros import lee
from verifactu_lint.reglas import audita

informe = audita(lee("registros.xml"))
for hallazgo in informe.errores:
    print(hallazgo.regla, hallazgo.titulo, hallazgo.referencia)
```

## Las reglas

**Registros de facturación** (alta y anulación):

| Regla | Comprueba |
|---|---|
| `RRSIF001` | La huella declarada sale de los campos del registro |
| `RRSIF002` | La huella tiene 64 caracteres hexadecimales en mayúsculas |
| `RRSIF003` | Cada registro encadena con la huella del anterior |
| `RRSIF004` | `PrimerRegistro` y `RegistroAnterior` son coherentes y hay un único inicio de cadena |
| `RRSIF005` | `TipoHuella` es `01` (SHA-256), el único que admite la lista L12 |
| `RRSIF010` | No hay numeración de factura duplicada |
| `RRSIF011` | El SIF se identifica con NIF + `IdSistemaInformatico` + `NumeroInstalacion` |
| `RRSIF012` | `IndicadorMultiplesOT` es coherente con `TipoUsoPosibleMultiOT` |
| `RRSIF013` | La cadena pertenece a un único obligado tributario |
| `RRSIF030` | `TipoFactura` está entre los ocho de la lista L2 |
| `RRSIF031` | Una rectificativa declara su modalidad y qué factura rectifica |
| `RRSIF032` | Los campos de rectificación no aparecen en facturas normales |
| `RRSIF033` | `ImporteRectificacion` va exactamente en las sustitutivas |
| `RRSIF034` | Una F3 identifica las simplificadas a las que sustituye |
| `RRSIF035` | `Subsanacion` y `RechazoPrevio` son válidos y no se confunden con rectificar |
| `RRSIF040` | El registro de alta lleva desglose |
| `RRSIF041` | `CuotaTotal` = Σ cuotas + Σ recargos *(error AEAT 2006)* |
| `RRSIF042` | `ImporteTotal` = Σ bases + Σ cuotas + Σ recargos *(errores 1210 y 2005)* |
| `RRSIF043` | La cuota de cada línea sale de su base y su tipo *(error 1142)* |
| `RRSIF044` | Base y cuota de una línea llevan el mismo signo *(errores 1140 y 1143)* |
| `RRSIF045` | `Impuesto`, `ClaveRegimen`, calificación y exención existen |
| `RRSIF046` | Lo exento, lo no sujeto y la inversión del sujeto pasivo no repercuten cuota |
| `RRSIF047` | El recargo de equivalencia corresponde a su tipo *(errores 1160 y 1162-1170)* |
| `RRSIF048` | `Macrodato` marca los importes de ±100.000.000 *(errores 1137-1139)* |
| `RRSIF049` | F1, F3 y R1-R4 llevan destinatario *(error 1189)* |

**Registros de evento** — es decir, la modalidad **NO VERI\*FACTU**:

| Regla | Comprueba |
|---|---|
| `RRSIF020` | `TipoEvento` está entre los once del esquema oficial |
| `RRSIF021` | La huella del evento sale de sus nueve campos |
| `RRSIF022` | Formato de `HuellaEvento` |
| `RRSIF023` | Cada evento encadena con la huella del evento anterior |
| `RRSIF024` | `PrimerEvento` y `EventoAnterior` son excluyentes, y hay un único origen |
| `RRSIF025` | Todo registro de evento lleva firma electrónica |
| `RRSIF026` | `DatosPropiosEvento` corresponde al tipo de evento |
| `RRSIF027` | Los arranques y paradas como NO VERI\*FACTU se emparejan |
| `RRSIF028` | Existe registro resumen de eventos |

> Si tu sistema opera en **NO VERI\*FACTU**, esta segunda tabla es la que te concierne. La AEAT es explícita en que esa modalidad es **técnicamente más exigente** que VERI\*FACTU: al no remitir los registros a la sede, la integridad y la trazabilidad hay que demostrarlas con el registro de eventos, su encadenamiento propio y su firma. Mucha implementación la elige creyendo que es la opción de menos trabajo.

### Tres severidades, no dos

- **`error`** — incumple. Lo que hay en el fichero contradice la norma citada.
- **`aviso`** — muy probablemente incumple, o incumplirá en cuanto se dé una condición previsible.
- **`incompleto`** — no se puede determinar con este fichero, y el hallazgo dice qué habría que mirar.

`incompleto` existe porque en una herramienta de cumplimiento **afirmar un incumplimiento que no existe es peor que callar uno que sí**: quien lo lee cambia código correcto y deja de creerse el resto del informe. Cuando una regla no puede concluir, lo dice.

Un ejemplo real de esa cautela: la orden admite `123.1` y `123.10` como el mismo importe, y cada forma produce un SHA-256 distinto. Un verificador que calculase sólo una declararía incorrecta una huella que la AEAT acepta. `verifactu-lint` prueba las formas admisibles antes de afirmar nada.

## Validar contra el XSD no es cumplir el reglamento

Es la distinción que justifica esta herramienta, y está demostrada en la suite en vez
de afirmada: **los ejemplos con defectos de este repositorio validan contra los
esquemas oficiales de la AEAT**.

`ejemplos/cadena-rota.xml` es impecable para `SuministroLR.xsd` y tiene la cadena de
huellas partida. `ejemplos/eventos-con-defectos.xml` valida y le faltan los datos
propios de un evento de exportación.

Un esquema comprueba **forma**; no sabe calcular un SHA-256, no conoce el orden de
los registros y no puede saber que a un tipo de evento le corresponde un bloque
concreto. Esa franja —lo estructuralmente correcto y sustantivamente incorrecto— es
donde trabaja `verifactu-lint`.

Los XSD oficiales están versionados en [`esquemas/`](esquemas/) y la suite los usa
para comprobar que los ejemplos son ficheros que un sistema real podría haber
emitido. Sin ese ancla, las pruebas se construirían con la misma interpretación del
reglamento que luego verifican.

## Sobre qué se apoya

- **RD 1007/2023**, de 5 de diciembre — Reglamento de requisitos de los sistemas informáticos de facturación.
- **Orden HAC/1177/2024**, de 17 de octubre — especificaciones técnicas, funcionales y de contenido.
- **AEAT — *Detalle de las especificaciones técnicas para generación de la huella o hash de los registros de facturación*, v0.1.2** (27/08/2024). Los tres vectores de su apartado 6 están en la suite de tests y se ejecutan en cada cambio: son la definición de correcto para el cálculo de la huella.
- **AEAT — *Aclaraciones a dudas de los desarrolladores*, v1.3** (04/12/2025).
- **AEAT — *Listado de códigos de error***. Las reglas que citan un código (1118, 1142, 1189, 2006…) comprueban exactamente lo que rechazaría el validador de la AEAT, y el hallazgo lo dice para que se pueda contrastar.

Cuando una regla y la norma discrepen, la norma tiene razón y la regla es un bug. [Abre un issue](https://github.com/easybytehub/verifactu-lint/issues) citando el apartado.

## Alcance actual

Cubre el encadenamiento, el formato de la huella y la identificación del SIF sobre registros de **alta** y **anulación**, y el encadenamiento, la firma y la coherencia de los registros de **evento**.

Cada fichero se audita detectando qué contiene. Las dos cadenas —facturación y eventos— se auditan por separado porque son independientes: un evento no encadena con una factura ni al revés.

Todavía **no** cubre: los requisitos de conservación de la modalidad NO VERI\*FACTU que no se pueden observar desde un fichero de registros, ni el seguimiento del `NumeroInstalacion` entre ejecuciones. Están en los [issues](https://github.com/easybytehub/verifactu-lint/issues).

## Contribuir

Una regla es una función `list[Registro] -> list[Hallazgo]`. No hay clase base, ni registro por decorador, ni sistema de plugins: escribes la función, la añades a la tupla `REGLAS` de su familia en `src/verifactu_lint/reglas/`, y le pones un test.

Toda regla nueva necesita: la cita normativa concreta, una severidad justificada, y un test con un caso que la dispare y otro que no. Las reglas que producirían ruido en ficheros grandes deben agregar — un hallazgo por campo, no uno por registro.

```bash
git clone https://github.com/easybytehub/verifactu-lint
cd verifactu-lint
python -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest
.venv/bin/python -m ruff check .
.venv/bin/python -m mypy
```

## Procedencia

Cada release publica su procedencia mediante [attestations de GitHub](https://docs.github.com/actions/security-guides/using-artifact-attestations), firmadas con OIDC efímero. No hay ninguna clave privada custodiada por nadie.

```bash
gh attestation verify --owner easybytehub verifactu_lint-*.whl
```

La atestación dice qué commit, qué workflow y qué runner produjeron ese artefacto exacto. Si vas a meter código de terceros en el sistema del que respondes tú, esto es lo que deberías poder comprobar de cualquiera de ellos.

## Licencia

[Apache-2.0](LICENSE).


## Quién lo mantiene

EasyByte Hub S. Coop. Mad. — cooperativa de desarrollo de software a medida. Más en https://easybyte.es
