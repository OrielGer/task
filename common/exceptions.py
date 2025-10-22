"""
Custom Exceptions Module
Defines C2-specific exceptions for better error handling
"""


class MessageTooLargeError(Exception):
    """Raised when message exceeds size limit"""
    pass
