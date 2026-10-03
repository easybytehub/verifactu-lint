"""Reglas sobre la estructura del registro y el formato de sus fechas.

**Por qué esta familia existe, si el XSD ya comprueba la forma.** El resto de reglas
leen cada dato en la ruta que fija el esquema, y un dato escrito en otra ruta cuenta
como ausente. Un registro con su propia estructura —`<Factura><TipoFactura>` en vez
de `TipoFactura` colgando de `RegistroAlta`— recibía hasta 0.4.0 una cascada de
hallazgos ciertos y engañosos: «no informa TipoFactura», «no tiene desglose», «no
informa Huella». Quien los lee busca datos que faltan, y los datos están (estudio S1,
incidencias I-2 e I-3). Aquí se nombra la causa una vez, antes que las consecuencias.

Las dos reglas de formato (I-1 e I-4) son el otro hueco que dejaba la tesis
«complementaria al XSD»: la fecha `dd-mm-aaaa` sí la caza el esquema, pero quien no
valida contra él no se enteraba; y el huso horario de `FechaHoraHusoGenRegistro` no
lo caza ni el esquema, que tipa el campo como `xs:dateTime` y lo admite sin huso,
aunque la orden lo exige.

Esto **no** es una validación XSD: no comprueba orden ni obligatoriedad de cada
elemento. Para eso está el esquema, y el paquete sigue sin dependencias.
"""

from __future__ import annotations

import re
from dataclasses import replace
from datetime import date

from verifactu_lint.hallazgos import Hallazgo, Severidad
from verifactu_lint.registros import ID_FACTURA, ElementoInesperado, Registro

NORMA_ESTRUCTURA = (
    "Orden HAC/1177/2024, arts. 10.c) y 11.c) y anexo, ap. 2.3 y 2.4; "
    "SuministroInformacion.xsd (AEAT)"
)
NORMA_ANULACION = (
    "Orden HAC/1177/2024, anexo, ap. 2.4 — bloque «RegistroAnulacion», IDFactura; "
    "SuministroInformacion.xsd, IDFacturaExpedidaBajaType"
)
NORMA_FECHA = (
    "Orden HAC/1177/2024, anexo, ap. 2.3 y 2.4 — Fecha (dd-mm-yyyy); "
    "SuministroInformacion.xsd, tipo «fecha»; Validaciones y errores AEAT v1.2.2, §3.1"
)
NORMA_HUSO = (
    "Orden HAC/1177/2024, art. 7.g) y anexo, ap. 2.3 y 2.4 — "
    "DateTime, formato YYYY-MM-DDThh:mm:ssTZD (ISO 8601); "
    "Diseño de registro AEAT v1.0 (DsRegistroVeriFactu.xlsx)"
)

# Las reglas cuyo hallazgo explica otros. Van primero en el informe y anotan los
# hallazgos de los mismos registros: ver `anota_cascada`.
CAUSAS_RAIZ = frozenset({"RRSIF050", "RRSIF051"})

_FECHA = re.compile(r"^(\d{2})-(\d{2})-(\d{4})$")
_FECHA_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# `YYYY-MM-DDThh:mm:ss`, fracción opcional y TZD opcional: así se distingue «le falta
# el huso» de «no es una fecha y hora», que son dos defectos con dos explicaciones.
_FECHA_HORA = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?P<fraccion>\.\d+)?(?P<tzd>Z|[+-]\d{2}:\d{2})?$"
)


def _plural(n: int, singular: str, plural: str) -> str:
    return f"{n} {singular if n == 1 else plural}"


def _enumera(nombres: list[str] | tuple[str, ...]) -> str:
    if len(nombres) == 1:
        return nombres[0]
    return ", ".join(nombres[:-1]) + " y " + nombres[-1]


def _referencias(afectados: list[Registro], tope: int = 5) -> str:
    texto = ", ".join(r.referencia for r in afectados[:tope])
    if len(afectados) > tope:
        texto += f" y {len(afectados) - tope} más"
    return texto


def _explicado_por_rrsif051(registro: Registro, elemento: ElementoInesperado) -> bool:
    """Un nombre del alta dentro del `IDFactura` de una anulación es cosa de RRSIF051.

    Contarlo también aquí daría dos hallazgos para un solo defecto.
    """
    padre, _, nombre = elemento.ruta.rpartition("/")
    return (
        registro.tipo == "anulacion"
        and padre == "RegistroAnulacion/IDFactura"
        and nombre in ID_FACTURA["RegistroAlta"]
    )


def _inesperados(registro: Registro) -> list[ElementoInesperado]:
    return [e for e in registro.fuera_de_esquema if not _explicado_por_rrsif051(registro, e)]


def estructura_del_esquema(registros: list[Registro]) -> list[Hallazgo]:
    """RRSIF050 — los elementos del registro están donde el esquema los prevé.

    **Un solo hallazgo para todo el fichero**, con cada ruta inesperada y en cuántos
    registros aparece. Un generador con su propia estructura la repite en todos sus
    registros, y un hallazgo por registro enterraría lo único que hay que leer.

    Cuando el elemento inesperado lleva dentro datos que el esquema espera en el
    bloque padre —`TipoFactura` dentro de un `<Factura>` inventado—, se dice: es la
    diferencia entre «falta TipoFactura» y «TipoFactura está en otra ruta».
    """
    # Por número de orden y no por registro: comparar `Registro` entre sí es comparar
    # todos sus campos, y en un fichero de veinte mil registros eso se nota.
    por_ruta: dict[str, set[int]] = {}
    ejemplo: dict[str, ElementoInesperado] = {}
    contiene: dict[str, list[str]] = {}
    registros_afectados: list[Registro] = []
    for r in registros:
        inesperados = _inesperados(r)
        if inesperados:
            registros_afectados.append(r)
        for elemento in inesperados:
            por_ruta.setdefault(elemento.ruta, set()).add(r.orden)
            ejemplo.setdefault(elemento.ruta, elemento)
            dentro = contiene.setdefault(elemento.ruta, [])
            for nombre in elemento.contiene:
                if nombre not in dentro:
                    dentro.append(nombre)
    if not registros_afectados:
        return []

    total = len(registros)
    lineas: list[str] = []
    for ruta, afectados in por_ruta.items():
        bloque = ruta.rpartition("/")[0].rpartition("/")[2]
        linea = f"  {ruta} — en {len(afectados)} de {_plural(total, 'registro', 'registros')}."
        if contiene[ruta]:
            linea += (
                f" Lleva dentro {_enumera(contiene[ruta])}, que el esquema espera "
                f"directamente en {bloque}."
            )
        elif ejemplo[ruta].en_un_valor:
            linea += f" {bloque} lleva un valor, no elementos."
        lineas.append(linea)

    primero = registros_afectados[0]
    titulo = (
        "La estructura del registro no corresponde al esquema"
        if len(registros_afectados) == 1
        else f"La estructura de {len(registros_afectados)} registros no corresponde al esquema"
    )
    return [
        Hallazgo(
            regla="RRSIF050",
            severidad=Severidad.ERROR,
            titulo=titulo,
            detalle=(
                "Elementos en posiciones que el esquema no prevé:\n"
                + "\n".join(lineas)
                + "\nUn registro así no valida contra SuministroInformacion.xsd. Y como "
                "las demás reglas leen cada dato en la ruta del esquema, un dato escrito "
                "en otra cuenta como ausente: los hallazgos que siguen sobre estos "
                "registros llevan una nota cuando pueden ser consecuencia de esto. "
                "Corrige primero la estructura."
            ),
            norma=NORMA_ESTRUCTURA,
            referencia=primero.referencia,
            orden=primero.orden,
        )
    ]


def identificacion_de_la_anulacion(registros: list[Registro]) -> list[Hallazgo]:
    """RRSIF051 — la anulación identifica la factura con sus tres campos obligatorios.

    Es el equivalente, para la anulación, de lo que RRSIF030 comprueba en el alta: un
    campo obligatorio que falta. Y tiene una causa típica que merece nombre propio
    (estudio S1, I-3): escribir `IDEmisorFactura`, `NumSerieFactura` y
    `FechaExpedicionFactura`, que son los nombres del **alta**. En la anulación llevan
    el sufijo «Anulada», así que el parser los lee vacíos, la referencia sale «(sin
    NumSerieFactura)» y lo único que se veía era RRSIF001: la huella no cuadra. Cierto,
    pero sin la causa.

    Se agrega por causa: un generador que se equivoca de nombres lo hace en todas sus
    anulaciones.
    """
    nombres = ID_FACTURA["RegistroAnulacion"]
    con_nombres_de_alta: list[tuple[Registro, list[str], list[str]]] = []
    sin_campos: dict[tuple[str, ...], list[Registro]] = {}
    anulaciones = [r for r in registros if r.tipo == "anulacion"]
    for r in anulaciones:
        valores = (r.id_emisor, r.num_serie, r.fecha_expedicion)
        faltan = [n for n, v in zip(nombres, valores, strict=True) if not (v or "").strip()]
        if not faltan:
            continue
        de_alta = [
            e.ruta.rpartition("/")[2] for e in r.fuera_de_esquema
            if _explicado_por_rrsif051(r, e)
        ]
        if de_alta:
            con_nombres_de_alta.append((r, faltan, de_alta))
        else:
            sin_campos.setdefault(tuple(faltan), []).append(r)

    hallazgos: list[Hallazgo] = []
    total = len(anulaciones)
    if con_nombres_de_alta:
        afectados = [x[0] for x in con_nombres_de_alta]
        de_alta = sorted({n for x in con_nombres_de_alta for n in x[2]},
                         key=ID_FACTURA["RegistroAlta"].index)
        correctos = [nombres[ID_FACTURA["RegistroAlta"].index(n)] for n in de_alta]
        hallazgos.append(
            Hallazgo(
                regla="RRSIF051",
                severidad=Severidad.ERROR,
                titulo="La anulación identifica la factura con los nombres del registro de alta",
                detalle=(
                    f"IDFactura lleva {_enumera(de_alta)}, que son los nombres del alta. "
                    f"En un registro de anulación el esquema los llama {_enumera(correctos)}.\n"
                    "Leídos con su nombre correcto, esos campos faltan, y la huella se "
                    "calcula con ellos vacíos: si además sale RRSIF001 en estos registros, "
                    "es por esto y no por el cálculo.\n"
                    f"Afecta a {len(afectados)} de "
                    f"{_plural(total, 'registro de anulación', 'registros de anulación')}: "
                    f"{_referencias(afectados)}."
                ),
                norma=NORMA_ANULACION,
                referencia=afectados[0].referencia,
                orden=afectados[0].orden,
            )
        )
    for ausentes, afectados in sin_campos.items():
        hallazgos.append(
            Hallazgo(
                regla="RRSIF051",
                severidad=Severidad.ERROR,
                titulo=(
                    "El registro de anulación no informa "
                    + (", ".join(ausentes[:-1]) + " ni " + ausentes[-1] if len(ausentes) > 1
                       else ausentes[0])
                ),
                detalle=(
                    f"{_enumera(list(nombres))} son obligatorios en el IDFactura de una "
                    "anulación: identifican la factura que se anula y entran en la huella "
                    "(Orden HAC/1177/2024, art. 13.1.b).\n"
                    f"Afecta a {len(afectados)} de "
                    f"{_plural(total, 'registro de anulación', 'registros de anulación')}: "
                    f"{_referencias(afectados)}."
                ),
                norma=NORMA_ANULACION,
                referencia=afectados[0].referencia,
                orden=afectados[0].orden,
            )
        )
    return hallazgos


def _campos_de_fecha(r: Registro) -> list[tuple[str, str | None]]:
    """Las fechas `dd-mm-aaaa` que lee el parser, con su ruta en el registro."""
    raiz = "RegistroAlta" if r.tipo == "alta" else "RegistroAnulacion"
    return [
        (f"IDFactura/{ID_FACTURA[raiz][2]}", r.fecha_expedicion),
        ("Encadenamiento/RegistroAnterior/FechaExpedicionFactura", r.anterior_fecha_expedicion),
    ]


def _es_fecha(valor: str) -> bool:
    m = _FECHA.match(valor)
    if not m:
        return False
    dia, mes, anio = (int(x) for x in m.groups())
    try:
        date(anio, mes, dia)
    except ValueError:
        return False
    return True


def formato_de_fecha(registros: list[Registro]) -> list[Hallazgo]:
    """RRSIF052 — las fechas de expedición van en `dd-mm-aaaa`.

    El anexo de la orden da a `FechaExpedicionFactura` (y a su gemela de la anulación y
    a la del registro anterior) el formato «Fecha (dd-mm-yyyy)», y el esquema la tipa
    con el patrón `\\d{2,2}-\\d{2,2}-\\d{4,4}`. El XSD ya lo caza; la regla existe para
    quien no valida contra él, y porque la fecha entra en la huella tal como está
    escrita (estudio S1, I-4).

    Un campo vacío no es asunto de esta regla: de eso se ocupan RRSIF051 y el XSD.
    """
    por_campo: dict[str, list[tuple[Registro, str]]] = {}
    for r in registros:
        for campo, valor in _campos_de_fecha(r):
            limpio = (valor or "").strip()
            if limpio and not _es_fecha(limpio):
                por_campo.setdefault(campo, []).append((r, limpio))

    hallazgos: list[Hallazgo] = []
    for campo, casos in por_campo.items():
        r, valor = casos[0]
        if _FECHA_ISO.match(valor):
            pista = (
                f"Parece una fecha ISO (aaaa-mm-dd): «{valor}» se escribe "
                f"«{valor[8:10]}-{valor[5:7]}-{valor[0:4]}»."
            )
        elif _FECHA.match(valor):
            pista = f"«{valor}» tiene la forma dd-mm-aaaa, pero no es una fecha del calendario."
        else:
            pista = f"«{valor}» no tiene la forma dd-mm-aaaa."
        hallazgos.append(
            Hallazgo(
                regla="RRSIF052",
                severidad=Severidad.ERROR,
                titulo=f"{campo.rpartition('/')[2]} no tiene el formato dd-mm-aaaa",
                detalle=(
                    f"{campo}, en {len(casos)} de "
                    f"{_plural(len(registros), 'registro', 'registros')} "
                    f"(el primero, {r.referencia}). {pista}\n"
                    "El formato es una validación sintáctica de la AEAT y, a nivel de "
                    "registro, provoca su rechazo. La fecha entra además en la huella tal "
                    "como está escrita."
                ),
                norma=NORMA_FECHA,
                referencia=r.referencia,
                orden=r.orden,
            )
        )
    return hallazgos


def huso_horario(registros: list[Registro]) -> list[Hallazgo]:
    """RRSIF053 — `FechaHoraHusoGenRegistro` lleva el huso horario.

    **La exigencia es de la orden, no del validador de la AEAT, y la severidad sale de
    ahí.** El art. 7.g) dice que la fecha y hora de generación «deberá incluir el huso
    horario aplicado en el momento de la generación del registro», y el anexo —igual
    que el diseño de registro de la AEAT— fija el formato `YYYY-MM-DDThh:mm:ssTZD`.
    En cambio, el XSD tipa el campo como `xs:dateTime`, que admite el valor sin huso,
    y las *Validaciones y errores* v1.2.2 sólo comprueban que no sea posterior a la
    fecha del sistema de la AEAT. Un registro sin huso puede pasar la remisión e
    incumplir igualmente: por eso `ERROR`, y por eso el hallazgo lo dice.

    Las fracciones de segundo son otra cosa: el formato del anexo no las incluye, pero
    `xs:dateTime` las admite y nada en la norma dice que invaliden el registro. Ahí no
    se afirma el incumplimiento: es un `AVISO`.

    Agregado por causa: un generador sin huso lo omite en todos sus registros.
    """
    grupos: dict[str, list[tuple[Registro, str]]] = {
        "falta": [], "formato": [], "sin_huso": [], "fraccion": [],
    }
    for r in registros:
        valor = (r.fecha_hora_huso or "").strip()
        if not valor:
            grupos["falta"].append((r, valor))
            continue
        m = _FECHA_HORA.match(valor)
        if not m:
            grupos["formato"].append((r, valor))
        elif not m.group("tzd"):
            grupos["sin_huso"].append((r, valor))
        elif m.group("fraccion"):
            grupos["fraccion"].append((r, valor))

    total = len(registros)
    formato = (
        "La orden fija el formato YYYY-MM-DDThh:mm:ssTZD (ISO 8601), por ejemplo "
        "2024-01-01T19:20:30+01:00."
    )
    en_la_huella = (
        "El valor entra en la huella tal como está escrito (art. 13.1), así que se "
        "corrige en el generador, no editando registros ya emitidos."
    )
    textos: dict[str, tuple[Severidad, str, str]] = {
        "falta": (
            Severidad.ERROR,
            "No se informa FechaHoraHusoGenRegistro",
            "Es obligatorio en el registro de alta y en el de anulación, y es uno de los "
            "campos de la huella. " + formato,
        ),
        "formato": (
            Severidad.ERROR,
            "FechaHoraHusoGenRegistro no es una fecha y hora en el formato exigido",
            formato + " " + en_la_huella,
        ),
        "sin_huso": (
            Severidad.ERROR,
            "FechaHoraHusoGenRegistro no incluye el huso horario",
            "La orden exige que la fecha y hora de generación incluya «el huso horario "
            "aplicado en el momento de la generación del registro» (art. 7.g). "
            + formato
            + "\nEl XSD (xs:dateTime) admite el valor sin huso y las validaciones que "
            "publica la AEAT (v1.2.2) no lo comprueban, así que una remisión puede no "
            "rechazarse por esto: el incumplimiento es de la orden, no del validador. "
            + en_la_huella,
        ),
        "fraccion": (
            Severidad.AVISO,
            "FechaHoraHusoGenRegistro lleva fracciones de segundo",
            formato
            + " El anexo y el diseño de registro de la AEAT no incluyen fracciones; "
            "xs:dateTime sí las admite y las validaciones de la AEAT no las mencionan, "
            "así que no se afirma un incumplimiento. " + en_la_huella,
        ),
    }

    hallazgos: list[Hallazgo] = []
    for clave, casos in grupos.items():
        if not casos:
            continue
        severidad, titulo, explicacion = textos[clave]
        r, valor = casos[0]
        ejemplo = f"«{valor}» en {r.referencia}" if valor else r.referencia
        hallazgos.append(
            Hallazgo(
                regla="RRSIF053",
                severidad=severidad,
                titulo=titulo,
                detalle=(
                    f"{len(casos)} de {_plural(total, 'registro', 'registros')} "
                    f"(el primero, {ejemplo}).\n{explicacion}"
                ),
                norma=NORMA_HUSO,
                referencia=r.referencia,
                orden=r.orden,
            )
        )
    return hallazgos


def anota_cascada(hallazgos: list[Hallazgo], registros: list[Registro]) -> list[Hallazgo]:
    """Marca los hallazgos que pueden ser consecuencia de una causa raíz.

    **Se anotan, no se suprimen.** Suprimirlos sería más limpio y más peligroso: un
    registro con un elemento de más —una extensión del fabricante, por ejemplo— puede
    tener además la cadena rota de verdad, y callarlo por la estructura sería esconder
    un incumplimiento real detrás de otro. La nota dice de dónde puede venir el
    hallazgo; quien corrige la estructura y vuelve a pasar la herramienta ve qué queda.

    Sólo se anota si el hallazgo de la causa raíz está en el informe: una nota que
    remite a un hallazgo que no aparece no explica nada.
    """
    presentes = {h.regla for h in hallazgos}
    # Por registro: las reglas a las que se aplica cada nota (None, a todas) y su texto.
    notas: dict[int, list[tuple[frozenset[str] | None, str]]] = {}
    if "RRSIF050" in presentes:
        for r in registros:
            if _inesperados(r):
                notas.setdefault(r.orden, []).append((
                    None,
                    f"Nota: {r.referencia} tiene elementos en rutas que el esquema no "
                    "prevé (RRSIF050). Si el dato que este hallazgo echa en falta está en "
                    "una de ellas, es consecuencia de la estructura y no un dato ausente.",
                ))
    if "RRSIF051" in presentes:
        for r in registros:
            identificada = all(
                (v or "").strip() for v in (r.id_emisor, r.num_serie, r.fecha_expedicion)
            )
            if r.tipo == "anulacion" and not identificada:
                # Sólo la huella sale de IDFactura: anotar el resto sería atribuirle
                # hallazgos que no tienen nada que ver.
                notas.setdefault(r.orden, []).append((
                    frozenset({"RRSIF001"}),
                    f"Nota: {r.referencia} no identifica la factura anulada con los campos "
                    "que exige el esquema (RRSIF051), y la huella se ha calculado con esos "
                    "campos vacíos.",
                ))
    if not notas:
        return hallazgos

    def anotado(h: Hallazgo) -> Hallazgo:
        if h.regla in CAUSAS_RAIZ or h.orden is None:
            return h
        propias = [
            texto for reglas, texto in notas.get(h.orden, [])
            if reglas is None or h.regla in reglas
        ]
        return replace(h, detalle=h.detalle + "\n" + "\n".join(propias)) if propias else h

    return [anotado(h) for h in hallazgos]


REGLAS = (
    estructura_del_esquema,
    identificacion_de_la_anulacion,
    formato_de_fecha,
    huso_horario,
)
