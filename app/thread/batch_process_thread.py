from re import S
from typing import List, Dict, Optional
from PyQt5.QtCore import QThread, pyqtSignal, Qt
from pathlib import Path
import queue
import time
from functools import partial
from string import Template
from PyQt5.QtCore import QThread, pyqtSignal, Qt, QTime



from app.core.task_factory import TaskFactory
from app.core.entities import (
    TranscribeTask,
    SubtitleTask,
    TranscriptAndSubtitleTask,
    FullProcessTask,
)
from app.thread.transcript_thread import TranscriptThread
from app.thread.subtitle_thread import SubtitleThread
from app.thread.video_synthesis_thread import VideoSynthesisThread
from app.core.utils.logger import setup_logger
from app.core.entities import BatchTaskType, BatchTaskStatus

logger = setup_logger("batch_process_thread")


class BatchTask:
    def __init__(self, file_path: str, task_type: BatchTaskType):
        self.file_path = file_path
        self.task_type = task_type
        self.status = BatchTaskStatus.WAITING
        self.progress = 0
        self.error_message = ""
        self.current_thread: Optional[QThread] = None


class BatchProcessThread(QThread):
    # 信号定义
    task_progress = pyqtSignal(str, int, str)  # file_path, progress, status
    task_error = pyqtSignal(str, str)  # file_path, error_message
    task_completed = pyqtSignal(str)  # file_path

    def __init__(self):
        super().__init__()
        self.task_queue = queue.Queue()
        self.current_tasks: Dict[str, BatchTask] = {}
        self.max_concurrent_tasks = 1
        self.is_running = False
        self.factory = TaskFactory()
        self.threads = []  # 保存所有创建的线程

    def add_task(self, task: BatchTask):
        self.task_queue.put(task)
        self.current_tasks[task.file_path] = task
        if not self.isRunning():
            self.is_running = True
            self.start()

    def run(self):
        while self.is_running:
            # 检查是否有正在运行的任务数量是否达到上限
            running_tasks = sum(
                1
                for task in self.current_tasks.values()
                if task.status == BatchTaskStatus.RUNNING
            )

            if running_tasks < self.max_concurrent_tasks:
                try:
                    # 非阻塞方式获取任务
                    task = self.task_queue.get_nowait()
                    self._process_task(task)
                except queue.Empty:
                    time.sleep(0.1)  # 避免CPU过度使用
            else:
                time.sleep(0.1)

    def _process_task(self, batch_task: BatchTask):
        try:
            batch_task.status = BatchTaskStatus.RUNNING
            self.task_progress.emit(
                batch_task.file_path, 0, str(BatchTaskStatus.RUNNING)
            )

            if batch_task.task_type == BatchTaskType.TRANSCRIBE:
                self._handle_transcribe_task(batch_task)
            elif batch_task.task_type == BatchTaskType.SUBTITLE:
                self._handle_subtitle_task(batch_task)
            elif batch_task.task_type == BatchTaskType.TRANS_SUB:
                self._handle_trans_sub_task(batch_task)
            elif batch_task.task_type == BatchTaskType.SUB_NOTE:
                self._handle_sub_note_task(batch_task)
            elif batch_task.task_type == BatchTaskType.FULL_PROCESS:
                self._handle_full_process_task(batch_task)

        except Exception as e:
            logger.exception(f"处理任务失败: {str(e)}")
            batch_task.status = BatchTaskStatus.FAILED
            batch_task.error_message = str(e)
            self.task_error.emit(batch_task.file_path, str(e))

    def _on_progress_wrapper(self, batch_task: BatchTask, progress: int, message: str):
        """进度信号包装器"""
        self.task_progress.emit(batch_task.file_path, progress, message)

    def _on_error_wrapper(self, batch_task: BatchTask, error: str):
        """错误信号包装器"""
        batch_task.status = BatchTaskStatus.FAILED
        batch_task.error_message = error
        self.task_error.emit(batch_task.file_path, error)

    def _on_finished_wrapper(self, batch_task: BatchTask, task=None):
        """完成信号包装器"""
        batch_task.status = BatchTaskStatus.COMPLETED
        batch_task.progress = 100
        self.task_completed.emit(batch_task.file_path)
        if batch_task.current_thread in self.threads:
            self.threads.remove(batch_task.current_thread)

    def _handle_transcribe_task(self, batch_task: BatchTask):
        # self.max_concurrent_tasks = 3
        task = self.factory.create_transcribe_task(batch_task.file_path)
        thread = TranscriptThread(task)
        batch_task.current_thread = thread

        # 保存线程引用
        self.threads.append(thread)

        thread.progress.connect(
            partial(self._on_progress_wrapper, batch_task), Qt.QueuedConnection
        )
        thread.error.connect(
            partial(self._on_error_wrapper, batch_task), Qt.QueuedConnection
        )
        thread.finished.connect(
            partial(self._on_finished_wrapper, batch_task), Qt.QueuedConnection
        )

        thread.start()

    def _handle_subtitle_task(self, batch_task: BatchTask):
        logger.info(f"开始处理字幕任务: {batch_task.file_path}")

        task = self.factory.create_subtitle_task(batch_task.file_path)
        thread = SubtitleThread(task)
        batch_task.current_thread = thread

        # 保存线程引用
        self.threads.append(thread)

        thread.progress.connect(
            partial(self._on_progress_wrapper, batch_task), Qt.QueuedConnection
        )
        thread.error.connect(
            partial(self._on_error_wrapper, batch_task), Qt.QueuedConnection
        )
        thread.finished.connect(
            partial(self._on_finished_wrapper, batch_task), Qt.QueuedConnection
        )

        thread.start()

    def _handle_trans_sub_task(self, batch_task: BatchTask):
        task = self.factory.create_transcript_and_subtitle_task(batch_task.file_path)
        trans_task = self.factory.create_transcribe_task(
            batch_task.file_path, need_next_task=True
        )
        thread = TranscriptThread(trans_task)
        batch_task.current_thread = thread
        self.current_tasks[batch_task.file_path] = batch_task

        # 保存线程引用
        self.threads.append(thread)

        thread.progress.connect(
            partial(self._on_trans_sub_progress_wrapper, batch_task),
            Qt.QueuedConnection,
        )
        thread.error.connect(
            partial(self._on_error_wrapper, batch_task), Qt.QueuedConnection
        )
        thread.finished.connect(
            partial(self._on_trans_sub_finished_wrapper, batch_task),
            Qt.QueuedConnection,
        )

        thread.start()

    def _on_trans_sub_progress_wrapper(
        self, batch_task: BatchTask, progress: int, message: str
    ):
        """转录+字幕任务进度包装器"""
        progress = progress // 2  # 转录占50%进度
        self.task_progress.emit(batch_task.file_path, progress, message)

    def _on_trans_sub_finished_wrapper(
        self, batch_task: BatchTask, task: TranscribeTask
    ):
        """转录+字幕任务转录完成包装器"""
        if batch_task.current_thread in self.threads:
            self.threads.remove(batch_task.current_thread)

        # 创建字幕任务
        subtitle_task = self.factory.create_subtitle_task(
            task.output_path, batch_task.file_path, need_next_task=True
        )
        thread = SubtitleThread(subtitle_task)
        batch_task.current_thread = thread
        self.current_tasks[batch_task.file_path] = batch_task

        # 保存线程引用
        self.threads.append(thread)

        from functools import partial

        thread.progress.connect(
            partial(self._on_trans_sub_subtitle_progress_wrapper, batch_task),
            Qt.QueuedConnection,
        )
        thread.error.connect(
            partial(self._on_error_wrapper, batch_task), Qt.QueuedConnection
        )
        thread.finished.connect(
            partial(self._on_finished_wrapper, batch_task), Qt.QueuedConnection
        )

        thread.start()

    def _on_trans_sub_subtitle_progress_wrapper(
        self, batch_task: BatchTask, progress: int, message: str
    ):
        """转录+字幕任务字幕进度包装器"""
        progress = 50 + progress // 2  # 字幕处理占后50%进度
        self.task_progress.emit(batch_task.file_path, progress, message)

    def _handle_full_process_task(self, batch_task: BatchTask):
        task = self.factory.create_full_process_task(batch_task.file_path)
        # 首先创建转录任务
        trans_task = self.factory.create_transcribe_task(
            batch_task.file_path, need_next_task=True
        )
        thread = TranscriptThread(trans_task)
        batch_task.current_thread = thread

        # 保存线程引用
        self.threads.append(thread)

        thread.progress.connect(
            partial(self.on_full_process_progress, batch_task), Qt.QueuedConnection
        )
        thread.error.connect(
            partial(self._on_error_wrapper, batch_task), Qt.QueuedConnection
        )
        thread.finished.connect(
            partial(self.on_full_process_finished, batch_task), Qt.QueuedConnection
        )

        thread.start()

    def on_full_process_progress(
        self, batch_task: BatchTask, progress: int, message: str
    ):
        """处理全流程任务的转录进度"""
        if batch_task.status == BatchTaskStatus.RUNNING:
            progress_value = progress // 3  # 转录占33%进度
            self.task_progress.emit(batch_task.file_path, progress_value, message)

    def on_full_process_finished(self, batch_task: BatchTask, task: TranscribeTask):
        """处理转录完成后开始字幕任务"""
        if batch_task.current_thread in self.threads:
            self.threads.remove(batch_task.current_thread)

        # 转录完成后创建字幕任务
        subtitle_task = self.factory.create_subtitle_task(
            task.output_path,
            batch_task.file_path,
            need_next_task=True,
        )
        thread = SubtitleThread(subtitle_task)
        batch_task.current_thread = thread

        # 保存线程引用
        self.threads.append(thread)

        thread.progress.connect(
            partial(self.on_full_process_subtitle_progress, batch_task),
            Qt.QueuedConnection,
        )
        thread.error.connect(
            partial(self._on_error_wrapper, batch_task), Qt.QueuedConnection
        )
        thread.finished.connect(
            partial(self.on_full_process_subtitle_finished, batch_task),
            Qt.QueuedConnection,
        )

        thread.start()

    def on_full_process_subtitle_progress(
        self, batch_task: BatchTask, progress: int, message: str
    ):
        """处理全流程任务中字幕部分的进度"""
        if batch_task.status == BatchTaskStatus.RUNNING:
            progress_value = 33 + progress // 3  # 字幕处理占中间33%进度
            self.task_progress.emit(batch_task.file_path, progress_value, message)

    def on_full_process_subtitle_finished(
        self, batch_task: BatchTask, video_path: str, subtitle_path: str
    ):
        """处理字幕完成后开始视频合成任务"""
        if batch_task.current_thread in self.threads:
            self.threads.remove(batch_task.current_thread)

        # 字幕完成后创建视频合成任务
        synthesis_task = self.factory.create_synthesis_task(video_path, subtitle_path)
        thread = VideoSynthesisThread(synthesis_task)
        batch_task.current_thread = thread

        # 保存线程引用
        self.threads.append(thread)

        thread.progress.connect(
            partial(self.on_full_process_synthesis_progress, batch_task),
            Qt.QueuedConnection,
        )
        thread.error.connect(
            partial(self._on_error_wrapper, batch_task), Qt.QueuedConnection
        )
        thread.finished.connect(
            partial(self._on_finished_wrapper, batch_task), Qt.QueuedConnection
        )

        thread.start()

    def on_full_process_synthesis_progress(
        self, batch_task: BatchTask, progress: int, message: str
    ):
        """处理全流程任务中视频合成部分的进度"""
        if batch_task.status == BatchTaskStatus.RUNNING:
            progress_value = 66 + progress // 3  # 视频合成占最后34%进度
            self.task_progress.emit(batch_task.file_path, progress_value, message)

    def stop_task(self, file_path: str):
        if file_path in self.current_tasks:
            task = self.current_tasks[file_path]
            if task.current_thread:
                if hasattr(task.current_thread, "stop"):
                    task.current_thread.stop()
            del self.current_tasks[file_path]
            # 从队列中移除任务
            with self.task_queue.mutex:
                self.task_queue.queue.clear()

    def stop_all(self):
        self.is_running = False
        # 停止所有线程
        for thread in self.threads:
            if hasattr(thread, "stop"):
                thread.stop()
            thread.wait()  # 等待线程结束
        self.threads.clear()
        self.current_tasks.clear()
        # 清空任务队列
        with self.task_queue.mutex:
            self.task_queue.queue.clear()

    def _handle_sub_note_task(self, batch_task: BatchTask):
        """处理字幕+笔记任务：基于转录的代码逻辑，添加生成笔记的功能"""
        logger.info(f"开始处理字幕+笔记任务: {batch_task.file_path}")
        
        # 检查提示词文件是否存在
        from pathlib import Path
        import os
        prompt_file = Path(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))) / "promt_notes.md"
        if not prompt_file.exists():
            logger.info(f"未找到提示词文件，将自动创建默认提示词文件: {prompt_file}")
        else:
            logger.info(f"找到提示词文件: {prompt_file}")
            
        # 类似于转录任务，先执行转录
        task = self.factory.create_transcribe_task(batch_task.file_path)
        thread = TranscriptThread(task)
        batch_task.current_thread = thread

        # 保存线程引用
        self.threads.append(thread)

        thread.progress.connect(
            partial(self._on_sub_note_progress_wrapper, batch_task), Qt.QueuedConnection
        )
        thread.error.connect(
            partial(self._on_error_wrapper, batch_task), Qt.QueuedConnection
        )
        thread.finished.connect(
            partial(self._on_sub_note_finished_wrapper, batch_task),
            Qt.QueuedConnection,
        )

        thread.start()

    def _on_sub_note_progress_wrapper(
        self, batch_task: BatchTask, progress: int, message: str
    ):
        """字幕+笔记任务进度包装器"""
        
        try:
            # 获取字幕内容
            from app.core.bk_asr.asr_data import ASRData
            output_path = task.output_path
            asr_data = ASRData.from_subtitle_file(output_path)
            
            # 获取LLM服务配置
            from app.common.config import cfg
            from app.core.entities import LLMServiceEnum
            
            # 优先使用笔记处理的LLM配置
            current_service = cfg.note_llm_service.value
            
            # 如果笔记处理的LLM配置为空，则使用默认的LLM配置
            if not current_service:
                current_service = cfg.llm_service.value
            
            if current_service == LLMServiceEnum.OPENAI:
                base_url = cfg.note_openai_api_base.value or cfg.openai_api_base.value
                api_key = cfg.note_openai_api_key.value or cfg.openai_api_key.value
                llm_model = cfg.note_openai_model.value or cfg.openai_model.value
            elif current_service == LLMServiceEnum.SILICON_CLOUD:
                base_url = cfg.note_silicon_cloud_api_base.value or cfg.silicon_cloud_api_base.value
                api_key = cfg.note_silicon_cloud_api_key.value or cfg.silicon_cloud_api_key.value
                llm_model = cfg.note_silicon_cloud_model.value or cfg.silicon_cloud_model.value
            elif current_service == LLMServiceEnum.DEEPSEEK:
                base_url = cfg.note_deepseek_api_base.value or cfg.deepseek_api_base.value
                api_key = cfg.note_deepseek_api_key.value or cfg.deepseek_api_key.value
                llm_model = cfg.note_deepseek_model.value or cfg.deepseek_model.value
            elif current_service == LLMServiceEnum.OLLAMA:
                base_url = cfg.note_ollama_api_base.value or cfg.ollama_api_base.value
                api_key = cfg.note_ollama_api_key.value or cfg.ollama_api_key.value
                llm_model = cfg.note_ollama_model.value or cfg.ollama_model.value
            elif current_service == LLMServiceEnum.LM_STUDIO:
                base_url = cfg.note_lm_studio_api_base.value or cfg.lm_studio_api_base.value
                api_key = cfg.note_lm_studio_api_key.value or cfg.lm_studio_api_key.value
                llm_model = cfg.note_lm_studio_model.value or cfg.lm_studio_model.value
            elif current_service == LLMServiceEnum.GEMINI:
                base_url = cfg.note_gemini_api_base.value or cfg.gemini_api_base.value
                api_key = cfg.note_gemini_api_key.value or cfg.gemini_api_key.value
                llm_model = cfg.note_gemini_model.value or cfg.gemini_model.value
            elif current_service == LLMServiceEnum.CHATGLM:
                base_url = cfg.note_chatglm_api_base.value or cfg.chatglm_api_base.value
                api_key = cfg.note_chatglm_api_key.value or cfg.chatglm_api_key.value
                llm_model = cfg.note_chatglm_model.value or cfg.chatglm_model.value
            elif current_service == LLMServiceEnum.PUBLIC:
                base_url = cfg.note_public_api_base.value or cfg.public_api_base.value
                api_key = cfg.note_public_api_key.value or cfg.public_api_key.value
                llm_model = cfg.note_public_model.value or cfg.public_model.value
            else:
                base_url = ""
                api_key = ""
                llm_model = ""
                
            # 设置OpenAI环境变量
            import os
            os.environ["OPENAI_BASE_URL"] = base_url
            os.environ["OPENAI_API_KEY"] = api_key
            
            # 提取字幕文本
            subtitle_text = ""
            for seg in asr_data.segments:
                start_time = QTime(0, 0).addMSecs(seg.start_time).toString("hh:mm:ss.zzz")[:-2]
                subtitle_text += f"[{start_time}] {seg.text}\n"
            
            # 生成笔记
            from pathlib import Path
            import openai
            
            # 创建笔记输出路径
            notes_path = self.factory.get_notes_path(output_path)
            
            # 读取提示词文件内容
            if prompt_file.exists():
                prompt = prompt_file.read_text(encoding="utf-8")
                logger.info("成功读取提示词文件内容")
            else:
                logger.exception(f"生成笔记失败: {str(e)}")
                return
                # 创建默认提示词文件
        
            usr_prompt = """字幕内容如下:${subtitle_text}。
要求：
1. 直接生成markdown内容，不用代码块包裹
2. 不用生多余内容
3. 保持内容的连贯性和逻辑结构


请直接返回Markdown格式的笔记内容（不用代码块），无需包含其他解释。"""

            # 使用Template替换变量
            usr_prompt = Template(usr_prompt).safe_substitute(subtitle_text=subtitle_text)
            
            self.task_progress.emit(batch_task.file_path, 60, "正在使用大语言模型生成笔记...")
            
            client = openai.OpenAI(
                base_url=base_url,
                api_key=api_key
            )

            # logger.info(f"创建了默认提示词文件: {prompt}")
            logger.info(f"创建了默认提示词文件: {usr_prompt}")
            response = client.chat.completions.create(
                model=llm_model,
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": usr_prompt}
                ],
                temperature=0.3
            )
            
            markdown_notes = response.choices[0].message.content
            
            # 写入笔记文件
            with open(notes_path, "w", encoding="utf-8") as f:
                f.write(markdown_notes)
                
            self.task_progress.emit(batch_task.file_path, 100, "笔记生成完成")
            batch_task.status = BatchTaskStatus.COMPLETED
            self.task_completed.emit(batch_task.file_path)
            
        except Exception as e:
            logger.exception(f"生成笔记失败: {str(e)}")
            batch_task.status = BatchTaskStatus.FAILED
            batch_task.error_message = str(e)
            self.task_error.emit(batch_task.file_path, str(e))

    def _on_sub_note_finished_wrapper(
        self, batch_task: BatchTask, task: TranscribeTask
    ):
        """字幕转录完成后生成笔记"""
        if batch_task.current_thread in self.threads:
            self.threads.remove(batch_task.current_thread)

        # 开始笔记生成过程
        import os
        from pathlib import Path
        prompt_file = Path(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))) / "promt_notes.md"
        logger.info(f"提示词文件位置: {prompt_file}")
        logger.info(f"可通过编辑该文件自定义笔记生成效果，文件中使用{{subtitle_text}}作为字幕内容占位符")
        
        self.task_progress.emit(batch_task.file_path, 50, "正在生成笔记...")
        
        try:
            # 获取字幕内容
            from app.core.bk_asr.asr_data import ASRData
            output_path = task.output_path
            asr_data = ASRData.from_subtitle_file(output_path)
            
            # 获取LLM服务配置
            from app.common.config import cfg
            from app.core.entities import LLMServiceEnum
            current_service = cfg.llm_service.value
            
            if current_service == LLMServiceEnum.OPENAI:
                base_url = cfg.openai_api_base.value
                api_key = cfg.openai_api_key.value
                llm_model = cfg.openai_model.value
            elif current_service == LLMServiceEnum.SILICON_CLOUD:
                base_url = cfg.silicon_cloud_api_base.value
                api_key = cfg.silicon_cloud_api_key.value
                llm_model = cfg.silicon_cloud_model.value
            elif current_service == LLMServiceEnum.DEEPSEEK:
                base_url = cfg.deepseek_api_base.value
                api_key = cfg.deepseek_api_key.value
                llm_model = cfg.deepseek_model.value
            elif current_service == LLMServiceEnum.OLLAMA:
                base_url = cfg.ollama_api_base.value
                api_key = cfg.ollama_api_key.value
                llm_model = cfg.ollama_model.value
            elif current_service == LLMServiceEnum.LM_STUDIO:
                base_url = cfg.lm_studio_api_base.value
                api_key = cfg.lm_studio_api_key.value
                llm_model = cfg.lm_studio_model.value
            elif current_service == LLMServiceEnum.GEMINI:
                base_url = cfg.gemini_api_base.value
                api_key = cfg.gemini_api_key.value
                llm_model = cfg.gemini_model.value
            elif current_service == LLMServiceEnum.CHATGLM:
                base_url = cfg.chatglm_api_base.value
                api_key = cfg.chatglm_api_key.value
                llm_model = cfg.chatglm_model.value
            elif current_service == LLMServiceEnum.PUBLIC:
                base_url = cfg.public_api_base.value
                api_key = cfg.public_api_key.value
                llm_model = cfg.public_model.value
            else:
                base_url = ""
                api_key = ""
                llm_model = ""
                
            # 设置OpenAI环境变量
            import os
            os.environ["OPENAI_BASE_URL"] = base_url
            os.environ["OPENAI_API_KEY"] = api_key
            
            # 提取字幕文本
            subtitle_text = ""
            for seg in asr_data.segments:
                start_time = QTime(0, 0).addMSecs(seg.start_time).toString("hh:mm:ss.zzz")[:-2]
                subtitle_text += f"[{start_time}] {seg.text}\n"
            
            # 生成笔记
            from pathlib import Path
            import openai
            
            # 创建笔记输出路径
            notes_path = self.factory.get_notes_path(output_path)
            
            # 读取提示词文件内容
            if prompt_file.exists():
                prompt = prompt_file.read_text(encoding="utf-8")
                logger.info("成功读取提示词文件内容")
            else:
                logger.exception(f"生成笔记失败: {str(e)}")
                return
                # 创建默认提示词文件
        
            usr_prompt = """字幕内容如下:${subtitle_text}。
要求：
1. 直接生成markdown内容，不用代码块包裹
2. 不用生多余内容
3. 保持内容的连贯性和逻辑结构


请直接返回Markdown格式的笔记内容（不用代码块），无需包含其他解释。"""

            # 使用Template替换变量
            usr_prompt = Template(usr_prompt).safe_substitute(subtitle_text=subtitle_text)
            
            self.task_progress.emit(batch_task.file_path, 60, "正在使用大语言模型生成笔记...")
            
            client = openai.OpenAI(
                base_url=base_url,
                api_key=api_key
            )

            # logger.info(f"创建了默认提示词文件: {prompt}")
            logger.info(f"创建了默认提示词文件: {usr_prompt}")
            response = client.chat.completions.create(
                model=llm_model,
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": usr_prompt}
                ],
                temperature=0.3
            )
            
            markdown_notes = response.choices[0].message.content
            
            # 写入笔记文件
            with open(notes_path, "w", encoding="utf-8") as f:
                f.write(markdown_notes)
                
            self.task_progress.emit(batch_task.file_path, 100, "笔记生成完成")
            batch_task.status = BatchTaskStatus.COMPLETED
            self.task_completed.emit(batch_task.file_path)
            
        except Exception as e:
            logger.exception(f"生成笔记失败: {str(e)}")
            batch_task.status = BatchTaskStatus.FAILED
            batch_task.error_message = str(e)
            self.task_error.emit(batch_task.file_path, str(e))
