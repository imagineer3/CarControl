#ifndef MAINWINDOW_H
#define MAINWINDOW_H

#include <QMainWindow>
#include <QTcpSocket>
#include <QNetworkAccessManager>
#include <QNetworkReply>
#include <QTimer>

QT_BEGIN_NAMESPACE
namespace Ui { class MainWindow; }
QT_END_NAMESPACE

class MainWindow : public QMainWindow
{
    Q_OBJECT

public:
    MainWindow(QWidget *parent = nullptr);
    ~MainWindow();

private slots:
    // 连接/断开
    void on_btn_connect_clicked();
    void on_btn_disconnect_clicked();

    // 小车控制
    void on_btn_forward_clicked();
    void on_btn_backward_clicked();
    void on_btn_left_clicked();
    void on_btn_right_clicked();
    void on_btn_stop_clicked();

    // 舵机控制
    void on_btn_servo_up_clicked();
    void on_btn_servo_down_clicked();
    void on_btn_servo_left_clicked();
    void on_btn_servo_right_clicked();

private:
    Ui::MainWindow *ui;
    QTcpSocket *m_tcpSocket;
    QNetworkAccessManager *m_netMgr;
    QTimer *m_videoTimer;

    // 你的配置（改成自己的IP/端口）
    const QString CAR_IP     = "192.168.1.1";
    const quint16 CAR_PORT   = 2001;
    const QString VIDEO_URL  = "http://" + CAR_IP + ":8080/?action=snapshot";

    void sendCommand(const char cmd);
};

#endif // MAINWINDOW_H
