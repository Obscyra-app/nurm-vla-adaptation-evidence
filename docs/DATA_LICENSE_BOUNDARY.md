# Data-license publication boundary

Open weights, open source code and open evaluation data are three different
questions. Check all three independently.

## Release gate

Before publishing any result card:

1. identify every model, dataset, label source and evaluator involved;
2. preserve the exact license or permission version used;
3. check whether outputs, derivatives, benchmark results and performance data
   may be disclosed publicly;
4. record the permission basis in the result card;
5. exclude all bytes and measurements whose publication right is unclear.

The schema in this repository requires `public_disclosure_allowed: true` and
a non-empty `permission_basis` plus `permission_reference`. This is an
attestation, not a legal opinion; the publisher remains responsible for its
accuracy.

## PhysicalAI-AV example

NVIDIA's Alpamayo 2 Super model weights are released under OpenMDW-1.1, while
the associated source repository is Apache-2.0. The PhysicalAI Autonomous
Vehicles dataset has separate terms. Its confidentiality definition includes
the dataset, its output, and benchmarking, competitive-analysis, regression or
performance data relating to the dataset.

Therefore this repository does not include real experiment measurements,
frames, outputs or identifiers from that dataset. Written permission from the
rightsholder—or a different data source whose terms allow publication—is the
clean path to a numeric public report.

Official references:

- <https://huggingface.co/nvidia/Alpamayo2-Super>
- <https://github.com/NVlabs/alpamayo2>
- <https://huggingface.co/datasets/nvidia/PhysicalAI-Autonomous-Vehicles/tree/main/reasoning>

This document is an engineering publication gate, not legal advice.
