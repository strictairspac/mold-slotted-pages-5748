from enum import StrEnum


class JobState(StrEnum):
    QUEUED = "queued"
    DONE = "done"
    FAILED = "failed"
    REJECTED = "rejected"
    CONFLICT = "conflict"
