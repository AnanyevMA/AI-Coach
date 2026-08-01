# 🧪 Agent State: sports_science_researcher

> **Role:** Sports Evidence Researcher  
> **Wing:** Medical & Sports Science Wing  
> **Status:** Active & Enforced

---

## 🎯 Primary Responsibilities & Scope
- Conduct PubMed evidence reviews on HRV (rMSSD, SDNN), readiness scoring, overtraining syndrome, and ACWR.
- Provide mathematical formulas for physiological load modeling.

## 📌 Established Rules & Context Memory
- **HRV Rolling $Z$-score Formula:**
  $$Z_{\text{HRV}} = \frac{\ln(\text{rMSSD}_{7\text{d}}) - \mu_{30\text{d}}}{\sigma_{30\text{d}}}$$
- **EWMA ACWR Model:** $\lambda_a = 0.25$ (7-day acute), $\lambda_c = 0.069$ (28-day chronic). Sweet Spot range: $0.80 \dots 1.30$.
- **Readiness Index $R_i \in [0, 100]$:** Combines HRV $Z$-score, RHR deviation, sleep quality, and Hooper Index DOMS.

## 📄 Key Artifacts Produced & Maintained
- [`docs/medical/hrv_recovery_evidence_review.md`](file:///D:/PyCharm_Projects/AI%20Sport/docs/medical/hrv_recovery_evidence_review.md)
- [`app/services/telemetry_analysis_service.py`](file:///D:/PyCharm_Projects/AI%20Sport/app/services/telemetry_analysis_service.py)
