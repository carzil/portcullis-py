import copy


class Logger:
    def __init__(self, parent, **kwargs):
        self._extra = kwargs
        self._logger = parent

    def child(self, **kwargs):
        extra = copy.copy(self._extra)
        extra.update(kwargs)
        return Logger(self._logger, **extra)

    def info(self, *args, **kwargs):
        self._logger.info(*args, extra=self._extra, **kwargs)

    def warn(self, *args, **kwargs):
        self._logger.warning(*args, extra=self._extra, **kwargs)

    def err(self, *args, **kwargs):
        self._logger.error(*args, extra=self._extra, **kwargs)

    def debug(self, *args, **kwargs):
        self._logger.debug(*args, extra=self._extra, **kwargs)

    def exception(self, *args, **kwargs):
        self._logger.exception(*args, extra=self._extra, **kwargs)

    def setLevel(self, level):
        self._logger.setLevel(level)
