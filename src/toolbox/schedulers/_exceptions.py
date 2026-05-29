class SchedulerError(Exception):
    """Base class for all toolbox.schedulers exceptions."""


class AddUrlError(SchedulerError):
    """The id already exists in the queue"""


class AddQueueError(SchedulerError):
    """The id already exists in the queue"""


class RemoveQueueError(SchedulerError):
    """The id already exists in the queue"""


class EmptyQueueError(SchedulerError):
    """The queue is empty"""
