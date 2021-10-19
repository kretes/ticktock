import inspect
import math
import os
import time
from dataclasses import dataclass
from typing import Dict, Optional

DEFAULT_PERIOD = 2


class ClockCollection:
    def __init__(self, period: Optional[float] = None) -> None:
        self.clocks: Dict[str, Clock] = {}
        self._last_refresh_time_s: Optional[float] = None
        self._period: float = period or os.environ.get(
            "TICKTOCK_DEFAULT_PERIOD", float(DEFAULT_PERIOD)
        )

    def update(self):
        if (
            self._last_refresh_time_s is None
            or time.perf_counter() - self._last_refresh_time_s > self._period
        ):
            self.print()
            self._last_refresh_time_s = time.perf_counter()

    def print(self):
        print("# Clocks")
        for clock in self.clocks.values():
            for key, info in clock.aggregate_times.items():
                print(
                    f"Clock {clock.name} [{key}]: avg = {info.avg_time_ns}, last = {info.last_time_ns}, n = {info.n_periods}"
                )


_INTIME_CLOCKS = ClockCollection()


@dataclass
class TickTimeInfo:
    file_name: str
    line_no: str


@dataclass
class AggregateTimes:
    avg_time_ns: float
    min_time_ns: int
    max_time_ns: int
    last_time_ns: int
    last_dt_ns: int

    n_periods: int = 1

    def update(self, tock_time_ns: int) -> None:
        self.last_dt_ns = tock_time_ns - self.last_time_ns
        self.n_periods += 1
        self.max_time_ns = max(tock_time_ns, self.max_time_ns or -math.inf)
        self.min_time_ns = min(tock_time_ns, self.min_time_ns or math.inf)
        self.avg_time_ns = (
            (self.avg_time_ns or 0) * (self.n_periods - 1) + self.last_dt_ns
        ) / self.n_periods
        self.last_time_ns = tock_time_ns


class Clock:
    def __init__(
        self,
        name: str = None,
        collection: Optional[ClockCollection] = None,
        tick_time_ns: Optional[int] = None,
        tick_frame_info: Optional[inspect.FrameInfo] = None,
    ) -> None:
        self.collection: ClockCollection = collection or _INTIME_CLOCKS

        self.name: str = name or f"clock_{len(self.collection.clocks)}"

        self._tick_frame_info: inspect.FrameInfo = tick_frame_info or inspect.stack()[1]
        self._unique_id = (
            name or f"{self._tick_frame_info.filename}:{self._tick_frame_info.lineno}"
        )

        self.aggregate_times: Dict[str, AggregateTimes] = {}

        self.collection.clocks[self._unique_id] = self

        self._tick_time_ns: Optional[int] = tick_time_ns

    def tick(self) -> int:
        self._tick_time_ns: float = time.perf_counter_ns()
        return self._tick_time_ns

    def tock(self, name: str = None) -> int:
        if not name:
            tock_caller_frame = inspect.stack()[1]
            name = f"{tock_caller_frame.filename}:{self._tick_frame_info.lineno}-{tock_caller_frame.lineno}"

        tock_time_ns = time.perf_counter_ns()

        if name in self.aggregate_times:
            self.aggregate_times[name].update(tock_time_ns)
        else:
            dt = tock_time_ns - self._tick_time_ns
            self.aggregate_times[name] = AggregateTimes(
                last_time_ns=dt,
                avg_time_ns=dt,
                min_time_ns=dt,
                max_time_ns=dt,
                last_dt_ns=dt,
            )

        self.collection.update()
        return tock_time_ns


def tick(
    name: str = None,
    collection: Optional[ClockCollection] = None,
    tick_time_ns: Optional[int] = None,
) -> Clock:
    collection: ClockCollection = collection or _INTIME_CLOCKS
    if not name:
        tick_frame_info: inspect.FrameInfo = inspect.stack()[1]
        if f"{tick_frame_info.filename}:{tick_frame_info.lineno}" in collection.clocks:
            clock = collection.clocks[
                f"{tick_frame_info.filename}:{tick_frame_info.lineno}"
            ]
            clock.tick()
            return clock
    clock = Clock(
        name=name,
        collection=collection,
        tick_time_ns=tick_time_ns,
        tick_frame_info=tick_frame_info,
    )
    clock.tick()
    return clock
