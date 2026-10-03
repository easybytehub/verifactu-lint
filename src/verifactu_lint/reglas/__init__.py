"""El catálogo de reglas y el motor que las aplica.

Una regla es una función `list[Registro] -> list[Hallazgo]`. Nada más: sin clase
base, sin registro por decorador, sin plugins. Añadir una comprobación es escribir
una función y ponerla en la tupla `REGLAS` de su familia, que es la barrera de
entrada más baja posible para quien quiera contribuir una.

**Las reglas reciben la lista entera, no un registro.** La mayoría de lo que importa
aquí es relacional —el encadenamiento, la numeración duplicada, cuántas cadenas hay
mezcladas— y una interfaz de un registro cada vez habría obligado a las reglas
interesantes a mantener estado por su cuenta.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

from verifactu_lint.hallazgos import Hallazgo, Informe
from verifactu_lint.registros import Evento, Registro
from verifactu_lint.reglas import (
    desglose,
    encadenamiento,
    estructura,
    eventos,
    identificacion,
    rectificacion,
)

Regla = Callable[[list[Registro]], list[Hallazgo]]
ReglaEvento = Callable[[list[Evento]], list[Hallazgo]]

TODAS: tuple[Regla, ...] = (
    *estructura.REGLAS,
    *encadenamiento.REGLAS,
    *identificacion.REGLAS,
    *rectificacion.REGLAS,
    *desglose.REGLAS,
)
TODAS_EVENTOS: tuple[ReglaEvento, ...] = eventos.REGLAS


def sella(
    hallazgos: list[Hallazgo], fichero: str, lineas: dict[int, int | None]
) -> list[Hallazgo]:
    """Cada hallazgo, con su fichero y la línea del XML de su registro.

    Se hace en un solo sitio para que ninguna regla tenga que acordarse; también lo
    usan los hallazgos que no salen de `audita`, como los del histórico.
    """
    return [
        replace(
            h,
            fichero=h.fichero or fichero,
            linea_xml=(
                h.linea_xml if h.linea_xml is not None
                else lineas.get(h.orden) if h.orden is not None
                else None
            ),
        )
        for h in hallazgos
    ]


def _informe(
    hallazgos: list[Hallazgo],
    analizados: int,
    fichero: str,
    lineas: dict[int, int | None],
) -> Informe:
    sellados = sella(hallazgos, fichero, lineas)
    # El orden de los hallazgos es el de los registros, no el de las reglas: quien lee
    # el informe recorre su fichero de arriba abajo, no el catálogo de reglas.
    #
    # **Con una excepción, desde 0.4.1: las causas raíz van primero.** Un registro que no
    # sigue el esquema produce una cascada de hallazgos que sólo se entienden después
    # de leer el de la estructura; ponerlo en su sitio cronológico obligaría a leer las
    # consecuencias antes que la causa.
    sellados.sort(
        key=lambda h: (
            h.regla not in estructura.CAUSAS_RAIZ,
            h.orden if h.orden is not None else -1,
            h.regla,
        )
    )
    return Informe(hallazgos=sellados, registros_analizados=analizados, fichero=fichero)


def audita(
    registros: list[Registro],
    fichero: str = "",
    reglas: tuple[Regla, ...] = TODAS,
) -> Informe:
    """Aplica las reglas de facturación y devuelve el informe."""
    hallazgos: list[Hallazgo] = []
    for regla in reglas:
        hallazgos.extend(regla(registros))
    hallazgos = estructura.anota_cascada(hallazgos, registros)
    lineas = {r.orden: r.linea_xml for r in registros}
    return _informe(hallazgos, len(registros), fichero, lineas)


def audita_eventos(
    eventos_: list[Evento],
    fichero: str = "",
    reglas: tuple[ReglaEvento, ...] = TODAS_EVENTOS,
) -> Informe:
    """Aplica las reglas de eventos y devuelve el informe.

    Función aparte de `audita` porque la cadena de eventos es **independiente** de la
    de facturación: un evento no encadena con una factura ni al revés. Auditarlos
    juntos produciría roturas inventadas en la frontera entre unos y otros.
    """
    hallazgos: list[Hallazgo] = []
    for regla in reglas:
        hallazgos.extend(regla(eventos_))
    lineas = {e.orden: e.linea_xml for e in eventos_}
    return _informe(hallazgos, len(eventos_), fichero, lineas)
