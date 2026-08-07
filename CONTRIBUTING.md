# Contribuir

## Lo más útil que puedes aportar

**Un registro real que esta herramienta juzga mal.** Un falso positivo —algo marcado
como `error` que la AEAT acepta— es el defecto más grave que puede tener un linter de
cumplimiento, porque hace que alguien cambie código correcto y deje de creerse el
resto del informe. Si te encuentras uno, ábrelo como issue con el caso mínimo que lo
reproduce (anonimizado: NIF y números de factura ficticios bastan).

Lo segundo más útil: **un incumplimiento real que no detecta**.

## Entorno

```bash
git clone https://github.com/easybytehub/verifactu-lint
cd verifactu-lint
python -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

Los tres gates, que son los mismos que corren en CI:

```bash
.venv/bin/python -m ruff check .
.venv/bin/python -m mypy
.venv/bin/python -m pytest
```

## Escribir una regla

Una regla es una función `list[Registro] -> list[Hallazgo]`. No hay clase base, ni
registro por decorador, ni sistema de plugins: escribes la función, la añades a la
tupla `REGLAS` de su familia en `src/verifactu_lint/reglas/`, y le pones un test.

Recibe la lista completa y no un registro suelto porque casi todo lo que importa aquí
es relacional —el encadenamiento, la numeración duplicada, cuántas cadenas hay
mezcladas— y una interfaz de uno en uno obligaría a las reglas interesantes a
mantener estado por su cuenta.

Toda regla necesita:

1. **La cita normativa concreta** en el campo `norma`. Sin ella el hallazgo no se
   puede contrastar, y un informe que hay que creerse a ciegas no sirve de nada.
2. **Una severidad justificada.** Si no puedes demostrar el incumplimiento con lo que
   hay en el fichero, es `AVISO` o `INCOMPLETO`, no `ERROR`.
3. **Dos tests como mínimo**: uno con un caso que la dispare y otro con uno que no.
4. **Agregación si puede repetirse.** Una regla que emita un hallazgo por registro
   produce miles de líneas idénticas en un fichero real y hace ilegible el informe.
   Emite uno por campo o por causa, y di cuántos registros afecta.

Los identificadores de regla (`RRSIF0NN`) son estables: no se reutilizan ni se
renumeran, porque la gente los mete en configuraciones y filtros.

## Los vectores oficiales

`tests/test_huella.py` contiene los tres ejemplos del apartado 6 del documento de la
AEAT *Detalle de las especificaciones técnicas para generación de la huella o hash de
los registros de facturación*.

**Esos tests no se tocan.** Si un cambio los rompe, es el cambio el que está mal. Son
lo único que permite a esta herramienta afirmar algo sobre el cumplimiento de otros.

## Workflows

Las acciones se fijan al SHA completo del commit, nunca a una etiqueta: una etiqueta
la puede mover su autor, y el workflow de release sostiene un token capaz de publicar
paquetes. Hay un test que lo comprueba (`tests/test_workflows.py`), así que no hace
falta acordarse.

## Estilo

Los comentarios explican **por qué**, no qué. El qué ya está en el código. Si un
fragmento existe porque una alternativa evidente no funciona, escribe cuál y por qué:
eso es lo que evita que alguien lo «simplifique» dentro de seis meses.
