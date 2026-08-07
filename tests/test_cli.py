"""La interfaz de línea de comandos, y sobre todo sus códigos de salida.

Quien mete esto en un CI no lee el informe: lee el código de salida. Un código
equivocado es un fallo peor que un hallazgo mal redactado, porque nadie lo ve.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from verifactu_lint.cli import main

RAIZ = Path(__file__).parent.parent
EJEMPLOS = RAIZ / "ejemplos"


def test_fichero_conforme_sale_cero() -> None:
    assert main([str(EJEMPLOS / "cadena-conforme.xml"), "--sin-color"]) == 0


def test_fichero_con_errores_sale_uno() -> None:
    assert main([str(EJEMPLOS / "cadena-rota.xml"), "--sin-color"]) == 1


def test_fichero_inexistente_sale_dos(tmp_path: Path) -> None:
    assert main([str(tmp_path / "no-existe.xml")]) == 2


def test_xml_sin_registros_no_se_confunde_con_conforme(tmp_path: Path) -> None:
    """El defecto que encontró el primer XML ajeno que probamos.

    Un fichero que no contiene registros salía con código **0** y el informe decía
    «sin hallazgos» — indistinguible de un fichero correcto para quien mira el código
    de salida. Y ese caso no es raro: es apuntar al XML equivocado, a una exportación
    con otro envoltorio, o a una ruta mal escrita.
    """
    otro = tmp_path / "otra-cosa.xml"
    otro.write_text('<?xml version="1.0"?><SistemaInformatico/>', encoding="utf-8")
    assert main([str(otro), "--sin-color"]) == 2


def test_un_fichero_util_entre_varios_sigue_auditando(tmp_path: Path) -> None:
    """Si algo se pudo auditar, el resultado es el de esa auditoría.

    Se avisa por stderr del fichero que no aportó registros, pero no se convierte en
    error de uso: el usuario sí obtuvo un informe.
    """
    vacio = tmp_path / "vacio.xml"
    vacio.write_text('<?xml version="1.0"?><nada/>', encoding="utf-8")
    codigo = main([str(vacio), str(EJEMPLOS / "cadena-conforme.xml"), "--sin-color"])
    assert codigo == 0


def test_estricto_convierte_avisos_en_fallo(tmp_path: Path) -> None:
    from test_desglose import escribe, factura, linea

    ruta = escribe(tmp_path, factura([linea(calificacion="S2")]))
    assert main([str(ruta), "--sin-color"]) == 0
    assert main([str(ruta), "--sin-color", "--estricto"]) == 1


@pytest.mark.parametrize("formato", ["texto", "json", "sarif"])
def test_todos_los_formatos_producen_salida(
    formato: str, capsys: pytest.CaptureFixture[str]
) -> None:
    main([str(EJEMPLOS / "cadena-rota.xml"), "--formato", formato, "--sin-color"])
    salida = capsys.readouterr().out
    assert salida.strip(), f"el formato {formato} no imprimió nada"
    if formato in {"json", "sarif"}:
        import json

        json.loads(salida)  # debe ser JSON válido
