"""The workflow engine.

Six modules, each with one job:

    catalogue.py  which node types exist and what category each belongs to
    steps.py      the shape of execution_log, and the accumulator that builds it
    graph.py      React Flow nodes and edges parsed into something walkable
    policy.py     the refusals from AI_CALL_SAFETY_POLICY.md, as code
    nodes.py      one handler per node type
    runner.py     creates the run row, walks the graph, parks, resumes

Read AI_CALL_SAFETY_POLICY.md before changing policy.py or the call_patient
handler in nodes.py. The refusals there are the reason this engine is allowed
to dial a patient at all.
"""
