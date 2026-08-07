# verifactu-lint

[![ci](https://github.com/easybytehub/verifactu-lint/actions/workflows/ci.yml/badge.svg)](https://github.com/easybytehub/verifactu-lint/actions/workflows/ci.yml)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/easybytehub/verifactu-lint/badge)](https://scorecard.dev/viewer/?uri=github.com/easybytehub/verifactu-lint)
[![PyPI](https://img.shields.io/pypi/v/verifactu-lint)](https://pypi.org/project/verifactu-lint/)
[![Python](https://img.shields.io/pypi/pyversions/verifactu-lint)](https://pypi.org/project/verifactu-lint/)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue)](LICENSE)

Audita registros de facturación **ya emitidos** contra el Reglamento de requisitos de los sistemas informáticos de facturación (RD 1007/2023) y su Orden de desarrollo (HAC/1177/2024).

Le das el XML que tu sistema genera y te dice dónde incumple, citando el artículo.

```console
$ verifactu-lint registros-2026-01.xml

verifactu-lint · 1.284 registros · registros-2026-01.xml

ERROR      RRSIF003 [#412 FA/2026/0412]: La cadena se rompe en este registro
           Declara como huella anterior 9F2C…A31B, y la huella de #411 FA/2026/0411 es 4D77…C0E9.
           Una cadena rota significa que la secuencia conservada no es la que se generó:
           falta un registro por medio, se reordenaron, o se modificó uno después de emitirlo.
           norma: Orden HAC/1177/2024, art. 13 y especificaciones técnicas de la huella

1 errores · 0 avisos · 0 sin determinar
```

## Qué es, y qué no es

Existen ya varias librerías buenas para **generar** registros Verifactu. Ninguna responde a la pregunta que se hace quien ya tiene un sistema en marcha: *¿lo que llevo emitido cumple?*

Eso es lo que hace esta herramienta.

**No es un sistema informático de facturación.** No expide facturas, no genera registros, no los firma y no los remite a la AEAT. Sólo lee. Por tanto no le corresponde emitir declaración responsable alguna, ni la emite.

**Un resultado sin errores no acredita conformidad.** Significa que estas reglas, sobre esos registros, no han encontrado un incumplimiento. La declaración responsable del artículo 13 del RRSIF la emite el productor del SIF bajo su propia responsabilidad, y ninguna herramienta puede emitirla por él.

## Instalación

```bash
pip install verifactu-lint
```

Sin dependencias en tiempo de ejecución: sólo la biblioteca estándar de Python (3.11+).

## Uso

```bash
# informe legible
verifactu-lint registros.xml

# varios ficheros; cada uno se audita como su propia cadena
verifactu-lint enero.xml febrero.xml

# para tratarlo con jq, o para archivarlo
verifactu-lint registros.xml --formato json

# para GitHub Code Scanning
verifactu-lint registros.xml --formato sarif > verifactu.sarif

# que los avisos también rompan la build
verifactu-lint registros.xml --estricto
```

**Códigos de salida:** `0` sin errores · `1` con errores (o con avisos si `--estricto`) · `2` si el fichero no se pudo leer.

Como librería:

```python
from verifactu_lint.registros import lee
from verifactu_lint.reglas import audita

informe = audita(lee("registros.xml"))
for hallazgo in informe.errores:
    print(hallazgo.regla, hallazgo.titulo, hallazgo.referencia)
```

### En tu CI

Auditar en cada cambio cuesta menos que descubrir la cadena rota en una inspección. Con salida SARIF los hallazgos aparecen en la pestaña **Security** del repositorio, sin que nadie tenga que abrir un log:

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
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install verifactu-lint
      - run: verifactu-lint registros/*.xml --formato sarif > verifactu.sarif
        continue-on-error: true
      - uses: github/codeql-action/upload-sarif@v3
        with: { sarif_file: verifactu.sarif }
```

El `continue-on-error` del paso de auditoría es deliberado: sin él, un hallazgo abortaría el job antes de subir el SARIF y no verías *qué* falló. El fallo lo señala la pestaña Security, que es donde se puede leer.

## Las reglas

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

### Tres severidades, no dos

- **`error`** — incumple. Lo que hay en el fichero contradice la norma citada.
- **`aviso`** — muy probablemente incumple, o incumplirá en cuanto se dé una condición previsible.
- **`incompleto`** — no se puede determinar con este fichero, y el hallazgo dice qué habría que mirar.

`incompleto` existe porque en una herramienta de cumplimiento **afirmar un incumplimiento que no existe es peor que callar uno que sí**: quien lo lee cambia código correcto y deja de creerse el resto del informe. Cuando una regla no puede concluir, lo dice.

Un ejemplo real de esa cautela: la orden admite `123.1` y `123.10` como el mismo importe, y cada forma produce un SHA-256 distinto. Un verificador que calculase sólo una declararía incorrecta una huella que la AEAT acepta. `verifactu-lint` prueba las formas admisibles antes de afirmar nada.

## Sobre qué se apoya

- **RD 1007/2023**, de 5 de diciembre — Reglamento de requisitos de los sistemas informáticos de facturación.
- **Orden HAC/1177/2024**, de 17 de octubre — especificaciones técnicas, funcionales y de contenido.
- **AEAT — *Detalle de las especificaciones técnicas para generación de la huella o hash de los registros de facturación*, v0.1.2** (27/08/2024). Los tres vectores de su apartado 6 están en la suite de tests y se ejecutan en cada cambio: son la definición de correcto para el cálculo de la huella.
- **AEAT — *Aclaraciones a dudas de los desarrolladores*, v1.3** (04/12/2025).

Cuando una regla y la norma discrepen, la norma tiene razón y la regla es un bug. [Abre un issue](https://github.com/easybytehub/verifactu-lint/issues) citando el apartado.

## Alcance actual

Cubre el encadenamiento, el formato de la huella y la identificación del SIF, sobre registros de **alta** y **anulación**.

Todavía **no** cubre: registros de **evento** (el cálculo de su huella está implementado y probado, pero no las reglas que los auditan), la tipificación de rectificativas y subsanaciones, ni la conservación exigida a la modalidad NO VERI\*FACTU. Están en ese orden en los issues.

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
