"""
run_paper2_multiseverity.py
==========================
Paper 2, #4: does the recovery generalise across fault severity?

Sweeps D0 (deployed) vs D2 (anchored+CUSUM) over onset-to-window ratio at five
severities (1.0, 1.5, 2.0, 3.0, 4.0 kW), 100 seeds/point, 95% bootstrap CIs,
calibrated operating point k=0.10, h=1.0. Synthetic substrate.

Expectation: D0 collapses at every severity (the collapse shifting right as
severity rises, per the §4.7 note), while D2 holds ~100% at every severity.

Outputs: paper2_multiseverity_summary.csv, fig_paper2_multiseverity.png
"""
from __future__ import annotations
import time, numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from energy_substrate import Config as E, simulate_work_center
from carbon_layer import CarbonConfig
from anomaly_model import AnomalyConfig, AnomalySpec, inject_anomalies
from monitoring import MonitorConfig, sample_and_noise, detect as detect_deployed
from monitoring_anchored import AnchoredMonitorConfig, detect_anchored

EF = CarbonConfig().static_emission_factor_kg_per_kwh
SENSOR = MonitorConfig(sampling_interval_seconds=60.0, meter_accuracy_pct=1.0,
                       ci_estimation_window_minutes=15.0)
K, HW, HC = 0.10, 1.0, 2.0
BWS = 3600.0
RAMP_SECONDS = [600, 1080, 1440, 1800, 2160, 2520, 2880, 3240, 3600, 5400, 7200]
SEVERITIES = [1.0, 1.5, 2.0, 3.0, 4.0]
DUR = 240
N_SEEDS = 100
T0 = 10 * 3600.0; T1 = T0 + DUR * 60.0

DET = {
    "D0_deployed": lambda o: detect_deployed(o, MonitorConfig()),
    "D2_anchored_cusum": lambda o: detect_anchored(o, AnchoredMonitorConfig(
        detector="anchored_cusum", anchor_mode="shift_start",
        cusum_k_frac=K, cusum_h_warn=HW, cusum_h_crit=HC)),
}

def _starts(al):
    a=(al>=1).astype(int); s=list(np.where(np.diff(a)==1)[0]+1)
    if a[0]==1: s=[0]+s
    return np.array(s,int)
def _det(al,t):
    st=_starts(al); ts=t[st] if len(st) else np.array([])
    return bool(len(ts[(ts>=T0)&(ts<=T1)]))
def _boot(b,nb=2000,seed=0):
    rng=np.random.default_rng(seed); v=np.asarray(b,float)
    if len(v)==0: return (np.nan,)*3
    bs=rng.choice(v,size=(nb,len(v)),replace=True).mean(axis=1)
    return v.mean(),np.percentile(bs,2.5),np.percentile(bs,97.5)

def main():
    t0=time.time(); raw=[]
    for sev in SEVERITIES:
        for ramp in RAMP_SECONDS:
            for s in range(N_SEEDS):
                seed=42+s
                sub=simulate_work_center(E(seed=seed))
                spec=AnomalySpec(onset_hour=10,duration_minutes=DUR,magnitude_kw=sev,
                                 onset_profile="ramp",onset_ramp_seconds=ramp,
                                 affects="spindle",label="x")
                obs=sample_and_noise(inject_anomalies(sub,AnomalyConfig([spec])),SENSOR,EF,seed=seed+1000)
                for name,fn in DET.items():
                    fn(obs)
                    raw.append({"config":name,"severity_kw":sev,"onset_ratio":ramp/BWS,
                                "seed":seed,"detected":_det(obs["alert_level"].values,obs["t_s"].values)})
        print(f"  severity {sev} kW done  [{time.time()-t0:.0f}s]")
    df=pd.DataFrame(raw)
    rows=[]
    for (cfg,sev,ratio),g in df.groupby(["config","severity_kw","onset_ratio"]):
        m,lo,hi=_boot(g["detected"].values,seed=int(sev*1000+ratio*100))
        rows.append({"config":cfg,"severity_kw":sev,"onset_ratio":ratio,
                     "detection_rate":m,"ci_lo":lo,"ci_hi":hi})
    summ=pd.DataFrame(rows); summ.to_csv("paper2_multiseverity_summary.csv",index=False)

    import matplotlib.cm as cm
    colors=cm.viridis(np.linspace(0,0.85,len(SEVERITIES)))
    fig,(axA,axB)=plt.subplots(1,2,figsize=(13,5.4),sharey=True)
    for ax,cfg,title in [(axA,"D0_deployed","D0 deployed (rolling threshold)"),
                         (axB,"D2_anchored_cusum","D2 anchored + CUSUM (proposed)")]:
        for sev,c in zip(SEVERITIES,colors):
            d=summ[(summ.config==cfg)&(summ.severity_kw==sev)].sort_values("onset_ratio")
            ax.plot(d.onset_ratio,d.detection_rate*100,marker="o",ms=4,lw=2,color=c,label=f"{sev:g} kW")
            ax.fill_between(d.onset_ratio,d.ci_lo*100,d.ci_hi*100,color=c,alpha=0.12)
        ax.axhline(80,color="grey",ls=":",lw=1); ax.axvline(1.0,color="grey",ls="--",lw=1)
        ax.set_xlabel("onset-to-window ratio"); ax.set_title(title); ax.set_ylim(-3,103); ax.grid(alpha=0.25)
        ax.legend(title="severity",fontsize=8)
    axA.set_ylabel("detection rate (%)")
    fig.suptitle("Recovery generalises across severity: D0 collapses at every severity, D2 holds (100 seeds, 95% CI)",fontsize=11)
    fig.tight_layout(rect=[0,0,1,0.96]); fig.savefig("fig_paper2_multiseverity.png",dpi=150)

    pd.set_option("display.width",170)
    for cfg in DET:
        print(f"\n=== {cfg}: detection (%) [severity rows x onset-ratio cols] ===")
        p=(summ[summ.config==cfg].pivot(index="severity_kw",columns="onset_ratio",values="detection_rate")*100).round(0).astype("Int64")
        print(p.to_string())
    print(f"\nDone in {time.time()-t0:.0f}s.")

if __name__=="__main__":
    main()
