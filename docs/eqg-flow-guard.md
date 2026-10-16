# EQG Flow Guard y artefactos privados por corrida

## Alcance

El guardián adapta el detector de duplicación de egress (EgressLink) a un protocolo EQG de eventos y canales. Vigila las transiciones de estado, el propietario y el identificador de corrida, secuencia monotónica, nonces anti-replay, canales autorizados, límites de tamaño y hashes de artefactos. El registro no almacena payloads ni claves.

Estados: INIT → PRECHECK → AUTHORIZED → RUNNING → VERIFYING → PACKAGED; las anomalías llevan a QUARANTINED y los errores operativos pueden llevar a REJECTED. No existe una transición de recuperación silenciosa desde estados terminales.

## Privacidad por corrida

- Cada corrida crea una clave aleatoria AES-256-GCM exclusiva y la guarda en un archivo separado con permisos de propietario (0600 en POSIX).
- report.json y ablation.png se cifran como report.eqg.enc y ablation.eqg.enc. Los artefactos en claro no se conservan en el directorio de salida.
- run_manifest.json sólo contiene versión, identificador aleatorio de corrida y hashes de ciphertext/envelope; no incluye proveedor, backend, resultados, coste, propietario ni datos brutos.
- La clave se vincula al run_id, al propietario local y al identificador de clave. No permite descifrar otra corrida que tenga una clave distinta.
- La clave no debe publicarse, subirse al repositorio ni almacenarse junto a los ciphertexts en un entorno compartido. Entregar el archivo de clave al usuario es un paso de entrega separado.
- Descifrado: python -m ddqpu.privacy decrypt --input report.eqg.enc --key-file RUTA/run.key --output /ruta/privada/report.json.

La identidad local:<usuario-del-SO> es una etiqueta local, no una autenticación remota. En un servicio multiusuario real, la autenticación del usuario, entrega de clave y revocación deben conectarse a un proveedor de identidad/KMS; no debe confiarse en un owner_id que el cliente pueda declarar libremente. Una clave de corrida robada permite descifrar esa corrida.

## Índice comunitario y frescura

La publicación está desactivada por defecto. El guardián rechaza eventos públicos salvo que una política lo habilite expresamente; los resultados privados no se convierten automáticamente en registros comunitarios. Esta versión no implementa un historial global de resultados. Cada comparación fresca requiere nuevas ejecuciones de las plataformas elegidas; el manifiesto local no da acceso a otras corridas.

## Límite criptográfico

AES-GCM protege los artefactos en reposo y detecta alteraciones del ciphertext. El hash SHA3-256 del guardián detecta discrepancias de bytes dentro del proceso. Esto no equivale a un sello notarial CSG: la integración con CSG, la confianza en claves y el anclaje antirretroceso se mantienen como controles separados. El guardián tampoco demuestra la veracidad física de los datos reportados por una QPU ni puede detectar un espejo pasivo fuera de los canales que controla.

## Verificación

Ejecutar pytest -q tests/test_flow_guard.py. La suite comprueba transiciones, replay, reordenamiento, propietario incorrecto, canal público no autorizado, presupuesto de egress, modificación de artefactos, cifrado/descifrado por corrida, clave incorrecta y manipulación de ciphertext.
