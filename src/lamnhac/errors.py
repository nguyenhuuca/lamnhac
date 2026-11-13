"""Exception tree; each class carries the CLI exit code."""


class LamnhacError(Exception):
    exit_code = 1


class UsageError(LamnhacError):
    exit_code = 2


class InputError(LamnhacError):
    exit_code = 3


class ProcessingError(LamnhacError):
    exit_code = 4


class OutputError(LamnhacError):
    exit_code = 5
