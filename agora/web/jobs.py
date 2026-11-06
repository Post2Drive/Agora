"""Background jobs for the web app: building a project and running a simulation.

One job per project at a time. Jobs run in threads and report progress through a
log and a small status dict that the browser polls. Stopping is cooperative: the job
finishes its current step (a chunk or a round), saves it, and stops cleanly.
"""
from __future__ import annotations

import itertools
import threading
import time
import traceback
from typing import Callable

_ids = itertools.count(1)


class Job:
    def __init__(self, kind: str, project: str):
        self.id = next(_ids)
        self.kind = kind                 # create | run
        self.project = project
        self.state = "running"           # running | done | stopped | error
        self.log: list[str] = []
        self.progress: dict = {}
        self.error = ""
        self.started = time.time()
        self.finished: float | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def say(self, msg: str) -> None:
        self.log.append(msg)
        if len(self.log) > 400:
            del self.log[:100]

    def stop(self) -> None:
        self._stop.set()

    @property
    def stopping(self) -> bool:
        return self._stop.is_set()

    def as_dict(self) -> dict:
        return {"id": self.id, "kind": self.kind, "project": self.project, "state": self.state,
                "log": self.log[-80:], "progress": self.progress, "error": self.error,
                "started": self.started, "finished": self.finished,
                "stopping": self.stopping and self.state == "running"}


class Jobs:
    def __init__(self):
        self.by_project: dict[str, Job] = {}
        self.lock = threading.Lock()

    def current(self, project: str) -> Job | None:
        return self.by_project.get(project)

    def busy(self, project: str) -> bool:
        j = self.by_project.get(project)
        return bool(j and j.state == "running")

    def start(self, kind: str, project: str, fn: Callable[[Job], None]) -> Job:
        with self.lock:
            if self.busy(project):
                raise RuntimeError("This project already has a job running.")
            job = Job(kind, project)
            self.by_project[project] = job

        def runner():
            try:
                fn(job)
                job.state = "stopped" if job.stopping else "done"
            except Exception as e:  # noqa: BLE001 - shown to the user
                from ..pipeline import Stopped
                if isinstance(e, (Stopped, KeyboardInterrupt)):
                    job.state = "stopped"
                    job.say("Stopped. Everything finished so far is saved.")
                else:
                    job.state = "error"
                    job.error = str(e) or e.__class__.__name__
                    job.say("Error: " + job.error)
                    job.say(traceback.format_exc(limit=3))
            finally:
                job.finished = time.time()

        job._thread = threading.Thread(target=runner, name=f"agora-{kind}-{project}", daemon=True)
        job._thread.start()
        return job

    def stop_all(self) -> None:
        for j in self.by_project.values():
            j.stop()
