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

Since **0.12.0 the organism gave its blood for a full workup**: hematology re-reads all poured blood against the schema (SPEC-0003 v0.4.0 §6), an OSV scan hunts known pathogens in the feed (pip-audit), dependabot delivers antigens weekly, and OpenSSF Scorecard issues the immunity passport.

Since **0.13.0 the organism has transplantology** ([SPEC-0009](specs/SPEC-0009-transplant.md), [ADR-0011](docs/adr/ADR-0011-donation-protocol.md)): a donation protocol — blood leaves for upstream only by handshake (DCO) and only to those who donate; the CLA collar is not signed — the patch lives inside the body.

Since **0.14.0 the whole registry is visible**: 18 donation cards — every patch-target organ typed with live facts (2026-11-02); the body donates only to those who donate.

Since **0.15.0 the body requires no channel** ([SPEC-0010](specs/SPEC-0010-persona.md), [ADR-0012](docs/adr/ADR-0012-persona-channels.md)): the mandate — «I am blind, I am deaf, I am mute, I have no hands». Text is the universal nerve in both directions: everything the organism says is text (markdown, JSONL blood, worded gate summaries like `IMMUNE: 41 ok, 0 failed` plus exit codes), everything it hears is text (commands, YAML data, environment variables). Pictures never speak alone — the excalidraw organ map has a text twin ([docs/organ-map.md](docs/organ-map.md)) generated from the same live registry; control is one command, no combos or timings. The persona-proof is Helen Keller: 578 days of sight and hearing across 32,115 days of life — and 12 books ([runs/2026-11-02-persona/](runs/2026-11-02-persona/report.md)).

Since **0.16.0 the house has hygiene**: the doctor ([`scripts/doctor.py`](scripts/doctor.py)) catches docs-drift on the machine — stale counters, versions, broken and orphan links, paths, SPEC/ADR refs, entry points — a flea paints the PR red; self-portraits are under a freshness gate (`--check` in CI).

Since **0.17.0 the organism passed the red run** ([runs/2026-11-02-red-run/](runs/2026-11-02-red-run/report.md)): organ swap without touching the brainstem, simultaneous failure without a crash, restoration from blood, 10/10 whitelist attacks repelled — the external-review audit matrix is closed frame-wise; the honest A/B usefulness still belongs to the live host.

Since **0.18.0 the house cleans itself on schedule**: the sweep ([`.github/workflows/fleas.yml`](.github/workflows/fleas.yml)) — the doctor and external links (lychee) weekly, no pushes required: links die on their own, not only from pushes; conflict markers and stale counters (acceptance/practice counts, badge versions) are under the doctor's gates.

Since **0.19.0 the gates have no blind spots**: ROADMAP is under the stale-counter gate (historical acceptance counters swept out — the live number lives in `python -m pytest -q`), and the version is verified in both READMEs — ru and en no longer drift silently; this very file caught up three releases (0.16.0–0.18.0), the blind spot made visible.

Since **0.20.0 the machine imagines the people itself** ([docs/personas.md](docs/personas.md)): a registry of personas × wants × status × links — from the Human (PID 1) to the upstream maintainer, the passer-by, the external reviewer and the future contributor; an orphaned want or one without a verdict is a flea (the doctor's `wants` gate), and the honest backlog holds the A/B and the live red-run until a host appears. With **0.21.0 the spikes are measured wherever a host already exists**: S6 — a live bench of all three memory engines (Python 3.12; chromadb 1.5.9, lancedb 0.41.0, sqlite-vec 0.1.9): sqlite-vec 4.0/6.5 ms vs the 41.4/224.5 ms baseline — chosen by metrics, not by fashion; wiring it into the manifest is a separate wave per the ADR-0005 ritual ([`spikes/s6-memory/`](spikes/s6-memory/)); S5 — the full cycle with live specify 1.2.6.dev0: init structure and section mapping verified, the genome gap honestly named (no pair for Guarantees — spec-kit plays that role with Success Criteria/Measurable Outcomes) ([`spikes/s5-genome/`](spikes/s5-genome/)); S1/S3/S4 keep waiting for live servers and a browser — no fantasizing.

Since **0.22.0 authority is enforced at runtime** (SPEC-0002 v0.4.0): the guard (an audit hook) interrupts any organ call that steps beyond the declared `fs`/`network`/`process` powers before the violation happens — `security.violation` in the blood, the trace closed with reflect+halt; the manifest carries an executable, fail-closed authority grammar; an impostor adapter is refused at binding — see [`runs/2026-11-02-wave7-authority/`](runs/2026-11-02-wave7-authority/report.md). Since **0.23.0 the guard knows paths and ports** (SPEC-0002 v0.5.0): the `{mode, paths}` scope confines an organ to the declared directories (realpath-checked, symlink escape closed), `{hosts, ports}` — to the declared ports; an unset variable in authority paths means the organ is not deployed (§6); the house manifest is migrated — ollama/llama.cpp are port-scoped, browser-use writes only into its downloads directory — see [`runs/2026-11-02-wave9-scopes/`](runs/2026-11-02-wave9-scopes/report.md). Since **0.26.0 the organism recovers from blood** (SPEC-0003 v0.5.0, wave 10): the journal is a chain of envelopes (`prev_id`), a gap is caught at read time (`verify`, hematology fails the file), poured blood without a chain stays valid forever; a brainstem session is reconstructed from the journal in full — plan, calls, verdicts, halts and price (`blood.resume`), a gap honestly drops `complete` — see [`runs/2026-11-02-wave10-resume/`](runs/2026-11-02-wave10-resume/report.md). Since **0.27.0 the organism has compared itself to itself on a live host** (wave №10, wants W-0011 and W-0012 served together — neither excludes the other): a live GLM (via the `z-ai` CLI) planned and solved a task through real organs — the "with organism" group solved it in 3 of 3 seeds, recovered through a reserve organ after a live organ failure, and had its bait cut by the guardian **before** the fact (the witness service saw zero connections); the "without" group (a bare dispatcher over the same organ classes) lost the task three times, leaked for real, and left zero blood envelopes; the live red-run repelled fs/network renegades before the fact, survived a hard process death by restoring from blood — and surfaced a blind spot: child processes (`process: spawn`) carry network traffic out of the guardian's sight (SPEC-0002 v0.6.0 candidate) ([`runs/2026-11-02-wave10-ab-live/`](runs/2026-11-02-wave10-ab-live/report.md), [`runs/2026-11-02-wave10-red-run-live/`](runs/2026-11-02-wave10-red-run-live/report.md)). Since **0.28.0 the guard is inherited by threads** (SPEC-0002 v0.6.0, wave 11): powers bind the organ's code, not the execution thread — a thread born under the guard inherits it (a `Thread.start` wrapper), the `threading.Thread` escape is closed; a grandchild thread and a Thread subclass are guarded too; a lazy-import `__pycache__` write is interrupted with a warm-up-your-imports prescription; a thread born outside the call is an action boundary, not a hole — see [`runs/2026-11-02-wave11-threads/`](runs/2026-11-02-wave11-threads/report.md). Since **0.29.0 child processes live under the guard** (SPEC-0002 v0.7.0, wave 12): execve kills the audit hook, but the guard wraps `subprocess.Popen` — a Python child receives the `COMMONS_AUTHORITY` envelope, loads the guard at startup (`sitecustomize`, a corrupted envelope means exit before the first statement) and lives under the organ's powers; a grandchild inherits the same way, inheritance survives a foreign shell; the `{mode: spawn, programs, max_children}` scope declares birth; a foreign binary does not read the envelope — an honest boundary — see [`runs/2026-11-03-wave12-children/`](runs/2026-11-03-wave12-children/report.md). Since **0.30.0 the house narrows child powers by name** (wave №12, beat 2): on top of guardian inheritance (0.29.0), house manifest v0.5.0 declares the children of stdio organs in the process-axis scope (`{mode: spawn, programs: [...]}`) — "name what you spawn": markitdown and browser-use are named, http organs stay `process: none` ([`runs/2026-11-03-wave12-children/`](runs/2026-11-03-wave12-children/report.md)). Since **0.31.0 children are chained by the kernel** (SPEC-0002 v0.8.0 §11, wave №13): the process scope accepts `sandbox: {network: none}` — a seccomp-BPF filter is applied before execve (`socket(AF_INET/6)` → EPERM) and is inherited by execve across the whole descendant tree regardless of language: a non-python child is kernel-denied exactly like a python one, no envelope needed; unix lives, the filter cannot be removed; seccomp does not restrict fs — Landlock waits for kernel ≥ 5.13, recorded as a candidate ([`runs/2026-11-03-wave13-sandbox/`](runs/2026-11-03-wave13-sandbox/report.md)). Since **0.32.0 the kernel is not blind where the audit grammar is** (SPEC-0002 v0.9.0 §11, wave №13 beat 2): UDP `sendto` and ctypes raw syscalls are not audit events (findings U1/C13: the guard was blind — the datagram went out silently), the sandbox denies `socket()` of any domain before the child's code — defense in depth; the R1 boundary is honestly named: a child connects through an inherited descriptor (`pass_fds`, created before the guard) with a raw connect — the filter denies `socket()`, not `connect`; the prescription acceptance will turn red when R1 is closed, until then the host's remedy is not to hand network fds to children ([`runs/2026-11-03-wave13-seccomp/`](runs/2026-11-03-wave13-seccomp/report.md)).

Since **0.23.0 the doctor traps poison and reports to machines** (wave №9, beat 1): the secrets gate hunts exposed keys (GitHub/AWS/Slack/Google/PEM shapes) in the statics and in the blood (runs/) — every catch is masked in the report, the trapper does not multiply what it traps; `--json` makes every run machine-readable for colleague agents (wiring the trace into the gates themselves is beat 2, waiting for a key with the `workflow` scope).

Since **0.24.0 beat 2 is delivered** (a key with the `workflow` scope): the doctor's table in the summary and a doctor-report.json artifact on every ci.yml and fleas.yml run, plus `timeout-minutes` on all jobs and `concurrency` — the gates do not hang. Since **0.24.1 the sweep does not blush at someone else's walls**: medium.com (403 to datacenter bots, live run 41471082096) is excluded from lychee; the same live run proved the gates' memory works — the artifact exists. Since **0.25.0 the guard knows paths and ports** (SPEC-0002 v0.5.0, beat 3 of wave 9): the `{mode, paths}` scope confines an organ to the declared directories (realpath-checked, symlink escape closed), `{hosts, ports}` — to the declared ports; an unset variable in authority paths means the organ is not deployed (§6); the house manifest is migrated — ollama/llama.cpp are port-scoped, browser-use writes only into its downloads directory — see [`runs/2026-11-02-wave9-scopes/`](runs/2026-11-02-wave9-scopes/report.md).

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
