import logging
import colorlog
from pathlib import Path
from logging.handlers import TimedRotatingFileHandler

class LoggerManager:
    _loggers = {}  # Store created loggers to prevent duplicates

    @staticmethod
    def add_logger(name, colour):
        if name not in LoggerManager._loggers:
            logger = logging.getLogger(name)
            if not logger.handlers:  # Only configure if no handlers exist
                # Configure the logger (e.g., set level, add handlers)
                format_str = f'%(log_color)s%(levelname)-8s%(reset)s%(asctime)s - %({colour})s%(name)s - %(message)s'
                formatter = colorlog.ColoredFormatter(format_str, '%Y-%m-%d %H:%M:%S')
                handler = colorlog.StreamHandler() # Output to console
                handler.setFormatter(formatter)
                logger.addHandler(handler)
                logger.setLevel(logging.DEBUG)  # Set the desired logging level
            LoggerManager._loggers[name] = logger
        return LoggerManager._loggers[name]

def remove_stream_handler(logger):
    """ Removes all stream handlers from logger provided.

    :param logger logger: logger object to remove stream handler from
    """
    for handler in logger.handlers:
        if isinstance(handler, logging.StreamHandler):
            logger.removeHandler(handler)

# Set up the root logger
root_logger = logging.getLogger()

# If the root logger doesn't have a file handler then add one
if not any(isinstance(handler, logging.FileHandler) for handler in root_logger.handlers):
    # Start by defining the root log path
    root_log_path = Path.home() / "pycam_logs" / "root.log"
    root_log_path.parent.mkdir(parents=True, exist_ok=True)

    # Then setup a file handler and formatter for the root logger
    root_file_handler = TimedRotatingFileHandler(
        root_log_path, when = 'D', interval=1, backupCount=5
    )
    root_file_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        '%Y-%m-%d %H:%M:%S'
    )

    root_file_handler.setFormatter(root_file_formatter)
    root_logger.addHandler(root_file_handler)

    root_logger.info("New session started")
