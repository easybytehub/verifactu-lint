"""Las reglas de eventos, sobre cadenas construidas con huellas reales.

Los códigos de `TipoEvento` y la estructura del registro salen del esquema oficial
`EventosSIF.xsd` de la AEAT. Igual que en `test_reglas.py`, las huellas se calculan
con el propio módulo en vez de escribirse a mano: una constante copiada de la salida
deja de comprobar nada en cuanto alguien la actualiza sin pensar.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from verifactu_lint.hallazgos import Severidad
from verifactu_lint.huella import huella_evento
from verifactu_lint.registros import lee_eventos
from verifactu_lint.reglas import audita_eventos
from verifactu_lint.reglas.eventos import DATOS_POR_TIPO, TIPOS_EVENTO

NIF_SIS = "89890001K"
NIF_OBL = "12345678Z"
FIRMA = '<ds:Signature xmlns:ds="http://www.w3.org/2000/09/xmldsig#"><ds:SignatureValue>x</ds:SignatureValue></ds:Signature>'


def evento_xml(
    tipo: str,
    huella_valor: str,
    *,
    anterior: str | None = None,
    hora: str = "2024-01-01T19:20:30+01:00",
    datos: str | None = None,
    firma: str = FIRMA,
    version: str = "1.0",
    num_instalacion: str = "0001",
) -> str:
    if anterior is None:
        enc = "<Encadenamiento><PrimerEvento>S</PrimerEvento></Encadenamiento>"
    else:
        enc = (
            "<Encadenamiento><EventoAnterior>"
            "<TipoEvento>01</TipoEvento>"
            f"<FechaHoraHusoGenEvento>{hora}</FechaHoraHusoGenEvento>"
            f"<HuellaEvento>{anterior}</HuellaEvento>"
            "</EventoAnterior></Encadenamiento>"
        )
    bloque_datos = ""
    if datos is None and tipo in DATOS_POR_TIPO:
        datos = DATOS_POR_TIPO[tipo]
    if datos:
        bloque_datos = f"<DatosPropiosEvento><{datos}/></DatosPropiosEvento>"

    return f"""
  <RegistroEvento>
    <IDVersion>1.0</IDVersion>
    <Evento>
      <SistemaInformatico>
        <NombreRazon>Ejemplo SL</NombreRazon>
        <NIF>{NIF_SIS}</NIF>
        <IdSistemaInformatico>A1</IdSistemaInformatico>
        <Version>{version}</Version>
        <NumeroInstalacion>{num_instalacion}</NumeroInstalacion>
      </SistemaInformatico>
      <ObligadoEmision><NombreRazon>Cliente SL</NombreRazon><NIF>{NIF_OBL}</NIF></ObligadoEmision>
      <FechaHoraHusoGenEvento>{hora}</FechaHoraHusoGenEvento>
      <TipoEvento>{tipo}</TipoEvento>
      {bloque_datos}
      {enc}
      <TipoHuella>01</TipoHuella>
      <HuellaEvento>{huella_valor}</HuellaEvento>
      {firma}
    </Evento>
  </RegistroEvento>
"""


def calcula(tipo: str, anterior: str | None, hora: str, *, version: str = "1.0",
            num_instalacion: str = "0001") -> str:
    return huella_evento(
        NIF_SIS, None, "A1", version, num_instalacion, NIF_OBL, tipo, anterior, hora
    )


def envuelve(*eventos: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<RegFactuSistemaFacturacion>" + "".join(eventos) + "</RegFactuSistemaFacturacion>"
    )


def escribe(tmp_path: Path, contenido: str) -> Path:
    ruta = tmp_path / "eventos.xml"
    ruta.write_text(contenido, encoding="utf-8")
    return ruta


def cadena(tipos: list[str]) -> list[str]:
    """Eventos correctamente encadenados, con los tipos dados."""
    salida: list[str] = []
    previa: str | None = None
    for i, tipo in enumerate(tipos):
        hora = f"2024-01-01T19:{20 + i:02d}:30+01:00"
        h = calcula(tipo, previa, hora)
        salida.append(evento_xml(tipo, h, anterior=previa, hora=hora))
        previa = h
    return salida


def reglas_de(informe: object) -> set[str]:
    return {h.regla for h in informe.hallazgos}  # type: ignore[attr-defined]


class TestCatalogo:
    def test_los_once_tipos_del_esquema(self) -> None:
        assert set(TIPOS_EVENTO) == {
            "01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "90"
        }

    def test_los_tipos_con_datos_propios_existen_en_el_catalogo(self) -> None:
        assert set(DATOS_POR_TIPO) <= set(TIPOS_EVENTO)


class TestCadenaCorrecta:
    def test_no_produce_hallazgos(self, tmp_path: Path) -> None:
        ruta = escribe(tmp_path, envuelve(*cadena(["01", "10", "02"])))
        informe = audita_eventos(lee_eventos(ruta))
        assert informe.hallazgos == []
        assert informe.registros_analizados == 3

    def test_se_leen_con_namespace(self, tmp_path: Path) -> None:
        contenido = envuelve(*cadena(["01", "10"])).replace(
            "<RegFactuSistemaFacturacion>",
            '<sf:RegFactuSistemaFacturacion xmlns:sf="urn:x">',
        ).replace("</RegFactuSistemaFacturacion>", "</sf:RegFactuSistemaFacturacion>")
        ruta = escribe(tmp_path, contenido)
        assert len(lee_eventos(ruta)) == 2


class TestHuellaDeEvento:
    def test_huella_incorrecta(self, tmp_path: Path) -> None:
        ruta = escribe(tmp_path, envuelve(evento_xml("01", "0" * 64)))
        informe = audita_eventos(lee_eventos(ruta))
        assert "RRSIF021" in reglas_de(informe)

    def test_el_nif_del_obligado_entra_en_la_huella(self, tmp_path: Path) -> None:
        """El error clásico: tratar los dos `NIF` de la cadena como uno solo.

        Si se omitiera el del obligado, esta huella —correcta— se marcaría mal.
        """
        hora = "2024-01-01T19:20:30+01:00"
        h = calcula("01", None, hora)
        ruta = escribe(tmp_path, envuelve(evento_xml("01", h, hora=hora)))
        informe = audita_eventos(lee_eventos(ruta))
        assert "RRSIF021" not in reglas_de(informe)

    def test_cambiar_la_version_cambia_la_huella(self, tmp_path: Path) -> None:
        """`Version` es uno de los nueve campos: no es metadato decorativo."""
        hora = "2024-01-01T19:20:30+01:00"
        h = calcula("01", None, hora, version="1.0")
        ruta = escribe(tmp_path, envuelve(evento_xml("01", h, hora=hora, version="2.0")))
        informe = audita_eventos(lee_eventos(ruta))
        assert "RRSIF021" in reglas_de(informe)

    def test_huella_en_minusculas(self, tmp_path: Path) -> None:
        hora = "2024-01-01T19:20:30+01:00"
        h = calcula("01", None, hora)
        ruta = escribe(tmp_path, envuelve(evento_xml("01", h.lower(), hora=hora)))
        informe = audita_eventos(lee_eventos(ruta))
        assert "RRSIF022" in reglas_de(informe)


class TestTipoEvento:
    def test_tipo_inexistente(self, tmp_path: Path) -> None:
        hora = "2024-01-01T19:20:30+01:00"
        h = calcula("99", None, hora)
        ruta = escribe(tmp_path, envuelve(evento_xml("99", h, hora=hora, datos="")))
        informe = audita_eventos(lee_eventos(ruta))
        assert "RRSIF020" in reglas_de(informe)

    @pytest.mark.parametrize("tipo", sorted(TIPOS_EVENTO))
    def test_todos_los_tipos_del_esquema_se_aceptan(self, tmp_path: Path, tipo: str) -> None:
        hora = "2024-01-01T19:20:30+01:00"
        h = calcula(tipo, None, hora)
        ruta = escribe(tmp_path, envuelve(evento_xml(tipo, h, hora=hora)))
        informe = audita_eventos(lee_eventos(ruta))
        assert "RRSIF020" not in reglas_de(informe)


class TestEncadenamiento:
    def test_cadena_rota(self, tmp_path: Path) -> None:
        eventos = cadena(["01", "10"])
        hora = "2024-01-01T19:21:30+01:00"
        h = calcula("10", "F" * 64, hora)
        eventos[1] = evento_xml("10", h, anterior="F" * 64, hora=hora)
        ruta = escribe(tmp_path, envuelve(*eventos))
        informe = audita_eventos(lee_eventos(ruta))
        assert "RRSIF023" in reglas_de(informe)

    def test_dos_primeros_eventos(self, tmp_path: Path) -> None:
        hora = "2024-01-01T19:20:30+01:00"
        h = calcula("01", None, hora)
        uno = evento_xml("01", h, hora=hora)
        ruta = escribe(tmp_path, envuelve(uno, uno))
        informe = audita_eventos(lee_eventos(ruta))
        assert "RRSIF024" in reglas_de(informe)


class TestFirma:
    def test_evento_sin_firma(self, tmp_path: Path) -> None:
        hora = "2024-01-01T19:20:30+01:00"
        h = calcula("01", None, hora)
        ruta = escribe(tmp_path, envuelve(evento_xml("01", h, hora=hora, firma="")))
        informe = audita_eventos(lee_eventos(ruta))
        assert "RRSIF025" in reglas_de(informe)

    def test_evento_firmado_no_da_hallazgo(self, tmp_path: Path) -> None:
        ruta = escribe(tmp_path, envuelve(*cadena(["01"])))
        informe = audita_eventos(lee_eventos(ruta))
        assert "RRSIF025" not in reglas_de(informe)


class TestDatosPropios:
    def test_exportacion_sin_sus_datos(self, tmp_path: Path) -> None:
        hora = "2024-01-01T19:20:30+01:00"
        h = calcula("08", None, hora)
        ruta = escribe(tmp_path, envuelve(evento_xml("08", h, hora=hora, datos="")))
        informe = audita_eventos(lee_eventos(ruta))
        assert "RRSIF026" in reglas_de(informe)

    def test_datos_de_otro_tipo(self, tmp_path: Path) -> None:
        hora = "2024-01-01T19:20:30+01:00"
        h = calcula("08", None, hora)
        ruta = escribe(
            tmp_path,
            envuelve(evento_xml("08", h, hora=hora, datos="ResumenEventos")),
        )
        informe = audita_eventos(lee_eventos(ruta))
        assert "RRSIF026" in reglas_de(informe)

    def test_tipo_sin_datos_que_los_lleva_es_aviso(self, tmp_path: Path) -> None:
        hora = "2024-01-01T19:20:30+01:00"
        h = calcula("01", None, hora)
        ruta = escribe(
            tmp_path,
            envuelve(evento_xml("01", h, hora=hora, datos="ResumenEventos")),
        )
        informe = audita_eventos(lee_eventos(ruta))
        avisos = [x for x in informe.hallazgos if x.regla == "RRSIF026"]
        assert avisos and all(x.severidad is Severidad.AVISO for x in avisos)


class TestCicloYResumen:
    def test_fin_sin_inicio(self, tmp_path: Path) -> None:
        ruta = escribe(tmp_path, envuelve(*cadena(["02"])))
        informe = audita_eventos(lee_eventos(ruta))
        assert "RRSIF027" in reglas_de(informe)

    def test_dos_inicios_seguidos(self, tmp_path: Path) -> None:
        ruta = escribe(tmp_path, envuelve(*cadena(["01", "01"])))
        informe = audita_eventos(lee_eventos(ruta))
        assert "RRSIF027" in reglas_de(informe)

    def test_sin_resumen_es_incompleto_no_error(self, tmp_path: Path) -> None:
        """No se puede demostrar el incumplimiento sin saber cuánto estuvo operativo."""
        ruta = escribe(tmp_path, envuelve(*cadena(["01", "02"])))
        informe = audita_eventos(lee_eventos(ruta))
        resumen = [x for x in informe.hallazgos if x.regla == "RRSIF028"]
        assert resumen and all(x.severidad is Severidad.INCOMPLETO for x in resumen)

    def test_con_resumen_no_hay_hallazgo(self, tmp_path: Path) -> None:
        ruta = escribe(tmp_path, envuelve(*cadena(["01", "10", "02"])))
        informe = audita_eventos(lee_eventos(ruta))
        assert "RRSIF028" not in reglas_de(informe)
