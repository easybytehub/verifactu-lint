"""Los ejemplos se validan contra los esquemas oficiales de la AEAT.

**Esto existe para romper una circularidad.** El resto de la suite construye XML con
la misma interpretación del reglamento que luego comprueba: si esa interpretación
fuese incorrecta en algún punto, los ejemplos replicarían el error y los tests
pasarían igual de verdes. Los tres vectores oficiales de `test_huella.py` anclan el
cálculo del hash, pero no la estructura.

Aquí el ancla es el XSD que publica la AEAT: si los ejemplos validan contra él, al
menos son ficheros que un sistema real podría haber emitido.

**Y hay un segundo motivo, que es la tesis de la herramienta.** `cadena-rota.xml` y
`eventos-con-defectos.xml` **validan contra el esquema oficial** y aun así incumplen
el reglamento: la cadena de huellas está partida y a un evento de exportación le
faltan sus datos propios. Un XSD comprueba forma, no coherencia. Esa franja —lo que
es estructuralmente impecable y sustantivamente incorrecto— es exactamente donde
trabaja `verifactu-lint`, y estos tests lo demuestran en vez de afirmarlo.
"""

from __future__ import annotations

from pathlib import Path

import pytest

RAIZ = Path(__file__).parent.parent
ESQUEMAS = RAIZ / "esquemas"
EJEMPLOS = RAIZ / "ejemplos"

NS_EVENTOS = (
    "https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/"
    "aplicaciones/es/aeat/tike/cont/ws/EventosSIF.xsd"
)

etree = pytest.importorskip(
    "lxml.etree",
    reason="lxml sólo es dependencia de desarrollo: el paquete no valida XSD",
)


class _ResolverLocal(etree.Resolver):  # type: ignore[misc,name-defined]
    """Sirve el XSD de xmldsig desde disco.

    Los esquemas de la AEAT importan `xmldsig-core-schema.xsd` por su URL de w3.org.
    Ir a buscarlo en cada ejecución haría que la suite dependiese de la red y de que
    un tercero siga sirviendo el mismo fichero — un test que puede fallar por algo
    ajeno al código deja de significar nada.
    """

    def resolve(self, url: str, pid: object, context: object) -> object:
        if url.endswith("xmldsig-core-schema.xsd"):
            return self.resolve_filename(str(ESQUEMAS / "xmldsig-core-schema.xsd"), context)
        return None


def _esquema(nombre: str) -> object:
    parser = etree.XMLParser()
    parser.resolvers.add(_ResolverLocal())
    return etree.XMLSchema(etree.parse(str(ESQUEMAS / nombre), parser))


@pytest.fixture(scope="module")
def esquema_facturas() -> object:
    return _esquema("SuministroLR.xsd")


@pytest.fixture(scope="module")
def esquema_eventos() -> object:
    return _esquema("EventosSIF.xsd")


def test_los_esquemas_estan_en_el_repositorio() -> None:
    """Versionados, no descargados en cada ejecución.

    Un esquema que se baja al vuelo convierte cualquier cambio de la AEAT en un fallo
    sorpresa de CI, en un commit que no tiene nada que ver. Aquí actualizarlos es un
    cambio explícito, revisable en un diff.
    """
    for nombre in (
        "SuministroLR.xsd",
        "SuministroInformacion.xsd",
        "EventosSIF.xsd",
        "xmldsig-core-schema.xsd",
    ):
        assert (ESQUEMAS / nombre).is_file(), f"falta esquemas/{nombre}"


@pytest.mark.parametrize(
    "nombre", ["cadena-conforme.xml", "cadena-rota.xml"]
)
def test_ejemplos_de_facturacion_validan(nombre: str, esquema_facturas: object) -> None:
    documento = etree.parse(str(EJEMPLOS / nombre))
    valido = esquema_facturas.validate(documento)  # type: ignore[attr-defined]
    errores = [e.message for e in esquema_facturas.error_log]  # type: ignore[attr-defined]
    assert valido, f"{nombre} no valida contra SuministroLR.xsd:\n" + "\n".join(errores[:5])


@pytest.mark.parametrize(
    "nombre", ["eventos-conforme.xml", "eventos-con-defectos.xml"]
)
def test_ejemplos_de_eventos_validan(nombre: str, esquema_eventos: object) -> None:
    """Cada `RegistroEvento` se valida por separado, y no es un capricho.

    `RegistroEvento` es el **único elemento global** del esquema de eventos: la AEAT
    no define ningún envoltorio para agrupar varios. Un fichero con más de uno lleva
    por fuerza un contenedor propio del fabricante, así que lo que se puede validar
    contra el esquema oficial es cada registro suelto.
    """
    documento = etree.parse(str(EJEMPLOS / nombre))
    registros = documento.getroot().findall(f"{{{NS_EVENTOS}}}RegistroEvento")
    assert registros, f"{nombre} no contiene ningún RegistroEvento"

    for posicion, nodo in enumerate(registros, start=1):
        suelto = etree.ElementTree(etree.fromstring(etree.tostring(nodo)))
        valido = esquema_eventos.validate(suelto)  # type: ignore[attr-defined]
        errores = [e.message for e in esquema_eventos.error_log]  # type: ignore[attr-defined]
        assert valido, (
            f"{nombre}, evento {posicion}, no valida contra EventosSIF.xsd:\n"
            + "\n".join(errores[:5])
        )


def test_el_ejemplo_roto_es_valido_para_el_xsd_y_no_para_el_reglamento(
    esquema_facturas: object,
) -> None:
    """La demostración de para qué sirve esta herramienta.

    `cadena-rota.xml` es un fichero impecable para el esquema y con la cadena de
    huellas partida. Ninguna validación estructural puede verlo, porque el XSD no
    sabe calcular un SHA-256 ni conoce el orden de los registros.
    """
    from verifactu_lint.registros import lee
    from verifactu_lint.reglas import audita

    ruta = EJEMPLOS / "cadena-rota.xml"
    assert esquema_facturas.validate(etree.parse(str(ruta)))  # type: ignore[attr-defined]

    informe = audita(lee(ruta))
    assert informe.errores, "el ejemplo roto debería producir errores"
    assert any(h.regla == "RRSIF003" for h in informe.errores)


def test_el_ejemplo_conforme_no_produce_errores() -> None:
    """Y el complemento: válido para el XSD y también para las reglas.

    Sin este test, «no hay errores» podría significar que el parser no está leyendo
    nada — que es cómo se ve un fichero conforme y uno que no se entiende.
    """
    from verifactu_lint.registros import lee
    from verifactu_lint.reglas import audita

    registros = lee(EJEMPLOS / "cadena-conforme.xml")
    assert len(registros) == 3
    assert audita(registros).errores == []
