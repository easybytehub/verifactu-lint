"""Qué es un hallazgo, y por qué hay tres severidades y no dos.

**`INCOMPLETO` es la severidad que hace honesta a esta herramienta.** Un linter de
cumplimiento tiene dos formas de equivocarse y no cuestan lo mismo: callar un
incumplimiento real es malo, y afirmar uno que no existe es peor, porque quien lo
lee cambia código correcto y deja de creerse el resto del informe.

Así que cuando una regla no puede determinar el resultado con lo que tiene delante
—un campo que falta, un dato que vive fuera del fichero— no adivina: lo dice. Es el
mismo reparto que usan las herramientas serias de accesibilidad, y por el mismo
motivo.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Severidad(StrEnum):
    ERROR = "error"
    """Incumple. Lo que hay en el fichero contradice la norma citada."""

    AVISO = "aviso"
    """Muy probablemente incumple, o incumplirá en cuanto se dé una condición
    previsible. No basta para afirmar `ERROR` sin ver algo más."""

    INCOMPLETO = "incompleto"
    """No se puede determinar con este fichero. Requiere comprobación humana, y el
    hallazgo dice exactamente qué haría falta mirar."""


@dataclass(frozen=True)
class Hallazgo:
    """Un incumplimiento, o la imposibilidad de descartarlo.

    `norma` no es decorado: sin la cita, quien recibe el informe no puede
    contrastarlo, y un informe que hay que creerse a ciegas no sirve para un
    expediente.
    """

    regla: str          # identificador estable, p. ej. "RRSIF001"
    severidad: Severidad
    titulo: str
    detalle: str
    norma: str          # artículo o apartado concreto que se incumple
    referencia: str = ""  # qué registro, en términos localizables por el usuario
    orden: int | None = None  # posición 0-indexada, para herramientas
    # De qué fichero sale y en qué línea del XML abre su registro. Los pone `audita`, no
    # las reglas: una regla razona sobre registros y no tiene por qué saber de ficheros.
    # Sin ellos, auditar `registros/*.xml` daba hallazgos que no decían de qué fichero
    # eran, y un SARIF cuya ruta era «a.xml, b.xml».
    fichero: str = ""
    linea_xml: int | None = None

    def linea(self, con_fichero: bool = False) -> str:
        """Una línea legible en terminal.

        `con_fichero` antepone el fichero a la referencia, para cuando el informe junta
        varios y «#3 FA/2024/3» ya no basta para saber de dónde sale.
        """
        partes = [p for p in ((self.fichero if con_fichero else ""), self.referencia) if p]
        donde = f" [{' · '.join(partes)}]" if partes else ""
        return f"{self.severidad.value.upper():10} {self.regla}{donde}: {self.titulo}"


@dataclass
class Informe:
    """El resultado completo de auditar un conjunto de registros."""

    hallazgos: list[Hallazgo]
    registros_analizados: int
    fichero: str = ""

    @property
    def errores(self) -> list[Hallazgo]:
        return [h for h in self.hallazgos if h.severidad is Severidad.ERROR]

    @property
    def avisos(self) -> list[Hallazgo]:
        return [h for h in self.hallazgos if h.severidad is Severidad.AVISO]

    @property
    def incompletos(self) -> list[Hallazgo]:
        return [h for h in self.hallazgos if h.severidad is Severidad.INCOMPLETO]

    @property
    def conforme(self) -> bool:
        """Sin errores.

        Deliberadamente **no** significa «cumple el RRSIF»: significa que estas
        reglas, sobre estos registros, no han encontrado un incumplimiento. La
        diferencia está escrita en el README y es la razón por la que esta
        herramienta no emite declaraciones responsables de nadie.
        """
        return not self.errores
