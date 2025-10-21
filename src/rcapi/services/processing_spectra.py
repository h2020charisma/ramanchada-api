from rcapi.config.app_config import initialize_dirs
from rcapi.models.models import Task


config, UPLOAD_DIR, NEXUS_DIR, TEMPLATE_DIR = initialize_dirs()


class ProcessMock:
    def process(task: Task, nexus_dataset_url: str, base_url: str):
        pass


class ProcessCalibrate:
    def process(task: Task, nexus_dataset_url: str, base_url: str):
        pass


class ProcessFindPeak:
    def process(task: Task, nexus_dataset_url: str, base_url: str):
        pass
