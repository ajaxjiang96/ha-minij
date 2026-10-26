"""Exercise notification deduplication without relying on appliance status."""

from datetime import datetime, timedelta

from custom_components.minij.api import DeviceNotification
from custom_components.minij.notifications import NotificationTracker

BASE = datetime(2026, 1, 1, 12)


def message(identifier, seconds=0, kind="wash_completed"):
    return DeviceNotification(identifier, BASE + timedelta(seconds=seconds), kind)


def test_baseline_new_messages_duplicates_and_late_history():
    tracker = NotificationTracker()
    old = message("old")
    assert tracker.consume([old]) == []
    new = message("new", 60)
    same_second = message("same-second", 60, "cleaning_completed")
    reminder = message("reminder", 61, None)
    assert tracker.consume([reminder, same_second, new, old]) == [same_second, new]
    assert tracker.consume([reminder, same_second, new, old]) == []
    assert tracker.consume([message("late-old", -60), old]) == []
    # Editing or replaying a known ID never creates another completion.
    assert tracker.consume([message("new", 120)]) == []
    assert tracker.consume([message("next", 180)]) == [message("next", 180)]


def test_empty_baseline_first_real_message_and_recovery_gap():
    tracker = NotificationTracker()
    assert tracker.consume([]) == []
    assert tracker.consume([message("first")]) == [message("first")]
    tracker.reset_baseline()
    assert tracker.consume([message("during-outage", 60), message("first")]) == []
    assert tracker.consume([message("during-outage", 60)]) == []
    assert tracker.consume([message("after-recovery", 120)]) == [
        message("after-recovery", 120)
    ]
    # A fresh tracker on restart baselines all existing history.
    assert NotificationTracker().consume([message("after-recovery", 120)]) == []
