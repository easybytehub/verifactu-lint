"""La composite action se comprueba como código, porque también lo es.

**Lo que estos tests protegen es una clase de fallo muy concreta**: la action sólo se
ejecuta de verdad cuando alguien la usa en su repositorio, y ahí un error es visible
para un extraño antes que para nosotros. Comprobar aquí lo comprobable —que el YAML
es válido, que las acciones anidadas están fijadas por SHA, que la versión que instala
existe— cuesta milisegundos y evita publicar una action rota.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).parent.parent
ACTION = RAIZ / "action.yml"


@pytest.fixture(scope="module")
def action() -> dict[str, object]:
    yaml = pytest.importorskip(
        "yaml", reason="PyYAML no es dependencia del paquete; sólo del entorno de dev"
    )
    return dict(yaml.safe_load(ACTION.read_text(encoding="utf-8")))


def test_existe() -> None:
    assert ACTION.is_file()


def test_es_composite(action: dict[str, object]) -> None:
    runs = action["runs"]
    assert isinstance(runs, dict)
    assert runs["using"] == "composite"


def test_acciones_anidadas_fijadas_a_sha(action: dict[str, object]) -> None:
    """Mismo criterio que en los workflows: una etiqueta la puede mover su autor."""
    runs = action["runs"]
    assert isinstance(runs, dict)
    pasos = runs["steps"]
    assert isinstance(pasos, list)
    for paso in pasos:
        referencia = paso.get("uses")
        if not referencia:
            continue
        _, _, ref = str(referencia).rpartition("@")
        assert re.fullmatch(r"[0-9a-f]{40}", ref), (
            f"{referencia} no está fijada a un SHA completo"
        )


def test_la_version_por_defecto_es_la_del_paquete(action: dict[str, object]) -> None:
    """La action instala una versión fija, y tiene que ser una que exista.

    Fijarla —en vez de instalar «lo último»— es lo que evita que la action cambie de
    comportamiento sin que nadie haya tocado nada. El precio es que hay que subirla
    con cada release, y este test es el recordatorio.
    """
    from verifactu_lint import __version__

    entradas = action["inputs"]
    assert isinstance(entradas, dict)
    por_defecto = entradas["version"]["default"]
    assert por_defecto == __version__, (
        f"action.yml instala {por_defecto} y el paquete es {__version__}. "
        "Súbelo al preparar la release."
    )


def test_declara_las_entradas_documentadas(action: dict[str, object]) -> None:
    entradas = action["inputs"]
    assert isinstance(entradas, dict)
    assert {"ficheros", "formato", "estricto", "fallar", "salida", "version"} <= set(
        entradas
    )


def test_ficheros_es_obligatorio(action: dict[str, object]) -> None:
    entradas = action["inputs"]
    assert isinstance(entradas, dict)
    assert entradas["ficheros"]["required"] is True


def test_el_paso_de_auditar_no_usa_el_bash_con_set_e(action: dict[str, object]) -> None:
    """`shell: bash` añade `set -e` y abortaría antes de leer el código de salida.

    Es un fallo silencioso: la action funcionaría en el caso sin hallazgos y se
    comportaría mal justo en el caso para el que existe.
    """
    runs = action["runs"]
    assert isinstance(runs, dict)
    pasos = runs["steps"]
    assert isinstance(pasos, list)
    auditar = next(p for p in pasos if p.get("id") == "auditar")
    assert auditar["shell"] == "bash {0}"
