# IMPLEMENTATION

## Goal

Evolve the current Discord bot into a private study assistant for Direito and Programação, with support for:

- academic research with web search and ABNT output,
- code generation with learning-oriented explanations,
- study plans,
- ABNT helper,
- quiz/simulado,
- monitoria de progresso.

The product identity for this target state is **LexNeuro**: a disciplined Discord assistant for legal study, technical learning, and focus-oriented productivity.

## Product guardrails

- Keep the existing single-file bot working while the LexNeuro features are introduced incrementally.
- Do not assume capabilities that the current runtime does not have yet.
- Treat branding, tone, and task routing as separate concerns.
- Prefer grounded educational assistance over broad "assistant for everything" behavior.
- Avoid architecture decisions that fight the current config-driven, OpenAI-compatible design unless there is a clear payoff.

## Reality check against the Gemini description

The Gemini summary is useful for product direction, but some items need reinterpretation for this repo:

- **Language/runtime**: this codebase is already Python and should stay Python for now.
- **Framework**: the bot already uses `discord.py`; that is the correct implementation baseline.
- **AI integration**: "OpenRouter presets" are optional operational convenience, not a core architectural requirement.
- **Secrets management**: the current repo stores provider credentials in `config.yaml`, not `.env`. A future environment-variable migration is possible, but it is a separate task.
- **Hosting**: Railway, Oracle Cloud, Docker, or a VPS are deployment choices, not implementation blockers.

## 0 to HERO path

### 0. Define the contract

Lock the product scope before changing behavior.

**Deliverables**
- Final product positioning for LexNeuro.
- Final list of supported modes.
- Output format for each mode.
- Access rules for the private server.
- Decision on whether the bot responds only through slash commands, mentions, or both.
- Base system prompt that matches the LexNeuro identity and current technical limits.

**Done when**
- The bot has clear task boundaries.
- No feature depends on a vague “generic chat” behavior.
- The default assistant behavior is useful even before advanced modes exist.

### 1. Stabilize the current bot

Keep the existing chat flow working while preparing the new experience.

**Deliverables**
- Preserve Discord connection, permissions, and model switching.
- Keep config-driven behavior.
- Keep response streaming and message caching intact.

**Done when**
- The current bot still behaves correctly after the later task layers are added.

### 2. Introduce task routing

Add explicit task modes instead of relying on one prompt.

**Modes**
- `pesquisa`
- `code`
- `study_plan`
- `abnt`
- `quiz`
- `monitor`

**Deliverables**
- Slash command or message command to pick a mode.
- Shared request object with mode, topic, target audience, and constraints.
- System prompts or templates per mode.
- A safe default fallback mode for generic academic/technical assistance when no explicit mode is chosen.

**Done when**
- The bot can route the same user input into different behaviors safely.

### 3. Build research mode

This mode should gather sources before answering.

**Deliverables**
- Web search step.
- Source ranking by trust and recency.
- ABNT-style report structure.
- Inline citations and bibliography.
- Clear distinction between factual claims and interpretation.
- Clear output behavior when search is unavailable, disabled, or incomplete.

**Done when**
- The bot can produce a research report with traceable sources.

### 4. Build code mode

This mode should help beginners learn from code, not just copy it.

**Deliverables**
- Snippet generation in any requested language.
- Explanations per line or per block.
- Links to official docs and beginner-friendly references.
- Guidance on prerequisites and common mistakes.

**Done when**
- The bot can return code plus learning context in a predictable format.

### 5. Build study-plan mode

Turn topics, deadlines, and availability into a realistic plan.

**Deliverables**
- Intake for subjects, exam date, and study availability.
- Time allocation per topic.
- Review slots and practice slots.
- Adjustments for limited time or heavy content.
- Optional focus-oriented output templates such as Pomodoro blocks, weekly checkpoints, or "pauta" summaries.

**Done when**
- The bot can output a plan that fits the available calendar.

### 6. Build ABNT helper

Make the bot useful for formatting academic material.

**Deliverables**
- Reference formatting.
- Citation formatting.
- Basic structure checks for academic text.
- Conversion of links, articles, and books into ready-to-use references.

**Done when**
- Users can paste material and get ABNT help without rewriting the full content.

### 7. Build quiz and simulado

Use the bot as a practice engine.

**Deliverables**
- Question generation by topic and difficulty.
- Multiple-choice, true/false, and essay prompts.
- Answer correction with explanation.
- Reusable question bank sourced from server materials.

**Done when**
- The bot can create and grade study practice on demand.

### 8. Build monitoria de progresso

Track learning progress for users and for the group.

**Deliverables**
- Topic completion tracking.
- Weak-topic detection.
- Progress summaries.
- Group-level study reports.
- Clear privacy rules for per-user versus group-visible progress data.

**Done when**
- The server can see what is being studied, finished, and missed.

### 9. Add server knowledge

Turn the server’s own materials into a reusable knowledge base.

**Deliverables**
- Ingestion for summaries, notes, and recommendations.
- Search over server-shared content.
- Source tagging by subject and credibility.
- Summaries from uploaded material.

**Done when**
- The bot can prefer the server’s own content when answering study questions.

### 10. Hardening and launch

Make the bot safe and stable for daily use.

**Deliverables**
- Permission rules for private-server use.
- Rate limits and size limits.
- Automatic file export when a response would exceed Discord's 4k text limit.
- Configurable delivery target: server channel, DM, or hybrid fallback.
- Optional short notice in the server when the full response is delivered by DM.
- Clear error handling.
- Logging for failures and task flow.
- Config documentation for the new modes.
- Configuration guidance for secure secret handling, whether that remains `config.yaml` or later moves to environment variables.
- Final review of the base system prompt and per-mode prompts to avoid overlap or contradictory instructions.

**Done when**
- The bot is reliable enough for regular study use.

## Recommended build order

1. Keep the existing bot stable.
2. Define the LexNeuro base prompt and behavioral contract.
3. Add task routing.
4. Build research mode.
5. Build code mode.
6. Build study-plan mode.
7. Add ABNT helper.
8. Add quiz/simulado.
9. Add monitoria.
10. Add server knowledge features.
11. Add configurable DM delivery.
12. Harden and document everything.

## Non-goals for the first pass

- Full fine-tuning before prompt and workflow validation.
- A complex multi-service architecture too early.
- Rewriting the whole bot before the feature set is validated.
- Building mascot-heavy or aesthetic features before the assistant behavior is correct.

