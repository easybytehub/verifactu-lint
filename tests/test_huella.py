"""Los tres vectores oficiales de la AEAT, y lo que se deduce de ellos.

Los casos 1, 2 y 3 son literalmente el apartado 6 del documento *Detalle de las
especificaciones técnicas para generación de la huella o hash de los registros de
facturación* (AEAT, v0.1.2, 27/08/2024): mismos datos de entrada, misma cadena
intermedia, misma huella de salida.

**Se comprueba la cadena intermedia además de la huella, y no es redundante.** Si
sólo se comparase el SHA-256, un fallo diría «no coincide» y nada más; comparando
primero la cadena, el fallo señala el campo exacto que se construyó mal. En un
formato donde un `&` de más produce una huella igual de bien formada pero
incorrecta, esa diferencia es la que hace que un fallo sea diagnosticable.
"""

from __future__ import annotations

from verifactu_lint.huella import (
    CAMPOS_ALTA,
    CAMPOS_ANULACION,
    CAMPOS_EVENTO,
    cadena_canonica,
    huella,
    huella_alta,
    huella_anulacion,
    normaliza,
    variantes_numericas,
)

# Caso 1 del documento oficial: primer registro de alta de un SIF, sin huella anterior.
CASO_1_CADENA = (
    "IDEmisorFactura=89890001K"
    "&NumSerieFactura=12345678/G33"
    "&FechaExpedicionFactura=01-01-2024"
    "&TipoFactura=F1"
    "&CuotaTotal=12.35"
    "&ImporteTotal=123.45"
    "&Huella="
    "&FechaHoraHusoGenRegistro=2024-01-01T19:20:30+01:00"
)
CASO_1_HUELLA = "3C464DAF61ACB827C65FDA19F352A4E3BDC2C640E9E9FC4CC058073F38F12F60"

# Caso 2: alta con registro anterior. La huella del caso 1 entra como campo `Huella`.
CASO_2_CADENA = (
    "IDEmisorFactura=89890001K"
    "&NumSerieFactura=12345679/G34"
    "&FechaExpedicionFactura=01-01-2024"
    "&TipoFactura=F1"
    "&CuotaTotal=12.35"
    "&ImporteTotal=123.45"
    f"&Huella={CASO_1_HUELLA}"
    "&FechaHoraHusoGenRegistro=2024-01-01T19:20:35+01:00"
)
CASO_2_HUELLA = "F7B94CFD8924EDFF273501B01EE5153E4CE8F259766F88CF6ACB8935802A2B97"

# Caso 3: anulación encadenada al caso 2. Cinco campos, no ocho.
CASO_3_CADENA = (
    "IDEmisorFacturaAnulada=89890001K"
    "&NumSerieFacturaAnulada=12345679/G34"
    "&FechaExpedicionFacturaAnulada=01-01-2024"
    f"&Huella={CASO_2_HUELLA}"
    "&FechaHoraHusoGenRegistro=2024-01-01T19:20:40+01:00"
)
CASO_3_HUELLA = "177547C0D57AC74748561D054A9CEC14B4C4EA23D1BEFD6F2E69E3A388F90C68"


class TestVectoresOficiales:
    def test_caso_1_cadena(self) -> None:
        cadena = cadena_canonica(
            CAMPOS_ALTA,
            [
                "89890001K",
                "12345678/G33",
                "01-01-2024",
                "F1",
                "12.35",
                "123.45",
                None,  # primer registro: no hay huella anterior
                "2024-01-01T19:20:30+01:00",
            ],
        )
        assert cadena == CASO_1_CADENA

    def test_caso_1_huella(self) -> None:
        assert huella(CASO_1_CADENA) == CASO_1_HUELLA

    def test_caso_1_extremo_a_extremo(self) -> None:
        assert (
            huella_alta(
                "89890001K",
                "12345678/G33",
                "01-01-2024",
                "F1",
                "12.35",
                "123.45",
                None,
                "2024-01-01T19:20:30+01:00",
            )
            == CASO_1_HUELLA
        )

    def test_caso_2_cadena(self) -> None:
        cadena = cadena_canonica(
            CAMPOS_ALTA,
            [
                "89890001K",
                "12345679/G34",
                "01-01-2024",
                "F1",
                "12.35",
                "123.45",
                CASO_1_HUELLA,
                "2024-01-01T19:20:35+01:00",
            ],
        )
        assert cadena == CASO_2_CADENA

    def test_caso_2_extremo_a_extremo(self) -> None:
        assert (
            huella_alta(
                "89890001K",
                "12345679/G34",
                "01-01-2024",
                "F1",
                "12.35",
                "123.45",
                CASO_1_HUELLA,
                "2024-01-01T19:20:35+01:00",
            )
            == CASO_2_HUELLA
        )

    def test_caso_3_cadena(self) -> None:
        cadena = cadena_canonica(
            CAMPOS_ANULACION,
            [
                "89890001K",
                "12345679/G34",
                "01-01-2024",
                CASO_2_HUELLA,
                "2024-01-01T19:20:40+01:00",
            ],
        )
        assert cadena == CASO_3_CADENA

    def test_caso_3_extremo_a_extremo(self) -> None:
        assert (
            huella_anulacion(
                "89890001K",
                "12345679/G34",
                "01-01-2024",
                CASO_2_HUELLA,
                "2024-01-01T19:20:40+01:00",
            )
            == CASO_3_HUELLA
        )

    def test_el_encadenamiento_de_los_tres_casos_es_consistente(self) -> None:
        """Los tres vectores son una cadena real: 1 → 2 → 3.

        Comprobarlo junto, y no sólo por separado, es la prueba de que el
        encadenamiento se entiende igual que lo entiende la AEAT.
        """
        h1 = huella_alta(
            "89890001K", "12345678/G33", "01-01-2024", "F1", "12.35", "123.45",
            None, "2024-01-01T19:20:30+01:00",
        )
        h2 = huella_alta(
            "89890001K", "12345679/G34", "01-01-2024", "F1", "12.35", "123.45",
            h1, "2024-01-01T19:20:35+01:00",
        )
        h3 = huella_anulacion(
            "89890001K", "12345679/G34", "01-01-2024", h2,
            "2024-01-01T19:20:40+01:00",
        )
        assert (h1, h2, h3) == (CASO_1_HUELLA, CASO_2_HUELLA, CASO_3_HUELLA)


class TestFormatoDeSalida:
    def test_siempre_64_caracteres(self) -> None:
        assert len(huella("")) == 64

    def test_siempre_mayusculas(self) -> None:
        h = huella("IDEmisorFactura=89890001K")
        assert h == h.upper()

    def test_utf8_no_latin1(self) -> None:
        """La orden fija UTF-8. Con Latin-1 la huella de una eñe sería otra.

        Sin acentos el bug es invisible: sólo aparece con un nombre de serie que
        lleve un carácter no ASCII, es decir, en producción y no en las pruebas.
        """
        cadena = "NumSerieFactura=AÑO/2024"
        esperado = __import__("hashlib").sha256(
            cadena.encode("utf-8")
        ).hexdigest().upper()
        assert huella(cadena) == esperado


class TestNormalizacion:
    def test_recorta_los_extremos(self) -> None:
        assert normaliza("  12345678 / G33  ") == "12345678 / G33"

    def test_conserva_los_espacios_interiores(self) -> None:
        """El ejemplo oficial los conserva, y es lo que distingue `strip` de
        `replace`: recortar los extremos no es limpiar el valor."""
        assert normaliza("  12345678 / G33  ") == "12345678 / G33"

    def test_ausente_y_vacio_son_el_mismo_caso(self) -> None:
        assert normaliza(None) == normaliza("") == ""

    def test_campo_vacio_deja_el_nombre_y_el_igual(self) -> None:
        assert cadena_canonica(("A", "B"), [None, "x"]) == "A=&B=x"

    def test_sin_separador_final(self) -> None:
        """El error silencioso más caro de este formato."""
        cadena = cadena_canonica(("A", "B"), ["1", "2"])
        assert cadena == "A=1&B=2"
        assert not cadena.endswith("&")

    def test_numero_de_valores_desparejado(self) -> None:
        import pytest

        with pytest.raises(ValueError, match="se esperaban 2 valores"):
            cadena_canonica(("A", "B"), ["1"])


class TestVariantesNumericas:
    def test_un_decimal_equivale_a_dos(self) -> None:
        assert "123.10" in variantes_numericas("123.1")
        assert "123.1" in variantes_numericas("123.10")

    def test_incluye_siempre_el_valor_literal(self) -> None:
        assert variantes_numericas("123.1")[0] == "123.1"

    def test_no_inventa_equivalencias_que_cambian_el_importe(self) -> None:
        """`123.456` con un decimal sería `123.5`, que es otro importe."""
        assert "123.5" not in variantes_numericas("123.456")

    def test_valor_no_numerico_se_devuelve_intacto(self) -> None:
        assert variantes_numericas("F1") == ["F1"]

    def test_vacio(self) -> None:
        assert variantes_numericas("") == [""]


class TestCamposDeEvento:
    def test_nif_aparece_dos_veces_y_es_correcto(self) -> None:
        """`SistemaInformatico/NIF` y `ObligadoEmision/NIF` son campos distintos
        con el mismo nombre. Un diccionario perdería uno."""
        assert CAMPOS_EVENTO.count("NIF") == 2
        assert len(CAMPOS_EVENTO) == 9

    def test_nif_e_id_son_excluyentes_en_la_cadena(self) -> None:
        """Ejemplo oficial: `NIF=89890001K&ID=&IdSistemaInformatico=…`"""
        cadena = cadena_canonica(
            CAMPOS_EVENTO,
            [
                "89890001K",
                None,
                "A1",
                "1.0",
                "0001",
                "89890001K",
                "01",
                None,
                "2024-01-01T19:20:30+01:00",
            ],
        )
        assert cadena.startswith("NIF=89890001K&ID=&IdSistemaInformatico=A1")
