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

    # Una cuota que se desvía 5 céntimos de base por tipo: la AEAT la admite (±10 €), así
    # que es un aviso y sólo --estricto la convierte en fallo.
    detalle = linea(base="100.00", tipo="21", cuota="21.05")
    ruta = escribe(tmp_path, factura([detalle], cuota_total="21.05", importe_total="121.05"))
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


def _ejecuta(argumentos: list[str], capsys: pytest.CaptureFixture[str]) -> str:
    main(argumentos)
    return capsys.readouterr().out


def test_sarif_con_varios_ficheros_ubica_cada_hallazgo(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Cada resultado apunta a SU fichero y a la línea de SU registro.

    Hasta 0.4.0 la URI era la lista de ficheros unida por comas —que no existe, y las
    anotaciones del CI no aparecían— y la línea era el número de orden del registro.
    """
    import json

    ficheros = [EJEMPLOS / "cadena-rota.xml", EJEMPLOS / "eventos-con-defectos.xml"]
    sarif = json.loads(
        _ejecuta([*map(str, ficheros), "--formato", "sarif", "--sin-color"], capsys)
    )
    resultados = sarif["runs"][0]["results"]
    assert resultados
    por_uri = {f.as_posix(): f for f in ficheros}
    for resultado in resultados:
        ubicacion = resultado["locations"][0]["physicalLocation"]
        fichero = por_uri[ubicacion["artifactLocation"]["uri"]]
        linea = fichero.read_text(encoding="utf-8").split("\n")[
            ubicacion["region"]["startLine"] - 1
        ]
        assert "<" in linea and ("Registro" in linea or "Evento" in linea), linea
    assert {r["locations"][0]["physicalLocation"]["artifactLocation"]["uri"]
            for r in resultados} == set(por_uri)


def test_json_lleva_fichero_y_linea_por_hallazgo(capsys: pytest.CaptureFixture[str]) -> None:
    import json

    datos = json.loads(
        _ejecuta([str(EJEMPLOS / "cadena-rota.xml"), "--formato", "json"], capsys)
    )
    assert datos["hallazgos"]
    for h in datos["hallazgos"]:
        assert h["fichero"].endswith("cadena-rota.xml")
        assert isinstance(h["linea"], int)


def test_texto_con_varios_ficheros_dice_de_cual_es_cada_hallazgo(
    capsys: pytest.CaptureFixture[str],
) -> None:
    salida = _ejecuta(
        [str(EJEMPLOS / "cadena-rota.xml"), str(EJEMPLOS / "eventos-con-defectos.xml"),
         "--sin-color"],
        capsys,
    )
    assert "cadena-rota.xml · #" in salida
    assert "eventos-con-defectos.xml · evento #" in salida
