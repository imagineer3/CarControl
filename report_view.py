# -*- coding: utf-8 -*-
"""
接收地址：192.168.137.63:8888
保存目录：C:\Car_Report
完全对齐标准recv_all循环读逻辑，支持接收任意数量PDF，适配TCP_NODELAY
"""
import socket
import struct
import os
import sys
from datetime import datetime
from PySide6.QtWidgets import *
from PySide6.QtCore import *

class PDFReceiverThread(QThread):
    pdf_received = Signal(str)
    log_msg = Signal(str)
    finished = Signal()

    def __init__(self, listen_port=8888, save_dir=r"C:\Car_Report"):
        super().__init__()
        self.listen_port = listen_port
        self.save_dir = save_dir
        self.running = True
        # 确保目录存在
        os.makedirs(self.save_dir, exist_ok=True)
        # 单文件最大限制，过滤异常脏数据
        self.MAX_FILE_SIZE = 5 * 1024 * 1024

    # 标准recv_all：循环收满指定字节（和对方要求完全一致）
    def recv_all(self, sock, n):
        data = b""
        while len(data) < n:
            # 剩余多少就读多少
            chunk = sock.recv(n - len(data))
            if not chunk:
                # 连接断开，返回已收到数据
                break
            data += chunk
        return data

    def run(self):
        try:
            # 创建TCP服务端套接字
            server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            # 端口复用
            server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            # 绑定本机所有网卡 + 8888端口
            server_sock.bind(("0.0.0.0", self.listen_port))
            # 开始监听
            server_sock.listen(1)
            server_sock.settimeout(1)

            self.log_msg.emit("========================================")
            self.log_msg.emit("✅ 接收服务启动成功")
            self.log_msg.emit("📍 接收地址：192.168.137.63:8888")
            self.log_msg.emit("📄 支持接收任意数量 PDF")
            self.log_msg.emit("📍 保存目录：C:\\Car_Report")
            self.log_msg.emit("========================================")

            while self.running:
                try:
                    # 等待客户端连接
                    conn, client_addr = server_sock.accept()
                    # 连接超时30秒
                    conn.settimeout(30)
                    self.log_msg.emit(f"🔗 客户端已连接：{client_addr}")

                    current_file = 0
                    # 无限循环接收文件，直到对方断开连接
                    while True:
                        current_file += 1
                        self.log_msg.emit(f"\n---------- 开始接收第 {current_file} 个 PDF ----------")

                        # 1. 读取4字节文件长度包头
                        header_data = self.recv_all(conn, 4)
                        if len(header_data) != 4:
                            self.log_msg.emit(f"ℹ️ 对方已断开连接，本次共接收 {current_file-1} 个文件")
                            break

                        # 解析大端无符号整型文件长度
                        file_length = struct.unpack(">I", header_data)[0]
                        self.log_msg.emit(f"📏 解析文件长度：{file_length} 字节")

                        # 过滤非法大小
                        if file_length <= 0 or file_length > self.MAX_FILE_SIZE:
                            self.log_msg.emit(f"❌ 第{current_file}个文件：文件大小异常，丢弃数据")
                            continue

                        # 2. 循环读取完整文件内容
                        file_content = self.recv_all(conn, file_length)
                        if len(file_content) != file_length:
                            self.log_msg.emit(f"❌ 第{current_file}个文件：文件内容接收不完整")
                            continue

                        # 拼接文件名并保存
                        file_name = f"pdf_{datetime.now().strftime('%Y%m%d%H%M%S')}_{current_file}.pdf"
                        save_path = os.path.join(self.save_dir, file_name)
                        with open(save_path, "wb") as f:
                            f.write(file_content)

                        self.pdf_received.emit(save_path)
                        self.log_msg.emit(f"✅ 第{current_file}个文件接收完成，保存路径：{save_path}")

                    # 对方断开后关闭当前连接
                    conn.close()

                except socket.timeout:
                    # 监听超时，继续循环
                    continue
                except Exception as e:
                    self.log_msg.emit(f"⚠️ 连接异常：{str(e)}")

        except Exception as e:
            self.log_msg.emit(f"❌ 服务启动失败：{str(e)}")
        finally:
            if 'server_sock' in locals() and server_sock:
                server_sock.close()
            self.finished.emit()

    def stop(self):
        # 停止线程
        self.running = False
        self.wait()

class ReportViewWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.save_dir = r"C:\Car_Report"
        self.listen_port = 8888
        self.local_ip = "192.168.137.63"
        self.current_file_path = None  # 存储最新接收的PDF路径
        self.work_thread = None
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("PDF 接收工具（标准recv_all版）")
        self.setStyleSheet("background-color:#ffffff;")
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(25, 25, 25, 25)
        main_layout.setSpacing(12)

        # 标题
        title_label = QLabel("📄 PDF 文件接收工具")
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet("font-size:22px; font-weight:bold; color:#2c3e50;")
        main_layout.addWidget(title_label)

        # 地址提示
        addr_tip = QLabel(f"本机接收地址：{self.local_ip}:{self.listen_port}\n支持接收任意数量 PDF 文件")
        addr_tip.setAlignment(Qt.AlignCenter)
        addr_tip.setStyleSheet("font-size:15px; color:#27ae60; padding:10px; border:1px solid #dddddd; border-radius:8px;")
        main_layout.addWidget(addr_tip)

        # 功能按钮
        self.btn_start = QPushButton("▶ 开始监听")
        self.btn_stop = QPushButton("■ 停止监听")
        self.btn_open_file = QPushButton("📄 打开最新PDF")
        self.btn_open_folder = QPushButton("📂 打开保存文件夹")
        self.btn_clear_log = QPushButton("🧹 清空日志")

        btn_style = """
        QPushButton{
            font-size:14px;
            padding:9px;
            border-radius:6px;
            background-color:#3498db;
            color:#ffffff;
        }
        QPushButton:disabled{
            background-color:#95a5a6;
        }
        """
        for btn in [self.btn_start, self.btn_stop, self.btn_open_file, self.btn_open_folder, self.btn_clear_log]:
            btn.setStyleSheet(btn_style)
            main_layout.addWidget(btn)

        # 初始禁用停止、打开文件按钮
        self.btn_stop.setEnabled(False)
        self.btn_open_file.setEnabled(False)

        # 日志区域
        log_title = QLabel("运行日志")
        log_title.setStyleSheet("font-size:14px; font-weight:bold;")
        main_layout.addWidget(log_title)

        self.log_edit = QTextEdit()
        self.log_edit.setReadOnly(True)
        main_layout.addWidget(self.log_edit)

        # 最新文件路径显示
        self.file_path_label = QLabel("当前无接收文件")
        self.file_path_label.setStyleSheet("background:#f8f9fa; padding:8px; border-radius:6px;")
        main_layout.addWidget(self.file_path_label)

        self.setLayout(main_layout)
        self.resize(850, 680)

        # 绑定事件
        self.btn_start.clicked.connect(self.start_listen)
        self.btn_stop.clicked.connect(self.stop_listen)
        self.btn_open_file.clicked.connect(self.open_latest_file)
        self.btn_open_folder.clicked.connect(self.open_save_folder)
        self.btn_clear_log.clicked.connect(self.log_edit.clear)

    def start_listen(self):
        if self.work_thread and self.work_thread.isRunning():
            return
        # 启动接收线程
        self.work_thread = PDFReceiverThread(self.listen_port, self.save_dir)
        self.work_thread.log_msg.connect(self.log_edit.append)
        self.work_thread.pdf_received.connect(self.on_file_received)
        self.work_thread.finished.connect(lambda: self.log_edit.append("✅ 监听服务已停止"))
        self.work_thread.start()

        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.log_edit.append("⏳ 监听已启动，等待客户端连接...")

    def stop_listen(self):
        if self.work_thread:
            self.work_thread.stop()
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)

    def on_file_received(self, file_path):
        # 更新最新文件路径
        self.current_file_path = file_path
        self.file_path_label.setText(f"最新文件：{file_path}")
        self.btn_open_file.setEnabled(True)
        # 弹窗提示
        QMessageBox.information(self, "接收成功", f"文件已成功保存：\n{file_path}")

    def open_latest_file(self):
        """修改核心逻辑：确保打开最新接收并保存的PDF文件"""
        if self.current_file_path and os.path.isfile(self.current_file_path):
            try:
                # 兼容不同系统的文件打开方式（Windows用startfile，其他系统用os.system/ subprocess）
                if sys.platform == "win32":
                    os.startfile(self.current_file_path)
                else:
                    import subprocess
                    subprocess.run(["open" if sys.platform == "darwin" else "xdg-open", self.current_file_path])
            except Exception as e:
                QMessageBox.warning(self, "打开失败", f"无法打开文件：{str(e)}")
        else:
            QMessageBox.warning(self, "文件不存在", "最新接收的PDF文件不存在，请检查保存路径！")

    def open_save_folder(self):
        os.startfile(self.save_dir)

    def closeEvent(self, event):
        # 关闭窗口时停止监听
        self.stop_listen()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = ReportViewWidget()
    win.show()
    sys.exit(app.exec())