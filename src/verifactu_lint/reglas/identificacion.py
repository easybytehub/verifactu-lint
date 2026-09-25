"""Reglas sobre la identificación del SIF y la numeración de las facturas.

Esta familia existe porque son incumplimientos **silenciosos**: no rompen ningún
envío, no fallan contra el XSD, y el sistema funciona con normalidad durante años.
Aparecen en una inspección, mirando hacia atrás, cuando ya no se pueden corregir.
"""

from __future__ import annotations

from collections import defaultdict

from verifactu_lint.hallazgos import Hallazgo, Severidad
from verifactu_lint.registros import Registro

NORMA_ID = "Orden HAC/1177/2024, anexo — bloque SistemaInformatico; FAQ desarrolladores AEAT, ap. 4"


def numeracion_no_duplicada(registros: list[Registro]) -> list[Hallazgo]:
    """RRSIF010 — un mismo número de factura no puede aparecer dos veces.

    La prohibición de numeración duplicada tiene apartado propio en el FAQ de
    desarrolladores de la AEAT. La clave es la terna emisor + serie/número + fecha de
    expedición, que es lo que identifica a la factura.

    Se cuentan altas y anulaciones por separado a propósito: anular una factura
    emitida es exactamente el caso legítimo en que la misma terna aparece dos veces,
    una en cada tipo de registro.

    **Las altas de subsanación quedan fuera del recuento**, por el mismo motivo. El
    apartado 17 del FAQ manda corregir una factura errónea generando un alta con
    `Subsanacion = "S"` sobre la MISMA factura: tanto si el registro original fue
    aceptado por la AEAT como si fue rechazado —y entonces además `RechazoPrevio`—.
    Repetir la terna ahí no es un defecto, es el procedimiento.

    El apartado 6, que es el que sostiene esta regla, prohíbe una cosa distinta:
    reutilizar la numeración de una factura DIFERENTE, como dar el número de una
    factura de prueba borrada a la siguiente. Contar la subsanación como duplicado
    convertía en error el flujo que la norma obliga a seguir, que es lo peor que
    puede hacer una herramienta de cumplimiento: empujar a incumplir para pasar.

    Lo que esto NO comprueba es el caso inverso —una subsanación sin alta previa con
    su misma terna—, que sería un hallazgo legítimo pero exige distinguir si el fichero
    contiene el registro rechazado o no. Queda fuera a propósito.
    """
    hallazgos: list[Hallazgo] = []
    vistos: dict[tuple[str, str, str, str], list[Registro]] = defaultdict(list)

    for r in registros:
        if r.tipo == "alta" and (r.subsanacion or "").strip().upper() == "S":
            continue  # repite la terna a propósito; ver el docstring
        clave = (
            r.tipo,
            (r.id_emisor or "").strip(),
            (r.num_serie or "").strip(),
            (r.fecha_expedicion or "").strip(),
        )
        if not clave[2]:
            continue  # sin número no hay duplicidad que comprobar
        vistos[clave].append(r)

    for (tipo, _emisor, num_serie, _fecha), grupo in vistos.items():
        if len(grupo) < 2:
            continue
        etiqueta = "alta" if tipo == "alta" else "anulación"
        posiciones = ", ".join(r.referencia for r in grupo)
        for r in grupo[1:]:
            hallazgos.append(
                Hallazgo(
                    regla="RRSIF010",
                    severidad=Severidad.ERROR,
                    titulo=f"Número de factura duplicado en registros de {etiqueta}",
                    detalle=(
                        f"{num_serie} aparece {len(grupo)} veces como registro de "
                        f"{etiqueta}: {posiciones}.\n"
                        "La numeración duplicada está expresamente prohibida."
                    ),
                    norma="FAQ desarrolladores AEAT, ap. 6 — prohibición de numeración duplicada",
                    referencia=r.referencia,
                    orden=r.orden,
                )
            )
    return hallazgos


def sif_identificado(registros: list[Registro]) -> list[Hallazgo]:
    """RRSIF011 — el SIF se identifica con NIF + IdSistemaInformatico + NumeroInstalacion.

    Sólo se emite un hallazgo por campo que falte, no uno por registro: un fichero de
    veinte mil facturas del mismo SIF produciría veinte mil líneas idénticas y el
    informe dejaría de leerse.
    """
    hallazgos: list[Hallazgo] = []
    if not registros:
        return hallazgos

    # Nombre en el XML → atributo en `SistemaInformatico`. El nombre del XML es el que
    # ve el usuario en su fichero, así que es el que aparece en el hallazgo.
    obligatorios: dict[str, str] = {
        "IdSistemaInformatico": "id_sistema_informatico",
        "Version": "version",
        "NumeroInstalacion": "numero_instalacion",
    }
    for campo, atributo in obligatorios.items():
        sin_valor = [
            r for r in registros if not (getattr(r.sistema, atributo) or "").strip()
        ]
        if not sin_valor:
            continue
        hallazgos.append(
            Hallazgo(
                regla="RRSIF011",
                severidad=Severidad.ERROR,
                titulo=f"SistemaInformatico/{campo} no se informa",
                detalle=(
                    f"{len(sin_valor)} de {len(registros)} registros no lo informan. "
                    "La identificación universal del SIF es la concatenación de NIF del "
                    "obligado, IdSistemaInformatico y NumeroInstalacion; sin uno de los "
                    "tres el SIF no es identificable de forma unívoca."
                ),
                norma=NORMA_ID,
                referencia=sin_valor[0].referencia,
                orden=sin_valor[0].orden,
            )
        )

    identificadores = {
        (
            (r.sistema.nif or r.sistema.id_otro or "").strip(),
            (r.sistema.id_sistema_informatico or "").strip(),
            (r.sistema.numero_instalacion or "").strip(),
        )
        for r in registros
    }
    identificadores.discard(("", "", ""))
    if len(identificadores) > 1:
        hallazgos.append(
            Hallazgo(
                regla="RRSIF011",
                severidad=Severidad.AVISO,
                titulo="El fichero mezcla registros de más de un SIF",
                detalle=(
                    f"Se han encontrado {len(identificadores)} identificaciones distintas de "
                    "SistemaInformatico. Cada SIF lleva su propia cadena de huellas, así que "
                    "un fichero con varios no se puede auditar como una única cadena: "
                    "sepáralos y audita cada uno por su lado.\n"
                    + "\n".join(
                        f"  NIF={n or '(vacío)'} IdSIF={i or '(vacío)'} "
                        f"NumeroInstalacion={ni or '(vacío)'}"
                        for n, i, ni in sorted(identificadores)
                    )
                ),
                norma=NORMA_ID,
                referencia=registros[0].referencia,
                orden=registros[0].orden,
            )
        )
    return hallazgos


def multiples_ot_coherente(registros: list[Registro]) -> list[Hallazgo]:
    """RRSIF012 — `IndicadorMultiplesOT` sólo cabe si el SIF admite multi-OT.

    El FAQ de desarrolladores aclara que en un SIF SaaS este valor **se calcula por
    cada usuario**, no a nivel global del producto: se informa `S` para aquellos
    usuarios que tengan creada más de una facturación, y `N` para el resto. Un
    fichero donde todos los registros comparten el mismo valor es lo esperable
    cuando corresponde a un solo usuario, y sospechoso cuando el SIF es multi-OT.
    """
    hallazgos: list[Hallazgo] = []
    for r in registros:
        multi_posible = (r.sistema.tipo_uso_multi_ot or "").strip().upper()
        indicador = (r.sistema.indicador_multiples_ot or "").strip().upper()
        if indicador == "S" and multi_posible == "N":
            hallazgos.append(
                Hallazgo(
                    regla="RRSIF012",
                    severidad=Severidad.ERROR,
                    titulo="IndicadorMultiplesOT=S en un SIF declarado como no multi-OT",
                    detalle=(
                        "TipoUsoPosibleMultiOT vale N, luego el sistema declara no poder "
                        "usarse para varios obligados tributarios. Los dos campos se "
                        "contradicen."
                    ),
                    norma=NORMA_ID,
                    referencia=r.referencia,
                    orden=r.orden,
                )
            )
        elif multi_posible == "S" and not indicador:
            hallazgos.append(
                Hallazgo(
                    regla="RRSIF012",
                    severidad=Severidad.AVISO,
                    titulo="SIF multi-OT que no informa IndicadorMultiplesOT",
                    detalle=(
                        "El sistema declara poder gestionar varios obligados tributarios "
                        "pero no indica si este usuario tiene más de una facturación. En un "
                        "SIF SaaS ese valor se calcula por usuario, no a nivel global."
                    ),
                    norma="FAQ desarrolladores AEAT, ap. 4 — IndicadorMultiplesOT en SIF SaaS",
                    referencia=r.referencia,
                    orden=r.orden,
                )
            )
    return hallazgos


def emisor_consistente(registros: list[Registro]) -> list[Hallazgo]:
    """RRSIF013 — todos los registros de una cadena son del mismo obligado."""
    emisores = {(r.id_emisor or "").strip() for r in registros}
    emisores.discard("")
    if len(emisores) <= 1:
        return []
    return [
        Hallazgo(
            regla="RRSIF013",
            severidad=Severidad.AVISO,
            titulo="El fichero contiene facturas de más de un emisor",
            detalle=(
                f"NIF emisores encontrados: {', '.join(sorted(emisores))}.\n"
                "La cadena de huellas de un SIF pertenece a un obligado tributario. Si esto "
                "es una gestoría o un SaaS multi-OT, cada obligado necesita su propia cadena "
                "y su propio número de instalación."
            ),
            norma=NORMA_ID,
            referencia=registros[0].referencia if registros else "",
            orden=registros[0].orden if registros else None,
        )
    ]


REGLAS = (
    numeracion_no_duplicada,
    sif_identificado,
    multiples_ot_coherente,
    emisor_consistente,
)
