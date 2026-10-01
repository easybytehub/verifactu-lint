"""Reglas sobre el desglose de impuestos y su cuadre con los totales.

**Éstas son las que ningún XSD puede hacer.** Un esquema comprueba que
`ImporteTotal` sea un número con dos decimales; no puede sumar las líneas del
desglose y ver que no dan eso. La AEAT sí lo comprueba, con un margen de ±10 € y
con consecuencias distintas según dónde esté el descuadre: la cuota de una línea
fuera de margen se **rechaza** (1142); los totales descuadrados se **aceptan con
error admisible** (2005, 2006), que deja el registro dentro pero pendiente de
subsanar.

Hay además una consecuencia que hace estos cuadres especialmente valiosos aquí:
`CuotaTotal` e `ImporteTotal` **entran en el cálculo de la huella**. Un desglose que
no cuadra produce un registro con la huella formalmente correcta y el contenido
inconsistente — encadenado, íntegro y equivocado.

Los códigos citados en cada regla son los del *Listado de códigos de error* de la
AEAT (`errores.properties`), y las condiciones, las de su documento *Validaciones y
errores* v1.2.2, para que un hallazgo se pueda contrastar contra lo que diría su
validador.
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
# medio céntimo, así que un céntimo por línea absorbe el redondeo legítimo. Por debajo
# de este umbral no se dice nada.
TOLERANCIA_LINEA = Decimal("0.01")

# El margen con que valida la AEAT los cuadres: ±10,00 € (Validaciones v1.2.2, §15.7,
# §16 y §17). Entre la tolerancia de redondeo y este margen el registro pasa, y lo que
# hay es un aviso: algo no sale de la aritmética, pero la AEAT no lo va a marcar.
MARGEN_AEAT = Decimal("10.00")

NORMA_VALIDACIONES = "Validaciones y errores AEAT v1.2.2"

# Regímenes en los que la AEAT no cuadra CuotaTotal ni ImporteTotal con el desglose
# (§16 y §17): REBU (03), agencias de viajes (05), grupo de entidades avanzado (06),
# operaciones sujetas a IPSI/IGIC (08) y prestaciones de agencias de viajes en nombre
# y por cuenta ajena (09). En ellos los totales no salen de las líneas por diseño.
REGIMENES_SIN_CUADRE = frozenset({"03", "05", "06", "08", "09"})


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


def _limpio(valor: str | None) -> str:
    return (valor or "").strip().upper()


def _es_s1(d: DetalleDesglose) -> bool:
    """La línea es sujeta y no exenta sin inversión: la única que repercute cuota.

    Una línea sin calificación ni exención no es válida, pero tampoco hay base para
    suponerla otra cosa: se trata como S1, que es lo que comprobaba la versión anterior.
    """
    calificacion = _limpio(d.calificacion)
    return calificacion == "S1" or (not calificacion and not _limpio(d.operacion_exenta))


def _cuota_exenta_de_cuadre(r: Registro) -> bool:
    """§15.7 no cuadra la cuota en las rectificativas por diferencias ni en R2/R3."""
    return _limpio(r.tipo_rectificativa) == "I" or _limpio(r.tipo_factura) in {"R2", "R3"}


def _regimen_sin_cuadre(r: Registro) -> str | None:
    for d in r.desglose:
        clave = _limpio(d.clave_regimen)
        if clave in REGIMENES_SIN_CUADRE:
            return clave
    return None


def _severidad_del_total(diferencia: Decimal) -> Severidad:
    return Severidad.ERROR if abs(diferencia) > MARGEN_AEAT else Severidad.AVISO


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

    Es el error **2006** del listado de la AEAT, que es **admisible**: con más de 10 €
    de diferencia el registro se acepta con error y hay que subsanarlo; por debajo, la
    AEAT no dice nada y aquí sale como aviso. No se aplica en los regímenes 03, 05,
    06, 08 y 09 (§16).
    """
    hallazgos: list[Hallazgo] = []
    for r in registros:
        if r.tipo != "alta" or not r.desglose or _regimen_sin_cuadre(r):
            continue
        declarada = _numero(r.cuota_total)
        if declarada is None:
            continue
        cuotas = _suma(r.desglose, "cuota_repercutida")
        recargos = _suma(r.desglose, "cuota_recargo")
        if cuotas is None or recargos is None:
            continue

        esperada = cuotas + recargos
        diferencia = declarada - esperada
        if abs(diferencia) <= TOLERANCIA_LINEA * len(r.desglose):
            continue
        severidad = _severidad_del_total(diferencia)
        consecuencia = (
            "Supera el margen de ±10 € de la AEAT: el registro se acepta con el error "
            "admisible 2006, queda registrado y hay que subsanarlo."
            if severidad is Severidad.ERROR
            else "Está dentro del margen de ±10 € con que valida la AEAT, que no lo "
            "marcará; pero el total no sale de sus líneas."
        )
        hallazgos.append(
            Hallazgo(
                regla="RRSIF041",
                severidad=severidad,
                titulo="CuotaTotal no cuadra con el desglose",
                detalle=(
                    f"Declarada: {declarada}\n"
                    f"Suma del desglose: {esperada} "
                    f"(cuotas {cuotas} + recargos {recargos})\n"
                    f"Diferencia: {diferencia}\n"
                    f"{consecuencia} Y como CuotaTotal entra en la huella, el registro "
                    "queda encadenado con un total que sus propias líneas no sostienen."
                ),
                norma=f"Códigos de error AEAT — 2006; {NORMA_VALIDACIONES}, §16",
                referencia=r.referencia,
                orden=r.orden,
            )
        )
    return hallazgos


def importe_total_cuadra(registros: list[Registro]) -> list[Hallazgo]:
    """RRSIF042 — `ImporteTotal` = Σ bases + Σ cuotas + Σ recargos.

    Errores **2005** (admisible) y **1210** del listado de la AEAT. Mismo margen y
    mismas excepciones de régimen que RRSIF041 (§17).
    """
    hallazgos: list[Hallazgo] = []
    for r in registros:
        if r.tipo != "alta" or not r.desglose or _regimen_sin_cuadre(r):
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
        diferencia = declarado - esperado
        if abs(diferencia) <= TOLERANCIA_LINEA * len(r.desglose):
            continue
        severidad = _severidad_del_total(diferencia)
        consecuencia = (
            "Supera el margen de ±10 € de la AEAT: el registro se acepta con el error "
            "admisible 2005, queda registrado y hay que subsanarlo."
            if severidad is Severidad.ERROR
            else "Está dentro del margen de ±10 € con que valida la AEAT, que no lo "
            "marcará. Si la diferencia son suplidos o retenciones, no van en "
            "ImporteTotal (FAQ desarrolladores, ap. 20)."
        )
        hallazgos.append(
            Hallazgo(
                regla="RRSIF042",
                severidad=severidad,
                titulo="ImporteTotal no cuadra con el desglose",
                detalle=(
                    f"Declarado: {declarado}\n"
                    f"Suma del desglose: {esperado} "
                    f"(bases {bases} + cuotas {cuotas} + recargos {recargos})\n"
                    f"Diferencia: {diferencia}\n"
                    f"{consecuencia} ImporteTotal entra además en el cálculo de la huella."
                ),
                norma=f"Códigos de error AEAT — 2005 y 1210; {NORMA_VALIDACIONES}, §17",
                referencia=r.referencia,
                orden=r.orden,
            )
        )
    return hallazgos


def cuota_de_la_linea_cuadra(registros: list[Registro]) -> list[Hallazgo]:
    """RRSIF043 — en S1, cuota repercutida = base por tipo impositivo.

    Es el error **1142**, que la AEAT aplica con ±10 € de margen y sólo a líneas S1,
    sobre `BaseImponibleACoste` cuando está informada, y nunca en las rectificativas
    por diferencias ni en R2/R3 (§15.7). Una línea S1 sin tipo o sin cuota es el error
    **1208** (**1209** con base a coste).

    Los desvíos dentro del margen se **agregan** en un solo aviso: un sistema que
    redondea artículo a artículo los tiene en casi todas sus líneas, y un aviso por
    línea enterraría el informe.
    """
    hallazgos: list[Hallazgo] = []
    dentro_del_margen: list[tuple[Registro, DetalleDesglose, str, Decimal]] = []
    for r in registros:
        if r.tipo != "alta":
            continue
        for d in r.desglose:
            if not _es_s1(d):
                continue
            base_a_coste = _numero(d.base_a_coste)
            tipo = _numero(d.tipo_impositivo)
            cuota = _numero(d.cuota_repercutida)

            if _limpio(d.calificacion) == "S1" and (tipo is None or cuota is None):
                faltan = [
                    nombre
                    for nombre, valor in (("TipoImpositivo", d.tipo_impositivo),
                                          ("CuotaRepercutida", d.cuota_repercutida))
                    if valor is None or not valor.strip()
                ]
                if faltan:
                    codigo = "1209" if base_a_coste is not None else "1208"
                    hallazgos.append(
                        Hallazgo(
                            regla="RRSIF043",
                            severidad=Severidad.ERROR,
                            titulo="Una línea S1 sin " + " ni ".join(faltan),
                            detalle=(
                                "En una operación sujeta y no exenta sin inversión, "
                                "TipoImpositivo y CuotaRepercutida son obligatorios.\n"
                                f"La AEAT rechaza el registro con el error {codigo}."
                            ),
                            norma=f"Códigos de error AEAT — {codigo}",
                            referencia=_referencia_linea(r, d),
                            orden=r.orden,
                        )
                    )
                    continue

            if _cuota_exenta_de_cuadre(r):
                continue
            base = base_a_coste if base_a_coste is not None else _numero(d.base)
            if base is None or tipo is None or cuota is None:
                continue

            esperada = base * tipo / Decimal("100")
            diferencia = cuota - esperada
            if abs(diferencia) <= TOLERANCIA_LINEA:
                continue
            etiqueta = "Base a coste" if base_a_coste is not None else "Base"
            calculo = (
                f"{etiqueta} {base} por {tipo}% son "
                f"{esperada.quantize(Decimal('0.01'))}, y se declara {cuota}."
            )
            if abs(diferencia) > MARGEN_AEAT:
                hallazgos.append(
                    Hallazgo(
                        regla="RRSIF043",
                        severidad=Severidad.ERROR,
                        titulo="La cuota de la línea no sale de su base y su tipo",
                        detalle=(
                            f"{calculo}\nLa diferencia supera el margen de ±10 € y la "
                            "AEAT rechaza el registro con el error 1142."
                        ),
                        norma=f"Códigos de error AEAT — 1142; {NORMA_VALIDACIONES}, §15.7",
                        referencia=_referencia_linea(r, d),
                        orden=r.orden,
                    )
                )
            else:
                dentro_del_margen.append((r, d, calculo, diferencia))

    if dentro_del_margen:
        hallazgos.append(_desvios_dentro_del_margen(dentro_del_margen))
    return hallazgos


def _desvios_dentro_del_margen(
    desvios: list[tuple[Registro, DetalleDesglose, str, Decimal]],
) -> Hallazgo:
    r, d, calculo, _ = desvios[0]
    explicacion = (
        "La AEAT lo admite (margen de ±10 €). Suele ser una cuota calculada artículo a "
        "artículo y sumada después: es legítimo, pero conviene que sea una decisión y "
        "no un accidente de redondeo."
    )
    if len(desvios) == 1:
        titulo = "La cuota de la línea se desvía de su base por su tipo"
        detalle = f"{calculo}\n{explicacion}"
    else:
        mayor = max(desvios, key=lambda x: abs(x[3]))
        registros_afectados = len({x[0].orden for x in desvios})
        ejemplos = "\n".join(f"  {_referencia_linea(x[0], x[1])}: {x[2]}" for x in desvios[:5])
        resto = f"\n  … y {len(desvios) - 5} más" if len(desvios) > 5 else ""
        titulo = (
            f"La cuota se desvía de base por tipo en {len(desvios)} líneas "
            f"de {registros_afectados} registros"
        )
        detalle = (
            f"El mayor desvío es de {abs(mayor[3]).quantize(Decimal('0.01'))} € "
            f"({_referencia_linea(mayor[0], mayor[1])}).\n{ejemplos}{resto}\n{explicacion}"
        )
    return Hallazgo(
        regla="RRSIF043",
        severidad=Severidad.AVISO,
        titulo=titulo,
        detalle=detalle,
        norma=f"{NORMA_VALIDACIONES}, §15.7",
        referencia=_referencia_linea(r, d),
        orden=r.orden,
    )


def signos_coherentes(registros: list[Registro]) -> list[Hallazgo]:
    """RRSIF044 — en S1, la base y la cuota de una línea llevan el mismo signo.

    Error **1143**, o **1140** cuando hay base a coste, que es entonces la que se
    compara. Mismo alcance que el cuadre de la cuota (§15.7): sólo S1, y ni en las
    rectificativas por diferencias ni en R2/R3, donde un signo cruzado puede ser la
    propia corrección. Una base negativa con cuota positiva es el patrón de un abono
    a medio hacer: alguien invirtió el signo de un campo y no del otro.
    """
    hallazgos: list[Hallazgo] = []
    for r in registros:
        if r.tipo != "alta" or _cuota_exenta_de_cuadre(r):
            continue
        for d in r.desglose:
            if not _es_s1(d):
                continue
            if _numero(d.base_a_coste) is not None:
                campo, etiqueta, codigo = "base_a_coste", "BaseImponibleACoste", "1140"
            else:
                campo, etiqueta, codigo = "base", "BaseImponibleOimporteNoSujeto", "1143"
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
    """RRSIF046 — sólo una línea S1 repercute cuota.

    Es el error **1207** («la CuotaRepercutida solo podrá ser distinta de 0 si
    CalificacionOperacion es S1»), con su concreción para cada caso: **1198** en la
    inversión del sujeto pasivo (S2), donde TipoImpositivo y CuotaRepercutida han de
    valer 0; **1237** en lo no sujeto con IVA, y **1238** en lo exento, donde ni el
    tipo ni la cuota se informan. Hasta 0.4.0 salía como aviso porque no se había
    localizado el código; el listado oficial lo tipifica como rechazo.
    """
    hallazgos: list[Hallazgo] = []
    for r in registros:
        if r.tipo != "alta":
            continue
        for d in r.desglose:
            cuota = _numero(d.cuota_repercutida)
            tipo = _numero(d.tipo_impositivo)
            con_cuota = cuota is not None and cuota != 0
            exenta = _limpio(d.operacion_exenta)
            calificacion = _limpio(d.calificacion)
            iva = _limpio(d.impuesto) in {"", "01"}

            if exenta:
                informados = (d.tipo_impositivo, d.cuota_repercutida)
                if not any(v is not None and v.strip() for v in informados):
                    continue
                motivo = f"la operación está exenta ({exenta}): no se informa tipo ni cuota"
                codigo = "1238"
            elif calificacion in {"N1", "N2"}:
                informados = (d.tipo_impositivo, d.cuota_repercutida)
                if iva and any(v is not None and v.strip() for v in informados):
                    codigo = "1237"
                    motivo = (
                        f"la operación no está sujeta ({calificacion}) y el impuesto es "
                        "IVA: no se informa tipo ni cuota"
                    )
                elif con_cuota:
                    codigo = "1207"
                    motivo = f"la operación no está sujeta ({calificacion})"
                else:
                    continue
            elif calificacion == "S2":
                if not con_cuota and not (tipo is not None and tipo != 0):
                    continue
                motivo = (
                    "hay inversión del sujeto pasivo (S2): repercute el destinatario, y "
                    "TipoImpositivo y CuotaRepercutida van a 0"
                )
                codigo = "1198"
            else:
                continue

            hallazgos.append(
                Hallazgo(
                    regla="RRSIF046",
                    severidad=Severidad.ERROR,
                    titulo="Tipo o cuota en una operación que no repercute",
                    detalle=(
                        f"TipoImpositivo: {d.tipo_impositivo or '—'} · "
                        f"CuotaRepercutida: {d.cuota_repercutida or '—'}, y {motivo}.\n"
                        f"La AEAT rechaza el registro con el error {codigo}. Revisa si la "
                        "calificación es la correcta o si el tipo y la cuota sobran."
                    ),
                    norma=f"Códigos de error AEAT — {codigo}; {NORMA_VALIDACIONES}, §15.7",
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
    """RRSIF049 — F1, F3 y R1-R4 llevan destinatario; F2 y R5, no.

    Errores **1189** y **1190**: la regla corta en los dos sentidos (Validaciones
    v1.2.2, §13). Una simplificada con `Destinatarios` no es una simplificada más
    completa, es un registro que la AEAT rechaza.
    """
    con_destinatario = {"F1", "F3", "R1", "R2", "R3", "R4"}
    sin_destinatario = {"F2", "R5"}
    hallazgos: list[Hallazgo] = []
    for r in registros:
        if r.tipo != "alta":
            continue
        tipo = _limpio(r.tipo_factura)
        if tipo in con_destinatario and r.destinatarios == 0:
            hallazgos.append(
                Hallazgo(
                    regla="RRSIF049",
                    severidad=Severidad.ERROR,
                    titulo=f"Una factura {tipo} sin destinatario",
                    detalle=(
                        "El bloque `Destinatarios` es obligatorio para F1, F3, R1, R2, R3 "
                        "y R4. Sólo las simplificadas (F2, R5) van sin él.\n"
                        "La AEAT rechaza el registro con el error 1189."
                    ),
                    norma=f"Códigos de error AEAT — 1189; {NORMA_VALIDACIONES}, §13",
                    referencia=r.referencia,
                    orden=r.orden,
                )
            )
        elif tipo in sin_destinatario and r.destinatarios > 0:
            hallazgos.append(
                Hallazgo(
                    regla="RRSIF049",
                    severidad=Severidad.ERROR,
                    titulo=f"Una factura {tipo} con destinatario",
                    detalle=(
                        "F2 y R5 no pueden llevar el bloque `Destinatarios`. Si la factura "
                        "identifica al destinatario no es simplificada: es una F1 (o la F3 "
                        "que sustituye a la simplificada).\n"
                        "La AEAT rechaza el registro con el error 1190."
                    ),
                    norma=f"Códigos de error AEAT — 1190; {NORMA_VALIDACIONES}, §13",
                    referencia=r.referencia,
                    orden=r.orden,
                )
            )
    return hallazgos


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
