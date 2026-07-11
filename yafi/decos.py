import functools

def tag(tag):
    """A decorator factory that attaches metadata tags to a function."""
    def decorator(func):
        # preserve original function identity (name, docstring)
        @functools.wraps(func) 
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)
        
        # Attach the tags directly to the wrapper function object
        wrapper.tag = tag
        return wrapper
    return decorator