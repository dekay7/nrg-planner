"""Price-data fallback state machine, independent of HA and equipment commands."""
from dataclasses import dataclass

RECOVERY_SECONDS = 120
LIVE_MAX_AGE = 900
KNOWN_SOURCES = frozenset({"flat", "time_of_use", "running_average", "day_ahead", "external_live", "external_forecast"})


def live_valid(stamp, now, *, hourly=False):
    return (stamp is not None and 0 <= now - stamp < LIVE_MAX_AGE
            and (not hourly or int(stamp // 3600) == int(now // 3600)))


@dataclass
class PriceFallback:
    manual: bool = False
    automatic: bool = False
    recovery_since: float | None = None
    recovery_observation: object = None
    state: str = "Healthy"

    def update(self, now, *, enabled, known, degraded=False, observation=None, allow_recovery=False):
        """Require distinct valid observations across two minutes before recovery.

        Command-time checks may enter fallback immediately, but only a coordinator
        update can release it, invalidating the old plan before making a new one.
        """
        if not enabled:
            self.automatic = False
            self.recovery_since = None
            self.state = "Healthy" if known and not degraded else "Degraded"
        elif self.manual or not known:
            self.automatic = self.automatic or not known
            self.recovery_since = None
            self.state = "Fallback"
        elif self.automatic:
            if self.recovery_since is None or now < self.recovery_since:
                self.recovery_since = now
                self.recovery_observation = observation
            if (allow_recovery and now - self.recovery_since >= RECOVERY_SECONDS
                    and observation != self.recovery_observation and not degraded):
                self.automatic = False
                self.recovery_since = None
                self.state = "Healthy"
            else:
                self.state = "Recovering"
        else:
            self.state = "Degraded" if degraded else "Healthy"
        return enabled and (self.manual or self.automatic)
