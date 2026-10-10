# Reanalisis de corridas previas (ibm_fez, q142)

Generado por `scripts/reanalyze_previous.py` a partir de `data/previous_runs.json` (sin gastar cola).

## Canal libre

- Ajuste Ramsey con los 17 puntos densos de v1: δf = **27.14 ± 0.06 kHz**, T2* = **139 ± 7 µs**, β = 1.00 ± 0.06 (χ²_red = 1.3).
- v2 reporto δf = 53.9 kHz y T2 = 61.8 µs. Con un paso minimo de 26.5 µs, el limite de Nyquist es 18.9 kHz < δf real: esa frecuencia es un **alias** y el T2 asociado no es fiable.
- v1 reporto T2_libre = 5.2 µs porque ajustaba un decaimiento monotono a una oscilacion. Ese numero no es una medida de T2.

## CPMG y XY4

| Protocolo | v1 largo | v2 | v3 | Combinado |
|---|---|---|---|---|
| CPMG | 170 ± 5 µs (β=1.15) | 166 ± 19 µs (β=0.76) | 199 ± 13 µs (β=1.10) | 178 ± 5 µs (β=0.96) |
| XY4 | 197 ± 7 µs (β=0.97) | 170 ± 81 µs (β=0.61) | 203 ± 7 µs (β=1.20) | 193 ± 9 µs (β=0.87) |

- Extension real frente a T2*: CPMG **1.28 ± 0.07x**, XY4 **1.39 ± 0.09x** (antes se reportaba 10.7x y 3.2x).
- El beneficio principal del DD en este qubit es **refocalizar el detuning coherente** (la fase), y en segundo lugar alargar la envolvente alrededor de un 30-40 %.
- β ≈ 0.96 (CPMG) y 0.87 (XY4): el decaimiento con DD es casi exponencial, asi que el ruido restante es sobre todo Markoviano o de alta frecuencia. Mas pulsos no ayudan mucho (ver barrido N).

## Reproducibilidad v2 vs v3 (mismo qubit y mismos tiempos)

- CPMG: diferencia maxima 0.066, χ²_red = 4.2, |z|max = 4.4. Supera el ruido de disparo, lo que indica **deriva temporal** entre jobs.
- XY4: diferencia maxima 0.137, χ²_red = 11.4, |z|max = 6.1. Supera el ruido de disparo, lo que indica **deriva temporal** entre jobs.

## Relevos (v3)

- P(1) agregada de los vecinos: 0.126 % (108 de 86016 disparos). **Cota superior al 95 % de transferencia a vecinos: 0.145 %**, que ya incluye el error de lectura.
- Comparar contra el control lejano (P(1) = 1.79 %) no es valido: mide el error de lectura de otro qubit. La v4 usa una referencia pareada (objetivo inactivo) por cada vecino.
- Las correlaciones reportadas (+0.47, −0.39, +0.51) salen de 7 puntos con 1 a 9 cuentas cada uno:
  - free: Spearman ρ = +0.18, p = 0.70, cuentas = [2, 4, 5, 9, 9, 7, 3]
  - cpmg: Spearman ρ = -0.45, p = 0.31, cuentas = [6, 6, 7, 3, 9, 4, 2]
  - xy4: Spearman ρ = +0.40, p = 0.38, cuentas = [6, 1, 3, 4, 6, 7, 5]
  Ninguna es significativa, asi que no aportan evidencia en ningun sentido.
- La verificacion estructural de v3 buscaba compuertas `swap`, pero tras transpilar un SWAP aparece como 3 CZ. La v4 cuenta cualquier compuerta de 2 qubits y verifica el layout inicial y final.

## Barrido N (CPMG a 60 µs)

- ⟨X⟩ entre 0.691 y 0.719 (σ por punto ≈ 0.016); χ²_red frente a una constante = 0.49. Las curvas son planas: el "N óptimo = 16" no es significativo (1.2 σ entre el maximo y el minimo).
