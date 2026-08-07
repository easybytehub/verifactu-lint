"""Reglas sobre el desglose de impuestos y su cuadre con los totales.

**Éstas son las que ningún XSD puede hacer.** Un esquema comprueba que
`ImporteTotal` sea un número con dos decimales; no puede sumar las líneas del
desglose y ver que no dan eso. Y la AEAT sí lo comprueba: rechaza el registro con
los errores 1210, 2005 y 2006 de su listado oficial.

Hay además una consecuencia que hace estos cuadres especialmente valiosos aquí:
`CuotaTotal` e `ImporteTotal` **entran en el cálculo de la huella**. Un desglose que
no cuadra produce un registro con la huella formalmente correcta y el contenido
inconsistente — encadenado, íntegro y equivocado.

Los códigos citados en cada regla son los del *Listado de códigos de error* de la
AEAT, para que un hallazgo se pueda contrastar contra lo que diría su validador.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from verifactu_lint.hallazgos import Hallazgo, Severidad
from verifactu_lint.registros import DetalleDesglose, Registro

IMPUESTOS: dict[str, str] = {
    "01": "IVA",
    "02": "IPSI de Ceuta y Melilla",
    "03": "IGIC",
    "05": "Otros",
}

CALIFICACIONES: dict[str, str] = {
    "S1": "sujeta y no exenta, sin inversión del sujeto pasivo",
    "S2": "sujeta y no exenta, con inversión del sujeto pasivo",
    "N1": "no sujeta por los artículos 7, 14 u otros",
    "N2": "no sujeta por reglas de localización",
}

EXENCIONES = frozenset({"E1", "E2", "E3", "E4", "E5", "E6"})

CLAVES_REGIMEN = frozenset(
    {"01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11",
     "14", "15", "17", "18", "19", "20", "21"}
)

# Recargo de equivalencia admitido para cada tipo impositivo vigente. Sale de los
# errores 1160 a 1170, que lo fijan tipo a tipo. Los tipos históricos con su propia
# ventana temporal (el 5 % con 0,5 o 0,62 según el año) no se comprueban aquí: exigen
# saber la fecha de operación y producirían falsos positivos en cuanto se rozara el
# borde de una de esas ventanas.
RECARGO_POR_TIPO: dict[Decimal, set[Decimal]] = {
    Decimal("21"): {Decimal("5.2"), Decimal("1.75")},
    Decimal("10"): {Decimal("1.4")},
    Decimal("4"): {Decimal("0.5")},
}

# Un céntimo por línea implicada. El redondeo de cada línea puede desviar como mucho
# medio céntimo, así que un céntimo por línea absorbe el redondeo legítimo sin tragarse
# un error real: equivocarse en una cuota da diferencias de euros, no de céntimos.
TOLERANCIA_LINEA = Decimal("0.01")


def _numero(valor: str | None) -> Decimal | None:
    if valor is None or not valor.strip():
        return None
    try:
        return Decimal(valor.strip())
    except (InvalidOperation, ValueError):
        return None


def _suma(detalles: tuple[DetalleDesglose, ...], campo: str) -> Decimal | None:
    """Suma un campo de todas las líneas, o `None` si alguna no es un número.

    Devolver `None` en vez de saltarse la línea es deliberado: una suma a la que le
    falta un sumando cuadraría mal y el hallazgo culparía al total, que está bien.
    """
    total = Decimal("0")
    for d in detalles:
        crudo = getattr(d, campo)
        if crudo is None or not str(crudo).strip():
            continue
        numero = _numero(crudo)
        if numero is None:
            return None
        total += numero
    return total


def _referencia_linea(r: Registro, d: DetalleDesglose) -> str:
    return f"{r.referencia} · desglose línea {d.orden + 1}"


def hay_desglose(registros: list[Registro]) -> list[Hallazgo]:
    """RRSIF040 — un registro de alta lleva desglose."""
    return [
        Hallazgo(
            regla="RRSIF040",
            severidad=Severidad.ERROR,
            titulo="El registro de alta no tiene desglose",
            detalle=(
                "`Desglose` es obligatorio en el registro de alta: es donde constan la "
                "base, el tipo y la cuota que sostienen los totales."
            ),
            norma="Orden HAC/1177/2024, anexo — bloque Desglose",
            referencia=r.referencia,
            orden=r.orden,
        )
        for r in registros
        if r.tipo == "alta" and not r.desglose
    ]


def cuota_total_cuadra(registros: list[Registro]) -> list[Hallazgo]:
    """RRSIF041 — `CuotaTotal` = Σ cuotas repercutidas + Σ recargos.

    Es el error **2006** del listado de la AEAT.
    """
    hallazgos: list[Hallazgo] = []
    for r in registros:
        if r.tipo != "alta" or not r.desglose:
            continue
        declarada = _numero(r.cuota_total)
        if declarada is None:
            continue
        cuotas = _suma(r.desglose, "cuota_repercutida")
        recargos = _suma(r.desglose, "cuota_recargo")
        if cuotas is None or recargos is None:
            continue

        esperada = cuotas + recargos
        margen = TOLERANCIA_LINEA * len(r.desglose)
        if abs(declarada - esperada) <= margen:
            continue
        hallazgos.append(
            Hallazgo(
                regla="RRSIF041",
                severidad=Severidad.ERROR,
                titulo="CuotaTotal no cuadra con el desglose",
                detalle=(
                    f"Declarada: {declarada}\n"
                    f"Suma del desglose: {esperada} "
                    f"(cuotas {cuotas} + recargos {recargos})\n"
                    f"Diferencia: {declarada - esperada}\n"
                    "La AEAT rechaza el registro con el error 2006. Y como CuotaTotal "
                    "entra en la huella, el registro queda encadenado con un total que "
                    "sus propias líneas no sostienen."
                ),
                norma="Códigos de error AEAT — 2006",
                referencia=r.referencia,
                orden=r.orden,
            )
        )
    return hallazgos


def importe_total_cuadra(registros: list[Registro]) -> list[Hallazgo]:
    """RRSIF042 — `ImporteTotal` = Σ bases + Σ cuotas + Σ recargos.

    Errores **1210** y **2005** del listado de la AEAT.
    """
    hallazgos: list[Hallazgo] = []
    for r in registros:
        if r.tipo != "alta" or not r.desglose:
            continue
        declarado = _numero(r.importe_total)
        if declarado is None:
            continue
        bases = _suma(r.desglose, "base")
        cuotas = _suma(r.desglose, "cuota_repercutida")
        recargos = _suma(r.desglose, "cuota_recargo")
        if bases is None or cuotas is None or recargos is None:
            continue

        esperado = bases + cuotas + recargos
        margen = TOLERANCIA_LINEA * len(r.desglose)
        if abs(declarado - esperado) <= margen:
            continue
        hallazgos.append(
            Hallazgo(
                regla="RRSIF042",
                severidad=Severidad.ERROR,
                titulo="ImporteTotal no cuadra con el desglose",
                detalle=(
                    f"Declarado: {declarado}\n"
                    f"Suma del desglose: {esperado} "
                    f"(bases {bases} + cuotas {cuotas} + recargos {recargos})\n"
                    f"Diferencia: {declarado - esperado}\n"
                    "La AEAT rechaza el registro con los errores 1210 y 2005. "
                    "ImporteTotal entra además en el cálculo de la huella."
                ),
                norma="Códigos de error AEAT — 1210 y 2005",
                referencia=r.referencia,
                orden=r.orden,
            )
        )
    return hallazgos


def cuota_de_la_linea_cuadra(registros: list[Registro]) -> list[Hallazgo]:
    """RRSIF043 — cuota repercutida = base por tipo impositivo.

    Es el error **1142** del listado de la AEAT.
    """
    hallazgos: list[Hallazgo] = []
    for r in registros:
        if r.tipo != "alta":
            continue
        for d in r.desglose:
            base = _numero(d.base)
            tipo = _numero(d.tipo_impositivo)
            cuota = _numero(d.cuota_repercutida)
            if base is None or tipo is None or cuota is None:
                continue

            esperada = base * tipo / Decimal("100")
            if abs(cuota - esperada) <= TOLERANCIA_LINEA:
                continue
            hallazgos.append(
                Hallazgo(
                    regla="RRSIF043",
                    severidad=Severidad.ERROR,
                    titulo="La cuota de la línea no sale de su base y su tipo",
                    detalle=(
                        f"Base {base} por {tipo}% son {esperada.quantize(Decimal('0.01'))}, "
                        f"y se declara {cuota}.\n"
                        "La AEAT rechaza el registro con el error 1142."
                    ),
                    norma="Códigos de error AEAT — 1142",
                    referencia=_referencia_linea(r, d),
                    orden=r.orden,
                )
            )
    return hallazgos


def signos_coherentes(registros: list[Registro]) -> list[Hallazgo]:
    """RRSIF044 — base y cuota de una línea llevan el mismo signo.

    Error **1143** (y **1140** para la base a coste). Una base negativa con cuota
    positiva es el patrón de un abono a medio hacer: alguien invirtió el signo de un
    campo y no del otro.
    """
    hallazgos: list[Hallazgo] = []
    for r in registros:
        if r.tipo != "alta":
            continue
        for d in r.desglose:
            for campo, etiqueta, codigo in (
                ("base", "BaseImponibleOimporteNoSujeto", "1143"),
                ("base_a_coste", "BaseImponibleACoste", "1140"),
            ):
                base = _numero(getattr(d, campo))
                cuota = _numero(d.cuota_repercutida)
                if base is None or cuota is None or not base or not cuota:
                    continue
                if (base > 0) == (cuota > 0):
                    continue
                hallazgos.append(
                    Hallazgo(
                        regla="RRSIF044",
                        severidad=Severidad.ERROR,
                        titulo=f"{etiqueta} y CuotaRepercutida tienen signos distintos",
                        detalle=(
                            f"{etiqueta} es {base} y CuotaRepercutida es {cuota}.\n"
                            f"La AEAT rechaza el registro con el error {codigo}."
                        ),
                        norma=f"Códigos de error AEAT — {codigo}",
                        referencia=_referencia_linea(r, d),
                        orden=r.orden,
                    )
                )
    return hallazgos


def valores_de_lista(registros: list[Registro]) -> list[Hallazgo]:
    """RRSIF045 — `Impuesto`, `ClaveRegimen`, calificación y exención existen.

    Errores **1181** (`CalificacionOperacion`) y **1182** (`OperacionExenta`).
    """
    hallazgos: list[Hallazgo] = []
    for r in registros:
        if r.tipo != "alta":
            continue
        for d in r.desglose:
            comprobaciones = (
                ("Impuesto", d.impuesto, set(IMPUESTOS), "L1"),
                ("ClaveRegimen", d.clave_regimen, CLAVES_REGIMEN, "L8"),
                ("CalificacionOperacion", d.calificacion, set(CALIFICACIONES), "1181"),
                ("OperacionExenta", d.operacion_exenta, EXENCIONES, "1182"),
            )
            for etiqueta, valor, admitidos, referencia_norma in comprobaciones:
                limpio = (valor or "").strip().upper()
                if not limpio or limpio in admitidos:
                    continue
                hallazgos.append(
                    Hallazgo(
                        regla="RRSIF045",
                        severidad=Severidad.ERROR,
                        titulo=f"{etiqueta}={limpio} no está en la lista de valores",
                        detalle="Valores admitidos: " + ", ".join(sorted(admitidos)),
                        norma=f"Orden HAC/1177/2024, anexo — {referencia_norma}",
                        referencia=_referencia_linea(r, d),
                        orden=r.orden,
                    )
                )
    return hallazgos


def exenta_sin_cuota(registros: list[Registro]) -> list[Hallazgo]:
    """RRSIF046 — lo exento y lo no sujeto no repercuten cuota.

    No hay un código de error concreto para esto, y por eso sale como **aviso**: una
    operación exenta o no sujeta no debería llevar cuota repercutida, pero el listado
    de la AEAT no lo tipifica como rechazo y no queremos afirmar más de lo que se
    puede sostener. Lo mismo con `S2`: en la inversión del sujeto pasivo quien
    repercute es el destinatario, no el emisor.
    """
    hallazgos: list[Hallazgo] = []
    for r in registros:
        if r.tipo != "alta":
            continue
        for d in r.desglose:
            cuota = _numero(d.cuota_repercutida)
            if cuota is None or cuota == 0:
                continue
            exenta = (d.operacion_exenta or "").strip().upper()
            calificacion = (d.calificacion or "").strip().upper()

            if exenta:
                motivo = f"la operación está exenta ({exenta})"
            elif calificacion in {"N1", "N2"}:
                motivo = f"la operación no está sujeta ({calificacion})"
            elif calificacion == "S2":
                motivo = "hay inversión del sujeto pasivo (S2) y repercute el destinatario"
            else:
                continue

            hallazgos.append(
                Hallazgo(
                    regla="RRSIF046",
                    severidad=Severidad.AVISO,
                    titulo="Se repercute cuota en una operación que no debería llevarla",
                    detalle=(
                        f"CuotaRepercutida es {cuota} y {motivo}.\n"
                        "Revisa si la calificación es la correcta o si la cuota sobra."
                    ),
                    norma="Orden HAC/1177/2024, anexo — listas L9 (calificación) y L10 (exención)",
                    referencia=_referencia_linea(r, d),
                    orden=r.orden,
                )
            )
    return hallazgos


def recargo_de_equivalencia(registros: list[Registro]) -> list[Hallazgo]:
    """RRSIF047 — el recargo va con su tipo, y el tipo con su recargo.

    Los errores **1160** y **1162** a **1170** fijan qué recargo admite cada tipo
    impositivo. Aquí se comprueban los tipos vigentes; los históricos dependen de la
    fecha de operación y no se afirman.
    """
    hallazgos: list[Hallazgo] = []
    for r in registros:
        if r.tipo != "alta":
            continue
        for d in r.desglose:
            tipo_recargo = _numero(d.tipo_recargo)
            cuota_recargo = _numero(d.cuota_recargo)

            if (tipo_recargo is None) != (cuota_recargo is None):
                falta = (
                    "CuotaRecargoEquivalencia"
                    if cuota_recargo is None
                    else "TipoRecargoEquivalencia"
                )
                hallazgos.append(
                    Hallazgo(
                        regla="RRSIF047",
                        severidad=Severidad.ERROR,
                        titulo=f"Recargo de equivalencia a medias: falta {falta}",
                        detalle=(
                            "El tipo de recargo y su cuota se informan juntos o no se "
                            "informa ninguno."
                        ),
                        norma="Orden HAC/1177/2024, anexo — bloque Desglose",
                        referencia=_referencia_linea(r, d),
                        orden=r.orden,
                    )
                )
                continue

            if tipo_recargo is None:
                continue

            tipo = _numero(d.tipo_impositivo)
            if tipo is None or tipo not in RECARGO_POR_TIPO:
                continue
            admitidos = RECARGO_POR_TIPO[tipo]
            if tipo_recargo in admitidos:
                continue
            hallazgos.append(
                Hallazgo(
                    regla="RRSIF047",
                    severidad=Severidad.ERROR,
                    titulo=f"Recargo {tipo_recargo}% no admitido para un tipo del {tipo}%",
                    detalle=(
                        "Recargos admitidos para ese tipo: "
                        + ", ".join(str(a) for a in sorted(admitidos))
                        + ".\nLa AEAT los fija tipo a tipo en los errores 1160 y 1162-1170."
                    ),
                    norma="Códigos de error AEAT — 1160, 1162-1170",
                    referencia=_referencia_linea(r, d),
                    orden=r.orden,
                )
            )
    return hallazgos


def macrodato_coherente(registros: list[Registro]) -> list[Hallazgo]:
    """RRSIF048 — `Macrodato` marca los importes de ocho cifras.

    Errores **1137**, **1138** y **1139**: sólo admite `S` o `N`, y tiene que valer
    `S` exactamente cuando `ImporteTotal` alcanza ±100.000.000.
    """
    limite = Decimal("100000000")
    hallazgos: list[Hallazgo] = []
    for r in registros:
        if r.tipo != "alta":
            continue
        valor = (r.macrodato or "").strip().upper()
        total = _numero(r.importe_total)

        if valor and valor not in {"S", "N"}:
            hallazgos.append(
                Hallazgo(
                    regla="RRSIF048",
                    severidad=Severidad.ERROR,
                    titulo=f"Macrodato={valor} no es válido",
                    detalle="Sólo admite S o N (error 1137).",
                    norma="Códigos de error AEAT — 1137",
                    referencia=r.referencia,
                    orden=r.orden,
                )
            )
            continue

        if total is None:
            continue
        supera = abs(total) >= limite
        if supera and valor != "S":
            hallazgos.append(
                Hallazgo(
                    regla="RRSIF048",
                    severidad=Severidad.ERROR,
                    titulo="ImporteTotal alcanza los 100.000.000 y Macrodato no vale S",
                    detalle=(
                        f"ImporteTotal es {total}. Cuando iguala o supera ±100.000.000, "
                        "Macrodato debe informarse con S (error 1139)."
                    ),
                    norma="Códigos de error AEAT — 1138 y 1139",
                    referencia=r.referencia,
                    orden=r.orden,
                )
            )
        elif not supera and valor == "S":
            hallazgos.append(
                Hallazgo(
                    regla="RRSIF048",
                    severidad=Severidad.ERROR,
                    titulo="Macrodato=S con un ImporteTotal que no lo alcanza",
                    detalle=(
                        f"ImporteTotal es {total}, por debajo de ±100.000.000. "
                        "Macrodato sólo se informa con S a partir de ese importe "
                        "(error 1138)."
                    ),
                    norma="Códigos de error AEAT — 1138",
                    referencia=r.referencia,
                    orden=r.orden,
                )
            )
    return hallazgos


def destinatario_obligatorio(registros: list[Registro]) -> list[Hallazgo]:
    """RRSIF049 — F1, F3, R1, R2, R3 y R4 llevan destinatario.

    Error **1189**. Las simplificadas (F2, R5) son justamente las que no lo llevan,
    así que la regla distingue en vez de exigirlo siempre.
    """
    con_destinatario = {"F1", "F3", "R1", "R2", "R3", "R4"}
    return [
        Hallazgo(
            regla="RRSIF049",
            severidad=Severidad.ERROR,
            titulo=f"Una factura {(r.tipo_factura or '').strip().upper()} sin destinatario",
            detalle=(
                "El bloque `Destinatarios` es obligatorio para F1, F3, R1, R2, R3 y R4. "
                "Sólo las simplificadas (F2, R5) pueden no llevarlo.\n"
                "La AEAT rechaza el registro con el error 1189."
            ),
            norma="Códigos de error AEAT — 1189",
            referencia=r.referencia,
            orden=r.orden,
        )
        for r in registros
        if r.tipo == "alta"
        and (r.tipo_factura or "").strip().upper() in con_destinatario
        and r.destinatarios == 0
    ]


REGLAS = (
    hay_desglose,
    cuota_total_cuadra,
    importe_total_cuadra,
    cuota_de_la_linea_cuadra,
    signos_coherentes,
    valores_de_lista,
    exenta_sin_cuota,
    recargo_de_equivalencia,
    macrodato_coherente,
    destinatario_obligatorio,
)
