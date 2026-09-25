"""El histórico de instalaciones entre ejecuciones.

Lo que más importa aquí no es que detecte la reinstalación, sino que **no avise cuando
no toca**: auditar el mismo SIF todos los días en el CI es el uso normal, y una
herramienta que avisa a diario se apaga a la semana.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from test_reglas import NIF, SISTEMA, alta_xml, envuelve
from verifactu_lint.cli import main
from verifactu_lint.huella import huella_alta


def cadena(tmp_path: Path, nombre: str, num: str) -> Path:
    """Un fichero con una cadena que arranca: un único registro con PrimerRegistro."""
    h = huella_alta(NIF, num, "01-01-2024", "F1", "12.35", "123.45", None,
                    "2024-01-01T19:20:30+01:00")
    ruta = tmp_path / nombre
    ruta.write_text(envuelve(alta_xml(num, h)), encoding="utf-8")
    return ruta


class TestHistorico:
    def test_sin_el_flag_no_escribe_nada(self, tmp_path: Path) -> None:
        f = cadena(tmp_path, "a.xml", "FA/1")
        main([str(f), "--formato", "json"])
        assert list(tmp_path.glob("*.json")) == []

    def test_primera_ejecucion_anota_y_no_avisa(self, tmp_path: Path) -> None:
        f = cadena(tmp_path, "a.xml", "FA/1")
        estado = tmp_path / "instalaciones.json"
        main([str(f), "--historico", str(estado), "--formato", "json"])
        datos = json.loads(estado.read_text(encoding="utf-8"))
        (clave,) = datos["instalaciones"]
        assert clave.endswith("|0001")
        assert len(datos["instalaciones"][clave]["arranques"]) == 1

    def test_reauditar_el_mismo_fichero_no_avisa(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """El caso del CI: el mismo SIF, todos los días. No puede convertirse en ruido."""
        f = cadena(tmp_path, "a.xml", "FA/1")
        estado = tmp_path / "instalaciones.json"
        main([str(f), "--historico", str(estado), "--formato", "json"])
        capsys.readouterr()
        main([str(f), "--historico", str(estado), "--formato", "json"])
        assert "RRSIF014" not in capsys.readouterr().out

    def test_una_cadena_nueva_de_la_misma_instalacion_avisa(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Arrancar otra cadena con el mismo NumeroInstalacion es lo que la norma prohíbe."""
        estado = tmp_path / "instalaciones.json"
        primera = cadena(tmp_path, "a.xml", "FA/1")
        main([str(primera), "--historico", str(estado), "--formato", "json"])
        capsys.readouterr()

        # Mismo SIF, misma instalación, pero la cadena vuelve a empezar de cero.
        segunda = cadena(tmp_path, "b.xml", "FB/1")
        main([str(segunda), "--historico", str(estado), "--formato", "json"])
        salida = capsys.readouterr().out
        assert "RRSIF014" in salida

        datos = json.loads(estado.read_text(encoding="utf-8"))
        (clave,) = datos["instalaciones"]
        assert len(datos["instalaciones"][clave]["arranques"]) == 2

    def test_otra_instalacion_no_avisa(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Dos números de instalación distintos son dos sistemas: ninguno reutiliza nada."""
        estado = tmp_path / "instalaciones.json"
        primera = cadena(tmp_path, "a.xml", "FA/1")
        main([str(primera), "--historico", str(estado), "--formato", "json"])
        capsys.readouterr()

        otro = alta_xml(
            "FB/1",
            huella_alta(NIF, "FB/1", "01-01-2024", "F1", "12.35", "123.45", None,
                        "2024-01-01T19:20:30+01:00"),
            sistema=SISTEMA.replace(
                "<NumeroInstalacion>0001</NumeroInstalacion>",
                "<NumeroInstalacion>0002</NumeroInstalacion>",
            ),
        )
        ruta = tmp_path / "b.xml"
        ruta.write_text(envuelve(otro), encoding="utf-8")
        main([str(ruta), "--historico", str(estado), "--formato", "json"])
        assert "RRSIF014" not in capsys.readouterr().out

    def test_historico_ilegible_no_se_pisa(self, tmp_path: Path) -> None:
        """Sobrescribir en silencio perdería justo lo que da valor a la comprobación."""
        estado = tmp_path / "instalaciones.json"
        estado.write_text("{ esto no es json", encoding="utf-8")
        f = cadena(tmp_path, "a.xml", "FA/1")
        assert main([str(f), "--historico", str(estado)]) == 2
        assert estado.read_text(encoding="utf-8") == "{ esto no es json"

    def test_formato_desconocido_no_se_pisa(self, tmp_path: Path) -> None:
        estado = tmp_path / "instalaciones.json"
        estado.write_text('{"formato": 99, "instalaciones": {}}', encoding="utf-8")
        f = cadena(tmp_path, "a.xml", "FA/1")
        assert main([str(f), "--historico", str(estado)]) == 2
