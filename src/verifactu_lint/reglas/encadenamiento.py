"""Reglas sobre la huella y el encadenamiento.

Es la familia que da sentido al resto: el artículo 13 del RRSIF encadena cada
registro con el anterior precisamente para que una modificación posterior sea
detectable. Una cadena rota no es un defecto estético — es la prueba de que los
registros conservados no son los que se generaron.
"""

from __future__ import annotations

import re
from itertools import pairwise
from typing import NamedTuple

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


def _por_obligado(registros: list[Registro]) -> list[list[Registro]]:
    """Los registros agrupados por emisor, cada grupo en su orden del fichero.

    **Una cadena por obligado tributario, no una por fichero.** Lo dice la AEAT en sus
    preguntas frecuentes sobre trazabilidad: «Un SIF tiene una única cadena de RF (por
    cada obligado tributario que gestione, en el caso de que gestione varios dentro de
    él)». Hasta 0.4.0 el fichero se auditaba como una sola cadena, y un SIF multi-OT que
    exportara dos obligados intercalados —cada uno con su cadena perfecta— recibía
    errores de cadena rota y de «más de un primer registro» que no existían.

    Se agrupa sólo por emisor, no por número de instalación: si una cadena cambia de
    instalación a mitad, partirla por ahí escondería justo la rotura que hay que ver.
    """
    grupos: dict[str, list[Registro]] = {}
    for r in registros:
        grupos.setdefault((r.id_emisor or "").strip(), []).append(r)
    return list(grupos.values())


def _literal_primero(valor: str | None) -> list[str]:
    """Las formas admisibles de un importe, empezando por la que está escrita.

    `variantes_numericas` no garantiza ese orden —para `21.40` da primero `21.4`—, y la
    forma escrita es la que usa quien recalcula la huella por su cuenta para comparar.
    """
    escrita = (valor or "").strip()
    formas = variantes_numericas(escrita)
    return [escrita, *(f for f in formas if f != escrita)] if escrita in formas else formas


class _Calculo(NamedTuple):
    cuota: str
    importe: str
    cadena: str
    huella: str


def _calculos_admisibles(registro: Registro) -> list[_Calculo]:
    """Cada huella que sería correcta para este registro, con la cadena que la produce.

    Hay más de una porque la orden admite `123.1` y `123.10` como el mismo importe,
    y cada forma produce un SHA-256 distinto. Calcular sólo una y compararla sería
    declarar incorrecto lo que la AEAT acepta.

    **La primera es siempre la de los importes tal como están escritos**, que es la que
    se muestra como «Calculada». Hasta 0.4.0 se mostraba la primera variante, que para
    `21.40` era `21.4`: quien comparaba con su propio cálculo sobre el valor literal
    veía un tercer hash y no sabía de dónde salía (estudio S1, I-6).

    El producto cartesiano está acotado a mano: dos campos numéricos con dos formas
    cada uno son cuatro combinaciones como mucho.
    """
    if registro.tipo == "anulacion":
        cadena = cadena_canonica(
            CAMPOS_ANULACION,
            [
                registro.id_emisor,
                registro.num_serie,
                registro.fecha_expedicion,
                registro.anterior_huella,
                registro.fecha_hora_huso,
            ],
        )
        return [_Calculo("", "", cadena, huella(cadena))]

    calculos: list[_Calculo] = []
    for cuota in _literal_primero(registro.cuota_total):
        for importe in _literal_primero(registro.importe_total):
            cadena = cadena_canonica(
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
            calculos.append(_Calculo(cuota, importe, cadena, huella(cadena)))
    return calculos


def _importes(calculo: _Calculo) -> str:
    return f"CuotaTotal={calculo.cuota}, ImporteTotal={calculo.importe}"


def _explica_calculo(calculos: list[_Calculo], es_alta: bool) -> str:
    """El bloque «Calculada» de RRSIF001: qué se calculó y sobre qué cadena."""
    literal = calculos[0]
    if not es_alta:
        return f"Calculada: {literal.huella}\nSobre la cadena: {literal.cadena}"
    lineas = [
        f"Calculada: {literal.huella} (importes tal como están escritos: "
        f"{_importes(literal)})",
        f"Sobre la cadena: {literal.cadena}",
    ]
    if len(calculos) > 1:
        lineas.append(
            "Formas equivalentes de los importes, que la orden admite y producen otra "
            "huella (tampoco coinciden):"
        )
        lineas.extend(f"  {_importes(c)}: {c.huella}" for c in calculos[1:])
    return "\n".join(lineas)


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

        calculos = _calculos_admisibles(r)
        if declarada in {c.huella for c in calculos}:
            continue

        hallazgos.append(
            Hallazgo(
                regla="RRSIF001",
                severidad=Severidad.ERROR,
                titulo="La huella declarada no coincide con la calculada",
                detalle=(
                    f"Declarada: {declarada}\n"
                    f"{_explica_calculo(calculos, r.tipo == 'alta')}\n"
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
    """RRSIF003 — cada registro encadena con la huella del anterior del mismo obligado."""
    hallazgos: list[Hallazgo] = []
    for cadena in _por_obligado(registros):
        hallazgos.extend(_cadena_continua(cadena))
    return hallazgos


def _cadena_continua(registros: list[Registro]) -> list[Hallazgo]:
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
    """RRSIF004 — `PrimerRegistro` y `RegistroAnterior` son excluyentes, y sólo uno por obligado."""
    hallazgos: list[Hallazgo] = []
    for cadena in _por_obligado(registros):
        hallazgos.extend(_primer_registro_coherente(cadena))
    return hallazgos


def _primer_registro_coherente(registros: list[Registro]) -> list[Hallazgo]:
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
