from enum import Enum, auto
from pony.orm.dbapiprovider import StrConverter


class GcodeStates(Enum):
    VALID = 1
    INVALID = 2
    NO_PRINTER_MODEL = 3


class PermissionCodeStates(Enum):
    VALID = 1
    """Active code"""
    INVALID = 2
    """Code does not exist"""
    EXPIRED = 3
    """Code exists, but has expired"""
    NOT_YET_ACTIVE = 4
    """Code exists, but not yet active"""
    OVER_BUDGET = 5
    """Not yet implemented"""
    VALIDATOR_FAIL = 6
    """System specific failure"""


class JiraTransitionCodes(Enum):
    START_PROGRESS = 11
    """Start Progress: 11 (From Open to In Progress)"""
    READY_FOR_REVIEW = 21
    """Ready for review: 21 (From In Progress to UNDER REVIEW)"""
    STOP_PROGRESS = 111
    """Stop Progress: 111 (From In Progress to CANCELLED)"""
    APPROVE = 31
    """Approve : 31 (From Under Review to APPROVED)"""
    REJECT = 131
    """Reject: 131 (From Under Review to REJECTED)"""
    DONE = 41
    """Done: 41  (From APPROVED to DONE)"""
    REOPEN = 121
    """Reopen: 121  (From Cancelled to OPEN)"""
    RESTART_PROGRESS = 141
    """Restart progress : 141  (From REJECTED to IN PROGRESS) # Renamed from "Start progress" to "Restart progress" when changing these to enums"""


class GcodeCheckActions(Enum):
    ADD_COMMAND_AT_END = auto()
    """Add this command at the end of the file if it is not already the last command."""
    REMOVE_COMMAND_ALL = auto()
    """Remove all instances of this command. Will occur BEFORE ADD_COMMAND_AT_END"""
    COMMAND_MUST_EXIST = auto()
    """Ensure the command is present. For comments, a specific string such as 'nozzle diameter = 0.4' must be present in the comment. 
    For other commands, the only thing checked is the command itself."""
    COMMAND_PARAM_MAX = auto()
    """First parameter of command must be UNDER this value.
    Only sees digits. For example, M104 S205 is set nozzle temp. The S will be ignored and only the 205 checked."""
    COMMAND_PARAM_MIN = auto()
    """First parameter of command must be OVER this value."""
    KEYWORD_CHECK = auto()
    """Check if the associated keyword exists in the gcode. action_value of the gcode check item should be the id of the keyword you want to check for."""


class PrintStatus(Enum):
    NEW = auto()
    """Job has not been validated."""
    IN_QUEUE = auto()
    """Job is waiting for printer."""
    PRINTING = auto()
    """Currently Printing or waiting to be cleared."""
    FINISHED = auto()
    """Print has been completed and patron notified."""
    CANCELLED = auto()
    """Job cancelled for some reason."""
    FAILED = auto()
    """Print failed and was not completed."""


class PaymentStatus(Enum):
    NEEDS_PAYMENT_LINK = auto()
    """Job has been finished but payment link has not been generated."""
    WAITING_FOR_PAYMENT = auto()
    """Payment link has been generated but not paid."""
    PAID = auto()
    """Invoice has been generated for this tax exempt job"""
    INVOICED = auto()


class UrlTypes(Enum):
    UNKNOWN = auto()
    JIRA_ATTACHMENT = auto()
    GOOGLE_DRIVE = auto()


class MessageNames(Enum):
    WHITE_LIST_FAIL = auto()
    BLACK_LIST_FAIL = auto()
    PERMISSION_CODE_INVALID = auto()
    PERMISSION_CODE_EXPIRED = auto()
    PERMISSION_VALIDATOR_FAIL = auto()
    PERMISSION_CODE_NOT_YET_ACTIVE = auto()
    NO_FILE_ATTACHED = auto()
    UNKNOWN_DOWNLOAD_ERROR = auto()
    GOOGLE_DRIVE_403_ERROR = auto()
    GCODE_CHECK_FAIL = auto()
    FINISH_TEXT_TAX_EXEMPT = auto()
    FINISH_TEXT_WITH_TAX = auto()
    NO_PRINTER_MODEL = auto()
    PRINT_CANCELLED = auto()
    PRINT_QUEUED = auto()


def get_dict(enum_type):
    result = {}
    for x in enum_type:
        result[x.name] = x.value
    return result
