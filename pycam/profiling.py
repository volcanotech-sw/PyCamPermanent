import cProfile
import functools

def profile_method(output_file):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            profiler = cProfile.Profile()
            profiler.enable()

            result = func(*args, **kwargs)

            profiler.disable()
            profiler.dump_stats(output_file)

            return result

        return wrapper
    return decorator