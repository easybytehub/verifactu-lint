# Política de seguridad

## Reportar una vulnerabilidad

Usa el [aviso privado de seguridad de GitHub](https://github.com/easybytehub/verifactu-lint/security/advisories/new).
No abras un issue público para esto.

Respuesta inicial en 5 días laborables.

## Qué se considera vulnerabilidad aquí

Esta herramienta lee ficheros XML que su usuario no siempre ha inspeccionado, y se
ejecuta a menudo dentro de un CI. Con lo que interesa especialmente:

- **Agotamiento de recursos** al procesar un XML manipulado. Los documentos con
  DOCTYPE se rechazan antes de parsear precisamente por esto; si encuentras otra
  entrada que cuelgue el proceso o consuma memoria sin límite, es un fallo.
- **Cualquier lectura de fichero, red o ejecución** provocada por el contenido del
  XML. La herramienta no debe abrir nada más que los ficheros que se le pasan por
  argumento.
- **Un falso negativo explotable**: un registro construido para que la herramienta lo
  declare conforme cuando no lo es.

## Qué no es una vulnerabilidad

- Que un informe sin errores no acredite conformidad con el RD 1007/2023. Es
  deliberado y está documentado: esta herramienta no es un sistema informático de
  facturación y no emite declaración responsable de nadie.
- Un falso positivo. Es un defecto serio y nos importa mucho, pero se trata como
  [issue](https://github.com/easybytehub/verifactu-lint/issues) normal, en abierto.

## Alcance

Sólo el código de este repositorio. Las versiones publicadas llevan procedencia
verificable:

```bash
gh attestation verify --owner easybytehub verifactu_lint-*.whl
```

Si esa comprobación falla en un artefacto que dice venir de aquí, repórtalo por el
canal privado.
