"""The alarm is the whole reason this project was rewritten, so it is tested without hardware.

`Watchdog` takes `now` as an argument precisely so these tests can drive time by hand: a real
clock would make them slow and flaky, and a sleeping test proves nothing about the thresholds.
"""

from __future__ import annotations

import pytest

from dito.audio.level import DEAD_THRESHOLD, QUIET_THRESHOLD, State, Watchdog

SILENCE = 0.0
ROOM_TONE = 0.0038      # measured: H510 headset, silent room
SPEECH = 0.05           # measured range is 0.036-0.272


def feed_for(wd: Watchdog, peak: float, seconds: float, start: float, step: float = 0.05) -> float:
    """Push `peak` for `seconds` of simulated time; return the clock afterwards."""
    now = start
    end = start + seconds
    while now < end:
        now += step
        wd.feed(peak, now)
    return now


def fresh(**kwargs) -> tuple[Watchdog, float]:
    wd = Watchdog(**kwargs)
    wd.restart(0.0)
    return wd, 0.0


def test_grace_period_does_not_alarm_immediately():
    """PipeWire wakes a suspended source lazily; the first blocks are legitimately silent."""
    wd, now = fresh()
    now = feed_for(wd, SILENCE, 0.25, now)
    assert wd.state is State.OK


def test_digital_silence_alarms_within_a_second():
    """The failure that cost 99 seconds of speech has to be caught in about one."""
    wd, now = fresh()
    now = feed_for(wd, SILENCE, 1.2, now)
    assert wd.state is State.DEAD


def test_dead_alarm_needs_grace_plus_dead_window():
    wd, now = fresh(grace_ms=300, dead_ms=700)
    now = feed_for(wd, SILENCE, 0.9, now)
    assert wd.state is State.OK, "must not fire before grace + dead_ms = 1.0s"
    now = feed_for(wd, SILENCE, 0.2, now)
    assert wd.state is State.DEAD


def test_speech_never_alarms():
    wd, now = fresh()
    now = feed_for(wd, SPEECH, 5.0, now)
    assert wd.state is State.OK
    assert wd.ever_heard


def test_room_tone_alone_warns_quiet_not_dead():
    """A live but useless microphone: something is arriving, just nothing usable."""
    wd, now = fresh()
    now = feed_for(wd, ROOM_TONE, 3.0, now)
    assert wd.state is State.QUIET


def test_pause_after_speech_does_not_warn():
    """The regression this gate exists for: staying silent between sentences is not a fault.
    Room tone sits at 0.0038, below the quiet threshold, so without the `ever_heard` gate every
    pause longer than quiet_ms would raise a false 'audio too quiet'."""
    wd, now = fresh()
    now = feed_for(wd, SPEECH, 1.0, now)
    now = feed_for(wd, ROOM_TONE, 6.0, now)
    assert wd.state is State.OK


def test_device_dying_mid_sentence_still_alarms():
    """DEAD stays armed after speech: exact zeros following real audio means the device died."""
    wd, now = fresh()
    now = feed_for(wd, SPEECH, 1.0, now)
    now = feed_for(wd, SILENCE, 1.2, now)
    assert wd.state is State.DEAD


def test_alarm_clears_when_audio_returns():
    wd, now = fresh()
    now = feed_for(wd, SILENCE, 1.5, now)
    assert wd.state is State.DEAD
    now = feed_for(wd, SPEECH, 0.5, now)
    assert wd.state is State.OK


def test_dead_downgrades_to_quiet_when_weak_signal_returns():
    """Device alive again but level still unusable: amber, not red, and not green either."""
    wd, now = fresh()
    now = feed_for(wd, SILENCE, 1.5, now)
    assert wd.state is State.DEAD
    now = feed_for(wd, ROOM_TONE, 0.5, now)
    assert wd.state is State.QUIET


def test_single_click_does_not_clear_the_alarm():
    """Clearing requires sustained sound, so one spike cannot blink the alarm off and back on."""
    wd, now = fresh(clear_ms=200)
    now = feed_for(wd, SILENCE, 1.5, now)
    assert wd.state is State.DEAD
    wd.feed(SPEECH, now + 0.05)
    assert wd.state is State.DEAD


def test_overflow_becomes_choppy_only_after_three():
    wd, _ = fresh()
    wd.record_overflow()
    wd.record_overflow()
    assert not wd.choppy
    wd.record_overflow()
    assert wd.choppy


@pytest.mark.parametrize(
    "peak,expected_ever_heard",
    [(SILENCE, False), (ROOM_TONE, False), (QUIET_THRESHOLD, True), (SPEECH, True)],
)
def test_ever_heard_tracks_the_quiet_threshold(peak, expected_ever_heard):
    wd, now = fresh()
    feed_for(wd, peak, 1.0, now)
    assert wd.ever_heard is expected_ever_heard


def test_a_single_transient_does_not_count_as_having_heard_you():
    """A keystroke as the hotkey goes down is 100 ms of signal. It used to latch `ever_heard` for
    the whole session and permanently disarm the amber warning — measured on a real recording
    where two blocks out of forty crossed the line, median peak 0.00069, and nothing was said."""
    wd, now = fresh(clear_ms=200)
    now = feed_for(wd, SPEECH, 0.10, now)      # the click
    now = feed_for(wd, 0.0005, 4.0, now)       # then a dead microphone

    assert not wd.ever_heard, "um estalo não é ter ouvido a pessoa"
    assert wd.state is not State.OK, "o alarme tinha que estar aceso"


def test_sustained_speech_does_count(fresh_kwargs=None):
    wd, now = fresh(clear_ms=200)
    feed_for(wd, SPEECH, 1.0, now)
    assert wd.ever_heard


def test_thresholds_sit_between_the_measured_floor_and_the_measured_speech():
    """Guards the numbers themselves. Room tone measured at 0.0038 and the weakest logged speech
    at 0.036: a threshold outside that band is either a false alarm or a missed one."""
    assert DEAD_THRESHOLD < ROOM_TONE
    assert ROOM_TONE < QUIET_THRESHOLD < 0.036
