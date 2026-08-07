"""Reglas sobre rectificativas, sustitutivas y subsanaciones.

**Por qué esta familia es la que más se equivoca.** Mezcla una decisión de negocio
—qué pasó con la factura— con una tipificación técnica que tiene ocho valores y dos
modalidades, y el sistema funciona igual de bien esté bien o mal puesta. Nada falla
en el momento: el error aparece cuando alguien cruza los datos, que suele ser tarde.

Los códigos salen del esquema oficial `SuministroInformacion.xsd` de la AEAT.
"""

from __future__ import annotations

from verifactu_lint.hallazgos import Hallazgo, Severidad
from verifactu_lint.registros import Registro

NORMA_TIPOS = "Orden HAC/1177/2024, anexo — listas L2 (TipoFactura) y L3 (TipoRectificativa)"
NORMA_FAQ17 = "FAQ desarrolladores AEAT, ap. 17 — rectificaciones, anulaciones y subsanaciones"

TIPOS_FACTURA: dict[str, str] = {
    "F1": "Factura (art. 6, 7.2 y 7.3 del RD 1619/2012)",
    "F2": "Factura simplificada y facturas sin identificación del destinatario",
    "F3": "Factura emitida en sustitución de facturas simplificadas",
    "R1": "Factura rectificativa (art. 80.1 y 80.2 y error fundado en derecho)",
    "R2": "Factura rectificativa (art. 80.3)",
    "R3": "Factura rectificativa (art. 80.4)",
    "R4": "Factura rectificativa (resto)",
    "R5": "Factura rectificativa en facturas simplificadas",
}

TIPOS_RECTIFICATIVA: dict[str, str] = {
    "S": "por sustitución",
    "I": "por diferencias (incremental)",
}


def tipo_factura_valido(registros: list[Registro]) -> list[Hallazgo]:
    """RRSIF030 — `TipoFactura` debe estar en la lista L2."""
    hallazgos: list[Hallazgo] = []
    for r in registros:
        if r.tipo != "alta":
            continue
        valor = (r.tipo_factura or "").strip().upper()
        if not valor:
            hallazgos.append(
                Hallazgo(
                    regla="RRSIF030",
                    severidad=Severidad.ERROR,
                    titulo="El registro de alta no informa TipoFactura",
                    detalle=(
                        "`TipoFactura` es obligatorio y entra además en el cálculo de la "
                        "huella: sin él, ni el registro es válido ni la huella cuadra."
                    ),
                    norma=NORMA_TIPOS,
                    referencia=r.referencia,
                    orden=r.orden,
                )
            )
        elif valor not in TIPOS_FACTURA:
            hallazgos.append(
                Hallazgo(
                    regla="RRSIF030",
                    severidad=Severidad.ERROR,
                    titulo=f"TipoFactura={valor} no existe",
                    detalle="Valores admitidos: " + ", ".join(sorted(TIPOS_FACTURA)),
                    norma=NORMA_TIPOS,
                    referencia=r.referencia,
                    orden=r.orden,
                )
            )
    return hallazgos


def rectificativa_completa(registros: list[Registro]) -> list[Hallazgo]:
    """RRSIF031 — una rectificativa declara su modalidad y a qué factura rectifica."""
    hallazgos: list[Hallazgo] = []
    for r in registros:
        if r.tipo != "alta" or not r.es_rectificativa:
            continue
        tipo = (r.tipo_factura or "").strip().upper()

        modalidad = (r.tipo_rectificativa or "").strip().upper()
        if not modalidad:
            hallazgos.append(
                Hallazgo(
                    regla="RRSIF031",
                    severidad=Severidad.ERROR,
                    titulo=f"La rectificativa {tipo} no informa TipoRectificativa",
                    detalle=(
                        "Toda rectificativa declara si es por sustitución (S) o por "
                        "diferencias (I). Sin ese dato no se puede saber si el importe "
                        "que lleva reemplaza al original o se suma a él, que es "
                        "justamente lo que distingue una de otra."
                    ),
                    norma=NORMA_TIPOS,
                    referencia=r.referencia,
                    orden=r.orden,
                )
            )
        elif modalidad not in TIPOS_RECTIFICATIVA:
            hallazgos.append(
                Hallazgo(
                    regla="RRSIF031",
                    severidad=Severidad.ERROR,
                    titulo=f"TipoRectificativa={modalidad} no existe",
                    detalle="Sólo admite S (sustitutiva) o I (por diferencias).",
                    norma=NORMA_TIPOS,
                    referencia=r.referencia,
                    orden=r.orden,
                )
            )

        if r.facturas_rectificadas == 0:
            # R5 rectifica facturas simplificadas, que pueden no ser identificables
            # una a una: ahí no se puede afirmar el incumplimiento.
            severidad = Severidad.INCOMPLETO if tipo == "R5" else Severidad.ERROR
            hallazgos.append(
                Hallazgo(
                    regla="RRSIF031",
                    severidad=severidad,
                    titulo=f"La rectificativa {tipo} no identifica ninguna factura rectificada",
                    detalle=(
                        "No informa `FacturasRectificadas/IDFacturaRectificada`."
                        + (
                            "\nEn R5 puede ser legítimo si las simplificadas rectificadas "
                            "no eran identificables individualmente; conviene comprobarlo."
                            if tipo == "R5"
                            else ""
                        )
                    ),
                    norma=NORMA_FAQ17,
                    referencia=r.referencia,
                    orden=r.orden,
                )
            )
    return hallazgos


def rectificacion_solo_en_rectificativas(registros: list[Registro]) -> list[Hallazgo]:
    """RRSIF032 — los campos de rectificación no caben en una factura normal.

    Corresponde a los errores **1115** (`TipoRectificativa` sin ser rectificativa) y
    **1117** (`FacturasRectificadas` sin serlo) del listado de la AEAT.

    `ImporteRectificacion` no se comprueba aquí aunque encaje: lo cubre RRSIF033, que
    conoce además la distinción entre sustitutiva y por diferencias. Duplicarlo daría
    dos hallazgos para un solo defecto.
    """
    hallazgos: list[Hallazgo] = []
    for r in registros:
        if r.tipo != "alta" or r.es_rectificativa:
            continue
        tipo = (r.tipo_factura or "").strip().upper()
        sobrantes: list[str] = []
        if (r.tipo_rectificativa or "").strip():
            sobrantes.append("TipoRectificativa")
        if r.facturas_rectificadas:
            sobrantes.append("FacturasRectificadas")
        if not sobrantes:
            continue
        hallazgos.append(
            Hallazgo(
                regla="RRSIF032",
                severidad=Severidad.ERROR,
                titulo=f"Una factura {tipo} informa campos de rectificación",
                detalle=(
                    f"Informa {', '.join(sobrantes)} sin ser rectificativa. O el "
                    "TipoFactura debería ser R1-R5, o esos campos sobran."
                ),
                norma=NORMA_TIPOS,
                referencia=r.referencia,
                orden=r.orden,
            )
        )
    return hallazgos


def importe_rectificacion_correcto(registros: list[Registro]) -> list[Hallazgo]:
    """RRSIF033 — `ImporteRectificacion` va exactamente en las sustitutivas.

    **Esta regla era un aviso y ahora es un error, y la corrección viene del listado
    oficial de códigos de error de la AEAT.** El error **1118** dice que en una
    rectificativa por sustitución el bloque `ImporteRectificacion` es *obligatorio*,
    y el **1119** que en cualquier otro caso no debe tener valor. No es una
    conveniencia para cuadrar a mano: es motivo de rechazo del registro.
    """
    hallazgos: list[Hallazgo] = []
    for r in registros:
        if r.tipo != "alta":
            continue
        sustitutiva = (
            r.es_rectificativa and (r.tipo_rectificativa or "").strip().upper() == "S"
        )
        if sustitutiva and not r.importe_rectificacion:
            hallazgos.append(
                Hallazgo(
                    regla="RRSIF033",
                    severidad=Severidad.ERROR,
                    titulo="Rectificativa por sustitución sin ImporteRectificacion",
                    detalle=(
                        "En una sustitutiva (S) el importe reemplaza al de la factura "
                        "original, y el bloque `ImporteRectificacion` es obligatorio.\n"
                        "La AEAT rechaza el registro con el error 1118."
                    ),
                    norma="Códigos de error AEAT — 1118",
                    referencia=r.referencia,
                    orden=r.orden,
                )
            )
        elif not sustitutiva and r.importe_rectificacion:
            hallazgos.append(
                Hallazgo(
                    regla="RRSIF033",
                    severidad=Severidad.ERROR,
                    titulo="ImporteRectificacion en una factura que no es sustitutiva",
                    detalle=(
                        "El bloque sólo corresponde a las rectificativas por sustitución. "
                        "La AEAT rechaza el registro con el error 1119."
                    ),
                    norma="Códigos de error AEAT — 1119",
                    referencia=r.referencia,
                    orden=r.orden,
                )
            )
    return hallazgos


def sustitucion_de_simplificadas(registros: list[Registro]) -> list[Hallazgo]:
    """RRSIF034 — F3 identifica las simplificadas a las que sustituye.

    F3 es la factura completa que se emite en sustitución de simplificadas ya
    facturadas y declaradas. Sin `FacturasSustituidas`, la operación se declara dos
    veces y no hay forma de saberlo mirando los registros.
    """
    hallazgos: list[Hallazgo] = []
    for r in registros:
        if r.tipo != "alta":
            continue
        tipo = (r.tipo_factura or "").strip().upper()
        if tipo == "F3" and r.facturas_sustituidas == 0:
            hallazgos.append(
                Hallazgo(
                    regla="RRSIF034",
                    severidad=Severidad.ERROR,
                    titulo="F3 sin identificar las facturas sustituidas",
                    detalle=(
                        "Una F3 sustituye a simplificadas ya facturadas y declaradas. Si "
                        "no las identifica en `FacturasSustituidas`, la misma operación "
                        "queda declarada dos veces sin rastro de que son la misma."
                    ),
                    norma=(
                        "FAQ desarrolladores AEAT, ap. 27 — facturas expedidas en "
                        "sustitución de facturas simplificadas"
                    ),
                    referencia=r.referencia,
                    orden=r.orden,
                )
            )
        elif tipo != "F3" and r.facturas_sustituidas:
            hallazgos.append(
                Hallazgo(
                    regla="RRSIF034",
                    severidad=Severidad.ERROR,
                    titulo=f"Una factura {tipo} informa FacturasSustituidas",
                    detalle="Ese bloque corresponde a F3, la sustitución de simplificadas.",
                    norma=NORMA_TIPOS,
                    referencia=r.referencia,
                    orden=r.orden,
                )
            )
    return hallazgos


def subsanacion_valida(registros: list[Registro]) -> list[Hallazgo]:
    """RRSIF035 — `Subsanacion` y `RechazoPrevio` sólo admiten sus valores.

    Subsanar no es rectificar: se subsana un registro que se generó mal —o que la
    AEAT rechazó— mientras que se rectifica una factura cuyo contenido cambia. Que se
    confundan es habitual, y la pista es un registro marcado como subsanación con
    tipo rectificativo.
    """
    hallazgos: list[Hallazgo] = []
    for r in registros:
        subsana = (r.subsanacion or "").strip().upper()
        rechazo = (r.rechazo_previo or "").strip().upper()

        if subsana and subsana not in {"S", "N"}:
            hallazgos.append(
                Hallazgo(
                    regla="RRSIF035",
                    severidad=Severidad.ERROR,
                    titulo=f"Subsanacion={subsana} no es válido",
                    detalle="Sólo admite S o N.",
                    norma=NORMA_TIPOS,
                    referencia=r.referencia,
                    orden=r.orden,
                )
            )
        if rechazo and rechazo not in {"S", "N", "X"}:
            hallazgos.append(
                Hallazgo(
                    regla="RRSIF035",
                    severidad=Severidad.ERROR,
                    titulo=f"RechazoPrevio={rechazo} no es válido",
                    detalle="Sólo admite S, N o X.",
                    norma=NORMA_TIPOS,
                    referencia=r.referencia,
                    orden=r.orden,
                )
            )
        if subsana == "S" and r.es_rectificativa:
            hallazgos.append(
                Hallazgo(
                    regla="RRSIF035",
                    severidad=Severidad.AVISO,
                    titulo="Registro marcado como subsanación y con tipo rectificativo",
                    detalle=(
                        "Subsanar corrige un registro de facturación que se generó mal; "
                        "rectificar corrige una factura cuyo contenido cambia. Los dos a "
                        "la vez suele significar que se ha usado uno por el otro."
                    ),
                    norma=NORMA_FAQ17,
                    referencia=r.referencia,
                    orden=r.orden,
                )
            )
    return hallazgos


REGLAS = (
    tipo_factura_valido,
    rectificativa_completa,
    rectificacion_solo_en_rectificativas,
    importe_rectificacion_correcto,
    sustitucion_de_simplificadas,
    subsanacion_valida,
)
