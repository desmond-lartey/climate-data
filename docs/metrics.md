# Validation Metrics

The study uses a **dual-class** evaluation framework: continuous metrics
that measure how close a product's values are to the gauge observations,
and categorical metrics that measure how well a product detects the
occurrence of rain.

## Continuous performance

| Metric | Full name | Perfect value | Detects |
|---|---|---|---|
| Bias | Mean error | 0 mm/day | Systematic over/under-estimation |
| PBIAS | Percent bias | 0% | Relative bias, normalised by observed total |
| MAE | Mean absolute error | 0 | Average error magnitude |
| RMSE | Root mean squared error | 0 | Error magnitude, penalises extremes |
| r | Pearson correlation | 1 | Timing and seasonal-pattern agreement |
| r² | Coefficient of determination | 1 | Variance explained |
| NSE | Nash–Sutcliffe efficiency | 1 | Skill vs using the observed mean as predictor |
| KGE | Kling–Gupta efficiency | 1 | Combined correlation, variability, and bias |

KGE is used as the primary single-number summary of continuous skill, as
it balances correlation, variability ratio, and bias rather than
rewarding any one of them alone.

## Categorical (wet/dry detection)

Computed from a 2×2 contingency table of wet/dry agreement between a
product and the gauge observation, at a rain-detection threshold
(1.0 mm/day by default).

| Metric | Full name | Perfect value | Detects |
|---|---|---|---|
| POD | Probability of detection | 1 | Fraction of wet months correctly identified |
| FAR | False alarm ratio | 0 | Fraction of wet predictions that were actually dry |
| CSI | Critical success index | 1 | Combined detection skill |
| ETS | Equitable threat score | 1 | Detection skill adjusted for chance |
| Freq. bias | Frequency bias | 1 | Over/under-prediction of wet frequency |

## Threshold sensitivity

A distinctive contribution of this study is treating the wet/dry
threshold not as a fixed choice but as a variable. Categorical metrics
are recomputed across a sweep of thresholds:

```
0.1   0.5   1.0   2.0   5.0   mm/day
```

The finding: **categorical detection metrics are structurally unstable in
near-zero-rainfall environments.** In the driest zones, small changes in
the threshold produce large swings in POD/FAR/CSI regardless of which
product is used — meaning a single-threshold categorical evaluation can
be misleading in drylands. This has direct implications for how
precipitation products should be validated in arid and semi-arid regions.

## Application-weighted scoring

Individual metrics are combined into a composite score per product, using
weights that differ by **application**. Seven conservation and
water-management applications are considered — each weighting the metrics
differently, because (for example) drought early warning cares most about
detection while hydrological modelling cares most about magnitude and
KGE. The result is a decision matrix: the best product is read off for a
given application **and** a given zone, rather than assumed to be
constant.
