# Evidencia cruda

**Aviso importante**  
Los archivos contenidos en `ibm_jobs/` corresponden a resultados de jobs ejecutados en hardware de IBM Quantum.  
Se publican **exclusivamente con fines de reproducibilidad científica**.  
El uso de estos datos está sujeto a los términos de servicio y políticas de IBM Quantum.  
Este repositorio no está afiliado ni respaldado por IBM.

---

- `ibm_jobs/<job_id>/`: archivos `*-info.json` y `*-result.json` descargados de IBM Quantum (backend `ibm_fez`, 23 de septiembre de 2026).
- `notebooks_tempranos/`: iteraciones previas de CPMG con un solo qubit. Su métrica \(|\langle X\rangle_\mathrm{CPMG}| / |\langle X\rangle_\mathrm{libre}|\) se dispara cuando \(\langle X\rangle_\mathrm{libre} \approx 0\) y **no** constituye una extensión real de \(T_2\); ver `results/reanalisis_previas.md`.
- Los notebooks v1–v4 completos se encuentran en `data/notebooks_originales/`.
- Los notebooks leen el token del secreto `IBM_QUANTUM_TOKEN`; no hay credenciales almacenadas en los archivos del repositorio.

## Jobs incluidos

| Creado (UTC)                  | Job ID                     | Backend  | Corrida v4 |
|-------------------------------|----------------------------|----------|------------|
| 2026-09-23T00:38:03.808732Z  | `daphuqr18flc739mb47g`    | ibm_fez |            |
| 2026-09-23T00:48:40.436143Z  | `dapi3q2c505c73ci8v6g`    | ibm_fez |            |
| 2026-09-23T00:49:44.207824Z  | `dapi4a318flc739mbatg`    | ibm_fez |            |
| 2026-09-23T01:37:24.089641Z  | `dapiql318flc739mc7c0`    | ibm_fez |            |
| 2026-09-23T02:07:21.313643Z  | `dapj8mac505c73ciad30`    | ibm_fez |            |
| 2026-09-23T02:56:28.656111Z  | `dapjvn318flc739mdml0`    | ibm_fez |            |
| 2026-09-23T03:40:08.93352Z   | `dapkk6318flc739metfg`    | ibm_fez |            |
| 2026-09-23T03:48:03.031814Z  | `dapknsgr7bnc73b3k930`    | ibm_fez |            |
| 2026-09-23T03:48:47.131596Z  | `dapko7sak42c73ciou90`    | ibm_fez |            |
| 2026-09-23T03:59:50.772194Z  | `dapktdj18flc739mf8l0`    | ibm_fez | A          |
| 2026-09-23T04:01:02.436362Z  | `dapktvgr7bnc73b3kg8g`    | ibm_fez | B          |
| 2026-09-23T04:13:24.669217Z  | `dapl3p2c505c73cid330`    | ibm_fez | C          |
| 2026-09-23T04:14:46.992788Z  | `dapl4dkak42c73cipd30`    | ibm_fez | D          |
