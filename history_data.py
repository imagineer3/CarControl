# -*- coding: utf-8 -*-
"""
历史数据界面 - 显示已完成工单列表，工单编号使用连续编号（与工单管理一致）
"""

from PySide6.QtWidgets import *
from PySide6.QtCore import *
from PySide6.QtGui import QColor
import pymysql
from datetime import datetime

DB_CONFIG = {
    "host": "localhost",
    "port": 3306,
    "database": "database",
    "user": "root",
    "password": "123456"
}

class HistoryWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
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

        btn_layout = QHBoxLayout()
        self.view_btn = QPushButton("查看详情")
        self.refresh_btn = QPushButton("刷新")
        btn_layout.addWidget(self.view_btn)
        btn_layout.addWidget(self.refresh_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        self.view_btn.clicked.connect(self.view_detail)
        self.refresh_btn.clicked.connect(self.load_data)

        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(["工单编号", "建筑代号", "执行人", "计划时间", "完成时间", "创建时间", "备注"])
        self.table.setColumnWidth(0, 80)
        self.table.setColumnWidth(1, 100)
        self.table.setColumnWidth(2, 120)
        self.table.setColumnWidth(3, 140)
        self.table.setColumnWidth(4, 140)
        self.table.setColumnWidth(5, 140)
        self.table.setColumnWidth(6, 100)

    def load_executor_list(self):
        conn = self.get_connection()
        if not conn:
            return
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT executor_name FROM inspect_work_order WHERE order_status='已完成' AND executor_name IS NOT NULL AND executor_name != ''")
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
            sql = """
                SELECT order_id, building_code, executor_name, plan_time, finish_time, create_time, remark
                FROM inspect_work_order
                WHERE order_status = '已完成'
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
            sql += " ORDER BY finish_time DESC"
            cursor.execute(sql, params)
            rows = cursor.fetchall()
            self.table.setRowCount(len(rows))
            for i, row in enumerate(rows):
                order_id = row[0]
                serial_num = f"{i+1:03d}"
                id_item = QTableWidgetItem(serial_num)
                id_item.setData(Qt.UserRole, order_id)
                self.table.setItem(i, 0, id_item)

                self.table.setItem(i, 1, QTableWidgetItem(row[1] or ""))
                executor_name = row[2] if row[2] else "未指派"
                self.table.setItem(i, 2, QTableWidgetItem(executor_name))
                plan_time = row[3]
                if isinstance(plan_time, datetime):
                    plan_time = plan_time.strftime("%Y-%m-%d %H:%M:%S")
                self.table.setItem(i, 3, QTableWidgetItem(plan_time or ""))
                finish_time = row[4]
                if isinstance(finish_time, datetime):
                    finish_time = finish_time.strftime("%Y-%m-%d %H:%M:%S")
                self.table.setItem(i, 4, QTableWidgetItem(finish_time or ""))
                create_time = row[5]
                if isinstance(create_time, datetime):
                    create_time = create_time.strftime("%Y-%m-%d %H:%M:%S")
                self.table.setItem(i, 5, QTableWidgetItem(create_time or ""))
                self.table.setItem(i, 6, QTableWidgetItem(row[6] or ""))
            cursor.close()
        except Exception as e:
            QMessageBox.critical(self, "错误", f"加载历史数据失败：{str(e)}")
        finally:
            conn.close()
        self.table.clearSelection()
        self.clear_detail()

    def search(self):
        self.load_data()

    def clear_search(self):
        self.building_combo.setCurrentIndex(0)
        self.executor_combo.setCurrentIndex(0)
        self.start_date.setDate(QDate())
        self.end_date.setDate(QDate())
        self.load_data()

    def get_current_id(self):
        row = self.table.currentRow()
        if row < 0:
            return None
        id_item = self.table.item(row, 0)
        if id_item:
            return id_item.data(Qt.UserRole)
        return None

    def view_detail(self):
        order_id = self.get_current_id()
        if not order_id:
            QMessageBox.information(self, "提示", "请先选择一条记录")
            return
        conn = self.get_connection()
        if not conn:
            return
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT order_id, building_code, order_status, executor_name, plan_time, finish_time, create_time, remark
                FROM inspect_work_order WHERE order_id = %s
            """, (order_id,))
            row = cursor.fetchone()
            cursor.close()
            if row:
                dialog = HistoryDetailDialog(self, row)
                dialog.exec()
        except Exception as e:
            QMessageBox.critical(self, "错误", f"查询详情失败：{str(e)}")
        finally:
            conn.close()

    def clear_detail(self):
        pass

class HistoryDetailDialog(QDialog):
    def __init__(self, parent=None, row=None):
        super().__init__(parent)
        self.setWindowTitle("工单详情")
        self.setModal(True)
        self.row = row
        self.setup_ui()

    def setup_ui(self):
        layout = QFormLayout(self)
        order_id = self.row[0]
        building_code = self.row[1]
        order_status = self.row[2]
        executor_name = self.row[3] if self.row[3] else "未指派"
        plan_time = self.row[4]
        if isinstance(plan_time, datetime):
            plan_time = plan_time.strftime("%Y-%m-%d %H:%M:%S")
        finish_time = self.row[5]
        if isinstance(finish_time, datetime):
            finish_time = finish_time.strftime("%Y-%m-%d %H:%M:%S")
        create_time = self.row[6]
        if isinstance(create_time, datetime):
            create_time = create_time.strftime("%Y-%m-%d %H:%M:%S")
        remark = self.row[7] or ""

        serial = f"{order_id:03d}"
        layout.addRow("工单编号:", QLabel(serial))
        layout.addRow("建筑代号:", QLabel(building_code))
        layout.addRow("工单状态:", QLabel(order_status))
        layout.addRow("执行人:", QLabel(executor_name))
        layout.addRow("计划时间:", QLabel(plan_time))
        layout.addRow("完成时间:", QLabel(finish_time))
        layout.addRow("创建时间:", QLabel(create_time))
        layout.addRow("备注:", QLabel(remark))

        btn_box = QDialogButtonBox(QDialogButtonBox.Ok)
        btn_box.accepted.connect(self.accept)
        layout.addRow(btn_box)
        self.setMinimumWidth(400)

if __name__ == "__main__":
    import sys
    app = QApplication(sys.argv)
    w = HistoryWidget()
    w.show()
    sys.exit(app.exec())