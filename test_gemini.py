import google.generativeai as genai
import os
from rich import print
from rich.console import Console
from rich.panel import Panel

# 初始化控制台用于更好的输出展示
console = Console()

# 设置 HTTP/HTTPS 代理
os.environ['HTTP_PROXY'] = 'http://127.0.0.1:1080'  # Clash 默认端口
os.environ['HTTPS_PROXY'] = 'http://127.0.0.1:1080'

# 配置 API key
GOOGLE_API_KEY = "AIzaSyDxYyXeJC4m-Jfz9fxzagl3PZEyn2t4yz0"  # 请替换成你的实际 API key
genai.configure(api_key=GOOGLE_API_KEY)

# 设置使用的模型
GEMINI_MODEL = 'gemini-2.0-flash'

def list_available_models():
    """列出所有可用的模型"""
    try:
        models = genai.list_models()
        console.print("\n[bold yellow]可用的模型列表：[/bold yellow]")
        for model in models:
            is_current = model.name == GEMINI_MODEL
            border_style = "red" if is_current else "green"
            title_style = "bold red" if is_current else "cyan"
            
            console.print(Panel(
                f"名称: {model.name}\n"
                f"显示名称: {model.display_name}\n"
                f"描述: {model.description}\n"
                f"支持的生成类型: {', '.join(model.supported_generation_methods)}\n"
                f"温度范围: {model.temperature_range if hasattr(model, 'temperature_range') else '未指定'}",
                title=f"[{title_style}]{model.name}[/{title_style}]{'  [当前使用]' if is_current else ''}",
                border_style=border_style
            ))
    except Exception as e:
        console.print(f"[bold red]获取模型列表时出错[/bold red]: {str(e)}")

def test_text_generation():
    """测试基本的文本生成功能"""
    try:
        # 使用统一的模型变量
        model = genai.GenerativeModel(GEMINI_MODEL)
        
        # 测试简单问题
        prompt = "用简短的话解释一下什么是量子计算？"
        console.print(f"\n[bold cyan]提问[/bold cyan]: {prompt}")
        
        response = model.generate_content(prompt)
        console.print(Panel(response.text, title="回答", border_style="green"))
        
    except Exception as e:
        console.print(f"[bold red]错误[/bold red]: {str(e)}")

def test_conversation():
    """测试对话功能"""
    try:
        model = genai.GenerativeModel(GEMINI_MODEL)
        chat = model.start_chat(history=[])
        
        # 进行多轮对话测试
        questions = [
            "你好，我想学习Python，应该从哪里开始？",
            "我想写一个网站，需要学习哪些框架？",
            "这些框架中哪个最适合初学者？"
        ]
        
        console.print("\n[bold magenta]开始对话测试[/bold magenta]")
        
        for question in questions:
            console.print(f"\n[bold cyan]用户[/bold cyan]: {question}")
            response = chat.send_message(question)
            console.print(Panel(response.text, title="Gemini", border_style="green"))
            
    except Exception as e:
        console.print(f"[bold red]错误[/bold red]: {str(e)}")

def test_code_generation():
    """测试代码生成功能"""
    try:
        model = genai.GenerativeModel(GEMINI_MODEL)
        
        prompt = "写一个Python函数，实现冒泡排序，并包含注释"
        console.print(f"\n[bold cyan]提问[/bold cyan]: {prompt}")
        
        response = model.generate_content(prompt)
        console.print(Panel(response.text, title="生成的代码", border_style="blue"))
        
    except Exception as e:
        console.print(f"[bold red]错误[/bold red]: {str(e)}")

if __name__ == "__main__":
    console.print("[bold yellow]开始测试 Gemini API...[/bold yellow]")
    console.print(f"[bold cyan]当前使用模型[/bold cyan]: {GEMINI_MODEL}")
    
    # 首先列出可用模型
    list_available_models()
    
    # 运行所有测试
    test_text_generation()
    test_conversation()
    test_code_generation()
    
    console.print("\n[bold green]测试完成！[/bold green]") 