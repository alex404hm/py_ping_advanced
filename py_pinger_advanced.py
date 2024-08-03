import sys
import time
import psutil
import socket
import requests
from PyQt5.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QWidget, QPushButton, 
                             QLabel, QProgressBar, QTextEdit, QTabWidget, QTreeWidget, QTreeWidgetItem, 
                             QStyle, QStatusBar, QMenuBar, QAction, QFileDialog, QLineEdit)
from PyQt5.QtCore import QThread, pyqtSignal, Qt, QTimer, QSettings
from PyQt5.QtGui import QFont, QIcon, QColor
from PyQt5.QtChart import QChart, QChartView, QLineSeries, QValueAxis
import speedtest as st

class SpeedTestThread(QThread):
    update_signal = pyqtSignal(float, float, float)

    def run(self):
        s = st.Speedtest()
        download = s.download() / 1_000_000
        upload = s.upload() / 1_000_000
        ping = s.results.ping
        self.update_signal.emit(download, upload, ping)

class NetworkMonitorThread(QThread):
    update_signal = pyqtSignal(list)

    def run(self):
        old_value = psutil.net_io_counters().bytes_recv
        while True:
            time.sleep(1)
            new_value = psutil.net_io_counters().bytes_recv
            download_speed = (new_value - old_value) / 1024 / 1024  # MB/s
            connections = psutil.net_connections()
            active_connections = [conn for conn in connections if conn.status == 'ESTABLISHED']
            self.update_signal.emit([download_speed, active_connections])
            old_value = new_value

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Advanced Network Monitor")
        self.setGeometry(100, 100, 1000, 700)
        self.setStyleSheet("""
            QMainWindow {background-color: #f0f0f0;}
            QLabel {font-size: 14px;}
            QPushButton {font-size: 14px; padding: 5px; background-color: #4CAF50; color: white; border: none; border-radius: 3px;}
            QPushButton:hover {background-color: #45a049;}
            QProgressBar {border: 2px solid grey; border-radius: 5px; text-align: center;}
            QProgressBar::chunk {background-color: #4CAF50; width: 10px; margin: 0.5px;}
            QTabWidget::pane {border: 1px solid #cccccc; background-color: white;}
            QTabBar::tab {background-color: #e1e1e1; padding: 5px;}
            QTabBar::tab:selected {background-color: white;}
        """)

        self.settings = QSettings("YourCompany", "AdvancedNetworkMonitor")

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        self.create_menu_bar()

        # Create tabs
        self.tabs = QTabWidget()
        self.speed_test_tab = QWidget()
        self.network_monitor_tab = QWidget()
        self.ip_info_tab = QWidget()
        self.tabs.addTab(self.speed_test_tab, "Speed Test")
        self.tabs.addTab(self.network_monitor_tab, "Network Monitor")
        self.tabs.addTab(self.ip_info_tab, "IP Information")

        self.setup_speed_test_tab()
        self.setup_network_monitor_tab()
        self.setup_ip_info_tab()

        main_layout.addWidget(self.tabs)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")

        self.speed_test_thread = SpeedTestThread()
        self.speed_test_thread.update_signal.connect(self.update_speed_test_results)

        self.network_monitor_thread = NetworkMonitorThread()
        self.network_monitor_thread.update_signal.connect(self.update_network_monitor)
        self.network_monitor_thread.start()

        self.load_settings()

    def create_menu_bar(self):
        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu("File")
        
        save_action = QAction("Save Results", self)
        save_action.triggered.connect(self.save_results)
        file_menu.addAction(save_action)
        
        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

    def setup_speed_test_tab(self):
        layout = QVBoxLayout(self.speed_test_tab)

        self.download_label = QLabel("Download Speed: N/A")
        self.upload_label = QLabel("Upload Speed: N/A")
        self.ping_label = QLabel("Ping: N/A")

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)

        self.test_button = QPushButton("Run Speed Test")
        self.test_button.setIcon(self.style().standardIcon(QStyle.SP_BrowserReload))
        self.test_button.clicked.connect(self.run_speed_test)

        self.speed_chart = QChart()
        self.speed_chart.setTitle("Speed Test History")
        self.download_series = QLineSeries()
        self.upload_series = QLineSeries()
        self.speed_chart.addSeries(self.download_series)
        self.speed_chart.addSeries(self.upload_series)
        self.speed_chart.createDefaultAxes()
        self.speed_chart.axes(Qt.Horizontal)[0].setTitleText("Test Number")
        self.speed_chart.axes(Qt.Vertical)[0].setTitleText("Speed (Mbps)")
        self.chart_view = QChartView(self.speed_chart)

        layout.addWidget(self.download_label)
        layout.addWidget(self.upload_label)
        layout.addWidget(self.ping_label)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.test_button)
        layout.addWidget(self.chart_view)

    def setup_network_monitor_tab(self):
        layout = QVBoxLayout(self.network_monitor_tab)

        self.current_download_speed = QLabel("Current Download Speed: N/A")
        self.active_connections_tree = QTreeWidget()
        self.active_connections_tree.setHeaderLabels(["Local Address", "Local Port", "Remote Address", "Remote Port", "Status"])

        layout.addWidget(self.current_download_speed)
        layout.addWidget(QLabel("Active Connections:"))
        layout.addWidget(self.active_connections_tree)

    def setup_ip_info_tab(self):
        layout = QVBoxLayout(self.ip_info_tab)

        self.local_ip_label = QLabel(f"Local IP: {self.get_local_ip()}")
        self.public_ip_label = QLabel("Public IP: Fetching...")
        self.ip_info_text = QTextEdit()
        self.ip_info_text.setReadOnly(True)

        layout.addWidget(self.local_ip_label)
        layout.addWidget(self.public_ip_label)
        layout.addWidget(QLabel("IP Information:"))
        layout.addWidget(self.ip_info_text)

        self.fetch_public_ip()

    def get_local_ip(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
            return local_ip
        except:
            return "Unable to determine local IP"

    def fetch_public_ip(self):
        try:
            public_ip = requests.get('https://api.ipify.org').text
            self.public_ip_label.setText(f"Public IP: {public_ip}")
            self.fetch_ip_info(public_ip)
        except:
            self.public_ip_label.setText("Public IP: Unable to fetch")

    def fetch_ip_info(self, ip):
        try:
            response = requests.get(f'http://ip-api.com/json/{ip}')
            data = response.json()
            info = f"Country: {data['country']}\n"
            info += f"Region: {data['regionName']}\n"
            info += f"City: {data['city']}\n"
            info += f"ISP: {data['isp']}\n"
            info += f"Organization: {data['org']}\n"
            info += f"Latitude: {data['lat']}\n"
            info += f"Longitude: {data['lon']}"
            self.ip_info_text.setText(info)
        except:
            self.ip_info_text.setText("Unable to fetch IP information")

    def run_speed_test(self):
        self.test_button.setEnabled(False)
        self.progress_bar.setValue(0)
        self.speed_test_thread.start()
        self.simulate_progress()

    def simulate_progress(self):
        self.progress_bar.setValue(0)
        for i in range(1, 101):
            time.sleep(0.1)
            self.progress_bar.setValue(i)
            QApplication.processEvents()

    def update_speed_test_results(self, download, upload, ping):
        self.download_label.setText(f"Download Speed: {download:.2f} Mbps")
        self.upload_label.setText(f"Upload Speed: {upload:.2f} Mbps")
        self.ping_label.setText(f"Ping: {ping:.2f} ms")
        self.test_button.setEnabled(True)
        self.update_speed_chart(download, upload)

    def update_speed_chart(self, download, upload):
        self.download_series.append(self.download_series.count(), download)
        self.upload_series.append(self.upload_series.count(), upload)
        self.speed_chart.axes(Qt.Horizontal)[0].setRange(0, max(self.download_series.count(), self.upload_series.count()))
        self.speed_chart.axes(Qt.Vertical)[0].setRange(0, max(self.download_series.at(self.download_series.count()-1).y(), 
                                                              self.upload_series.at(self.upload_series.count()-1).y()))

    def update_network_monitor(self, data):
        download_speed, active_connections = data
        self.current_download_speed.setText(f"Current Download Speed: {download_speed:.2f} MB/s")
        
        self.active_connections_tree.clear()
        for conn in active_connections:
            item = QTreeWidgetItem(self.active_connections_tree)
            item.setText(0, conn.laddr.ip)
            item.setText(1, str(conn.laddr.port))
            item.setText(2, conn.raddr.ip if conn.raddr else "N/A")
            item.setText(3, str(conn.raddr.port) if conn.raddr else "N/A")
            item.setText(4, conn.status)

    def save_results(self):
        file_name, _ = QFileDialog.getSaveFileName(self, "Save Results", "", "Text Files (*.txt);;All Files (*)")
        if file_name:
            with open(file_name, 'w') as f:
                f.write(f"Download Speed: {self.download_label.text()}\n")
                f.write(f"Upload Speed: {self.upload_label.text()}\n")
                f.write(f"Ping: {self.ping_label.text()}\n")
                f.write(f"Local IP: {self.local_ip_label.text()}\n")
                f.write(f"Public IP: {self.public_ip_label.text()}\n")
                f.write(f"IP Information:\n{self.ip_info_text.toPlainText()}")
            self.status_bar.showMessage("Results saved successfully", 3000)

    def load_settings(self):
        geometry = self.settings.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)

    def closeEvent(self, event):
        self.settings.setValue("geometry", self.saveGeometry())
        super().closeEvent(event)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
