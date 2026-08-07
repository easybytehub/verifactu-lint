# Corpus de interoperabilidad

Registros generados por **otra implementación**, usados aquí como prueba cruzada.

| Fichero | Origen |
|---|---|
| `registration-record-f1.xml` | [josemmo/Verifactu-PHP](https://github.com/josemmo/Verifactu-PHP) · `tests/Models/Records/` |
| `registration-record-f2.xml` | ídem |
| `cancellation-record.xml` | ídem |

Licencia del proyecto de origen: **MIT**. Descargados el 2026-08-07.

## Por qué están aquí

Todo lo demás en `tests/` lo genera este repositorio. Los esquemas oficiales anclan
la **estructura** y los tres vectores de la AEAT anclan el **cálculo de la huella**,
pero ninguna de las dos cosas comprueba que un registro escrito por *otro programa*
—con otra lectura del reglamento, en otro lenguaje— se lea y se valide igual.

Estos ficheros sí. Sus huellas las calculó una implementación en PHP; `verifactu-lint`
las recalcula en Python y tienen que coincidir. Si algún día dejan de hacerlo, una de
las dos está mal y conviene saberlo antes que el usuario.

Traen además casos que los ejemplos propios no tenían: varios destinatarios, uno de
ellos extranjero identificado por `IDOtro`; varias líneas de desglose con tipos
distintos; `FechaOperacion` y `Subsanacion` informados; y un prefijo de namespace
(`sum1:`) que no es el que usa este repositorio.

## Qué no son

**No son ficheros de producción.** Siguen siendo ficheros de prueba, escritos por
alguien que también podría haber interpretado mal la norma — el acuerdo entre dos
implementaciones es una señal fuerte, no una demostración. Un registro emitido por un
SIF real en explotación sigue siendo la validación que falta.
