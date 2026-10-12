# Professor Praxis

**Community preview · v0.1.0 · MIT licensed · a local-first learning assistant for Hermes Agent**

Before you spend an hour watching a tutorial, Professor Praxis helps you decide whether to watch, listen, read, skim or skip it. It explains useful ideas, compares them against your recorded library, and saves source-grounded study guides with platforms, MCPs, CLIs and other tool leads worth investigating.

The dashboard keeps the original yellow, black and cream printed-study-guide design. It is a read-only view of your own notes and assessments, not a new cloud account.

## What is included

* A self-contained `professor-praxis` Hermes skill.
* A standard-library Python validator, scoped workspace CLI and local dashboard renderer.
* First-run setup, evidence schema, privacy boundaries and synthetic offline tests.
* An empty library on first setup. Example records are never loaded automatically.

**No creator's personal library, transcripts, vault, credentials, account connections or populated dashboard are included.** You use your own Hermes model/provider and authorize your own research tools.

## What it does not do

The Python helper does not call an LLM or transcribe videos. Hermes performs acquisition, reading, research and assessment using your available tools. If a transcript cannot be obtained, the result remains metadata-only/Unknown.

There is no hosted processing backend, automatic Obsidian watcher, scheduled crawler, built-in cloud deployment or account connection setup in this preview. Saving an assessment does not mark anything watched, learned, mastered or applied. Comparisons cover your recorded library, not everything you know.

## Requirements

1. **Hermes Agent**, installed and configured with your own model/provider. See the [official installation guide](https://hermes-agent.nousresearch.com/docs/getting-started/installation).
2. **Python 3.14 or newer** for the bundled helper. Check with `python --version`; some macOS/Linux systems use `python3` instead. No pip packages are required for normal use.
3. A private workspace directory and a Markdown notes folder that you approve. Obsidian is optional.

The code is intended for Windows, macOS and Linux. Windows with Python 3.14 was actually exercised; macOS/Linux portability has not been independently exercised. Tests and four-width browser checks are not a claim of physical-device testing.

## Install without Git experience

### 1. Get a copy

Open this public repository, click the green **Code** button and choose **Download ZIP**, then extract it. No repository invitation is required. Keep this software folder separate from your personal notes and runtime workspace.

If you prefer Git:

```text
git clone https://github.com/TheFoundry1720/professor-praxis-community.git
cd professor-praxis-community
```

This repository is public and can be downloaded without a GitHub account. Your learning workspace stays private on your machine; nobody inherits the creator's notes, credentials or connected accounts.

### 2. Install the skill into your selected Hermes profile

Ask Hermes to identify the **active profile's home directory**. Use that exact path rather than copying a path from another person's computer.

In a terminal opened in the extracted software folder:

```text
python install_skill.py --hermes-home "YOUR_ACTIVE_HERMES_HOME"
```

This copies the canonical seven-file skill into `YOUR_ACTIVE_HERMES_HOME/skills/professor-praxis` and generates one **local-only** `.praxis-install-origin.json` there. It records the canonical source-release and installed-skill paths so the CLI still refuses runtime data overlapping the original release after installation, even if that source folder is moved or deleted. The origin file is not shipped, copied from source, or suitable for sharing; it contains local machine paths. Its schema is exactly `{schema_version: 1, source_release: absolute_path, installed_skill: absolute_path}`. Missing, malformed, linked or mismatched origin metadata fails closed outside a recognizable source checkout. Reinstall from source into a fresh selected location rather than editing/removing metadata or copying installed scripts. A moved release is also rejected when the selected root has a recognizable release-layout ancestor; there is no global folder scan.

The installer does not request passwords, edit Hermes settings/configuration, connect accounts, create a workspace or overwrite an existing skill. Source release and selected Hermes home must be disjoint. A name collision or existing install stops with an error; this preview has no automatic upgrade/removal command. Source-relative package paths remain portable; no machine paths are embedded in shipped source.

The installer is a local-copy helper, **not the Hermes Skills Hub security scanner**. Review the source before running it. The [official skills documentation](https://hermes-agent.nousresearch.com/docs/user-guide/features/skills) explains Hub scanning and local skill directories.

Start a new Hermes conversation if the new skill is not visible yet.

### 3. Onboard once

Tell Hermes:

> Use Professor Praxis. Help me set up a fresh personal learning library. Ask which private workspace and Markdown notes folder to use; do not use another person's paths or data.

Hermes resolves the installed skill directory, then runs:

```text
python "SKILL_DIR/scripts/praxis_cli.py" init --workspace "YOUR_PRIVATE_WORKSPACE" --notes-root "YOUR_APPROVED_NOTES_FOLDER" --vault-name "Your Learning Library" --realm personal
```

All capitalized paths are placeholders that must be replaced. Workspace and notes paths must be **absolute, disjoint, traversal-free, and outside the source repository**, with existing parent directories and no symlink/junction ancestry. Initialization creates the selected roots if absent; it refuses a nonempty uninitialized workspace or incompatible config. For Obsidian links, select a notes root directly inside the named vault. Use `--realm work` for a separate work workspace, not a mixed personal/work library.

Then:

```text
python "SKILL_DIR/scripts/praxis_cli.py" refresh --workspace "YOUR_PRIVATE_WORKSPACE"
```

Open the reported dashboard file in your browser. A fresh setup should show **zero sources**.

### 4. Use it

In Hermes:

> /professor-praxis Assess this source before I spend time on it: [your URL]. Explain the useful ideas, compare with my recorded library, save a study guide, and include relevant tool leads. Do not install or connect anything.

A supplied transcript/text is also supported. Metadata alone cannot support a confident content assessment. If you ask for deeper explanation or practice, Hermes can extend the guide; it will not invent consumption or mastery events.

## CLI reference

Resolve `SKILL_DIR` to your installed skill folder. All state-changing commands require an explicit workspace.

```text
python "SKILL_DIR/scripts/praxis_cli.py" status --workspace "YOUR_PRIVATE_WORKSPACE"
python "SKILL_DIR/scripts/praxis_cli.py" validate --record "YOUR_CANDIDATE_JSON" --realm personal
python "SKILL_DIR/scripts/praxis_cli.py" compare --workspace "YOUR_PRIVATE_WORKSPACE" --record "YOUR_CANDIDATE_JSON"
python "SKILL_DIR/scripts/praxis_cli.py" save --workspace "YOUR_PRIVATE_WORKSPACE" --record "YOUR_CANDIDATE_JSON"
python "SKILL_DIR/scripts/praxis_cli.py" refresh --workspace "YOUR_PRIVATE_WORKSPACE"
```

See [the record contract](skills/professor-praxis/references/record-contract.md) for record fields and evidence rules. `compare` returns lexical candidates; it does not independently judge novelty or credibility.

## Privacy and sharing

Your private workspace contains configuration, assessment records and rendered output. Your approved Markdown folder contains your notes. Full source text is retained in private records for quotation validation, not projected wholesale. The dashboard **does include selected note text** and is personal data.

Keep those folders outside the source repository. `.gitignore` is a precaution, not a privacy guarantee; a forced add can bypass it. Never publish a populated dashboard, workspace, screenshots or connection state without a separate review and explicit permission.

Hosting and off-device viewing are optional, separately authorized work—not part of installation. Nobody inherits another user's connected accounts by installing this skill.

## Tests

From the repository root:

```text
python -B -m unittest discover -s tests -v
```

Tests use synthetic data and isolated temporary directories, not the creator's real learning library. Runtime helpers and core tests use only Python's standard library. Optional Node and Playwright/Edge cross-language tests skip explicitly when those tools are absent; Windows symlink tests may skip when the OS denies link creation. Actual Windows junction tests run separately. Browser QA is a release check, not automatic cross-device acceptance. The installer copies an explicit seven-file package manifest and rejects linked ancestry/descendants and unexpected source files.

## Known limits

* Source acquisition depends on the user's available tools, permissions and transcript availability.
* Saved notes render as plain Markdown text in the dashboard dialog.
* Duration labels are rounded hours/minutes; source metadata remains precise.
* Credibility checks are topic-specific, not independent security audits or guarantees of savings.
* The maintained ordinary HTML renderer is supported; foreign SVG/template wrappers are not a general supported input format.
* Locks and corrupt/missing watermark metadata fail closed. Do not delete them automatically to make a command work.
* No automatic legacy-library migration or public hosting is implied by setup. Legacy `log.jsonl` inputs, including empty files, are explicitly rejected. Records use canonical hashed filenames; use `save`, not manual store copies.
* Existing source identity/capture, established note binding and action state are preserved. A first approved note can be attached later; a previous assessment cannot be erased or backdated through `save`.
* `save` writes an assessment only. Hermes writes the Markdown note separately, then explicitly calls `refresh`.

## License and contributions

Created by Joshua Spence with Hermes Agent. This community software and its documentation are distributed under the **MIT license**: you may use, modify and redistribute them, including commercially, while retaining the copyright and license notice. See [LICENSE.md](LICENSE.md). Independently installed Hermes Agent, model providers and research tools retain their own licenses and terms.

Report reproducible software bugs through Issues or propose code changes with a pull request. Use synthetic examples: never attach credentials, personal transcripts, private notes, populated dashboards or installed-origin metadata. This repository receives reviewed software releases; it is not automatically mirrored from private development or personal runtime data.
