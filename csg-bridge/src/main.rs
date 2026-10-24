use sello_integridad::{
    verificar_sello, ClavePrivada, Firmante, Notario, NotarioPersistente,
};
use serde_json::json;
use std::{env, fs, path::PathBuf, process};

fn fail(msg: &str) -> ! {
    eprintln!("EQG_CSG_ERROR: {msg}");
    process::exit(2);
}

fn key_from_env(name: &str) -> ClavePrivada {
    let raw = env::var(name).unwrap_or_else(|_| fail(&format!("missing required environment variable {name}")));
    let bytes = hex::decode(raw.trim()).unwrap_or_else(|_| fail(&format!("{name} must be 64 hex characters")));
    let array: [u8; 32] = bytes.try_into().unwrap_or_else(|_| fail(&format!("{name} must encode exactly 32 bytes")));
    ClavePrivada::from_bytes(&array).unwrap_or_else(|_| fail(&format!("invalid key in {name}")))
}

fn write_attestation(payload: &[u8], output: &PathBuf, run_id: &str, key_mode: &str,
                     signer: &Firmante, notary: &Notario) {
    let project = env::var("EQG_CSG_PROJECT_ID").unwrap_or_else(|_| "EQG-MVP".to_string());
    // Ephemeral CPU self-test authorizes its throwaway signer in its throwaway notary.
    // Production authorization is provisioned once, explicitly, by the operator.
    let event_id = format!("eqg-{run_id}");
    let (event, signature) = signer
        .crear_evento_archivo(payload, project, Some(event_id))
        .unwrap_or_else(|e| fail(&format!("could not create signed CSG event: {e}")));
    let seal = notary
        .sellar_archivo(&event, &signature, &signer.clave_publica())
        .unwrap_or_else(|e| fail(&format!("CSG notary failed: {e}")));
    if !seal.aceptado {
        fail(&format!("CSG rejected event: {}", seal.razon));
    }
    let report = verificar_sello(&seal, &notary.clave_publica_hex(), None)
        .unwrap_or_else(|e| fail(&format!("CSG verification errored: {e}")));
    if !report.todo_valido { fail("CSG seal verification did not pass"); }
    let chain = notary.verificar_cadena().unwrap_or_else(|e| fail(&format!("CSG chain verification errored: {e}")));
    if chain.iter().any(|item| !item.todo_valido) { fail("CSG seal chain verification did not pass"); }
    let envelope = json!({
        "schema_version": "eqg.csg-attestation.v1",
        "run_id": run_id,
        "artifact_name": output.file_name().and_then(|s| s.to_str()).unwrap_or("artifact"),
        "artifact_bytes": payload.len(),
        "key_mode": key_mode,
        "csg_crate_version": sello_integridad::VERSION,
        "notary_public_key_hex": notary.clave_publica_hex(),
        "signer_public_key_hex": signer.clave_publica_hex(),
        "seal": seal,
        "verification": report,
        "chain_verification": chain,
        "warning": if key_mode == "ephemeral_cpu_self_test" { "TEST-ONLY ephemeral keys; not a production identity or durable trust anchor" } else { "Verification proves integrity/signature only; trust in the public key must be established out of band" }
    });
    fs::write(output, serde_json::to_vec_pretty(&envelope).unwrap_or_else(|e| fail(&e.to_string())))
        .unwrap_or_else(|e| fail(&format!("cannot write attestation: {e}")));
    println!("EQG_CSG_ATTESTATION_PASS {}", output.display());
}

fn main() {
    let args: Vec<String> = env::args().collect();
    if args.len() < 5 || args.len() > 6 {
        fail("usage: eqg-csg-bridge <artifact> <attestation.json> <run_id> <ephemeral_cpu_self_test|env_preflight|env> [enroll]");
    }
    let input = PathBuf::from(&args[1]);
    let output = PathBuf::from(&args[2]);
    let run_id = &args[3];
    let mode = &args[4];
    let payload = fs::read(&input).unwrap_or_else(|e| fail(&format!("cannot read artifact: {e}")));
    match mode.as_str() {
        "ephemeral_cpu_self_test" => {
            let signer = Firmante::generar("EQG CPU CSG self-test");
            let notary = Notario::nuevo("EQG CPU ephemeral notary");
            let project = env::var("EQG_CSG_PROJECT_ID").unwrap_or_else(|_| "EQG-MVP".to_string());
            notary.registrar_firmante_autorizado(&project, signer.clave_publica_hex());
            write_attestation(&payload, &output, run_id, mode, &signer, &notary);
        }
        "env_preflight" => {
            let signer_env = env::var("EQG_CSG_SIGNER_KEY_ENV").unwrap_or_else(|_| "EQG_CSG_SIGNER_KEY_HEX".to_string());
            let notary_env = env::var("EQG_CSG_NOTARY_KEY_ENV").unwrap_or_else(|_| "EQG_CSG_NOTARY_KEY_HEX".to_string());
            let signer = Firmante::desde_clave("EQG configured signer", key_from_env(&signer_env));
            let notary_key = key_from_env(&notary_env);
            let state_dir = env::var_os("EQG_CSG_STATE_DIR").map(PathBuf::from)
                .unwrap_or_else(|| PathBuf::from("outputs/csg-notary"));
            let notary = NotarioPersistente::abrir("EQG configured notary", state_dir, notary_key)
                .unwrap_or_else(|e| fail(&format!("cannot open persistent CSG notary in preflight: {e}")));
            let project = env::var("EQG_CSG_PROJECT_ID").unwrap_or_else(|_| "EQG-MVP".to_string());
            if args.get(5).map(String::as_str) == Some("enroll") {
                notary.registrar_firmante_autorizado(&project, signer.clave_publica_hex())
                    .unwrap_or_else(|e| fail(&format!("cannot persist CSG signer authorization: {e}")));
            }
            let event_id = format!("eqg-{run_id}");
            let (event, signature) = signer.crear_evento_archivo(&payload, project, Some(event_id))
                .unwrap_or_else(|e| fail(&format!("could not create signed CSG preflight event: {e}")));
            let seal = notary.sellar_archivo(&event, &signature, &signer.clave_publica())
                .unwrap_or_else(|e| fail(&format!("CSG preflight notary failed: {e}")));
            if !seal.aceptado { fail(&format!("CSG preflight signer is not authorized or seal rejected: {}", seal.razon)); }
            let report = verificar_sello(&seal, &notary.notario().clave_publica_hex(), None)
                .unwrap_or_else(|e| fail(&format!("CSG preflight verification errored: {e}")));
            let chain = notary.notario().verificar_cadena()
                .unwrap_or_else(|e| fail(&format!("CSG preflight chain verification errored: {e}")));
            if !report.todo_valido || chain.is_empty() || chain.iter().any(|x| !x.todo_valido) {
                fail("CSG preflight signature or persistent chain verification failed");
            }
            let envelope = json!({
                "schema_version":"eqg.csg-attestation.v1", "run_id":run_id,
                "artifact_name":input.file_name().and_then(|s| s.to_str()).unwrap_or("artifact"),
                "artifact_bytes":payload.len(), "key_mode":"env_preflight_persistent_notary",
                "csg_crate_version":sello_integridad::VERSION,
                "notary_public_key_hex":notary.notario().clave_publica_hex(),
                "signer_public_key_hex":signer.clave_publica_hex(), "seal":seal,
                "verification":report, "chain_verification":chain,
                "warning":"Preflight seal is written to the configured persistent CSG chain; public-key trust must be anchored out of band"
            });
            fs::write(output, serde_json::to_vec_pretty(&envelope).unwrap_or_else(|e| fail(&e.to_string())))
                .unwrap_or_else(|e| fail(&format!("cannot write preflight attestation: {e}")));
            println!("EQG_CSG_ATTESTATION_PASS");
        }
        "env" => {
            let signer_env = env::var("EQG_CSG_SIGNER_KEY_ENV").unwrap_or_else(|_| "EQG_CSG_SIGNER_KEY_HEX".to_string());
            let notary_env = env::var("EQG_CSG_NOTARY_KEY_ENV").unwrap_or_else(|_| "EQG_CSG_NOTARY_KEY_HEX".to_string());
            let signer = Firmante::desde_clave("EQG configured signer", key_from_env(&signer_env));
            let notary_key = key_from_env(&notary_env);
            let state_dir = env::var_os("EQG_CSG_STATE_DIR").map(PathBuf::from)
                .unwrap_or_else(|| PathBuf::from("outputs/csg-notary"));
            let notary = NotarioPersistente::abrir("EQG configured notary", state_dir, notary_key)
                .unwrap_or_else(|e| fail(&format!("cannot open persistent CSG notary: {e}")));
            let project = env::var("EQG_CSG_PROJECT_ID").unwrap_or_else(|_| "EQG-MVP".to_string());
            if args.get(5).map(String::as_str) == Some("enroll") {
                notary.registrar_firmante_autorizado(&project, signer.clave_publica_hex())
                    .unwrap_or_else(|e| fail(&format!("cannot persist CSG signer authorization: {e}")));
            }
            // Build and sign the event, then use the persistent notary so the seal enters its durable chain.
            let event_id = format!("eqg-{run_id}");
            let (event, signature) = signer.crear_evento_archivo(&payload, project, Some(event_id))
                .unwrap_or_else(|e| fail(&format!("could not create signed CSG event: {e}")));
            let seal = notary.sellar_archivo(&event, &signature, &signer.clave_publica())
                .unwrap_or_else(|e| fail(&format!("CSG notary failed: {e}")));
            if !seal.aceptado { fail(&format!("CSG rejected event: {}", seal.razon)); }
            let report = verificar_sello(&seal, &notary.notario().clave_publica_hex(), None)
                .unwrap_or_else(|e| fail(&format!("CSG verification errored: {e}")));
            if !report.todo_valido { fail("CSG seal verification did not pass"); }
            let chain = notary.notario().verificar_cadena()
                .unwrap_or_else(|e| fail(&format!("CSG chain verification errored: {e}")));
            if chain.iter().any(|item| !item.todo_valido) { fail("CSG seal chain verification did not pass"); }
            let envelope = json!({
                "schema_version":"eqg.csg-attestation.v1", "run_id":run_id,
                "artifact_name":input.file_name().and_then(|s| s.to_str()).unwrap_or("artifact"),
                "artifact_bytes":payload.len(), "key_mode":"env",
                "csg_crate_version":sello_integridad::VERSION,
                "notary_public_key_hex":notary.notario().clave_publica_hex(),
                "signer_public_key_hex":signer.clave_publica_hex(),
                "seal":seal, "verification":report, "chain_verification":chain,
                "warning":"Verification proves integrity/signature only; trust in the public key must be established out of band"
            });
            fs::write(output, serde_json::to_vec_pretty(&envelope).unwrap_or_else(|e| fail(&e.to_string())))
                .unwrap_or_else(|e| fail(&format!("cannot write attestation: {e}")));
            println!("EQG_CSG_ATTESTATION_PASS");
        }
        _ => fail("unsupported key mode"),
    }
}
