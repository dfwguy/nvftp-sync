# Run synchronization

Normal operation is automatic:

- A target-project schedule runs inbound synchronization.
- A target default-branch push runs outbound publication.

For an initial inbound test, open **Build → Pipelines → New pipeline** in the
target project and select its default branch. No selector variable is required.
There is no manual outbound selector; only an approved default-branch content
change can publish.
