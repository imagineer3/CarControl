import sys
import os
import cv2
import socket
import time
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
MODEL_PATH = "C:/Users/11/Desktop/car_detect/best.pt"
CAR_IP = "192.168.1.1"
CAR_PORT = 2001
VIDEO_URL = f"http://{CAR_IP}:8080/?action=stream"
PRINT_INTERVAL = 2.0
IMGSZ = 640

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

# ===================== 视频+YOLO线程 =====================
class VideoWorker(QThread):
    frame_updated = Signal(QPixmap)
    log_signal = Signal(str)

    def __init__(self):
        super().__init__()
        self.running = True
        self.fps = 0.0
        self.frame_count = 0
        self.start_time = time.time()
        self.model = None
        self.last_inference_time_ms = 0.0
        self.last_print_time = time.time()
        try:
            self.model = YOLO(MODEL_PATH)
            self.log_signal.emit("✅ YOLO模型加载成功")
        except Exception as e:
            self.log_signal.emit(f"❌ 模型加载失败：{str(e)}")

    def run(self):
        os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "timeout;5000000"
        cap = self._create_capture()
        if cap is None:
            return
        self.log_signal.emit("✅ 视频+YOLO已启动")
        while self.running:
            if cap is None or not cap.isOpened():
                self.log_signal.emit("⚠️ 视频流断开，5秒重试...")
                time.sleep(5)
                cap = self._create_capture()
                if cap is None:
                    continue
            ret, frame = cap.read()
            if not ret:
                self.log_signal.emit("⚠️ 读取帧失败，尝试重连...")
                cap.release()
                cap = None
                continue
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
                    results = self.model(frame, conf=0.5, imgsz=IMGSZ, verbose=False)
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
            self.frame_updated.emit(QPixmap.fromImage(qt_img))
            if time.time() - self.last_print_time >= PRINT_INTERVAL and results is not None:
                self.print_detections(results)
                self.last_print_time = time.time()
        if cap is not None:
            cap.release()
        self.log_signal.emit("⏹️ 视频流已关闭")

    def _create_capture(self):
        cap = cv2.VideoCapture(VIDEO_URL)
        if not cap.isOpened():
            self.log_signal.emit("❌ 无法打开视频流")
            return None
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        return cap

    def print_detections(self, results):
        boxes = results[0].boxes
        if boxes is None or len(boxes) == 0:
            self.log_signal.emit("\n======== 检测详情 ========")
            self.log_signal.emit("当前无检测目标")
            self.log_signal.emit(f"FPS: {self.fps:.1f}")
            self.log_signal.emit(f"推理耗时: {self.last_inference_time_ms:.1f} ms")
            self.log_signal.emit("==========================\n")
            return
        num_objects = len(boxes)
        names = results[0].names
        infos = []
        for box in boxes:
            cls_id = int(box.cls[0])
            conf = float(box.conf[0])
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            w = x2 - x1
            h = y2 - y1
            class_name = names[cls_id] if cls_id in names else str(cls_id)
            infos.append((class_name, conf, (x1, y1, x2, y2), w, h))
        self.log_signal.emit("\n======== 检测详情 ========")
        self.log_signal.emit(f"检测到目标数量: {num_objects}")
        show_limit = min(len(infos), 10)
        for i in range(show_limit):
            cls, conf, (x1, y1, x2, y2), w, h = infos[i]
            self.log_signal.emit(f"  {i+1}: {cls} 置信度:{conf:.2f} "
                  f"框:[{x1:.0f},{y1:.0f},{x2:.0f},{y2:.0f}] "
                  f"尺寸:{w:.0f}x{h:.0f}px")
        if num_objects > 10:
            self.log_signal.emit(f"  ... 还有 {num_objects - 10} 个目标未显示")
        self.log_signal.emit(f"FPS: {self.fps:.1f}")
        self.log_signal.emit(f"推理耗时: {self.last_inference_time_ms:.1f} ms")
        self.log_signal.emit("==========================\n")

    def stop(self):
        self.running = False
        self.wait()

# ===================== 主窗口 =====================
class CarController(QMainWindow, Ui_MainWindow):
    def __init__(self):
        super().__init__()
        self.setupUi(self)
        self.tcp_socket = None
        self.video_worker = None
        self.current_order_id = None
        self.current_order_serial = None
        self.manual_mode = False

        self.fix_button_colors()
        self.adjust_button_sizes()
        self.modify_bottom_layout()
        self.add_task_control_group()
        self.init_buttons()
        self.bind_all_functions()
        self.setup_navigation_and_pages()

    def modify_bottom_layout(self):
        log_container = QWidget()
        log_vbox = QVBoxLayout(log_container)
        log_vbox.setContentsMargins(0, 0, 0, 0)
        log_vbox.setSpacing(5)
        log_label = QLabel("操作日志")
        log_label.setStyleSheet("font-weight: bold; font-size: 13px;")
        log_vbox.addWidget(log_label)
        log_vbox.addWidget(self.text_log)
        idx = self.bottomLayout.indexOf(self.text_log)
        if idx >= 0:
            self.bottomLayout.insertWidget(idx, log_container)
            self.bottomLayout.removeWidget(self.text_log)
        else:
            self.bottomLayout.insertWidget(0, log_container)
        self.bottomLayout.setStretchFactor(log_container, 3)
        self.bottomLayout.setStretchFactor(self.buttonLayout, 1)

        btn_style = """
            QPushButton {
                font-size: 14px;
                padding: 6px;
                min-width: 80px;
                min-height: 40px;
                border-radius: 6px;
            }
        """
        self.btn_connect.setStyleSheet(self.btn_connect.styleSheet() + btn_style)
        self.btn_disconnect.setStyleSheet(self.btn_disconnect.styleSheet() + btn_style)

    def adjust_button_sizes(self):
        button_style = """
            QPushButton {
                font-size: 12px;
                padding: 6px;
                min-width: 70px;
                min-height: 30px;
                border-radius: 4px;
            }
        """
        all_buttons = [
            self.btn_forward, self.btn_backward, self.btn_left, self.btn_right, self.btn_stop,
            self.btn_servo_up, self.btn_servo_down, self.btn_servo_left, self.btn_servo_right, self.btn_servo_reset,
            self.btn_trace_start, self.btn_trace_stop, self.btn_set_point,
        ]
        for btn in all_buttons:
            btn.setStyleSheet(btn.styleSheet() + button_style)

    def get_db_connection(self):
        try:
            conn = pymysql.connect(
                host=DB_CONFIG["host"], port=DB_CONFIG["port"],
                user=DB_CONFIG["user"], password=DB_CONFIG["password"],
                database=DB_CONFIG["database"], charset="utf8mb4"
            )
            return conn
        except Exception as e:
            self.log(f"❌ 数据库连接失败：{str(e)}")
            return None

    def add_task_control_group(self):
        control_layout = self.controlLayout

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

        # 手动/自动控制按钮：使用相同的拉伸策略和样式
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
        control_layout.addWidget(self.task_group)

        control_layout.setStretch(0, 1)
        control_layout.setStretch(1, 1)
        control_layout.setStretch(2, 1)
        control_layout.setStretch(3, 3)

        self.btn_load_order.clicked.connect(self.load_order_dialog)
        self.btn_cancel_order.clicked.connect(self.cancel_order)
        self.btn_start_task.clicked.connect(self.start_task)
        self.btn_complete_task.clicked.connect(self.complete_task)
        self.btn_manual.clicked.connect(self.set_manual_mode)
        self.btn_auto.clicked.connect(self.set_auto_mode)

        for btn in [self.btn_load_order, self.btn_cancel_order, self.btn_start_task,
                    self.btn_complete_task, self.btn_manual, self.btn_auto]:
            btn.setEnabled(True)

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
                SELECT order_id, building_code, order_status, executor_name, plan_time
                FROM inspect_work_order
                WHERE order_status != '已完成'
                ORDER BY order_id
            """
            cursor.execute(sql)
            rows = cursor.fetchall()
            cursor.close()
            if not rows:
                QMessageBox.information(self, "提示", "当前没有未完成的工单")
                return

            dialog = QDialog(self)
            dialog.setWindowTitle("选择工单")
            dialog.setMinimumWidth(600)
            layout = QVBoxLayout(dialog)

            table = QTableWidget()
            table.setColumnCount(4)
            table.setHorizontalHeaderLabels(["建筑代号", "工单状态", "执行人", "计划时间"])
            table.setSelectionBehavior(QAbstractItemView.SelectRows)
            table.setSelectionMode(QAbstractItemView.SingleSelection)
            table.setEditTriggers(QAbstractItemView.NoEditTriggers)
            table.horizontalHeader().setStretchLastSection(True)
            table.setRowCount(len(rows))
            for i, row in enumerate(rows):
                for j, val in enumerate(row[1:], start=0):
                    table.setItem(i, j, QTableWidgetItem(str(val) if val else ""))
                id_item = QTableWidgetItem()
                id_item.setData(Qt.UserRole, row[0])
                table.setItem(i, 0, id_item)
            layout.addWidget(table)

            button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
            layout.addWidget(button_box)

            def on_accept():
                selected = table.currentRow()
                if selected < 0:
                    QMessageBox.warning(dialog, "提示", "请先选择一个工单")
                    return
                order_id = table.item(selected, 0).data(Qt.UserRole)
                self.current_order_id = order_id
                serial_num = f"{selected+1:03d}"
                self.current_order_serial = serial_num
                row_data = rows[selected]
                building = row_data[1]
                status = row_data[2]
                executor = row_data[3] if row_data[3] else "未指派"
                plan_time = row_data[4]
                if plan_time and isinstance(plan_time, datetime):
                    plan_time = plan_time.strftime("%Y-%m-%d %H:%M:%S")
                elif not plan_time:
                    plan_time = "未设置"
                self.update_order_display(serial_num, building, status, executor, plan_time)
                self.log(f"📋 已加载工单：{serial_num} {building} {status} {executor}")
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
            self.update_order_display(None, None, None, None, None)
            QMessageBox.information(self, "成功", "工单已完成")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"完成任务失败：{str(e)}")
        finally:
            conn.close()

    def set_motion_controls_enabled(self, enabled):
        motion_btns = [
            self.btn_forward, self.btn_backward, self.btn_left, self.btn_right, self.btn_stop,
            self.btn_servo_up, self.btn_servo_down, self.btn_servo_left, self.btn_servo_right, self.btn_servo_reset
        ]
        for btn in motion_btns:
            btn.setEnabled(enabled)

    def set_auto_trace_enabled(self, enabled):
        trace_btns = [self.btn_trace_start, self.btn_trace_stop, self.btn_set_point]
        for btn in trace_btns:
            btn.setEnabled(enabled)

    # ----- 原有功能 -----
    def fix_button_colors(self):
        self.btn_stop.setStyleSheet("""
            QPushButton {background-color: #e74c3c; color: white; font-weight: bold; border-radius: 6px;}
            QPushButton:disabled {background-color: #c0392b; color: white;}
        """)
        self.btn_servo_reset.setStyleSheet("""
            QPushButton {background-color: #f39c12; color: white; font-weight: bold; border-radius: 6px;}
            QPushButton:disabled {background-color: #e67e22; color: white;}
        """)

    def init_buttons(self):
        self.btn_connect.setEnabled(True)
        self.btn_disconnect.setEnabled(False)
        self.set_motion_controls_enabled(False)
        self.set_auto_trace_enabled(True)   # 未连接时循迹按钮可用（点击会提示请先连接）

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
        self.btn_trace_start.clicked.connect(lambda: self.send_raw("TR"))
        self.btn_trace_stop.clicked.connect(lambda: self.send("E"))
        self.btn_set_point.clicked.connect(self.set_point)

    def servo_left(self):
        try:
            angle = int(self.edit_servo_h_angle.text().strip())
            cmd = f"SERVO:H:{angle}:LEFT"
            self.send_raw(cmd, desc=f"云台左转{angle}°")
        except:
            self.log("⚠️ 请输入有效数字（水平角度）")

    def servo_right(self):
        try:
            angle = int(self.edit_servo_h_angle.text().strip())
            cmd = f"SERVO:H:{angle}:RIGHT"
            self.send_raw(cmd, desc=f"云台右转{angle}°")
        except:
            self.log("⚠️ 请输入有效数字（水平角度）")

    def servo_up(self):
        try:
            angle = int(self.edit_servo_v_angle.text().strip())
            cmd = f"SERVO:V:{angle}:UP"
            self.send_raw(cmd, desc=f"云台上转{angle}°")
        except:
            self.log("⚠️ 请输入有效数字（垂直角度）")

    def servo_down(self):
        try:
            angle = int(self.edit_servo_v_angle.text().strip())
            cmd = f"SERVO:V:{angle}:DOWN"
            self.send_raw(cmd, desc=f"云台下转{angle}°")
        except:
            self.log("⚠️ 请输入有效数字（垂直角度）")

    def log(self, msg):
        self.text_log.append(msg)
        self.text_log.verticalScrollBar().setValue(self.text_log.verticalScrollBar().maximum())

    def connect_car(self):
        try:
            self.tcp_socket = socket.socket()
            self.tcp_socket.settimeout(5)
            self.tcp_socket.connect((CAR_IP, CAR_PORT))
            self.btn_connect.setEnabled(False)
            self.btn_disconnect.setEnabled(True)
            self.log(f"✅ 连接成功：{CAR_IP}:{CAR_PORT}")
            self.video_worker = VideoWorker()
            self.video_worker.frame_updated.connect(self.update_video)
            self.video_worker.log_signal.connect(self.log)
            self.video_worker.start()
            if self.manual_mode:
                self.set_motion_controls_enabled(True)
                self.set_auto_trace_enabled(False)
            else:
                self.set_motion_controls_enabled(False)
                self.set_auto_trace_enabled(True)
        except Exception as e:
            self.log(f"❌ 连接失败：{str(e)}")

    def disconnect_car(self):
        if self.video_worker:
            self.video_worker.stop()
            self.video_worker = None
            self.label_video.setText("等待视频连接...")
        if self.tcp_socket:
            self.tcp_socket.close()
            self.tcp_socket = None
        self.btn_connect.setEnabled(True)
        self.btn_disconnect.setEnabled(False)
        self.set_motion_controls_enabled(False)
        self.set_auto_trace_enabled(True)
        self.log("❌ 已断开连接")

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
                elif data == "TR":
                    self.log(f"📤 发送：{data}（开始循迹）")
                elif data.startswith("SET"):
                    num = data[3:]
                    self.log(f"📤 发送：{data}（设置途径点{num}个）")
                else:
                    self.log(f"📤 发送：{data}")
        except:
            self.log("❌ 发送失败")

    def set_point(self):
        num = self.edit_point_num.text().strip()
        if num.isdigit() and 1 <= int(num) <= 9:
            self.send_raw(f"SET{num}", desc=f"设置途径点{num}个")
        else:
            self.log("⚠️ 输入1-9之间的数字！")

    def update_video(self, pix):
        self.label_video.setPixmap(pix.scaled(
            self.label_video.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def closeEvent(self, e):
        self.disconnect_car()
        e.accept()

    # ----- 左侧导航栏及多页面 -----
    def setup_navigation_and_pages(self):
        original_central = self.centralWidget
        new_central = QWidget()
        new_layout = QHBoxLayout(new_central)
        new_layout.setContentsMargins(0, 0, 0, 0)
        new_layout.setSpacing(0)

        self.nav_widget = QWidget()
        self.nav_widget.setObjectName("navWidget")
        self.nav_widget.setStyleSheet("""
            QWidget#navWidget {
                background-color: #1e1e1e;
                border-right: 1px solid #3c3c3c;
            }
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
                QPushButton:hover {
                    background-color: #2c2c2c;
                }
            """)
            btn.clicked.connect(lambda checked, n=name: self.switch_page(n))
            nav_layout.addWidget(btn)
            self.nav_buttons.append(btn)
        nav_layout.addStretch()

        self.stacked_widget = QStackedWidget()

        home_page = QWidget()
        home_page.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        home_layout = QVBoxLayout(home_page)
        home_layout.setContentsMargins(0, 0, 0, 0)
        home_layout.setSpacing(0)
        original_central.setParent(None)
        original_central.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        original_central.show()
        home_layout.addWidget(original_central, 1)
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
                    QPushButton:hover {
                        background-color: #2980b9;
                    }
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
                    QPushButton:hover {
                        background-color: #2c2c2c;
                    }
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