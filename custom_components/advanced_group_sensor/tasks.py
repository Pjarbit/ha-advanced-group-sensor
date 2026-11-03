"""Task trackers for Advanced Group Sensor.

A task is something Home Assistant can't see you do: give the dog meds, work
out, pay rent, call Mom. Each task has a repeat pattern and an optional lead
time. The integration stores when each task was marked done, works out when it
is next due, and reports whether it should be alerting right now.

Task config (stored in config_entry.data["tasks"]):
    id            str   stable id, generated if missing
    name          str   alert label, e.g. "Bailey Medication Due"
    repeat        str   daily | weekly | every_x_days | monthly | yearly
    interval_days int   every_x_days only, >= 1
    date          str   YYYY-MM-DD
                        yearly:  the anniversary date (year ignored)
                        monthly: pins the day of the month (month/year ignored)
                        others:  optional first due date until the first Done
    lead_days     int   start alerting this many days before the due date
    paused        bool
    created       str   YYYY-MM-DD, set once when the task is first saved

Stored by the integration (Store), per task id:
    last_done     date Done was last pressed
    covered_due   the due date that Done was pressed for (occurrence tasks)
    undo          previous last_done / covered_due, so Undo restores one step

Behavior:
    Interval (daily, weekly, every_x_days, monthly with no date):
        due = last_done + interval. Never done -> due = first due date or today.
        Alerts from (due - lead_days) onward, including overdue, until Done.
        Done moves the due date forward. A late Done pushes the next due.
    Pinned monthly (monthly with a date):
        due = earliest day-of-month occurrence on or after `created` that is
        after covered_due. Day is clamped (31st -> Feb 28, back to Mar 31).
        If that day has passed without Done it stays due (overdue, negative
        days) until Done. One Done clears everything: it covers the latest
        occurrence up to today (or the upcoming one if pressed early), and the
        next due is the following occurrence. A task created on the 20th does not alert for the
        15th that already passed.
    Yearly:
        due = next occurrence of the month/day (today counts).
        Alerts from (due - lead_days) through the day itself unless Done
        covered that occurrence. After the day it rolls to next year.
        Feb 29 falls back to Feb 28 in non leap years.
"""
from __future__ import annotations

import calendar
import logging
import uuid
from datetime import date, timedelta
from typing import Any, Callable

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import DOMAIN, SIGNAL_TASKS_UPDATED, TASK_REPEAT_DAYS, TASK_REPEATS, TASK_STORAGE_VERSION

_LOGGER = logging.getLogger(__name__)


# ── Pure date helpers (no HA objects, easy to unit test) ─────────────────────

def parse_date(value: Any) -> date | None:
    """Parse YYYY-MM-DD into a date, or None."""
    if isinstance(value, date):
        return value
    if not value or not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value.strip()[:10])
    except ValueError:
        return None


def add_months(d: date, months: int) -> date:
    """Add months, clamping the day (Jan 31 + 1 month = Feb 28/29)."""
    y, m = divmod(d.month - 1 + months, 12)
    year, month = d.year + y, m + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def yearly_occurrence(anchor: date, year: int) -> date:
    """Anchor month/day in the given year. Feb 29 -> Feb 28 in non leap years."""
    if anchor.month == 2 and anchor.day == 29 and not calendar.isleap(year):
        return date(year, 2, 28)
    return date(year, anchor.month, anchor.day)


def next_monthly_fixed(day: int, start: date) -> date:
    """First occurrence of a day-of-month on or after start. Day is clamped
    per month from the original day, so the 31st is Feb 28 then Mar 31."""
    day = max(1, min(31, day))
    y, m = start.year, start.month
    occ = date(y, m, min(day, calendar.monthrange(y, m)[1]))
    if occ < start:
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
        occ = date(y, m, min(day, calendar.monthrange(y, m)[1]))
    return occ


def last_monthly_fixed(day: int, end: date) -> date:
    """Latest occurrence of a day-of-month on or before end (clamped per month)."""
    day = max(1, min(31, day))
    y, m = end.year, end.month
    occ = date(y, m, min(day, calendar.monthrange(y, m)[1]))
    if occ > end:
        y, m = (y - 1, 12) if m == 1 else (y, m - 1)
        occ = date(y, m, min(day, calendar.monthrange(y, m)[1]))
    return occ


def is_pinned_monthly(task: dict) -> bool:
    return task.get("repeat") == "monthly" and parse_date(task.get("date")) is not None


def is_occurrence(task: dict) -> bool:
    """Yearly or pinned monthly: Done covers one occurrence, not a time span."""
    return task.get("repeat") == "yearly" or is_pinned_monthly(task)


def next_due(
    task: dict,
    last_done: date | None,
    today: date,
    covered_due: date | None = None,
) -> date | None:
    """Return the date the task is due, or None if misconfigured.
    For pinned monthly this can be in the past (overdue)."""
    repeat = task.get("repeat")

    if repeat == "yearly":
        anchor = parse_date(task.get("date"))
        if anchor is None:
            return None
        occ = yearly_occurrence(anchor, today.year)
        if occ < today:
            occ = yearly_occurrence(anchor, today.year + 1)
        return occ

    if is_pinned_monthly(task):
        start = parse_date(task.get("created")) or today
        if covered_due is not None:
            start = max(start, covered_due + timedelta(days=1))
        return next_monthly_fixed(parse_date(task["date"]).day, start)

    if last_done is None:
        return parse_date(task.get("date")) or today

    if repeat == "monthly":
        return add_months(last_done, 1)
    if repeat == "every_x_days":
        return last_done + timedelta(days=max(1, int(task.get("interval_days") or 1)))
    if repeat in TASK_REPEAT_DAYS:
        return last_done + timedelta(days=TASK_REPEAT_DAYS[repeat])
    return None


def task_status(
    task: dict,
    last_done: date | None,
    today: date,
    covered_due: date | None = None,
) -> dict:
    """Full status for one task: due date, days until due, alerting flag."""
    due = next_due(task, last_done, today, covered_due)
    if due is None:
        return {
            "due_date": None,
            "days_until_due": None,
            "last_done": last_done.isoformat() if last_done else None,
            "alerting": False,
            "valid": False,
        }

    lead = max(0, int(task.get("lead_days") or 0))
    window_start = due - timedelta(days=lead)

    if task.get("paused") or today < window_start:
        alerting = False
    elif task.get("repeat") == "yearly":
        # After the day, next_due has rolled to next year, so a missed
        # birthday stops alerting. Inside the window: alert unless covered.
        alerting = covered_due != due
    else:
        # Interval tasks: due moves forward on Done.
        # Pinned monthly: due is by definition not covered yet (stays overdue).
        alerting = True

    return {
        "due_date": due.isoformat(),
        "days_until_due": (due - today).days,
        "last_done": last_done.isoformat() if last_done else None,
        "alerting": alerting,
        "valid": True,
    }


def normalize_tasks(
    tasks: Any,
    today: date | None = None,
    previous: list[dict] | None = None,
) -> list[dict]:
    """Clean task configs from the panel. Drops junk, fills defaults, adds ids.

    `created` is set once: kept from the incoming task, else from the previous
    saved version of the same id, else today. It is never overwritten.
    """
    clean: list[dict] = []
    if not isinstance(tasks, list):
        return clean
    today = today or dt_util.now().date()
    prev_created = {
        t.get("id"): t.get("created")
        for t in (previous or [])
        if isinstance(t, dict) and t.get("id")
    }
    seen_ids: set[str] = set()
    seen_names: set[str] = set()
    for raw in tasks:
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name", "")).strip()
        repeat = raw.get("repeat")
        if not name or repeat not in TASK_REPEATS:
            _LOGGER.warning("Skipping invalid task: %s", raw)
            continue
        if name in seen_names:
            _LOGGER.warning(
                "Duplicate task name %r: Home Assistant will add a suffix to the entity ids", name
            )
        seen_names.add(name)
        task_id = str(raw.get("id") or "").strip() or uuid.uuid4().hex[:12]
        if task_id in seen_ids:
            task_id = uuid.uuid4().hex[:12]
        seen_ids.add(task_id)
        try:
            interval = max(1, int(raw.get("interval_days") or 1))
        except (TypeError, ValueError):
            interval = 1
        try:
            lead = max(0, int(raw.get("lead_days") or 0))
        except (TypeError, ValueError):
            lead = 0
        task_date = parse_date(raw.get("date"))
        if repeat == "yearly" and task_date is None:
            _LOGGER.warning("Skipping yearly task without a date: %s", name)
            continue
        created = (
            parse_date(raw.get("created"))
            or parse_date(prev_created.get(task_id))
            or today
        )
        clean.append({
            "id": task_id,
            "name": name,
            "repeat": repeat,
            "interval_days": interval,
            "date": task_date.isoformat() if task_date else "",
            "lead_days": lead,
            "paused": bool(raw.get("paused", False)),
            "created": created.isoformat(),
        })
    return clean


# ── Manager: owns storage, midnight rollover, and change notifications ───────

class TaskManager:
    """Holds task configs and done records for one config entry."""

    def __init__(self, hass: HomeAssistant, entry_id: str, tasks: list[dict]) -> None:
        self.hass = hass
        self.entry_id = entry_id
        self.tasks: list[dict] = normalize_tasks(tasks)
        self._store = Store(hass, TASK_STORAGE_VERSION, f"{DOMAIN}.{entry_id}.tasks")
        self._last_done: dict[str, str] = {}
        self._covered_due: dict[str, str] = {}
        self._undo: dict[str, dict] = {}
        self._unsub_midnight: Callable[[], None] | None = None

    @property
    def signal(self) -> str:
        return SIGNAL_TASKS_UPDATED.format(self.entry_id)

    async def async_load(self) -> None:
        data = await self._store.async_load() or {}
        self._last_done = dict(data.get("last_done", {}))
        self._covered_due = dict(data.get("covered_due", {}))
        self._undo = dict(data.get("undo", {}))
        # Fire just after midnight so tasks roll into "due" with no state change
        self._unsub_midnight = async_track_time_change(
            self.hass, self._midnight, hour=0, minute=0, second=5
        )

    @callback
    def async_stop(self) -> None:
        if self._unsub_midnight:
            self._unsub_midnight()
            self._unsub_midnight = None

    @callback
    def _midnight(self, _now) -> None:
        self._notify()

    @callback
    def _notify(self) -> None:
        async_dispatcher_send(self.hass, self.signal)

    async def _save(self) -> None:
        await self._store.async_save({
            "last_done": self._last_done,
            "covered_due": self._covered_due,
            "undo": self._undo,
        })

    def get_task(self, task_id: str) -> dict | None:
        return next((t for t in self.tasks if t["id"] == task_id), None)

    def last_done(self, task_id: str) -> date | None:
        return parse_date(self._last_done.get(task_id))

    def covered_due(self, task_id: str) -> date | None:
        return parse_date(self._covered_due.get(task_id))

    def _status_for(self, task: dict, today: date) -> dict:
        return task_status(
            task, self.last_done(task["id"]), today, self.covered_due(task["id"])
        )

    def status(self, task_id: str) -> dict | None:
        task = self.get_task(task_id)
        if task is None:
            return None
        return self._status_for(task, dt_util.now().date())

    def alerting_labels(self) -> list[str]:
        """Labels of every task that should be alerting right now."""
        today = dt_util.now().date()
        return [t["name"] for t in self.tasks if self._status_for(t, today)["alerting"]]

    def all_status(self) -> dict[str, dict]:
        today = dt_util.now().date()
        return {
            t["id"]: {**t, **self._status_for(t, today), "can_undo": self.can_undo(t["id"])}
            for t in self.tasks
        }

    async def async_mark_done(self, task_id: str, day: date | None = None) -> None:
        task = self.get_task(task_id)
        if task is None:
            _LOGGER.warning("Mark done for unknown task %s", task_id)
            return
        today = day or dt_util.now().date()
        self._undo[task_id] = {
            "last_done": self._last_done.get(task_id),
            "covered_due": self._covered_due.get(task_id),
        }
        if is_occurrence(task):
            # Cover the occurrence that is due right now (in the lead window,
            # or the next upcoming one if pressed early). Pinned monthly that is
            # overdue: one press clears everything, so cover the latest
            # occurrence up to today, not just the oldest missed one.
            due = next_due(task, self.last_done(task_id), today, self.covered_due(task_id))
            if due:
                if is_pinned_monthly(task):
                    latest = last_monthly_fixed(parse_date(task["date"]).day, today)
                    due = max(due, latest)
                self._covered_due[task_id] = due.isoformat()
        self._last_done[task_id] = today.isoformat()
        await self._save()
        self._notify()

    async def async_clear_done(self, task_id: str) -> None:
        """Undo the last Done press (restores the previous state, one step)."""
        prev = self._undo.pop(task_id, None)
        if prev is None:
            return
        for store, key in ((self._last_done, "last_done"), (self._covered_due, "covered_due")):
            if prev.get(key):
                store[task_id] = prev[key]
            else:
                store.pop(task_id, None)
        await self._save()
        self._notify()

    def can_undo(self, task_id: str) -> bool:
        return task_id in self._undo

    async def async_update_tasks(self, tasks: list[dict]) -> None:
        """Swap in new task configs (already normalized) and prune old records."""
        old = {t["id"]: t for t in self.tasks}
        self.tasks = tasks
        ids = {t["id"] for t in tasks}
        for store in (self._last_done, self._covered_due, self._undo):
            for k in [k for k in store if k not in ids]:
                store.pop(k, None)
        for t in tasks:
            prev = old.get(t["id"])
            if not prev:
                continue
            if is_pinned_monthly(t) and not is_pinned_monthly(prev):
                # Just became pinned (date added, or switched to monthly):
                # start from today, don't back-fill months since `created`
                yesterday = dt_util.now().date() - timedelta(days=1)
                self._covered_due[t["id"]] = yesterday.isoformat()
                self._undo.pop(t["id"], None)
            elif prev.get("repeat") != t.get("repeat"):
                # Different kind of task: old coverage means nothing now
                self._covered_due.pop(t["id"], None)
                self._undo.pop(t["id"], None)
            elif t.get("repeat") == "yearly" and prev.get("date") != t.get("date"):
                # New birthday date: the old Done doesn't cover the new occurrence
                self._covered_due.pop(t["id"], None)
                self._undo.pop(t["id"], None)
            # Pinned monthly day change keeps covered_due on purpose: it marks
            # "handled up to this date", so the new day starts after it instead
            # of back-filling every missed month since `created`.
        await self._save()
        self._notify()

    async def async_remove_store(self) -> None:
        await self._store.async_remove()
