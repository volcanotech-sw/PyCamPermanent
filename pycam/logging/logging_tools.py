import logging
from pathlib import Path
from logging.handlers import TimedRotatingFileHandler

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
    root_logger.setLevel(logging.INFO)

    root_logger.info("New session started")

