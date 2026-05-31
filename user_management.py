# -*- coding: utf-8 -*-
"""
用户管理界面 - 使用 PyMySQL 连接 MySQL，QTableWidget 展示数据
支持增删改查，显示连续编号（基于记录顺序），实时显示选中详情，选中行淡蓝色，点击空白取消选中
搜索增强：支持按角色、状态、姓名/电话搜索
"""

from PySide6.QtWidgets import *
from PySide6.QtCore import *
from PySide6.QtGui import QColor
import pymysql


# ========== 数据库配置（请修改为你的实际参数）==========
DB_CONFIG = {
    "host": "localhost",
    "port": 3306,
    "database": "database",
    "user": "root",
    "password": "123456"         # 修改为你的密码
}
# =================================================


class UserManagementWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
        self.load_data()

    def get_connection(self):
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
            QMessageBox.critical(self, "数据库错误", f"连接失败：{str(e)}")
            return None

    def setup_ui(self):
        layout = QVBoxLayout(self)

        # 搜索栏
        search_layout = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("输入姓名/电话/角色(管理员/操作员)/状态(在岗/离岗)")
        self.search_btn = QPushButton("搜索用户")
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
        self.table.horizontalHeader().setStretchLastSection(True)
        # 隐藏行号
        self.table.verticalHeader().setVisible(False)
        # 设置选中行样式：淡蓝色背景，黑色文字
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

        # 用户详情显示区域
        detail_group = QGroupBox("用户详情")
        detail_layout = QFormLayout(detail_group)
        self.detail_labels = {}
        fields = ["用户编号", "姓名", "角色", "在岗状态", "电话", "创建时间", "备注"]
        for field in fields:
            label = QLabel("")
            label.setWordWrap(True)
            self.detail_labels[field] = label
            detail_layout.addRow(field + ":", label)
        layout.addWidget(detail_group)

        # 按钮栏
        btn_layout = QHBoxLayout()
        self.add_btn = QPushButton("新增用户")
        self.edit_btn = QPushButton("编辑用户")
        self.del_btn = QPushButton("删除用户")
        self.refresh_btn = QPushButton("刷新")
        btn_layout.addWidget(self.add_btn)
        btn_layout.addWidget(self.edit_btn)
        btn_layout.addWidget(self.del_btn)
        btn_layout.addWidget(self.refresh_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # 绑定事件
        self.add_btn.clicked.connect(self.add_user)
        self.edit_btn.clicked.connect(self.edit_user)
        self.del_btn.clicked.connect(self.delete_user)
        self.refresh_btn.clicked.connect(self.load_data)
        self.table.itemSelectionChanged.connect(self.on_selection_changed)
        self.table.setFocusPolicy(Qt.StrongFocus)
        self.table.clicked.connect(self.on_table_clicked)

        # 设置表头
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(["用户编号", "姓名", "角色", "在岗状态", "电话", "创建时间", "备注"])
        # 调整列宽
        self.table.setColumnWidth(0, 80)   # 编号
        self.table.setColumnWidth(1, 120)  # 姓名
        self.table.setColumnWidth(2, 90)   # 角色
        self.table.setColumnWidth(3, 90)   # 在岗状态
        self.table.setColumnWidth(4, 120)  # 电话
        self.table.setColumnWidth(5, 150)  # 创建时间
        self.table.setColumnWidth(6, 80)   # 备注

    def on_table_clicked(self, index):
        if not index.isValid():
            self.table.clearSelection()
            self.clear_detail()

    def on_selection_changed(self):
        current_row = self.table.currentRow()
        if current_row < 0:
            self.clear_detail()
            return
        # 获取当前行数据（第一列为连续编号）
        serial_item = self.table.item(current_row, 0)
        serial_num = serial_item.text() if serial_item else ""
        real_name = self.table.item(current_row, 1).text()
        role = self.table.item(current_row, 2).text()
        work_status = self.table.item(current_row, 3).text()
        phone = self.table.item(current_row, 4).text()
        create_time = self.table.item(current_row, 5).text()
        remark = self.table.item(current_row, 6).text()
        self.detail_labels["用户编号"].setText(serial_num)
        self.detail_labels["姓名"].setText(real_name)
        self.detail_labels["角色"].setText(role)
        self.detail_labels["在岗状态"].setText(work_status)
        self.detail_labels["电话"].setText(phone)
        self.detail_labels["创建时间"].setText(create_time)
        self.detail_labels["备注"].setText(remark)

    def clear_detail(self):
        for label in self.detail_labels.values():
            label.setText("")

    def build_search_condition(self, keyword):
        """根据关键词构建搜索条件"""
        if not keyword:
            return "", ()
        keyword = keyword.strip()
        if keyword in ["管理员", "操作员"]:
            return "role = %s", (keyword,)
        if keyword in ["在岗", "离岗"]:
            return "work_status = %s", (keyword,)
        return "(real_name LIKE %s OR phone LIKE %s)", (f"%{keyword}%", f"%{keyword}%")

    def load_data(self, keyword=""):
        conn = self.get_connection()
        if not conn:
            return
        try:
            cursor = conn.cursor()
            condition, params = self.build_search_condition(keyword)
            if condition:
                sql = f"SELECT user_id, real_name, role, work_status, phone, create_time, remark FROM sys_user WHERE {condition} ORDER BY user_id"
                cursor.execute(sql, params)
            else:
                sql = "SELECT user_id, real_name, role, work_status, phone, create_time, remark FROM sys_user ORDER BY user_id"
                cursor.execute(sql)
            rows = cursor.fetchall()
            self.table.setRowCount(len(rows))
            for i, row in enumerate(rows):
                user_id = row[0]
                # 显示连续编号（从 001 开始），基于当前行顺序
                serial_num = f"{i+1:03d}"
                id_item = QTableWidgetItem(serial_num)
                id_item.setData(Qt.UserRole, user_id)   # 存储原始 user_id 用于编辑/删除
                self.table.setItem(i, 0, id_item)
                for j in range(1, 7):
                    val = row[j]
                    self.table.setItem(i, j, QTableWidgetItem(str(val) if val else ""))
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
            return id_item.data(Qt.UserRole)   # 返回原始 user_id
        return None

    def add_user(self):
        dialog = UserEditDialog(self)
        if dialog.exec() == QDialog.Accepted:
            data = dialog.get_data()
            conn = self.get_connection()
            if not conn:
                return
            try:
                cursor = conn.cursor()
                sql = """
                    INSERT INTO sys_user (real_name, role, work_status, phone, remark)
                    VALUES (%s, %s, %s, %s, %s)
                """
                cursor.execute(sql, (data["real_name"], data["role"], data["work_status"], data["phone"], data["remark"]))
                conn.commit()
                cursor.close()
                QMessageBox.information(self, "成功", "用户添加成功")
                self.load_data()
            except Exception as e:
                QMessageBox.critical(self, "错误", f"添加失败：{str(e)}")
            finally:
                conn.close()

    def edit_user(self):
        user_id = self.get_current_id()
        if not user_id:
            QMessageBox.information(self, "提示", "请先选择一条记录")
            return
        row = self.table.currentRow()
        current_data = {
            "user_id": user_id,
            "real_name": self.table.item(row, 1).text(),
            "role": self.table.item(row, 2).text(),
            "work_status": self.table.item(row, 3).text(),
            "phone": self.table.item(row, 4).text(),
            "remark": self.table.item(row, 6).text(),
        }
        dialog = UserEditDialog(self, current_data)
        if dialog.exec() == QDialog.Accepted:
            new_data = dialog.get_data()
            conn = self.get_connection()
            if not conn:
                return
            try:
                cursor = conn.cursor()
                sql = """
                    UPDATE sys_user
                    SET real_name=%s, role=%s, work_status=%s, phone=%s, remark=%s
                    WHERE user_id=%s
                """
                cursor.execute(sql, (new_data["real_name"], new_data["role"],
                                    new_data["work_status"], new_data["phone"],
                                    new_data["remark"], user_id))
                conn.commit()
                cursor.close()
                QMessageBox.information(self, "成功", "用户信息已更新")
                self.load_data()
            except Exception as e:
                QMessageBox.critical(self, "错误", f"更新失败：{str(e)}")
            finally:
                conn.close()

    def delete_user(self):
        user_id = self.get_current_id()
        if not user_id:
            QMessageBox.information(self, "提示", "请先选择一条记录")
            return
        real_name = self.table.item(self.table.currentRow(), 1).text()
        reply = QMessageBox.question(self, "确认删除", f"确定删除用户【{real_name}】吗？",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            conn = self.get_connection()
            if not conn:
                return
            try:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM sys_user WHERE user_id=%s", (user_id,))
                conn.commit()
                cursor.close()
                QMessageBox.information(self, "成功", "用户已删除")
                self.load_data()
            except Exception as e:
                QMessageBox.critical(self, "错误", f"删除失败：{str(e)}")
            finally:
                conn.close()


class UserEditDialog(QDialog):
    def __init__(self, parent=None, data=None):
        super().__init__(parent)
        self.data = data or {}
        self.setWindowTitle("编辑用户" if data else "新增用户")
        self.setModal(True)
        self.setup_ui()

    def setup_ui(self):
        layout = QFormLayout(self)

        self.real_name_edit = QLineEdit()
        self.real_name_edit.setText(self.data.get("real_name", ""))
        layout.addRow("姓名:", self.real_name_edit)

        self.role_combo = QComboBox()
        self.role_combo.addItems(["管理员", "操作员"])
        self.role_combo.setCurrentText(self.data.get("role", "操作员"))
        layout.addRow("角色:", self.role_combo)

        self.status_combo = QComboBox()
        self.status_combo.addItems(["在岗", "离岗"])
        self.status_combo.setCurrentText(self.data.get("work_status", "在岗"))
        layout.addRow("在岗状态:", self.status_combo)

        self.phone_edit = QLineEdit()
        self.phone_edit.setText(self.data.get("phone", ""))
        layout.addRow("电话:", self.phone_edit)

        self.remark_edit = QLineEdit()
        self.remark_edit.setText(self.data.get("remark", ""))
        layout.addRow("备注:", self.remark_edit)

        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addRow(btn_box)

        self.setMinimumWidth(350)

    def get_data(self):
        return {
            "real_name": self.real_name_edit.text().strip(),
            "role": self.role_combo.currentText(),
            "work_status": self.status_combo.currentText(),
            "phone": self.phone_edit.text().strip(),
            "remark": self.remark_edit.text().strip(),
        }


# 单独测试
if __name__ == "__main__":
    import sys
    app = QApplication(sys.argv)
    w = UserManagementWidget()
    w.show()
    sys.exit(app.exec())