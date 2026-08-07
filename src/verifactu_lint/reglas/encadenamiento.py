"""Reglas sobre la huella y el encadenamiento.

Es la familia que da sentido al resto: el artículo 13 del RRSIF encadena cada
registro con el anterior precisamente para que una modificación posterior sea
detectable. Una cadena rota no es un defecto estético — es la prueba de que los
registros conservados no son los que se generaron.
"""

from __future__ import annotations

import re
from itertools import pairwise

from verifactu_lint.hallazgos import Hallazgo, Severidad
from verifactu_lint.huella import (
    CAMPOS_ALTA,
    CAMPOS_ANULACION,
    cadena_canonica,
    huella,
    variantes_numericas,
)
from verifactu_lint.registros import Registro

# 64 caracteres hexadecimales en mayúsculas: el «Datos de salida» del documento
# técnico de la AEAT no admite otra forma.
FORMATO_HUELLA = re.compile(r"^[0-9A-F]{64}$")

NORMA_HUELLA = "Orden HAC/1177/2024, art. 13 y especificaciones técnicas de la huella"


def _huellas_admisibles(registro: Registro) -> list[str]:
    """Todas las huellas que serían correctas para este registro.

    Hay más de una porque la orden admite `123.1` y `123.10` como el mismo importe,
    y cada forma produce un SHA-256 distinto. Calcular sólo una y compararla sería
    declarar incorrecto lo que la AEAT acepta.

    El producto cartesiano está acotado a mano: dos campos numéricos con dos formas
    cada uno son cuatro combinaciones como mucho.
    """
    if registro.tipo == "anulacion":
        return [
            huella(
                cadena_canonica(
                    CAMPOS_ANULACION,
                    [
                        registro.id_emisor,
                        registro.num_serie,
                        registro.fecha_expedicion,
                        registro.anterior_huella,
                        registro.fecha_hora_huso,
                    ],
                )
            )
        ]

    admisibles: list[str] = []
    for cuota in variantes_numericas(registro.cuota_total or ""):
        for importe in variantes_numericas(registro.importe_total or ""):
            admisibles.append(
                huella(
                    cadena_canonica(
                        CAMPOS_ALTA,
                        [
                            registro.id_emisor,
                            registro.num_serie,
                            registro.fecha_expedicion,
                            registro.tipo_factura,
                            cuota,
                            importe,
                            registro.anterior_huella,
                            registro.fecha_hora_huso,
                        ],
                    )
                )
            )
    return admisibles


def huella_correcta(registros: list[Registro]) -> list[Hallazgo]:
    """RRSIF001 — la huella declarada debe salir de los campos del registro."""
    hallazgos: list[Hallazgo] = []
    for r in registros:
        declarada = (r.huella or "").strip().upper()
        if not declarada:
            hallazgos.append(
                Hallazgo(
                    regla="RRSIF001",
                    severidad=Severidad.ERROR,
                    titulo="El registro no informa el campo Huella",
                    detalle=(
                        "La huella siempre se informa, también en el primer registro "
                        "del SIF. Sin ella el registro no es verificable ni encadenable."
                    ),
                    norma=NORMA_HUELLA,
                    referencia=r.referencia,
                    orden=r.orden,
                )
            )
            continue

        admisibles = _huellas_admisibles(r)
        if declarada in admisibles:
            continue

        hallazgos.append(
            Hallazgo(
                regla="RRSIF001",
                severidad=Severidad.ERROR,
                titulo="La huella declarada no coincide con la calculada",
                detalle=(
                    f"Declarada: {declarada}\n"
                    f"Calculada: {admisibles[0]}\n"
                    "En una remisión VERI*FACTU la AEAT marcaría este registro como "
                    '"Aceptado con errores". Las causas habituales son el separador "&" '
                    "final sobrante, el orden de los campos, o no recortar los espacios "
                    "de los valores."
                ),
                norma=NORMA_HUELLA,
                referencia=r.referencia,
                orden=r.orden,
            )
        )
    return hallazgos


def formato_de_huella(registros: list[Registro]) -> list[Hallazgo]:
    """RRSIF002 — 64 caracteres hexadecimales en mayúsculas."""
    hallazgos: list[Hallazgo] = []
    for r in registros:
        valor = (r.huella or "").strip()
        if not valor or FORMATO_HUELLA.match(valor):
            continue
        if FORMATO_HUELLA.match(valor.upper()):
            hallazgos.append(
                Hallazgo(
                    regla="RRSIF002",
                    severidad=Severidad.ERROR,
                    titulo="La huella está en minúsculas",
                    detalle=(
                        "El formato de salida es hexadecimal en mayúsculas. El valor es "
                        "correcto pero su representación no, y la comparación de la AEAT "
                        "es sobre la cadena."
                    ),
                    norma=NORMA_HUELLA,
                    referencia=r.referencia,
                    orden=r.orden,
                )
            )
        else:
            hallazgos.append(
                Hallazgo(
                    regla="RRSIF002",
                    severidad=Severidad.ERROR,
                    titulo="La huella no tiene el formato exigido",
                    detalle=(
                        f"Se esperan 64 caracteres hexadecimales en mayúsculas y se "
                        f"encontraron {len(valor)}: {valor[:80]}"
                    ),
                    norma=NORMA_HUELLA,
                    referencia=r.referencia,
                    orden=r.orden,
                )
            )
    return hallazgos


def cadena_continua(registros: list[Registro]) -> list[Hallazgo]:
    """RRSIF003 — cada registro encadena con la huella del anterior."""
    hallazgos: list[Hallazgo] = []
    for previo, actual in pairwise(registros):
        declarada_anterior = (actual.anterior_huella or "").strip().upper()
        huella_previa = (previo.huella or "").strip().upper()

        if not declarada_anterior:
            if actual.es_primer_registro:
                continue  # RRSIF004 se ocupa de si eso tiene sentido aquí
            hallazgos.append(
                Hallazgo(
                    regla="RRSIF003",
                    severidad=Severidad.ERROR,
                    titulo="El registro no encadena con ninguno anterior",
                    detalle=(
                        "No informa Encadenamiento/RegistroAnterior/Huella y tampoco se "
                        "declara como primer registro del SIF."
                    ),
                    norma=NORMA_HUELLA,
                    referencia=actual.referencia,
                    orden=actual.orden,
                )
            )
            continue

        if not huella_previa:
            hallazgos.append(
                Hallazgo(
                    regla="RRSIF003",
                    severidad=Severidad.INCOMPLETO,
                    titulo="No se puede comprobar el encadenamiento",
                    detalle=(
                        f"El registro anterior ({previo.referencia}) no informa su propia "
                        "huella, así que no hay con qué comparar."
                    ),
                    norma=NORMA_HUELLA,
                    referencia=actual.referencia,
                    orden=actual.orden,
                )
            )
            continue

        if declarada_anterior != huella_previa:
            hallazgos.append(
                Hallazgo(
                    regla="RRSIF003",
                    severidad=Severidad.ERROR,
                    titulo="La cadena se rompe en este registro",
                    detalle=(
                        f"Declara como huella anterior {declarada_anterior}, y la huella "
                        f"de {previo.referencia} es {huella_previa}.\n"
                        "Una cadena rota significa que la secuencia conservada no es la "
                        "que se generó: falta un registro por medio, se reordenaron, o se "
                        "modificó uno después de emitirlo."
                    ),
                    norma=NORMA_HUELLA,
                    referencia=actual.referencia,
                    orden=actual.orden,
                )
            )
    return hallazgos


def primer_registro_coherente(registros: list[Registro]) -> list[Hallazgo]:
    """RRSIF004 — `PrimerRegistro` y `RegistroAnterior` son excluyentes, y sólo uno."""
    hallazgos: list[Hallazgo] = []
    primeros = [r for r in registros if r.es_primer_registro]

    for r in primeros:
        if (r.anterior_huella or "").strip():
            hallazgos.append(
                Hallazgo(
                    regla="RRSIF004",
                    severidad=Severidad.ERROR,
                    titulo="Se declara primer registro y a la vez informa uno anterior",
                    detalle=(
                        "PrimerRegistro vale S, luego el bloque RegistroAnterior no debe "
                        "informarse. Son excluyentes por diseño de registro."
                    ),
                    norma="Orden HAC/1177/2024, anexo — diseño del bloque Encadenamiento",
                    referencia=r.referencia,
                    orden=r.orden,
                )
            )

    if len(primeros) > 1:
        for r in primeros[1:]:
            hallazgos.append(
                Hallazgo(
                    regla="RRSIF004",
                    severidad=Severidad.ERROR,
                    titulo="Hay más de un registro declarado como primero",
                    detalle=(
                        f"{len(primeros)} registros declaran PrimerRegistro=S. Un SIF tiene "
                        "una única cadena y por tanto un único primer registro; varios "
                        "indican cadenas mezcladas o un reinicio no previsto."
                    ),
                    norma="Orden HAC/1177/2024, anexo — diseño del bloque Encadenamiento",
                    referencia=r.referencia,
                    orden=r.orden,
                )
            )

    if registros and not primeros and not (registros[0].anterior_huella or "").strip():
        hallazgos.append(
            Hallazgo(
                regla="RRSIF004",
                severidad=Severidad.INCOMPLETO,
                titulo="No consta el inicio de la cadena",
                detalle=(
                    "El primer registro del fichero no declara PrimerRegistro=S ni informa "
                    "un registro anterior. Puede ser correcto si el fichero es un tramo de "
                    "una cadena más larga: en ese caso hay que comprobar el enlace contra "
                    "el registro que lo precede fuera de este fichero."
                ),
                norma="Orden HAC/1177/2024, anexo — diseño del bloque Encadenamiento",
                referencia=registros[0].referencia,
                orden=registros[0].orden,
            )
        )
    return hallazgos


def tipo_de_huella(registros: list[Registro]) -> list[Hallazgo]:
    """RRSIF005 — `TipoHuella` sólo admite `01` (SHA-256) a día de hoy."""
    hallazgos: list[Hallazgo] = []
    for r in registros:
        valor = (r.tipo_huella or "").strip()
        if not valor:
            hallazgos.append(
                Hallazgo(
                    regla="RRSIF005",
                    severidad=Severidad.AVISO,
                    titulo="No se informa TipoHuella",
                    detalle=(
                        "El diseño de registro incluye TipoHuella y la lista L12 sólo "
                        "admite 01 (SHA-256). Omitirlo deja implícito lo que la orden pide "
                        "explícito."
                    ),
                    norma="Orden HAC/1177/2024, anexo apartado 6, lista L12",
                    referencia=r.referencia,
                    orden=r.orden,
                )
            )
        elif valor != "01":
            hallazgos.append(
                Hallazgo(
                    regla="RRSIF005",
                    severidad=Severidad.ERROR,
                    titulo=f"TipoHuella={valor} no está admitido",
                    detalle="El único algoritmo permitido por la lista L12 es 01 (SHA-256).",
                    norma="Orden HAC/1177/2024, anexo apartado 6, lista L12",
                    referencia=r.referencia,
                    orden=r.orden,
                )
            )
    return hallazgos


REGLAS = (
    huella_correcta,
    formato_de_huella,
    cadena_continua,
    primer_registro_coherente,
    tipo_de_huella,
)
