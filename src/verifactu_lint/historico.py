"""El histórico de instalaciones, entre ejecuciones.

**Por qué hace falta estado.** La AEAT es tajante con el `NumeroInstalacion`: no puede
repetirse nunca para un mismo obligado, ni siquiera formateando el equipo y
reinstalando el mismo software, en cuyo caso el SIF resultante debe llevar uno
distinto (FAQ de desarrolladores, ap. 4). Pero esa reutilización ocurre **entre**
instalaciones separadas en el tiempo, y una herramienta que sólo mira un fichero no
puede verla: dentro del fichero todo es coherente.

**Lo que NO se puede detectar, y por qué no se intenta.** Que una terna aparezca en
dos ejecuciones no dice nada: auditar el mismo SIF cada día en el CI la repite
legítimamente. Comparar ternas a secas convertiría el uso normal de la herramienta en
un aviso diario, que es la forma más rápida de que alguien apague la comprobación.

**Lo que sí es señal.** Una instalación viva no vuelve a arrancar su cadena: encadena
cada registro con el anterior y `PrimerRegistro = "S"` aparece una sola vez, al
principio de su vida. Si una terna que ya arrancó una cadena arranca **otra distinta**,
lo que hay debajo es un sistema que empezó de cero conservando su número de
instalación — exactamente el caso que la norma prohíbe.

Por eso lo que se guarda no es la terna, sino la terna **con la huella de cada
arranque**. Eso hace la comprobación idempotente: volver a auditar el mismo fichero
reconoce el arranque que ya estaba anotado y no inventa nada.

El fichero es del usuario y sólo se toca cuando lo pide con `--historico`. La
herramienta sigue siendo de sólo lectura sobre los registros.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from verifactu_lint.hallazgos import Hallazgo, Severidad
from verifactu_lint.registros import Registro

FORMATO = 1
NORMA = (
    "FAQ desarrolladores AEAT, ap. 4 — el NumeroInstalacion no puede repetirse "
    "para un mismo obligado, ni tras reinstalar"
)


class ErrorDeHistorico(Exception):
    """El fichero de histórico existe pero no se puede usar."""


def _clave(r: Registro) -> tuple[str, str, str]:
    """La identificación universal del SIF: NIF del obligado + IdSIF + nº de instalación."""
    return (
        (r.sistema.nif or r.sistema.id_otro or "").strip(),
        (r.sistema.id_sistema_informatico or "").strip(),
        (r.sistema.numero_instalacion or "").strip(),
    )


def _texto(clave: tuple[str, str, str]) -> str:
    return "|".join(clave)


def lee(ruta: Path) -> dict[str, Any]:
    """Devuelve el histórico, o uno vacío si el fichero aún no existe.

    Un fichero ilegible **no** se trata como vacío: sobrescribirlo en silencio
    perdería el histórico entero, que es justo lo que da valor a la comprobación.
    """
    if not ruta.exists():
        return {"formato": FORMATO, "instalaciones": {}}
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ErrorDeHistorico(f"{ruta}: no se puede leer el histórico ({exc})") from exc
    if not isinstance(datos, dict) or "instalaciones" not in datos:
        raise ErrorDeHistorico(f"{ruta}: no parece un histórico de verifactu-lint")
    if datos.get("formato") != FORMATO:
        raise ErrorDeHistorico(
            f"{ruta}: histórico en formato {datos.get('formato')!r}, "
            f"esta versión escribe el {FORMATO}"
        )
    return datos


def escribe(ruta: Path, datos: dict[str, Any]) -> None:
    """Guarda el histórico. Escritura atómica: un corte a medias no lo corrompe."""
    tmp = ruta.with_suffix(ruta.suffix + ".tmp")
    try:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(
            json.dumps(datos, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        tmp.replace(ruta)
    except OSError as exc:
        raise ErrorDeHistorico(f"{ruta}: no se puede escribir el histórico ({exc})") from exc


def arranques(registros: list[Registro]) -> dict[tuple[str, str, str], list[str]]:
    """Por instalación, las huellas de los registros que arrancan cadena."""
    vistos: dict[tuple[str, str, str], list[str]] = {}
    for r in registros:
        clave = _clave(r)
        if clave == ("", "", ""):
            continue  # sin SIF identificado no hay instalación que seguir; eso es RRSIF011
        vistos.setdefault(clave, [])
        huella = (r.huella or "").strip().upper()
        if r.es_primer_registro and huella:
            if huella not in vistos[clave]:
                vistos[clave].append(huella)
    return vistos


def comprueba(
    registros: list[Registro], datos: dict[str, Any], fichero: str = ""
) -> tuple[list[Hallazgo], dict[str, Any]]:
    """RRSIF014 — una instalación que vuelve a arrancar su cadena.

    Devuelve los hallazgos y el histórico actualizado. Se anota **siempre**, también
    cuando hay hallazgos: si sólo se anotara en las ejecuciones limpias, la instalación
    que interesa seguir sería justo la que nunca queda registrada.
    """
    hallazgos: list[Hallazgo] = []
    instalaciones: dict[str, Any] = dict(datos.get("instalaciones", {}))
    hoy = date.today().isoformat()

    for clave, nuevos in arranques(registros).items():
        texto = _texto(clave)
        previo = instalaciones.get(texto) or {}
        conocidos: list[str] = list(previo.get("arranques", []))

        ineditos = [h for h in nuevos if h not in conocidos]
        if conocidos and ineditos:
            primero = next(
                r for r in registros if _clave(r) == clave and r.es_primer_registro
            )
            hallazgos.append(
                Hallazgo(
                    regla="RRSIF014",
                    severidad=Severidad.AVISO,
                    titulo="La instalación vuelve a arrancar su cadena de registros",
                    detalle=(
                        f"NumeroInstalacion {clave[2]!r} de {clave[0]} "
                        f"({clave[1]}) ya tenía {len(conocidos)} arranque(s) anotado(s) "
                        f"en el histórico, visto por última vez el "
                        f"{previo.get('visto', '?')}. Una instalación en marcha no "
                        "vuelve a emitir PrimerRegistro: si el sistema se reinstaló, "
                        "el SIF resultante debe llevar un NumeroInstalacion distinto.\n"
                        "Si en realidad son dos instalaciones que comparten número, es "
                        "el incumplimiento que esta comprobación busca."
                    ),
                    norma=NORMA,
                    referencia=primero.referencia,
                    orden=primero.orden,
                )
            )

        instalaciones[texto] = {
            "arranques": conocidos + ineditos,
            "visto": hoy,
            "ultimo_fichero": fichero or previo.get("ultimo_fichero", ""),
        }

    return hallazgos, {"formato": FORMATO, "instalaciones": instalaciones}
