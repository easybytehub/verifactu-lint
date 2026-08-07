"""Modelo de los registros de facturación, y su lectura desde XML.

**Lo que este módulo NO hace: validar contra el XSD.** Los esquemas oficiales ya
existen y cualquier parser los aplica. Lo que aquí interesa es lo que un XSD no
puede expresar — que la huella del registro 41 coincida con lo que resulta de los
campos del 41, o que el encadenamiento no se rompa entre el 40 y el 41. Por eso el
parseo es deliberadamente tolerante: un registro al que le falte un campo entra
igualmente y son las reglas quienes se pronuncian sobre él. Un parser estricto
convertiría un hallazgo explicable en un error de arranque.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path


class ErrorDeLectura(Exception):
    """El fichero no se pudo leer como XML de registros de facturación."""


@dataclass(frozen=True)
class SistemaInformatico:
    """El bloque `SistemaInformatico` del registro.

    Es el que identifica al SIF, y tres de sus campos forman la identificación
    universal descrita en el FAQ de desarrolladores de la AEAT: NIF del obligado,
    `IdSistemaInformatico` y `NumeroInstalacion`.
    """

    nombre_razon: str | None = None
    nif: str | None = None
    id_otro: str | None = None
    id_sistema_informatico: str | None = None
    version: str | None = None
    numero_instalacion: str | None = None
    tipo_uso_solo_verifactu: str | None = None
    tipo_uso_multi_ot: str | None = None
    indicador_multiples_ot: str | None = None


@dataclass(frozen=True)
class Registro:
    """Un registro de facturación, de alta o de anulación.

    Los dos tipos comparten estructura suficiente como para que separarlos en dos
    clases obligase a duplicar cada regla de encadenamiento. `tipo` distingue, y los
    campos que sólo tiene el alta quedan a `None` en la anulación.
    """

    tipo: str  # "alta" | "anulacion"
    orden: int  # posición en el fichero, 0-indexada; para señalar hallazgos
    id_emisor: str | None = None
    num_serie: str | None = None
    fecha_expedicion: str | None = None
    tipo_factura: str | None = None
    cuota_total: str | None = None
    importe_total: str | None = None
    fecha_hora_huso: str | None = None
    tipo_huella: str | None = None
    huella: str | None = None
    primer_registro: str | None = None
    anterior_id_emisor: str | None = None
    anterior_num_serie: str | None = None
    anterior_fecha_expedicion: str | None = None
    anterior_huella: str | None = None
    sistema: SistemaInformatico = field(default_factory=SistemaInformatico)

    @property
    def es_primer_registro(self) -> bool:
        """`PrimerRegistro` vale `S`, según el diseño de registro."""
        return (self.primer_registro or "").strip().upper() == "S"

    @property
    def referencia(self) -> str:
        """Cómo se nombra este registro en un hallazgo, para que sea localizable."""
        serie = self.num_serie or "(sin NumSerieFactura)"
        return f"#{self.orden + 1} {serie}"


def _local(tag: str) -> str:
    """El nombre del elemento sin su namespace.

    Los registros van namespaced (`sf:`, `sfLR:`) y el prefijo concreto varía entre
    emisores y versiones del esquema. Comparar por nombre local es lo que hace que
    un fichero perfectamente válido no se lea como vacío por un prefijo distinto.
    """
    return tag.rsplit("}", 1)[-1]


def _texto(elemento: ET.Element | None) -> str | None:
    if elemento is None or elemento.text is None:
        return None
    return elemento.text


def _hijo(padre: ET.Element, nombre: str) -> ET.Element | None:
    for hijo in padre:
        if _local(hijo.tag) == nombre:
            return hijo
    return None


def _buscar(padre: ET.Element, *ruta: str) -> ET.Element | None:
    actual: ET.Element | None = padre
    for nombre in ruta:
        if actual is None:
            return None
        actual = _hijo(actual, nombre)
    return actual


def _valor(padre: ET.Element, *ruta: str) -> str | None:
    return _texto(_buscar(padre, *ruta))


def _lee_sistema(nodo: ET.Element | None) -> SistemaInformatico:
    if nodo is None:
        return SistemaInformatico()
    return SistemaInformatico(
        nombre_razon=_valor(nodo, "NombreRazon"),
        nif=_valor(nodo, "NIF"),
        id_otro=_valor(nodo, "IDOtro", "ID"),
        id_sistema_informatico=_valor(nodo, "IdSistemaInformatico"),
        version=_valor(nodo, "Version"),
        numero_instalacion=_valor(nodo, "NumeroInstalacion"),
        tipo_uso_solo_verifactu=_valor(nodo, "TipoUsoPosibleSoloVerifactu"),
        tipo_uso_multi_ot=_valor(nodo, "TipoUsoPosibleMultiOT"),
        indicador_multiples_ot=_valor(nodo, "IndicadorMultiplesOT"),
    )


def _lee_encadenamiento(nodo: ET.Element) -> tuple[ET.Element | None, ET.Element | None]:
    """El bloque `Encadenamiento` y, si lo hay, su `RegistroAnterior`.

    **Se compara `is not None` y no truthiness.** Un `ET.Element` es falsy cuando no
    tiene hijos, así que `if encadenamiento` trata un bloque vacío como si no
    existiera — y un `<Encadenamiento/>` vacío es precisamente uno de los defectos
    que esta herramienta debe ver, no ignorar.
    """
    encadenamiento = _hijo(nodo, "Encadenamiento")
    if encadenamiento is None:
        return None, None
    return encadenamiento, _hijo(encadenamiento, "RegistroAnterior")


def _lee_alta(nodo: ET.Element, orden: int) -> Registro:
    encadenamiento, anterior = _lee_encadenamiento(nodo)
    return Registro(
        tipo="alta",
        orden=orden,
        id_emisor=_valor(nodo, "IDFactura", "IDEmisorFactura"),
        num_serie=_valor(nodo, "IDFactura", "NumSerieFactura"),
        fecha_expedicion=_valor(nodo, "IDFactura", "FechaExpedicionFactura"),
        tipo_factura=_valor(nodo, "TipoFactura"),
        cuota_total=_valor(nodo, "CuotaTotal"),
        importe_total=_valor(nodo, "ImporteTotal"),
        fecha_hora_huso=_valor(nodo, "FechaHoraHusoGenRegistro"),
        tipo_huella=_valor(nodo, "TipoHuella"),
        huella=_valor(nodo, "Huella"),
        primer_registro=(
            _valor(encadenamiento, "PrimerRegistro") if encadenamiento is not None else None
        ),
        anterior_id_emisor=(
            _valor(anterior, "IDEmisorFactura") if anterior is not None else None
        ),
        anterior_num_serie=(
            _valor(anterior, "NumSerieFactura") if anterior is not None else None
        ),
        anterior_fecha_expedicion=(
            _valor(anterior, "FechaExpedicionFactura") if anterior is not None else None
        ),
        anterior_huella=_valor(anterior, "Huella") if anterior is not None else None,
        sistema=_lee_sistema(_hijo(nodo, "SistemaInformatico")),
    )


def _lee_anulacion(nodo: ET.Element, orden: int) -> Registro:
    encadenamiento, anterior = _lee_encadenamiento(nodo)
    return Registro(
        tipo="anulacion",
        orden=orden,
        id_emisor=_valor(nodo, "IDFactura", "IDEmisorFacturaAnulada"),
        num_serie=_valor(nodo, "IDFactura", "NumSerieFacturaAnulada"),
        fecha_expedicion=_valor(nodo, "IDFactura", "FechaExpedicionFacturaAnulada"),
        fecha_hora_huso=_valor(nodo, "FechaHoraHusoGenRegistro"),
        tipo_huella=_valor(nodo, "TipoHuella"),
        huella=_valor(nodo, "Huella"),
        primer_registro=(
            _valor(encadenamiento, "PrimerRegistro") if encadenamiento is not None else None
        ),
        anterior_id_emisor=(
            _valor(anterior, "IDEmisorFactura") if anterior is not None else None
        ),
        anterior_num_serie=(
            _valor(anterior, "NumSerieFactura") if anterior is not None else None
        ),
        anterior_fecha_expedicion=(
            _valor(anterior, "FechaExpedicionFactura") if anterior is not None else None
        ),
        anterior_huella=_valor(anterior, "Huella") if anterior is not None else None,
        sistema=_lee_sistema(_hijo(nodo, "SistemaInformatico")),
    )


# Cuánto del principio del documento se inspecciona buscando un DOCTYPE. La
# declaración de tipo de documento sólo puede aparecer en el prólogo, antes del
# elemento raíz, así que un margen generoso sobra: aquí caben el prólogo, los
# comentarios de cabecera y varias instrucciones de proceso.
_PROLOGO = 8192


def _rechaza_doctype(texto_inicial: str, ruta: Path) -> None:
    """Rechaza cualquier documento con DTD interna.

    **Por qué antes de parsear y no durante.** `xml.etree` no expande entidades
    externas, pero sí las internas, y con eso basta para un *billion laughs*: diez
    líneas de XML que agotan la memoria del proceso. Interceptarlo dentro del parser
    obligaría a hurgar en el expat subyacente, que es un detalle de implementación y
    ha cambiado entre versiones de Python.

    Mirar el prólogo es una comprobación sobre el formato, no sobre los internos de
    nadie: un registro de facturación no declara entidades jamás, así que rechazar
    todo DOCTYPE no pierde ningún fichero legítimo y no añade una dependencia cuya
    única función sería ésta.
    """
    if "<!DOCTYPE" in texto_inicial:
        raise ErrorDeLectura(
            f"{ruta}: el documento declara un DOCTYPE. verifactu-lint no procesa DTD "
            "ni entidades — un registro de facturación no las necesita, y admitirlas "
            "abre la puerta a un XML que agota la memoria del proceso."
        )


def lee(origen: Path | str) -> list[Registro]:
    """Lee un fichero XML y devuelve sus registros en orden de aparición.

    El orden importa y por eso se conserva: el encadenamiento es una secuencia, y un
    hallazgo que dice «se rompe entre el 40 y el 41» sólo es accionable si esos
    números corresponden a lo que el usuario ve en su fichero.
    """
    ruta = Path(origen)
    try:
        contenido = ruta.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise ErrorDeLectura(f"{ruta}: no se pudo abrir ({exc})") from exc

    _rechaza_doctype(contenido[:_PROLOGO], ruta)

    try:
        raiz = ET.fromstring(contenido)  # noqa: S314
    except ET.ParseError as exc:
        raise ErrorDeLectura(f"{ruta}: XML mal formado ({exc})") from exc

    registros: list[Registro] = []
    for nodo in raiz.iter():
        nombre = _local(nodo.tag)
        if nombre == "RegistroAlta":
            registros.append(_lee_alta(nodo, len(registros)))
        elif nombre == "RegistroAnulacion":
            registros.append(_lee_anulacion(nodo, len(registros)))
    return registros
