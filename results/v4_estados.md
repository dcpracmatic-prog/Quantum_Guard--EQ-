# Corridas v4 en hardware: dos estados del qubit q142

Datos: `data/v4_runs.json` (4 jobs del 23-sep-2026, mismo layout).

| Corrida | Hora UTC | T2* libre (µs) | T2 CPMG (µs) | T2 XY4 (µs) | Detuning (kHz) | Estado |
|---|---|---|---|---|---|---|
| A | 04:00 | 158.6 ± 7.6 | 207.5 ± 12.2 | 220.4 ± 21.4 | -27.04 ± 0.21 | bueno |
| B | 04:02 | 45.4 ± 3.7 | 86.2 ± 10.8 | 98.0 ± 11.7 | -25.32 ± 0.38 | degradado |
| C | 04:14 | 37.6 ± 2.4 | 90.2 ± 10.1 | 87.9 ± 13.1 | -20.81 ± 0.36 | degradado |
| D | 04:16 | 153.3 ± 6.3 | 217.0 ± 10.6 | 228.3 ± 23.0 | -27.05 ± 0.17 | bueno |

## Por estado (media ponderada; error inflado por sqrt(chi2) si hay tension)

| Magnitud | Estado bueno (A, D) | Estado degradado (B, C) |
|---|---|---|
| T2* libre (µs) | 155.46 ± 4.85 (χ²=0.3) | 39.91 ± 3.56 (χ²=3.1) |
| T2 CPMG (µs) | 212.91 ± 8.00 (χ²=0.3) | 88.33 ± 7.38 (χ²=0.1) |
| T2 XY4 (µs) | 224.07 ± 15.67 (χ²=0.1) | 93.52 ± 8.73 (χ²=0.3) |
| Detuning (kHz) | -27.05 ± 0.13 (χ²=0.0) | -22.94 ± 2.25 (χ²=74.2) |
| Extension CPMG/libre | 1.37 ± 0.07 (χ²=0.7) | 2.12 ± 0.25 (χ²=1.4) |
| Extension XY4/libre | 1.44 ± 0.11 (χ²=0.2) | 2.23 ± 0.24 (χ²=0.1) |

## Tasas de decoherencia (1/T2, en 1/ms)

| Protocolo | Estado bueno | Estado degradado | Exceso por el estado degradado |
|---|---|---|---|
| free | 6.43 ± 0.20 | 25.06 ± 2.24 | 18.62 ± 2.24 |
| cpmg | 4.70 ± 0.18 | 11.32 ± 0.95 | 6.62 ± 0.96 |
| xy4 | 4.46 ± 0.31 | 10.69 ± 1.00 | 6.23 ± 1.05 |

El CPMG elimina 64 ± 7 % del exceso de desfase del estado degradado.

El XY4 elimina 67 ± 7 % del exceso de desfase del estado degradado.

## Otros invariantes
- Correlacion |detuning| vs 1/T2* entre corridas: r = -0.88 (n = 4; indicativo, no concluyente).
- ZZ con vecinos en |1> (libre): -4.05 ± 0.20 kHz en los dos estados -> el estado degradado no viene de los vecinos.
- ZZ con CPMG: -0.27 ± 0.18 kHz -> el DD suprime el 93 % del ZZ.
- Cota de relevo a vecinos (95 %): 0.081-0.182 % en las 4 corridas.

## Correcciones a la seccion 13 del notebook
- Combinar A-D por varianza inversa mezcla dos estados fisicos distintos (χ² de hasta 294): el promedio no describe ninguno.
- 'XY4 > CPMG en ambas corridas' no se cumple en C (87.9 vs 90.2 µs); XY4 y CPMG son compatibles en todas.
- El texto de la seccion 11 cita una extension de 0.90-0.94x que no aparece en ninguna salida mostrada.
- La extension por DD depende del estado: ~1.4x en estado bueno y ~2.1x en degradado. Reportarla sin estado es ambiguo.
