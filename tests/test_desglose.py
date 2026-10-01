"""Reglas del desglose y su cuadre con los totales.

Cada regla de este módulo corresponde a un código de error del listado oficial de la
AEAT, así que los tests comprueban justo lo que su validador rechazaría.

**El caso que resume por qué existe la herramienta** está en
`TestCuadreDeTotales::test_un_desglose_descuadrado_con_huella_correcta`: un registro
cuya huella es impecable y cuyos totales no salen de sus propias líneas.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from verifactu_lint.hallazgos import Severidad
from verifactu_lint.huella import huella_alta
from verifactu_lint.registros import lee
from verifactu_lint.reglas import audita

NIF = "89890001K"
HORA = "2024-01-01T19:20:30+01:00"


def linea(
    *,
    base: str = "100.00",
    tipo: str = "21",
    cuota: str = "21.00",
    calificacion: str = "S1",
    exenta: str | None = None,
    impuesto: str | None = None,
    regimen: str = "01",
    tipo_recargo: str | None = None,
    cuota_recargo: str | None = None,
    base_a_coste: str | None = None,
) -> str:
    partes = [f"<ClaveRegimen>{regimen}</ClaveRegimen>"]
    if impuesto:
        partes.insert(0, f"<Impuesto>{impuesto}</Impuesto>")
    partes.append(
        f"<OperacionExenta>{exenta}</OperacionExenta>"
        if exenta
        else f"<CalificacionOperacion>{calificacion}</CalificacionOperacion>"
    )
    if tipo:
        partes.append(f"<TipoImpositivo>{tipo}</TipoImpositivo>")
    partes.append(f"<BaseImponibleOimporteNoSujeto>{base}</BaseImponibleOimporteNoSujeto>")
    if base_a_coste:
        partes.append(f"<BaseImponibleACoste>{base_a_coste}</BaseImponibleACoste>")
    if cuota:
        partes.append(f"<CuotaRepercutida>{cuota}</CuotaRepercutida>")
    if tipo_recargo:
        partes.append(f"<TipoRecargoEquivalencia>{tipo_recargo}</TipoRecargoEquivalencia>")
    if cuota_recargo:
        partes.append(f"<CuotaRecargoEquivalencia>{cuota_recargo}</CuotaRecargoEquivalencia>")
    return "<DetalleDesglose>" + "".join(partes) + "</DetalleDesglose>"


def factura(
    lineas: list[str],
    *,
    cuota_total: str = "21.00",
    importe_total: str = "121.00",
    tipo_factura: str = "F1",
    destinatario: bool = True,
    macrodato: str | None = None,
    num: str = "FA/1",
) -> str:
    h = huella_alta(NIF, num, "01-01-2024", tipo_factura, cuota_total, importe_total, None, HORA)
    dest = (
        "<Destinatarios><IDDestinatario><NombreRazon>Cliente SL</NombreRazon>"
        "<NIF>12345678Z</NIF></IDDestinatario></Destinatarios>"
        if destinatario
        else ""
    )
    macro = f"<Macrodato>{macrodato}</Macrodato>" if macrodato else ""
    return f"""
    <RegistroAlta>
      <IDVersion>1.0</IDVersion>
      <IDFactura>
        <IDEmisorFactura>{NIF}</IDEmisorFactura>
        <NumSerieFactura>{num}</NumSerieFactura>
        <FechaExpedicionFactura>01-01-2024</FechaExpedicionFactura>
      </IDFactura>
      <NombreRazonEmisor>Ejemplo SL</NombreRazonEmisor>
      {macro}
      <TipoFactura>{tipo_factura}</TipoFactura>
      {dest}
      <Desglose>{"".join(lineas)}</Desglose>
      <CuotaTotal>{cuota_total}</CuotaTotal>
      <ImporteTotal>{importe_total}</ImporteTotal>
      <Encadenamiento><PrimerRegistro>S</PrimerRegistro></Encadenamiento>
      <SistemaInformatico>
        <NombreRazon>Ejemplo SL</NombreRazon><NIF>{NIF}</NIF>
        <IdSistemaInformatico>A1</IdSistemaInformatico><Version>1.0</Version>
        <NumeroInstalacion>0001</NumeroInstalacion>
      </SistemaInformatico>
      <FechaHoraHusoGenRegistro>{HORA}</FechaHoraHusoGenRegistro>
      <TipoHuella>01</TipoHuella>
      <Huella>{h}</Huella>
    </RegistroAlta>"""


def escribe(tmp_path: Path, *registros: str) -> Path:
    ruta = tmp_path / "f.xml"
    ruta.write_text(
        '<?xml version="1.0"?><RegFactuSistemaFacturacion>'
        + "".join(registros)
        + "</RegFactuSistemaFacturacion>",
        encoding="utf-8",
    )
    return ruta


def reglas_de(informe: object) -> set[str]:
    return {h.regla for h in informe.hallazgos}  # type: ignore[attr-defined]


class TestFacturaCorrecta:
    def test_sin_hallazgos(self, tmp_path: Path) -> None:
        informe = audita(lee(escribe(tmp_path, factura([linea()]))))
        assert informe.hallazgos == []

    def test_varias_lineas_con_tipos_distintos(self, tmp_path: Path) -> None:
        lineas = [
            linea(base="100.00", tipo="21", cuota="21.00"),
            linea(base="200.00", tipo="10", cuota="20.00"),
        ]
        informe = audita(
            lee(escribe(tmp_path, factura(lineas, cuota_total="41.00", importe_total="341.00")))
        )
        assert informe.hallazgos == []


class TestCuadreDeTotales:
    def test_cuota_total_descuadrada(self, tmp_path: Path) -> None:
        informe = audita(
            lee(escribe(tmp_path, factura([linea()], cuota_total="30.00", importe_total="121.00")))
        )
        assert "RRSIF041" in reglas_de(informe)

    def test_importe_total_descuadrado(self, tmp_path: Path) -> None:
        informe = audita(lee(escribe(tmp_path, factura([linea()], importe_total="200.00"))))
        assert "RRSIF042" in reglas_de(informe)

    def test_un_desglose_descuadrado_con_huella_correcta(self, tmp_path: Path) -> None:
        """El caso que justifica la herramienta entera.

        La huella se calcula sobre `CuotaTotal` e `ImporteTotal`, así que un registro
        con los totales mal produce una huella **correcta** para esos totales. Queda
        encadenado, íntegro y equivocado: ningún XSD lo ve, y la cadena de huellas
        tampoco, porque la cadena no sabe de aritmética.
        """
        ruta = escribe(tmp_path, factura([linea()], importe_total="999.00"))
        informe = audita(lee(ruta))
        assert "RRSIF001" not in reglas_de(informe), "la huella debería ser correcta"
        assert "RRSIF042" in reglas_de(informe), "y el importe no debería cuadrar"

    def test_el_recargo_entra_en_el_cuadre(self, tmp_path: Path) -> None:
        """CuotaTotal = cuotas + recargos, no sólo cuotas (error 2006)."""
        detalle = linea(tipo_recargo="5.2", cuota_recargo="5.20")
        informe = audita(
            lee(escribe(tmp_path, factura([detalle], cuota_total="26.20", importe_total="126.20")))
        )
        assert "RRSIF041" not in reglas_de(informe)
        assert "RRSIF042" not in reglas_de(informe)

    def test_tolera_el_redondeo_por_linea(self, tmp_path: Path) -> None:
        """Un céntimo por línea es redondeo, y de eso no se dice nada."""
        informe = audita(lee(escribe(tmp_path, factura([linea()], importe_total="121.01"))))
        assert "RRSIF042" not in reglas_de(informe)

    @pytest.mark.parametrize(
        "importe,severidad",
        [("125.00", Severidad.AVISO), ("131.00", Severidad.AVISO), ("131.01", Severidad.ERROR)],
    )
    def test_margen_de_diez_euros(
        self, tmp_path: Path, importe: str, severidad: Severidad
    ) -> None:
        """La AEAT valida los totales con ±10 € y, aun fuera, acepta con error 2005.

        Dentro del margen no lo va a marcar: aviso. Fuera, el registro entra con un
        error admisible que hay que subsanar: error.
        """
        informe = audita(lee(escribe(tmp_path, factura([linea()], importe_total=importe))))
        hallazgos = [h for h in informe.hallazgos if h.regla == "RRSIF042"]
        assert [h.severidad for h in hallazgos] == [severidad]
        if severidad is Severidad.ERROR:
            assert "subsanar" in hallazgos[0].detalle
            assert "rechaza" not in hallazgos[0].detalle

    @pytest.mark.parametrize("regimen", ["03", "05", "06", "08", "09"])
    def test_regimenes_sin_cuadre_de_totales(self, tmp_path: Path, regimen: str) -> None:
        """En el REBU y compañía los totales no salen de las líneas por diseño (§16-17)."""
        informe = audita(
            lee(escribe(tmp_path, factura([linea(regimen=regimen)], cuota_total="40.00",
                                          importe_total="500.00")))
        )
        assert "RRSIF041" not in reglas_de(informe)
        assert "RRSIF042" not in reglas_de(informe)


class TestCuadreDeLinea:
    def test_cuota_que_no_sale_de_base_por_tipo(self, tmp_path: Path) -> None:
        detalle = linea(base="100.00", tipo="21", cuota="15.00")
        informe = audita(
            lee(escribe(tmp_path, factura([detalle], cuota_total="15.00", importe_total="115.00")))
        )
        assert "RRSIF043" in reglas_de(informe)

    def test_fuera_del_margen_es_rechazo(self, tmp_path: Path) -> None:
        """Más de 10 € de desvío en la cuota de una línea: error 1142, rechazo."""
        detalle = linea(base="1000.00", tipo="21", cuota="190.00")
        informe = audita(
            lee(escribe(tmp_path, factura([detalle], cuota_total="190.00",
                                          importe_total="1190.00")))
        )
        hallazgos = [h for h in informe.hallazgos if h.regla == "RRSIF043"]
        assert [h.severidad for h in hallazgos] == [Severidad.ERROR]
        assert "1142" in hallazgos[0].norma

    def test_redondeo_por_articulo_es_aviso(self, tmp_path: Path) -> None:
        """Cinco céntimos de desvío: la AEAT lo admite (±10 €), así que no es un error."""
        detalle = linea(base="100.00", tipo="21", cuota="21.05")
        informe = audita(
            lee(escribe(tmp_path, factura([detalle], cuota_total="21.05", importe_total="121.05")))
        )
        hallazgos = [h for h in informe.hallazgos if h.regla == "RRSIF043"]
        assert [h.severidad for h in hallazgos] == [Severidad.AVISO]

    def test_los_desvios_dentro_del_margen_se_agregan(self, tmp_path: Path) -> None:
        """Redondear por artículo desvía casi todas las líneas: un aviso, no uno por línea."""
        registros = [
            factura([linea(cuota="21.03"), linea(cuota="21.02")], num=f"FA/{i}",
                     cuota_total="42.05", importe_total="242.05")
            for i in range(1, 4)
        ]
        informe = audita(lee(escribe(tmp_path, *registros)))
        hallazgos = [h for h in informe.hallazgos if h.regla == "RRSIF043"]
        assert len(hallazgos) == 1
        assert hallazgos[0].severidad is Severidad.AVISO
        assert "6 líneas de 3 registros" in hallazgos[0].titulo
        assert "… y 1 más" in hallazgos[0].detalle

    def test_base_a_coste_es_la_que_cuenta(self, tmp_path: Path) -> None:
        """Con BaseImponibleACoste, la cuota sale de ella y no de la base (§15.7)."""
        detalle = linea(base="100.00", base_a_coste="80.00", tipo="21", cuota="16.80")
        informe = audita(
            lee(escribe(tmp_path, factura([detalle], cuota_total="16.80", importe_total="116.80")))
        )
        assert "RRSIF043" not in reglas_de(informe)

    @pytest.mark.parametrize("tipo_factura", ["R2", "R3"])
    def test_r2_y_r3_no_se_cuadran(self, tmp_path: Path, tipo_factura: str) -> None:
        """§15.7 exceptúa el cuadre y el signo de la cuota en R2 y R3."""
        detalle = linea(base="-100.00", tipo="21", cuota="5.00")
        registro = factura(
            [detalle], cuota_total="5.00", importe_total="-95.00", tipo_factura=tipo_factura
        ).replace(
            f"<TipoFactura>{tipo_factura}</TipoFactura>",
            f"<TipoFactura>{tipo_factura}</TipoFactura><TipoRectificativa>S</TipoRectificativa>",
        )
        informe = audita(lee(escribe(tmp_path, registro)))
        assert "RRSIF043" not in reglas_de(informe)
        assert "RRSIF044" not in reglas_de(informe)

    def test_s1_sin_cuota(self, tmp_path: Path) -> None:
        """En S1 tipo y cuota son obligatorios: error 1208."""
        detalle = linea(cuota="")
        informe = audita(
            lee(escribe(tmp_path, factura([detalle], cuota_total="0.00", importe_total="100.00")))
        )
        hallazgos = [h for h in informe.hallazgos if h.regla == "RRSIF043"]
        assert hallazgos and "1208" in hallazgos[0].norma

    def test_signos_distintos(self, tmp_path: Path) -> None:
        detalle = linea(base="-100.00", tipo="21", cuota="21.00")
        informe = audita(
            lee(escribe(tmp_path, factura([detalle], cuota_total="21.00", importe_total="-79.00")))
        )
        assert "RRSIF044" in reglas_de(informe)

    def test_abono_con_ambos_negativos_es_correcto(self, tmp_path: Path) -> None:
        detalle = linea(base="-100.00", tipo="21", cuota="-21.00")
        informe = audita(
            lee(
                escribe(
                    tmp_path,
                    factura([detalle], cuota_total="-21.00", importe_total="-121.00"),
                )
            )
        )
        assert "RRSIF044" not in reglas_de(informe)


class TestValoresDeLista:
    @pytest.mark.parametrize("campo,valor", [("impuesto", "99"), ("regimen", "99")])
    def test_valor_fuera_de_lista(self, tmp_path: Path, campo: str, valor: str) -> None:
        informe = audita(lee(escribe(tmp_path, factura([linea(**{campo: valor})]))))
        assert "RRSIF045" in reglas_de(informe)

    def test_calificacion_invalida(self, tmp_path: Path) -> None:
        informe = audita(lee(escribe(tmp_path, factura([linea(calificacion="X9")]))))
        assert "RRSIF045" in reglas_de(informe)

    @pytest.mark.parametrize("impuesto", ["01", "02", "03", "05"])
    def test_impuestos_validos(self, tmp_path: Path, impuesto: str) -> None:
        informe = audita(lee(escribe(tmp_path, factura([linea(impuesto=impuesto)]))))
        assert "RRSIF045" not in reglas_de(informe)


class TestExentasYNoSujetas:
    def test_exenta_con_cuota_es_error(self, tmp_path: Path) -> None:
        """Lo exento no informa tipo ni cuota: error 1238 del listado de la AEAT."""
        detalle = linea(exenta="E1", tipo="", cuota="21.00", base="100.00")
        informe = audita(
            lee(escribe(tmp_path, factura([detalle], cuota_total="21.00", importe_total="121.00")))
        )
        hallazgos = [h for h in informe.hallazgos if h.regla == "RRSIF046"]
        assert hallazgos and all(h.severidad is Severidad.ERROR for h in hallazgos)
        assert "1238" in hallazgos[0].norma

    def test_exenta_con_tipo_y_sin_cuota(self, tmp_path: Path) -> None:
        """Tampoco el tipo: una exenta con TipoImpositivo es el mismo 1238."""
        detalle = linea(exenta="E1", tipo="21", cuota="")
        informe = audita(
            lee(escribe(tmp_path, factura([detalle], cuota_total="0.00", importe_total="100.00")))
        )
        assert "RRSIF046" in reglas_de(informe)

    def test_no_sujeta_con_iva_y_cuota(self, tmp_path: Path) -> None:
        detalle = linea(calificacion="N1", tipo="21", cuota="21.00")
        informe = audita(lee(escribe(tmp_path, factura([detalle]))))
        hallazgos = [h for h in informe.hallazgos if h.regla == "RRSIF046"]
        assert hallazgos and "1237" in hallazgos[0].norma

    def test_no_sujeta_sin_tipo_ni_cuota_es_correcta(self, tmp_path: Path) -> None:
        detalle = linea(calificacion="N1", tipo="", cuota="")
        informe = audita(
            lee(escribe(tmp_path, factura([detalle], cuota_total="0.00", importe_total="100.00")))
        )
        assert informe.hallazgos == []

    def test_exenta_sin_cuota_es_correcta(self, tmp_path: Path) -> None:
        detalle = linea(exenta="E1", tipo="", cuota="")
        informe = audita(
            lee(escribe(tmp_path, factura([detalle], cuota_total="0.00", importe_total="100.00")))
        )
        assert "RRSIF046" not in reglas_de(informe)

    def test_inversion_del_sujeto_pasivo_con_cuota(self, tmp_path: Path) -> None:
        """En S2 repercute el destinatario, no el emisor (error 1198)."""
        detalle = linea(calificacion="S2")
        informe = audita(lee(escribe(tmp_path, factura([detalle]))))
        hallazgos = [h for h in informe.hallazgos if h.regla == "RRSIF046"]
        assert hallazgos and "1198" in hallazgos[0].norma

    def test_inversion_del_sujeto_pasivo_con_tipo_y_cuota_cero(self, tmp_path: Path) -> None:
        """S2 lleva el tipo a 0, no el 21 de la operación: también es 1198.

        Y no es un descuadre de cuota (RRSIF043): el 1142 sólo se aplica a S1.
        """
        detalle = linea(calificacion="S2", tipo="21", cuota="0.00")
        informe = audita(
            lee(escribe(tmp_path, factura([detalle], cuota_total="0.00", importe_total="100.00")))
        )
        assert "RRSIF046" in reglas_de(informe)
        assert "RRSIF043" not in reglas_de(informe)

    def test_inversion_del_sujeto_pasivo_bien_informada(self, tmp_path: Path) -> None:
        detalle = linea(calificacion="S2", tipo="0", cuota="0.00")
        informe = audita(
            lee(escribe(tmp_path, factura([detalle], cuota_total="0.00", importe_total="100.00")))
        )
        assert informe.hallazgos == []


class TestRecargoDeEquivalencia:
    def test_tipo_sin_cuota(self, tmp_path: Path) -> None:
        informe = audita(lee(escribe(tmp_path, factura([linea(tipo_recargo="5.2")]))))
        assert "RRSIF047" in reglas_de(informe)

    @pytest.mark.parametrize(
        "tipo,recargo,valido",
        [("21", "5.2", True), ("10", "1.4", True), ("4", "0.5", True), ("21", "1.4", False)],
    )
    def test_recargo_admitido_por_tipo(
        self, tmp_path: Path, tipo: str, recargo: str, valido: bool
    ) -> None:
        from decimal import Decimal

        base = Decimal("100.00")
        cuota = (base * Decimal(tipo) / 100).quantize(Decimal("0.01"))
        c_rec = (base * Decimal(recargo) / 100).quantize(Decimal("0.01"))
        detalle = linea(base="100.00", tipo=tipo, cuota=str(cuota),
                  tipo_recargo=recargo, cuota_recargo=str(c_rec))
        informe = audita(
            lee(
                escribe(
                    tmp_path,
                    factura([detalle], cuota_total=str(cuota + c_rec),
                             importe_total=str(base + cuota + c_rec)),
                )
            )
        )
        assert ("RRSIF047" in reglas_de(informe)) is not valido


class TestMacrodato:
    def test_importe_grande_sin_macrodato(self, tmp_path: Path) -> None:
        detalle = linea(base="100000000.00", tipo="0", cuota="0.00")
        informe = audita(
            lee(
                escribe(
                    tmp_path,
                    factura([detalle], cuota_total="0.00", importe_total="100000000.00"),
                )
            )
        )
        assert "RRSIF048" in reglas_de(informe)

    def test_macrodato_en_importe_pequeno(self, tmp_path: Path) -> None:
        informe = audita(lee(escribe(tmp_path, factura([linea()], macrodato="S"))))
        assert "RRSIF048" in reglas_de(informe)

    def test_valor_invalido(self, tmp_path: Path) -> None:
        informe = audita(lee(escribe(tmp_path, factura([linea()], macrodato="X"))))
        assert "RRSIF048" in reglas_de(informe)


class TestDestinatario:
    @pytest.mark.parametrize("tipo", ["F1", "F3", "R1", "R2", "R3", "R4"])
    def test_obligatorio(self, tmp_path: Path, tipo: str) -> None:
        informe = audita(
            lee(escribe(tmp_path, factura([linea()], tipo_factura=tipo, destinatario=False)))
        )
        assert "RRSIF049" in reglas_de(informe)

    @pytest.mark.parametrize("tipo", ["F2", "R5"])
    def test_simplificadas_no_lo_exigen(self, tmp_path: Path, tipo: str) -> None:
        informe = audita(
            lee(escribe(tmp_path, factura([linea()], tipo_factura=tipo, destinatario=False)))
        )
        assert "RRSIF049" not in reglas_de(informe)

    @pytest.mark.parametrize("tipo", ["F2", "R5"])
    def test_simplificadas_no_lo_admiten(self, tmp_path: Path, tipo: str) -> None:
        """Error 1190: una F2 o R5 con `Destinatarios` se rechaza."""
        informe = audita(
            lee(escribe(tmp_path, factura([linea()], tipo_factura=tipo, destinatario=True)))
        )
        hallazgos = [h for h in informe.hallazgos if h.regla == "RRSIF049"]
        assert hallazgos and "1190" in hallazgos[0].norma


class TestSinDesglose:
    def test_alta_sin_desglose(self, tmp_path: Path) -> None:
        informe = audita(lee(escribe(tmp_path, factura([]))))
        assert "RRSIF040" in reglas_de(informe)
