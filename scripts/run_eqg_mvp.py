#!/usr/bin/env python3
"""Run CPU operational smoke or explicitly authorized IBM hardware workload."""
from __future__ import annotations
import argparse, importlib.util, json, os, re, subprocess, sys
from pathlib import Path
import numpy as np
import yaml

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from eqg_mvp.engine import morph_path, build_qaoa_path, ar_from_counts, verdict


def expand_env(value):
    if not isinstance(value,str): return value
    m=re.fullmatch(r'\$\{([A-Z0-9_]+)\}',value)
    return os.getenv(m.group(1)) if m else value


def read_config(path):
    cfg=yaml.safe_load(Path(path).read_text(encoding='utf-8'))
    cfg.setdefault('validation',{}); cfg.setdefault('execution',{})
    return cfg


def run_cpu(cfg):
    ex=cfg['execution']; n=int(ex.get('n_logical',4)); p=int(ex.get('qaoa_p',1)); shots=int(ex.get('shots',2048)); seed=int(ex.get('seed',20261024))
    fixture=json.loads((ROOT/'tests/fixtures/mvp_cpu_backend.json').read_text())
    # Deliberately an operational fixture: no hardware performance inference is made from this run.
    eqg=morph_path(n,fixture['friction'],fixture['edges'])
    ref=morph_path(n,fixture['friction'],fixture['edges'],maximize=True)
    rng=np.random.default_rng(seed); gammas=rng.uniform(.25,.85,size=p); betas=rng.uniform(.15,.45,size=p)
    qc=build_qaoa_path(n,p,gammas,betas)
    from qiskit_aer import AerSimulator
    from qiskit import transpile
    sim=AerSimulator()
    # On CPU, logical-qubit permutations are used only to exercise path wiring and transpilation.
    results=[]
    for layout in (eqg,ref):
        local_layout=[layout.index(q) for q in sorted(layout)]
        tc=transpile(qc,sim,initial_layout=local_layout,optimization_level=1,seed_transpiler=seed)
        counts=sim.run(tc,shots=shots,seed_simulator=seed).result().get_counts()
        ar,se=ar_from_counts(counts,n,shots)
        results.append({'layout':layout,'ar':ar,'se':se})
    delta=results[0]['ar']-results[1]['ar']; sed=(results[0]['se']**2+results[1]['se']**2)**.5
    z=delta/sed if sed else float('nan')
    payload={'mode':'cpu','status':'CPU_SMOKE_PASS','evidence_class':'operational_smoke_not_hardware_evidence','workload':'canonical_mvp_qaoa_maxcut_path','configuration':{'n_logical':n,'qaoa_p':p,'shots_per_layout':shots,'seed':seed},'fixture_note':fixture['fixture_type'],'morph_layout':results[0]['layout'],'reference_layout':results[1]['layout'],'simulated_ar':{'morph':results[0]['ar'],'reference':results[1]['ar'],'delta':delta,'z':z},'product_verdict':None}
    out=ROOT/'outputs'/'eqg_mvp_cpu_smoke.json'; out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(payload,indent=2)+'\n',encoding='utf-8')
    print('EQG_MVP_CPU_OPERATIONAL_SMOKE_PASS')
    print('Mode: CPU only; no provider API/token/QPU used.')
    print('Synthetic fixture is for execution-path smoke only; simulated AR is NOT a performance/product verdict.')
    print('Saved:',out.relative_to(ROOT))


def run_hardware(cfg):
    ex=cfg['execution']; v=cfg.get('validation',{})
    if not ex.get('confirm_spend',False): raise SystemExit('Hardware mode blocked: set execution.confirm_spend: true after reviewing QPU budget.')
    token_env=ex.get('token_env','IBM_QUANTUM_TOKEN'); token=os.getenv(token_env)
    if not token: raise SystemExit(f'Hardware mode blocked: environment variable {token_env} is missing.')
    from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2
    from qiskit import transpile
    backend_name=ex.get('backend','ibm_kingston'); instance=expand_env(ex.get('instance'))
    if ex.get('instance') and not instance:
        raise SystemExit('Hardware mode requires the configured IBM_QUANTUM_INSTANCE environment variable.')
    kwargs={'channel':'ibm_quantum_platform','token':token}
    if instance: kwargs['instance']=instance
    service=QiskitRuntimeService(**kwargs); backend=service.backend(backend_name); props=backend.properties()
    fr=[]
    for q in range(backend.num_qubits):
        try: ro=float(props.readout_error(q))
        except Exception: ro=.03
        try: xe=float(props.gate_error('x',[q]))
        except Exception: xe=.001
        fr.append(min(1.,6*ro+60*xe))
    edges=list(backend.coupling_map.get_edges()); n=int(ex.get('n_logical',4)); p=int(ex.get('qaoa_p',1)); shots=int(ex.get('shots',2048)); seed=int(ex.get('seed',20261024))
    eqg=morph_path(n,fr,edges); ref=morph_path(n,fr,edges,maximize=True)
    if eqg==ref: raise SystemExit('MORPH and reference paths coincide; refuse the unconnected fallback. Inspect the comparison before submitting.')
    rng=np.random.default_rng(seed); qc=build_qaoa_path(n,p,rng.uniform(.25,.85,size=p),rng.uniform(.15,.45,size=p))
    t1=transpile(qc,backend,initial_layout=eqg,optimization_level=1); t2=transpile(qc,backend,initial_layout=ref,optimization_level=1)
    job=SamplerV2(mode=backend).run([(t1,None,shots),(t2,None,shots)]); result=job.result()
    counts=[result[i].data.c.get_counts() for i in range(2)]
    vals=[ar_from_counts(c,n,shots) for c in counts]; delta=vals[0][0]-vals[1][0]; sed=(vals[0][1]**2+vals[1][1]**2)**.5; z=delta/sed if sed else float('nan')
    state=cfg.get('validation',{})
    status,lower=verdict(delta,sed,z,delta_min=float(ex.get('delta_min',.02)),z_min=float(ex.get('z_min',2)),ic95_low_min=float(ex.get('ic95_low_min',.006)))
    payload={'mode':'hardware','backend':backend_name,'instance':instance,'job_id':job.job_id(),'n_logical':n,'qaoa_p':p,'shots_per_layout':shots,'morph_layout':eqg,'reference_layout':ref,'ar_morph':vals[0][0],'se_morph':vals[0][1],'ar_reference':vals[1][0],'se_reference':vals[1][1],'delta_ar':delta,'se_delta':sed,'z':z,'ic95_low':lower,'verdict':status,'evidence_class':'single hardware run; does not establish multi-day reproducibility'}
    out=ROOT/'outputs'/f'eqg_mvp_{backend_name}_{job.job_id()}.json'; out.parent.mkdir(exist_ok=True); out.write_text(json.dumps(payload,indent=2)+'\n')
    print('Hardware run complete:',job.job_id(),status,'report:',out.relative_to(ROOT))


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--config',default=str(ROOT/'config/eqg_mvp.yaml')); parser.add_argument('--skip-pytest',action='store_true'); a=parser.parse_args()
    cfg=read_config(a.config); v=cfg['validation']; ex=cfg['execution']
    if v.get('pytest',True) and not a.skip_pytest:
        r=subprocess.run([sys.executable,'-m','pytest','-q'],cwd=ROOT)
        if r.returncode: return r.returncode
    if v.get('verify_evidence',False):
        r=subprocess.run([sys.executable,str(ROOT/'scripts/validate_product_evidence.py')],cwd=ROOT)
        if r.returncode: return r.returncode
    if v.get('workload_mvp',True):
        if ex.get('mode','cpu')=='cpu': run_cpu(cfg)
        elif ex.get('mode')=='hardware': run_hardware(cfg)
        else: raise SystemExit('execution.mode must be cpu or hardware')
    else:
        workload=v.get('user_workload')
        if not workload: raise SystemExit('workload_mvp is false: set validation.user_workload to a Python file implementing run(config).')
        path=(ROOT / workload).resolve()
        if not path.is_file() or ROOT not in path.parents: raise SystemExit('Custom workload must be a file inside the cloned repository.')
        spec=importlib.util.spec_from_file_location('eqg_user_workload',path)
        if spec is None or spec.loader is None: raise SystemExit('Unable to load the configured custom workload.')
        module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        if not callable(getattr(module,'run',None)): raise SystemExit('Custom workload must expose run(config).')
        result=module.run(cfg)
        print('CUSTOM_WORKLOAD_OPERATIONAL_RUN_COMPLETE')
        if result is not None: print(json.dumps(result,default=str))
    return 0
if __name__=='__main__': raise SystemExit(main())
