"""Los workflows se comprueban como código, porque lo son.

**Una acción fijada a una etiqueta no está fijada.** `uses: alguien/accion@v4` sigue
lo que apunte `v4` en ese momento, y quien controla el repositorio de la acción puede
moverlo. En un workflow de release —que sostiene un token capaz de publicar
paquetes— eso significa que un tercero decide qué código corre con él.

Esto es una regla que se olvida al añadir la siguiente acción, medio año después, con
prisa. Por eso es un test y no una nota en el CONTRIBUTING.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

WORKFLOWS = sorted((Path(__file__).parent.parent / ".github" / "workflows").glob("*.yml"))

# `uses: owner/repo@ref` — también en su forma con subdirectorio (`repo/sub@ref`).
USES = re.compile(r"^\s*-?\s*uses:\s*([^\s#]+)", re.MULTILINE)
SHA_COMPLETO = re.compile(r"^[0-9a-f]{40}$")


def test_hay_workflows() -> None:
    """Si el glob deja de encontrar ficheros, el resto de tests pasaría vacío."""
    assert WORKFLOWS, "no se han encontrado workflows en .github/workflows"


@pytest.mark.parametrize("ruta", WORKFLOWS, ids=lambda p: p.name)
def test_acciones_fijadas_a_sha(ruta: Path) -> None:
    contenido = ruta.read_text(encoding="utf-8")
    sin_fijar: list[str] = []

    for referencia in USES.findall(contenido):
        if "@" not in referencia:
            sin_fijar.append(referencia)
            continue
        _, _, ref = referencia.rpartition("@")
        if not SHA_COMPLETO.match(ref):
            sin_fijar.append(referencia)

    assert not sin_fijar, (
        f"{ruta.name}: acciones sin fijar a un SHA completo: {sin_fijar}. "
        "Una etiqueta la puede mover su autor; un SHA no."
    )


@pytest.mark.parametrize("ruta", WORKFLOWS, ids=lambda p: p.name)
def test_permisos_declarados(ruta: Path) -> None:
    """Sin `permissions`, el workflow hereda los de por defecto del repositorio.

    Declararlos explícitamente es lo que hace que el permiso mínimo sea una decisión
    y no un accidente de configuración.
    """
    contenido = ruta.read_text(encoding="utf-8")
    assert re.search(r"^permissions:", contenido, re.MULTILINE), (
        f"{ruta.name}: no declara `permissions` a nivel de workflow"
    )


@pytest.mark.parametrize("ruta", WORKFLOWS, ids=lambda p: p.name)
def test_sin_escritura_a_nivel_de_workflow(ruta: Path) -> None:
    """La escritura se concede por job, nunca arriba.

    Un `write` en el bloque superior se otorga a *todos* los jobs del fichero,
    incluido el que se añada el año que viene y sólo necesite leer.
    """
    contenido = ruta.read_text(encoding="utf-8")
    bloque = re.search(
        r"^permissions:\n((?:[ \t]+.*\n)+)", contenido, re.MULTILINE
    )
    assert bloque, f"{ruta.name}: no se pudo leer el bloque `permissions`"
    assert "write" not in bloque.group(1), (
        f"{ruta.name}: el bloque `permissions` de nivel superior concede escritura. "
        "Decláralo en el job que la necesite."
    )
