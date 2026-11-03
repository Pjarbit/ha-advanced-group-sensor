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

## Task Trackers (new in 1.1.0)

For things Home Assistant can't see you do: meds, workouts, paying rent, birthdays. Open the **Tasks** tab in the panel and add a task:

- **Alert Label**: what the sensor shows when it's due (ex: `Bailey Medication Due`)
- **Repeat**: Daily, Weekly, Every X days, Monthly, or Yearly
- **Date**:
  - Yearly: the birthday or anniversary (the year doesn't matter)
  - Monthly: optional. Set it to pin the day of the month (the 15th stays the 15th, and a missed one stays overdue until Done). Leave it empty to count a month from the last Done
  - Others: optional first due date
- **Lead days**: start alerting this many days early

When you save, each task gets two entities:

- `button.<label>_done`: press it when the task is done and the alert clears. One press means you're caught up, even if several were missed
- `sensor.<label>_days_remaining`: days until due (negative means overdue), handy for countdown cards. Attributes include `due_date`, `last_done` and `alerting`

The integration stores the done dates itself. No helpers, no template YAML. Press Done from a dashboard card, the panel, an automation (`button.press`), or voice. In the panel the button is red **✓ Done** when the task is due and gray **Done early** when it isn't.

Birthday tip: make two yearly tasks with the same date. `Send Mom a Card` with 7 lead days, and `Call Mom` with 0. Each clears on its own Done and both come back next year.

## Duplicate Sensor (new in 1.1.0)

In a sensor's panel, **⧉ Duplicate Sensor** (Backup & Restore) asks for a new name and creates a copy of the last saved version: conditions, colors, icons, labels and attribute mode. Task Trackers are not copied. The button is greyed out until the sensor has been saved with at least one condition.

## Moving from Combined Notifications (new in 1.1.0)

You can bring every Combined Notifications sensor over in one go, keeping each sensor's name and entity ID:

1. Update Combined Notifications to 8.12.0 or later. **If you use compatibility mode, turn it off and test first.** AGS does not have a compatibility mode (BREAKING CHANGE).
2. Rename each Combined Notifications sensor and its Fault Count sensor so the entity ID ends in `_old` (for example `sensor.kitchen_old`).
3. In any Combined Notifications panel, click **⬇ Export ALL for AGS** in Backup & Restore.
4. In AGS, create a sensor named `import` and open its panel. At the bottom, click **⬆ Import from Combined Notifications**, choose the file, and tick the sensors to bring over. Sensors that can't be imported yet are greyed out with the reason.
5. Check the new sensors, then delete the `import` sensor and disable the old Combined Notifications entries.

Conditions, colors, icons, labels and attribute mode carry over. Nothing in Combined Notifications is changed.

## Installation (HACS)

1. Add this repository as a custom repository in HACS (category: Integration).
2. Install **Advanced Group Sensor**.
3. Restart Home Assistant.
4. Add the integration via **Settings → Devices & Services → Add Integration**.

## Requirements

Home Assistant with the `frontend`, `websocket_api`, and `http` integrations (all standard).

## Author

Maintained by [@Pjarbit](https://github.com/Pjarbit).
