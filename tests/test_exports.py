import roadmaps
from roadmaps import (
    COMPLETED,
    DEFAULT_PRIORITY,
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
