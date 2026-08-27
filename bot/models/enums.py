from __future__ import annotations

import enum


class VoteStatus(str, enum.Enum):
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    OPEN = "open"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    ARCHIVED = "archived"


class VoteType(str, enum.Enum):
    STANDARD = "standard"
    NO_ABSTAIN = "no_abstain"
    SINGLE_CHOICE = "single_choice"
    MULTI_CHOICE = "multi_choice"
    RANKED = "ranked"
    WEIGHTED = "weighted"


class AnonymityLevel(str, enum.Enum):
    OPEN = "open"
    ANONYMOUS_MEMBERS = "anonymous_members"
    ANONYMOUS_ADMINS = "anonymous_admins"
    PARTIAL = "partial"
    FULL = "full"


class VoteChangeMode(str, enum.Enum):
    NONE = "none"
    CHANGE = "change"
    REVOKE = "revoke"
    ADMIN_ONLY = "admin_only"


class QuorumRule(str, enum.Enum):
    MIN_COUNT = "min_count"
    MIN_PERCENT = "min_percent"
    REQUIRED_ROLES = "required_roles"
    AUTO_REJECT = "auto_reject"
    AUTO_EXTEND = "auto_extend"
    ADMIN_DECISION = "admin_decision"


class MajorityRule(str, enum.Enum):
    SIMPLE = "simple"
    QUALIFIED = "qualified"
    ALL_PARTICIPANTS = "all_participants"
    VOTERS_ONLY = "voters_only"
    UNANIMOUS = "unanimous"
    MIN_AFFIRMATIVE = "min_affirmative"


class TieRule(str, enum.Enum):
    NOT_ACCEPTED = "not_accepted"
    EXTEND = "extend"
    RE_VOTE = "re_vote"
    CHAIR_VOTE = "chair_vote"
    MANUAL = "manual"


class AuditAction(str, enum.Enum):
    VOTE_CREATED = "vote_created"
    DRAFT_EDITED = "draft_edited"
    SENT_FOR_APPROVAL = "sent_for_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    RETURNED = "returned"
    PUBLISHED = "published"
    PARAMETERS_CHANGED = "parameters_changed"
    PARTICIPANT_ADDED = "participant_added"
    PARTICIPANT_REMOVED = "participant_removed"
    VOTE_CAST = "vote_cast"
    VOTE_CHANGED = "vote_changed"
    VOTE_REVOKED = "vote_revoked"
    REMINDER_SENT = "reminder_sent"
    PAUSED = "paused"
    RESUMED = "resumed"
    EXTENDED = "extended"
    EARLY_COMPLETION = "early_completion"
    AUTO_COMPLETED = "auto_completed"
    CANCELLED = "cancelled"
    EXPORTED = "exported"
    CONFIDENTIAL_VIEWED = "confidential_viewed"
    SETTINGS_CHANGED = "settings_changed"
    SYSTEM_ERROR = "system_error"


class ApprovalStatus(str, enum.Enum):
    NONE = "none"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    RETURNED = "returned"


class ExportFormat(str, enum.Enum):
    CSV = "csv"
    XLSX = "xlsx"
    PDF = "pdf"
    JSON = "json"


class NotificationType(str, enum.Enum):
    NEW_VOTE = "new_vote"
    REMINDER = "reminder"
    EARLY_END_WARNING = "early_end_warning"
    VOTE_COMPLETED = "vote_completed"
    QUORUM_NOT_REACHED = "quorum_not_reached"
    ADMIN_WARNING = "admin_warning"
