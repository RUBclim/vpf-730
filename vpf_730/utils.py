from __future__ import annotations

import contextlib
import sqlite3
import sys
from collections.abc import Generator
from collections.abc import ItemsView
from collections.abc import Iterable
from collections.abc import Iterator
from collections.abc import Mapping
from functools import wraps
from typing import Callable
from typing import Generic
from typing import TypeVar

if sys.version_info >= (3, 10):  # pragma >=3.10 cover
    from typing import ParamSpec
else:  # pragma <3.10 cover
    from typing_extensions import ParamSpec


@contextlib.contextmanager
def connect(db_path: str) -> Generator[sqlite3.Connection, None, None]:
    """Context manager to connect to a sqlite database.

    :param db_path: path to the sqlite database

    :return: A Generator yielding an open sqlite connection
    """
    with contextlib.closing(
        sqlite3.connect(
            db_path,
            detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
        ),
    ) as db:
        db.row_factory = sqlite3.Row
        with db:
            yield db


P = ParamSpec('P')
R = TypeVar('R')


def retry(
        retries: int,
        exceptions: tuple[type[Exception], ...] = (Exception,),
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Decorator to retry a function ``retries`` times when a specific
    exceptions is raised (defined in ``exceptions``). If any other exception is
    raised, it will not retry the function.

    It can be used like this: A function is decorated and it is retried a
    maximum of 10 times when a ``ValueError`` or ``KeyError`` is raised. Every
    other exception will instantly be raised.

    .. code-block:: python

        @retry(retries=10, exceptions=(ValueError, KeyError))
        def my_func():
            ...

    :param retries: number of times a function is retried
    :param exceptions: the exceptions to except and retry
    """
    def retry_dec(f: Callable[P, R]) -> Callable[P, R]:
        @wraps(f)
        def inner(*args: P.args, **kwargs: P.kwargs) -> R:
            curr_tries = 0
            while True:
                try:
                    return f(*args, **kwargs)
                except exceptions:
                    if curr_tries >= retries:
                        raise
                    curr_tries += 1

        return inner
    return retry_dec


K = TypeVar('K')
V = TypeVar('V')


class FrozenDict(Generic[K, V]):
    """Immutable, generic implementation of a frozen dictionary."""

    def __init__(self, d: Mapping[K, V]) -> None:
        self._d = d

    def __getitem__(self, k: K) -> V:
        return self._d[k]

    def __contains__(self, k: K) -> bool:
        return k in self._d

    def __iter__(self) -> Iterator[K]:
        yield from self._d

    def get(self, k: K) -> V | None:
        return self._d.get(k)

    def values(self) -> Iterable[V]:
        return self._d.values()

    def keys(self) -> Iterable[K]:
        return self._d.keys()

    def items(self) -> ItemsView[K, V]:
        return self._d.items()

    def __repr__(self) -> str:
        return f'{type(self).__name__}({self._d})'
