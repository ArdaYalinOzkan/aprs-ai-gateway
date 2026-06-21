# APRS AI Gateway

An intelligent APRS messaging gateway that automatically responds to radio messages using AI. When someone sends a message to the configured callsign over APRS, the system generates an AI-powered response and transmits it back through the APRS network.

## How It Works

```
[Radio] → [APRS Repeater] → [IGate] → [APRS-IS Network]
                                              ↓
                                    [This Server: AI Gateway]
                                              ↓
                                        [AI Provider]
                                              ↓
[Radio] ← [APRS Repeater] ← [IGate] ← [APRS-IS Network]
```

1. A ham radio operator sends a message to the AI callsign (e.g., `DMW`) via APRS
2. The message travels through APRS repeaters and IGates into the APRS-IS internet network
3. The gateway server monitors the APRS-IS log stream and detects messages addressed to its callsign
4. The message is forwarded to an AI provider (Puter, Groq, OpenRouter, or custom endpoint)
5. The AI generates a response (max 64 characters per SMS, with optional multi-part messages)
6. The response is injected back into the APRS-IS network
7. A nearby bidirectional IGate transmits it on RF, delivering it to the operator's radio

## Features

- **Web Dashboard** — Adwaita-styled configuration panel with live APRS log stream
- **Multiple AI Providers** — Puter (free), Groq, OpenRouter, or any OpenAI-compatible endpoint
- **Multi-Part Messages** — Long responses are split into multiple SMS parts (5s delay between each)
- **ASCII Enforcement** — All responses are automatically transliterated to pure 7-bit ASCII for radio compatibility
- **Whitelist** — Optional access control to restrict which callsigns can interact with the AI
- **Live Log** — Real-time APRS packet stream with color-coded AI activity (SEEN, response, TX)
- **PWA Support** — Installable as a Progressive Web App on mobile devices

## Requirements

- A Linux server (VPS) with Python 3.9+
- An existing [APRS Agent](https://github.com/TA3HRJ/aprs-agent) installation connected to APRS-IS
- An API key from a supported AI provider

## Installation

```bash
# Clone the repository
git clone https://github.com/YOUR_USER/aprs-ai-gateway.git
cd aprs-ai-gateway

# Run the install script
chmod +x install.sh
./install.sh

# Edit the APRS agent config to add AI gateway settings
sudo nano /etc/aprsagent.toml

# Start the service
sudo systemctl start aprs-ai-panel
```

## Configuration

The AI gateway reads its configuration from the `[extensions.ai_gateway]` section of `/etc/aprsagent.toml`:

```toml
[extensions.ai_gateway]
enabled = true
callsign = "DMW"
api_key = "your-api-key-here"
provider = "puter"
base_url = ""
extra_sms = 2
trigger_prefix = ""
whitelist_enabled = false
whitelist = []
```

All settings can also be configured through the web dashboard at `http://your-server:8081`.

### Configuration Options

| Option | Description | Default |
|--------|-------------|---------|
| `enabled` | Enable/disable the AI module | `false` |
| `callsign` | The APRS callsign for the AI gateway (max 7 chars) | `DMW` |
| `api_key` | API key or auth token for the AI provider | — |
| `provider` | AI provider: `puter`, `groq`, `openrouter`, or `custom` | `puter` |
| `base_url` | Custom OpenAI-compatible API endpoint (only for `custom` provider) | — |
| `extra_sms` | Number of additional SMS parts for long responses (0-4) | `0` |
| `trigger_prefix` | Optional prefix to filter messages (empty = respond to all) | `""` |
| `whitelist_enabled` | Enable callsign whitelist | `false` |
| `whitelist` | List of allowed callsigns (supports `*` wildcard) | `[]` |
| `send_delay` | Seconds to wait before sending AI response (0-30) | `0` |

### Remote Commands (via APRS)

You can configure the gateway remotely by sending messages starting with `!`:

| Command | Description | Example |
|---------|-------------|---------|
| `!CALL <name>` | Change AI callsign | `!CALL DMW` |
| `!<number>` | Set total SMS parts (1-5) | `!3` → 3 parts |
| `!DELAY <sec>` | Set response delay in seconds | `!DELAY 5` |
| `!WLON` | Enable whitelist | `!WLON` |
| `!WLOFF` | Disable whitelist | `!WLOFF` |
| `!WL <calls>` | Set whitelist callsigns | `!WL TA3HRJ,TA3EKM` |
| `!STATUS` | Show current settings | `!STATUS` |
| `!HELP` | List available commands | `!HELP` |

Commands are sent as regular APRS messages to the AI callsign. The response confirms the change.

### AI Providers

| Provider | Free Tier | Setup |
|----------|-----------|-------|
| **Puter** | Unlimited (user-pays model) | [puter.com](https://puter.com) — copy auth token from dashboard |
| **Groq** | 14,400 req/day | [console.groq.com](https://console.groq.com) — create API key |
| **OpenRouter** | 50 req/day | [openrouter.ai](https://openrouter.ai) — create API key |
| **Custom** | Varies | Any OpenAI-compatible endpoint |

## Architecture

The gateway integrates with an existing APRS Agent installation:

- **APRS Agent** (Rust) — Connects to APRS-IS, logs all packets via systemd journal
- **AI Gateway** (Python/Flask) — Monitors the journal log, detects messages to its callsign, queries AI, sends responses back via APRS-IS
- **Web Dashboard** — Flask web app for configuration and live monitoring

The AI module does NOT maintain its own APRS-IS connection for receiving. Instead, it reads the APRS Agent's journal log stream, which is more reliable. For sending responses, it opens a direct TCP connection to an APRS-IS server.

## License

Creative Commons Attribution-NonCommercial 4.0 International (CC BY-NC 4.0)

You are free to share and adapt this work, provided you give appropriate credit to the original author and do not use it for commercial purposes.

See [LICENSE](LICENSE) for details.
