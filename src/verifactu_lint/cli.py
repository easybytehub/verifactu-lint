"""La interfaz de línea de comandos.

**El código de salida es la parte que importa.** Quien mete esto en su CI necesita
que un incumplimiento rompa la build: `1` cuando hay errores, `0` cuando no. Los
avisos y lo indeterminado no fallan por defecto, porque una herramienta que rompe la
build por algo que no ha podido determinar se desactiva la misma semana. `--estricto`
está para quien quiera lo contrario, y es su decisión, no la nuestra.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from verifactu_lint import __version__
from verifactu_lint.hallazgos import Hallazgo, Informe
from verifactu_lint.registros import ErrorDeLectura, lee, lee_eventos
from verifactu_lint.reglas import audita, audita_eventos
from verifactu_lint.salida import como_json, como_sarif, texto

EPILOGO = """\
verifactu-lint audita registros de facturación y de evento YA EMITIDOS. No genera
facturas, no las firma y no las remite a la AEAT: es una herramienta de sólo lectura
y no constituye un sistema informático de facturación.

Cada fichero se audita por separado y detectando qué contiene: los registros de
facturación y los de evento forman cadenas de huellas independientes.

Un resultado sin errores no es una declaración responsable ni acredita conformidad
con el RD 1007/2023. Esa declaración la emite el productor del SIF, bajo su
responsabilidad.
"""


def _argumentos(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="verifactu-lint",
        description=(
            "Audita registros de facturación contra el RRSIF "
            "(RD 1007/2023 y Orden HAC/1177/2024)."
        ),
        epilog=EPILOGO,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("ficheros", nargs="+", type=Path, help="ficheros XML de registros")
    parser.add_argument(
        "--formato",
        choices=("texto", "json", "sarif"),
        default="texto",
        help="formato de salida (por defecto: texto)",
    )
    parser.add_argument(
        "--estricto",
        action="store_true",
        help="salir con código 1 también si hay avisos",
    )
    parser.add_argument("--sin-color", action="store_true", help="desactiva el color")
    parser.add_argument("--version", action="version", version=f"verifactu-lint {__version__}")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _argumentos(argv)

    hallazgos: list[Hallazgo] = []
    analizados = 0
    ficheros_leidos: list[str] = []
    # **Un fichero sin registros no es un fichero conforme.** Es, casi siempre, el
    # fichero equivocado — otro XML, una exportación con envoltorio distinto, una
    # ruta mal escrita. Decir «sin hallazgos» y salir con 0 ahí es la peor respuesta
    # posible: indistinguible de un fichero correcto para quien mira el código de
    # salida en su CI. Se lleva la cuenta para poder distinguirlo al final.
    sin_registros: list[str] = []

    for ruta in args.ficheros:
        # Se detecta qué contiene el fichero en vez de pedírselo al usuario con un
        # flag: el XML ya lo dice, y un flag mal puesto auditaría eventos con las
        # reglas de facturación y produciría un informe sin sentido.
        try:
            registros = lee(ruta)
            eventos = lee_eventos(ruta)
        except ErrorDeLectura as exc:
            print(f"verifactu-lint: {exc}", file=sys.stderr)
            return 2

        if not registros and not eventos:
            print(
                f"verifactu-lint: {ruta}: no contiene RegistroAlta, RegistroAnulacion "
                "ni RegistroEvento",
                file=sys.stderr,
            )
            sin_registros.append(str(ruta))
            continue

        # Cada fichero se audita como su propia cadena, y dentro de él la de
        # facturación y la de eventos por separado: son independientes, y mezclarlas
        # produciría roturas de encadenamiento inventadas.
        for informe_parcial in (
            audita(registros, fichero=str(ruta)) if registros else None,
            audita_eventos(eventos, fichero=str(ruta)) if eventos else None,
        ):
            if informe_parcial is None:
                continue
            hallazgos.extend(informe_parcial.hallazgos)
            analizados += informe_parcial.registros_analizados
        ficheros_leidos.append(str(ruta))

    informe = Informe(
        hallazgos=hallazgos,
        registros_analizados=analizados,
        fichero=", ".join(ficheros_leidos),
    )

    if args.formato == "json":
        print(como_json(informe))
    elif args.formato == "sarif":
        print(como_sarif(informe, __version__))
    else:
        print(texto(informe, color=not args.sin_color and sys.stdout.isatty()))

    if informe.errores:
        return 1
    if args.estricto and informe.avisos:
        return 1
    # Nada auditado y algún fichero ilegible como registros: eso es un error de uso,
    # no un resultado limpio.
    if sin_registros and not ficheros_leidos:
        print(
            "verifactu-lint: ningún fichero contenía registros que auditar.",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
