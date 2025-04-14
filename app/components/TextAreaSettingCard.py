from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QPlainTextEdit
from qfluentwidgets import SettingCard
from qfluentwidgets.common.config import ConfigItem, qconfig


class TextAreaSettingCard(SettingCard):
    """多行文本输入卡片"""

    textChanged = pyqtSignal(str)

    def __init__(
        self,
        configItem: ConfigItem,
        icon,
        title: str,
        content: str = None,
        placeholder: str = "",
        parent=None,
    ):
        super().__init__(icon, title, content, parent)

        self.configItem = configItem

        self.textEdit = QPlainTextEdit(self)
        self.textEdit.setPlaceholderText(placeholder)
        self.textEdit.setMinimumWidth(500)
        self.textEdit.setMinimumHeight(200)
        
        # 设置垂直布局
        self.vBoxLayout.addWidget(self.textEdit)
        
        # 初始化值
        self.setValue(qconfig.get(configItem))

        self.textEdit.textChanged.connect(self.__onTextChanged)
        configItem.valueChanged.connect(self.setValue)

    def __onTextChanged(self):
        text = self.textEdit.toPlainText()
        self.setValue(text)
        self.textChanged.emit(text)

    def setValue(self, value: str):
        qconfig.set(self.configItem, value)
        self.textEdit.setPlainText(value) 