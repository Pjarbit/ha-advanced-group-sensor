# Advanced Group Sensor

A Home Assistant custom integration that consolidates the state of many entities into a single, human-readable sensor.

## What it is

Advanced Group Sensor watches a set of entity conditions you define and rolls them up into one sensor. Instead of building dozens of conditional cards or template sensors by hand, you get:

- A single sensor whose state reflects whether any of your watched conditions are active
- Human-readable alert names for each triggered condition
- An alert count and styling attributes you can bind directly to dashboard cards
- Full configuration through a dedicated UI panel — no YAML required

## Configuration

Everything is set up in the UI. Add the integration, open its panel from the sidebar, and define your conditions, alert names, and grouping. States load when the panel opens.

## Installation (HACS)

1. Add this repository as a custom repository in HACS (category: Integration).
2. Install **Advanced Group Sensor**.
3. Restart Home Assistant.
4. Add the integration via **Settings → Devices & Services → Add Integration**.

## Requirements

Home Assistant with the `frontend`, `websocket_api`, and `http` integrations (all standard).

## Author

Maintained by [@Pjarbit](https://github.com/Pjarbit).
