# Esquemas oficiales

Copias literales de los XSD que publica la AEAT, **sin modificar**. Se usan sólo en
tests, para validar que los ficheros de `ejemplos/` son estructuralmente correctos.

| Fichero | Origen |
|---|---|
| `SuministroLR.xsd` | [AEAT · desarrolladores](https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/tikeV1.0/cont/ws/SuministroLR.xsd) |
| `SuministroInformacion.xsd` | [AEAT · desarrolladores](https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/tikeV1.0/cont/ws/SuministroInformacion.xsd) |
| `EventosSIF.xsd` | [AEAT · desarrolladores](https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/tikeV1.0/cont/ws/EventosSIF.xsd) |
| `xmldsig-core-schema.xsd` | [W3C](https://www.w3.org/TR/xmldsig-core/xmldsig-core-schema.xsd) — lo importan los dos anteriores |

Descargados el **2026-08-07**.

## Por qué están versionados y no se descargan al vuelo

Un esquema que se baja en cada ejecución convierte cualquier cambio de la AEAT en un
fallo sorpresa de CI, en un commit que no tiene nada que ver con él. Y ata la suite a
que un tercero siga sirviendo el mismo fichero en la misma URL: un test que puede
fallar por algo ajeno al código deja de significar nada.

Versionados, actualizarlos es un cambio explícito y revisable en un diff.

## Por qué no se tocan

Son fuente primaria. `xmldsig-core-schema.xsd` está aquí en local porque los esquemas
de la AEAT lo importan por su URL de w3.org; en vez de reescribir esa referencia
—que sería modificar el original— los tests usan un resolver que la sirve desde este
directorio.

## Dos cosas que hay que saber al usarlos

**`RegistroEvento` es el único elemento global de `EventosSIF.xsd`.** La AEAT no
define ningún envoltorio para agrupar varios eventos: cada registro es un documento
completo por sí mismo. Un fichero con más de uno lleva por fuerza un contenedor
propio del fabricante, así que contra el esquema oficial sólo se puede validar cada
registro suelto.

**Validar contra el XSD no es cumplir el reglamento.** `ejemplos/cadena-rota.xml`
valida perfectamente y tiene la cadena de huellas partida; `eventos-con-defectos.xml`
valida y le faltan los datos propios de un evento de exportación. Un esquema
comprueba forma, no coherencia — no sabe calcular un SHA-256 ni conoce el orden de
los registros. Esa diferencia es la razón de ser de esta herramienta.
