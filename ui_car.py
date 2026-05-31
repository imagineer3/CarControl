# -*- coding: utf-8 -*-
################################################################################
## UI设计由 Qt Designer 生成，自动转换为 PySide6 代码
## 1:1 还原你的树莓派小车控制上位机界面 + 全部样式表
################################################################################
from PySide6 import QtCore, QtGui, QtWidgets

class Ui_MainWindow(object):
    def setupUi(self, MainWindow):
        MainWindow.setObjectName("MainWindow")
        MainWindow.resize(1000, 750)
        MainWindow.setMinimumSize(QtCore.QSize(1000, 750))
        MainWindow.setStyleSheet("QMainWindow {\n"
"        background-color: #f5f7fa;\n"
"}\n"
"QLabel#label_video {\n"
"        background-color: #000000;\n"
"        border: 3px solid #34495e;\n"
"        border-radius: 10px;\n"
"        font-size: 16px;\n"
"        color: #ffffff;\n"
"}\n"
"QPushButton {\n"
"        font-size: 14px;\n"
"        padding: 12px;\n"
"        border-radius: 6px;\n"
"        background-color: #3498db;\n"
"        color: white;\n"
"        min-width: 100px;\n"
"        min-height: 40px;\n"
"}\n"
"QPushButton:pressed {\n"
"        background-color: #2980b9;\n"
"}\n"
"QPushButton:disabled {\n"
"        background-color: #bdc3c7;\n"
"        color: #7f8c8d;\n"
"}\n"
"QPushButton#btn_connect {\n"
"        background-color: #27ae60;\n"
"        font-weight: bold;\n"
"        min-width: 160px;\n"
"}\n"
"QPushButton#btn_connect:disabled {\n"
"        background-color: #bdc3c7;\n"
"}\n"
"QPushButton#btn_disconnect {\n"
"        background-color: #e67e22;\n"
"        font-weight: bold;\n"
"        min-width: 160px;\n"
"}\n"
"QPushButton#btn_disconnect:disabled {\n"
"        background-color: #bdc3c7;\n"
"}\n"
"QPushButton#btn_stop {\n"
"        background-color: #e74c3c;\n"
"        font-weight: bold;\n"
"        font-size: 15px;\n"
"}\n"
"QPushButton#btn_stop:disabled {\n"
"        background-color: #bdc3c7;\n"
"}\n"
"QPushButton#btn_trace_start {\n"
"        background-color: #9b59b6;\n"
"        font-weight: bold;\n"
"}\n"
"QPushButton#btn_trace_start:disabled {\n"
"        background-color: #bdc3c7;\n"
"}\n"
"QPushButton#btn_trace_stop {\n"
"        background-color: #e74c3c;\n"
"        font-weight: bold;\n"
"}\n"
"QPushButton#btn_trace_stop:disabled {\n"
"        background-color: #bdc3c7;\n"
"}\n"
"QPushButton#btn_set_point {\n"
"        background-color: #16a085;\n"
"        font-weight: bold;\n"
"}\n"
"QPushButton#btn_set_point:disabled {\n"
"        background-color: #bdc3c7;\n"
"}\n"
"QPushButton#btn_servo_reset {\n"
"        background-color: #f39c12;\n"
"        font-weight: bold;\n"
"}\n"
"QPushButton#btn_servo_reset:disabled {\n"
"        background-color: #bdc3c7;\n"
"}\n"
"QGroupBox {\n"
"        font-size: 14px;\n"
"        font-weight: bold;\n"
"        color: #2c3e50;\n"
"        margin-top: 10px;\n"
"        padding-top: 10px;\n"
"}\n"
"QTextEdit {\n"
"        font-size: 13px;\n"
"        border: 2px solid #bdc3c7;\n"
"        border-radius: 6px;\n"
"        padding: 8px;\n"
"        background-color: #ffffff;\n"
"        min-height: 80px;\n"
"}\n"
"QLineEdit {\n"
"        font-size: 13px;\n"
"        padding: 8px;\n"
"        border: 2px solid #bdc3c7;\n"
"        border-radius: 6px;\n"
"        background-color: #ffffff;\n"
"        min-height: 25px;\n"
"}\n"
"QLineEdit:disabled {\n"
"        background-color: #ecf0f1;\n"
"        border-color: #d0d7d9;\n"
"}\n"
"QLabel {\n"
"        font-size: 13px;\n"
"        color: #2c3e50;\n"
"}")
        self.centralWidget = QtWidgets.QWidget(MainWindow)
        self.centralWidget.setObjectName("centralWidget")
        self.mainLayout = QtWidgets.QVBoxLayout(self.centralWidget)
        self.mainLayout.setSpacing(15)
        self.mainLayout.setContentsMargins(20, 20, 20, 20)
        self.mainLayout.setObjectName("mainLayout")
        
        # 视频显示区域
        self.label_video = QtWidgets.QLabel(self.centralWidget)
        self.label_video.setAlignment(QtCore.Qt.AlignCenter)
        self.label_video.setObjectName("label_video")
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        sizePolicy.setVerticalStretch(6)
        self.label_video.setSizePolicy(sizePolicy)
        self.mainLayout.addWidget(self.label_video)

        # 控制布局
        self.controlLayout = QtWidgets.QHBoxLayout()
        self.controlLayout.setSpacing(20)
        self.controlLayout.setObjectName("controlLayout")

        # 小车运动控制组
        self.groupBox = QtWidgets.QGroupBox(self.centralWidget)
        self.groupBox.setTitle("小车运动控制")
        self.gridLayout = QtWidgets.QGridLayout(self.groupBox)
        self.gridLayout.setSpacing(10)
        self.btn_forward = QtWidgets.QPushButton(self.groupBox)
        self.btn_forward.setText("前进")
        self.gridLayout.addWidget(self.btn_forward, 0, 1)
        self.btn_left = QtWidgets.QPushButton(self.groupBox)
        self.btn_left.setText("左转")
        self.gridLayout.addWidget(self.btn_left, 1, 0)
        self.btn_stop = QtWidgets.QPushButton(self.groupBox)
        self.btn_stop.setText("停止")
        self.gridLayout.addWidget(self.btn_stop, 1, 1)
        self.btn_right = QtWidgets.QPushButton(self.groupBox)
        self.btn_right.setText("右转")
        self.gridLayout.addWidget(self.btn_right, 1, 2)
        self.btn_backward = QtWidgets.QPushButton(self.groupBox)
        self.btn_backward.setText("后退")
        self.gridLayout.addWidget(self.btn_backward, 2, 1)
        self.controlLayout.addWidget(self.groupBox)

        # 舵机云台控制组
        self.groupBox_2 = QtWidgets.QGroupBox(self.centralWidget)
        self.groupBox_2.setTitle("舵机云台控制")
        self.gridLayout_2 = QtWidgets.QGridLayout(self.groupBox_2)
        self.gridLayout_2.setSpacing(8)
        self.hboxLayout_h = QtWidgets.QHBoxLayout()
        self.label_h_angle = QtWidgets.QLabel(self.groupBox_2)
        self.label_h_angle.setText("水平角度：")
        self.hboxLayout_h.addWidget(self.label_h_angle)
        self.edit_servo_h_angle = QtWidgets.QLineEdit(self.groupBox_2)
        self.edit_servo_h_angle.setText("10")
        self.edit_servo_h_angle.setPlaceholderText("1-90")
        self.edit_servo_h_angle.setAlignment(QtCore.Qt.AlignCenter)
        self.hboxLayout_h.addWidget(self.edit_servo_h_angle)
        self.gridLayout_2.addLayout(self.hboxLayout_h, 0, 0, 1, 3)
        self.btn_servo_up = QtWidgets.QPushButton(self.groupBox_2)
        self.btn_servo_up.setText("云台上")
        self.gridLayout_2.addWidget(self.btn_servo_up, 1, 1)
        self.btn_servo_left = QtWidgets.QPushButton(self.groupBox_2)
        self.btn_servo_left.setText("云台左")
        self.gridLayout_2.addWidget(self.btn_servo_left, 2, 0)
        self.btn_servo_reset = QtWidgets.QPushButton(self.groupBox_2)
        self.btn_servo_reset.setText("云台复位")
        self.gridLayout_2.addWidget(self.btn_servo_reset, 2, 1)
        self.btn_servo_right = QtWidgets.QPushButton(self.groupBox_2)
        self.btn_servo_right.setText("云台右")
        self.gridLayout_2.addWidget(self.btn_servo_right, 2, 2)
        self.btn_servo_down = QtWidgets.QPushButton(self.groupBox_2)
        self.btn_servo_down.setText("云台下")
        self.gridLayout_2.addWidget(self.btn_servo_down, 3, 1)
        self.hboxLayout_v = QtWidgets.QHBoxLayout()
        self.label_v_angle = QtWidgets.QLabel(self.groupBox_2)
        self.label_v_angle.setText("垂直角度：")
        self.hboxLayout_v.addWidget(self.label_v_angle)
        self.edit_servo_v_angle = QtWidgets.QLineEdit(self.groupBox_2)
        self.edit_servo_v_angle.setText("10")
        self.edit_servo_v_angle.setPlaceholderText("1-90")
        self.edit_servo_v_angle.setAlignment(QtCore.Qt.AlignCenter)
        self.hboxLayout_v.addWidget(self.edit_servo_v_angle)
        self.gridLayout_2.addLayout(self.hboxLayout_v, 4, 0, 1, 3)
        self.controlLayout.addWidget(self.groupBox_2)

        # 自动循迹控制组
        self.groupBox_3 = QtWidgets.QGroupBox(self.centralWidget)
        self.groupBox_3.setTitle("自动循迹控制")
        self.verticalLayout = QtWidgets.QVBoxLayout(self.groupBox_3)
        self.verticalLayout.setSpacing(10)
        self.edit_point_num = QtWidgets.QLineEdit(self.groupBox_3)
        self.edit_point_num.setPlaceholderText("输入途径点数量(1-9)")
        self.edit_point_num.setAlignment(QtCore.Qt.AlignCenter)
        self.verticalLayout.addWidget(self.edit_point_num)
        self.btn_set_point = QtWidgets.QPushButton(self.groupBox_3)
        self.btn_set_point.setText("设置途径点")
        self.verticalLayout.addWidget(self.btn_set_point)
        self.btn_trace_start = QtWidgets.QPushButton(self.groupBox_3)
        self.btn_trace_start.setText("开始循迹")
        self.verticalLayout.addWidget(self.btn_trace_start)
        self.btn_trace_stop = QtWidgets.QPushButton(self.groupBox_3)
        self.btn_trace_stop.setText("停止循迹")
        self.verticalLayout.addWidget(self.btn_trace_stop)
        self.controlLayout.addWidget(self.groupBox_3)

        self.mainLayout.addLayout(self.controlLayout)

        # 底部布局：日志 + 连接按钮
        self.bottomLayout = QtWidgets.QHBoxLayout()
        self.bottomLayout.setSpacing(20)
        self.text_log = QtWidgets.QTextEdit(self.centralWidget)
        self.text_log.setPlaceholderText("小车返回数据日志...")
        self.text_log.setReadOnly(True)
        sizePolicy1 = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        sizePolicy1.setVerticalStretch(1)
        self.text_log.setSizePolicy(sizePolicy1)
        self.bottomLayout.addWidget(self.text_log)
        self.buttonLayout = QtWidgets.QVBoxLayout()
        self.buttonLayout.setSpacing(10)
        self.btn_connect = QtWidgets.QPushButton(self.centralWidget)
        self.btn_connect.setText("连接小车")
        self.buttonLayout.addWidget(self.btn_connect)
        self.btn_disconnect = QtWidgets.QPushButton(self.centralWidget)
        self.btn_disconnect.setText("断开连接")
        self.buttonLayout.addWidget(self.btn_disconnect)
        self.bottomLayout.addLayout(self.buttonLayout)
        self.mainLayout.addLayout(self.bottomLayout)

        MainWindow.setCentralWidget(self.centralWidget)
        self.menuBar = QtWidgets.QMenuBar(MainWindow)
        self.menuBar.setGeometry(QtCore.QRect(0, 0, 1000, 22))
        MainWindow.setMenuBar(self.menuBar)
        self.statusBar = QtWidgets.QStatusBar(MainWindow)
        MainWindow.setStatusBar(self.statusBar)

        self.retranslateUi(MainWindow)
        QtCore.QMetaObject.connectSlotsByName(MainWindow)

    def retranslateUi(self, MainWindow):
        MainWindow.setWindowTitle(QtCore.QCoreApplication.translate("MainWindow", "树莓派小车控制上位机"))
        self.label_video.setText(QtCore.QCoreApplication.translate("MainWindow", "等待视频连接..."))