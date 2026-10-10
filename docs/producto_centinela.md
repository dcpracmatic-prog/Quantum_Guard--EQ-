Centinela QPU: de experimento a herramienta práctica
Documento público resumido. Basado en notebooks v1–v4 y en las cuatro corridas de hardware realizadas el 23 de septiembre de 2026 en el backend ibm_fez (qubit q142).
Resumen
Los datos experimentales muestran algo más valioso que la simple extensión de (T_2) mediante Dynamical Decoupling: el qubit q142 cambia de estado en escalas de minutos. La calibración publicada por el proveedor no refleja estas fluctuaciones.
En dos corridas se observó (T_2^* \approx 155,\mu\mathrm{s}) y en otras dos (T_2^* \approx 40,\mu\mathrm{s}), acompañadas de saltos de frecuencia de hasta 6 kHz. Este comportamiento es compatible con la física conocida de defectos de dos niveles (TLS) acoplados al qubit.
Centinela es un sondeo previo de aproximadamente 7 segundos de QPU que mide varios qubits candidatos en paralelo y responde tres preguntas antes de enviar un trabajo costoso:
¿Qué qubit se encuentra en buen estado en este momento?
¿Conviene activar Dynamical Decoupling y cuánta mejora se espera?
¿Qué corrección de fase (Z virtual, de costo cero) debe aplicarse?
Cada sondeo puede alimentar una bitácora por qubit. Con el tiempo, esa información (estados observados, tiempos de permanencia y huellas de frecuencia) constituye un activo de conocimiento útil.
El prototipo funcional se encuentra en este repositorio (src/ddqpu/sentinel.py, notebooks/centinela_preflight.ipynb).
Resultados experimentales principales (corridas v4)
Corrida
Hora (UTC aprox.)
(T_2^*) libre (µs)
(T_2) CPMG (µs)
(T_2) XY4 (µs)
Detuning (kHz)
Estado
A
04:00
158.6 ± 7.6
207.5 ± 12.2
220.4 ± 21.4
−27.04 ± 0.21
bueno
B
04:02
45.4 ± 3.7
86.2 ± 10.8
98.0 ± 11.7
−25.32 ± 0.38
degradado
C
04:14
37.6 ± 2.4
90.2 ± 10.1
87.9 ± 13.1
−20.81 ± 0.36
degradado
D
04:16
153.3 ± 6.3
217.0 ± 10.6
228.3 ± 23.0
−27.05 ± 0.17
bueno
Resumen por estado
Magnitud
Estado bueno (A, D)
Estado degradado (B, C)
(T_2^*) libre
155 ± 5 µs
40 ± 4 µs
(T_2) CPMG
213 ± 8 µs
88 ± 7 µs
Extensión CPMG / libre
1.37 ± 0.07×
2.12 ± 0.25×
Extensión XY4 / libre
1.44 ± 0.11×
2.23 ± 0.24×
Detuning
−27.05 ± 0.13 kHz
−21 a −25 kHz
Lecturas físicas principales:
Se observan dos estados discretos, no una deriva continua. Dentro de cada estado las corridas son estadísticamente compatibles; entre estados difieren por más de 10σ.
La frecuencia salta junto con el desfase, firma característica de un TLS acoplado al qubit.
El protocolo CPMG elimina aproximadamente el 64–65 % del exceso de desfase asociado al estado degradado.
El acoplamiento ZZ con vecinos (medido con vecinos en |1⟩) es de −4.05 ± 0.20 kHz y resulta invariante entre estados. El DD lo suprime en un ~93 %.
La cota superior de relevo (fuga o crosstalk) hacia qubits vecinos se sitúa por debajo del 0.18 % (95 % de confianza) en todas las corridas.
Más detalle cuantitativo disponible en results/v4_estados.md y results/v4_estados.json.
Qué implementa Centinela
El módulo src/ddqpu/sentinel.py realiza:
Sondeo paralelo de varios qubits candidatos (Ramsey en cuadratura + CPMG + (T_1)).
Estimación de (\Delta f), (T_2^*), (T_2) de eco, (T_1) y tasa de desfase puro (\Gamma_\varphi).
Clasificación del estado del qubit (estable / degradado).
Generación de bitácora y huella de referencia.
Aplicación de corrección de fase mediante rotación Z virtual (compensate_detuning).
El notebook notebooks/centinela_preflight.ipynb permite ejecutarlo de forma autocontenida (modos simulación y hardware).
Alcance de este documento
Este archivo presenta los resultados experimentales y la descripción de alto nivel de la herramienta Centinela.
No incluye proyecciones de mercado, estimaciones de ahorro económico detalladas ni planes de validación comercial. Esas consideraciones se mantienen fuera del repositorio público.
Reproducibilidad
Los datos crudos de los jobs de IBM Quantum utilizados en este estudio se incluyen en evidence/ibm_jobs/ únicamente con fines de reproducibilidad científica.
El uso de dichos datos está sujeto a los términos de servicio de IBM Quantum.
Copyright (c) 2026 Arturo Salvador Balderas Hernández
Licencia MIT (ver archivo LICENSE en la raíz del repositorio).
