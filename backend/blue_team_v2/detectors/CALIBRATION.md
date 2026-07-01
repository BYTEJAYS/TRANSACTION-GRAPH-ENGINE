# Detector Calibration (Phase 4)

Severity is 0–1 "how damning"; confidence is 0–1 "how sure the detector is". The
**risk engine remains the only thing that opens a case** — detectors never trip a
case alone; their severity feeds the cumulative score. Bands below are starting
points, tuned against the synthetic fixtures and the Red-Team FP harness.

| Detector | Min gate | Severity band | Confidence | Notes |
|---|---|---|---|---|
| diamond | ≥2 parallel paths, ≥₹1L split | 0.66–0.97 | 0.84 | +0.06 per chained diamond |
| nested_layering | primary ≥4 hops + branch ≥3 hops | 0.62–0.95 | 0.80 | +0.05 if relay pass-through |
| round_tripping | loop ≤4, ≥₹50k, balance ≤15% | 0.74–0.96 | 0.88 | rotation-independent time order |
| hub_network | ≥4 in AND ≥4 out, ≥₹2L throughput | 0.64–0.96 | 0.83 | distinct from fan-in/out |
| scatter_gather | ≥3 src, ≥3 dst, pass-through ≥0.5 | 0.68–0.97 | 0.85 | core mule-network mechanic |
| structuring | ≥3 transfers in [0.8T, T) | 0.60–0.95 | 0.82 | T = report_threshold() (₹10L default) |
| cash_laundering | ≥₹1L CASH_IN, ≥50% forwarded | 0.66–0.95 | 0.80 | placement stage |
| night_activity | ≥4 txns, ≥60% in 00–05h, ≥₹1L | 0.30–0.70 | 0.60 | supporting signal only |
| weekend_activity | ≥4 txns, ≥70% weekend, ≥₹1L | 0.28–0.65 | 0.55 | supporting signal only |
| temporal_spike | ≥60% value in ≤1h, ≥₹2L | 0.50–0.90 | 0.70 | baseline-free; STL upgrade in Phase 5 |
| uniform_amount | same amount ×≥4, ≥₹20k | 0.50–0.90 | 0.72 | automation/templating signature |

**Precision guard:** `tests/test_wave1_detectors.py::test_benign_no_wave1_noise`
asserts a benign daytime low-value component trips none of these. Add a fixture +
no-fire assertion for every new detector.

**Wave 2/3** (identity rings, profile mismatch, geo, ML-structural) calibrate
once the entity graph / ML models are live; they no-op until then.
