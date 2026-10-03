"""Estructura del registro y formato de sus fechas (RRSIF050-053), y lo que arrastran.

Los casos reproducen, con registros sintéticos mínimos, la forma de los que encontró
el estudio S1 de EasyxLab (incidencias I-1 a I-4): un generador con su propia
estructura (`<Factura><TipoFactura>`, `<Huella><Hash>`, `<Desglose><DetalleIVA>`,
fechas ISO), una anulación escrita con los nombres del alta y una
`FechaHoraHusoGenRegistro` con microsegundos y sin huso. No se copia ningún fichero
de terceros: sólo la forma del defecto.

Las huellas se calculan con el propio módulo, igual que en `test_reglas.py`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from test_reglas import NIF, SISTEMA, alta_xml, cadena_valida, envuelve, escribe, reglas_de
from verifactu_lint.hallazgos import Hallazgo, Informe, Severidad
from verifactu_lint.huella import huella_alta, huella_anulacion
from verifactu_lint.registros import ID_FACTURA, lee
from verifactu_lint.reglas import audita

HORA = "2024-01-01T19:20:30+01:00"


def de(informe: Informe, regla: str) -> list[Hallazgo]:
    return [h for h in informe.hallazgos if h.regla == regla]


def alta_con_estructura_propia(num_serie: str, fecha: str = "2026-05-01") -> str:
    """La forma del caso S1/I-2: los datos están, pero en rutas inventadas."""
    return f"""
    <RegistroAlta>
      <IDVersion>1.0</IDVersion>
      <IDFactura>
        <IDEmisorFactura>{NIF}</IDEmisorFactura>
        <NumSerieFactura>{num_serie}</NumSerieFactura>
        <FechaExpedicionFactura>{fecha}</FechaExpedicionFactura>
      </IDFactura>
      <Factura>
        <TipoFactura>F1</TipoFactura>
        <Desglose><DetalleIVA><Base>100.00</Base><Cuota>21.00</Cuota></DetalleIVA></Desglose>
        <CuotaTotal>21.00</CuotaTotal>
        <ImporteTotal>121.00</ImporteTotal>
      </Factura>
      <Encadenamiento><PrimerRegistro>S</PrimerRegistro></Encadenamiento>
      {SISTEMA}
      <FechaHoraHusoGenRegistro>{HORA}</FechaHoraHusoGenRegistro>
      <TipoHuella>01</TipoHuella>
      <Huella><Hash>{"A" * 64}</Hash></Huella>
    </RegistroAlta>
"""


def anulacion_xml(
    huella_valor: str,
    *,
    nombres: tuple[str, str, str] = ID_FACTURA["RegistroAnulacion"],
    num_serie: str = "FA/1",
    anterior: str = "B" * 64,
    hora: str = HORA,
) -> str:
    emisor, serie, fecha = nombres
    return f"""
    <RegistroAnulacion>
      <IDVersion>1.0</IDVersion>
      <IDFactura>
        <{emisor}>{NIF}</{emisor}>
        <{serie}>{num_serie}</{serie}>
        <{fecha}>01-01-2024</{fecha}>
      </IDFactura>
      <Encadenamiento>
        <RegistroAnterior>
          <IDEmisorFactura>{NIF}</IDEmisorFactura>
          <NumSerieFactura>FA/1</NumSerieFactura>
          <FechaExpedicionFactura>01-01-2024</FechaExpedicionFactura>
          <Huella>{anterior}</Huella>
        </RegistroAnterior>
      </Encadenamiento>
      {SISTEMA}
      <FechaHoraHusoGenRegistro>{hora}</FechaHoraHusoGenRegistro>
      <TipoHuella>01</TipoHuella>
      <Huella>{huella_valor}</Huella>
    </RegistroAnulacion>
"""


class TestEstructuraDelEsquema:
    """RRSIF050 — incidencia I-2 del estudio S1."""

    def test_nombra_cada_ruta_inesperada_en_un_solo_hallazgo(self, tmp_path: Path) -> None:
        ruta = escribe(tmp_path, envuelve(alta_con_estructura_propia("NOVA-1")))
        informe = audita(lee(ruta))
        estructura = de(informe, "RRSIF050")
        assert len(estructura) == 1
        assert estructura[0].severidad is Severidad.ERROR
        detalle = estructura[0].detalle
        assert "RegistroAlta/Factura" in detalle
        assert "RegistroAlta/Huella/Hash" in detalle
        # El dato no falta: está dentro del elemento inventado, y se dice.
        assert "Lleva dentro TipoFactura, Desglose, CuotaTotal y ImporteTotal" in detalle
        assert "Huella lleva un valor, no elementos" in detalle

    def test_va_primero_y_la_cascada_queda_anotada(self, tmp_path: Path) -> None:
        """Las consecuencias siguen ahí —son ciertas contra el esquema—, pero detrás de
        la causa y diciendo que pueden venir de ella."""
        ruta = escribe(tmp_path, envuelve(alta_con_estructura_propia("NOVA-1")))
        informe = audita(lee(ruta))
        assert informe.hallazgos[0].regla == "RRSIF050"
        cascada = [h for h in informe.hallazgos if h.regla in {"RRSIF001", "RRSIF030", "RRSIF040"}]
        assert {h.regla for h in cascada} == {"RRSIF001", "RRSIF030", "RRSIF040"}
        assert all("(RRSIF050)" in h.detalle for h in cascada)

    def test_se_agrega_en_vez_de_repetirse_por_registro(self, tmp_path: Path) -> None:
        registros = [alta_con_estructura_propia(f"NOVA-{i}") for i in range(1, 4)]
        informe = audita(lee(escribe(tmp_path, envuelve(*registros))))
        estructura = de(informe, "RRSIF050")
        assert len(estructura) == 1
        assert estructura[0].titulo == "La estructura de 3 registros no corresponde al esquema"
        assert "RegistroAlta/Factura — en 3 de 3 registros" in estructura[0].detalle

    def test_anotar_no_esconde_una_rotura_real(self, tmp_path: Path) -> None:
        """Por qué se anota y no se suprime: un elemento de más no tapa la cadena rota."""
        registros = cadena_valida(2)
        registros[1] = registros[1].replace(
            "<TipoHuella>", "<ExtensionDelFabricante>x</ExtensionDelFabricante><TipoHuella>"
        )
        previa = huella_alta(
            NIF, "FA/1", "01-01-2024", "F1", "12.35", "123.45", None, "2024-01-01T19:20:30+01:00"
        )
        registros[1] = registros[1].replace(previa, "C" * 64)
        informe = audita(lee(escribe(tmp_path, envuelve(*registros))))
        assert "RegistroAlta/ExtensionDelFabricante" in de(informe, "RRSIF050")[0].detalle
        assert "RRSIF003" in reglas_de(informe)

    def test_una_cadena_conforme_no_lo_dispara(self, tmp_path: Path) -> None:
        informe = audita(lee(escribe(tmp_path, envuelve(*cadena_valida(3)))))
        assert "RRSIF050" not in reglas_de(informe)


class TestIdentificacionDeLaAnulacion:
    """RRSIF051 — incidencia I-3 del estudio S1."""

    def test_nombres_del_alta_en_una_anulacion(self, tmp_path: Path) -> None:
        ruta = escribe(
            tmp_path, envuelve(anulacion_xml("D" * 64, nombres=ID_FACTURA["RegistroAlta"]))
        )
        informe = audita(lee(ruta))
        causa = de(informe, "RRSIF051")
        assert len(causa) == 1
        assert causa[0].severidad is Severidad.ERROR
        assert "nombres del registro de alta" in causa[0].titulo
        assert "IDEmisorFacturaAnulada, NumSerieFacturaAnulada y" in causa[0].detalle
        # Antes sólo se veía esto, sin la causa. Sigue saliendo, pero la nombra.
        huella = de(informe, "RRSIF001")
        assert huella and "(RRSIF051)" in huella[0].detalle
        # Y no se cuenta dos veces como estructura.
        assert "RRSIF050" not in reglas_de(informe)
        assert informe.hallazgos[0].regla == "RRSIF051"

    def test_campo_ausente(self, tmp_path: Path) -> None:
        xml = anulacion_xml("D" * 64).replace(
            "<NumSerieFacturaAnulada>FA/1</NumSerieFacturaAnulada>", ""
        )
        informe = audita(lee(escribe(tmp_path, envuelve(xml))))
        causa = de(informe, "RRSIF051")
        assert [h.titulo for h in causa] == [
            "El registro de anulación no informa NumSerieFacturaAnulada"
        ]

    def test_anulacion_correcta(self, tmp_path: Path) -> None:
        h = huella_anulacion(NIF, "FA/1", "01-01-2024", "B" * 64, HORA)
        informe = audita(lee(escribe(tmp_path, envuelve(anulacion_xml(h)))))
        assert "RRSIF051" not in reglas_de(informe)
        assert "RRSIF001" not in reglas_de(informe)


class TestFormatoDeFecha:
    """RRSIF052 — incidencia I-4 del estudio S1."""

    def test_fecha_iso(self, tmp_path: Path) -> None:
        h = huella_alta(NIF, "FA/1", "2026-05-01", "F1", "12.35", "123.45", None, HORA)
        informe = audita(lee(escribe(tmp_path, envuelve(alta_xml("FA/1", h, fecha="2026-05-01")))))
        fecha = de(informe, "RRSIF052")
        assert len(fecha) == 1
        assert fecha[0].severidad is Severidad.ERROR
        assert fecha[0].titulo == "FechaExpedicionFactura no tiene el formato dd-mm-aaaa"
        assert "«01-05-2026»" in fecha[0].detalle
        # La fecha del registro anterior es otro campo y se nombra aparte.
        assert "RRSIF001" not in reglas_de(informe)

    def test_forma_correcta_pero_no_es_fecha(self, tmp_path: Path) -> None:
        h = huella_alta(NIF, "FA/1", "31-02-2024", "F1", "12.35", "123.45", None, HORA)
        xml = alta_xml("FA/1", h, fecha="31-02-2024")
        fecha = de(audita(lee(escribe(tmp_path, envuelve(xml)))), "RRSIF052")
        assert fecha and "no es una fecha del calendario" in fecha[0].detalle

    def test_dd_mm_aaaa_no_lo_dispara(self, tmp_path: Path) -> None:
        informe = audita(lee(escribe(tmp_path, envuelve(*cadena_valida(2)))))
        assert "RRSIF052" not in reglas_de(informe)


class TestHusoHorario:
    """RRSIF053 — incidencia I-1 del estudio S1."""

    def _informe(self, tmp_path: Path, *horas: str) -> Informe:
        registros = []
        previa: str | None = None
        for i, hora in enumerate(horas):
            num = f"FA/{i + 1}"
            h = huella_alta(NIF, num, "01-01-2024", "F1", "12.35", "123.45", previa, hora)
            registros.append(alta_xml(num, h, anterior=previa, hora=hora))
            previa = h
        return audita(lee(escribe(tmp_path, envuelve(*registros))))

    def test_sin_huso_es_error(self, tmp_path: Path) -> None:
        huso = de(self._informe(tmp_path, "2025-11-29T14:03:11.312331"), "RRSIF053")
        assert len(huso) == 1
        assert huso[0].severidad is Severidad.ERROR
        assert huso[0].titulo == "FechaHoraHusoGenRegistro no incluye el huso horario"
        assert "art. 7.g" in huso[0].detalle
        assert "art. 7.g)" in huso[0].norma

    def test_se_agrega(self, tmp_path: Path) -> None:
        informe = self._informe(
            tmp_path, "2025-11-29T14:03:11", "2025-11-29T14:03:12", "2025-11-29T14:03:13"
        )
        huso = de(informe, "RRSIF053")
        assert len(huso) == 1 and huso[0].detalle.startswith("3 de 3 registros")

    @pytest.mark.parametrize(
        "hora", ["2024-01-01T19:20:30+01:00", "2024-01-01T18:20:30Z", "2024-07-01T19:20:30-04:00"]
    )
    def test_con_huso_no_lo_dispara(self, tmp_path: Path, hora: str) -> None:
        assert "RRSIF053" not in reglas_de(self._informe(tmp_path, hora))

    def test_fracciones_de_segundo_con_huso_es_aviso(self, tmp_path: Path) -> None:
        huso = de(self._informe(tmp_path, "2024-01-01T19:20:30.250+01:00"), "RRSIF053")
        assert [h.severidad for h in huso] == [Severidad.AVISO]

    def test_no_es_una_fecha_y_hora(self, tmp_path: Path) -> None:
        huso = de(self._informe(tmp_path, "29/11/2025 14:03"), "RRSIF053")
        assert [h.severidad for h in huso] == [Severidad.ERROR]
        assert "formato exigido" in huso[0].titulo


class TestCalculadaMuestraLaFormaEscrita:
    """RRSIF001 — incidencia I-6 del estudio S1."""

    def test_calculada_con_los_importes_tal_como_estan_escritos(self, tmp_path: Path) -> None:
        xml = alta_xml("FA/1", "0" * 64, cuota="21.40", importe="121.40", base="100.00",
                       tipo_impositivo="21.40")
        informe = audita(lee(escribe(tmp_path, envuelve(xml))))
        detalle = de(informe, "RRSIF001")[0].detalle
        literal = huella_alta(NIF, "FA/1", "01-01-2024", "F1", "21.40", "121.40", None, HORA)
        variante = huella_alta(NIF, "FA/1", "01-01-2024", "F1", "21.4", "121.4", None, HORA)
        assert f"Calculada: {literal} (importes tal como están escritos: " in detalle
        assert "CuotaTotal=21.40&ImporteTotal=121.40" in detalle
        assert f"CuotaTotal=21.4, ImporteTotal=121.4: {variante}" in detalle


class TestElMapaEsElDelEsquema:
    """Los hijos que conoce el parser son los del XSD oficial, no una copia que derive."""

    XSD = Path(__file__).parent.parent / "esquemas" / "SuministroInformacion.xsd"
    X = "{http://www.w3.org/2001/XMLSchema}"

    def _hijos(self, tipo: str) -> set[str]:
        """Los elementos que declara un tipo, sin bajar a sus tipos anónimos anidados."""
        etree = pytest.importorskip("lxml.etree", reason="lxml sólo es dependencia de desarrollo")
        documento = etree.parse(str(self.XSD))
        nodo = documento.find(f".//{self.X}complexType[@name='{tipo}']")
        assert nodo is not None, tipo
        nombres: set[str] = set()
        for elemento in nodo.iter(f"{self.X}element"):
            propio = next(a for a in elemento.iterancestors() if a.tag == f"{self.X}complexType")
            if propio is nodo:
                nombres.add(elemento.get("name") or elemento.get("ref").rpartition(":")[2])
        return nombres

    def test_registros_y_bloques(self) -> None:
        from verifactu_lint import registros as r

        assert r._HIJOS_DEL_REGISTRO["RegistroAlta"] == self._hijos("RegistroFacturacionAltaType")
        assert r._HIJOS_DEL_REGISTRO["RegistroAnulacion"] == self._hijos(
            "RegistroFacturacionAnulacionType"
        )
        assert set(ID_FACTURA["RegistroAlta"]) == self._hijos("IDFacturaExpedidaType")
        assert set(ID_FACTURA["RegistroAnulacion"]) == self._hijos("IDFacturaExpedidaBajaType")
        assert r._HIJOS_DEL_BLOQUE["RegistroAnterior"] == self._hijos(
            "EncadenamientoFacturaAnteriorType"
        )
        assert r._HIJOS_DEL_BLOQUE["Desglose"] == self._hijos("DesgloseType")
        assert r._HIJOS_DEL_BLOQUE["DetalleDesglose"] == self._hijos("DetalleType")
        assert r._HIJOS_DEL_BLOQUE["SistemaInformatico"] == self._hijos("SistemaInformaticoType")
