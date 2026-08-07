"""Cálculo canónico de la huella o «hash» de los registros de facturación.

Implementa el documento *Detalle de las especificaciones técnicas para generación de
la huella o hash de los registros de facturación* (AEAT, versión 0.1.2, 27/08/2024),
que desarrolla el artículo 13 de la Orden HAC/1177/2024.

**Por qué este módulo no tiene dependencias.** Es la única pieza cuya corrección no
admite matices: si la cadena canónica se construye mal, todo lo que hay encima
miente. Un `hashlib` de la biblioteca estándar y nada más significa que no hay
ninguna versión de nada que pueda cambiar el resultado a nuestras espaldas.

Los tres vectores del apartado 6 del documento oficial están en `tests/` y se
ejecutan en cada cambio. Son la definición de correcto aquí: si un día dejan de
pasar, es este módulo el que está mal, no ellos.
"""

from __future__ import annotations

import hashlib
from decimal import Decimal, InvalidOperation

# El orden es normativo y no es alfabético ni casual: coincide con el orden de
# aparición de los campos en los diseños de registro publicados en el anexo de la
# orden. Reordenar cualquiera de estas listas cambia todas las huellas.
CAMPOS_ALTA: tuple[str, ...] = (
    "IDEmisorFactura",
    "NumSerieFactura",
    "FechaExpedicionFactura",
    "TipoFactura",
    "CuotaTotal",
    "ImporteTotal",
    "Huella",
    "FechaHoraHusoGenRegistro",
)

CAMPOS_ANULACION: tuple[str, ...] = (
    "IDEmisorFacturaAnulada",
    "NumSerieFacturaAnulada",
    "FechaExpedicionFacturaAnulada",
    "Huella",
    "FechaHoraHusoGenRegistro",
)

# **`NIF` aparece dos veces, y es correcto.** El primero es
# `Evento/SistemaInformatico/NIF` y el sexto es `Evento/ObligadoEmision/NIF`: son dos
# campos distintos del XML que comparten nombre. Por eso este módulo trabaja con
# pares ordenados y no con un diccionario — un dict perdería silenciosamente uno de
# los dos y produciría una huella incorrecta que nadie sabría explicar.
CAMPOS_EVENTO: tuple[str, ...] = (
    "NIF",
    "ID",
    "IdSistemaInformatico",
    "Version",
    "NumeroInstalacion",
    "NIF",
    "TipoEvento",
    "HuellaEvento",
    "FechaHoraHusoGenEvento",
)

# Campos cuyo valor la orden trata como numérico. Importa sólo para la equivalencia
# de decimales descrita en `variantes_numericas`.
CAMPOS_NUMERICOS: frozenset[str] = frozenset({"CuotaTotal", "ImporteTotal"})


def normaliza(valor: str | None) -> str:
    """Devuelve el valor tal y como debe entrar en la cadena canónica.

    La orden pide «eliminando los espacios al inicio y al final de cada valor». Nada
    más: los espacios interiores se conservan, y el propio ejemplo oficial lo enseña
    — `<NumSerieFactura>  12345678 / G33  </NumSerieFactura>` produce el valor
    `12345678 / G33`, con sus espacios de en medio intactos.

    Un campo ausente y un campo presente pero vacío son el mismo caso: la cadena
    lleva el nombre y el `=`, sin valor.
    """
    if valor is None:
        return ""
    return valor.strip()


def cadena_canonica(campos: tuple[str, ...], valores: list[str | None]) -> str:
    """Concatena `nombre=valor` con `&`, en el orden dado y sin separador final.

    El separador final es un error clásico y silencioso: produce una huella
    perfectamente formada, de 64 caracteres, que no coincide con la de la AEAT. El
    ejemplo en Java del documento oficial lo marca pasando `false` al último campo.
    """
    if len(campos) != len(valores):
        raise ValueError(
            f"se esperaban {len(campos)} valores para {len(campos)} campos, "
            f"y llegaron {len(valores)}"
        )
    return "&".join(
        f"{n}={normaliza(v)}" for n, v in zip(campos, valores, strict=True)
    )


def huella(cadena: str) -> str:
    """SHA-256 de la cadena canónica, en hexadecimal y mayúsculas.

    SHA-256 es, a fecha del documento, el único algoritmo permitido por la lista L12
    del apartado 6 del anexo de la orden.
    """
    return hashlib.sha256(cadena.encode("utf-8")).hexdigest().upper()


def variantes_numericas(valor: str) -> list[str]:
    """Formas de un importe que la orden considera equivalentes entre sí.

    **Este es el motivo por el que verificar no es simplemente generar y comparar.**
    La orden dice que en los campos numéricos «se tratarán indistintamente los
    valores con una o dos posiciones en los decimales, sin tener relevancia los ceros
    a la derecha, considerándose todos igualmente válidos»: `123.1` y `123.10` son
    ambos correctos y producen huellas *distintas*.

    Un generador elige una forma y se acabó. Un verificador que elija la otra declara
    incorrecta una huella que la AEAT acepta — un falso positivo en una herramienta
    de cumplimiento, que es la peor clase de defecto que puede tener. Así que aquí se
    enumeran las formas admisibles y quien verifica las prueba todas.

    Un valor no numérico se devuelve tal cual: no es trabajo de esta función decidir
    que un campo está mal formado, sólo enumerar equivalencias cuando las hay.
    """
    v = valor.strip()
    if not v:
        return [""]
    try:
        d = Decimal(v)
    except (InvalidOperation, ValueError):
        return [v]

    formas: list[str] = []
    for decimales in (1, 2):
        candidato = f"{d:.{decimales}f}"
        # Sólo es una variante legítima si representa exactamente el mismo número.
        # `123.456` con un decimal sería `123.5`, que no es el mismo importe.
        if Decimal(candidato) == d and candidato not in formas:
            formas.append(candidato)
    if v not in formas:
        formas.insert(0, v)
    return formas


def huella_alta(
    id_emisor: str | None,
    num_serie: str | None,
    fecha_expedicion: str | None,
    tipo_factura: str | None,
    cuota_total: str | None,
    importe_total: str | None,
    huella_anterior: str | None,
    fecha_hora_huso: str | None,
) -> str:
    """Huella de un registro de facturación de alta.

    `huella_anterior` va vacía en el primer registro del SIF. Que sea el primero no
    exime de calcular su huella: la orden es explícita en que el campo `Huella`
    siempre se informa, incluso cuando `PrimerRegistro` vale `S`.
    """
    return huella(
        cadena_canonica(
            CAMPOS_ALTA,
            [
                id_emisor,
                num_serie,
                fecha_expedicion,
                tipo_factura,
                cuota_total,
                importe_total,
                huella_anterior,
                fecha_hora_huso,
            ],
        )
    )


def huella_anulacion(
    id_emisor_anulada: str | None,
    num_serie_anulada: str | None,
    fecha_expedicion_anulada: str | None,
    huella_anterior: str | None,
    fecha_hora_huso: str | None,
) -> str:
    """Huella de un registro de facturación de anulación."""
    return huella(
        cadena_canonica(
            CAMPOS_ANULACION,
            [
                id_emisor_anulada,
                num_serie_anulada,
                fecha_expedicion_anulada,
                huella_anterior,
                fecha_hora_huso,
            ],
        )
    )


def huella_evento(
    nif_sistema: str | None,
    id_otro: str | None,
    id_sistema_informatico: str | None,
    version: str | None,
    numero_instalacion: str | None,
    nif_obligado: str | None,
    tipo_evento: str | None,
    huella_evento_anterior: str | None,
    fecha_hora_huso: str | None,
) -> str:
    """Huella de un registro de evento.

    `nif_sistema` e `id_otro` son excluyentes: se informa uno de los dos y el otro
    queda vacío, tal y como recoge el ejemplo oficial
    `NIF=89890001K&ID=&IdSistemaInformatico=…`.
    """
    return huella(
        cadena_canonica(
            CAMPOS_EVENTO,
            [
                nif_sistema,
                id_otro,
                id_sistema_informatico,
                version,
                numero_instalacion,
                nif_obligado,
                tipo_evento,
                huella_evento_anterior,
                fecha_hora_huso,
            ],
        )
    )
