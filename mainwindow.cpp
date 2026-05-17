#include "mainwindow.h"
#include "ui_mainwindow.h"
#include <QMessageBox>
#include <QImage>
#include <QPixmap>

MainWindow::MainWindow(QWidget *parent)
    : QMainWindow(parent)
    , ui(new Ui::MainWindow)
{
    ui->setupUi(this);
    setWindowTitle("树莓派小车控制器");

    // 初始化对象
    m_tcpSocket = new QTcpSocket(this);
    m_netMgr = new QNetworkAccessManager(this);
    m_videoTimer = new QTimer(this);
    m_videoTimer->setInterval(20); // 20ms拉取一次截图

    // 关键：在定时器的lambda里直接处理视频请求，避免信号槽参数不匹配
    connect(m_videoTimer, &QTimer::timeout, this, [this](){
        QNetworkReply *reply = m_netMgr->get(QNetworkRequest(QUrl(VIDEO_URL)));

        // 直接在lambda里处理请求完成，不用额外的槽函数
        connect(reply, &QNetworkReply::finished, this, [=](){
            if(reply->error() == QNetworkReply::NoError){
                QByteArray data = reply->readAll();
                QImage img;
                if(img.loadFromData(data)){
                    ui->label_video->setPixmap(
                        QPixmap::fromImage(img).scaled(
                            ui->label_video->size(),
                            Qt::KeepAspectRatio,
                            Qt::SmoothTransformation
                            )
                        );
                }
            }
            reply->deleteLater(); // 释放请求资源
        });
    });
}

MainWindow::~MainWindow()
{
    m_videoTimer->stop();
    if(m_tcpSocket->isOpen()){
        m_tcpSocket->close();
    }
    delete ui;
}

// 连接小车
void MainWindow::on_btn_connect_clicked()
{
    m_tcpSocket->connectToHost(CAR_IP, CAR_PORT);
    if(m_tcpSocket->waitForConnected(3000)){
        QMessageBox::information(this, "成功", "小车连接成功！");
        m_videoTimer->start(); // 启动视频轮询
    }else{
        QMessageBox::critical(this, "错误", "连接失败：" + m_tcpSocket->errorString());
    }
}

// 断开连接
void MainWindow::on_btn_disconnect_clicked()
{
    m_videoTimer->stop();
    if(m_tcpSocket->isOpen()){
        m_tcpSocket->close();
    }
    ui->label_video->setText("视频已断开");
    QMessageBox::warning(this, "提示", "已断开连接");
}

// 发送指令（和Python一致）
void MainWindow::sendCommand(const char cmd)
{
    if(!m_tcpSocket->isOpen()){
        QMessageBox::warning(this, "提示", "请先连接小车！");
        return;
    }

    QByteArray data;
    data.append("ON");
    data.append(cmd);
    m_tcpSocket->write(data);
    m_tcpSocket->flush();
}

// ==================== 小车控制 ====================
void MainWindow::on_btn_forward_clicked()  { sendCommand('A'); }
void MainWindow::on_btn_backward_clicked() { sendCommand('B'); }
void MainWindow::on_btn_left_clicked()     { sendCommand('C'); }
void MainWindow::on_btn_right_clicked()    { sendCommand('D'); }
void MainWindow::on_btn_stop_clicked()      { sendCommand('E'); }

// ==================== 舵机控制 ====================
void MainWindow::on_btn_servo_up_clicked()    { sendCommand('J'); }
void MainWindow::on_btn_servo_down_clicked()  { sendCommand('K'); }
void MainWindow::on_btn_servo_left_clicked()  { sendCommand('L'); }
void MainWindow::on_btn_servo_right_clicked() { sendCommand('I'); }
