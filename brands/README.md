# brands/

One YAML file per brand — the platform's only extension point. Adding a brand
means adding a file here, **never** a code change. The file must hold public
editorial intent and secret references only. Schema: `README.md` §4 of the repo
root.

`_template.yaml` is the canonical shape; copy it to `<brand>.yaml`.

Never commit real credentials, chat IDs of private channels, or API tokens
here — reference them by env-var name and keep values on the host.
