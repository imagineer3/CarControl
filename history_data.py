# -*- coding: utf-8 -*-
"""
历史数据界面 - 显示已完成工单列表，支持查看报告（按工单编号前缀查找）
"""

import sys
import os
import glob
import json
from PySide6.QtWidgets import *
from PySide6.QtCore import *
from PySide6.QtGui import QDesktopServices
import pymysql
from datetime import datetime

# ================== 数据库配置 ==================
DB_CONFIG = {
    "host": "localhost",
    "port": 3306,
    "database": "database",
    "user": "root",
    "password": "123456"
}
# ==============================================

# 报告保存路径：优先读取 report_view 保存的配置，否则使用程序目录下的 reports 文件夹
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

CONFIG_FILE = os.path.join(BASE_DIR, "report_config.json")

def load_report_dir():
    """加载报告目录（与 report_view 保持一致）"""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
                path = config.get("report_dir", "")
                if path and os.path.exists(path):
                    return path
        except:
            pass
    return os.path.join(BASE_DIR, "reports")

REPORT_DIR = load_report_dir()

class HistoryWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
        self.load_executor_list()   # 加载执行人列表
        self.load_data()

    def get_connection(self):
        try:
            conn = pymysql.connect(
                host=DB_CONFIG["host"], port=DB_CONFIG["port"],
                user=DB_CONFIG["user"], password=DB_CONFIG["password"],
                database=DB_CONFIG["database"], charset="utf8mb4"
            )
            return conn
        except Exception as e:
            QMessageBox.critical(self, "数据库错误", f"连接失败：{str(e)}")
            return None

    def setup_ui(self):
        layout = QVBoxLayout(self)

        # 筛选栏
        filter_layout = QHBoxLayout()
        self.building_combo = QComboBox()
        self.building_combo.addItem("全部")
        self.building_combo.addItems(["east", "south", "north", "west"])
        filter_layout.addWidget(QLabel("建筑代号:"))
        filter_layout.addWidget(self.building_combo)

        self.executor_combo = QComboBox()
        self.executor_combo.addItem("全部")
        filter_layout.addWidget(QLabel("执行人:"))
        filter_layout.addWidget(self.executor_combo)

        self.start_date = QDateEdit()
        self.start_date.setDate(QDate(2026, 5, 1))
        self.start_date.setCalendarPopup(True)
        self.start_date.setDisplayFormat("yyyy-MM-dd")
        self.start_date.setSpecialValueText("起始日期")
        filter_layout.addWidget(QLabel("完成时间:"))
        filter_layout.addWidget(self.start_date)

        self.end_date = QDateEdit()
        self.end_date.setDate(QDate(2026, 9, 1))
        self.end_date.setCalendarPopup(True)
        self.end_date.setDisplayFormat("yyyy-MM-dd")
        self.end_date.setSpecialValueText("结束日期")
        filter_layout.addWidget(self.end_date)

        self.search_btn = QPushButton("筛选")
        self.search_btn.clicked.connect(self.search)
        self.clear_btn = QPushButton("清除")
        self.clear_btn.clicked.connect(self.clear_search)
        filter_layout.addWidget(self.search_btn)
        filter_layout.addWidget(self.clear_btn)
        filter_layout.addStretch()
        layout.addLayout(filter_layout)

        # 数据表格
        self.table = QTableWidget()
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setStyleSheet("""
            QTableWidget {
                selection-background-color: #b8d9ff;
                selection-color: #000000;
            }
            QTableWidget::item:selected {
                background-color: #b8d9ff;
                color: #000000;
            }
        """)
        layout.addWidget(self.table)

        # ========== 工单详情显示区域（始终显示，未选中时空白） ==========
        self.detail_group = QGroupBox("历史工单详情")
        detail_layout = QFormLayout(self.detail_group)
        self.detail_labels = {}
        fields = ["工单编号", "建筑代号", "工单状态", "执行人", "计划时间", "完成时间", "创建时间", "备注"]
        for field in fields:
            label = QLabel("")
            label.setWordWrap(True)
            self.detail_labels[field] = label
            detail_layout.addRow(field + ":", label)

        # 报告文件只显示文件名，不加按钮（按钮放在下面）
        self.report_file_label = QLabel("")
        self.report_file_label.setWordWrap(True)
        detail_layout.addRow("报告文件:", self.report_file_label)

        layout.addWidget(self.detail_group)

        # 按钮栏（“查看报告”直接打开报告）
        btn_layout = QHBoxLayout()
        self.view_report_btn = QPushButton("查看报告")
        self.refresh_btn = QPushButton("刷新")
        btn_layout.addWidget(self.view_report_btn)
        btn_layout.addWidget(self.refresh_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # 事件绑定
        self.view_report_btn.clicked.connect(self.open_report_directly)
        self.refresh_btn.clicked.connect(self.load_data)
        self.table.itemSelectionChanged.connect(self.on_selection_changed)

        # 设置表格列
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(["工单编号", "建筑代号", "执行人", "计划时间", "完成时间", "创建时间", "备注"])
        self.table.setColumnWidth(0, 80)
        self.table.setColumnWidth(1, 100)
        self.table.setColumnWidth(2, 120)
        self.table.setColumnWidth(3, 140)
        self.table.setColumnWidth(4, 140)
        self.table.setColumnWidth(5, 140)
        self.table.setColumnWidth(6, 100)

        # 初始清空详情（显示空白）
        self.clear_detail()

    def load_executor_list(self):
        """加载已完成工单中的执行人列表到下拉框"""
        conn = self.get_connection()
        if not conn:
            return
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT DISTINCT executor_name 
                FROM inspect_work_order 
                WHERE order_status='已完成' 
                  AND executor_name IS NOT NULL 
                  AND executor_name != ''
                ORDER BY executor_name
            """)
            rows = cursor.fetchall()
            self.executor_combo.clear()
            self.executor_combo.addItem("全部")
            for row in rows:
                if row[0]:
                    self.executor_combo.addItem(row[0])
            cursor.close()
        except Exception as e:
            print(f"加载执行人列表失败：{e}")
        finally:
            conn.close()

    def load_data(self):
        building = self.building_combo.currentText()
        executor = self.executor_combo.currentText()
        start_date = self.start_date.date().toString("yyyy-MM-dd") if self.start_date.date().isValid() else ""
        end_date = self.end_date.date().toString("yyyy-MM-dd") if self.end_date.date().isValid() else ""

        conn = self.get_connection()
        if not conn:
            return
        try:
            cursor = conn.cursor()

            # 构建基础SQL：先生成全局连续编号（按 order_id 升序），并包含 order_status
            base_sql = """
                SELECT 
                    (@row_number := @row_number + 1) AS serial_num,
                    order_id,
                    building_code,
                    executor_name,
                    order_status,
                    plan_time,
                    finish_time,
                    create_time,
                    remark
                FROM inspect_work_order, (SELECT @row_number := 0) vars
                ORDER BY order_id
            """
            # 外层筛选已完成工单及条件
            sql = f"""
                SELECT serial_num, order_id, building_code, executor_name, plan_time, finish_time, create_time, remark
                FROM ({base_sql}) t
                WHERE t.order_status = '已完成'
            """
            params = []
            if building != "全部":
                sql += " AND building_code = %s"
                params.append(building)
            if executor != "全部":
                sql += " AND executor_name = %s"
                params.append(executor)
            if start_date:
                sql += " AND DATE(finish_time) >= %s"
                params.append(start_date)
            if end_date:
                sql += " AND DATE(finish_time) <= %s"
                params.append(end_date)
            # 按全局编号升序排序
            sql += " ORDER BY serial_num"

            cursor.execute(sql, params)
            rows = cursor.fetchall()
            self.table.setRowCount(len(rows))
            for i, row in enumerate(rows):
                serial_num = row[0]          # 全局统一编号
                order_id = row[1]            # 数据库实际ID
                serial_display = f"{int(serial_num):03d}"
                id_item = QTableWidgetItem(serial_display)
                # 存储 order_id 和 serial_display 以便详情使用
                id_item.setData(Qt.UserRole, (order_id, serial_display))
                self.table.setItem(i, 0, id_item)

                self.table.setItem(i, 1, QTableWidgetItem(row[2] or ""))
                executor_name = row[3] if row[3] else "未指派"
                self.table.setItem(i, 2, QTableWidgetItem(executor_name))
                plan_time = row[4]
                if isinstance(plan_time, datetime):
                    plan_time = plan_time.strftime("%Y-%m-%d %H:%M:%S")
                self.table.setItem(i, 3, QTableWidgetItem(plan_time or ""))
                finish_time = row[5]
                if isinstance(finish_time, datetime):
                    finish_time = finish_time.strftime("%Y-%m-%d %H:%M:%S")
                self.table.setItem(i, 4, QTableWidgetItem(finish_time or ""))
                create_time = row[6]
                if isinstance(create_time, datetime):
                    create_time = create_time.strftime("%Y-%m-%d %H:%M:%S")
                self.table.setItem(i, 5, QTableWidgetItem(create_time or ""))
                self.table.setItem(i, 6, QTableWidgetItem(row[7] or ""))
            cursor.close()
        except Exception as e:
            QMessageBox.critical(self, "错误", f"加载历史数据失败：{str(e)}")
        finally:
            conn.close()
        self.table.clearSelection()
        self.clear_detail()   # 清空详情显示

    def clear_detail(self):
        """清空详情区域所有字段（显示空白）"""
        for label in self.detail_labels.values():
            label.setText("")
        self.report_file_label.setText("")

    def search(self):
        self.load_data()

    def clear_search(self):
        self.building_combo.setCurrentIndex(0)
        self.executor_combo.setCurrentIndex(0)
        self.start_date.setDate(QDate())
        self.end_date.setDate(QDate())
        self.load_data()

    def get_current_id_and_serial(self):
        row = self.table.currentRow()
        if row < 0:
            return None, None
        id_item = self.table.item(row, 0)
        if id_item:
            data = id_item.data(Qt.UserRole)
            if isinstance(data, tuple) and len(data) == 2:
                return data[0], data[1]   # order_id, serial_display
            else:
                return data, None
        return None, None

    def on_selection_changed(self):
        """选中表格行时，更新详情区域"""
        order_id, serial_display = self.get_current_id_and_serial()
        if not order_id:
            self.clear_detail()
            return

        conn = self.get_connection()
        if not conn:
            return
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT building_code, order_status, executor_name, plan_time, finish_time, create_time, remark
                FROM inspect_work_order WHERE order_id = %s
            """, (order_id,))
            row = cursor.fetchone()
            cursor.close()
            if row:
                self.detail_labels["工单编号"].setText(serial_display)
                self.detail_labels["建筑代号"].setText(row[0] or "")
                self.detail_labels["工单状态"].setText(row[1] or "")
                executor = row[2] if row[2] else "未指派"
                self.detail_labels["执行人"].setText(executor)
                plan_time = row[3]
                if isinstance(plan_time, datetime):
                    plan_time = plan_time.strftime("%Y-%m-%d %H:%M:%S")
                self.detail_labels["计划时间"].setText(plan_time or "")
                finish_time = row[4]
                if isinstance(finish_time, datetime):
                    finish_time = finish_time.strftime("%Y-%m-%d %H:%M:%S")
                self.detail_labels["完成时间"].setText(finish_time or "")
                create_time = row[5]
                if isinstance(create_time, datetime):
                    create_time = create_time.strftime("%Y-%m-%d %H:%M:%S")
                self.detail_labels["创建时间"].setText(create_time or "")
                self.detail_labels["备注"].setText(row[6] or "")

                # 查找该工单的报告文件，只显示文件名
                report_dir = load_report_dir()
                pattern1 = os.path.join(report_dir, f"{serial_display}_*.pdf")
                pattern2 = os.path.join(report_dir, f"{serial_display}.pdf")
                files = glob.glob(pattern1) + glob.glob(pattern2)
                if files:
                    files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
                    latest_pdf = files[0]
                    filename = os.path.basename(latest_pdf)
                    self.report_file_label.setText(filename)
                else:
                    self.report_file_label.setText("未找到报告文件")
            else:
                self.clear_detail()
        except Exception as e:
            print(f"加载详情失败：{e}")
            self.clear_detail()
        finally:
            conn.close()

    def open_report_directly(self):
        """直接打开当前选中工单的报告（使用表格下方按钮）"""
        order_id, serial_display = self.get_current_id_and_serial()
        if not order_id:
            QMessageBox.information(self, "提示", "请先选择一条记录")
            return
        report_dir = load_report_dir()
        if not os.path.exists(report_dir):
            QMessageBox.information(
                self, "提示",
                f"报告目录不存在：{report_dir}\n请先在「报告查看」界面下载报告或更改目录。"
            )
            return

        pattern1 = os.path.join(report_dir, f"{serial_display}_*.pdf")
        pattern2 = os.path.join(report_dir, f"{serial_display}.pdf")
        files = glob.glob(pattern1) + glob.glob(pattern2)
        if not files:
            QMessageBox.information(
                self, "提示",
                f"未找到工单 {serial_display} 的报告文件。\n请先在「报告查看」界面下载该工单的报告。"
            )
            return
        files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
        latest_pdf = files[0]
        QDesktopServices.openUrl(QUrl.fromLocalFile(latest_pdf))

if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = HistoryWidget()
    w.show()
    sys.exit(app.exec())