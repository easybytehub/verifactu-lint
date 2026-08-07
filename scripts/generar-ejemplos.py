#!/usr/bin/env python3
"""Genera los ficheros de `ejemplos/` con la estructura oficial.

**Se generan en vez de escribirse a mano por una razón concreta**: las huellas.
Un ejemplo con una huella copiada deja de ser correcto en cuanto alguien toca un
campo, y el error resultante —una cadena que no cuadra— es indistinguible del
defecto que el ejemplo pretende ilustrar. Aquí las huellas se calculan.

Los ejemplos con defectos son **estructuralmente válidos**: pasan el XSD oficial de
la AEAT y aun así incumplen. Ésa es exactamente la franja en la que trabaja esta
herramienta, y por eso los ejemplos rotos también se validan contra el esquema en
`tests/test_esquemas.py`.

Uso: python scripts/generar-ejemplos.py
"""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

from verifactu_lint.huella import huella_alta, huella_evento  # noqa: E402

LR = (
    "https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/"
    "aplicaciones/es/aeat/tike/cont/ws/SuministroLR.xsd"
)
SF = (
    "https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/"
    "aplicaciones/es/aeat/tike/cont/ws/SuministroInformacion.xsd"
)
EV = (
    "https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/"
    "aplicaciones/es/aeat/tike/cont/ws/EventosSIF.xsd"
)
DS = "http://www.w3.org/2000/09/xmldsig#"

NIF = "89890001K"
NIF_CLIENTE = "12345678Z"
EMISOR = "Empresa de Ejemplo SL"


def alta(
    num: str,
    huella: str,
    *,
    anterior: str | None,
    hora: str,
    base: str = "100.00",
    cuota: str = "21.00",
    total: str = "121.00",
) -> str:
    if anterior is None:
        encadenamiento = "<sf:PrimerRegistro>S</sf:PrimerRegistro>"
    else:
        encadenamiento = (
            "<sf:RegistroAnterior>"
            f"<sf:IDEmisorFactura>{NIF}</sf:IDEmisorFactura>"
            "<sf:NumSerieFactura>previa</sf:NumSerieFactura>"
            "<sf:FechaExpedicionFactura>01-01-2024</sf:FechaExpedicionFactura>"
            f"<sf:Huella>{anterior}</sf:Huella>"
            "</sf:RegistroAnterior>"
        )
    return f"""  <sfLR:RegistroFactura>
    <sf:RegistroAlta>
      <sf:IDVersion>1.0</sf:IDVersion>
      <sf:IDFactura>
        <sf:IDEmisorFactura>{NIF}</sf:IDEmisorFactura>
        <sf:NumSerieFactura>{num}</sf:NumSerieFactura>
        <sf:FechaExpedicionFactura>01-01-2024</sf:FechaExpedicionFactura>
      </sf:IDFactura>
      <sf:NombreRazonEmisor>{EMISOR}</sf:NombreRazonEmisor>
      <sf:TipoFactura>F1</sf:TipoFactura>
      <sf:DescripcionOperacion>Prestacion de servicios</sf:DescripcionOperacion>
      <sf:Destinatarios>
        <sf:IDDestinatario>
          <sf:NombreRazon>Cliente de Ejemplo SL</sf:NombreRazon>
          <sf:NIF>{NIF_CLIENTE}</sf:NIF>
        </sf:IDDestinatario>
      </sf:Destinatarios>
      <sf:Desglose>
        <sf:DetalleDesglose>
          <sf:ClaveRegimen>01</sf:ClaveRegimen>
          <sf:CalificacionOperacion>S1</sf:CalificacionOperacion>
          <sf:TipoImpositivo>21</sf:TipoImpositivo>
          <sf:BaseImponibleOimporteNoSujeto>{base}</sf:BaseImponibleOimporteNoSujeto>
          <sf:CuotaRepercutida>{cuota}</sf:CuotaRepercutida>
        </sf:DetalleDesglose>
      </sf:Desglose>
      <sf:CuotaTotal>{cuota}</sf:CuotaTotal>
      <sf:ImporteTotal>{total}</sf:ImporteTotal>
      <sf:Encadenamiento>{encadenamiento}</sf:Encadenamiento>
      <sf:SistemaInformatico>
        <sf:NombreRazon>EasyByte Hub S. Coop. Mad.</sf:NombreRazon>
        <sf:NIF>{NIF}</sf:NIF>
        <sf:NombreSistemaInformatico>Sistema de Ejemplo</sf:NombreSistemaInformatico>
        <sf:IdSistemaInformatico>A1</sf:IdSistemaInformatico>
        <sf:Version>1.0</sf:Version>
        <sf:NumeroInstalacion>0001</sf:NumeroInstalacion>
        <sf:TipoUsoPosibleSoloVerifactu>S</sf:TipoUsoPosibleSoloVerifactu>
        <sf:TipoUsoPosibleMultiOT>N</sf:TipoUsoPosibleMultiOT>
        <sf:IndicadorMultiplesOT>N</sf:IndicadorMultiplesOT>
      </sf:SistemaInformatico>
      <sf:FechaHoraHusoGenRegistro>{hora}</sf:FechaHoraHusoGenRegistro>
      <sf:TipoHuella>01</sf:TipoHuella>
      <sf:Huella>{huella}</sf:Huella>
    </sf:RegistroAlta>
  </sfLR:RegistroFactura>
"""


def envuelve_facturas(registros: list[str]) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<sfLR:RegFactuSistemaFacturacion xmlns:sfLR="{LR}" xmlns:sf="{SF}">\n'
        "  <sfLR:Cabecera>\n"
        "    <sf:ObligadoEmision>\n"
        f"      <sf:NombreRazon>{EMISOR}</sf:NombreRazon>\n"
        f"      <sf:NIF>{NIF}</sf:NIF>\n"
        "    </sf:ObligadoEmision>\n"
        "  </sfLR:Cabecera>\n" + "".join(registros) +
        "</sfLR:RegFactuSistemaFacturacion>\n"
    )


def cadena_facturas(n: int, romper_en: int | None = None) -> list[str]:
    registros: list[str] = []
    previa: str | None = None
    for i in range(n):
        num = f"FA/2024/{i + 1}"
        hora = f"2024-01-01T19:20:{30 + i:02d}+01:00"
        # El registro `romper_en` declara una huella anterior que no existe: la cadena
        # se corta ahí sin que el XML deje de ser válido.
        anterior = "A" * 64 if i == romper_en else previa
        h = huella_alta(NIF, num, "01-01-2024", "F1", "21.00", "121.00", anterior, hora)
        registros.append(alta(num, h, anterior=anterior, hora=hora))
        previa = h
    return registros


def evento(tipo: str, huella: str, *, anterior: str | None, hora: str, datos: str = "") -> str:
    if anterior is None:
        encadenamiento = "<sf:PrimerEvento>S</sf:PrimerEvento>"
    else:
        encadenamiento = (
            "<sf:EventoAnterior>"
            "<sf:TipoEvento>01</sf:TipoEvento>"
            f"<sf:FechaHoraHusoGenEvento>{hora}</sf:FechaHoraHusoGenEvento>"
            f"<sf:HuellaEvento>{anterior}</sf:HuellaEvento>"
            "</sf:EventoAnterior>"
        )
    bloque = f"<sf:DatosPropiosEvento>{datos}</sf:DatosPropiosEvento>" if datos else ""
    return f"""  <sf:RegistroEvento>
    <sf:IDVersion>1.0</sf:IDVersion>
    <sf:Evento>
      <sf:SistemaInformatico>
        <sf:NombreRazon>EasyByte Hub S. Coop. Mad.</sf:NombreRazon>
        <sf:NIF>{NIF}</sf:NIF>
        <sf:NombreSistemaInformatico>Sistema de Ejemplo</sf:NombreSistemaInformatico>
        <sf:IdSistemaInformatico>A1</sf:IdSistemaInformatico>
        <sf:Version>1.0</sf:Version>
        <sf:NumeroInstalacion>0001</sf:NumeroInstalacion>
        <sf:TipoUsoPosibleSoloVerifactu>N</sf:TipoUsoPosibleSoloVerifactu>
        <sf:TipoUsoPosibleMultiOT>N</sf:TipoUsoPosibleMultiOT>
        <sf:IndicadorMultiplesOT>N</sf:IndicadorMultiplesOT>
      </sf:SistemaInformatico>
      <sf:ObligadoEmision>
        <sf:NombreRazon>{EMISOR}</sf:NombreRazon>
        <sf:NIF>{NIF_CLIENTE}</sf:NIF>
      </sf:ObligadoEmision>
      <sf:FechaHoraHusoGenEvento>{hora}</sf:FechaHoraHusoGenEvento>
      <sf:TipoEvento>{tipo}</sf:TipoEvento>
      {bloque}
      <sf:Encadenamiento>{encadenamiento}</sf:Encadenamiento>
      <sf:TipoHuella>01</sf:TipoHuella>
      <sf:HuellaEvento>{huella}</sf:HuellaEvento>
      <ds:Signature xmlns:ds="{DS}">
        <ds:SignedInfo>
          <ds:CanonicalizationMethod Algorithm="http://www.w3.org/TR/2001/REC-xml-c14n-20010315"/>
          <ds:SignatureMethod Algorithm="http://www.w3.org/2001/04/xmldsig-more#rsa-sha256"/>
          <ds:Reference URI="">
            <ds:DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#sha256"/>
            <ds:DigestValue>ZXhlbXBsbw==</ds:DigestValue>
          </ds:Reference>
        </ds:SignedInfo>
        <ds:SignatureValue>ZXhlbXBsbw==</ds:SignatureValue>
      </ds:Signature>
    </sf:Evento>
  </sf:RegistroEvento>
"""


def envuelve_eventos(eventos: list[str]) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<sf:RegistroEventos xmlns:sf="{EV}">\n' + "".join(eventos) +
        "</sf:RegistroEventos>\n"
    )


# Los campos y su orden salen de `ResumenEventosType` en el esquema oficial. El
# resumen no es una marca de tiempo: lleva el recuento de registros del periodo y la
# suma de sus importes, que es lo que permite detectar que faltan registros.
# `TipoEvento` dentro del resumen no es el código suelto: es un bloque con el código y
# cuántos eventos de ese tipo hubo en el periodo. Se repite hasta veinte veces, uno por
# tipo, y es lo que convierte el resumen en un recuento comprobable.
RESUMEN = (
    "<sf:ResumenEventos>"
    "<sf:TipoEvento>"
    "<sf:TipoEvento>01</sf:TipoEvento>"
    "<sf:NumeroDeEventos>1</sf:NumeroDeEventos>"
    "</sf:TipoEvento>"
    "<sf:NumeroDeRegistrosFacturacionAltaGenerados>3"
    "</sf:NumeroDeRegistrosFacturacionAltaGenerados>"
    "<sf:SumaCuotaTotalAlta>63.00</sf:SumaCuotaTotalAlta>"
    "<sf:SumaImporteTotalAlta>363.00</sf:SumaImporteTotalAlta>"
    "<sf:NumeroDeRegistrosFacturacionAnulacionGenerados>0"
    "</sf:NumeroDeRegistrosFacturacionAnulacionGenerados>"
    "</sf:ResumenEventos>"
)


def cadena_eventos(tipos: list[tuple[str, str]], romper_en: int | None = None) -> list[str]:
    eventos: list[str] = []
    previa: str | None = None
    for i, (tipo, datos) in enumerate(tipos):
        hora = f"2024-01-01T19:{20 + i:02d}:30+01:00"
        anterior = "A" * 64 if i == romper_en else previa
        h = huella_evento(NIF, None, "A1", "1.0", "0001", NIF_CLIENTE, tipo, anterior, hora)
        eventos.append(evento(tipo, h, anterior=anterior, hora=hora, datos=datos))
        previa = h
    return eventos


def main() -> int:
    destino = RAIZ / "ejemplos"
    destino.mkdir(exist_ok=True)

    ficheros = {
        "cadena-conforme.xml": envuelve_facturas(cadena_facturas(3)),
        "cadena-rota.xml": envuelve_facturas(cadena_facturas(3, romper_en=2)),
        "eventos-conforme.xml": envuelve_eventos(
            cadena_eventos([("01", ""), ("10", RESUMEN), ("02", "")])
        ),
        "eventos-con-defectos.xml": envuelve_eventos(
            # El 08 exige `ExportacionRegFacturacionPeriodo` y no lo lleva; además la
            # cadena se rompe en él. Las dos cosas son invisibles para el XSD.
            cadena_eventos([("01", ""), ("08", "")], romper_en=1)
        ),
    }
    for nombre, contenido in ficheros.items():
        (destino / nombre).write_text(contenido, encoding="utf-8")
        print(f"escrito ejemplos/{nombre}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
