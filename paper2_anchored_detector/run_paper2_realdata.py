"""
run_paper2_realdata.py
=====================
Paper 2, #5 Level-2: real-data validation of the inertia result.

Re-runs the onset-ratio comparison of the deployed detector (D0) vs the proposed
anchored+CUSUM detector (D2) on a substrate whose spindle power is REAL measured
Brillinger servo-drive data (energy_substrate_real), instead of the synthetic
Gutowski model. If D0 still collapses and D2 still holds 100% on real spindle
dynamics, the headline result is validated beyond simulation.

Overlays the synthetic curves (from paper2_summary.csv) for direct comparison.
Uses the calibrated operating point k=0.10, h=1.0.

Outputs: paper2_realdata_summary.csv, fig_paper2_realdata.png
"""
from __future__ import annotations
import time, numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from energy_substrate import Config as E
from energy_substrate_real import simulate_work_center_real
from carbon_layer import CarbonConfig
from anomaly_model import AnomalyConfig, AnomalySpec, inject_anomalies
from monitoring import MonitorConfig, sample_and_noise, detect as detect_deployed
from monitoring_anchored import AnchoredMonitorConfig, detect_anchored

EF = CarbonConfig().static_emission_factor_kg_per_kwh
SENSOR = MonitorConfig(sampling_interval_seconds=60.0, meter_accuracy_pct=1.0,
                       ci_estimation_window_minutes=15.0)
K, HW, HC = 0.10, 1.0, 2.0
BWS = 3600.0
RAMP_SECONDS = [120, 300, 600, 1080, 1440, 1800, 2160, 2520, 2880, 3240, 3600, 5400, 7200]
SEV, DUR = 2.0, 240
N_SEEDS = 100
T0 = 10 * 3600.0; T1 = T0 + DUR * 60.0

DETECTORS = {
    "D0_deployed": lambda o: detect_deployed(o, MonitorConfig()),
    "D2_anchored_cusum": lambda o: detect_anchored(o, AnchoredMonitorConfig(
        detector="anchored_cusum", anchor_mode="shift_start",
        cusum_k_frac=K, cusum_h_warn=HW, cusum_h_crit=HC)),
}

def _starts(al):
    a=(al>=1).astype(int); s=list(np.where(np.diff(a)==1)[0]+1)
    if a[0]==1: s=[0]+s
    return np.array(s,int)

def _eval(al,t):
    st=_starts(al); ts=t[st] if len(st) else np.array([])
    w=ts[(ts>=T0)&(ts<=T1)]
    return (True,(w[0]-T0)/60.0) if len(w) else (False,np.nan)

def _fp(al,state):
    oph=(state=="PRODUCTION").sum()*60.0/3600.0
    return len(_starts(al))/max(oph,1e-6)

def _boot(b,nb=2000,seed=0):
    rng=np.random.default_rng(seed); v=np.asarray(b,float)
    if len(v)==0: return (np.nan,)*3
    bs=rng.choice(v,size=(nb,len(v)),replace=True).mean(axis=1)
    return v.mean(),np.percentile(bs,2.5),np.percentile(bs,97.5)

def main():
    t0=time.time(); raw=[]
    for ri,ramp in enumerate(RAMP_SECONDS):
        for s in range(N_SEEDS):
            seed=42+s
            sub=simulate_work_center_real(E(seed=seed))
            spec=AnomalySpec(onset_hour=10,duration_minutes=DUR,magnitude_kw=SEV,
                             onset_profile="ramp",onset_ramp_seconds=ramp,
                             affects="spindle",label="x")
            obs=sample_and_noise(inject_anomalies(sub,AnomalyConfig([spec])),SENSOR,EF,seed=seed+1000)
            for name,fn in DETECTORS.items():
                fn(obs); det,lat=_eval(obs["alert_level"].values,obs["t_s"].values)
                raw.append({"config":name,"ramp_s":ramp,"onset_ratio":ramp/BWS,"seed":seed,
                            "detected":det,"latency_min":lat})
        print(f"  ramp {ri+1}/{len(RAMP_SECONDS)} ({ramp}s) done  [{time.time()-t0:.0f}s]")
    fp={n:[] for n in DETECTORS}
    for s in range(N_SEEDS):
        sub=simulate_work_center_real(E(seed=242+s)).copy()
        sub["anomaly_kw"]=0.0; sub["anomaly_active"]=False; sub["anomaly_labels"]=""
        obs=sample_and_noise(sub,SENSOR,EF,seed=242+s+1000)
        for n,fn in DETECTORS.items():
            fn(obs); fp[n].append(_fp(obs["alert_level"].values,obs["state"].values))
    fp_mean={n:float(np.mean(v)) for n,v in fp.items()}

    df=pd.DataFrame(raw)
    rows=[]
    for (cfg,ramp,ratio),g in df.groupby(["config","ramp_s","onset_ratio"]):
        m,lo,hi=_boot(g["detected"].values,seed=int(ramp))
        rows.append({"config":cfg,"ramp_s":ramp,"onset_ratio":ratio,"detection_rate":m,
                     "ci_lo":lo,"ci_hi":hi,"mean_fp_rate":fp_mean[cfg]})
    summ=pd.DataFrame(rows); summ.to_csv("paper2_realdata_summary.csv",index=False)

    # overlay synthetic (from paper2_summary.csv) if available
    try: syn=pd.read_csv("paper2_summary.csv")
    except Exception: syn=None
    fig,ax=plt.subplots(figsize=(8.5,5.6))
    col={"D0_deployed":"#c0392b","D2_anchored_cusum":"#27ae60"}
    for c in DETECTORS:
        d=summ[summ.config==c].sort_values("onset_ratio")
        ax.plot(d.onset_ratio,d.detection_rate*100,marker="o",color=col[c],lw=2.4,ms=6,
                label=f"{c}  REAL spindle  (FP {fp_mean[c]:.3f}/h)")
        ax.fill_between(d.onset_ratio,d.ci_lo*100,d.ci_hi*100,color=col[c],alpha=0.15)
        if syn is not None:
            ds=syn[syn.config==c].sort_values("onset_ratio")
            ax.plot(ds.onset_ratio,ds.detection_rate*100,ls="--",color=col[c],lw=1.5,alpha=0.7,
                    label=f"{c}  synthetic")
    ax.axhline(80,color="grey",ls=":",lw=1); ax.axvline(1.0,color="grey",ls="--",lw=1)
    ax.set_xlabel("onset-to-window ratio  (ramp time / baseline window)")
    ax.set_ylabel("detection rate (%)"); ax.set_ylim(-3,103)
    ax.set_title("Real-data validation: inertia collapse & recovery on REAL spindle power\n"
                 "(solid = real Brillinger spindle, dashed = synthetic)")
    ax.legend(fontsize=8,loc="lower left"); ax.grid(alpha=0.25)
    fig.tight_layout(); fig.savefig("fig_paper2_realdata.png",dpi=150)

    pd.set_option("display.width",140)
    print("\n=== REAL-SUBSTRATE DETECTION RATE (%) ===")
    print((summ.pivot(index="onset_ratio",columns="config",values="detection_rate")[list(DETECTORS)]*100).round(0).astype("Int64"))
    print("\nFP:", {k:round(v,4) for k,v in fp_mean.items()})
    print(f"Done in {time.time()-t0:.0f}s.")

if __name__=="__main__":
    main()
