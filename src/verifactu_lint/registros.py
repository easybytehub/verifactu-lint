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
class DetalleDesglose:
    """Una línea del `Desglose`: un tipo impositivo con su base y su cuota.

    Los importes se guardan como texto, sin convertir. Convertirlos al leer obligaría
    a decidir aquí qué hacer con un valor mal formado, y esa decisión es de las
    reglas: una es «este importe no es un número» y otra «este importe no cuadra».
    """

    orden: int
    impuesto: str | None = None
    clave_regimen: str | None = None
    calificacion: str | None = None
    operacion_exenta: str | None = None
    tipo_impositivo: str | None = None
    base: str | None = None
    base_a_coste: str | None = None
    cuota_repercutida: str | None = None
    tipo_recargo: str | None = None
    cuota_recargo: str | None = None


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
    # Rectificación y subsanación. Sólo aparecen en registros de alta; en las
    # anulaciones quedan a su valor por defecto.
    tipo_rectificativa: str | None = None
    facturas_rectificadas: int = 0
    facturas_sustituidas: int = 0
    importe_rectificacion: bool = False
    subsanacion: str | None = None
    rechazo_previo: str | None = None
    macrodato: str | None = None
    destinatarios: int = 0
    desglose: tuple[DetalleDesglose, ...] = ()
    sistema: SistemaInformatico = field(default_factory=SistemaInformatico)

    @property
    def es_rectificativa(self) -> bool:
        """R1 a R5 son los tipos rectificativos del esquema."""
        return (self.tipo_factura or "").strip().upper().startswith("R")

    @property
    def es_primer_registro(self) -> bool:
        """`PrimerRegistro` vale `S`, según el diseño de registro."""
        return (self.primer_registro or "").strip().upper() == "S"

    @property
    def referencia(self) -> str:
        """Cómo se nombra este registro en un hallazgo, para que sea localizable."""
        serie = self.num_serie or "(sin NumSerieFactura)"
        return f"#{self.orden + 1} {serie}"


@dataclass(frozen=True)
class Evento:
    """Un registro de evento.

    **Los eventos sólo existen en la modalidad NO VERI\\*FACTU.** Un sistema que
    remite sus registros a la sede da por cumplidos los requisitos de seguridad con
    esa remisión; el que no los remite tiene que demostrar por su cuenta integridad,
    inalterabilidad y trazabilidad, y el registro de eventos es cómo lo hace. De ahí
    que la modalidad «discreta» sea en realidad la exigente.

    Su cadena de huellas es **independiente** de la de facturación: encadena con
    `HuellaEvento` del evento anterior, no con la de ninguna factura.
    """

    orden: int
    tipo_evento: str | None = None
    fecha_hora_huso: str | None = None
    tipo_huella: str | None = None
    huella: str | None = None
    primer_evento: str | None = None
    anterior_tipo_evento: str | None = None
    anterior_fecha_hora: str | None = None
    anterior_huella: str | None = None
    nif_obligado: str | None = None
    # Nombre del elemento hijo de `DatosPropiosEvento`, que el esquema declara como
    # `choice`: como mucho hay uno, y cuál es depende del tipo de evento.
    datos_propios: str | None = None
    otros_datos: str | None = None
    firmado: bool = False
    sistema: SistemaInformatico = field(default_factory=SistemaInformatico)

    @property
    def es_primer_evento(self) -> bool:
        return (self.primer_evento or "").strip().upper() == "S"

    @property
    def referencia(self) -> str:
        tipo = self.tipo_evento or "??"
        return f"evento #{self.orden + 1} (tipo {tipo})"


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
        tipo_rectificativa=_valor(nodo, "TipoRectificativa"),
        facturas_rectificadas=_cuenta(nodo, "FacturasRectificadas", "IDFacturaRectificada"),
        facturas_sustituidas=_cuenta(nodo, "FacturasSustituidas", "IDFacturaSustituida"),
        importe_rectificacion=_buscar(nodo, "ImporteRectificacion") is not None,
        subsanacion=_valor(nodo, "Subsanacion"),
        rechazo_previo=_valor(nodo, "RechazoPrevio"),
        macrodato=_valor(nodo, "Macrodato"),
        destinatarios=_cuenta(nodo, "Destinatarios", "IDDestinatario"),
        desglose=_lee_desglose(_hijo(nodo, "Desglose")),
        sistema=_lee_sistema(_hijo(nodo, "SistemaInformatico")),
    )


def _cuenta(padre: ET.Element, contenedor: str, elemento: str) -> int:
    """Cuántos `elemento` hay dentro de `contenedor`.

    Se cuenta en vez de guardar la lista porque las reglas preguntan «¿hay alguna?»
    y «¿cuántas?», nunca por una en concreto — y el esquema admite hasta mil.
    """
    nodo = _hijo(padre, contenedor)
    if nodo is None:
        return 0
    return sum(1 for h in nodo if _local(h.tag) == elemento)


def _lee_desglose(nodo: ET.Element | None) -> tuple[DetalleDesglose, ...]:
    """Lee los `DetalleDesglose` conservando su orden.

    El orden importa para los hallazgos: «la línea 3 no cuadra» sólo es accionable si
    esa línea es la tercera que el usuario ve en su fichero.
    """
    if nodo is None:
        return ()
    detalles: list[DetalleDesglose] = []
    for hijo in nodo:
        if _local(hijo.tag) != "DetalleDesglose":
            continue
        detalles.append(
            DetalleDesglose(
                orden=len(detalles),
                impuesto=_valor(hijo, "Impuesto"),
                clave_regimen=_valor(hijo, "ClaveRegimen"),
                calificacion=_valor(hijo, "CalificacionOperacion"),
                operacion_exenta=_valor(hijo, "OperacionExenta"),
                tipo_impositivo=_valor(hijo, "TipoImpositivo"),
                base=_valor(hijo, "BaseImponibleOimporteNoSujeto"),
                base_a_coste=_valor(hijo, "BaseImponibleACoste"),
                cuota_repercutida=_valor(hijo, "CuotaRepercutida"),
                tipo_recargo=_valor(hijo, "TipoRecargoEquivalencia"),
                cuota_recargo=_valor(hijo, "CuotaRecargoEquivalencia"),
            )
        )
    return tuple(detalles)


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


def _lee_evento(nodo: ET.Element, orden: int) -> Evento:
    """Lee el bloque `Evento` de un `RegistroEvento`."""
    encadenamiento = _hijo(nodo, "Encadenamiento")
    anterior = (
        _hijo(encadenamiento, "EventoAnterior") if encadenamiento is not None else None
    )

    datos = _hijo(nodo, "DatosPropiosEvento")
    # El esquema declara `DatosPropiosEvento` como `choice`: como mucho un hijo, y
    # cuál sea depende del tipo de evento. Guardamos su nombre para poder contrastar
    # esa correspondencia.
    hijo_datos: str | None = None
    if datos is not None:
        for h in datos:
            hijo_datos = _local(h.tag)
            break

    # `ds:Signature` no lleva `minOccurs="0"` en el esquema: la firma es obligatoria
    # en todo registro de evento, y su ausencia es un hallazgo.
    firmado = any(_local(h.tag) == "Signature" for h in nodo.iter())

    return Evento(
        orden=orden,
        tipo_evento=_valor(nodo, "TipoEvento"),
        fecha_hora_huso=_valor(nodo, "FechaHoraHusoGenEvento"),
        tipo_huella=_valor(nodo, "TipoHuella"),
        huella=_valor(nodo, "HuellaEvento"),
        primer_evento=(
            _valor(encadenamiento, "PrimerEvento") if encadenamiento is not None else None
        ),
        anterior_tipo_evento=(
            _valor(anterior, "TipoEvento") if anterior is not None else None
        ),
        anterior_fecha_hora=(
            _valor(anterior, "FechaHoraHusoGenEvento") if anterior is not None else None
        ),
        anterior_huella=_valor(anterior, "HuellaEvento") if anterior is not None else None,
        nif_obligado=_valor(nodo, "ObligadoEmision", "NIF"),
        datos_propios=hijo_datos,
        otros_datos=_valor(nodo, "OtrosDatosEvento"),
        firmado=firmado,
        sistema=_lee_sistema(_hijo(nodo, "SistemaInformatico")),
    )


def lee_eventos(origen: Path | str) -> list[Evento]:
    """Lee un fichero XML y devuelve sus registros de evento, en orden.

    Los eventos suelen vivir en ficheros propios, separados de los de facturación,
    y su cadena de huellas es independiente. Por eso son una función distinta y no
    un tipo más dentro de `lee`: mezclarlos produciría roturas de encadenamiento
    inventadas entre una factura y un evento que nunca estuvieron encadenados.
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

    eventos: list[Evento] = []
    for nodo in raiz.iter():
        if _local(nodo.tag) != "RegistroEvento":
            continue
        cuerpo = _hijo(nodo, "Evento")
        # El diseño mete todo bajo `Evento`; si un emisor lo aplana, se lee el propio
        # `RegistroEvento` antes que devolver un evento vacío.
        eventos.append(_lee_evento(cuerpo if cuerpo is not None else nodo, len(eventos)))
    return eventos
