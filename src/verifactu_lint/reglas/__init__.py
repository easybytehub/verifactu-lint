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

from verifactu_lint.hallazgos import Hallazgo, Informe
from verifactu_lint.registros import Evento, Registro
from verifactu_lint.reglas import encadenamiento, eventos, identificacion

Regla = Callable[[list[Registro]], list[Hallazgo]]
ReglaEvento = Callable[[list[Evento]], list[Hallazgo]]

TODAS: tuple[Regla, ...] = (*encadenamiento.REGLAS, *identificacion.REGLAS)
TODAS_EVENTOS: tuple[ReglaEvento, ...] = eventos.REGLAS


def _informe(hallazgos: list[Hallazgo], analizados: int, fichero: str) -> Informe:
    # El orden de los hallazgos es el de los registros, no el de las reglas: quien lee
    # el informe recorre su fichero de arriba abajo, no el catálogo de reglas.
    hallazgos.sort(key=lambda h: (h.orden if h.orden is not None else -1, h.regla))
    return Informe(hallazgos=hallazgos, registros_analizados=analizados, fichero=fichero)


def audita(
    registros: list[Registro],
    fichero: str = "",
    reglas: tuple[Regla, ...] = TODAS,
) -> Informe:
    """Aplica las reglas de facturación y devuelve el informe."""
    hallazgos: list[Hallazgo] = []
    for regla in reglas:
        hallazgos.extend(regla(registros))
    return _informe(hallazgos, len(registros), fichero)


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
    return _informe(hallazgos, len(eventos_), fichero)
