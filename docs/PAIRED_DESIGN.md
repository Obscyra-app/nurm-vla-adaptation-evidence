# Paired adapter evaluation design

The design answers one narrow question:

> Did learned adapter weights improve the same base model on the same held-out
> units under the same generation conditions?

## Required arms

1. **Base arm:** frozen upstream model, no candidate adapter.
2. **Adapter arm:** the exact same frozen base plus the candidate adapter.

The two arms must share:

- exact base checkpoint and processor bytes;
- held-out unit roster and ordering;
- inputs and preprocessing;
- seeds and number of samples per unit;
- sampling and decoding profile;
- runtime and scoring implementation.

The intended difference is the adapter. If tools, context, prompts, selection,
or decoding also change, report a system delta—not a weight delta.

## Split by the physical source

Random rows are often not independent. Driving events from the same clip or
scene can share nearly identical frames. Split and bootstrap by the highest
physical grouping that can leak information, such as scene or clip, and keep
that group entirely on one side of train/evaluation.

## Report both average and ceiling

When each event produces multiple candidates, report at least:

- mean quality across candidates;
- best-candidate quality;
- first or selected-candidate quality;
- candidate diversity.

An intervention can raise the average while lowering the best candidate. A
single aggregate hides that trade-off.

## Pair the statistics

Calculate a per-unit candidate-minus-base difference and derive uncertainty
from paired observations, clustered by the physical source. Report the sample
count, point delta and 95% confidence interval. Do not substitute independent
arm intervals for a paired interval.

## Use an interpretable corroborating metric

If a model-based semantic judge is used, label its scale as internal and add a
judge-free measure where possible—for example token F1, exact match or a
deterministic task-specific check. Keep official benchmark scores separate
from internal evaluation.
