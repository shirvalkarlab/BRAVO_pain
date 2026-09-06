# BRAVO local Git checkpoints

Follow the installed universal `rigorous-project-workflow` skill's
`references/git-checkpoints.md`. The user explicitly requires regular local
commits. Local checkpoints do not authorize pushing to either upstream remote.

Commit coherent validated units promptly. Perform a commit check after 30 minutes
of active editing or 10 substantively changed source/config/test files, whichever
comes first, and before long dependent runs, deployment, handoff or pause. End
each checkpoint with a reviewed commit, an explicitly incomplete WIP checkpoint,
or a concrete recorded exception and its next resolution step.

This checkout's working branch is `aditya`. Preserve the pristine source-tracking
branches and all unrelated dirty/staged work. One agent owns the index at a time.
Stage exact reviewed paths/hunks, inspect the full staged diff, and validate the
candidate with its prerequisites against HEAD. Exclude credentials, patient data,
private exports, analysis outputs and incidental build churn. A broad dirty tree
does not justify either skipping a separable unit or committing every file.

Before declaring a task checkpointed, report the local SHA, scope of validation,
remaining uncommitted work/reason and push status. Distinguish a complete deployed
workspace from a clean committed source snapshot when older uncommitted runtime
dependencies remain. Never claim one is the other.

The global skill lives outside Git on this machine. Changes to that canonical
skill must be verified there; this project document records the local application
of the rule, not a duplicate global skill or permission to initialize a new repo.
