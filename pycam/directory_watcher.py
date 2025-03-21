# -*- coding: utf-8 -*-

# This file has been modified from Peters' plumetrack directory watcher https://github.com/nonbiostudent/plumetrack

import sys
import os.path
import datetime
import calendar
import time
import threading
import queue
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler


def can_watch_directories():
    """
    Returns true if there is a directory watching implementation for
    this system type.
    """

    # because this function takes a long time to complete - we cache the result
    # and return that for future calls
    if not hasattr(can_watch_directories, 'result_cache'):

        # check if we have better than 1 second resolution on the system clock
        t1 = datetime.datetime.utcnow()
        time.sleep(0.5)
        t2 = datetime.datetime.utcnow()

        if abs((0.5 - (t2 - t1).microseconds * 1e-6)) > 0.1:
            result = False

        # check if the modules needed for directory watching are installed.
        # For Linux systems we use the inotify Python bindings and for Windows
        # we use the win32 Python module.
        if sys.platform == 'linux2' or sys.platform == 'linux':
            try:
                import pyinotify
                result = True
            except ImportError:
                result = False

        elif sys.platform == 'win32':
            try:
                import win32file
                import win32con
                result = True
            except ImportError:
                result = False
        else:
            result = False

        # cache the result so that future calls to this function return faster
        can_watch_directories.result_cache = result

    return can_watch_directories.result_cache


def create_dir_watcher(dir_name, recursive, func, *args, **kwargs):
    """
    Returns a watcher class suitable for this system type, or
    None if no implementation is available.

    * dir_name - path to directory to be watched
    * recursive - boolean specifying whether to watch subdirectories as well.
    * func - callable which will be called each time a new file is detected,
             this will be passed the the full path to the created file, the
             creation time of the file (a datetime object), and any additional
             args or kwargs specified.
    * args/kwargs - additional arguments to pass to func.
    """
    if can_watch_directories():

        if sys.platform == 'linux2':
            return LinuxDirectoryWatcher(dir_name, func, recursive, *args, **kwargs)
        elif sys.platform == 'linux':
            return PiDirectoryWatcher(dir_name, func, recursive, *args, **kwargs)
        elif sys.platform == 'win32':
            # return PiDirectoryWatcher(dir_name, func, recursive, *args, **kwargs)
            return WindowsDirectoryWatcher(dir_name, func, recursive, *args, **kwargs)
        else:
            raise RuntimeError("Failed to create DirectoryWatcher. Unsupported OS")
    else:
        return None


class _DirectoryWatcherBase:
    """
    Base class for watcher classes.
    """

    def __init__(self, dir_name, func, recursive, *args, **kwargs):
        self.dir_to_watch = dir_name
        self.__func = func
        self.__args = args
        self.__kwargs = kwargs

    def _on_new_file(self, filename, time_):
        self.__func(filename, time_, *self.__args, **self.__kwargs)

    def start(self):
        raise NotImplementedError

    def stop(self):
        raise NotImplementedError


# ======================================================================================================================
# RASPBERRY PI DIRECTORY WATCHER
class PiDirectoryWatcher(_DirectoryWatcherBase):
    """
    Directory watcher that will work on a Raspberry Pi
    """

    def __init__(self, dir_name, func, recursive=True, *args, **kwargs):
        _DirectoryWatcherBase.__init__(self, dir_name, func, recursive, *args, **kwargs)
        self.observer = Observer()
        self.recursive = recursive
        self.event_handler = Handler(self._on_new_file)

    def start(self):

        self.observer.schedule(
            self.event_handler, self.dir_to_watch, recursive=self.recursive
        )
        self.observer.start()
        print(f"Observer started for {self.dir_to_watch}")
        # This just returns here, so if you want to wait for it you'll need a sleep loop or a call to self.observer.join()

    def stop(self):
        self.observer.stop()
        self.observer.join()
        print(f"Observer Stopped for {self.dir_to_watch}")


class Handler(FileSystemEventHandler):

    def __init__(self, func):
        self.func = func

    def on_any_event(self, event):
        # print(event)
        pass

    def on_created(self, event):
        self.func(event.src_path, None)


# ======================================================================================================================


try:
    import pyinotify
    class LinuxDirectoryWatcher(_DirectoryWatcherBase, pyinotify.ProcessEvent):
        """
        Watcher class using inotify.
        """

        def __init__(self, dir_name, func, recursive, *args, **kwargs):
            # note that you are not supposed to override the __init__ method
            # of the ProcessEvent class, however, in order to pass args
            # through to the DirWatcherBase class I need to.

            pyinotify.ProcessEvent.__init__(self)
            _DirectoryWatcherBase.__init__(self, dir_name, func, recursive, *args, **kwargs)

            watch_manager = pyinotify.WatchManager()
            mask = pyinotify.EventsCodes.OP_FLAGS['IN_CREATE'] | pyinotify.EventsCodes.OP_FLAGS['IN_CLOSE_WRITE']
            watch_manager.add_watch(dir_name, mask, rec=recursive, auto_add=recursive)

            self.notifier = pyinotify.ThreadedNotifier(watch_manager, self)

            self.__created_files = {}


    def start(self):
        self.notifier.start()


    def stop(self):
        self.notifier.stop()


    def process_IN_CREATE(self, event):
        # we want to make sure that the process that created the new file has
        # finished writing to it before we call the on_new_file function, otherwise
        # we may end up reading a partly written file. To do this, we store the
        # creation time of each file in a dictionary, and then wait for the in_close_write
        # event to trigger before calling the on_new_file function. This also means
        # that the on_new_file function will only be called if the file is newly created,
        # editing an existing file will not result in on_new_file being called.

        t = datetime.datetime.utcnow()
        self.__created_files[os.path.join(event.path, event.name)] = calendar.timegm(t.timetuple()) + t.microsecond * 1e-6


    def process_IN_CLOSE_WRITE(self, event):
        try:
            filename = os.path.join(event.path, event.name)
            creation_time = self.__created_files.pop(filename)
            self._on_new_file(filename, creation_time)
        except KeyError:
            # file has only been edited, not newly created
            pass

except ImportError:
    pass


try:
    import win32file
    import winerror
    import win32con
    import pywintypes
    import ctypes

    class FSMonitorError(Exception):
        pass


    class FSMonitorOSError(OSError, FSMonitorError):
        pass


    class FSEvent(object):
        def __init__(self, watch, action, name=""):
            self.watch = watch
            self.name = name
            self.action = action

        @property
        def path(self):
            return self.watch.path

        @property
        def user(self):
            return self.watch.user

        Access = 0x01
        Modify = 0x02
        Attrib = 0x04
        Create = 0x08
        Delete = 0x10
        DeleteSelf = 0x20
        MoveFrom = 0x40
        MoveTo = 0x80
        All = 0xFF


    class FSMonitorWindowsError(FSMonitorError):
        pass


    class FSMonitorWatch(object):
        def __init__(self, path, flags, recursive):
            self.path = path
            self.enabled = True
            self._recursive = recursive
            self._win32_flags = flags
            self._key = None
            self._hDir = None

            self._hDir = win32file.CreateFile(
                path,
                0x0001,
                win32con.FILE_SHARE_READ | win32con.FILE_SHARE_WRITE | win32con.FILE_SHARE_DELETE,
                None,
                win32con.OPEN_EXISTING,
                win32con.FILE_FLAG_BACKUP_SEMANTICS | win32con.FILE_FLAG_OVERLAPPED,
                None)

            self._overlapped = pywintypes.OVERLAPPED()
            self._buf = ctypes.create_string_buffer(1024)
            self._removed = False

        def __del__(self):
            close_watch(self)

        def __repr__(self):
            return "<FSMonitorWatch %r>" % self.path


    def close_watch(watch):
        if watch._hDir is not None:
            win32file.CancelIo(watch._hDir)
            win32file.CloseHandle(watch._hDir)
            watch._hDir = None


    def read_changes(watch):
        win32file.ReadDirectoryChangesW(
            watch._hDir,
            watch._buf,
            True,
            win32con.FILE_NOTIFY_CHANGE_FILE_NAME |
            win32con.FILE_NOTIFY_CHANGE_LAST_WRITE,
            watch._overlapped,
            None
        )


    def process_events(watch, num):
        for action, name in win32file.FILE_NOTIFY_INFORMATION(watch._buf.raw, num):
            if action is not None and (
                    action & win32con.FILE_NOTIFY_CHANGE_FILE_NAME | win32con.FILE_NOTIFY_CHANGE_LAST_WRITE):
                yield FSEvent(watch, action, name)
        try:
            read_changes(watch)
        except pywintypes.error as e:
            if e.args[0] == 5:
                close_watch(watch)
                yield FSEvent(watch, FSEvent.DeleteSelf)
            else:
                raise FSMonitorWindowsError(*e.args)


    class FSMonitor(object):
        def __init__(self):
            self.__key_to_watch = {}
            self.__last_key = 0
            self.__lock = threading.Lock()
            self.__cphandle = win32file.CreateIoCompletionPort(-1, None, 0, 0)

        def __del__(self):
            self.close()

        def close(self):
            if self.__cphandle is not None:
                win32file.CloseHandle(self.__cphandle)
                self.__cphandle = None

        def add_dir_watch(self, path, flags, recursive=False):
            try:
                flags |= FSEvent.DeleteSelf
                watch = FSMonitorWatch(path, flags, recursive)
                with self.__lock:
                    key = self.__last_key
                    win32file.CreateIoCompletionPort(watch._hDir, self.__cphandle, key, 0)
                    self.__last_key += 1
                    read_changes(watch)
                    watch._key = key
                    self.__key_to_watch[key] = watch
                return watch
            except pywintypes.error as e:
                raise FSMonitorWindowsError(*e.args)

        def __remove_watch(self, watch):
            if not watch._removed:
                try:
                    watch._removed = True
                    close_watch(watch)
                    return True
                except pywintypes.error:
                    pass
            return False

        def remove_all_watches(self):
            with self.__lock:
                for watch in self.__key_to_watch.values():
                    self.__remove_watch(watch)

        def read_events(self):
            try:
                events = []
                rc, num, key, _ = win32file.GetQueuedCompletionStatus(self.__cphandle, 1000)
                if rc == 0:
                    with self.__lock:
                        watch = self.__key_to_watch.get(key)
                        if watch is not None and watch.enabled and not watch._removed:
                            for evt in process_events(watch, num):
                                events.append(evt)
                elif rc == 5:
                    with self.__lock:
                        watch = self.__key_to_watch.get(key)
                        if watch is not None and watch.enabled:
                            close_watch(watch)
                            del self.__key_to_watch[key]
                            events.append(FSEvent(watch, FSEvent.DeleteSelf))
                return events
            except pywintypes.error as e:
                raise FSMonitorWindowsError(*e.args)


    class WindowsDirectoryWatcher(_DirectoryWatcherBase):
        def __init__(self, dir_name, func, recursive, *args, **kwargs):
            _DirectoryWatcherBase.__init__(self, dir_name, func, recursive, *args, **kwargs)
            self.recursive = recursive
            self.worker_thread = None
            self.processing_thread = None
            self.stay_alive = True
            self.monitor = FSMonitor()
            self.__created_files = {}
            self.__new_files_q = queue.Queue()

        def start(self):
            self.stay_alive = True
            self.monitor.add_dir_watch(self.dir_to_watch,
                                       win32con.FILE_NOTIFY_CHANGE_FILE_NAME | win32con.FILE_NOTIFY_CHANGE_LAST_WRITE,
                                       recursive=self.recursive)
            self.worker_thread = threading.Thread(target=self.__do_watching)
            self.processing_thread = threading.Thread(target=self.__do_processing)

            self.worker_thread.start()
            self.processing_thread.start()

        def __do_watching(self):
            while self.stay_alive:
                # try:
                for event in self.monitor.read_events():

                    file_path = os.path.join(self.dir_to_watch, event.name)

                    if event.action == 1:  # file creation event
                        t = datetime.datetime.utcnow()
                        self.__created_files[file_path] = calendar.timegm(t.timetuple()) + t.microsecond * 1e-6
                        self.__new_files_q.put(file_path)
                    if event.action == 3:  # file update event
                        if file_path not in self.__created_files:
                            # file has just been modified - not newly created
                            continue

        def __do_processing(self):
            """
            Wait for the newly created file to be closed and then run the
            processing function on it (this is required since there is no such
            thing as a close_write event on Windows)
            """
            while self.stay_alive:
                path = self.__new_files_q.get()

                if not path:  # probably an exit request
                    continue

                if '.log' in path:
                    continue

                # Ignore lock files as otherwise this watcher recreates the file - not good
                if '.lock' in path:
                    continue

                # Ignore darkcorr images - we don't want to plot these
                if '_darkcorr.' in path:
                    continue

                file_is_closed = False
                while not file_is_closed and self.stay_alive:

                    # try to open the file for reading, specifying exclusive access
                    # this will fail if the file is already open in an another process

                    try:
                        handle = win32file.CreateFile(
                            path,
                            win32file.GENERIC_READ,
                            0,  # share mode - 0 == no sharing
                            None,
                            win32file.OPEN_ALWAYS,
                            win32file.FILE_ATTRIBUTE_NORMAL,
                            None)
                        handle.close()
                        file_is_closed = True
                    except pywintypes.error as e:
                        time.sleep(0.01)
                        # if e[0] == winerror.ERROR_SHARING_VIOLATION:   # This wasn't working so I have simplified
                        #     time.sleep(0.01)
                        # else:
                        #     raise

                if not self.stay_alive:
                    return

                self._on_new_file(path, self.__created_files[path])

        def stop(self):
            self.stay_alive = False
            self.monitor.remove_all_watches()
            if self.worker_thread is not None:
                self.worker_thread.join()

            if self.processing_thread is not None:
                self.__new_files_q.put(None)
                self.processing_thread.join()

            # empty the new_files queue
            try:
                while True:
                    self.__new_files_q.get_nowait()
            except queue.Empty:
                pass

            self.worker_thread = None
            self.processing_thread = None

except ImportError:
    pass
