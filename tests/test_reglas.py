"""Las reglas, sobre cadenas construidas a mano.

**Las cadenas de prueba se construyen con huellas reales**, calculadas por el propio
módulo, en vez de con constantes inventadas. Si se escribieran a mano, cada test
tendría que actualizarse al tocar el cálculo y la tentación sería copiar la salida
nueva — que es exactamente el bucle en el que un test deja de comprobar nada.

Los vectores oficiales de `test_huella.py` son el ancla que impide que ese cálculo
derive.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from verifactu_lint.hallazgos import Severidad
from verifactu_lint.huella import huella_alta
from verifactu_lint.registros import ErrorDeLectura, lee
from verifactu_lint.reglas import audita

NIF = "89890001K"
SISTEMA = """
      <SistemaInformatico>
        <NombreRazon>Ejemplo SL</NombreRazon>
        <NIF>89890001K</NIF>
        <IdSistemaInformatico>A1</IdSistemaInformatico>
        <Version>1.0</Version>
        <NumeroInstalacion>0001</NumeroInstalacion>
        <TipoUsoPosibleSoloVerifactu>S</TipoUsoPosibleSoloVerifactu>
        <TipoUsoPosibleMultiOT>N</TipoUsoPosibleMultiOT>
        <IndicadorMultiplesOT>N</IndicadorMultiplesOT>
      </SistemaInformatico>
"""


def alta_xml(
    num_serie: str,
    huella_valor: str,
    *,
    anterior: str | None = None,
    fecha: str = "01-01-2024",
    hora: str = "2024-01-01T19:20:30+01:00",
    cuota: str = "12.35",
    importe: str = "123.45",
    base: str = "111.10",
    tipo_impositivo: str = "11.116",
    tipo_huella: str = "01",
    sistema: str = SISTEMA,
) -> str:
    if anterior is None:
        encadenamiento = "<Encadenamiento><PrimerRegistro>S</PrimerRegistro></Encadenamiento>"
    else:
        encadenamiento = f"""<Encadenamiento>
        <RegistroAnterior>
          <IDEmisorFactura>{NIF}</IDEmisorFactura>
          <NumSerieFactura>previa</NumSerieFactura>
          <FechaExpedicionFactura>{fecha}</FechaExpedicionFactura>
          <Huella>{anterior}</Huella>
        </RegistroAnterior>
      </Encadenamiento>"""
    return f"""
    <RegistroAlta>
      <IDVersion>1.0</IDVersion>
      <IDFactura>
        <IDEmisorFactura>{NIF}</IDEmisorFactura>
        <NumSerieFactura>{num_serie}</NumSerieFactura>
        <FechaExpedicionFactura>{fecha}</FechaExpedicionFactura>
      </IDFactura>
      <TipoFactura>F1</TipoFactura>
      <Destinatarios>
        <IDDestinatario><NombreRazon>Cliente SL</NombreRazon><NIF>12345678Z</NIF></IDDestinatario>
      </Destinatarios>
      <Desglose>
        <DetalleDesglose>
          <ClaveRegimen>01</ClaveRegimen>
          <CalificacionOperacion>S1</CalificacionOperacion>
          <TipoImpositivo>{tipo_impositivo}</TipoImpositivo>
          <BaseImponibleOimporteNoSujeto>{base}</BaseImponibleOimporteNoSujeto>
          <CuotaRepercutida>{cuota}</CuotaRepercutida>
        </DetalleDesglose>
      </Desglose>
      <CuotaTotal>{cuota}</CuotaTotal>
      <ImporteTotal>{importe}</ImporteTotal>
      {encadenamiento}
      {sistema}
      <FechaHoraHusoGenRegistro>{hora}</FechaHoraHusoGenRegistro>
      <TipoHuella>{tipo_huella}</TipoHuella>
      <Huella>{huella_valor}</Huella>
    </RegistroAlta>
"""


def envuelve(*registros: str) -> str:
    cuerpo = "".join(registros)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<sf:RegFactuSistemaFacturacion xmlns:sf="https://www2.agenciatributaria.gob.es/'
        'static_files/common/internet/dep/aplicaciones/es/aeat/tike/cont/ws/SuministroLR.xsd">'
        f"{cuerpo}"
        "</sf:RegFactuSistemaFacturacion>"
    )


def escribe(tmp_path: Path, contenido: str) -> Path:
    ruta = tmp_path / "registros.xml"
    ruta.write_text(contenido, encoding="utf-8")
    return ruta


def cadena_valida(n: int = 3) -> list[str]:
    """`n` altas correctamente encadenadas."""
    registros: list[str] = []
    previa: str | None = None
    for i in range(n):
        num = f"FA/{i + 1}"
        hora = f"2024-01-01T19:20:{30 + i:02d}+01:00"
        h = huella_alta(NIF, num, "01-01-2024", "F1", "12.35", "123.45", previa, hora)
        registros.append(alta_xml(num, h, anterior=previa, hora=hora))
        previa = h
    return registros


def reglas_de(informe: object) -> set[str]:
    return {h.regla for h in informe.hallazgos}  # type: ignore[attr-defined]


class TestCadenaCorrecta:
    def test_no_produce_hallazgos(self, tmp_path: Path) -> None:
        ruta = escribe(tmp_path, envuelve(*cadena_valida(4)))
        informe = audita(lee(ruta))
        assert informe.hallazgos == []
        assert informe.conforme
        assert informe.registros_analizados == 4

    @pytest.mark.parametrize("prefijo", ["sf", "sfLR", "ns0", "cualquiera"])
    def test_el_prefijo_de_namespace_no_afecta(self, tmp_path: Path, prefijo: str) -> None:
        """El prefijo varía entre emisores y versiones del esquema.

        Comparar por nombre local es lo que evita que un fichero perfectamente
        válido se lea como vacío sólo porque su emisor eligió otra letra.
        """
        contenido = envuelve(*cadena_valida(2)).replace("sf:", f"{prefijo}:").replace(
            "xmlns:sf=", f"xmlns:{prefijo}="
        )
        ruta = escribe(tmp_path, contenido)
        assert len(lee(ruta)) == 2

    def test_sin_namespace_tambien_se_lee(self, tmp_path: Path) -> None:
        contenido = (
            '<?xml version="1.0" encoding="UTF-8"?><RegFactuSistemaFacturacion>'
            + "".join(cadena_valida(2))
            + "</RegFactuSistemaFacturacion>"
        )
        ruta = escribe(tmp_path, contenido)
        assert len(lee(ruta)) == 2


class TestHuella:
    def test_huella_manipulada(self, tmp_path: Path) -> None:
        registros = cadena_valida(1)
        roto = registros[0].replace("<Huella>", "<Huella>", 1)
        falsa = "0" * 64
        roto = roto[: roto.rfind("<Huella>")] + f"<Huella>{falsa}</Huella></RegistroAlta>\n"
        ruta = escribe(tmp_path, envuelve(roto))
        informe = audita(lee(ruta))
        assert "RRSIF001" in reglas_de(informe)
        assert informe.errores

    def test_huella_en_minusculas_se_distingue_de_incorrecta(self, tmp_path: Path) -> None:
        h = huella_alta(
            NIF, "FA/1", "01-01-2024", "F1", "12.35", "123.45", None,
            "2024-01-01T19:20:30+01:00",
        )
        ruta = escribe(tmp_path, envuelve(alta_xml("FA/1", h.lower())))
        informe = audita(lee(ruta))
        titulos = [x.titulo for x in informe.hallazgos if x.regla == "RRSIF002"]
        assert titulos == ["La huella está en minúsculas"]

    def test_decimales_equivalentes_no_son_un_fallo(self, tmp_path: Path) -> None:
        """`123.45` y `123.450` son el mismo importe para la orden.

        Éste es el falso positivo que la herramienta existe para no cometer.
        """
        h = huella_alta(
            NIF, "FA/1", "01-01-2024", "F1", "12.35", "123.45", None,
            "2024-01-01T19:20:30+01:00",
        )
        ruta = escribe(tmp_path, envuelve(alta_xml("FA/1", h, importe="123.450")))
        informe = audita(lee(ruta))
        assert "RRSIF001" not in reglas_de(informe)

    def test_falta_la_huella(self, tmp_path: Path) -> None:
        ruta = escribe(tmp_path, envuelve(alta_xml("FA/1", "")))
        informe = audita(lee(ruta))
        assert "RRSIF001" in reglas_de(informe)

    def test_tipo_huella_no_admitido(self, tmp_path: Path) -> None:
        h = huella_alta(
            NIF, "FA/1", "01-01-2024", "F1", "12.35", "123.45", None,
            "2024-01-01T19:20:30+01:00",
        )
        ruta = escribe(tmp_path, envuelve(alta_xml("FA/1", h, tipo_huella="02")))
        informe = audita(lee(ruta))
        assert any(x.regla == "RRSIF005" and x.severidad is Severidad.ERROR
                   for x in informe.hallazgos)


class TestEncadenamiento:
    def test_cadena_rota(self, tmp_path: Path) -> None:
        registros = cadena_valida(3)
        # El tercero apunta a una huella que no es la del segundo.
        registros[2] = registros[2].replace(
            registros[2].split("<Huella>")[1].split("</Huella>")[0], "F" * 64, 1
        )
        ruta = escribe(tmp_path, envuelve(*registros))
        informe = audita(lee(ruta))
        assert "RRSIF003" in reglas_de(informe)

    def test_dos_primeros_registros(self, tmp_path: Path) -> None:
        uno = cadena_valida(1)[0]
        ruta = escribe(tmp_path, envuelve(uno, uno.replace("FA/1", "FA/2")))
        informe = audita(lee(ruta))
        assert "RRSIF004" in reglas_de(informe)

    def test_tramo_sin_inicio_declarado_es_incompleto_no_error(self, tmp_path: Path) -> None:
        """Un fichero puede ser un tramo legítimo de una cadena más larga."""
        h1 = huella_alta(NIF, "FA/1", "01-01-2024", "F1", "12.35", "123.45",
                         "A" * 64, "2024-01-01T19:20:30+01:00")
        ruta = escribe(tmp_path, envuelve(alta_xml("FA/1", h1, anterior="A" * 64)))
        informe = audita(lee(ruta))
        sin_inicio = [x for x in informe.hallazgos if x.regla == "RRSIF004"]
        assert sin_inicio == [] or all(
            x.severidad is Severidad.INCOMPLETO for x in sin_inicio
        )


class TestIdentificacion:
    def test_numeracion_duplicada(self, tmp_path: Path) -> None:
        h = huella_alta(NIF, "FA/1", "01-01-2024", "F1", "12.35", "123.45", None,
                        "2024-01-01T19:20:30+01:00")
        uno = alta_xml("FA/1", h)
        h2 = huella_alta(NIF, "FA/1", "01-01-2024", "F1", "12.35", "123.45", h,
                         "2024-01-01T19:20:31+01:00")
        dos = alta_xml("FA/1", h2, anterior=h, hora="2024-01-01T19:20:31+01:00")
        ruta = escribe(tmp_path, envuelve(uno, dos))
        informe = audita(lee(ruta))
        assert "RRSIF010" in reglas_de(informe)

    def test_falta_numero_de_instalacion(self, tmp_path: Path) -> None:
        sistema = SISTEMA.replace("<NumeroInstalacion>0001</NumeroInstalacion>", "")
        h = huella_alta(NIF, "FA/1", "01-01-2024", "F1", "12.35", "123.45", None,
                        "2024-01-01T19:20:30+01:00")
        ruta = escribe(tmp_path, envuelve(alta_xml("FA/1", h, sistema=sistema)))
        informe = audita(lee(ruta))
        assert "RRSIF011" in reglas_de(informe)

    def test_un_hallazgo_por_campo_no_por_registro(self, tmp_path: Path) -> None:
        """Un fichero grande no debe producir miles de líneas idénticas."""
        sistema = SISTEMA.replace("<NumeroInstalacion>0001</NumeroInstalacion>", "")
        registros: list[str] = []
        previa: str | None = None
        for i in range(20):
            num = f"FA/{i + 1}"
            hora = f"2024-01-01T19:{20 + i:02d}:30+01:00"
            h = huella_alta(NIF, num, "01-01-2024", "F1", "12.35", "123.45", previa, hora)
            registros.append(alta_xml(num, h, anterior=previa, hora=hora, sistema=sistema))
            previa = h
        ruta = escribe(tmp_path, envuelve(*registros))
        informe = audita(lee(ruta))
        assert len([x for x in informe.hallazgos if x.regla == "RRSIF011"]) == 1

    def test_indicador_multiples_ot_contradictorio(self, tmp_path: Path) -> None:
        sistema = SISTEMA.replace(
            "<IndicadorMultiplesOT>N</IndicadorMultiplesOT>",
            "<IndicadorMultiplesOT>S</IndicadorMultiplesOT>",
        )
        h = huella_alta(NIF, "FA/1", "01-01-2024", "F1", "12.35", "123.45", None,
                        "2024-01-01T19:20:30+01:00")
        ruta = escribe(tmp_path, envuelve(alta_xml("FA/1", h, sistema=sistema)))
        informe = audita(lee(ruta))
        assert "RRSIF012" in reglas_de(informe)


class TestLectura:
    def test_xml_mal_formado(self, tmp_path: Path) -> None:
        ruta = escribe(tmp_path, "<RegistroAlta><sin cerrar>")
        with pytest.raises(ErrorDeLectura, match="mal formado"):
            lee(ruta)

    def test_fichero_inexistente(self, tmp_path: Path) -> None:
        with pytest.raises(ErrorDeLectura, match="no se pudo abrir"):
            lee(tmp_path / "no-existe.xml")

    def test_billion_laughs_no_cuelga_el_proceso(self, tmp_path: Path) -> None:
        """Diez líneas de XML que agotarían la memoria de un parser ingenuo."""
        bomba = """<?xml version="1.0"?>
<!DOCTYPE lolz [
  <!ENTITY lol "lol">
  <!ENTITY lol1 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
  <!ENTITY lol2 "&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;">
  <!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;">
]>
<RegistroAlta>&lol3;</RegistroAlta>"""
        ruta = escribe(tmp_path, bomba)
        with pytest.raises(ErrorDeLectura):
            lee(ruta)

    def test_sin_registros(self, tmp_path: Path) -> None:
        ruta = escribe(tmp_path, "<vacio/>")
        assert lee(ruta) == []
