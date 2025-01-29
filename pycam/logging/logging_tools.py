import logging
import colorlog
from pathlib import Path
from logging.handlers import TimedRotatingFileHandler

class LoggerManager:
    """ Class for manging creation of loggers and creation and deltion of handlers 
    for PyCam software
    """

    _loggers = {}  # Store created loggers to prevent duplicates
    _file_handlers = {}  # Store file handlers to avoid duplicates
    _file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s', '%Y-%m-%d %H:%M:%S')

    @staticmethod
    def add_logger(name, colour = "white", level = logging.INFO):
        """ Add a named logger.

        :param str name: Name of the logger to create
        :param str colour: Colour of the text used for logging messages, defaults to white
        :param int level: Logging level to set for the StreamHandler, defaults to logging.DEBUG
        :return logger: Reference to logger
        """

        if name not in LoggerManager._loggers:
            logger = logging.getLogger(name)
            logger.setLevel(logging.DEBUG)
            if not logger.handlers:  # Only configure if no handlers exist
                # Configure the logger (e.g., set level, add handlers)
                format_str = f'%(log_color)s%(levelname)-8s%(reset)s%(asctime)s - %({colour})s%(name)s - %(message)s'
                formatter = colorlog.ColoredFormatter(format_str, '%Y-%m-%d %H:%M:%S')
                handler = colorlog.StreamHandler() # Output to console
                handler.setFormatter(formatter)
                handler.setLevel(level)  # Set the desired logging level
                logger.addHandler(handler)
            LoggerManager._loggers[name] = logger
        return LoggerManager._loggers[name]
    
    @staticmethod
    def add_file_handler(logger, log_path, level=logging.DEBUG):
        """ Add FileHandler to an existing logger. If the log path is new then create a new handler,
        if not then use the existing one stored in the handler dict.

        :param logger logger: Existing logger to add FileHandler to
        :param (str|Path) log_path: Location to write the log file to
        :param int level: Logging level to set for the FileHandler, defaults to logging.DEBUG
        """
        log_path = Path(log_path)
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            print(f"Error creating log file: {e}")

        file_handler_key = str(log_path)  # Use log file path as key
        if file_handler_key not in LoggerManager._file_handlers:
            if logger.name == 'root':
                file_handler = TimedRotatingFileHandler(log_path, when = 'D', interval=1, backupCount=5)
            else:
                file_handler = logging.FileHandler(log_path)
            file_handler.setFormatter(LoggerManager._file_formatter)
            file_handler.setLevel(level)
            LoggerManager._file_handlers[file_handler_key] = file_handler
        
        logger.addHandler(LoggerManager._file_handlers[file_handler_key])

    @staticmethod
    def remove_file_handler(logger, log_path):
        """ Remove Filehandler from an existing logger. Removed based on the path to the log file.

        :param logger logger: Existing logger to remove FileHandler from
        :param (str|Path) log_path: Location of the log file
        """
        log_path = Path(log_path).resolve()
        for handler in logger.handlers:
            if isinstance(handler, logging.FileHandler):
                handler_path = Path(handler.baseFilename).resolve()
                if handler_path == log_path:
                    logger.removeHandler(handler)

    @staticmethod
    def delete_file_handler(log_path):
        """ Close and delete a saved FileHandler

        :param (str|Path) log_path: _description_
        """
        log_path = Path(log_path)
        try:
            handler = LoggerManager._file_handlers[log_path]
            handler.close()
            del LoggerManager._file_handlers[log_path]
        except KeyError:
            pass

    @staticmethod
    def remove_stream_handlers(logger):
        """ Removes all stream handlers from logger provided.

        :param logger logger: logger object to remove stream handlers from
        """
        for handler in logger.handlers:
            if isinstance(handler, logging.StreamHandler):
                logger.removeHandler(handler)

# Set up the root logger
root_logger = logging.getLogger()

# If the root logger doesn't have a file handler then add one
if not any(isinstance(handler, logging.FileHandler) for handler in root_logger.handlers):
    # Start by defining the root log path
    root_log_path = Path.home() / "pycam_logs/root.log"

    # Add the file handler
    LoggerManager.add_file_handler(root_logger, root_log_path, level = logging.INFO)
    
    root_logger.setLevel(logging.INFO)
    
    # Log message on creation
    root_logger.info("New session started")
