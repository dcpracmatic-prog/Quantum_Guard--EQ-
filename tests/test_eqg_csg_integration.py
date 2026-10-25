import hashlib
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from run_eqg_mvp import validate_csg_attestation


def _fixture(tmp_path):
    artifact=tmp_path/'report.enc'
    payload=b'ciphertext artifact fixture'
    artifact.write_bytes(payload)
    run_id='job-123'
    attestation=tmp_path/'report.csg.json'
    attestation.write_text(json.dumps({
        'schema_version':'eqg.csg-attestation.v1', 'run_id':run_id,
        'seal':{'evento_id':f'eqg-{run_id}','aceptado':True,'hash_contenido':hashlib.sha3_256(payload).hexdigest()},
        'verification':{'todo_valido':True},
        'chain_verification':[{'todo_valido':True}],
    }))
    return artifact,attestation,run_id


def test_valid_csg_attestation_binds_exact_bytes(tmp_path):
    artifact,attestation,run_id=_fixture(tmp_path)
    assert validate_csg_attestation(artifact,attestation,run_id)['run_id']==run_id


@pytest.mark.parametrize('mutate',[
    lambda d:d.update(run_id='other'),
    lambda d:d['seal'].update(aceptado=False),
    lambda d:d['seal'].update(hash_contenido='0'*64),
    lambda d:d['verification'].update(todo_valido=False),
    lambda d:d['chain_verification'][0].update(todo_valido=False),
])
def test_invalid_or_unbound_csg_attestations_fail(tmp_path,mutate):
    artifact,attestation,run_id=_fixture(tmp_path)
    data=json.loads(attestation.read_text()); mutate(data); attestation.write_text(json.dumps(data))
    with pytest.raises(ValueError): validate_csg_attestation(artifact,attestation,run_id)


def test_csg_enabled_fails_closed_if_attestation_absent(tmp_path):
    artifact,attestation,run_id=_fixture(tmp_path)
    attestation.unlink()
    with pytest.raises(FileNotFoundError): validate_csg_attestation(artifact,attestation,run_id)
