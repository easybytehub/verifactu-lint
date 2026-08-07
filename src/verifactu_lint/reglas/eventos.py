"""Reglas sobre los registros de evento.

**Los eventos son la modalidad NO VERI\\*FACTU.** Un sistema que remite sus registros
a la sede electrónica da por cumplidos los requisitos de seguridad con esa remisión.
El que no los remite tiene que demostrar por su cuenta integridad, inalterabilidad y
trazabilidad, y el registro de eventos es el mecanismo con el que lo hace.

Esa asimetría es la que sorprende: la modalidad que parece «la de menos compromiso»
—no enviar nada a Hacienda— es técnicamente la exigente. La AEAT lo dice sin rodeos
en su FAQ de desarrolladores.

Los códigos de `TipoEvento` y la estructura salen del esquema oficial `EventosSIF.xsd`
publicado por la AEAT, no de una interpretación nuestra.
"""

from __future__ import annotations

import re
from itertools import pairwise

from verifactu_lint.hallazgos import Hallazgo, Severidad
from verifactu_lint.huella import huella_evento
from verifactu_lint.registros import Evento

FORMATO_HUELLA = re.compile(r"^[0-9A-F]{64}$")

NORMA_EVENTOS = "RD 1007/2023, art. 8.3; Orden HAC/1177/2024, anexo — EventosSIF.xsd"

# Lista `TipoEventoType` del esquema oficial, con su descripción literal.
TIPOS_EVENTO: dict[str, str] = {
    "01": "Inicio del funcionamiento del sistema informático como «NO VERI*FACTU»",
    "02": "Fin del funcionamiento del sistema informático como «NO VERI*FACTU»",
    "03": "Lanzamiento del proceso de detección de anomalías en los registros de facturación",
    "04": "Detección de anomalías en registros de facturación",
    "05": "Lanzamiento del proceso de detección de anomalías en los registros de evento",
    "06": "Detección de anomalías en registros de evento",
    "07": "Restauración de copia de seguridad",
    "08": "Exportación de registros de facturación generados en un periodo",
    "09": "Exportación de registros de evento generados en un periodo",
    "10": "Registro resumen de eventos",
    "90": "Otros tipos de eventos, voluntarios",
}

# `DatosPropiosEvento` es un `choice` en el esquema: qué hijo corresponde a cada tipo
# no lo dice una tabla del reglamento, se deduce de los nombres. Los tipos que no
# aparecen aquí no llevan datos propios.
DATOS_POR_TIPO: dict[str, str] = {
    "03": "LanzamientoProcesoDeteccionAnomaliasRegFacturacion",
    "04": "DeteccionAnomaliasRegFacturacion",
    "05": "LanzamientoProcesoDeteccionAnomaliasRegEvento",
    "06": "DeteccionAnomaliasRegEvento",
    "08": "ExportacionRegFacturacionPeriodo",
    "09": "ExportacionRegEventoPeriodo",
    "10": "ResumenEventos",
}


def tipo_evento_valido(eventos: list[Evento]) -> list[Hallazgo]:
    """RRSIF020 — `TipoEvento` debe estar en la lista del esquema."""
    hallazgos: list[Hallazgo] = []
    for e in eventos:
        valor = (e.tipo_evento or "").strip()
        if not valor:
            hallazgos.append(
                Hallazgo(
                    regla="RRSIF020",
                    severidad=Severidad.ERROR,
                    titulo="El evento no informa TipoEvento",
                    detalle="`TipoEvento` es obligatorio en el diseño de registro de evento.",
                    norma=NORMA_EVENTOS,
                    referencia=e.referencia,
                    orden=e.orden,
                )
            )
        elif valor not in TIPOS_EVENTO:
            hallazgos.append(
                Hallazgo(
                    regla="RRSIF020",
                    severidad=Severidad.ERROR,
                    titulo=f"TipoEvento={valor} no existe",
                    detalle=(
                        "Valores admitidos: "
                        + ", ".join(f"{k} ({v})" for k, v in TIPOS_EVENTO.items())
                    ),
                    norma=NORMA_EVENTOS,
                    referencia=e.referencia,
                    orden=e.orden,
                )
            )
    return hallazgos


def huella_de_evento_correcta(eventos: list[Evento]) -> list[Hallazgo]:
    """RRSIF021 — la huella del evento sale de sus propios campos.

    Los nueve campos y su orden están en el documento técnico de la huella. Uno de
    ellos, `NIF`, aparece dos veces: el del sistema informático y el del obligado.
    """
    hallazgos: list[Hallazgo] = []
    for e in eventos:
        declarada = (e.huella or "").strip().upper()
        if not declarada:
            hallazgos.append(
                Hallazgo(
                    regla="RRSIF021",
                    severidad=Severidad.ERROR,
                    titulo="El evento no informa HuellaEvento",
                    detalle=(
                        "Se informa siempre, también en el primer evento del sistema."
                    ),
                    norma=NORMA_EVENTOS,
                    referencia=e.referencia,
                    orden=e.orden,
                )
            )
            continue

        calculada = huella_evento(
            e.sistema.nif,
            e.sistema.id_otro,
            e.sistema.id_sistema_informatico,
            e.sistema.version,
            e.sistema.numero_instalacion,
            e.nif_obligado,
            e.tipo_evento,
            e.anterior_huella,
            e.fecha_hora_huso,
        )
        if declarada != calculada:
            hallazgos.append(
                Hallazgo(
                    regla="RRSIF021",
                    severidad=Severidad.ERROR,
                    titulo="La huella del evento no coincide con la calculada",
                    detalle=(
                        f"Declarada: {declarada}\n"
                        f"Calculada: {calculada}\n"
                        "La cadena de eventos usa nueve campos, y el `NIF` entra dos "
                        "veces: el de SistemaInformatico y el de ObligadoEmision. "
                        "Tratarlos como uno solo es el error habitual."
                    ),
                    norma=NORMA_EVENTOS,
                    referencia=e.referencia,
                    orden=e.orden,
                )
            )
    return hallazgos


def formato_huella_evento(eventos: list[Evento]) -> list[Hallazgo]:
    """RRSIF022 — 64 caracteres hexadecimales en mayúsculas."""
    hallazgos: list[Hallazgo] = []
    for e in eventos:
        valor = (e.huella or "").strip()
        if not valor or FORMATO_HUELLA.match(valor):
            continue
        minusculas = bool(FORMATO_HUELLA.match(valor.upper()))
        hallazgos.append(
            Hallazgo(
                regla="RRSIF022",
                severidad=Severidad.ERROR,
                titulo=(
                    "La huella del evento está en minúsculas"
                    if minusculas
                    else "La huella del evento no tiene el formato exigido"
                ),
                detalle=(
                    "El formato de salida es hexadecimal en mayúsculas, 64 caracteres."
                    if minusculas
                    else f"Se esperaban 64 hexadecimales en mayúsculas y hay {len(valor)}."
                ),
                norma=NORMA_EVENTOS,
                referencia=e.referencia,
                orden=e.orden,
            )
        )
    return hallazgos


def cadena_de_eventos_continua(eventos: list[Evento]) -> list[Hallazgo]:
    """RRSIF023 — cada evento encadena con la huella del evento anterior."""
    hallazgos: list[Hallazgo] = []
    for previo, actual in pairwise(eventos):
        declarada = (actual.anterior_huella or "").strip().upper()
        previa = (previo.huella or "").strip().upper()

        if not declarada:
            if actual.es_primer_evento:
                continue
            hallazgos.append(
                Hallazgo(
                    regla="RRSIF023",
                    severidad=Severidad.ERROR,
                    titulo="El evento no encadena con ninguno anterior",
                    detalle=(
                        "No informa Encadenamiento/EventoAnterior/HuellaEvento ni se "
                        "declara como primer evento."
                    ),
                    norma=NORMA_EVENTOS,
                    referencia=actual.referencia,
                    orden=actual.orden,
                )
            )
            continue

        if not previa:
            hallazgos.append(
                Hallazgo(
                    regla="RRSIF023",
                    severidad=Severidad.INCOMPLETO,
                    titulo="No se puede comprobar el encadenamiento de eventos",
                    detalle=f"El evento anterior ({previo.referencia}) no informa su huella.",
                    norma=NORMA_EVENTOS,
                    referencia=actual.referencia,
                    orden=actual.orden,
                )
            )
            continue

        if declarada != previa:
            hallazgos.append(
                Hallazgo(
                    regla="RRSIF023",
                    severidad=Severidad.ERROR,
                    titulo="La cadena de eventos se rompe aquí",
                    detalle=(
                        f"Declara como huella anterior {declarada}, y la de "
                        f"{previo.referencia} es {previa}.\n"
                        "En NO VERI*FACTU la cadena de eventos es la prueba de que el "
                        "sistema funcionó sin manipulación: rota, no hay nada que la "
                        "sustituya, porque los registros no se remitieron a la AEAT."
                    ),
                    norma=NORMA_EVENTOS,
                    referencia=actual.referencia,
                    orden=actual.orden,
                )
            )
    return hallazgos


def primer_evento_coherente(eventos: list[Evento]) -> list[Hallazgo]:
    """RRSIF024 — `PrimerEvento` y `EventoAnterior` son excluyentes por esquema."""
    hallazgos: list[Hallazgo] = []
    primeros = [e for e in eventos if e.es_primer_evento]

    for e in primeros:
        if (e.anterior_huella or "").strip():
            hallazgos.append(
                Hallazgo(
                    regla="RRSIF024",
                    severidad=Severidad.ERROR,
                    titulo="Se declara primer evento y a la vez informa uno anterior",
                    detalle=(
                        "`Encadenamiento` es un `choice` en el esquema: o `PrimerEvento` "
                        "o `EventoAnterior`, nunca los dos."
                    ),
                    norma=NORMA_EVENTOS,
                    referencia=e.referencia,
                    orden=e.orden,
                )
            )

    for e in primeros[1:]:
        hallazgos.append(
            Hallazgo(
                regla="RRSIF024",
                severidad=Severidad.ERROR,
                titulo="Hay más de un evento declarado como primero",
                detalle=(
                    f"{len(primeros)} eventos declaran PrimerEvento=S. La cadena de "
                    "eventos de un sistema tiene un único origen."
                ),
                norma=NORMA_EVENTOS,
                referencia=e.referencia,
                orden=e.orden,
            )
        )
    return hallazgos


def evento_firmado(eventos: list[Evento]) -> list[Hallazgo]:
    """RRSIF025 — todo registro de evento lleva firma electrónica.

    En el esquema, `ds:Signature` no lleva `minOccurs="0"`: es obligatoria. Y tiene
    sentido — en NO VERI*FACTU nadie ha recibido esos registros, así que la firma es
    lo único que los ata a quien dice haberlos generado.
    """
    return [
        Hallazgo(
            regla="RRSIF025",
            severidad=Severidad.ERROR,
            titulo="El registro de evento no está firmado",
            detalle=(
                "El esquema exige `ds:Signature` en todo registro de evento. Sin firma "
                "el registro no acredita su origen, y en NO VERI*FACTU no hay una "
                "remisión a la AEAT que lo supla."
            ),
            norma=NORMA_EVENTOS,
            referencia=e.referencia,
            orden=e.orden,
        )
        for e in eventos
        if not e.firmado
    ]


def datos_propios_coherentes(eventos: list[Evento]) -> list[Hallazgo]:
    """RRSIF026 — `DatosPropiosEvento` debe corresponder al tipo de evento."""
    hallazgos: list[Hallazgo] = []
    for e in eventos:
        tipo = (e.tipo_evento or "").strip()
        if tipo not in TIPOS_EVENTO:
            continue  # RRSIF020 ya se ocupa
        esperado = DATOS_POR_TIPO.get(tipo)
        presente = e.datos_propios

        if esperado and not presente:
            hallazgos.append(
                Hallazgo(
                    regla="RRSIF026",
                    severidad=Severidad.ERROR,
                    titulo=f"El evento {tipo} no informa sus datos propios",
                    detalle=(
                        f"«{TIPOS_EVENTO[tipo]}» requiere el bloque `{esperado}` dentro "
                        "de `DatosPropiosEvento`. Sin él, el evento consta pero no dice "
                        "qué ocurrió."
                    ),
                    norma=NORMA_EVENTOS,
                    referencia=e.referencia,
                    orden=e.orden,
                )
            )
        elif esperado and presente and presente != esperado:
            hallazgos.append(
                Hallazgo(
                    regla="RRSIF026",
                    severidad=Severidad.ERROR,
                    titulo=f"Los datos propios no corresponden al evento {tipo}",
                    detalle=f"Se esperaba `{esperado}` y se encontró `{presente}`.",
                    norma=NORMA_EVENTOS,
                    referencia=e.referencia,
                    orden=e.orden,
                )
            )
        elif not esperado and presente:
            hallazgos.append(
                Hallazgo(
                    regla="RRSIF026",
                    severidad=Severidad.AVISO,
                    titulo=f"El evento {tipo} informa datos propios y no le corresponden",
                    detalle=(
                        f"«{TIPOS_EVENTO[tipo]}» no tiene bloque propio en el esquema, y "
                        f"aquí aparece `{presente}`."
                    ),
                    norma=NORMA_EVENTOS,
                    referencia=e.referencia,
                    orden=e.orden,
                )
            )
    return hallazgos


def ciclo_no_verifactu(eventos: list[Evento]) -> list[Hallazgo]:
    """RRSIF027 — el arranque y la parada como NO VERI\\*FACTU se emparejan.

    Un `02` (fin) sin un `01` (inicio) previo, o dos inicios seguidos sin fin, señalan
    eventos perdidos: exactamente lo que el registro existe para hacer detectable.
    """
    hallazgos: list[Hallazgo] = []
    abierto = False
    for e in eventos:
        tipo = (e.tipo_evento or "").strip()
        if tipo == "01":
            if abierto:
                hallazgos.append(
                    Hallazgo(
                        regla="RRSIF027",
                        severidad=Severidad.AVISO,
                        titulo="Dos inicios como NO VERI*FACTU sin un fin por medio",
                        detalle=(
                            "Falta el evento 02 que cierra el periodo anterior, o se "
                            "perdió por el camino."
                        ),
                        norma=NORMA_EVENTOS,
                        referencia=e.referencia,
                        orden=e.orden,
                    )
                )
            abierto = True
        elif tipo == "02":
            if not abierto:
                hallazgos.append(
                    Hallazgo(
                        regla="RRSIF027",
                        severidad=Severidad.AVISO,
                        titulo="Fin como NO VERI*FACTU sin inicio previo",
                        detalle=(
                            "Puede ser correcto si el inicio está en un fichero anterior; "
                            "si no, falta el evento 01."
                        ),
                        norma=NORMA_EVENTOS,
                        referencia=e.referencia,
                        orden=e.orden,
                    )
                )
            abierto = False
    return hallazgos


def resumen_presente(eventos: list[Evento]) -> list[Hallazgo]:
    """RRSIF028 — debe haber registro resumen (tipo 10).

    La AEAT lo pide cada 6 horas de operación y antes de apagar. Comprobar la cadencia
    exacta requiere saber cuándo estuvo operativo el sistema, que no se deduce del
    fichero; por eso esto es `INCOMPLETO` y no `ERROR`: señala dónde mirar sin
    afirmar un incumplimiento que no se puede demostrar aquí.
    """
    if not eventos:
        return []
    if any((e.tipo_evento or "").strip() == "10" for e in eventos):
        return []
    return [
        Hallazgo(
            regla="RRSIF028",
            severidad=Severidad.INCOMPLETO,
            titulo="No hay ningún registro resumen de eventos",
            detalle=(
                f"Ninguno de los {len(eventos)} eventos es de tipo 10. El resumen se "
                "genera cada 6 horas de funcionamiento y antes de cada parada.\n"
                "Si este fichero es un tramo corto puede ser correcto; comprueba el "
                "periodo completo."
            ),
            norma="FAQ AEAT — registro de eventos: registro resumen",
            referencia=eventos[0].referencia,
            orden=eventos[0].orden,
        )
    ]


REGLAS = (
    tipo_evento_valido,
    huella_de_evento_correcta,
    formato_huella_evento,
    cadena_de_eventos_continua,
    primer_evento_coherente,
    evento_firmado,
    datos_propios_coherentes,
    ciclo_no_verifactu,
    resumen_presente,
)
