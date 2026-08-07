"""Registros escritos por otra implementación deben leerse y validarse igual.

**Es la comprobación más fuerte de la suite, y la que menos depende de nosotros.**
Los esquemas oficiales anclan la estructura; los tres vectores de la AEAT anclan el
cálculo de la huella. Ninguna de las dos cosas dice si un registro producido por
*otro programa* —otra lectura del reglamento, otro lenguaje, otro autor— se procesa
correctamente.

El corpus viene de `josemmo/Verifactu-PHP` (MIT). Sus huellas las calculó una
implementación en PHP; aquí se recalculan en Python y tienen que salir idénticas.

Y trae casos que los ejemplos propios no tenían: varios destinatarios —uno extranjero
con `IDOtro`—, varias líneas de desglose con tipos distintos, `FechaOperacion`,
`Subsanacion`, y un prefijo de namespace ajeno.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from verifactu_lint.registros import lee
from verifactu_lint.reglas import audita

CORPUS = Path(__file__).parent / "interoperabilidad"
FICHEROS = sorted(CORPUS.glob("*.xml"))


def test_el_corpus_existe() -> None:
    """Si el glob queda vacío, el resto de tests pasaría sin comprobar nada."""
    assert len(FICHEROS) == 3, f"se esperaban 3 ficheros y hay {len(FICHEROS)}"


@pytest.mark.parametrize("ruta", FICHEROS, ids=lambda p: p.stem)
def test_se_leen(ruta: Path) -> None:
    registros = lee(ruta)
    assert registros, f"{ruta.name} no produjo ningún registro"


@pytest.mark.parametrize("ruta", FICHEROS, ids=lambda p: p.stem)
def test_la_huella_ajena_coincide_con_la_nuestra(ruta: Path) -> None:
    """El corazón de esta prueba.

    Una huella calculada por otra implementación tiene que ser la que sale de nuestro
    cálculo. Si RRSIF001 se dispara aquí, o su código o el nuestro está mal — y hasta
    saber cuál, ninguna de las dos merece confianza.
    """
    informe = audita(lee(ruta))
    fallos = [h for h in informe.hallazgos if h.regla == "RRSIF001"]
    assert not fallos, (
        f"{ruta.name}: la huella calculada por otra implementación no coincide.\n"
        + "\n".join(h.detalle for h in fallos)
    )


@pytest.mark.parametrize("ruta", FICHEROS, ids=lambda p: p.stem)
def test_no_producen_errores(ruta: Path) -> None:
    """Registros de prueba de una librería seria no deberían incumplir.

    Un error aquí es una de dos cosas, y las dos interesan: un falso positivo nuestro,
    o un defecto real en la otra implementación.
    """
    informe = audita(lee(ruta))
    assert not informe.errores, (
        f"{ruta.name} produce errores:\n"
        + "\n".join(f"  {h.regla}: {h.titulo}" for h in informe.errores)
    )


def test_se_leen_estructuras_que_los_ejemplos_propios_no_tienen() -> None:
    """Lo que este corpus aporta y los ficheros generados aquí no tenían."""
    registros = lee(CORPUS / "registration-record-f1.xml")
    r = registros[0]

    # Dos destinatarios, uno de ellos extranjero identificado por IDOtro.
    assert r.destinatarios == 2
    # Dos líneas de desglose con tipos impositivos distintos.
    assert len(r.desglose) == 2
    assert {d.tipo_impositivo for d in r.desglose} == {"21.00", "10.00"}
    # Y un prefijo de namespace que no es el que usa este repositorio.
    assert r.tipo_factura == "F1"
    assert r.subsanacion == "N"


def test_una_anulacion_ajena_se_reconoce_como_tal() -> None:
    registros = lee(CORPUS / "cancellation-record.xml")
    assert [r.tipo for r in registros] == ["anulacion"]


def test_el_cuadre_del_desglose_ajeno_sale() -> None:
    """100,00 al 21 % + 50,00 al 10 % = 26,00 de cuota y 176,00 de total."""
    r = lee(CORPUS / "registration-record-f1.xml")[0]
    assert r.cuota_total == "26.00"
    assert r.importe_total == "176.00"
    informe = audita([r])
    assert not [h for h in informe.hallazgos if h.regla in {"RRSIF041", "RRSIF042"}]
