import abc
import logging
import sys
from string import Formatter
from typing import TYPE_CHECKING, Callable, Iterable, List, Optional, TextIO

from ticktock.utils import format_ns_interval, value_from_env

if TYPE_CHECKING:
    from ticktock.timer import Clock

try:
    import tqdm

    has_tqdm = True
except ImportError:
    has_tqdm = False

logger = logging.getLogger("ticktock.renderers")

UP: Callable[[int], str] = lambda x: f"\x1B[{x}A" if x else ""
CLR = "\r\x1B[0K"

TIME_FIELDS = {
    "mean": lambda times: times.avg_time_ns,
    "std": lambda times: times.std_time_ns,
    "min": lambda times: times.min_time_ns,
    "max": lambda times: times.max_time_ns,
    "last": lambda times: times.last_time_ns,
}

FIELDS = {
    "count": lambda clock, times: times.n_periods,
    "tick_name": lambda clock, times: clock.tick_name,
    "tock_name": lambda clock, times: times.tock_name,
    "tick_line": lambda clock, times: clock.tick_line,
    "tock_line": lambda clock, times: times.tock_line,
    "tick_filename": lambda clock, times: clock.tick_filename,
    "tock_filename": lambda clock, times: times.tock_filename,
    "avg_time_ns": lambda clock, times: times.avg_time_ns,
    "std_time_ns": lambda clock, times: times.std_time_ns,
    "min_time_ns": lambda clock, times: times.min_time_ns,
    "max_time_ns": lambda clock, times: times.max_time_ns,
    "last_time_ns": lambda clock, times: times.last_time_ns,
}


class AbstractRenderer(abc.ABC):
    def render(self, render_data: List["Clock"]) -> None:
        ...


FORMATS = {
    "short": "⏱️ [{tick_name}-{tock_name}] {mean} count={count}",
    "long": "⏱️ [{tick_name}-{tock_name}] "
    "{mean} ({std} std) min={min} max={max}"
    " count={count} last={last}",
}


class StandardRenderer(AbstractRenderer):
    _format: str = ""
    _fields: List[str] = []
    _time_fields: List[str] = []
    _max_terms: int
    _out: TextIO
    _no_update: bool = False

    def __init__(
        self,
        format: Optional[str] = None,
        out: TextIO = sys.stderr,
        max_terms: int = 2,
        no_update: bool = False,
    ) -> None:
        self.set_format(format or value_from_env("TICKTOCK_DEFAULT_FORMAT", "short"))
        self._max_terms = max_terms
        self._out = out
        self._no_update = no_update

    def set_format(self, format: str):
        self._format = format
        if self._format in FORMATS:
            self._format = FORMATS[self._format]
        self._fields = []
        self._time_fields = []
        for (_, field_name, _, _) in Formatter().parse(self._format):
            if field_name is not None:
                if field_name in FIELDS:
                    self._fields.append(field_name)
                    continue
                if field_name in TIME_FIELDS:
                    self._time_fields.append(field_name)
                    continue
                raise ValueError(f"Field {field_name} unknown in format string")
        self._has_printed = 0

    def render(self, render_data: List["Clock"]) -> None:
        logger.debug("Rendering clock format={self._format}")
        ls: List[str] = []
        for clock in render_data:
            for line in self.render_times(clock):
                ls.append(line)
        if has_tqdm:
            with tqdm.tqdm.external_write_mode(sys.stderr, nolock=True):
                if self._no_update:
                    self._out.write("\n".join(ls) + "\n")
                else:
                    self._out.write(
                        UP(self._has_printed) + CLR + f"\n{CLR}".join(ls) + "\n"
                    )
                self._out.flush()
        else:
            if self._no_update:
                self._out.write("\n".join(ls) + "\n")
            else:
                self._out.write(
                    UP(self._has_printed) + CLR + f"\n{CLR}".join(ls) + "\n"
                )
            self._out.flush()
        self._has_printed = len(ls)

    def render_times(self, clock: "Clock") -> Iterable[str]:
        for times in clock.times.values():
            yield (
                ""
                + (clock._format or self._format).format(
                    **{
                        key: format_ns_interval(
                            TIME_FIELDS[key](times), max_terms=self._max_terms
                        )
                        for key in self._time_fields
                    },
                    **{key: str(FIELDS[key](clock, times)) for key in self._fields},
                )
            )


class LoggingRenderer(AbstractRenderer):
    def __init__(
        self, logger=None, level: str = "INFO", extra_as_kwargs: bool = False
    ) -> None:
        self.logger = logger or logging.getLogger("ticktock")
        _log_function = {
            "DEBUG": self.logger.debug,
            "INFO": self.logger.info,
            "WARNING": self.logger.warning,
            "ERROR": self.logger.error,
            "CRITICAL": self.logger.critical,
        }[level]
        if extra_as_kwargs:

            def _log(msg, **kwargs):
                _log_function(msg, **kwargs)

        else:

            def _log(msg, **kwargs):
                _log_function(msg, extra=kwargs)

        self._log = _log

    def render(self, render_data: List["Clock"]) -> None:
        for clock in render_data:
            for times in clock.times.values():
                self._log(
                    "clock",
                    tick_name=clock.tick_name,
                    tock_name=clock.tick_name,
                    mean=times.avg_time_ns * 1e9,
                    std=times.std_time_ns * 1e9,
                    min=times.min_time_ns * 1e9,
                    max=times.max_time_ns * 1e9,
                    count=times.n_periods,
                )
