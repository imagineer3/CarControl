# -*- coding: utf-8 -*-
"""
工单管理界面
支持增删改查，工单编号连续显示，编辑工单时若状态改为待巡检则清空完成时间
页面切换时自动刷新数据
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
    "password": "123456"          # 请修改为你的密码
}

class WorkOrderWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
        self.load_data()

    def showEvent(self, event):
        """每次页面显示时刷新数据，确保状态同步"""
        self.load_data()
        super().showEvent(event)

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

    def get_user_list(self):
        conn = self.get_connection()
        if not conn:
            return [("", "暂不指派")]
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT user_id, real_name FROM sys_user ORDER BY user_id")
            rows = cursor.fetchall()
            cursor.close()
            user_list = []
            for i, row in enumerate(rows):
                serial_num = f"{i+1:03d}"
                display_text = f"{serial_num} - {row[1]}"
                user_list.append((row[0], display_text))
            user_list.append((None, "暂不指派"))
            return user_list
        except Exception as e:
            print(f"获取人员列表失败：{e}")
            return [("", "暂不指派")]
        finally:
            conn.close()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        # 搜索栏
        search_layout = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("输入工单编号/建筑代号/执行人/状态")
        self.search_btn = QPushButton("搜索工单")
        self.search_btn.clicked.connect(self.search)
        self.clear_btn = QPushButton("清除输入")
        self.clear_btn.clicked.connect(self.clear_search)
        search_layout.addWidget(QLabel("搜索:"))
        search_layout.addWidget(self.search_edit)
        search_layout.addWidget(self.search_btn)
        search_layout.addWidget(self.clear_btn)
        search_layout.addStretch()
        layout.addLayout(search_layout)

        # 表格
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

        # 工单详情显示区域
        detail_group = QGroupBox("工单详情")
        detail_layout = QFormLayout(detail_group)
        self.detail_labels = {}
        fields = ["工单编号", "建筑代号", "工单状态", "执行人", "计划时间", "完成时间", "创建时间", "备注"]
        for field in fields:
            label = QLabel("")
            label.setWordWrap(True)
            self.detail_labels[field] = label
            detail_layout.addRow(field + ":", label)
        layout.addWidget(detail_group)

        # 按钮栏
        btn_layout = QHBoxLayout()
        self.add_btn = QPushButton("新增工单")
        self.edit_btn = QPushButton("编辑工单")
        self.complete_btn = QPushButton("完成工单")
        self.del_btn = QPushButton("删除工单")
        self.refresh_btn = QPushButton("刷新")
        btn_layout.addWidget(self.add_btn)
        btn_layout.addWidget(self.edit_btn)
        btn_layout.addWidget(self.complete_btn)
        btn_layout.addWidget(self.del_btn)
        btn_layout.addWidget(self.refresh_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # 事件绑定
        self.add_btn.clicked.connect(self.add_order)
        self.edit_btn.clicked.connect(self.edit_order)
        self.complete_btn.clicked.connect(self.complete_order)
        self.del_btn.clicked.connect(self.delete_order)
        self.refresh_btn.clicked.connect(self.load_data)
        self.table.itemSelectionChanged.connect(self.on_selection_changed)
        self.table.setFocusPolicy(Qt.StrongFocus)
        self.table.clicked.connect(self.on_table_clicked)

        # 设置表头
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels([
            "工单编号", "建筑代号", "工单状态", "执行人",
            "计划时间", "完成时间", "创建时间", "备注"
        ])
        self.table.setColumnWidth(0, 80)
        self.table.setColumnWidth(1, 100)
        self.table.setColumnWidth(2, 100)
        self.table.setColumnWidth(3, 120)
        self.table.setColumnWidth(4, 140)
        self.table.setColumnWidth(5, 140)
        self.table.setColumnWidth(6, 140)
        self.table.setColumnWidth(7, 80)

    def on_table_clicked(self, index):
        if not index.isValid():
            self.table.clearSelection()
            self.clear_detail()

    def on_selection_changed(self):
        current_row = self.table.currentRow()
        if current_row < 0:
            self.clear_detail()
            return
        # 获取当前行数据
        id_item = self.table.item(current_row, 0)
        serial_num = id_item.text() if id_item else ""
        building_code = self.table.item(current_row, 1).text()
        order_status = self.table.item(current_row, 2).text()
        executor_name = self.table.item(current_row, 3).text()
        plan_time = self.table.item(current_row, 4).text()
        finish_time = self.table.item(current_row, 5).text()
        create_time = self.table.item(current_row, 6).text()
        remark = self.table.item(current_row, 7).text()
        self.detail_labels["工单编号"].setText(serial_num)
        self.detail_labels["建筑代号"].setText(building_code)
        self.detail_labels["工单状态"].setText(order_status)
        self.detail_labels["执行人"].setText(executor_name)
        self.detail_labels["计划时间"].setText(plan_time)
        self.detail_labels["完成时间"].setText(finish_time)
        self.detail_labels["创建时间"].setText(create_time)
        self.detail_labels["备注"].setText(remark)

    def clear_detail(self):
        for label in self.detail_labels.values():
            label.setText("")

    def build_search_condition(self, keyword):
        if not keyword:
            return "", ()
        kw = keyword.strip()
        if kw in ["待巡检", "巡检中", "已完成", "异常"]:
            return "order_status = %s", (kw,)
        try:
            int_val = int(kw)
            return "order_id = %s", (int_val,)
        except:
            return "(building_code LIKE %s OR executor_name LIKE %s)", (f"%{kw}%", f"%{kw}%")

    def load_data(self, keyword=""):
        conn = self.get_connection()
        if not conn:
            return
        try:
            cursor = conn.cursor()
            condition, params = self.build_search_condition(keyword)
            if condition:
                sql = f"SELECT order_id, building_code, order_status, executor_name, plan_time, finish_time, create_time, remark FROM inspect_work_order WHERE {condition} ORDER BY order_id"
                cursor.execute(sql, params)
            else:
                sql = "SELECT order_id, building_code, order_status, executor_name, plan_time, finish_time, create_time, remark FROM inspect_work_order ORDER BY order_id"
                cursor.execute(sql)
            rows = cursor.fetchall()
            self.table.setRowCount(len(rows))
            for i, row in enumerate(rows):
                order_id = row[0]
                serial_num = f"{i+1:03d}"
                id_item = QTableWidgetItem(serial_num)
                id_item.setData(Qt.UserRole, order_id)
                self.table.setItem(i, 0, id_item)

                # 建筑代号
                self.table.setItem(i, 1, QTableWidgetItem(row[1] or ""))
                # 状态
                self.table.setItem(i, 2, QTableWidgetItem(row[2] or ""))
                # 执行人（空则显示"未指派"）
                executor = row[3] if row[3] else "未指派"
                self.table.setItem(i, 3, QTableWidgetItem(executor))
                # 计划时间
                plan_time = row[4]
                if isinstance(plan_time, datetime):
                    plan_time = plan_time.strftime("%Y-%m-%d %H:%M:%S")
                self.table.setItem(i, 4, QTableWidgetItem(plan_time or ""))
                # 完成时间
                finish_time = row[5]
                if isinstance(finish_time, datetime):
                    finish_time = finish_time.strftime("%Y-%m-%d %H:%M:%S")
                if row[2] != "已完成" and (finish_time is None or finish_time == ""):
                    finish_time = "未完成"
                self.table.setItem(i, 5, QTableWidgetItem(finish_time or ""))
                # 创建时间
                create_time = row[6]
                if isinstance(create_time, datetime):
                    create_time = create_time.strftime("%Y-%m-%d %H:%M:%S")
                self.table.setItem(i, 6, QTableWidgetItem(create_time or ""))
                # 备注
                self.table.setItem(i, 7, QTableWidgetItem(row[7] or ""))
            cursor.close()
        except Exception as e:
            QMessageBox.critical(self, "错误", f"加载数据失败：{str(e)}")
        finally:
            conn.close()
        self.table.clearSelection()
        self.clear_detail()

    def search(self):
        keyword = self.search_edit.text().strip()
        self.load_data(keyword)

    def clear_search(self):
        self.search_edit.clear()
        self.load_data()

    def get_current_id(self):
        current_row = self.table.currentRow()
        if current_row < 0:
            return None
        id_item = self.table.item(current_row, 0)
        if id_item:
            return id_item.data(Qt.UserRole)
        return None

    def add_order(self):
        user_list = self.get_user_list()
        if not user_list:
            QMessageBox.warning(self, "警告", "无法加载人员列表")
            return
        dialog = OrderEditDialog(self, user_list=user_list)
        if dialog.exec() == QDialog.Accepted:
            data = dialog.get_data()
            conn = self.get_connection()
            if not conn:
                return
            try:
                cursor = conn.cursor()
                executor_value = data["executor_name"] if data["executor_name"] != "暂不指派" else ""
                sql = """
                    INSERT INTO inspect_work_order (building_code, order_status, executor_name, plan_time, remark)
                    VALUES (%s, %s, %s, %s, %s)
                """
                cursor.execute(sql, (data["building_code"], data["order_status"], executor_value, data["plan_time"], data["remark"]))
                conn.commit()
                cursor.close()
                QMessageBox.information(self, "成功", "工单添加成功")
                self.load_data()
            except Exception as e:
                QMessageBox.critical(self, "错误", f"添加失败：{str(e)}")
            finally:
                conn.close()

    def edit_order(self):
        order_id = self.get_current_id()
        if not order_id:
            QMessageBox.information(self, "提示", "请先选择一条记录")
            return
        row = self.table.currentRow()
        # 获取执行人存储值（表格中可能是"未指派"或实际姓名）
        executor_display = self.table.item(row, 3).text()
        executor_stored = "" if executor_display == "未指派" else executor_display
        current_data = {
            "order_id": order_id,
            "building_code": self.table.item(row, 1).text(),
            "order_status": self.table.item(row, 2).text(),
            "executor_name": executor_stored,
            "plan_time": self.table.item(row, 4).text(),
            "remark": self.table.item(row, 7).text(),
        }
        user_list = self.get_user_list()
        if not user_list:
            QMessageBox.warning(self, "警告", "无法加载人员列表")
            return
        dialog = OrderEditDialog(self, current_data, user_list)
        if dialog.exec() == QDialog.Accepted:
            new_data = dialog.get_data()
            conn = self.get_connection()
            if not conn:
                return
            try:
                cursor = conn.cursor()
                executor_value = new_data["executor_name"] if new_data["executor_name"] != "暂不指派" else ""
                sql = """
                    UPDATE inspect_work_order
                    SET building_code=%s, order_status=%s, executor_name=%s, plan_time=%s, remark=%s
                    WHERE order_id=%s
                """
                cursor.execute(sql, (new_data["building_code"], new_data["order_status"], executor_value,
                                    new_data["plan_time"], new_data["remark"], order_id))
                # 如果状态改为“待巡检”，同时清空完成时间
                if new_data["order_status"] == "待巡检":
                    cursor.execute("UPDATE inspect_work_order SET finish_time=NULL WHERE order_id=%s", (order_id,))
                conn.commit()
                cursor.close()
                QMessageBox.information(self, "成功", "工单已更新")
                self.load_data()
            except Exception as e:
                QMessageBox.critical(self, "错误", f"更新失败：{str(e)}")
            finally:
                conn.close()

    def complete_order(self):
        order_id = self.get_current_id()
        if not order_id:
            QMessageBox.information(self, "提示", "请先选择一条记录")
            return
        row = self.table.currentRow()
        current_status = self.table.item(row, 2).text()
        if current_status == "已完成":
            QMessageBox.information(self, "提示", "该工单已经是已完成状态")
            return
        reply = QMessageBox.question(self, "确认完成", "确定将此工单标记为已完成吗？",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            conn = self.get_connection()
            if not conn:
                return
            try:
                cursor = conn.cursor()
                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                sql = "UPDATE inspect_work_order SET order_status='已完成', finish_time=%s WHERE order_id=%s"
                cursor.execute(sql, (now, order_id))
                conn.commit()
                cursor.close()
                QMessageBox.information(self, "成功", "工单已完成")
                self.load_data()
            except Exception as e:
                QMessageBox.critical(self, "错误", f"完成操作失败：{str(e)}")
            finally:
                conn.close()

    def delete_order(self):
        order_id = self.get_current_id()
        if not order_id:
            QMessageBox.information(self, "提示", "请先选择一条记录")
            return
        building_code = self.table.item(self.table.currentRow(), 1).text()
        reply = QMessageBox.question(self, "确认删除", f"确定删除工单【{building_code}】吗？",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            conn = self.get_connection()
            if not conn:
                return
            try:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM inspect_work_order WHERE order_id=%s", (order_id,))
                conn.commit()
                cursor.close()
                QMessageBox.information(self, "成功", "工单已删除")
                self.load_data()
            except Exception as e:
                QMessageBox.critical(self, "错误", f"删除失败：{str(e)}")
            finally:
                conn.close()


class OrderEditDialog(QDialog):
    def __init__(self, parent=None, data=None, user_list=None):
        super().__init__(parent)
        self.data = data or {}
        self.user_list = user_list or []
        self.setWindowTitle("编辑工单" if data else "新增工单")
        self.setModal(True)
        self.setup_ui()

    def setup_ui(self):
        layout = QFormLayout(self)

        # 建筑代号下拉框
        self.building_code_combo = QComboBox()
        building_options = ["east", "south", "north", "west"]
        self.building_code_combo.addItems(building_options)
        current_building = self.data.get("building_code", "")
        if current_building in building_options:
            self.building_code_combo.setCurrentText(current_building)
        else:
            self.building_code_combo.setCurrentIndex(0)
        layout.addRow("建筑代号:", self.building_code_combo)

        self.status_combo = QComboBox()
        self.status_combo.addItems(["待巡检", "巡检中", "已完成", "异常"])
        self.status_combo.setCurrentText(self.data.get("order_status", "待巡检"))
        layout.addRow("工单状态:", self.status_combo)

        # 执行人下拉框
        self.executor_combo = QComboBox()
        self.executor_combo.addItem("")
        for user_id, display_text in self.user_list:
            self.executor_combo.addItem(display_text, user_id)
        current_executor = self.data.get("executor_name", "")
        if current_executor:
            for i in range(self.executor_combo.count()):
                if self.executor_combo.itemText(i) == current_executor:
                    self.executor_combo.setCurrentIndex(i)
                    break
        layout.addRow("执行人:", self.executor_combo)

        # 计划时间选择器
        self.plan_time_edit = QDateTimeEdit()
        self.plan_time_edit.setCalendarPopup(True)
        self.plan_time_edit.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        if self.data.get("plan_time"):
            try:
                dt = datetime.strptime(self.data["plan_time"], "%Y-%m-%d %H:%M:%S")
                self.plan_time_edit.setDateTime(QDateTime(dt))
            except:
                pass
        else:
            self.plan_time_edit.setDateTime(QDateTime.currentDateTime())
        layout.addRow("计划时间:", self.plan_time_edit)

        self.remark_edit = QLineEdit()
        self.remark_edit.setText(self.data.get("remark", ""))
        layout.addRow("备注:", self.remark_edit)

        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addRow(btn_box)
        self.setMinimumWidth(400)

    def get_data(self):
        plan_time = self.plan_time_edit.dateTime().toString("yyyy-MM-dd HH:mm:ss")
        executor_text = self.executor_combo.currentText()
        return {
            "building_code": self.building_code_combo.currentText(),
            "order_status": self.status_combo.currentText(),
            "executor_name": executor_text,
            "plan_time": plan_time,
            "remark": self.remark_edit.text().strip(),
        }

if __name__ == "__main__":
    import sys
    app = QApplication(sys.argv)
    w = WorkOrderWidget()
    w.show()
    sys.exit(app.exec())