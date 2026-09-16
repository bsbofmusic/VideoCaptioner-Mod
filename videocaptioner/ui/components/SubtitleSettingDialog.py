from qfluentwidgets import BodyLabel, MessageBoxBase
from qfluentwidgets import FluentIcon as FIF

from videocaptioner.ui.common.config import cfg
from videocaptioner.ui.components.SpinBoxSettingCard import SpinBoxSettingCard


class SubtitleSettingDialog(MessageBoxBase):
    """Subtitle display-length settings used by deterministic mechanical reflow."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.titleLabel = BodyLabel(self.tr("字幕设置"), self)

        self.word_count_cjk_card = SpinBoxSettingCard(
            cfg.mechanical_max_word_count_cjk,
            FIF.TILES,  # type: ignore
            self.tr("中文最大字数"),
            self.tr("机械断句单条字幕的最大字数（中日韩等字符）"),
            minimum=8,
            maximum=50,
            parent=self,
        )

        self.word_count_english_card = SpinBoxSettingCard(
            cfg.mechanical_max_word_count_english,
            FIF.TILES,  # type: ignore
            self.tr("英文最大单词数"),
            self.tr("机械断句单条字幕的最大单词数（英文等空格分词语言）"),
            minimum=8,
            maximum=50,
            parent=self,
        )

        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addWidget(self.word_count_cjk_card)
        self.viewLayout.addWidget(self.word_count_english_card)
        self.viewLayout.setSpacing(10)

        self.setWindowTitle(self.tr("字幕设置"))
        self.widget.setMinimumWidth(380)
        self.yesButton.hide()
        self.cancelButton.setText(self.tr("关闭"))
