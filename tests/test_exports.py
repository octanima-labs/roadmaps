import roadmaps
from roadmaps import (
    COMPLETED,
    DEFAULT_PRIORITY,
    DEFAULT_TASK_DESCRIPTION,
    DEFAULT_TASK_GROUP_DESCRIPTION,
    ENABLE_TUI_ORDER_BREADCRUMBS,
    ENABLE_TUI_ROMAN_MILESTONES,
    ENABLE_TUI_UNICODE_PROGRESS,
    MAX_PRIORITY,
    NO_MILESTONE,
    NOT_STARTED,
    ONGOING,
    OPTIONAL_TASK,
    TUI_PROGRESS_BAR_WIDTH,
    UNSORTED,
    JsonSerializer,
    JSONValidationError,
    MarkdownParser,
    MarkdownRenderer,
    Roadmap,
    Task,
    TaskGroup,
    TextParser,
    TextRenderer,
    YamlSerializer,
    YAMLValidationError,
)
from roadmaps.constants import COMPLETED as ConstantsCompleted
from roadmaps.constants import DEFAULT_PRIORITY as ConstantsDefaultPriority
from roadmaps.constants import (
    DEFAULT_TASK_DESCRIPTION as ConstantsDefaultTaskDescription,
)
from roadmaps.constants import (
    DEFAULT_TASK_GROUP_DESCRIPTION as ConstantsDefaultTaskGroupDescription,
)
from roadmaps.constants import (
    ENABLE_TUI_ORDER_BREADCRUMBS as ConstantsEnableTuiOrderBreadcrumbs,
)
from roadmaps.constants import (
    ENABLE_TUI_ROMAN_MILESTONES as ConstantsEnableTuiRomanMilestones,
)
from roadmaps.constants import (
    ENABLE_TUI_UNICODE_PROGRESS as ConstantsEnableTuiUnicodeProgress,
)
from roadmaps.constants import MAX_PRIORITY as ConstantsMaxPriority
from roadmaps.constants import NO_MILESTONE as ConstantsNoMilestone
from roadmaps.constants import NOT_STARTED as ConstantsNotStarted
from roadmaps.constants import ONGOING as ConstantsOngoing
from roadmaps.constants import OPTIONAL_TASK as ConstantsOptionalTask
from roadmaps.constants import TUI_PROGRESS_BAR_WIDTH as ConstantsTuiProgressBarWidth
from roadmaps.constants import UNSORTED as ConstantsUnsorted
from roadmaps.model import Roadmap as ModelRoadmap
from roadmaps.model import Task as ModelTask
from roadmaps.model import TaskGroup as ModelTaskGroup
from roadmaps.parsers import MarkdownParser as ModuleMarkdownParser
from roadmaps.parsers import TextParser as ModuleTextParser
from roadmaps.renderers import MarkdownRenderer as ModuleMarkdownRenderer
from roadmaps.renderers import TextRenderer as ModuleTextRenderer
from roadmaps.serializers import JsonSerializer as ModuleJsonSerializer
from roadmaps.serializers import JSONValidationError as ModuleJSONValidationError
from roadmaps.serializers import YamlSerializer as ModuleYamlSerializer
from roadmaps.serializers import YAMLValidationError as ModuleYAMLValidationError


def test_format_classes_are_public_exports() -> None:
    assert JsonSerializer is ModuleJsonSerializer
    assert JSONValidationError is ModuleJSONValidationError
    assert YamlSerializer is ModuleYamlSerializer
    assert YAMLValidationError is ModuleYAMLValidationError
    assert TextParser is ModuleTextParser
    assert MarkdownParser is ModuleMarkdownParser
    assert TextRenderer is ModuleTextRenderer
    assert MarkdownRenderer is ModuleMarkdownRenderer


def test_model_classes_are_shared_across_import_surfaces() -> None:
    assert roadmaps.Task is Task is ModelTask
    assert roadmaps.TaskGroup is TaskGroup is ModelTaskGroup
    assert roadmaps.Roadmap is Roadmap is ModelRoadmap


def test_constants_are_shared_across_import_surfaces() -> None:
    assert COMPLETED is ConstantsCompleted
    assert DEFAULT_PRIORITY is ConstantsDefaultPriority
    assert DEFAULT_TASK_DESCRIPTION is ConstantsDefaultTaskDescription
    assert DEFAULT_TASK_GROUP_DESCRIPTION is ConstantsDefaultTaskGroupDescription
    assert ENABLE_TUI_ORDER_BREADCRUMBS is ConstantsEnableTuiOrderBreadcrumbs
    assert ENABLE_TUI_ROMAN_MILESTONES is ConstantsEnableTuiRomanMilestones
    assert ENABLE_TUI_UNICODE_PROGRESS is ConstantsEnableTuiUnicodeProgress
    assert MAX_PRIORITY is ConstantsMaxPriority
    assert NO_MILESTONE is ConstantsNoMilestone
    assert NOT_STARTED is ConstantsNotStarted
    assert ONGOING is ConstantsOngoing
    assert OPTIONAL_TASK is ConstantsOptionalTask
    assert TUI_PROGRESS_BAR_WIDTH is ConstantsTuiProgressBarWidth
    assert UNSORTED is ConstantsUnsorted
