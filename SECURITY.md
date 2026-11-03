# Security Policy

## Requirements

- **Home Assistant 2024.12.0 or newer** (set in `hacs.json`; HACS will not offer the integration on older versions)
- Installed through HACS or by copying `custom_components/advanced_group_sensor` into your Home Assistant config folder

## Supported Versions

Only the latest release of Advanced Group Sensor receives security updates. Please make sure you are running the most recent version before reporting a vulnerability.

| Version        | Supported |
|----------------|-----------|
| Latest release | ✅        |
| Older versions | ❌        |

## Reporting a Vulnerability

If you discover a security vulnerability in Advanced Group Sensor, **please do not open a public GitHub issue**. Instead, report it privately using one of these channels:

- 🔒 [GitHub Security Advisories](https://github.com/Pjarbit/ha-advanced-group-sensor/security/advisories/new) — preferred, private disclosure with a coordinated fix
- 📧 Email: pjarbit@gmail.com

Please include:
- A clear description of the vulnerability and its potential impact
- Steps to reproduce (or a proof-of-concept)
- The version of Advanced Group Sensor affected
- Any suggested mitigation or patch

## Response Timeline

You can expect an acknowledgement within a few days. A fix will be prepared and released as soon as reasonably possible depending on severity.

## Scope

Advanced Group Sensor is a Home Assistant custom integration with a WebSocket-based configuration panel. It has no REST endpoints and no iframe/compatibility panel (the legacy HTML panel and REST layer were removed in v1.0.4).

- The configuration panel is registered with `require_admin`, so only Home Assistant administrators can open it.
- Every WebSocket command (`get_config`, `get_states`, `save_config`, `get_tasks`, `task_done`, `task_undo`, `duplicate_sensor`, `import_preview`, `import_sensors`) requires a Home Assistant admin user and uses Home Assistant's own authentication.
- **Import from Combined Notifications** only accepts a file in the Combined Notifications export format, refuses files over 3 MiB, and never carries over Combined Notifications' compatibility-mode settings (including `compat_mode_key`).
- Task Tracker done dates are stored locally in Home Assistant's `.storage` folder. Nothing is sent outside your Home Assistant instance.

Security-relevant issues typically include:

- Access to configuration or entity-state data by a non-admin user or without authentication
- Cross-site scripting (XSS) via panel input, alert labels, or rendering
- Authentication or authorization bypass on any WebSocket command
- Any behaviour that leaks Home Assistant state or credentials outside the browser session

### Known tradeoffs

- **Dynamic Labels** render Jinja2 templates that an admin types into the panel, using Home Assistant's own template engine. Only admins can create or change them.

Issues in Home Assistant itself, HACS, or third-party integrations are out of scope — please report those to their respective projects.

Thanks for helping keep Advanced Group Sensor and its users safe! 🙏
