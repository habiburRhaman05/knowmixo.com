"""RAG evaluation harness.

Lives at backend/eval/ so it imports the app as a library without
touching production paths. Spec: launch/05-RAG-V2-SPEC.md §8.

CLI:

    python -m eval.harness --config baseline_v1
    python -m eval.harness --config v2 --ship-gate
"""
