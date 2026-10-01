"""Cómo se presenta el informe: texto, JSON y SARIF.

**SARIF no está por completismo.** Es el formato que GitHub ingiere en su pestaña
Security, y eso convierte una ejecución en CI en algo que el equipo ve sin haber
abierto un log. Es la diferencia entre una herramienta que hay que acordarse de
correr y una que avisa sola.
"""

from __future__ import annotations

import json
from pathlib import PurePath
from typing import Any

from verifactu_lint.hallazgos import Informe, Severidad

# GitHub sólo entiende error / warning / note.
_NIVEL_SARIF = {
    Severidad.ERROR: "error",
    Severidad.AVISO: "warning",
    Severidad.INCOMPLETO: "note",
}


def texto(informe: Informe, color: bool = True) -> str:
    """Informe legible en terminal."""
    rojo, amarillo, azul, gris, fin = (
        ("\033[31m", "\033[33m", "\033[34m", "\033[90m", "\033[0m")
        if color
        else ("", "", "", "", "")
    )
    tinte = {Severidad.ERROR: rojo, Severidad.AVISO: amarillo, Severidad.INCOMPLETO: azul}

    lineas: list[str] = []
    cabecera = f"verifactu-lint · {informe.registros_analizados} registros"
    if informe.fichero:
        cabecera += f" · {informe.fichero}"
    lineas.append(cabecera)
    lineas.append("")

    # Con varios ficheros, la referencia sola («#3 FA/2024/3») ya no dice de dónde sale.
    varios = len({h.fichero for h in informe.hallazgos if h.fichero}) > 1
    if not informe.hallazgos:
        lineas.append("Sin hallazgos.")
    for h in informe.hallazgos:
        lineas.append(f"{tinte[h.severidad]}{h.linea(con_fichero=varios)}{fin}")
        for detalle in h.detalle.splitlines():
            lineas.append(f"           {detalle}")
        lineas.append(f"{gris}           norma: {h.norma}{fin}")
        lineas.append("")

    def plural(n: int, singular: str, plural_: str) -> str:
        return f"{n} {singular if n == 1 else plural_}"

    lineas.append(
        " · ".join(
            (
                plural(len(informe.errores), "error", "errores"),
                plural(len(informe.avisos), "aviso", "avisos"),
                f"{len(informe.incompletos)} sin determinar",
            )
        )
    )
    # Sin esta línea el informe se lee como un certificado, y no lo es.
    lineas.append(
        f"{gris}Cero errores significa que estas reglas no han encontrado un "
        f"incumplimiento; no es una declaración de conformidad.{fin}"
    )
    return "\n".join(lineas)


def como_json(informe: Informe) -> str:
    datos: dict[str, Any] = {
        "fichero": informe.fichero,
        "registros_analizados": informe.registros_analizados,
        "resumen": {
            "errores": len(informe.errores),
            "avisos": len(informe.avisos),
            "incompletos": len(informe.incompletos),
        },
        "hallazgos": [
            {
                "regla": h.regla,
                "severidad": h.severidad.value,
                "titulo": h.titulo,
                "detalle": h.detalle,
                "norma": h.norma,
                "referencia": h.referencia,
                "orden": h.orden,
                "fichero": h.fichero,
                "linea": h.linea_xml,
            }
            for h in informe.hallazgos
        ],
    }
    return json.dumps(datos, ensure_ascii=False, indent=2)


def _uri(fichero: str) -> str:
    """Ruta en el formato de SARIF: barras normales, como las ve el repositorio."""
    return PurePath(fichero).as_posix()


def como_sarif(informe: Informe, version: str) -> str:
    reglas_vistas: dict[str, dict[str, Any]] = {}
    resultados: list[dict[str, Any]] = []

    for h in informe.hallazgos:
        reglas_vistas.setdefault(
            h.regla,
            {
                "id": h.regla,
                "shortDescription": {"text": h.titulo},
                "fullDescription": {"text": h.norma},
                "defaultConfiguration": {"level": _NIVEL_SARIF[h.severidad]},
            },
        )
        resultados.append(
            {
                "ruleId": h.regla,
                "level": _NIVEL_SARIF[h.severidad],
                "message": {"text": f"{h.titulo}. {h.detalle}"},
                "locations": [
                    {
                        "physicalLocation": {
                            # La ruta es la del fichero del hallazgo. Hasta 0.4.0 era
                            # `informe.fichero`, que con varios ficheros valía
                            # «a.xml, b.xml»: una ruta que no existe, y GitHub no podía
                            # anclar la alerta en ningún sitio.
                            "artifactLocation": {
                                "uri": _uri(h.fichero or informe.fichero or "registros.xml")
                            },
                            # La línea del XML donde abre el registro, si se sabe con
                            # certeza; si no, la posición del registro, que es lo que
                            # se usaba antes y lo que el usuario reconoce.
                            "region": {
                                "startLine": h.linea_xml
                                if h.linea_xml is not None
                                else (h.orden or 0) + 1
                            },
                        }
                    }
                ],
            }
        )

    sarif = {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "verifactu-lint",
                        "version": version,
                        "informationUri": "https://github.com/easybytehub/verifactu-lint",
                        "rules": list(reglas_vistas.values()),
                    }
                },
                "results": resultados,
            }
        ],
    }
    return json.dumps(sarif, ensure_ascii=False, indent=2)
