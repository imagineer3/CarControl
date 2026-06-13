# -*- coding: utf-8 -*-
import sys
import os
import cv2
import socket
import time
import json
import requests
import gc
import pymysql
from datetime import datetime
from PySide6.QtWidgets import *
from PySide6.QtGui import *
from PySide6.QtCore import *
from ultralytics import YOLO
from ui_car import Ui_MainWindow
from user_management import UserManagementWidget
from work_order_management import WorkOrderWidget
from history_data import HistoryWidget
from report_view import ReportViewWidget


# ===================== 配置参数 =====================
MODEL_PATH = "C:/car_detect/yolov8n-seg-cracks-joints.pt"
CAR_IP = "192.168.1.1"
CAR_PORT = 2001
VIDEO_URL = f"http://{CAR_IP}:8080/?action=stream"
PRINT_INTERVAL = 10.0
IMGSZ = 640
TCP_RECV_BUFFER_SIZE = 1024
AUTO_CAPTURE_PATH = "./captures/auto"
MANUAL_CAPTURE_PATH = "./captures/manual"
SERVER_URL = "http://192.168.137.1:8080/api/detect-sequence"
DB_CONFIG = {
    "host": "localhost",
    "port": 3306,
    "database": "database",
    "user": "root",
    "password": "123456"
}
# ====================================================

CMD_DESC = {
    "A": "前进", "B": "后退", "C": "左转", "D": "右转", "E": "停止",
    "L": "云台左（水平+10°）", "I": "云台右（水平-10°）",
    "K": "云台上（垂直+10°）", "J": "云台下（垂直-10°）"
}

# ===================== 图片发送线程 =====================
class ImageSenderThread(QThread):
    progress_updated = Signal(int, int)
    result_received = Signal(dict)
    send_finished = Signal(bool, str)
    log_signal = Signal(str)

    def __init__(self, auto_path, manual_path, wall_id, order_serial=None):
        super().__init__()
        self.auto_path = auto_path
        self.manual_path = manual_path
        self.wall_id = wall_id
        self.order_serial = order_serial
        self.running = True

    def run(self):
        image_paths = []
        for base_path in [self.auto_path, self.manual_path]:
            if os.path.exists(base_path):
                for filename in os.listdir(base_path):
                    if filename.lower().endswith('.jpg'):
                        if self.order_serial:
                            if f"工单{self.order_serial}" in filename:
                                image_paths.append(os.path.join(base_path, filename))
                        else:
                            image_paths.append(os.path.join(base_path, filename))
        if not image_paths:
            self.send_finished.emit(False, f"没有找到任何图片（工单编号：{self.order_serial}）")
            return
        self.log_signal.emit(f"📤 准备发送 {len(image_paths)} 张图片（工单 {self.order_serial}）")
        self.log_signal.emit(f"📍 墙面标识：{self.wall_id}")
        files = []
        open_files = []
        try:
            for path in image_paths:
                f = open(path, 'rb')
                open_files.append(f)
                files.append(('files', (os.path.basename(path), f, 'image/jpeg')))
            self.log_signal.emit("🔌 正在连接服务器...")
            resp = requests.post(
                SERVER_URL,
                files=files,
                data={"wall_id": self.wall_id, "order_serial": self.order_serial},
                stream=True,
                timeout=300
            )
            if resp.status_code != 200:
                self.send_finished.emit(False, f"服务器返回错误：{resp.status_code} {resp.text}")
                return
            self.log_signal.emit("✅ 连接成功，开始接收检测结果...")
            for line in resp.iter_lines():
                if not self.running:
                    break
                if line and line.startswith(b'data: '):
                    try:
                        event = json.loads(line[6:])
                        self.result_received.emit(event)
                        if event.get('status') == 'success':
                            self.progress_updated.emit(event['index'], event['total'])
                        self.log_signal.emit(f"📥 收到检测结果：{json.dumps(event, ensure_ascii=False)}")
                    except json.JSONDecodeError:
                        continue
            self.send_finished.emit(True, f"所有图片发送完成，共处理 {len(image_paths)} 张")
        except requests.exceptions.ConnectionError:
            self.send_finished.emit(False, "无法连接到服务器，请检查网络连接和服务器地址")
        except requests.exceptions.Timeout:
            self.send_finished.emit(False, "连接超时，服务器响应时间过长")
        except Exception as e:
            self.send_finished.emit(False, f"发送失败：{str(e)}")
        finally:
            for f in open_files:
                try:
                    f.close()
                except:
                    pass

    def stop(self):
        self.running = False
        self.wait()

# ===================== TCP数据接收线程 =====================
class TcpReceiverThread(QThread):
    data_received = Signal(str)
    connection_lost = Signal()

    def __init__(self, tcp_socket):
        super().__init__()
        self.tcp_socket = tcp_socket
        self.running = True

    def run(self):
        self.tcp_socket.settimeout(1.0)
        while self.running:
            try:
                data = self.tcp_socket.recv(TCP_RECV_BUFFER_SIZE)
                if not data:
                    self.connection_lost.emit()
                    break
                text = data.decode('utf-8').strip()
                if text:
                    self.data_received.emit(text)
            except socket.timeout:
                continue
            except Exception:
                self.connection_lost.emit()
                break

    def stop(self):
        self.running = False
        self.wait()

# ===================== 视频+YOLO线程 =====================
class VideoWorker(QThread):
    frame_updated = Signal(QPixmap)
    log_signal = Signal(str)
    capture_ready = Signal(bool)

    def __init__(self):
        super().__init__()
        self.running = True
        self.fps = 0.0
        self.frame_count = 0
        self.start_time = time.time()
        self.model = None
        self.last_inference_time_ms = 0.0
        self.last_print_time = time.time()
        self.current_pixmap = None
        self.original_frame = None
        self.cap = None
        self.consecutive_errors = 0
        self.max_consecutive_errors = 5
        self.retry_interval = 1
        self.max_retry_interval = 16
        try:
            self.model = YOLO(MODEL_PATH)
            self.log_signal.emit("✅ YOLO模型加载成功")
        except Exception as e:
            self.log_signal.emit(f"❌ 模型加载失败：{str(e)}")

    def run(self):
        os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp|timeout;5000000"
        self.log_signal.emit("✅ 视频+YOLO已启动")
        while self.running:
            if self.cap is None or not self.cap.isOpened():
                self.log_signal.emit(f"🔄 正在连接视频流（下次重试：{self.retry_interval}秒）...")
                self._cleanup_capture()
                if not self._check_tcp_port(CAR_IP, 8080, timeout=2):
                    self.log_signal.emit(f"⚠️ 树莓派8080端口未开放，{self.retry_interval}秒后重试...")
                    time.sleep(self.retry_interval)
                    self.retry_interval = min(self.retry_interval * 2, self.max_retry_interval)
                    continue
                self.cap = self._create_capture()
                if self.cap is None:
                    self.log_signal.emit(f"⚠️ 视频流连接失败，{self.retry_interval}秒后重试...")
                    time.sleep(self.retry_interval)
                    self.retry_interval = min(self.retry_interval * 2, self.max_retry_interval)
                    continue
                self.consecutive_errors = 0
                self.retry_interval = 1
                self.capture_ready.emit(True)
                self.log_signal.emit("✅ 视频流连接成功")
            ret, frame = self.cap.read()
            if not ret:
                self.consecutive_errors += 1
                self.log_signal.emit(f"⚠️ 读取帧失败 ({self.consecutive_errors}/{self.max_consecutive_errors})")
                if self.consecutive_errors >= self.max_consecutive_errors:
                    self.log_signal.emit("❌ 连续读取失败，正在重新连接视频流...")
                    self._cleanup_capture()
                    self.capture_ready.emit(False)
                time.sleep(0.1)
                continue
            self.consecutive_errors = 0
            self.capture_ready.emit(True)
            self.original_frame = frame.copy()
            self.frame_count += 1
            elapsed = time.time() - self.start_time
            if elapsed >= 0.5:
                self.fps = self.frame_count / elapsed
                self.frame_count = 0
                self.start_time = time.time()
            results = None
            if self.model:
                try:
                    t0 = time.time()
                    results = self.model(frame, conf=0.3, imgsz=IMGSZ, verbose=False)
                    t1 = time.time()
                    self.last_inference_time_ms = (t1 - t0) * 1000.0
                    frame = results[0].plot()
                except Exception as e:
                    self.log_signal.emit(f"❌ YOLO推理异常：{str(e)}")
            fps_text = f"FPS: {self.fps:.1f} | Inference: {self.last_inference_time_ms:.1f}ms"
            cv2.putText(frame, fps_text, (10, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 0), 4)
            cv2.putText(frame, fps_text, (10, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (255, 255, 255), 2)
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w, ch = frame_rgb.shape
            qt_img = QImage(frame_rgb.data, w, h, ch * w, QImage.Format_RGB888)
            self.current_pixmap = QPixmap.fromImage(qt_img)
            self.frame_updated.emit(self.current_pixmap)
        self._cleanup_capture()
        self.capture_ready.emit(False)
        self.log_signal.emit("⏹️ 视频流已关闭")

    def _check_tcp_port(self, host, port, timeout=2):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(timeout)
                result = s.connect_ex((host, port))
                return result == 0
        except:
            return False

    def _create_capture(self):
        cap = cv2.VideoCapture(VIDEO_URL)
        if not cap.isOpened():
            return None
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc('M', 'J', 'P', 'G'))
        cap.set(cv2.CAP_PROP_FPS, 20)
        for _ in range(3):
            cap.grab()
        return cap

    def _cleanup_capture(self):
        if self.cap is not None:
            self.cap.release()
            self.cap = None
        gc.collect()
        self.original_frame = None
        self.current_pixmap = None
        self.consecutive_errors = 0

    def stop(self):
        self.running = False
        self.wait()

# ===================== 主窗口 =====================
class CarController(QMainWindow, Ui_MainWindow):
    def __init__(self):
        super().__init__()
        self.setupUi(self)
        self.tcp_socket = None
        self.tcp_receiver = None
        self.video_worker = None
        self.image_sender = None
        self.manual_mode = False
        self.scan_running = False
        self.current_v_angle = 90.0
        self.current_h_angle = 90.0
        self.current_order_id = None
        self.current_order_serial = None
        self.active_task_order_serial = None
        self.conn_status_label = None
        self._is_closing = False

        os.makedirs(AUTO_CAPTURE_PATH, exist_ok=True)
        os.makedirs(MANUAL_CAPTURE_PATH, exist_ok=True)
        self.log(f"✅ 自动截图保存路径：{os.path.abspath(AUTO_CAPTURE_PATH)}")
        self.log(f"✅ 手动截图保存路径：{os.path.abspath(MANUAL_CAPTURE_PATH)}")

        self.add_task_control_group()
        self.add_auto_scan_group()
        self.reorganize_ui()
        self.fix_button_colors()
        self.adjust_button_sizes()
        self.init_buttons()
        self.bind_all_functions()
        self.setup_navigation_and_pages()

    def reorganize_ui(self):
        """
        完全重构首页布局，严格按照手绘比例：
        主内容区垂直比例：40%（顶部）:30%（中间）:30%（底部）
        顶部水平比例：视频60% : 任务控制40%
        中间水平比例：小车25% : 云台25% : 自动扫描50%
        底部水平比例：操作日志80% : 连接控制20%
        """
        original_widgets = {
            "label_video": self.label_video,
            "car_group": self.groupBox,
            "servo_group": self.groupBox_2,
            "text_log": self.text_log,
            "btn_connect": self.btn_connect,
            "btn_disconnect": self.btn_disconnect
        }

        # 清空原centralWidget的旧布局
        old_layout = self.centralWidget.layout()
        if old_layout is not None:
            while old_layout.count():
                item = old_layout.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.setParent(None)
                else:
                    sub_layout = item.layout()
                    if sub_layout is not None:
                        while sub_layout.count():
                            sub_item = sub_layout.takeAt(0)
                            sub_widget = sub_item.widget()
                            if sub_widget is not None:
                                sub_widget.setParent(None)
            QWidget().setLayout(old_layout)

        # 创建新的主垂直布局
        main_vbox = QVBoxLayout(self.centralWidget)
        main_vbox.setContentsMargins(10, 10, 10, 10)
        main_vbox.setSpacing(10)

        # -------------------------- 顶部区域（40%高度） --------------------------
        top_hbox = QHBoxLayout()
        top_hbox.setSpacing(10)

        # 视频区域（60%宽度）
        video_container = QWidget()
        video_layout = QVBoxLayout(video_container)
        video_layout.setContentsMargins(0, 0, 0, 0)
        original_widgets["label_video"].setParent(video_container)
        original_widgets["label_video"].setAlignment(Qt.AlignCenter)
        original_widgets["label_video"].setStyleSheet("background-color: #000000; color: white;")
        video_layout.addWidget(original_widgets["label_video"])
        top_hbox.addWidget(video_container, 6)

        # 任务控制区域（40%宽度）
        top_hbox.addWidget(self.task_group, 4)
        main_vbox.addLayout(top_hbox, 4)

        # -------------------------- 中间区域（30%高度） --------------------------
        middle_hbox = QHBoxLayout()
        middle_hbox.setSpacing(10)

        # 小车控制（25%宽度）
        middle_hbox.addWidget(original_widgets["car_group"], 2.5)
        # 云台控制（25%宽度）
        middle_hbox.addWidget(original_widgets["servo_group"], 2.5)
        # 自动扫描控制（50%宽度）
        middle_hbox.addWidget(self.auto_scan_group, 5)
        main_vbox.addLayout(middle_hbox, 2)

        # -------------------------- 底部区域（30%高度） --------------------------
        bottom_hbox = QHBoxLayout()
        bottom_hbox.setSpacing(10)

        # 操作日志区域（80%宽度）
        log_container = QWidget()
        log_vbox = QVBoxLayout(log_container)
        log_vbox.setContentsMargins(0, 0, 0, 0)
        log_vbox.setSpacing(5)
        log_label = QLabel("操作日志")
        log_label.setStyleSheet("font-weight: bold; font-size: 13px;")
        log_vbox.addWidget(log_label)
        original_widgets["text_log"].setParent(log_container)
        log_vbox.addWidget(original_widgets["text_log"])
        bottom_hbox.addWidget(log_container, 8)

        # 连接控制区域（20%宽度） -> 底部对齐，整体下移
        conn_container = QWidget()
        conn_vbox = QVBoxLayout(conn_container)
        conn_vbox.setContentsMargins(0, 0, 0, 0)
        conn_vbox.setSpacing(10)
        conn_vbox.setAlignment(Qt.AlignCenter)   # 改为底部对齐
  

        # 连接状态标签
        self.conn_status_label = QLabel("未连接")
        self.conn_status_label.setAlignment(Qt.AlignCenter)
        self.conn_status_label.setStyleSheet("""
            QLabel {
                font-size: 14px;
                font-weight: bold;
                color: #e74c3c;
                padding: 8px;
                border: 1px solid #e74c3c;
                border-radius: 6px;
            }
        """)
        conn_vbox.addWidget(self.conn_status_label)

        # 连接按钮
        original_widgets["btn_connect"].setParent(conn_container)
        original_widgets["btn_connect"].setMinimumHeight(45)
        conn_vbox.addWidget(original_widgets["btn_connect"])

        # 断开按钮
        original_widgets["btn_disconnect"].setParent(conn_container)
        original_widgets["btn_disconnect"].setMinimumHeight(45)
        conn_vbox.addWidget(original_widgets["btn_disconnect"])

        bottom_hbox.addWidget(conn_container, 2)
        main_vbox.addLayout(bottom_hbox, 4)

        # 移除原界面的“自动循迹控制”组框（如果存在）
        trace_group = None
        if hasattr(self, 'groupBox_3'):
            trace_group = self.groupBox_3
            if '循迹' not in trace_group.title():
                trace_group = None
        if trace_group is None:
            for child in self.centralWidget.children():
                if isinstance(child, QGroupBox) and '循迹' in child.title():
                    trace_group = child
                    break
        if trace_group is not None:
            trace_group.deleteLater()

    def set_all_parameters(self):
        """设置所有参数：途径点数量、初始水平/垂直角度、垂直步长，发送到树莓派"""
        if not hasattr(self, 'edit_point_num') or self.edit_point_num is None:
            self.log("❌ 途径点输入框未初始化")
            return
        num = self.edit_point_num.text().strip()
        h_init = self.edit_servo_h_init.text().strip()
        v_init = self.edit_servo_v_init.text().strip()
        step = self.edit_servo_step.text().strip()

        if not num.isdigit() or not (1 <= int(num) <= 9):
            self.log("⚠️ 途径点数量必须是1-9之间的数字！")
            return
        try:
            h_init_val = float(h_init) if h_init else 90.0
            if not (0 <= h_init_val <= 180):
                self.log("⚠️ 初始水平角度必须在0-180之间！")
                return
        except:
            self.log("⚠️ 初始水平角度必须是数字！")
            return
        try:
            v_init_val = float(v_init) if v_init else 0.0
            if not (0 <= v_init_val <= 90):
                self.log("⚠️ 初始垂直角度必须在0-90之间！")
                return
        except:
            self.log("⚠️ 初始垂直角度必须是数字！")
            return
        try:
            step_val = int(step) if step else 10
            if not (1 <= step_val <= 90):
                self.log("⚠️ 垂直步长必须在1-90之间！")
                return
        except:
            self.log("⚠️ 垂直步长必须是数字！")
            return

        self.send_raw(f"SET{num}", desc=f"设置途径点{num}个")
        self.log(f"✅ 参数已设置：途径点={num}，初始水平={h_init_val}°，初始垂直={v_init_val}°，垂直步长={step_val}°")

    # ===================== 数据库连接 =====================
    def get_db_connection(self):
        try:
            conn = pymysql.connect(
                host=DB_CONFIG["host"],
                port=DB_CONFIG["port"],
                user=DB_CONFIG["user"],
                password=DB_CONFIG["password"],
                database=DB_CONFIG["database"],
                charset="utf8mb4"
            )
            return conn
        except Exception as e:
            self.log(f"❌ 数据库连接失败：{str(e)}")
            return None

    # ===================== 任务控制组 =====================
    def add_task_control_group(self):
        """创建任务控制组控件"""
        self.task_group = QGroupBox("任务控制")
        task_layout = QVBoxLayout(self.task_group)
        self.current_title = QLabel("当前工单：")
        self.current_title.setStyleSheet("font-weight: bold; font-size: 13px;")
        task_layout.addWidget(self.current_title)
        self.info_widget = QWidget()
        info_layout = QVBoxLayout(self.info_widget)
        info_layout.setSpacing(4)
        self.label_line1 = QLabel()
        self.label_line2 = QLabel()
        self.label_line3 = QLabel()
        for lbl in [self.label_line1, self.label_line2, self.label_line3]:
            lbl.setWordWrap(True)
            lbl.setStyleSheet("font-size: 12px; background-color: #f5f5f5; padding: 3px; border-radius: 3px;")
            info_layout.addWidget(lbl)
        task_layout.addWidget(self.info_widget)
        self.mode_label = QLabel("当前模式：自动控制")
        self.mode_label.setStyleSheet("font-size: 12px; font-weight: bold; color: #2c3e50; margin-top: 5px;")
        task_layout.addWidget(self.mode_label)
        hbox_start = QHBoxLayout()
        self.btn_start_task = QPushButton("开始任务")
        self.btn_complete_task = QPushButton("完成任务")
        for btn in [self.btn_start_task, self.btn_complete_task]:
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            btn.setStyleSheet("font-size: 12px; min-height: 35px;")
            hbox_start.addWidget(btn)
        task_layout.addLayout(hbox_start)
        hbox_load = QHBoxLayout()
        self.btn_load_order = QPushButton("加载工单")
        self.btn_cancel_order = QPushButton("取消工单")
        for btn in [self.btn_load_order, self.btn_cancel_order]:
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            btn.setStyleSheet("font-size: 12px; min-height: 30px;")
            hbox_load.addWidget(btn)
        task_layout.addLayout(hbox_load)
        hbox_mode = QHBoxLayout()
        self.btn_manual = QPushButton("手动控制")
        self.btn_auto = QPushButton("自动控制")
        self.btn_manual.setCheckable(True)
        self.btn_auto.setCheckable(True)
        for btn in [self.btn_manual, self.btn_auto]:
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            btn.setStyleSheet("font-size: 12px; min-height: 30px;")
        self.btn_auto.setChecked(True)
        self.btn_auto.setStyleSheet("background-color: #3498db; color: white; font-size: 12px; min-height: 30px;")
        hbox_mode.addWidget(self.btn_manual)
        hbox_mode.addWidget(self.btn_auto)
        task_layout.addLayout(hbox_mode)
        task_layout.addStretch()
        self.btn_load_order.clicked.connect(self.load_order_dialog)
        self.btn_cancel_order.clicked.connect(self.cancel_order)
        self.btn_start_task.clicked.connect(self.start_task)
        self.btn_complete_task.clicked.connect(self.complete_task)
        self.btn_manual.clicked.connect(self.set_manual_mode)
        self.btn_auto.clicked.connect(self.set_auto_mode)
        self.update_order_display(None, None, None, None, None)

    def update_order_display(self, serial_num, building, status, executor, plan_time):
        if serial_num:
            self.label_line1.setText(f"工单编号：{serial_num}  建筑代号：{building}")
            self.label_line2.setText(f"工单状态：{status}  执行人：{executor}")
            self.label_line3.setText(f"计划时间：{plan_time if plan_time else '未设置'}")
        else:
            self.label_line1.setText("未加载工单")
            self.label_line2.setText("")
            self.label_line3.setText("")

    def set_manual_mode(self):
        if not self.btn_manual.isChecked():
            return
        self.manual_mode = True
        self.btn_manual.setChecked(True)
        self.btn_auto.setChecked(False)
        self.btn_manual.setStyleSheet("background-color: #3498db; color: white; font-size: 12px; min-height: 30px;")
        self.btn_auto.setStyleSheet("font-size: 12px; min-height: 30px;")
        self.mode_label.setText("当前模式：手动控制")
        self.log("🎮 已切换到手动控制模式")
        self.set_auto_trace_enabled(False)
        self.set_motion_controls_enabled(True)

    def set_auto_mode(self):
        if not self.btn_auto.isChecked():
            return
        self.manual_mode = False
        self.btn_auto.setChecked(True)
        self.btn_manual.setChecked(False)
        self.btn_auto.setStyleSheet("background-color: #3498db; color: white; font-size: 12px; min-height: 30px;")
        self.btn_manual.setStyleSheet("font-size: 12px; min-height: 30px;")
        self.mode_label.setText("当前模式：自动控制")
        self.log("🤖 已切换到自动控制模式")
        self.set_auto_trace_enabled(True)
        self.set_motion_controls_enabled(False)

    def load_order_dialog(self):
        conn = self.get_db_connection()
        if not conn:
            return
        try:
            cursor = conn.cursor()
            sql = """
                SELECT t.serial_num, t.order_id, t.building_code, t.order_status, t.executor_name, t.plan_time
                FROM (
                    SELECT 
                        (@row_number := @row_number + 1) AS serial_num,
                        order_id,
                        building_code,
                        order_status,
                        executor_name,
                        plan_time
                    FROM inspect_work_order, (SELECT @row_number := 0) AS vars
                    ORDER BY order_id
                ) AS t
                WHERE t.order_status != '已完成'
                ORDER BY t.serial_num
            """
            cursor.execute(sql)
            rows = cursor.fetchall()
            cursor.close()
            if not rows:
                QMessageBox.information(self, "提示", "当前没有未完成的工单")
                return
            dialog = QDialog(self)
            dialog.setWindowTitle("选择工单")
            dialog.setMinimumWidth(700)
            layout = QVBoxLayout(dialog)
            table = QTableWidget()
            table.verticalHeader().setVisible(False)
            table.setColumnCount(5)
            table.setHorizontalHeaderLabels(["工单编号", "建筑代号", "工单状态", "执行人", "计划时间"])
            table.setSelectionBehavior(QAbstractItemView.SelectRows)
            table.setSelectionMode(QAbstractItemView.SingleSelection)
            table.setEditTriggers(QAbstractItemView.NoEditTriggers)
            table.horizontalHeader().setStretchLastSection(True)
            table.setRowCount(len(rows))
            for i, row in enumerate(rows):
                serial_num_val = row[0]
                serial_num_int = int(float(serial_num_val))
                table.setItem(i, 0, QTableWidgetItem(f"{serial_num_int:03d}"))
                table.setItem(i, 1, QTableWidgetItem(row[2] or ""))
                table.setItem(i, 2, QTableWidgetItem(row[3] or ""))
                executor = row[4] if row[4] else "未指派"
                table.setItem(i, 3, QTableWidgetItem(executor))
                plan_time = row[5]
                if plan_time and isinstance(plan_time, datetime):
                    plan_time = plan_time.strftime("%Y-%m-%d %H:%M:%S")
                elif not plan_time:
                    plan_time = ""
                table.setItem(i, 4, QTableWidgetItem(plan_time))
                table.item(i, 0).setData(Qt.UserRole, row[1])
            layout.addWidget(table)
            button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
            layout.addWidget(button_box)
            def on_accept():
                selected = table.currentRow()
                if selected < 0:
                    QMessageBox.warning(dialog, "提示", "请先选择一个工单")
                    return
                order_id = table.item(selected, 0).data(Qt.UserRole)
                serial_num_text = table.item(selected, 0).text()
                serial_num_int = int(serial_num_text)
                self.current_order_id = order_id
                self.current_order_serial = f"{serial_num_int:03d}"
                building = table.item(selected, 1).text()
                status = table.item(selected, 2).text()
                executor = table.item(selected, 3).text()
                plan_time = table.item(selected, 4).text()
                if not plan_time:
                    plan_time = "未设置"
                self.update_order_display(self.current_order_serial, building, status, executor, plan_time)
                self.log(f"📋 已加载工单：{self.current_order_serial} {building} {status} {executor}")
                dialog.accept()
            button_box.accepted.connect(on_accept)
            button_box.rejected.connect(dialog.reject)
            dialog.exec()
        except Exception as e:
            QMessageBox.critical(self, "错误", f"加载工单列表失败：{str(e)}")
        finally:
            conn.close()

    def cancel_order(self):
        if self.current_order_id is None:
            QMessageBox.information(self, "提示", "当前没有加载任何工单")
            return
        conn = self.get_db_connection()
        if conn:
            try:
                cursor = conn.cursor()
                cursor.execute("UPDATE inspect_work_order SET order_status='待巡检', finish_time=NULL WHERE order_id=%s", (self.current_order_id,))
                conn.commit()
                cursor.close()
                self.log(f"🔄 工单 {self.current_order_serial} 已取消，状态恢复为待巡检")
            except Exception as e:
                self.log(f"❌ 取消工单失败：{str(e)}")
            finally:
                conn.close()
        self.current_order_id = None
        self.current_order_serial = None
        self.active_task_order_serial = None
        self.update_order_display(None, None, None, None, None)
        self.log("❌ 已取消当前工单")

    def start_task(self):
        if self.current_order_id is None:
            QMessageBox.warning(self, "警告", "请先加载工单")
            return
        conn = self.get_db_connection()
        if not conn:
            return
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT order_status FROM inspect_work_order WHERE order_id=%s", (self.current_order_id,))
            row = cursor.fetchone()
            if not row:
                QMessageBox.warning(self, "错误", "工单不存在")
                self.cancel_order()
                return
            if row[0] == "已完成":
                QMessageBox.warning(self, "提示", "该工单已完成，无法开始")
                return
            cursor.execute("UPDATE inspect_work_order SET order_status='巡检中' WHERE order_id=%s", (self.current_order_id,))
            conn.commit()
            self.log(f"✅ 工单 {self.current_order_serial} 已开始（状态：巡检中）")
            self.active_task_order_serial = self.current_order_serial
            current_line2 = self.label_line2.text()
            if "  执行人：" in current_line2:
                parts = current_line2.split("  执行人：")
                if len(parts) >= 2:
                    self.label_line2.setText(f"工单状态：巡检中  执行人：{parts[1]}")
            QMessageBox.information(self, "成功", f"工单 {self.current_order_serial} 已开始")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"开始任务失败：{str(e)}")
        finally:
            conn.close()

    def complete_task(self):
        if self.current_order_id is None:
            QMessageBox.warning(self, "警告", "请先加载工单")
            return
        conn = self.get_db_connection()
        if not conn:
            return
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT order_status FROM inspect_work_order WHERE order_id=%s", (self.current_order_id,))
            row = cursor.fetchone()
            if not row:
                QMessageBox.warning(self, "错误", "工单不存在")
                self.cancel_order()
                return
            if row[0] == "已完成":
                QMessageBox.warning(self, "提示", "工单已经是已完成状态")
                return
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute("UPDATE inspect_work_order SET order_status='已完成', finish_time=%s WHERE order_id=%s", (now, self.current_order_id))
            conn.commit()
            self.log(f"✅ 工单 {self.current_order_serial} 已完成，完成时间：{now}")
            self.current_order_id = None
            self.current_order_serial = None
            self.active_task_order_serial = None
            self.update_order_display(None, None, None, None, None)
            QMessageBox.information(self, "成功", "工单已完成")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"完成任务失败：{str(e)}")
        finally:
            conn.close()

    # ===================== 自动扫描控制组 =====================
    def add_auto_scan_group(self):
        """创建自动扫描控制组控件（增大行距，均匀分布）"""
        self.auto_scan_group = QGroupBox("自动扫描控制")
        layout = QVBoxLayout(self.auto_scan_group)
        # 增大垂直间距，从6改为12
        layout.setSpacing(12)
        layout.setContentsMargins(8, 8, 8, 8)

        # 第一行：途径点数量 + 垂直步长
        row1_layout = QHBoxLayout()
        row1_layout.setSpacing(8)
        point_layout = QHBoxLayout()
        point_layout.addWidget(QLabel("途径点："))
        self.edit_point_num = QLineEdit()
        self.edit_point_num.setPlaceholderText("1-9")
        self.edit_point_num.setAlignment(Qt.AlignCenter)
        self.edit_point_num.setMinimumHeight(26)
        point_layout.addWidget(self.edit_point_num, 1)
        row1_layout.addLayout(point_layout, 1)
        step_layout = QHBoxLayout()
        step_layout.addWidget(QLabel("垂直步长："))
        self.edit_servo_step = QLineEdit("10")
        self.edit_servo_step.setPlaceholderText("1-90")
        self.edit_servo_step.setAlignment(Qt.AlignCenter)
        self.edit_servo_step.setMinimumHeight(26)
        step_layout.addWidget(self.edit_servo_step, 1)
        row1_layout.addLayout(step_layout, 1)
        layout.addLayout(row1_layout)

        # 第二行：初始水平 + 初始垂直
        row2_layout = QHBoxLayout()
        row2_layout.setSpacing(8)
        h_init_layout = QHBoxLayout()
        h_init_layout.addWidget(QLabel("初始水平："))
        self.edit_servo_h_init = QLineEdit()
        self.edit_servo_h_init.setPlaceholderText("0=最左 90=中间 180=最右")
        self.edit_servo_h_init.setAlignment(Qt.AlignCenter)
        self.edit_servo_h_init.setMinimumHeight(26)
        h_init_layout.addWidget(self.edit_servo_h_init, 1)
        row2_layout.addLayout(h_init_layout, 1)
        v_init_layout = QHBoxLayout()
        v_init_layout.addWidget(QLabel("初始垂直："))
        self.edit_servo_v_init = QLineEdit()
        self.edit_servo_v_init.setPlaceholderText("0=垂直向下 90=水平向前")
        self.edit_servo_v_init.setAlignment(Qt.AlignCenter)
        self.edit_servo_v_init.setMinimumHeight(26)
        v_init_layout.addWidget(self.edit_servo_v_init, 1)
        row2_layout.addLayout(v_init_layout, 1)
        layout.addLayout(row2_layout)

        # 第三行：四个按钮并排（统一高度）
        row3_layout = QHBoxLayout()
        row3_layout.setSpacing(6)
        button_style = """
        QPushButton {
            min-height: 28px;
            font-size: 12px;
        }
        """
        self.btn_scan_start = QPushButton("开始扫描")
        self.btn_scan_start.setStyleSheet(button_style)
        self.btn_scan_start.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        row3_layout.addWidget(self.btn_scan_start, 1)
        self.btn_scan_stop = QPushButton("停止扫描")
        self.btn_scan_stop.setEnabled(False)
        self.btn_scan_stop.setStyleSheet(button_style)
        self.btn_scan_stop.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        row3_layout.addWidget(self.btn_scan_stop, 1)
        self.btn_set_point = QPushButton("设置")
        self.btn_set_point.setStyleSheet(button_style)
        self.btn_set_point.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.btn_set_point.clicked.connect(self.set_all_parameters)
        row3_layout.addWidget(self.btn_set_point, 1)
        self.btn_manual_capture = QPushButton("手动截图")
        self.btn_manual_capture.setEnabled(False)
        self.btn_manual_capture.setStyleSheet(button_style)
        self.btn_manual_capture.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        row3_layout.addWidget(self.btn_manual_capture, 1)
        layout.addLayout(row3_layout)

        # 第四行：墙面标识 + 发送图片
        row4_layout = QHBoxLayout()
        row4_layout.setSpacing(8)
        wall_layout = QHBoxLayout()
        wall_layout.addWidget(QLabel("墙面标识："))
        self.edit_wall_id = QLineEdit("3F东墙")
        self.edit_wall_id.setPlaceholderText("如：3F东墙")
        self.edit_wall_id.setMinimumHeight(26)
        wall_layout.addWidget(self.edit_wall_id, 2)
        row4_layout.addLayout(wall_layout, 2)
        self.btn_send_images = QPushButton("发送图片")
        self.btn_send_images.setMinimumHeight(28)
        row4_layout.addWidget(self.btn_send_images, 1)
        layout.addLayout(row4_layout)

        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setFormat("发送进度：%v/%m")
        self.progress_bar.setMinimumHeight(18)
        layout.addWidget(self.progress_bar)
        # 添加一个伸缩项，使内容在框中均匀分布（如果有剩余空间）
        layout.addStretch()

    # ===================== UI样式调整 =====================
    def adjust_button_sizes(self):
        button_style = """
            QPushButton { font-size: 12px; padding: 6px; min-width: 70px; min-height: 30px; border-radius: 4px; }
        """
        all_buttons = [
            self.btn_forward, self.btn_backward, self.btn_left, self.btn_right, self.btn_stop,
            self.btn_servo_up, self.btn_servo_down, self.btn_servo_left, self.btn_servo_right, self.btn_servo_reset
        ]
        if hasattr(self, 'btn_start_task'):
            all_buttons.extend([self.btn_start_task, self.btn_complete_task, self.btn_load_order, self.btn_cancel_order, self.btn_manual, self.btn_auto])
        if hasattr(self, 'btn_scan_start'):
            all_buttons.extend([self.btn_scan_start, self.btn_scan_stop, self.btn_manual_capture, self.btn_send_images])
        if hasattr(self, 'btn_set_point'):
            all_buttons.append(self.btn_set_point)
        for btn in all_buttons:
            btn.setStyleSheet(btn.styleSheet() + button_style)

    def fix_button_colors(self):
        self.btn_stop.setStyleSheet("""
            QPushButton {background-color: #e74c3c; color: white; font-weight: bold; border-radius: 6px;}
            QPushButton:disabled {background-color: #c0392b; color: white;}
        """)
        self.btn_servo_reset.setStyleSheet("""
            QPushButton {background-color: #f39c12; color: white; font-weight: bold; border-radius: 6px;}
            QPushButton:disabled {background-color: #e67e22; color: white;}
        """)
        if hasattr(self, 'btn_manual_capture'):
            self.btn_manual_capture.setStyleSheet("""
                QPushButton {background-color: #2ecc71; color: white; font-weight: bold; border-radius: 6px;}
                QPushButton:disabled {background-color: #bdc3c7; color: #7f8c8d;}
            """)

    def init_buttons(self):
        self.btn_connect.setEnabled(True)
        self.btn_disconnect.setEnabled(False)
        self.set_motion_controls_enabled(True)
        self.set_scan_controls_enabled(True)
        if hasattr(self, 'btn_scan_stop'):
            self.btn_scan_stop.setEnabled(False)
        if hasattr(self, 'btn_manual_capture'):
            self.btn_manual_capture.setEnabled(False)
        if hasattr(self, 'btn_send_images'):
            self.btn_send_images.setEnabled(True)

    def bind_all_functions(self):
        self.btn_connect.clicked.connect(self.connect_car)
        self.btn_disconnect.clicked.connect(self.disconnect_car)
        self.btn_forward.clicked.connect(lambda: self.send("A"))
        self.btn_backward.clicked.connect(lambda: self.send("B"))
        self.btn_left.clicked.connect(lambda: self.send("C"))
        self.btn_right.clicked.connect(lambda: self.send("D"))
        self.btn_stop.clicked.connect(lambda: self.send("E"))
        self.btn_servo_left.clicked.connect(self.servo_left)
        self.btn_servo_right.clicked.connect(self.servo_right)
        self.btn_servo_up.clicked.connect(self.servo_up)
        self.btn_servo_down.clicked.connect(self.servo_down)
        self.btn_servo_reset.clicked.connect(lambda: self.send_raw("SERVO:RESET"))
        if hasattr(self, 'btn_scan_start'):
            self.btn_scan_start.clicked.connect(self.start_auto_scan)
            self.btn_scan_stop.clicked.connect(self.stop_auto_scan)
        if hasattr(self, 'btn_manual_capture'):
            self.btn_manual_capture.clicked.connect(self.manual_capture)
        if hasattr(self, 'btn_send_images'):
            self.btn_send_images.clicked.connect(self.send_images_to_server)

    # ===================== 云台控制 =====================
    def servo_left(self):
        try:
            angle = int(self.edit_servo_h_angle.text().strip())
            cmd = f"SERVO:H:{angle}:LEFT"
            self.send_raw(cmd, desc=f"云台左转{angle}°")
            self.current_h_angle = max(0.0, min(180.0, self.current_h_angle - angle))
        except:
            self.log("⚠️ 请输入有效数字（水平角度）")

    def servo_right(self):
        try:
            angle = int(self.edit_servo_h_angle.text().strip())
            cmd = f"SERVO:H:{angle}:RIGHT"
            self.send_raw(cmd, desc=f"云台右转{angle}°")
            self.current_h_angle = max(0.0, min(180.0, self.current_h_angle + angle))
        except:
            self.log("⚠️ 请输入有效数字（水平角度）")

    def servo_up(self):
        try:
            angle = int(self.edit_servo_v_angle.text().strip())
            cmd = f"SERVO:V:{angle}:UP"
            self.send_raw(cmd, desc=f"云台上转{angle}°")
            self.current_v_angle = max(0.0, min(90.0, self.current_v_angle + angle))
        except:
            self.log("⚠️ 请输入有效数字（垂直角度）")

    def servo_down(self):
        try:
            angle = int(self.edit_servo_v_angle.text().strip())
            cmd = f"SERVO:V:{angle}:DOWN"
            self.send_raw(cmd, desc=f"云台下转{angle}°")
            self.current_v_angle = max(0.0, min(90.0, self.current_v_angle - angle))
        except:
            self.log("⚠️ 请输入有效数字（垂直角度）")

    # ===================== 自动扫描控制 =====================
    def set_scan_controls_enabled(self, enabled):
        if not hasattr(self, 'btn_scan_start'):
            return
        scan_controls = [
            self.edit_point_num, self.btn_set_point,
            self.edit_servo_h_init, self.edit_servo_v_init, self.edit_servo_step,
            self.btn_scan_start
        ]
        for ctrl in scan_controls:
            try:
                ctrl.setEnabled(enabled)
            except RuntimeError:
                pass
        try:
            self.btn_scan_stop.setEnabled(not enabled)
        except RuntimeError:
            pass
        if hasattr(self, 'btn_manual_capture'):
            try:
                self.btn_manual_capture.setEnabled(enabled and self.tcp_socket is not None and self.video_worker is not None and self.video_worker.original_frame is not None)
            except RuntimeError:
                pass
        if hasattr(self, 'btn_send_images'):
            try:
                self.btn_send_images.setEnabled(enabled and not self.scan_running)
            except RuntimeError:
                pass

    def set_motion_controls_enabled(self, enabled):
        motion_btns = [
            self.btn_forward, self.btn_backward, self.btn_left, self.btn_right, self.btn_stop,
            self.btn_servo_up, self.btn_servo_down, self.btn_servo_left, self.btn_servo_right, self.btn_servo_reset
        ]
        for btn in motion_btns:
            try:
                btn.setEnabled(enabled)
            except RuntimeError:
                pass

    def set_auto_trace_enabled(self, enabled):
        pass

    def calculate_total_rounds(self, v_init, step):
        if step <= 0:
            return 1
        total = 1
        current_v = v_init
        while True:
            next_v = current_v + step
            if abs(next_v - 90.0) < 0.001:
                total += 1
                break
            elif next_v > 90.0:
                total += 1
                break
            else:
                current_v = next_v
                total += 1
        return total

    def start_auto_scan(self):
        if self.active_task_order_serial is None:
            QMessageBox.warning(self, "警告", "请先加载工单并点击\"开始任务\"！")
            return
        if not hasattr(self, 'btn_scan_start'):
            return
        try:
            h_init = float(self.edit_servo_h_init.text().strip()) if self.edit_servo_h_init.text().strip() else 90.0
            v_init = float(self.edit_servo_v_init.text().strip()) if self.edit_servo_v_init.text().strip() else 0.0
            step = int(self.edit_servo_step.text().strip()) if self.edit_servo_step.text().strip() else 10
            num = int(self.edit_point_num.text().strip()) if self.edit_point_num.text().strip() else 1
            if not (1 <= num <= 9):
                self.log("⚠️ 途径点数量必须在1-9之间！")
                return
            if not (0 <= h_init <= 180):
                self.log("⚠️ 初始水平角度必须在0-180之间！")
                return
            if not (0 <= v_init <= 90):
                self.log("⚠️ 初始垂直角度必须在0-90之间！")
                return
            if not (1 <= step <= 90):
                self.log("⚠️ 垂直步长必须在1-90之间！")
                return
            total_rounds = self.calculate_total_rounds(v_init, step)
            self.send_raw(f"SET{num}", desc=f"设置途径点{num}个")
            cmd = f"SCAN:{h_init:.1f}:{v_init:.1f}:{step}:{total_rounds}"
            self.send_raw(cmd)
            self.scan_running = True
            self.set_scan_controls_enabled(False)
        except ValueError:
            self.log("⚠️ 请输入有效的数字！")

    def stop_auto_scan(self):
        if self.scan_running:
            self.send_raw("SCAN_STOP")

    # ===================== 截图功能 =====================
    def manual_capture(self):
        if self.active_task_order_serial is None:
            QMessageBox.warning(self, "警告", "请先加载工单并点击\"开始任务\"！")
            return
        self.log("📸 触发手动截图")
        self.save_capture(is_manual=True)

    def save_capture(self, node_name=None, v_angle=None, h_angle=None, is_manual=False):
        if self.video_worker is None or self.video_worker.original_frame is None:
            self.log("⚠️ 没有可用的视频帧，无法截图")
            return False
        if self.active_task_order_serial is None:
            self.log("⚠️ 没有活动工单，无法保存截图（请先开始任务）")
            return False
        illegal_chars = ['<', '>', ':', '"', '/', '\\', '|', '?', '*']
        if node_name:
            for char in illegal_chars:
                node_name = node_name.replace(char, '_')
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        order_prefix = f"工单{self.active_task_order_serial}"
        if is_manual:
            filename = f"{order_prefix}_垂直{self.current_v_angle:.1f}度_水平{self.current_h_angle:.1f}度_{timestamp}.jpg"
            filepath = os.path.join(MANUAL_CAPTURE_PATH, filename)
            log_msg = f"📸 手动截图已保存：{filepath}"
        else:
            filename = f"{order_prefix}_{node_name}_垂直{v_angle:.1f}度_水平{h_angle:.1f}度_{timestamp}.jpg"
            filepath = os.path.join(AUTO_CAPTURE_PATH, filename)
            log_msg = f"📸 自动截图已保存：{filepath}"
        max_retries = 3
        for retry in range(max_retries):
            try:
                success = cv2.imwrite(filepath, self.video_worker.original_frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
                if success and os.path.exists(filepath) and os.path.getsize(filepath) > 1024:
                    self.log(log_msg)
                    return True
                else:
                    raise Exception("文件大小异常")
            except Exception as e:
                self.log(f"⚠️ 截图保存失败（重试{retry+1}/{max_retries}）：{str(e)}")
                time.sleep(0.1)
        self.log(f"❌ 截图保存失败，已重试{max_retries}次：{filepath}")
        return False

    # ===================== 发送图片到服务器 =====================
    def send_images_to_server(self):
        if self.active_task_order_serial is None:
            QMessageBox.warning(self, "警告", "请先加载工单并点击\"开始任务\"！")
            return
        if not hasattr(self, 'edit_wall_id'):
            QMessageBox.warning(self, "功能不可用", "请更新 UI 文件后使用图片发送功能")
            return
        wall_id = self.edit_wall_id.text().strip()
        if not wall_id:
            QMessageBox.warning(self, "警告", "请输入墙面标识！")
            return
        reply = QMessageBox.question(self, "确认",
            f"将发送工单 {self.active_task_order_serial} 的所有截图，请确认您已经：\n1. 断开了树莓派的WiFi\n2. 连接到了与服务器相同的网络\n\n是否继续发送？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        self.btn_send_images.setEnabled(False)
        if hasattr(self, 'progress_bar'):
            self.progress_bar.setVisible(True)
            self.progress_bar.setValue(0)
        self.image_sender = ImageSenderThread(AUTO_CAPTURE_PATH, MANUAL_CAPTURE_PATH, wall_id, self.active_task_order_serial)
        self.image_sender.progress_updated.connect(self.on_send_progress)
        self.image_sender.result_received.connect(self.on_detection_result)
        self.image_sender.send_finished.connect(self.on_send_finished)
        self.image_sender.log_signal.connect(self.log)
        self.image_sender.start()

    def on_send_progress(self, current, total):
        if hasattr(self, 'progress_bar'):
            self.progress_bar.setMaximum(total)
            self.progress_bar.setValue(current)

    def on_detection_result(self, result):
        pass

    def on_send_finished(self, success, message):
        if hasattr(self, 'progress_bar'):
            self.progress_bar.setVisible(False)
        if hasattr(self, 'btn_send_images'):
            self.btn_send_images.setEnabled(True)
        if success:
            QMessageBox.information(self, "成功", message)
            self.log(f"✅ {message}")
        else:
            QMessageBox.critical(self, "失败", message)
            self.log(f"❌ {message}")

    # ===================== TCP数据接收处理 =====================
    def on_tcp_data_received(self, data):
        if data.startswith("NODE:"):
            node_code = data[5:]
            self.log(f"📥 收到节点数据：{data}")
            if node_code == "0x19":
                self.log("📍 到达起点")
            elif node_code == "0x20":
                self.log("🏁 到达终点")
            elif node_code.startswith("0x2") and len(node_code) == 4:
                point_num = int(node_code[3], 16)
                self.log(f"📍 到达途径点 {point_num}")
        elif data.startswith("SCAN:"):
            status = data[5:]
            self.log(f"📥 收到扫描状态：{data}")
            if status == "COMPLETE":
                self.log("✅ 所有自动扫描任务完成！")
                self.scan_running = False
                self.set_scan_controls_enabled(True)
                self.log("💡 提示：现在可以断开树莓派WiFi，连接到服务器网络后点击\"发送图片到服务器\"")
            elif status == "STOPPED":
                self.log("⏹️ 自动扫描已停止")
                self.scan_running = False
                self.set_scan_controls_enabled(True)
            elif status == "GOING":
                self.log("🚗 开始去程扫描")
            elif status == "RETURNING":
                self.log("🚗 开始回程扫描")
        elif data.startswith("CAPTURE:AUTO:"):
            parts = data.split(':')
            if len(parts) >= 5:
                node_name = parts[2]
                try:
                    v_angle = float(parts[3])
                    h_angle = float(parts[4])
                    self.current_v_angle = v_angle
                    self.current_h_angle = h_angle
                    self.log(f"📥 收到自动截图指令：{node_name}（垂直{v_angle:.1f}°，水平{h_angle:.1f}°）")
                    self.save_capture(node_name, v_angle, h_angle, is_manual=False)
                except ValueError:
                    self.log(f"⚠️ 自动截图指令角度解析失败：{data}")
            else:
                node_name = data[13:]
                self.log(f"📥 收到自动截图指令：{node_name}（兼容旧格式）")
                self.save_capture(node_name, self.current_v_angle, self.current_h_angle, is_manual=False)
        else:
            self.log(f"📥 收到小车数据：{data}")

    def on_tcp_connection_lost(self):
        self.log("⚠️ TCP连接已断开")
        self.scan_running = False
        self.disconnect_car()

    def on_capture_ready(self, ready):
        if hasattr(self, 'btn_manual_capture'):
            self.btn_manual_capture.setEnabled(ready and self.tcp_socket is not None)
        if not ready:
            self.log("⚠️ 视频流暂时不可用，截图功能已禁用")

    # ===================== 网络连接/断开 =====================
    def connect_car(self):
        try:
            self.log("🔄 正在清理旧连接...")
            if self.video_worker:
                self.video_worker.stop()
                self.video_worker.wait(3000)
                self.video_worker = None
                self.label_video.setText("等待视频连接...")
            if self.tcp_receiver:
                self.tcp_receiver.stop()
                self.tcp_receiver.wait(3000)
                self.tcp_receiver = None
            if self.tcp_socket:
                try:
                    self.tcp_socket.shutdown(socket.SHUT_RDWR)
                except:
                    pass
                try:
                    self.tcp_socket.close()
                except:
                    pass
                self.tcp_socket = None
            gc.collect()
            time.sleep(0.5)
            self.log("🔌 正在建立TCP连接...")
            self.tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.tcp_socket.settimeout(5)
            self.tcp_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self.tcp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            self.tcp_socket.connect((CAR_IP, CAR_PORT))
            self.btn_connect.setEnabled(False)
            self.btn_disconnect.setEnabled(True)
            self.conn_status_label.setText("已连接")
            self.conn_status_label.setStyleSheet("""
                QLabel {
                    font-size: 14px;
                    font-weight: bold;
                    color: #2ecc71;
                    padding: 8px;
                    border: 1px solid #2ecc71;
                    border-radius: 6px;
                }
            """)
            self.log(f"✅ TCP连接成功：{CAR_IP}:{CAR_PORT}")
            self.tcp_receiver = TcpReceiverThread(self.tcp_socket)
            self.tcp_receiver.data_received.connect(self.on_tcp_data_received)
            self.tcp_receiver.connection_lost.connect(self.on_tcp_connection_lost)
            self.tcp_receiver.start()
            self.log("✅ TCP接收线程已启动")
            self.log("📹 正在连接视频流...")
            self.video_worker = VideoWorker()
            self.video_worker.frame_updated.connect(self.update_video)
            self.video_worker.log_signal.connect(self.log)
            self.video_worker.capture_ready.connect(self.on_capture_ready)
            self.video_worker.start()
            self.scan_running = False
            self.current_v_angle = 90.0
            self.current_h_angle = 90.0
            self.set_motion_controls_enabled(True)
            self.set_scan_controls_enabled(True)
            if hasattr(self, 'btn_manual_capture'):
                self.btn_manual_capture.setEnabled(True)
            self.log("✅ 所有连接已建立，小车准备就绪")
        except Exception as e:
            self.log(f"❌ 连接失败：{str(e)}")
            self.disconnect_car()

    def disconnect_car(self):
        self.log("🔌 正在断开连接...")
        if self.scan_running:
            try:
                self.send_raw("SCAN_STOP")
            except:
                pass
            self.scan_running = False
        if self.tcp_receiver:
            self.tcp_receiver.stop()
            self.tcp_receiver.wait(3000)
            self.tcp_receiver = None
        if self.video_worker:
            self.video_worker.stop()
            self.video_worker.wait(3000)
            self.video_worker = None
            self.label_video.setText("等待视频连接...")
        if self.tcp_socket:
            try:
                self.tcp_socket.shutdown(socket.SHUT_RDWR)
            except:
                pass
            try:
                self.tcp_socket.close()
            except:
                pass
            self.tcp_socket = None

        self.btn_connect.setEnabled(True)
        self.btn_disconnect.setEnabled(False)
        if self.conn_status_label:
            self.conn_status_label.setText("未连接")
            self.conn_status_label.setStyleSheet("""
                QLabel {
                    font-size: 14px;
                    font-weight: bold;
                    color: #e74c3c;
                    padding: 8px;
                    border: 1px solid #e74c3c;
                    border-radius: 6px;
                }
            """)
        if not self._is_closing:
            self.set_motion_controls_enabled(True)
            self.set_scan_controls_enabled(True)
        if hasattr(self, 'btn_manual_capture'):
            try:
                self.btn_manual_capture.setEnabled(False)
            except RuntimeError:
                pass
        gc.collect()
        self.log("❌ 已完全断开连接")

    def send(self, cmd):
        if not self.tcp_socket:
            self.log("⚠️ 请先连接！")
            return
        try:
            full_cmd = f"ON{cmd}"
            desc = CMD_DESC.get(cmd, "未知指令")
            self.tcp_socket.send(full_cmd.encode())
            self.log(f"📤 发送：{full_cmd}（{desc}）")
        except:
            self.log("❌ 发送失败")

    def send_raw(self, data, desc=None):
        if not self.tcp_socket:
            self.log("⚠️ 请先连接！")
            return
        try:
            self.tcp_socket.send(data.encode())
            if desc:
                self.log(f"📤 发送：{data}（{desc}）")
            else:
                if data == "SERVO:RESET":
                    self.log(f"📤 发送：{data}（云台复位）")
                    self.current_v_angle = 90.0
                    self.current_h_angle = 90.0
                elif data == "SCAN_STOP":
                    self.log(f"📤 发送：{data}（停止自动扫描）")
                elif data.startswith("SET"):
                    num = data[3:]
                    self.log(f"📤 发送：{data}（设置途径点{num}个）")
                elif data.startswith("SCAN:"):
                    self.log(f"📤 发送：{data}（启动自动扫描）")
                else:
                    self.log(f"📤 发送：{data}")
        except:
            self.log("❌ 发送失败")

    def update_video(self, pix):
        self.label_video.setPixmap(pix.scaled(
            self.label_video.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def log(self, msg):
        self.text_log.append(msg)
        self.text_log.verticalScrollBar().setValue(self.text_log.verticalScrollBar().maximum())

    def closeEvent(self, e):
        self._is_closing = True
        if self.image_sender and self.image_sender.isRunning():
            self.image_sender.stop()
        self.disconnect_car()
        e.accept()

    # ===================== 多页面导航 =====================
    def setup_navigation_and_pages(self):
        original_central = self.centralWidget
        new_central = QWidget()
        new_layout = QHBoxLayout(new_central)
        new_layout.setContentsMargins(0, 0, 0, 0)
        new_layout.setSpacing(0)

        self.nav_widget = QWidget()
        self.nav_widget.setObjectName("navWidget")
        self.nav_widget.setStyleSheet("""
            QWidget#navWidget { background-color: #1e1e1e; border-right: 1px solid #3c3c3c; }
        """)
        nav_layout = QVBoxLayout(self.nav_widget)
        nav_layout.setSpacing(8)
        nav_layout.setContentsMargins(10, 30, 10, 30)
        nav_layout.setAlignment(Qt.AlignTop)

        self.nav_buttons = []
        btn_names = ["首页", "用户身份管理", "工单管理", "历史数据", "报告查看"]
        self.page_index_map = {"首页": 0, "用户身份管理": 1, "工单管理": 2, "历史数据": 3, "报告查看": 4}
        for name in btn_names:
            btn = QPushButton(name)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFixedHeight(50)
            btn.setStyleSheet("""
                QPushButton {
                    text-align: left;
                    padding-left: 20px;
                    background-color: #000000;
                    color: #ffffff;
                    border: none;
                    border-radius: 8px;
                    font-size: 14px;
                    font-weight: 500;
                }
                QPushButton:hover { background-color: #2c2c2c; }
            """)
            btn.clicked.connect(lambda checked, n=name: self.switch_page(n))
            nav_layout.addWidget(btn)
            self.nav_buttons.append(btn)
        nav_layout.addStretch()

        self.stacked_widget = QStackedWidget()
        home_page = QWidget()
        home_page.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        home_layout2 = QVBoxLayout(home_page)
        home_layout2.setContentsMargins(0, 0, 0, 0)
        home_layout2.setSpacing(0)
        original_central.setParent(None)
        original_central.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        original_central.show()
        home_layout2.addWidget(original_central, 1)
        self.stacked_widget.addWidget(home_page)

        pages = ["用户身份管理", "工单管理", "历史数据", "报告查看"]
        for title in pages:
            if title == "用户身份管理":
                page = UserManagementWidget()
            elif title == "工单管理":
                page = WorkOrderWidget()
            elif title == "历史数据":
                page = HistoryWidget()
            else:
                page = ReportViewWidget()
            self.stacked_widget.addWidget(page)

        new_layout.addWidget(self.nav_widget, 15)
        new_layout.addWidget(self.stacked_widget, 85)
        self.setCentralWidget(new_central)
        self.switch_page("首页")
        self.resize(1200, 750)

    def switch_page(self, page_name):
        idx = self.page_index_map.get(page_name, 0)
        self.stacked_widget.setCurrentIndex(idx)
        for btn in self.nav_buttons:
            if btn.text() == page_name:
                btn.setStyleSheet("""
                    QPushButton {
                        text-align: left;
                        padding-left: 20px;
                        background-color: #3498db;
                        color: white;
                        border: none;
                        border-radius: 8px;
                        font-size: 14px;
                        font-weight: bold;
                    }
                    QPushButton:hover { background-color: #2980b9; }
                """)
            else:
                btn.setStyleSheet("""
                    QPushButton {
                        text-align: left;
                        padding-left: 20px;
                        background-color: #000000;
                        color: #ffffff;
                        border: none;
                        border-radius: 8px;
                        font-size: 14px;
                        font-weight: 500;
                    }
                    QPushButton:hover { background-color: #2c2c2c; }
                """)
        current_widget = self.stacked_widget.currentWidget()
        if current_widget:
            current_widget.updateGeometry()
            current_widget.repaint()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = CarController()
    win.show()
    sys.exit(app.exec())