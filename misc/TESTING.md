# Testing `LexNeuro`

This guide walks through a first manual test pass of the bot using Docker.
It is written to verify the features currently implemented in the bot, one by one.

## 0. What you need first

Before you start, make sure you have:

- Docker installed
- A Discord bot created in the Discord Developer Portal
- The bot token and application/client ID
- A Discord server where you can invite the bot
- At least one OpenAI-compatible model endpoint configured
  - This can be a hosted provider such as OpenAI, Groq, OpenRouter, Mistral, xAI, Google, or Azure OpenAI
  - Or a local server such as Ollama, LM Studio, or vLLM

If you want the simplest first run, use a model that does not require extra provider options beyond `base_url` and `api_key`.
If you are testing a local provider from Docker, make sure the provider is reachable from the container's host network settings.

## 1. Prepare the config

1. Copy the example config:

   ```bash
   cp config-example.yaml config.yaml
   ```

2. Edit `config.yaml` and set:

   - `bot_token`
   - `client_id`
   - At least one provider with a valid `base_url`
   - At least one model in `models`
   - Optional: `status_message`
   - Optional: `system_prompt`

3. Make sure the first model in `models` is the one you want as the default startup model.
   The bot uses the first key in that mapping.

4. If you want to test image support later, choose a vision-capable model and add `:vision` to the model key if needed.

## 2. Build and start with Docker

1. Build the image:

   ```bash
   docker build -t lexneuro .
   ```

2. Start the service:

   ```bash
   docker compose up
   ```

3. Watch the logs and confirm:

   - The bot connects successfully
   - `on_ready` runs
   - The slash commands sync without errors

4. Copy the invite URL from the logs if `client_id` is set, then invite the bot to your test server.

## 3. Test checklist

Follow these tests in order. Each step verifies a different supported behavior.

### 3.1 Startup and readiness

1. Start the container.
2. Confirm the bot appears online in Discord.
3. Confirm the configured status message is visible on the bot profile.
4. If `client_id` is set, confirm the invite URL in the logs looks correct.

Expected result:

- The container stays running
- The bot is online
- The app commands are registered

### 3.2 `/model` command: view the current model

1. In Discord, run `/model`.
2. Use the autocomplete or type the current model name.
3. Submit the command with the active model.

Expected result:

- The bot replies with the current model name
- In a DM, the response should be ephemeral
- In a server channel, the response should be visible in the channel

### 3.3 `/model` command: switch models as an admin

1. Add your Discord user ID to `permissions.users.admin_ids`.
2. Restart the container or reload the config by using a fresh autocomplete request after editing `config.yaml`.
3. Run `/model` and switch to another model listed in `models`.

Expected result:

- The model changes
- The bot logs the change
- Subsequent messages use the new model

### 3.4 `/model` command: reject non-admin switching

1. Remove your user ID from `admin_ids` or use a different non-admin account.
2. Run `/model` and try to switch models.

Expected result:

- The bot refuses the change
- The current model remains unchanged

### 3.5 Mention gating

1. In a server channel, send a normal message without mentioning the bot.
2. Send another message that mentions the bot.

Expected result:

- The bot ignores the first message
- The bot responds to the mention

### 3.6 Permission checks: users, roles, and channels

Test each permission mode separately by changing `config.yaml`.

1. Set `permissions.users.allowed_ids` to a list that includes only your account.
2. Send a message while mentioning the bot from your account.
3. Try the same from a disallowed account.

Expected result:

- Allowed users can trigger the bot
- Disallowed users are ignored

Repeat the same idea for:

- `permissions.roles.allowed_ids`
- `permissions.channels.allowed_ids`
- `permissions.users.blocked_ids`
- `permissions.roles.blocked_ids`
- `permissions.channels.blocked_ids`

Expected result:

- Allowed entries work
- Blocked entries override allowed behavior

### 3.7 DM behavior

1. Open a DM with the bot.
2. Send a message without mentioning the bot.
3. Reply to your own previous message.

Expected result:

- DMs are accepted if `allow_dms: true`
- The conversation continues automatically in DMs
- Replies still work as part of the same conversation

4. Set `allow_dms: false`.
5. Restart the bot or reload the config.
6. Send another DM.

Expected result:

- The bot ignores the DM unless the sender is an admin

### 3.8 Reply-chain reconstruction

1. In a server channel, mention the bot in a message.
2. Reply to the bot’s response.
3. Reply again to continue the chain.

Expected result:

- The bot includes previous replies in the conversation context
- The bot stays on the same thread of conversation

### 3.9 Same-author message chaining

1. Send two or more messages in a row from the same user.
2. Reply to the latest one and mention the bot.

Expected result:

- The bot reconstructs adjacent same-author messages into the context
- The response should reflect the full chain instead of only the last message

### 3.10 Thread handling

1. Create a thread from a text channel message.
2. Mention the bot inside the thread.

Expected result:

- The bot can read the thread starter context
- The bot responds inside the thread

### 3.11 Text attachment handling

1. Send a message that mentions the bot and attaches a text file.
2. Use a simple file such as `.txt` or `.py`.

Expected result:

- The file contents are included in the prompt
- The bot responds using the attached text

3. Attach an unsupported file type.

Expected result:

- The bot ignores unsupported attachments
- A warning is shown when warnings are enabled

### 3.12 Image attachment handling

1. Switch to a vision-capable model.
2. Send a message that mentions the bot and includes one or more image attachments.

Expected result:

- The images are included in the request
- The bot responds using the image context

3. Send more images than `max_images`.

Expected result:

- Only the configured maximum is used
- A warning is shown when warnings are enabled

If the model does not support vision or the model key is not marked as vision-capable, the bot should warn that it cannot see images.

### 3.13 `/abnt` helper

1. Create a small `.docx` or `.odt` file with academic text and at least one rough reference.
2. Run `/abnt` and attach the file.
3. Optionally fill the `instructions` field with a constraint such as `manter seções curtas`.

Expected result:

- The bot accepts the supported Word attachment
- The model returns ABNT evaluation data as JSON (`score` + `improvements`)
- The bot sends a deterministic summary message in the same channel
- If score is `>= 0.9`, the bot says the document is good enough
- If score is `>= 0.7` and `< 0.9`, the bot lists improvements to raise the score
- If score is `< 0.7`, the bot sends a stricter warning and the same improvement list

4. Run `/abnt` with a PDF, DOC, TXT, or MD file.

Expected result:

- The bot rejects the unsupported file type with an explanatory message

### 3.14 Streaming response behavior

1. Send a prompt that produces a medium or long response.

Expected result:

- The bot starts streaming output instead of waiting for the full completion
- The embed turns green when the response is complete
- Long replies are split into multiple messages if needed

### 3.15 Plain-text response mode

1. Set `use_plain_responses: true`.
2. Restart the bot or reload config.
3. Send a prompt that produces a long reply.

Expected result:

- The bot sends plain text instead of embeds
- It does not do embed streaming while generating the response
- Warning messages are disabled
- Long responses split across multiple messages when needed

### 3.16 System prompt formatting

1. Set `system_prompt` to include `{date}` and `{time}`.
2. Send a message to the bot.

Expected result:

- The placeholders are replaced with the current date and time
- The bot behavior reflects the configured system prompt

### 3.17 Config hot reload

1. Edit `config.yaml` while the container is running.
2. Change a visible value such as:

   - `status_message`
   - `allow_dms`
   - `use_plain_responses`
   - `permissions`
   - `models`

3. Trigger a fresh `/model` autocomplete or send a new message.

Expected result:

- The bot picks up the updated config without a full restart in the cases where the code reloads config dynamically

Note:

- `on_message` reloads config on each message
- `/model` autocomplete reloads config when the input is empty
- Some changes may still require a restart to be visible in Discord client state or container startup state

### 3.18 Cache behavior

1. Send enough messages to grow the conversation cache.
2. Continue sending new messages until the cache limit is exceeded.

Expected result:

- The bot continues to work
- Older message nodes are evicted first
- There are no obvious memory growth issues during the test run

### 3.19 Error handling

1. Temporarily point the provider to an invalid `base_url`.
2. Send a message that would trigger a response.

Expected result:

- The bot logs the failure
- The process stays alive
- You can fix the config and continue testing

## 4. Recommended first run order

If you want the shortest useful test pass, do this order:

1. Build and start Docker
2. Confirm the bot is online
3. Test `/model` view
4. Test mention gating
5. Test a simple reply chain
6. Test a text attachment
7. Test a vision attachment, if you configured one
8. Test `/abnt` with a `.docx` or `.odt` document
9. Test DMs
10. Test permissions
11. Test plain-text mode
12. Test config hot reload

## 5. Troubleshooting

If something fails, check these first:

- `bot_token` is correct
- `client_id` is correct
- The Discord bot has the `MESSAGE CONTENT INTENT` enabled
- The provider `base_url` is valid
- The model name is valid for that provider
- Your account is allowed by the configured permissions
- The bot has permission to read messages and send messages in the channel

## 6. What this test plan covers

This file is aligned with the current runtime behavior in `main.py`:

- Discord startup and slash command registration
- `/model` view and switching
- Permission gating
- DM behavior
- Reply-chain context reconstruction
- Same-author message chaining
- Thread starter handling
- Text attachments
- `/abnt` helper for supported `.docx` and `.odt` documents
- Image attachments
- Streaming responses
- Plain-text responses
- System prompt insertion
- Config hot reload
- Cache eviction
