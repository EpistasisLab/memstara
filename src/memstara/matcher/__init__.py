"""Semantic matching adapted from afc-forge's ade_forge/tools/impl modules.

Catalog, vocabulary, embedding and scoring adapters retain upstream attribution
in their source headers. Dataset integration and service code are maintained here.
Matching ranks semantic relevance; it does not establish causal relevance or
exclude every possible proxy for the target. Apply the configured data policy.
The local policy adapter supports approved exact-column exclusions and policy
fingerprints; it does not infer exclusions or perform ontology screening.
"""
