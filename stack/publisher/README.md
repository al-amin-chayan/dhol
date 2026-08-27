# Publisher mapping and selected adapter

DG-01 selected Postiz `v2.23.0`. `postiz/` is therefore the only deployable
adapter; the Mixpost files under `infra/tests/publisher-eval/` remain decision
evidence and are not production desired state.

Each project gets one Postiz organization, one scoped public-API credential and
one logical workspace. Because this Postiz edition exposes organizations—not a
separate workspace object—the neutral `workspace_id` must equal the
`organization_id`. Brand account entries record unique integration and provider
grant IDs with their owning project. Cross-project credential, account or grant
reuse fails validation.

Real mappings are added only after the founder-approved connection gate. Until
then, the three generic fixtures prove two isolated account-owning projects and
a third project with no connected account. Every mapping requires current,
content-hash-bound human approval; the mapping itself cannot schedule a post.

No API key, OAuth token or provider credential belongs here. Mappings reference
catalog IDs whose values live only in project-scoped SOPS ciphertext or in the
provider/Postiz state covered by the recovery contract.
