"""单测：图像生成多模型调度 + 文件保存"""
import sys
from pathlib import Path
sys.path.insert(0, ".")

from app.tools.files import generate_image, save_output_file

print("== 1. 图像生成（多模型调度） ==")
try:
    url = generate_image("flat illustration of a cute cat reading a book, bright colors, minimal style")
    print("图片URL:", url)
    p = Path("data/outputs") / url.replace("/api/files/", "")
    print("文件存在:", p.exists(), "| 大小:", p.stat().st_size if p.exists() else 0, "bytes")
except Exception as e:
    print("FAIL:", str(e)[:200])

print("\n== 2. 文件保存 ==")
u1 = save_output_file("test-table.csv", "部门,任务,截止\n市场部,海报,周三\n技术部,页面,周五\n")
u2 = save_output_file("test-doc.md", "# 测试文档\n\n这是内容。\n")
print("CSV URL:", u1)
print("MD URL:", u2)
