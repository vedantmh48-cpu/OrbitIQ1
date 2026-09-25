"""Historical change analysis pipeline (op: ``change-analysis``).

A dedicated end-to-end feature that answers *"what changed between Date 1 and
Date 2 at this place?"*:

    geocoding -> imagery inventory -> change-detection engine -> AI/VLM report

Everything ships with a dependency-free, deterministic demo engine (pure
Python, no GDAL/NumPy) so the feature runs instantly and offline while staying
honestly labelled. Real STAC scene metadata is kept when reachable and the
optional VLM synthesis is used only when a key is configured.
"""