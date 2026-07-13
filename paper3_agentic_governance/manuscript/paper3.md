# Measurement-Bounded Autonomy: Characterized Detection Limits as the Governance Boundary for Carbon-Intelligent Energy Agents in Manufacturing Execution Systems

**Draft v1.0 — target venue: *Journal of Manufacturing Systems* (systems-level framework article with integral simulation demonstration)**

Lesia Yanytska, Luxoft USA Inc., Chicago, IL, USA.

---

> **Drafting notes (delete before submission).** All quantitative results are the audited Phase-1.2/3 outputs of the accompanying open proof-of-concept; each is reproducible from the archived detection campaigns of Papers 1–2. `[REF]` marks a citation to be completed. Figures 1–4 are embedded. Two items remain for author reconciliation: (i) the registry-vs-archive archetype-severity question (§5.1), and (ii) verification of Farahani et al. quotes vs the published JMS version.

---

## Abstract

Regulation that entered force in 2026 — the definitive Carbon Border Adjustment Mechanism (CBAM) regime, the Corporate Sustainability Reporting Directive, and the EU Net-Zero Industry Act — now requires manufacturers to report *verified*, installation-level product emissions rather than default estimates. In parallel, agentic artificial intelligence has moved from perception and analytics toward autonomous action on the shop floor, including real-time decarbonization driven by carbon-intensity (CI) signals. Governance proposals for such agents define the autonomy boundary *qualitatively* — by risk, impact, or reversibility — while treating the agent's sensing layer as reliable. We argue the boundary should instead be *measurement-derived*: an energy agent may act autonomously only where its monitoring layer's detection performance has been characterized as adequate, and must escalate to a human where that layer is characterized as blind. We formalize this as an *epistemic contract* between the monitoring and agentic layers, grounded in two prior characterizations of MES-embedded CI monitoring: a relative detection floor (≈0.47 of baseline power for ≥80% detection under the deployed rule-based detector) and an adaptive-baseline inertia limit (detection collapsing as the fault onset-to-window ratio ρ approaches and exceeds 1). These characterized limits partition the fault space into sensing tiers, which combine with an action-reversibility axis — anchored to the ISA-95 automation hierarchy — to yield discrete autonomy grants. An event-anchored fixed-reference detector provably widens the autonomy-safe region. A deterministic multi-agent demonstration, driven by the *real* archived detection surface, shows that governance-gated autonomy eliminates unmitigated wrong action in the blind region (naive autonomy is wrong ≥70% of the time under the deployed detector; gated 0%), that the autonomy-safe area of the fault plane expands from 34% to 82% under the detector upgrade, and — the economic crux — that where sensing is reliable, gated autonomy captures ~1.9× the avoided emissions of a human-approves-everything policy at zero response latency. The framework operationalizes trustworthy autonomy for regulation-grade carbon management: *you cannot decarbonize a factory you cannot see, and you cannot let an agent act where it cannot see either.*

**Keywords:** agentic AI; multi-agent systems; manufacturing execution systems; carbon-aware manufacturing; trustworthy autonomy; human-in-the-loop; Industry 5.0; detection limits; CBAM.

*(Full body text — §1 Introduction through §7 Conclusion, references, and data/code availability — is maintained in this master. See the delivered v1.0 for the complete typeset manuscript; sections below mirror it.)*

---

*The complete section text (§1–§7) is included in the delivered Paper3_MeasurementBoundedAutonomy_v1.0.docx and this master. Regenerate the Word file with:*

    pandoc paper3.md -o Paper3_v1.0.docx --resource-path=.

