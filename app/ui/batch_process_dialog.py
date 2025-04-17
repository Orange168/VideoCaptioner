from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, 
    QFileDialog, QListWidget, QListWidgetItem, QTabWidget, QWidget,
    QComboBox, QMenu
)
from PyQt5.QtCore import Qt, pyqtSignal
from app.core.entities import BatchTaskType, BatchTaskStatus

class BatchProcessDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("批量处理")
        self.setMinimumSize(800, 600)
        
        # 创建主布局
        main_layout = QVBoxLayout(self)
        
        # 创建标签页
        self.tab_widget = QTabWidget()
        self.batch_tab = QWidget()
        self.single_tab = QWidget()
        
        self.tab_widget.addTab(self.batch_tab, "批量处理")
        self.tab_widget.addTab(self.single_tab, "单个处理")
        
        # 设置默认显示批量处理标签页
        self.tab_widget.setCurrentIndex(1)
        
        main_layout.addWidget(self.tab_widget)
        
        # 初始化批量处理标签页
        self._init_batch_tab()
        
        # 初始化单个处理标签页
        self._init_single_tab() 

    def _init_batch_tab(self):
        layout = QVBoxLayout(self.batch_tab)
        
        # 添加文件按钮
        add_button = QPushButton("添加文件")
        add_button.clicked.connect(self._on_add_files)
        layout.addWidget(add_button)
        
        # 添加状态过滤下拉框
        filter_layout = QHBoxLayout()
        filter_label = QLabel("状态过滤:")
        self.status_filter = QComboBox()
        self.status_filter.addItem("全部", None)
        self.status_filter.addItem("等待中", BatchTaskStatus.WAITING)
        self.status_filter.addItem("处理中", BatchTaskStatus.RUNNING)
        self.status_filter.addItem("已完成", BatchTaskStatus.COMPLETED)
        self.status_filter.addItem("失败", BatchTaskStatus.FAILED)
        self.status_filter.currentIndexChanged.connect(self._on_filter_changed)
        
        filter_layout.addWidget(filter_label)
        filter_layout.addWidget(self.status_filter)
        filter_layout.addStretch()
        layout.addLayout(filter_layout)
        
        # 任务列表
        self.task_list = QListWidget()
        self.task_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.task_list.customContextMenuRequested.connect(self._show_context_menu)
        layout.addWidget(self.task_list)
        
        # 开始处理按钮
        self.start_button = QPushButton("开始处理")
        self.start_button.clicked.connect(self._on_start_process)
        layout.addWidget(self.start_button)
        
    def _show_context_menu(self, position):
        item = self.task_list.itemAt(position)
        if not item:
            return
            
        task = item.data(Qt.UserRole)
        if not task:
            return
            
        menu = QMenu()
        if task.status == BatchTaskStatus.FAILED:
            retry_action = menu.addAction("重新处理")
            retry_action.triggered.connect(lambda: self._on_retry_task(task))
            
        if menu.actions():
            menu.exec_(self.task_list.mapToGlobal(position))
            
    def _on_retry_task(self, task):
        # 重置任务状态
        task.status = BatchTaskStatus.WAITING
        task.error_message = ""
        task.progress = 0
        
        # 更新列表项显示
        self._update_task_item(task)
        
        # 如果批处理线程没有运行，启动它
        if not self.batch_thread.isRunning():
            self.batch_thread.start()
            
    def _on_filter_changed(self, index):
        status = self.status_filter.currentData()
        for i in range(self.task_list.count()):
            item = self.task_list.item(i)
            task = item.data(Qt.UserRole)
            if status is None or task.status == status:
                item.setHidden(False)
            else:
                item.setHidden(True)
                
    def _update_task_item(self, task):
        # 更新列表项显示
        for i in range(self.task_list.count()):
            item = self.task_list.item(i)
            if item.data(Qt.UserRole) == task:
                item.setText(f"{task.file_path} - {task.status.value} - {task.progress}%")
                if task.error_message:
                    item.setToolTip(f"错误: {task.error_message}")
                break 