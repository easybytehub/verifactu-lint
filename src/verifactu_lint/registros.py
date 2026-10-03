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

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field, replace
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
class ElementoInesperado:
    """Un elemento en una posición que el esquema no prevé.

    `ruta` va desde el propio registro («RegistroAlta/Huella/Hash»), que es como lo
    busca quien abre el fichero. `contiene` son los elementos que el esquema espera en
    el bloque padre y que aparecen dentro de éste: es la pista que convierte «no
    informa TipoFactura» en «TipoFactura está, pero dentro de Factura».
    """

    ruta: str
    contiene: tuple[str, ...] = ()
    # El padre es un elemento de valor (`Huella`, `CuotaTotal`…), que no admite hijos.
    en_un_valor: bool = False


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
    # Línea del XML donde abre el registro, cuando se puede saber con certeza. La usa la
    # salida SARIF para que la anotación del CI caiga en el registro y no en la línea N.
    linea_xml: int | None = None
    # Elementos en posiciones que el esquema no prevé, desde 0.4.1. El parseo sigue
    # siendo tolerante —el registro entra igual—, pero un dato escrito en otra ruta
    # cuenta como ausente para las reglas, y esto es lo que permite decir por qué.
    fuera_de_esquema: tuple[ElementoInesperado, ...] = ()

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
    linea_xml: int | None = None

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


# Qué hijos admite cada bloque, copiado de `SuministroInformacion.xsd`
# (`RegistroFacturacionAltaType`, `RegistroFacturacionAnulacionType` y los tipos que
# cuelgan de ellos). `tests/test_estructura.py` lo contrasta con el XSD versionado en
# `esquemas/`, así que no puede divergir sin que falle la suite.
#
# **Sólo los bloques que leen las reglas.** Esto no es una validación XSD —el paquete
# no la hace, y no comprueba orden ni obligatoriedad—: existe para explicar por qué
# una regla no encuentra un dato que sí está, sólo que en otra ruta. Un bloque que
# ninguna regla lee (`Destinatarios` por dentro, `Tercero`, la firma) no puede
# provocar ese engaño, y comprobarlo sería hacer de XSD a medias.
_HIJOS_DEL_REGISTRO: dict[str, frozenset[str]] = {
    "RegistroAlta": frozenset({
        "IDVersion", "IDFactura", "RefExterna", "NombreRazonEmisor", "Subsanacion",
        "RechazoPrevio", "TipoFactura", "TipoRectificativa", "FacturasRectificadas",
        "FacturasSustituidas", "ImporteRectificacion", "FechaOperacion",
        "DescripcionOperacion", "FacturaSimplificadaArt7273",
        "FacturaSinIdentifDestinatarioArt61d", "Macrodato",
        "EmitidaPorTerceroODestinatario", "Tercero", "Destinatarios", "Cupon",
        "Desglose", "CuotaTotal", "ImporteTotal", "Encadenamiento",
        "SistemaInformatico", "FechaHoraHusoGenRegistro",
        "NumRegistroAcuerdoFacturacion", "IdAcuerdoSistemaInformatico", "TipoHuella",
        "Huella", "Signature",
    }),
    "RegistroAnulacion": frozenset({
        "IDVersion", "IDFactura", "RefExterna", "SinRegistroPrevio", "RechazoPrevio",
        "GeneradoPor", "Generador", "Encadenamiento", "SistemaInformatico",
        "FechaHoraHusoGenRegistro", "TipoHuella", "Huella", "Signature",
    }),
}

# `IDFactura` cambia de nombres según el tipo de registro: en la anulación cada campo
# lleva el sufijo «Anulada». Confundirlos es un error real (estudio S1, I-3).
ID_FACTURA: dict[str, tuple[str, str, str]] = {
    "RegistroAlta": ("IDEmisorFactura", "NumSerieFactura", "FechaExpedicionFactura"),
    "RegistroAnulacion": (
        "IDEmisorFacturaAnulada",
        "NumSerieFacturaAnulada",
        "FechaExpedicionFacturaAnulada",
    ),
}

_HIJOS_DEL_BLOQUE: dict[str, frozenset[str]] = {
    "Encadenamiento": frozenset({"PrimerRegistro", "RegistroAnterior"}),
    "RegistroAnterior": frozenset({
        "IDEmisorFactura", "NumSerieFactura", "FechaExpedicionFactura", "Huella",
    }),
    "Desglose": frozenset({"DetalleDesglose"}),
    "DetalleDesglose": frozenset({
        "Impuesto", "ClaveRegimen", "CalificacionOperacion", "OperacionExenta",
        "TipoImpositivo", "BaseImponibleOimporteNoSujeto", "BaseImponibleACoste",
        "CuotaRepercutida", "TipoRecargoEquivalencia", "CuotaRecargoEquivalencia",
    }),
    "SistemaInformatico": frozenset({
        "NombreRazon", "NIF", "IDOtro", "NombreSistemaInformatico",
        "IdSistemaInformatico", "Version", "NumeroInstalacion",
        "TipoUsoPosibleSoloVerifactu", "TipoUsoPosibleMultiOT", "IndicadorMultiplesOT",
    }),
}

# Elementos de tipo simple: llevan un valor, nunca otros elementos. Un
# `<Huella><Hash>…</Hash></Huella>` se lee como una huella vacía, y avisar sólo de
# eso manda a buscar un dato que está ahí.
_DE_VALOR = frozenset({
    "IDVersion", "RefExterna", "NombreRazonEmisor", "Subsanacion", "RechazoPrevio",
    "TipoFactura", "TipoRectificativa", "FechaOperacion", "DescripcionOperacion",
    "FacturaSimplificadaArt7273", "FacturaSinIdentifDestinatarioArt61d", "Macrodato",
    "EmitidaPorTerceroODestinatario", "Cupon", "CuotaTotal", "ImporteTotal",
    "FechaHoraHusoGenRegistro", "NumRegistroAcuerdoFacturacion",
    "IdAcuerdoSistemaInformatico", "TipoHuella", "Huella", "SinRegistroPrevio",
    "GeneradoPor", "PrimerRegistro", "IDEmisorFactura", "NumSerieFactura",
    "FechaExpedicionFactura", "IDEmisorFacturaAnulada", "NumSerieFacturaAnulada",
    "FechaExpedicionFacturaAnulada", "Impuesto", "ClaveRegimen",
    "CalificacionOperacion", "OperacionExenta", "TipoImpositivo",
    "BaseImponibleOimporteNoSujeto", "BaseImponibleACoste", "CuotaRepercutida",
    "TipoRecargoEquivalencia", "CuotaRecargoEquivalencia", "NombreRazon", "NIF",
    "NombreSistemaInformatico", "IdSistemaInformatico", "Version", "NumeroInstalacion",
    "TipoUsoPosibleSoloVerifactu", "TipoUsoPosibleMultiOT", "IndicadorMultiplesOT",
})


def _inesperado(nodo: ET.Element, ruta: str, esperados: frozenset[str]) -> ElementoInesperado:
    """El elemento fuera de sitio, con los esperados del bloque padre que lleva dentro."""
    dentro: list[str] = []
    for descendiente in nodo.iter():
        nombre = _local(descendiente.tag)
        if descendiente is not nodo and nombre in esperados and nombre not in dentro:
            dentro.append(nombre)
    return ElementoInesperado(ruta=ruta, contiene=tuple(dentro))


def _fuera_de_esquema(nodo: ET.Element) -> tuple[ElementoInesperado, ...]:
    """Los elementos de un registro que están donde el esquema no los prevé."""
    raiz = _local(nodo.tag)
    hallados: list[ElementoInesperado] = []

    def recorre(padre: ET.Element, ruta: str, esperados: frozenset[str]) -> None:
        for hijo in padre:
            if not isinstance(hijo.tag, str):
                continue  # comentarios e instrucciones de proceso
            nombre = _local(hijo.tag)
            ruta_hijo = f"{ruta}/{nombre}"
            if nombre not in esperados:
                hallados.append(_inesperado(hijo, ruta_hijo, esperados))
            elif nombre == "IDFactura" and padre is nodo:
                recorre(hijo, ruta_hijo, frozenset(ID_FACTURA[raiz]))
            elif nombre in _HIJOS_DEL_BLOQUE:
                recorre(hijo, ruta_hijo, _HIJOS_DEL_BLOQUE[nombre])
            elif nombre in _DE_VALOR:
                for nieto in hijo:
                    if isinstance(nieto.tag, str):
                        hallados.append(
                            ElementoInesperado(
                                ruta=f"{ruta_hijo}/{_local(nieto.tag)}", en_un_valor=True
                            )
                        )

    recorre(nodo, raiz, _HIJOS_DEL_REGISTRO[raiz])
    return tuple(hallados)


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
        fuera_de_esquema=_fuera_de_esquema(nodo),
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
        fuera_de_esquema=_fuera_de_esquema(nodo),
    )


# Cuánto del principio del documento se inspecciona buscando un DOCTYPE. La
# declaración de tipo de documento sólo puede aparecer en el prólogo, antes del
# elemento raíz, así que un margen generoso sobra: aquí caben el prólogo, los
# comentarios de cabecera y varias instrucciones de proceso.
_PROLOGO = 8192

_DECLARACION = re.compile(rb"""<\?xml[^>]*?encoding\s*=\s*["']([A-Za-z0-9._-]+)["']""")


def _rechaza_doctype(crudo: bytes, ruta: Path) -> None:
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

    **Se busca en tres lecturas del prólogo, no en una.** Desde 0.4.0 el fichero se
    parsea en bytes, respetando la codificación que declara, y expat también reconoce
    UTF-16 con o sin BOM. En latin-1 se ve el DOCTYPE de cualquier codificación
    compatible con ASCII (UTF-8, ISO-8859-1, Windows-1252); en UTF-16, el de las otras
    dos que expat acepta. Mirar sólo la primera dejaría pasar un *billion laughs*
    escrito en UTF-16, que es justo el agujero que este chequeo existe para cerrar.
    """
    inicio = crudo[:_PROLOGO]
    lecturas = (
        inicio.decode("latin-1"),
        inicio.decode("utf-16-le", errors="ignore"),
        inicio.decode("utf-16-be", errors="ignore"),
    )
    if any("<!DOCTYPE" in texto for texto in lecturas):
        raise ErrorDeLectura(
            f"{ruta}: el documento declara un DOCTYPE. verifactu-lint no procesa DTD "
            "ni entidades — un registro de facturación no las necesita, y admitirlas "
            "abre la puerta a un XML que agota la memoria del proceso."
        )


def _explica_mal_formado(crudo: bytes, exc: Exception, ruta: Path) -> str:
    """El mensaje de un XML que no se pudo parsear, y por qué, si se puede decir.

    El caso que merece explicación propia es el de la codificación: un fichero que
    declara UTF-8 —o no declara nada, que en XML significa lo mismo— y está escrito en
    ISO-8859-1 o Windows-1252, como hacen muchos ERP. El mensaje de expat («invalid
    token») no lo dice, y la causa no es evidente para quien lo lee.
    """
    m = _DECLARACION.search(crudo[:512])
    declarada = m.group(1).decode("ascii").lower() if m else None
    if declarada in (None, "utf-8", "utf8"):
        try:
            crudo.decode("utf-8")
        except UnicodeDecodeError as error:
            linea = crudo[: error.start].count(b"\n") + 1
            origen = (
                "declara UTF-8" if declarada
                else "no declara codificación (y entonces es UTF-8)"
            )
            return (
                f"{ruta}: línea {linea}: el fichero {origen}, pero contiene bytes que no son "
                f"UTF-8 (0x{crudo[error.start]:02X}). Suele ser un fichero escrito en "
                "ISO-8859-1 o Windows-1252: declara su codificación real en "
                '<?xml version="1.0" encoding="..."?> o escríbelo en UTF-8.'
            )
    return f"{ruta}: XML mal formado ({exc})"


def _documento(origen: Path | str) -> tuple[ET.Element, bytes]:
    """Lee y parsea el fichero, una sola vez y en bytes.

    **En bytes, no como texto, desde 0.4.0.** Antes se leía forzando UTF-8 con
    `errors="replace"`, y eso ignoraba la codificación que el propio XML declara: un
    fichero ISO-8859-1 con una «Ñ» o un «º» en el número de serie se leía con un
    carácter de sustitución, la huella recalculada no cuadraba y salía un ERROR de
    huella sobre un registro correcto. Pasándole los bytes, expat aplica la
    codificación declarada, que es lo que manda la especificación de XML; y si los
    bytes no corresponden a la que declara, lo dice en vez de leer otra cosa.
    """
    ruta = Path(origen)
    try:
        crudo = ruta.read_bytes()
    except OSError as exc:
        raise ErrorDeLectura(f"{ruta}: no se pudo abrir ({exc})") from exc

    _rechaza_doctype(crudo, ruta)

    try:
        raiz = ET.fromstring(crudo)  # noqa: S314
    except ET.ParseError as exc:
        raise ErrorDeLectura(_explica_mal_formado(crudo, exc, ruta)) from exc
    except (ValueError, LookupError) as exc:
        # expat sólo admite codificaciones de un byte por carácter, UTF-8 y UTF-16.
        raise ErrorDeLectura(
            f"{ruta}: codificación no admitida ({exc}). Escríbelo en UTF-8."
        ) from exc
    return raiz, crudo


def _lineas_de(crudo: bytes, etiquetas: tuple[str, ...], esperados: int) -> list[int | None]:
    """Línea del XML en que abre cada elemento con esas etiquetas, en orden.

    `xml.etree` no da números de línea, así que se buscan las aperturas en los bytes.
    **Sólo se usan si cuadran**: si el número de aperturas encontradas no coincide con
    el de elementos parseados —un comentario que contiene una etiqueta, un fichero en
    UTF-16—, se devuelve `None` para todos. Una línea equivocada es peor que ninguna.
    """
    patron = re.compile(
        rb"<(?:[A-Za-z_][\w.\-]*:)?(?:"
        + b"|".join(e.encode() for e in etiquetas)
        + rb")[\s/>]"
    )
    posiciones = [m.start() for m in patron.finditer(crudo)]
    if len(posiciones) != esperados:
        return [None] * esperados
    lineas: list[int | None] = []
    contadas, previa = 1, 0
    for pos in posiciones:
        contadas += crudo.count(b"\n", previa, pos)
        previa = pos
        lineas.append(contadas)
    return lineas


def lee(origen: Path | str) -> list[Registro]:
    """Lee un fichero XML y devuelve sus registros en orden de aparición.

    El orden importa y por eso se conserva: el encadenamiento es una secuencia, y un
    hallazgo que dice «se rompe entre el 40 y el 41» sólo es accionable si esos
    números corresponden a lo que el usuario ve en su fichero.
    """
    raiz, crudo = _documento(origen)

    registros: list[Registro] = []
    for nodo in raiz.iter():
        nombre = _local(nodo.tag)
        if nombre == "RegistroAlta":
            registros.append(_lee_alta(nodo, len(registros)))
        elif nombre == "RegistroAnulacion":
            registros.append(_lee_anulacion(nodo, len(registros)))

    lineas = _lineas_de(crudo, ("RegistroAlta", "RegistroAnulacion"), len(registros))
    return [replace(r, linea_xml=linea) for r, linea in zip(registros, lineas, strict=True)]


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
    raiz, crudo = _documento(origen)

    eventos: list[Evento] = []
    for nodo in raiz.iter():
        if _local(nodo.tag) != "RegistroEvento":
            continue
        cuerpo = _hijo(nodo, "Evento")
        # El diseño mete todo bajo `Evento`; si un emisor lo aplana, se lee el propio
        # `RegistroEvento` antes que devolver un evento vacío.
        eventos.append(_lee_evento(cuerpo if cuerpo is not None else nodo, len(eventos)))

    lineas = _lineas_de(crudo, ("RegistroEvento",), len(eventos))
    return [replace(e, linea_xml=linea) for e, linea in zip(eventos, lineas, strict=True)]
