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
from verifactu_lint.registros import Registro
from verifactu_lint.reglas import encadenamiento, identificacion

Regla = Callable[[list[Registro]], list[Hallazgo]]

TODAS: tuple[Regla, ...] = (*encadenamiento.REGLAS, *identificacion.REGLAS)


def audita(
    registros: list[Registro],
    fichero: str = "",
    reglas: tuple[Regla, ...] = TODAS,
) -> Informe:
    """Aplica las reglas y devuelve el informe.

    El orden de los hallazgos es el de los registros, no el de las reglas: quien lee
    el informe recorre su fichero de arriba abajo, no el catálogo de reglas.
    """
    hallazgos: list[Hallazgo] = []
    for regla in reglas:
        hallazgos.extend(regla(registros))

    hallazgos.sort(key=lambda h: (h.orden if h.orden is not None else -1, h.regla))
    return Informe(
        hallazgos=hallazgos,
        registros_analizados=len(registros),
        fichero=fichero,
    )
