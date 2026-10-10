# Changelog

## 5.0.0
- Nuevo `ddqpu.sentinel` (Centinela): sondeo de 28 circuitos con K candidatos en paralelo (~7 s QPU), Ramsey en cuadratura + CPMG + T1, Gamma_phi, bitacora JSONL, huella de referencia, clasificacion estable/degradado, `compensate_detuning` (rz virtual).
- Analisis de las 4 corridas v4 en hardware: dos estados de q142 (T2* 155 vs 40 us, salto de frecuencia hasta 6 kHz); el DD elimina ~65 % del exceso de desfase; ZZ -4.05 kHz invariante, 93 % suprimido por CPMG.
- Correccion: combinar corridas de estados distintos por varianza inversa no es valido (seccion 13 del notebook de usuario).
- `docs/producto_centinela.md`, `notebooks/centinela_preflight.ipynb`, 7 pruebas nuevas.

## v4.0.0
### Relevos
- La verificacion estructural cuenta **todas** las compuertas de 2 qubits (cz/ecr/cx/swap/...). Un SWAP transpilado aparece como 3 CZ y la v3 no lo veia.
- Se verifican el layout inicial y el final de todos los qubits logicos, y que el bit 0 se mide en el qubit objetivo.
- Prueba **pareada**: P(1) de cada vecino con el objetivo activo o en |1⟩ frente al objetivo inactivo, al mismo t, con prueba de dos proporciones, Bonferroni y cota superior al 95 %. Se elimina la comparacion contra el piso de lectura de otro qubit y las correlaciones de 7 puntos.
- Nuevo bloque ZZ: vecinos en |1⟩ para medir el corrimiento de fase del objetivo y comprobar si el DD lo cancela.
- El control lejano se elige por menor error de lectura y distancia >= 4.

### Resultados
- Coherencia en cuadratura (lecturas en X e Y): |ρ01| no oscila con el detuning.
- Rejilla de tiempos con tramo denso (paso <= 5 µs hasta 40 µs) y tramo escalado a T2 (0.2x a 1.6x): sin aliasing.
- Mitigacion de lectura por qubit con calibracion en el mismo job.
- Ajustes con C = 0, ponderados por ruido de disparo y error inflado por √χ²_red. Se marca baja confianza si el error supera el 30 % o el barrido no llega a 0.7 T2.
- Delays en unidades dt, multiplos de la granularidad del backend: mismo tiempo exacto en libre/CPMG/XY4 y sin warnings. Se reporta t efectivo con pulsos.
- Orden aleatorio de circuitos, shots por PUB, estimacion y freno de tiempo QPU.
- Modos `sim` (FakeFez) y `reuse` (reanalisis por job ID).
- Seleccion de qubit con target API: min(T2, 2T1), error sx y error de lectura.
- El token no se guarda en disco.

## v3 (notebook -9)
Medicion de vecinos y control; verificacion de SWAP por nombre.
## v2 (notebook -8)
Barrido escalado a T2; ajuste Ramsey para libre.
## v1 (notebook -7)
Libre/CPMG/XY4 a 2-30 µs, barrido largo y barrido N.
