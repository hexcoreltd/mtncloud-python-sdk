# GitHub Action: inventory and planning

The composite action at `.github/actions/mtncloud` runs the SDK CLI for
`inventory` or dry-run `plan`. It includes a transport guard that permits GET
requests only. Mocked adapter checks and workflow linting pass; execution on
GitHub-hosted runners and live MTN verification remain pending.

## Run the repository workflow

The manual **MTN Cloud read-only** workflow uses the local action. It has no
push, pull-request or scheduled trigger and requests `contents: read` only.

1. Set repository variable `MTN_CLOUD_LIVE_TESTS=true` to enable its job.
2. Configure the GitHub environment `live-read-only` and store
   `MTN_CLOUD_TOKEN` there as a secret. `MTN_CLOUD_API_KEY` is the workflow's
   fallback secret name; either value is passed to the action's `token` input.
3. Optionally configure `MTN_CLOUD_GROUP` and `MTN_CLOUD_ZONE` for discovery.
4. For planning, set `MTN_CLOUD_TYPE_CODE`, `MTN_CLOUD_SERVICE_PLAN` and
   `MTN_CLOUD_GROUP`. Optional variables are `MTN_CLOUD_ZONE`,
   `MTN_CLOUD_RESOURCE_POOL`, `MTN_CLOUD_LAYOUT`, `MTN_CLOUD_NETWORK_ID` and
   `MTN_CLOUD_ROOT_VOLUME_SIZE_GB`.
5. Select `inventory` or `plan` when dispatching. Leave `only` empty for a
   plan. Inventory defaults to instances, networks and routers; `only` selects
   other supported CLI resources. The job retains an available result file
   for seven days, including partial/failure results when outputs are available.

Environment protection and secret access are configured by repository
maintainers. This change does not create environments, set secrets, dispatch
workflows, publish the action or establish a release tag.

## Use from another repository

After publishing this revision, replace `FULL_COMMIT_SHA` with its full commit
SHA. No action release tag is assumed to exist. A consumer checkout is not
needed for this action to install its own SDK revision.

```yaml
name: MTN Cloud inventory
on:
  workflow_dispatch:
permissions:
  contents: read
jobs:
  inventory:
    runs-on: ubuntu-latest
    timeout-minutes: 15
    environment: live-read-only
    steps:
      - name: Collect inventory
        id: mtncloud
        uses: hexcoreltd/mtncloud-python-sdk/.github/actions/mtncloud@FULL_COMMIT_SHA
        with:
          token: ${{ secrets.MTN_CLOUD_TOKEN }}
          command: inventory
          only: instances,networks,routers
          group: production
```

## Inputs

| Input | Purpose/default |
| --- | --- |
| `token` | Required API credential, supplied from a GitHub secret |
| `command` | `inventory` (default) or `plan` |
| `base-url` | HTTPS origin; defaults to `https://console.cloud.mtn.ng` |
| `timeout` | Per-request seconds, greater than zero and at most 300; default 30 |
| `only` | Inventory-only comma-separated CLI resources |
| `group`, `zone` | Optional discovery scope; group is required for plan |
| `name`, `type-code`, `service-plan` | Required plan selections |
| `resource-pool`, `layout`, `network-id` | Optional plan selections |
| `root-volume-size-gb` | Plan root size; CLI default 10 GiB |

Plan inputs are rejected for inventory; `only` is rejected for plan. Scope
restrictions follow the CLI: for example, volumes do not accept group scope
and storage buckets do not accept either scope. See [planning](cli-planning.md)
for defaults, compatibility checks and resolution limits. The action accepts
structured inputs, with no arbitrary CLI arguments, config execution or
resource-changing command. External-network and security-group overrides are
outside this first action interface.

## Outputs and result files

`exit-code` contains the original CLI code. `result-path` is an absolute path
under the runner's temporary directory. A nonzero code fails the action;
partial inventory remains code 3 and requires an explicit caller policy such
as `continue-on-error` if later steps must continue. Code 0 means discovery
succeeded, not that an instance was provisioned.

The private result file has this envelope:

```json
{
  "schema": "mtncloud.action/v1",
  "command": "inventory",
  "exit_code": 0,
  "result": {"schema": "mtncloud.inventory/v1", "resources": {}},
  "error": null
}
```

`result` contains a projection of the CLI document. Inventory keeps selected
scalar fields such as IDs, names, status, addresses and attachment hints;
nested provider metadata, tags, descriptions and status messages are omitted.
It retains collection counts, scope, timestamps, SDK version and base URL.
Section errors and top-level errors retain typed status/request metadata with
a generic message. Plan results retain the CLI's selected placement and
requested options. Known token occurrences are redacted from result values.
The file still contains tenant inventory and requires appropriate artifact
access and retention. It is not a complete CLI dump or regulatory evidence.

Logs contain masking commands and fixed completion diagnostics, with no raw
CLI/provider output. `GITHUB_STEP_SUMMARY` contains command, code and inventory
counts/failures, or a plan completion message. The action itself does not
upload files; the repository's manual workflow handles optional retention.
Input-validation/bootstrap failures may occur before a result file exists.

## Runtime and verification

The first version supports Linux runners with Bash and preinstalled Python 3
for preflight; `ubuntu-latest` is the reference runner. SHA-pinned setup actions
install Python 3.12 and uv 0.9.26. The action installs its own revision using
`uv sync --locked --no-dev --extra cli` into a fresh temporary environment.
Its dependencies do not modify the consumer's Python environment or lockfile.
It needs network access to GitHub, package indexes and the MTN endpoint;
offline/self-hosted bootstrap support remains pending.

Only the supplied action credential participates in SDK settings; caller
`MTN_CLOUD_*` settings and `.env` files are excluded from configuration, TLS
verification stays enabled, and GET retries are bounded to one retry. Inputs
are passed through environment values and Python argument lists. Credential
masking/output handling follows the [GitHub workflow command reference](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-commands).

```bash
uv run pytest tests/test_github_action.py -q
go run github.com/rhysd/actionlint/cmd/actionlint@v1.7.7 \
  -shellcheck= .github/workflows/mtncloud-read-only.yml
```

Unit checks use mocked MTN responses and isolated runner files. Hosted action
bootstrap, secret/environment configuration, failed-step output retention and
authenticated MTN execution still require an operator-driven workflow run.
