# COMMONS (English summary)

> **One organism built from the best open-source projects of humanity.**
> Organs stay alive on upstream — the unity lives in the exchange: genome, synapses, blood, metabolism, immunity.

[Русская версия — основная](README.md)

## What is this

COMMONS is an "organism" project assembled from the top-100 public GitHub repositories (by stars, snapshot of 2026-10-26, kept as data in [`organs/top100-2026-10-26.yaml`](organs/top100-2026-10-26.yaml)).

We deliberately do **not** merge foreign codebases into a monolith — that would create dozens of dead forks. Instead:

- **organs** (openclaw, ollama, llama.cpp, langchain, browser-use, markitdown, excalidraw, etc.) remain living projects on their upstream;
- **the exchange** is unified: one nervous protocol (MCP), one event stream ("blood", JSON-Schema'd envelope), one genome (specs as the source of truth), one metabolism (local inference), one immunity (license firewall).

**The whole is greater than the sum of its parts** — achieved through exchange, not through merging.

Since **0.4.0 the organism lives in time**: PID 1 is a heartbeat daemon (`boot → organ.health → shutdown`); every controlled death is recorded in the blood; a second instance gets a veto; the doctrine is **HUMAN=PID=1** — the human remains the init: no unit files, no autostart, launch and kill are done by human hands only ([SPEC-0004](specs/SPEC-0004-pid1.md), [ADR-0006](docs/adr/ADR-0006-pid1.md), first artifacts in [`runs/2026-11-01-pid1/`](runs/2026-11-01-pid1/)).

Since **0.5.0 the organism has a memory genome** ([SPEC-0005](specs/SPEC-0005-memory.md): memory is a derivative of blood — the journal is the truth, memory is an advisory cache), an engine decision ([ADR-0007](docs/adr/ADR-0007-memory-engines.md), all four vector candidates Apache-2.0, verified via the live GitHub API 2026-11-02), and a second self-portrait — an excalidraw map generated from the live registry ([`docs/organ-map.excalidraw`](docs/organ-map.excalidraw), 36 organs, 13 systems).

Since **0.6.0 memory runs**: graph + vectors + replay from the blood; PLAN reads it read-only; the engine is an organ in the manifest.

Since **0.7.0 immunity runs**: the license barrier as code ([SPEC-0006](specs/SPEC-0006-immunity.md), [ADR-0008](docs/adr/ADR-0008-license-barrier.md)) — rules live in data (`immune/license-matrix.yaml`), an unknown license is rejected from embedding (fail-closed, G1), rules change by editing YAML, not code (G2), and the `python -m immune` gate in CI turns a PR red before AGPL/fair-code enters the body.

Since **0.8.0 metabolism is budgeted** (SPEC-0001 G3): trace-level and per-call limits declared in the manifest (`budget` field), threshold crossing emits an `alert` event into the blood, exhaustion HALTs the loop.

Since **0.9.0 the organism has an external pipeline** ([SPEC-0007](specs/SPEC-0007-pipeline.md), [ADR-0009](docs/adr/ADR-0009-external-pipeline.md)): n8n stays an external node (fair-code, not embeddable — the registry keeps it in `external` mode); the reference deployment and exported workflows are **data** with a command whitelist (organ entry points only), arbitrary shell fails validation (G1 fail-closed); the pulse goes only through the brainstem (`commons-pid1`); the `python -m pipeline` gate in CI turns a violating PR red.

Since **0.11.0 the organism has hands** ([SPEC-0008](specs/SPEC-0008-effector.md), [ADR-0010](docs/adr/ADR-0010-cli-bridge-effector.md)): openclaw is connected behind the brainstem as the effector — a CLI bridge `openclaw gateway call` with a method whitelist (`health`/`status`/`chat.send`/`chat.abort`); parameters are structured data serialized by the body (no shell strings are ever built); hands without will — they execute brainstem impulses, they don't decide; the live gateway and the token stay with the human (PID 1).

## Core artifacts

| Artifact | Purpose |
|---|---|
| `specs/` | Genome: canonical agent loop, MCP synapse contract, blood envelope contract, living organism (PID 1), memory, license immunity |
| `immune/` | License barrier: rules-as-data matrix + `(license, mode) → verdict` + `commons-immune` CI gate |
| `pipeline/` | External pipeline (n8n): reference deployment + workflow data + `commons-pipeline` CI gate |
| `openclaw/` | Effector (openclaw as hands, SPEC-0008): CLI bridge + method whitelist + policy data + `commons-openclaw` CI gate |
| `organs/registry.yaml` | Which organs are connected, in which mode (dependency / adapter / external / reference / substrate), with verified licenses |
| `synapse/mcp-manifest.yaml` | Declarative manifest of organs as MCP servers |
| `blood/envelope.schema.json` | JSON Schema of the event envelope (every call carries its cost) |
| `PROVENANCE.md` | Origin declaration + live-verified license matrix (GitHub API, 2026-11-01) |
| `REUSE.toml` | File-level SPDX licensing (REUSE 3.3), machine-checked in CI |
| `CITATION.cff` | How to cite the project |
| `docs/adr/` | Architecture decision records (the "why") |

## Three laws

1. **Organs live on upstream** — no forks; patches flow back.
2. **No calls bypass the synapses** — every organ call goes through the MCP gateway and is logged with its cost.
3. **The unplug test** — any organ can be pulled out; the organism survives via substitution. Fails the test? It's a parasite, not an organ.

Docs are primarily in Russian. Specs are the source of truth; code comes later.

## Provenance

Nothing here is copied: no foreign code, texts, logos or media — only names, links and verified facts
(live GitHub API license matrix, dated 2026-11-01, in [`PROVENANCE.md`](PROVENANCE.md)). File-level
licensing is machine-checked via REUSE 3.3 ([`REUSE.toml`](REUSE.toml) + `reuse lint` in CI). Every
commit carries a DCO `Signed-off-by` line. Agents should start from [`llms.txt`](llms.txt) and
[`AGENTS.md`](AGENTS.md).

## License

Apache-2.0 — see [LICENSE](LICENSE). Rationale (in Russian): [ADR-0003](docs/adr/ADR-0003-apache-2.0.md).
