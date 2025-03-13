import logging
import colorlog
from pathlib import Path
from logging.handlers import TimedRotatingFileHandler, MemoryHandler

class LoggerManager:
    """ Class for managing creation of loggers and creation and deletion of handlers 
    for PyCam software
    """

    _loggers = {}  # Store created loggers to prevent duplicates
    _file_handlers = {}  # Store file handlers to avoid duplicates
    _mem_handlers = {}
    _file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s', '%Y-%m-%d %H:%M:%S')

    @staticmethod
    def add_logger(name, colour = "white", level = logging.INFO):
        """ Add a named logger.

        :param str name: Name of the logger to create
        :param str colour: Colour of the text used for logging messages, defaults to white
        :param int level: Logging level to set for the StreamHandler, defaults to logging.DEBUG
        :return logging.Logger: Newly created logger
        """

        if name not in LoggerManager._loggers:
            logger = logging.getLogger(name)
            logger.setLevel(logging.DEBUG)
            if not logger.handlers:  # Only configure if no handlers exist
                stream_handler = LoggerManager.create_stream_handler(colour, level)
                logger.addHandler(stream_handler)
            LoggerManager._loggers[name] = logger
        return LoggerManager._loggers[name]
    
    @staticmethod
    def add_file_handler(logger, log_path, level=logging.DEBUG):
        """ Add FileHandler to an existing logger.
        If the log path is new then create a new handler, otherwise use the existing handler stored 
        in the _file_handlers dict.

        :param logging.Logger logger: Existing logger to add FileHandler to
        :param (str|Path) log_path: Location to write the log file to
        :param int level: Logging level to set for the FileHandler, defaults to logging.DEBUG
        """
        log_path = Path(log_path)
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            print(f"Error creating log file: {e}")

        file_handler_key = log_path.as_posix()  # Use log file path as key
        if file_handler_key not in LoggerManager._file_handlers:
            root_logger = logger.name == "root"
            file_handler = LoggerManager.create_file_handler(log_path, root_logger=root_logger, level=level)
            LoggerManager._file_handlers[file_handler_key] = file_handler
        
        logger.addHandler(LoggerManager._file_handlers[file_handler_key])

    @staticmethod
    def create_file_handler(log_path, root_logger = False, level=logging.DEBUG):
        """ Create a new file handler.
        The type of file handler will depend on the root_logger parameter. If it is True a 
        TimedRotatingFileHandler will be created, otherwise a FileHandler will be created.

        :param (str|Path) log_path: Path specifying location of the log file
        :param bool root_logger: Is this for the root logger? defaults to False
        :param int level: Logging level for the file handler, defaults to logging.DEBUG
        :return (logging.handlers.TimedRotatingFileHandler, logging.handlers.FileHandler): Newly 
        created file handler
        """
        if root_logger:
            file_handler = TimedRotatingFileHandler(log_path, when = 'D', interval=1, backupCount=5)
        else:
            file_handler = logging.FileHandler(log_path)
        file_handler.setFormatter(LoggerManager._file_formatter)
        file_handler.setLevel(level)

        return file_handler

    @staticmethod
    def remove_file_handler(logger, log_path, delete=False):
        """ Remove Filehandler from an existing logger. Removed based on the path to the log file.

        :param logger logger: Existing logger to remove FileHandler from
        :param (str|Path) log_path: Location of the log file, used as a key to identify a handler
        :param bool delete: Close and delete the file handler after removal, Defaults to False
        """

        log_path = Path(log_path).as_posix()
        if log_path in LoggerManager._file_handlers:
            logger.removeHandler(LoggerManager._file_handlers[log_path])

            if delete:
                LoggerManager._file_handlers[log_path].close()
                del LoggerManager._file_handlers[log_path]
    
    @staticmethod
    def add_mem_handler(logger, log_key, level=logging.DEBUG):
        """ Add a memory handler to an existing logger.
        Will create a new hander if one with the same log_key doesn't already exist, otherwise will 
        use the existing handler.

        :param logging.Logger logger: The logger to add the memory handler to
        :param str log_key: Key identifying the memory handler
        :param int level: Logging level for the memory handler, defaults to logging.DEBUG
        """
        if log_key not in LoggerManager._mem_handlers:
            mem_handler = MemoryHandler(capacity=1e4)
            mem_handler.setFormatter(LoggerManager._file_formatter)
            mem_handler.setLevel(level)

            LoggerManager._mem_handlers[log_key] = mem_handler
        
        logger.addHandler(LoggerManager._mem_handlers[log_key])

    @staticmethod
    def remove_mem_handler(logger, log_key, delete=False):
        """ Remove a memory handler from an existing logger.

        :param logging.Logger logger: The logger to remove the memory handler from
        :param str log_key: Key identifying the specific memory handler
        :param bool delete: Close and delete the memory handler after removal? defaults to False
        """
        if log_key in LoggerManager._mem_handlers:
            logger.removeHandler(LoggerManager._mem_handlers[log_key])

            if delete:
                LoggerManager._mem_handlers[log_key].close()
                del LoggerManager._mem_handlers[log_key]

    @staticmethod
    def set_mem_handler_target(log_key, target):
        """ Set a target handler for a memory handler to flush to

        :param str log_key: Key to identify the specific memory handler to add a target to
        :param logger.Handler target: Handler to set as target for the memory handler
        :return logger.handlers.memoryHandler: Memory handler with added set target
        """
        if log_key in LoggerManager._mem_handlers:
            LoggerManager._mem_handlers[log_key].setTarget(target)

            return LoggerManager._mem_handlers[log_key]

    @staticmethod
    def remove_stream_handlers(logger):
        """ Removes all stream handlers from logger provided.

        :param logger logger: logger object to remove stream handlers from
        """
        for handler in logger.handlers:
            if isinstance(handler, logging.StreamHandler):
                logger.removeHandler(handler)

    @staticmethod
    def replace_stream_handlers(logger, colour = "white", level = logging.ERROR):
        """ Replaces stream handlers to be more consistent with PyCam.

        :param logging.Logger logger: Logger object to modify
        :param str colour: Colour for output of new stream handler
        :param int level: Logging level for the stream handler, defaults to logging.WARNING
        """
        # Start by removing current handlers
        LoggerManager.remove_stream_handlers(logger)

        # Now create a new handler
        stream_handler = LoggerManager.create_stream_handler(colour, level)
        logger.addHandler(stream_handler)

    @staticmethod
    def create_stream_handler(colour, level):
        format_str = f'%(log_color)s%(levelname)-8s%(reset)s%(asctime)s - %({colour})s%(name)s - %(message)s'
        formatter = colorlog.ColoredFormatter(format_str, '%Y-%m-%d %H:%M:%S')
        handler = colorlog.StreamHandler() # Output to console
        handler.setFormatter(formatter)
        handler.setLevel(level)  # Set the desired logging level

        return handler

# Get the root logger
root_logger = logging.getLogger()

# If the root logger doesn't have a file handler then add one
if not any(isinstance(handler, logging.FileHandler) for handler in root_logger.handlers):
    # Start by defining the root log path
    root_log_path = Path.home() / "pycam_logs" / "root.log"

    # Add the file handler
    LoggerManager.add_file_handler(root_logger, root_log_path, level = logging.INFO)
    
    root_logger.setLevel(logging.INFO)
    
    # Log message on creation
    root_logger.info("New session started")
