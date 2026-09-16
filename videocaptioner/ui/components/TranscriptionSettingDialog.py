# -*- coding: utf-8 -*-
from qfluentwidgets import BodyLabel, ComboBoxSettingCard, MessageBoxBase
from qfluentwidgets import FluentIcon as FIF

from videocaptioner.core.entities import TranscribeOutputFormatEnum
from videocaptioner.ui.common.config import cfg
from videocaptioner.ui.components.SpinBoxSettingCard import SpinBoxSettingCard


class TranscriptionSettingDialog(MessageBoxBase):
    """Transcription output and mechanical caption limits."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.titleLabel = BodyLabel(self.tr("转录设置"), self)

        self.output_format_card = ComboBoxSettingCard(
            cfg.transcribe_output_format,
            FIF.SAVE,
            self.tr("输出格式"),
            self.tr("选择转录字幕的输出格式"),
            texts=[fmt.value for fmt in TranscribeOutputFormatEnum],
            parent=self,
        )
        self.word_count_cjk_card = SpinBoxSettingCard(
            cfg.mechanical_max_word_count_cjk,
            FIF.TILES,  # type: ignore
            self.tr("中文最大字数"),
            self.tr("开启机械断句时，单条字幕的最大字数"),
            minimum=8,
            maximum=50,
            parent=self,
        )
        self.word_count_english_card = SpinBoxSettingCard(
            cfg.mechanical_max_word_count_english,
            FIF.TILES,  # type: ignore
            self.tr("英文最大单词数"),
            self.tr("开启机械断句时，单条字幕的最大单词数"),
            minimum=8,
            maximum=50,
            parent=self,
        )

        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addWidget(self.output_format_card)
        self.viewLayout.addWidget(self.word_count_cjk_card)
        self.viewLayout.addWidget(self.word_count_english_card)
        self.viewLayout.setSpacing(10)

        self.setWindowTitle(self.tr("转录设置"))
        self.widget.setMinimumWidth(380)
        self.yesButton.hide()
        self.cancelButton.setText(self.tr("关闭"))
