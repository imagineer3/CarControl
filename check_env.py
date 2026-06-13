# YOLOv8 核心依赖检查工具（显示当前版本+要求版本）
required_libs = {
    "torch": "2.0.0",
    "torchvision": "0.15.0",
    "ultralytics": "8.0.0",
    "numpy": "1.24.0",
    "cv2": "4.8.0",       # 对应 opencv-python
    "PIL": "10.0.0",      # 对应 pillow
    "yaml": "6.0"         # 对应 pyyaml
}

import importlib
from packaging import version

def check_package(package_name, min_version):
    try:
        # 特殊库名称映射
        if package_name == "cv2":
            import cv2
            current_ver = cv2.__version__
            show_name = "opencv-python"
        elif package_name == "PIL":
            from PIL import Image
            current_ver = Image.__version__
            show_name = "pillow"
        elif package_name == "yaml":
            import yaml
            current_ver = yaml.__version__
            show_name = "pyyaml"
        else:
            module = importlib.import_module(package_name)
            current_ver = module.__version__
            show_name = package_name

        # 版本对比
        if version.parse(current_ver) >= version.parse(min_version):
            status = "✅ 满足要求"
        else:
            status = "⚠️  版本过低"

        print(f"{show_name:<15} | 当前版本: {current_ver:<10} | 要求版本: ≥{min_version:<8} | {status}")

    except ImportError:
        print(f"{package_name:<15} | 当前版本: 未安装     | 要求版本: ≥{min_version:<8} | ❌ 未安装")

# 开始检查
print("="*60)
print("           YOLOv8 核心依赖版本检查结果")
print("="*60)
for lib, min_ver in required_libs.items():
    check_package(lib, min_ver)
print("="*60)