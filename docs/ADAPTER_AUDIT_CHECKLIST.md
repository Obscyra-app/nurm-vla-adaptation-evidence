# Adapter audit checklist

Use this before accepting or publishing an adapter result.

## Model identity

- [ ] Upstream repository, exact revision and license are recorded.
- [ ] Base checkpoint and processor are identical across both arms.
- [ ] Save/reload preserves the adapter result.
- [ ] No unreported merged or modified base weights are used.

## Trainable surface

- [ ] Every trainable parameter belongs to the declared adapter surface.
- [ ] Parameters outside the adapter are explicitly frozen, not merely missing
      gradients in one observed batch.
- [ ] Frozen visual, projector and action components are byte- or tensor-checked
      before and after training when the claim depends on them staying fixed.
- [ ] Trainable parameter count and fraction of the full model are reported.

## Data separation

- [ ] Train and evaluation are split by clip, scene or another physical group.
- [ ] Near-duplicate frames and repeated events cannot cross the split.
- [ ] The evaluation roster is frozen before the candidate is selected.
- [ ] The data license explicitly permits the intended public disclosure.

## Matched evaluation

- [ ] Inputs, order, seeds and candidate count match across arms.
- [ ] Sampling, prompts, tools and runtime match across arms.
- [ ] A paired confidence interval is reported.
- [ ] Average, ceiling and selected-output quality are not conflated.
- [ ] At least one judge-free corroborating metric is included when a model
      judge is used.

## Claim boundary

- [ ] Internal metrics are not described as an official benchmark.
- [ ] Open-loop text quality is not described as road safety or driving quality.
- [ ] Runtime selection gains are separate from learned-weight gains.
- [ ] Null and negative results are retained rather than silently omitted.
- [ ] Dataset bytes, outputs and performance data are disclosed only when the
      governing license or written permission allows it.
