from typing import Optional

from PyQt5.QtWidgets import QStackedWidget, QVBoxLayout, QWidget
from qfluentwidgets import FluentIcon as FIF
from qfluentwidgets import SettingCardGroup, SwitchSettingCard

from videocaptioner.core.entities import TranscribeModelEnum
from videocaptioner.core.utils.platform_utils import is_macos
from videocaptioner.ui.common.config import cfg

from .FasterWhisperSettingWidget import FasterWhisperSettingWidget
from .MiniMaxAPISettingWidget import MiniMaxAPISettingWidget
from .WhisperAPISettingWidget import WhisperAPISettingWidget
from .WhisperCppSettingWidget import WhisperCppSettingWidget


class PublicASRSettingWidget(QWidget):
    """Small opt-in surface for Bcut/JianYing deterministic reflow."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.group = SettingCardGroup(self.tr("字幕整理"), self)
        self.mechanical_split_card = SwitchSettingCard(
            FIF.ALIGNMENT,
            self.tr("机械断句"),
            self.tr("仅在原始字幕断句不好时开启；按真实字词时间戳整理，不调用大模型"),
            cfg.public_asr_mechanical_split,
            self.group,
        )
        self.group.addSettingCard(self.mechanical_split_card)
        layout.addWidget(self.group)
        layout.addStretch(1)


class TranscriptionSettingCard(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()

    def setup_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)

        self.stacked_widget = QStackedWidget(self)

        self.empty_widget = QWidget(self)
        self.public_asr_widget = PublicASRSettingWidget(self)
        self.whisper_cpp_widget = WhisperCppSettingWidget(self)
        self.whisper_api_widget = WhisperAPISettingWidget(self)
        self.minimax_api_widget = MiniMaxAPISettingWidget(self)

        self.faster_whisper_widget: Optional[FasterWhisperSettingWidget] = None
        if not is_macos():
            self.faster_whisper_widget = FasterWhisperSettingWidget(self)

        self.stacked_widget.addWidget(self.empty_widget)
        self.stacked_widget.addWidget(self.public_asr_widget)
        self.stacked_widget.addWidget(self.whisper_cpp_widget)
        self.stacked_widget.addWidget(self.whisper_api_widget)
        self.stacked_widget.addWidget(self.minimax_api_widget)
        if self.faster_whisper_widget is not None:
            self.stacked_widget.addWidget(self.faster_whisper_widget)

        self.main_layout.addWidget(self.stacked_widget)

    def on_model_changed(self, value):
        if value in (TranscribeModelEnum.BIJIAN.value, TranscribeModelEnum.JIANYING.value):
            self.stacked_widget.setCurrentWidget(self.public_asr_widget)
        elif value == TranscribeModelEnum.WHISPER_CPP.value:
            self.stacked_widget.setCurrentWidget(self.whisper_cpp_widget)
        elif value == TranscribeModelEnum.WHISPER_API.value:
            self.stacked_widget.setCurrentWidget(self.whisper_api_widget)
        elif value == TranscribeModelEnum.MINIMAX_API.value:
            self.stacked_widget.setCurrentWidget(self.minimax_api_widget)
        elif value == TranscribeModelEnum.FASTER_WHISPER.value and self.faster_whisper_widget is not None:
            self.stacked_widget.setCurrentWidget(self.faster_whisper_widget)
        else:
            self.stacked_widget.setCurrentWidget(self.empty_widget)
