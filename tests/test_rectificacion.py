"""Reglas de rectificativas, sustitutivas y subsanaciones.

Los códigos de `TipoFactura` y `TipoRectificativa` salen del esquema oficial
`SuministroInformacion.xsd` de la AEAT.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from verifactu_lint.hallazgos import Severidad
from verifactu_lint.huella import huella_alta
from verifactu_lint.registros import lee
from verifactu_lint.reglas import audita
from verifactu_lint.reglas.rectificacion import TIPOS_FACTURA, TIPOS_RECTIFICATIVA

NIF = "89890001K"
HORA = "2024-01-01T19:20:30+01:00"
SISTEMA = """
      <SistemaInformatico>
        <NombreRazon>Ejemplo SL</NombreRazon><NIF>89890001K</NIF>
        <IdSistemaInformatico>A1</IdSistemaInformatico><Version>1.0</Version>
        <NumeroInstalacion>0001</NumeroInstalacion>
      </SistemaInformatico>"""


def factura(
    tipo: str,
    *,
    num: str = "FA/1",
    rectificativa: str | None = None,
    rectificadas: int = 0,
    sustituidas: int = 0,
    importe_rect: bool = False,
    subsanacion: str | None = None,
    rechazo: str | None = None,
) -> str:
    h = huella_alta(NIF, num, "01-01-2024", tipo, "12.35", "123.45", None, HORA)
    bloques = ""
    if subsanacion:
        bloques += f"<Subsanacion>{subsanacion}</Subsanacion>"
    if rechazo:
        bloques += f"<RechazoPrevio>{rechazo}</RechazoPrevio>"
    if rectificativa:
        bloques += f"<TipoRectificativa>{rectificativa}</TipoRectificativa>"
    if rectificadas:
        items = "".join(
            f"<IDFacturaRectificada><IDEmisorFactura>{NIF}</IDEmisorFactura>"
            f"<NumSerieFactura>OLD/{i}</NumSerieFactura>"
            f"<FechaExpedicionFactura>01-01-2024</FechaExpedicionFactura>"
            "</IDFacturaRectificada>"
            for i in range(rectificadas)
        )
        bloques += f"<FacturasRectificadas>{items}</FacturasRectificadas>"
    if sustituidas:
        items = "".join(
            f"<IDFacturaSustituida><IDEmisorFactura>{NIF}</IDEmisorFactura>"
            f"<NumSerieFactura>SIM/{i}</NumSerieFactura>"
            f"<FechaExpedicionFactura>01-01-2024</FechaExpedicionFactura>"
            "</IDFacturaSustituida>"
            for i in range(sustituidas)
        )
        bloques += f"<FacturasSustituidas>{items}</FacturasSustituidas>"
    if importe_rect:
        bloques += (
            "<ImporteRectificacion><BaseRectificada>100.00</BaseRectificada>"
            "<CuotaRectificada>21.00</CuotaRectificada></ImporteRectificacion>"
        )

    return f"""
    <RegistroAlta>
      <IDVersion>1.0</IDVersion>
      <IDFactura>
        <IDEmisorFactura>{NIF}</IDEmisorFactura>
        <NumSerieFactura>{num}</NumSerieFactura>
        <FechaExpedicionFactura>01-01-2024</FechaExpedicionFactura>
      </IDFactura>
      <NombreRazonEmisor>Ejemplo SL</NombreRazonEmisor>
      {bloques}
      <TipoFactura>{tipo}</TipoFactura>
      <Destinatarios>
        <IDDestinatario><NombreRazon>Cliente SL</NombreRazon><NIF>12345678Z</NIF></IDDestinatario>
      </Destinatarios>
      <Desglose>
        <DetalleDesglose>
          <ClaveRegimen>01</ClaveRegimen>
          <CalificacionOperacion>S1</CalificacionOperacion>
          <TipoImpositivo>11.116</TipoImpositivo>
          <BaseImponibleOimporteNoSujeto>111.10</BaseImponibleOimporteNoSujeto>
          <CuotaRepercutida>12.35</CuotaRepercutida>
        </DetalleDesglose>
      </Desglose>
      <CuotaTotal>12.35</CuotaTotal>
      <ImporteTotal>123.45</ImporteTotal>
      <Encadenamiento><PrimerRegistro>S</PrimerRegistro></Encadenamiento>
      {SISTEMA}
      <FechaHoraHusoGenRegistro>{HORA}</FechaHoraHusoGenRegistro>
      <TipoHuella>01</TipoHuella>
      <Huella>{h}</Huella>
    </RegistroAlta>"""


def escribe(tmp_path: Path, *registros: str) -> Path:
    ruta = tmp_path / "f.xml"
    ruta.write_text(
        '<?xml version="1.0" encoding="UTF-8"?><RegFactuSistemaFacturacion>'
        + "".join(registros)
        + "</RegFactuSistemaFacturacion>",
        encoding="utf-8",
    )
    return ruta


def reglas_de(informe: object) -> set[str]:
    return {h.regla for h in informe.hallazgos}  # type: ignore[attr-defined]


class TestCatalogo:
    def test_los_ocho_tipos_de_factura(self) -> None:
        assert set(TIPOS_FACTURA) == {"F1", "F2", "F3", "R1", "R2", "R3", "R4", "R5"}

    def test_las_dos_modalidades(self) -> None:
        assert set(TIPOS_RECTIFICATIVA) == {"S", "I"}


class TestTipoFactura:
    @pytest.mark.parametrize("tipo", ["F1", "F2"])
    def test_factura_normal_sin_hallazgos(self, tmp_path: Path, tipo: str) -> None:
        informe = audita(lee(escribe(tmp_path, factura(tipo))))
        assert informe.hallazgos == []

    def test_tipo_inexistente(self, tmp_path: Path) -> None:
        informe = audita(lee(escribe(tmp_path, factura("X9"))))
        assert "RRSIF030" in reglas_de(informe)


class TestRectificativas:
    def test_rectificativa_correcta(self, tmp_path: Path) -> None:
        informe = audita(
            lee(
                escribe(
                    tmp_path,
                    factura("R1", rectificativa="I", rectificadas=1),
                )
            )
        )
        assert informe.hallazgos == []

    def test_rectificativa_sin_modalidad(self, tmp_path: Path) -> None:
        informe = audita(lee(escribe(tmp_path, factura("R1", rectificadas=1))))
        assert "RRSIF031" in reglas_de(informe)

    def test_modalidad_invalida(self, tmp_path: Path) -> None:
        informe = audita(
            lee(escribe(tmp_path, factura("R1", rectificativa="Z", rectificadas=1)))
        )
        assert "RRSIF031" in reglas_de(informe)

    def test_rectificativa_sin_factura_rectificada(self, tmp_path: Path) -> None:
        informe = audita(lee(escribe(tmp_path, factura("R1", rectificativa="I"))))
        errores = [h for h in informe.hallazgos if h.regla == "RRSIF031"]
        assert any(h.severidad is Severidad.ERROR for h in errores)

    def test_r5_sin_rectificadas_es_incompleto_no_error(self, tmp_path: Path) -> None:
        """R5 rectifica simplificadas, que pueden no ser identificables una a una."""
        informe = audita(lee(escribe(tmp_path, factura("R5", rectificativa="I"))))
        hallazgos = [
            h for h in informe.hallazgos
            if h.regla == "RRSIF031" and "no identifica" in h.titulo
        ]
        assert hallazgos and all(h.severidad is Severidad.INCOMPLETO for h in hallazgos)

    def test_sustitutiva_sin_importes_es_error(self, tmp_path: Path) -> None:
        """Error 1118 de la AEAT: en una sustitutiva el bloque es obligatorio.

        Esta regla empezó siendo un aviso —parecía una conveniencia para cuadrar— y
        el listado oficial de códigos de error demostró que es motivo de rechazo.
        """
        informe = audita(
            lee(escribe(tmp_path, factura("R1", rectificativa="S", rectificadas=1)))
        )
        hallazgos = [h for h in informe.hallazgos if h.regla == "RRSIF033"]
        assert hallazgos and all(h.severidad is Severidad.ERROR for h in hallazgos)

    def test_importe_rectificacion_sin_ser_sustitutiva(self, tmp_path: Path) -> None:
        """Error 1119: fuera de las sustitutivas, el bloque no debe tener valor."""
        informe = audita(
            lee(
                escribe(
                    tmp_path,
                    factura("R1", rectificativa="I", rectificadas=1, importe_rect=True),
                )
            )
        )
        assert "RRSIF033" in reglas_de(informe)

    def test_sustitutiva_con_importes_no_avisa(self, tmp_path: Path) -> None:
        informe = audita(
            lee(
                escribe(
                    tmp_path,
                    factura("R1", rectificativa="S", rectificadas=1, importe_rect=True),
                )
            )
        )
        assert "RRSIF033" not in reglas_de(informe)

    def test_incremental_sin_importes_no_avisa(self, tmp_path: Path) -> None:
        """En la modalidad I el importe ya es la diferencia."""
        informe = audita(
            lee(escribe(tmp_path, factura("R1", rectificativa="I", rectificadas=1)))
        )
        assert "RRSIF033" not in reglas_de(informe)


class TestCamposFueraDeSitio:
    def test_factura_normal_con_campos_de_rectificacion(self, tmp_path: Path) -> None:
        informe = audita(lee(escribe(tmp_path, factura("F1", rectificativa="S"))))
        assert "RRSIF032" in reglas_de(informe)

    def test_factura_normal_con_facturas_rectificadas(self, tmp_path: Path) -> None:
        informe = audita(lee(escribe(tmp_path, factura("F1", rectificadas=2))))
        assert "RRSIF032" in reglas_de(informe)


class TestSustitucionDeSimplificadas:
    def test_f3_sin_sustituidas(self, tmp_path: Path) -> None:
        informe = audita(lee(escribe(tmp_path, factura("F3"))))
        assert "RRSIF034" in reglas_de(informe)

    def test_f3_correcta(self, tmp_path: Path) -> None:
        informe = audita(lee(escribe(tmp_path, factura("F3", sustituidas=3))))
        assert "RRSIF034" not in reglas_de(informe)

    def test_sustituidas_en_factura_que_no_es_f3(self, tmp_path: Path) -> None:
        informe = audita(lee(escribe(tmp_path, factura("F1", sustituidas=1))))
        assert "RRSIF034" in reglas_de(informe)


class TestSubsanacion:
    def test_valor_invalido(self, tmp_path: Path) -> None:
        informe = audita(lee(escribe(tmp_path, factura("F1", subsanacion="X"))))
        assert "RRSIF035" in reglas_de(informe)

    def test_rechazo_previo_valido(self, tmp_path: Path) -> None:
        informe = audita(lee(escribe(tmp_path, factura("F1", rechazo="X"))))
        assert "RRSIF035" not in reglas_de(informe)

    def test_subsanacion_y_rectificativa_a_la_vez_es_aviso(self, tmp_path: Path) -> None:
        informe = audita(
            lee(
                escribe(
                    tmp_path,
                    factura("R1", rectificativa="I", rectificadas=1, subsanacion="S"),
                )
            )
        )
        avisos = [h for h in informe.hallazgos if h.regla == "RRSIF035"]
        assert avisos and all(h.severidad is Severidad.AVISO for h in avisos)

    def test_subsanacion_normal_no_avisa(self, tmp_path: Path) -> None:
        informe = audita(lee(escribe(tmp_path, factura("F1", subsanacion="S"))))
        assert "RRSIF035" not in reglas_de(informe)
