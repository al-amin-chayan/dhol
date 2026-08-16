# prompts/

Brand-agnostic LLM prompt templates (research, ideation, caption drafting,
metrics summarisation). Brand voice comes from the brand profile at render
time — a prompt that names a brand belongs in `brands/`, not here.

Each prompt manifest now defines cost/rate bounds (`max_tokens`, `max_cost_usd`,
`retry_policy`), model capability (`model`), structured output (`output_schema`)
and safety/disclosure policy.
