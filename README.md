<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 240" width="900" height="240">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#0a0f1d"/>
      <stop offset="100%" stop-color="#111827"/>
    </linearGradient>
    <linearGradient id="accent" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#4f46e5"/>
      <stop offset="100%" stop-color="#7c3aed"/>
    </linearGradient>
    <filter id="glow">
      <feGaussianBlur stdDeviation="8" result="blur"/>
      <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
  </defs>
  <rect width="900" height="240" fill="url(#bg)" rx="18"/>
  <rect x="1" y="1" width="898" height="238" fill="none" stroke="#243041" stroke-width="1.5" rx="17.5"/>
  <circle cx="56" cy="120" r="34" fill="url(#accent)" filter="url(#glow)" opacity="0.9"/>
  <text x="56" y="127" text-anchor="middle" font-family="ui-monospace,monospace" font-size="26" font-weight="800" fill="white">H</text>
  <text x="108" y="108" font-family="ui-sans-serif,system-ui,sans-serif" font-size="32" font-weight="800" fill="#e5e7eb" letter-spacing="-0.5">Hermes</text>
  <text x="108" y="138" font-family="ui-sans-serif,system-ui,sans-serif" font-size="16" font-weight="400" fill="#94a3b8">All-in-One · Railway Template</text>
  <line x1="108" y1="152" x2="580" y2="152" stroke="#243041" stroke-width="1"/>
  <text x="108" y="174" font-family="ui-sans-serif,system-ui,sans-serif" font-size="13" fill="#6b7280">One container. One volume. One Hermes identity.</text>
  <text x="108" y="194" font-family="ui-sans-serif,system-ui,sans-serif" font-size="13" fill="#6b7280">Telegram + WebUI + Admin — all on the same brain.</text>
  <rect x="640" y="88" width="220" height="36" rx="10" fill="url(#accent)" opacity="0.15" stroke="#4f46e5" stroke-width="1"/>
  <text x="750" y="111" text-anchor="middle" font-family="ui-monospace,monospace" font-size="12" fill="#a5b4fc">/ → WebUI</text>
  <rect x="640" y="132" width="220" height="36" rx="10" fill="url(#accent)" opacity="0.15" stroke="#4f46e5" stroke-width="1"/>
  <text x="750" y="155" text-anchor="middle" font-family="ui-monospace,monospace" font-size="12" fill="#a5b4fc">/admin → Control Plane</text>
  <rect x="640" y="176" width="220" height="36" rx="10" fill="url(#accent)" opacity="0.15" stroke="#4f46e5" stroke-width="1"/>
  <text x="750" y="199" text-anchor="middle" font-family="ui-monospace,monospace" font-size="12" fill="#a5b4fc">/health → Railway check</text>
</svg>

# Hermes All-in-One · Railway Template

> **One container. One volume. One Hermes identity.**
> Deploy a production-grade AI agent to Railway in minutes — chat on Telegram, browse the web UI, manage everything from `/admin`.

[![Deploy on Railway](https://railway.com/button.svg)](https://railway.com/new/template/PLACEHOLDER)

---

## ⚡ First time here? Go to `/admin` — not `/`

When you deploy this, your app opens at `/`. That's the Hermes WebUI — but it needs a password and a configured AI provider to work. **You must configure it first at `/admin`.**

```
https://your-app.railway.app/admin
```

Log in with `HERMES_ADMIN_PASSWORD` (or `HERMES_WEBUI_PASSWORD` if admin password isn't set). This is where you set your API key, connect Telegram, and start the gateway.

---

## What is this?

[Hermes Agent](https://github.com/NousResearch/hermes-agent) is a self-improving AI agent from NousResearch — it can use tools, remember things, and talk to you over multiple channels. This repo packages it into a single Railway-deployable container with:

| Surface | URL | What it is |
|---------|-----|-----------|
| **WebUI** | `/` | Hermes chat interface in the browser |
| **Control Plane** | `/admin` | Provider + channel setup, gateway controls, logs |
| **Health** | `/health` | Railway health check endpoint |

Everything shares one Hermes identity — the same memory, skills, config, and SOUL file — whether you're talking on Telegram or in the browser.

---

## Screenshots

| Control Plane Overview | Provider Setup | Channel Config |
|----------------------|----------------|---------------|
| _(screenshot)_ | _(screenshot)_ | _(screenshot)_ |

---

## Quick Deploy

### 1. Deploy to Railway

Click the button above or create a new Railway service from this repo manually.

### 2. Add a volume

In Railway → your service → **Volumes** tab → mount a persistent volume at `/data`.

> Without a volume, all your agent memory, config, and credentials are lost on every redeploy.

### 3. Set required environment variables

Go to **Variables** in your Railway service and set at minimum:

```
HERMES_WEBUI_PASSWORD=your-secure-password
HERMES_ADMIN_PASSWORD=your-admin-password
```

### 4. Deploy

Railway builds the Dockerfile and starts the container. The control plane at `/admin` is ready in ~30 seconds.

### 5. Configure your AI provider at `/admin`

Go to `/admin` → **Providers** → pick your provider → enter your API key → Save.

### 6. (Optional) Connect Telegram

Go to `/admin` → **Channels** → enter your bot token and your numeric Telegram user ID → Save.

The gateway starts automatically once both provider and channel are configured.

---

## Environment Variables

### Required

| Variable | Description |
|----------|-------------|
| `HERMES_WEBUI_PASSWORD` | Password for the WebUI at `/` |
| `HERMES_ADMIN_PASSWORD` | Password for `/admin` (falls back to WebUI password if unset) |

### AI Provider (set via `/admin` UI or manually)

| Variable | Description |
|----------|-------------|
| `OPENROUTER_API_KEY` | For OpenRouter (recommended — access to all models) |
| `ANTHROPIC_API_KEY` | For Anthropic direct |
| `OPENAI_API_KEY` | For OpenAI or custom OpenAI-compatible endpoints |

### Telegram (set via `/admin` UI or manually)

| Variable | Description |
|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | Your bot token from [@BotFather](https://t.me/BotFather) |
| `TELEGRAM_ALLOWED_USERS` | Comma-separated numeric user IDs allowed to chat |

### Gateway behavior

| Variable | Default | Description |
|----------|---------|-------------|
| `HERMES_GATEWAY_AUTOSTART` | `auto` | `auto` = start when provider + channel ready; `off` = never autostart |

### Internal paths (don't change these unless you know why)

| Variable | Default |
|----------|---------|
| `HERMES_HOME` | `/data/.hermes` |
| `HERMES_CONFIG_PATH` | `/data/.hermes/config.yaml` |
| `HERMES_WEBUI_STATE_DIR` | `/data/webui` |
| `HERMES_WORKSPACE_DIR` | `/data/workspace` |
| `PORT` | `8787` |

---

## Provider Setup Guide

### OpenRouter (recommended for beginners)

OpenRouter gives you a single API key that accesses Anthropic, OpenAI, Mistral, Google, and hundreds of other models. Create an account at [openrouter.ai](https://openrouter.ai), add credits, copy your API key.

In `/admin` → Providers:
- Provider: **OpenRouter**
- Model: `anthropic/claude-sonnet-4-6` (or any model from their catalog)
- API Key: your OpenRouter key

### Anthropic Direct

Get a key from [console.anthropic.com](https://console.anthropic.com).

In `/admin` → Providers:
- Provider: **Anthropic**
- Model: `claude-sonnet-4-6`
- API Key: your `sk-ant-...` key

### OpenAI Direct

Get a key from [platform.openai.com](https://platform.openai.com).

In `/admin` → Providers:
- Provider: **OpenAI**
- Model: `gpt-4o`
- API Key: your `sk-...` key

### Custom OpenAI-compatible endpoint

For Ollama, LM Studio, vLLM, Together, Groq, or any OpenAI-compatible API:

In `/admin` → Providers:
- Provider: **Custom OpenAI-compatible**
- Model: whatever your endpoint expects
- API Key: your key (or `ollama` for local Ollama)
- Base URL: `https://your-endpoint.com/v1`

### OpenAI Subscription / ChatGPT account login (advanced)

> **Disclaimer:** This uses your personal ChatGPT account via Railway's SSH terminal. It works but is fragile — OpenAI may change their auth flow at any time. Use at your own risk. Your credentials are stored only in your container's `/data` volume.

OAuth-style and subscription-based provider flows (ChatGPT, Codex, Nous Portal) can't be completed in the browser on Railway. Use the Railway CLI instead:

```bash
# Install Railway CLI
npm install -g @railway/cli

# Log in
railway login

# SSH into your running service
railway ssh

# Inside the container, run Hermes auth
hermes auth login
# Follow the prompts — this stores credentials in /data/.hermes
```

After completing auth in the terminal, go back to `/admin` and the provider should appear as configured.

---

## Telegram Setup Guide

### Step 1: Create a bot

1. Open Telegram, search for [@BotFather](https://t.me/BotFather)
2. Send `/newbot` and follow the prompts
3. Copy the bot token (looks like `123456789:ABCdef...`)

### Step 2: Find your numeric user ID

1. Open Telegram, search for [@userinfobot](https://t.me/userinfobot)
2. Start the bot — it replies with your numeric ID (e.g. `123456789`)

> Important: Telegram user IDs are **numbers**, not usernames. `@yourhandle` won't work — you need the numeric ID.

### Step 3: Configure in `/admin`

Go to `/admin` → **Channels** → **Telegram**:
- Bot token: paste your BotFather token
- Allowed user IDs: your numeric ID (comma-separate for multiple users)
- Save

The gateway starts automatically. Send `/start` to your bot on Telegram — it should respond.

---

## Your Agent's Identity — SOUL.md

`SOUL.md` controls the agent's persistent persona and behavior — its name, how it speaks, what it cares about. In this template it lives at `/data/.hermes/SOUL.md` on the persistent volume.

Edit it directly from the Hermes WebUI, then restart the gateway from `/admin` → Overview → **Restart** to apply changes.

For full formatting guidance, persona examples, and what `SOUL.md` can control, see the [Hermes Agent documentation](https://github.com/NousResearch/hermes-agent).

---

## Memory & Sessions

Hermes remembers everything in `/data/.hermes/`:

```
/data/.hermes/
  config.yaml        ← provider + model config
  .env               ← channel credentials (tokens, API keys)
  sessions/          ← conversation history per channel
  skills/            ← agent skills and tools
  SOUL.md            ← agent identity
```

The WebUI and Telegram gateway share this directory. That means:
- Your agent remembers Telegram conversations when you switch to WebUI
- Skills you add via one surface are available on the other
- One personality, two frontends

Back up `/data` entirely — not just `/data/.hermes`.

---

## Use Cases & Patterns

### Personal AI assistant on Telegram
Set `TELEGRAM_ALLOWED_USERS` to just your own ID. Use your agent for research, writing, brainstorming, and task tracking — all in your normal Telegram flow. Your conversations persist across reboots.

### Team knowledge base assistant
Add multiple user IDs to `TELEGRAM_ALLOWED_USERS`. Give the agent a custom SOUL.md as a team expert in your domain. Point it at your docs using Hermes skills.

### Automated task runner
Use the Hermes skills system to give your agent tools — file access, API calls, code execution. Trigger tasks over Telegram or the WebUI.

### Multi-channel bot
Configure Telegram + Discord + Slack simultaneously (all supported by the gateway). One agent responds across all channels with shared memory.

### Development sandbox
Keep `HERMES_GATEWAY_AUTOSTART=off`, deploy once, and use the WebUI exclusively for development and testing. Toggle the gateway on only when you're ready to go live.

---

## Tips from the field

**On first deploy, go straight to `/admin`** — not `/`. The WebUI at `/` requires a working provider before it's useful.

**Use OpenRouter for experimenting** — swap models without changing your deployment. Try Claude for reasoning, Mistral for speed, local models for privacy.

**Don't share your Telegram bot token in public repos.** Use Railway environment variables, not `.env` files committed to git.

**Your agent's `SOUL.md` is the highest-leverage file you'll ever write.** 200 words of well-crafted identity beats 2000 words of prompt injection in system prompts.

**Volume = memory.** If you delete the Railway volume, your agent forgets everything. Back up `/data` before destructive Railway operations.

**The gateway health check is time-based, not HTTP.** Hermes gateway is a Telegram bot process — it's healthy if it's been running without crashing for ≥3 seconds. No HTTP endpoint to probe.

**Password protect everything before sharing the URL.** Both `HERMES_WEBUI_PASSWORD` and `HERMES_ADMIN_PASSWORD` should be set before the service is public.

---

## Architecture Overview

```
Railway service (single container)
│
├── PID 1: Starlette control plane (:8787, public)
│   ├── / → proxy to internal WebUI
│   ├── /admin → control plane UI
│   └── /health → Railway health check
│
├── Internal: Hermes WebUI (:8788, loopback only)
│   └── imports hermes-agent directly via sys.path
│
└── Optional: Hermes gateway (subprocess)
    └── connects to Telegram / Discord / Slack
        └── reads /data/.hermes (shared with WebUI)
│
Volume: /data
  ├── .hermes/   ← agent identity, memory, config
  ├── webui/     ← WebUI state
  └── workspace/ ← agent workspace
```

The control plane is a thin Starlette wrapper — not a framework, not a product. It exists to:
1. Proxy WebUI behind auth
2. Expose `/admin` for initial setup
3. Manage the gateway process lifecycle

---

## Credits

This repository is a Railway deployment wrapper. All agent and WebUI logic lives upstream:

- **[Hermes Agent](https://github.com/NousResearch/hermes-agent)** — agent runtime by NousResearch
- **[Hermes WebUI](https://github.com/NousResearch/hermes-webui)** — browser chat interface by NousResearch
