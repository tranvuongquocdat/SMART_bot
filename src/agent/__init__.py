"""
Secretary Agent — multi-user routing, thinking UX, tool loop.
"""
import asyncio
import json
import logging
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from src import context, db, identity
from src.config import Settings
from src.context import ChatContext
from src.services import telegram
from src.infrastructure import qdrant_client as qdrant
from src.infrastructure import lark_client as lark
from src.agent.tool_definitions import TOOL_DEFINITIONS
from src.agent.tool_dispatcher import ToolDispatcher
from src.agent.handlers.web_search import WebSearchHandler
from src.agent.handlers.escalate import EscalateToAdvisorHandler
from src.agent.handlers.tasks import (
    CreateTaskHandler, ListTasksHandler, UpdateTaskHandler, DeleteTaskHandler,
    SearchTasksHandler, ApproveTaskChangeHandler, RejectTaskChangeHandler,
)
from src.agent.handlers.people import (
    AddPeopleHandler, GetPersonHandler, GetPeopleAliasHandler, ListPeopleHandler,
    UpdatePeopleHandler, DeletePeopleHandler,
    CheckEffortHandler, CheckTeamEngagementHandler,
)
from src.agent.handlers.projects import (
    CreateProjectHandler, GetProjectHandler, ListProjectsHandler,
    UpdateProjectHandler, DeleteProjectHandler,
)
from src.agent.handlers.notes import (
    GetNoteHandler, UpdateNoteHandler, AppendNoteHandler,
)
from src.agent.handlers.search import SearchHistoryHandler, SearchNotesHandler
from src.agent.handlers.summary import (
    GetSummaryHandler, GetWorkloadHandler, GetProjectReportHandler,
)
from src.agent.handlers.ideas import CreateIdeaHandler
from src.agent.handlers.reminders import (
    CreateReminderHandler, ListRemindersHandler,
    UpdateReminderHandler, DeleteReminderHandler,
)
from src.agent.handlers.review import (
    AddReviewScheduleHandler, ListReviewSchedulesHandler,
    ToggleReviewHandler, DeleteReviewScheduleHandler,
)
from src.agent.handlers.memory import ListPendingApprovalsHandler
from src.agent.handlers.join import (
    ListAvailableWorkspacesHandler, RequestJoinHandler,
    ApproveJoinHandler, RejectJoinHandler,
)
from src.agent.handlers.reset import (
    InitiateResetHandler, ConfirmResetStep1Handler, ExecuteResetHandler,
)
from src.agent.handlers.group import (
    ManageGroupHandler, SummarizeGroupConversationHandler,
    UpdateGroupNoteHandler, BroadcastToGroupHandler,
)
from src.agent.handlers.communication import (
    SendDmHandler, BroadcastHandler, GetCommunicationLogHandler,
    ResolvePersonHandler, LinkContactToPersonHandler,
    ListUnlinkedContactsHandler, GetGroupAdminsHandler,
)
from src.agent.handlers.workspace import SetLanguageHandler, SwitchWorkspaceHandler

# Phase 4b-2a: every LLM tool has a handler; the legacy fallback in the
# dispatcher only fires for genuinely unknown names. Phase 4b-2b moves
# logic from `src.tools.*` into `src.services.*` and the handlers
# constructor-inject those services.
_dispatcher = ToolDispatcher([
    # foundation (Phase 4b-1)
    WebSearchHandler(), EscalateToAdvisorHandler(),
    # tasks
    CreateTaskHandler(), ListTasksHandler(), UpdateTaskHandler(),
    DeleteTaskHandler(), SearchTasksHandler(),
    ApproveTaskChangeHandler(), RejectTaskChangeHandler(),
    # people
    AddPeopleHandler(), GetPersonHandler(), GetPeopleAliasHandler(),
    ListPeopleHandler(), UpdatePeopleHandler(), DeletePeopleHandler(),
    CheckEffortHandler(), CheckTeamEngagementHandler(),
    # projects
    CreateProjectHandler(), GetProjectHandler(), ListProjectsHandler(),
    UpdateProjectHandler(), DeleteProjectHandler(),
    # notes
    GetNoteHandler(), UpdateNoteHandler(), AppendNoteHandler(),
    # search
    SearchHistoryHandler(), SearchNotesHandler(),
    # summary
    GetSummaryHandler(), GetWorkloadHandler(), GetProjectReportHandler(),
    # ideas
    CreateIdeaHandler(),
    # reminders
    CreateReminderHandler(), ListRemindersHandler(),
    UpdateReminderHandler(), DeleteReminderHandler(),
    # review schedule
    AddReviewScheduleHandler(), ListReviewSchedulesHandler(),
    ToggleReviewHandler(), DeleteReviewScheduleHandler(),
    # memory / approvals
    ListPendingApprovalsHandler(),
    # join
    ListAvailableWorkspacesHandler(), RequestJoinHandler(),
    ApproveJoinHandler(), RejectJoinHandler(),
    # reset
    InitiateResetHandler(), ConfirmResetStep1Handler(), ExecuteResetHandler(),
    # group
    ManageGroupHandler(), SummarizeGroupConversationHandler(),
    UpdateGroupNoteHandler(), BroadcastToGroupHandler(),
    # communication
    SendDmHandler(), BroadcastHandler(), GetCommunicationLogHandler(),
    ResolvePersonHandler(), LinkContactToPersonHandler(),
    ListUnlinkedContactsHandler(), GetGroupAdminsHandler(),
    # workspace + language
    SetLanguageHandler(), SwitchWorkspaceHandler(),
])


import logging
from src.config import Settings

from src.agent.secretary_agent import (  # noqa: F401
    handle_message,
    SECRETARY_PROMPT,
    THINKING_MAP,
    MAX_TOOL_ROUNDS,
)
from src.agent.secretary_agent import init as _secretary_init
from src.agent.reminder_agent import send_reminder, REMINDER_PROMPT  # noqa: F401

logger = logging.getLogger("agent")

_settings: Settings | None = None


def init_agent(settings: Settings) -> None:
    """Wire Settings into agent + secretary agent. Called from main.py lifespan."""
    global _settings
    _settings = settings
    _secretary_init(settings)
