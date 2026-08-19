# Claim ladder

Keep different sources of improvement separate.

| Rung | What changed | Defensible wording |
|---|---|---|
| D0 | Nothing; frozen base | “Base measurement” |
| D1 | Runtime selection or decoding | “Selection improved the chosen output” |
| D2 | Context, tools or workflow | “The system improved around the same weights” |
| D3 | Adapter or other learned weights | “Weight adaptation improved the same base” |

A D1 gain is not a training gain. A D2 gain is not evidence that weights
learned. A D3 result is not an official benchmark unless it is measured by the
official evaluator under its rules.

If more than one rung changes between arms, publish the result as a system
delta and avoid attributing it to a single component.
