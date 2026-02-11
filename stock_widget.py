# -*- coding: utf-8 -*-
"""
桌面股票监控小工具
无边框透明窗口，可拖动位置
"""

import sys
import json
import requests
from datetime import datetime
from PyQt5.QtWidgets import (QApplication, QWidget, QLabel, QVBoxLayout,
                             QHBoxLayout, QPushButton, QSystemTrayIcon, QMenu,
                             QAction, QDialog, QListWidget, QLineEdit, QMessageBox,
                             QListWidgetItem, QAbstractItemView, QScrollArea,
                             QSlider, QSpinBox, QGridLayout)
from PyQt5.QtCore import Qt, QTimer, QPoint, QRegExp
from PyQt5.QtGui import QFont, QColor, QIcon, QDoubleValidator, QIntValidator, QRegExpValidator

# 导入matplotlib用于绘制图表
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.pyplot as plt
from matplotlib.dates import DateFormatter, HourLocator, MinuteLocator
import datetime


class ClickableLabel(QLabel):
    """可点击的标签，用于显示股票信息"""

    def __init__(self, stock_code, stock_name, parent=None):
        super().__init__(parent)
        self.stock_code = stock_code
        self.stock_name = stock_name
        self.callback = None

    def mousePressEvent(self, event):
        """鼠标点击事件"""
        if event.button() == Qt.LeftButton and self.callback:
            self.callback(self.stock_code, self.stock_name)
        super().mousePressEvent(event)

    def set_clicked_callback(self, callback):
        """设置点击回调函数"""
        self.callback = callback


class StockInfoWidget:
    """股票信息数据类"""
    def __init__(self, code: str, name: str, price: float,
                 change: float, change_percent: float, open_price: float):
        self.code = code
        self.name = name
        self.price = price
        self.change = change
        self.change_percent = change_percent
        self.open_price = open_price


class StockManageDialog(QDialog):
    """股票管理对话框 - 支持添加、删除、搜索股票"""

    def __init__(self, current_stocks: list, parent=None):
        super().__init__(parent)
        self.current_stocks = current_stocks[:]  # 复制一份
        self.stock_names = {}  # 存储代码到名称的映射
        self.search_results = []
        self.load_stock_names()  # 先加载股票名称
        self.init_ui()

    def load_stock_names(self):
        """加载当前股票的名称"""
        parent = self.parent()
        if parent and hasattr(parent, 'get_stock_price'):
            for code in self.current_stocks:
                info = parent.get_stock_price(code)
                if info:
                    self.stock_names[code] = info.name
                else:
                    self.stock_names[code] = code

    def init_ui(self):
        """初始化界面"""
        self.setWindowTitle('股票管理')
        self.setFixedSize(500, 400)
        self.setStyleSheet('''
            QDialog {
                background-color: #ffffff;
            }
            QLabel {
                color: #000000;
                font-size: 14px;
            }
            QPushButton {
                background-color: #0078d4;
                color: #ffffff;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #106ebe;
            }
            QListWidget {
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                background-color: #fafafa;
                font-size: 13px;
            }
            QListWidget::item {
                padding: 8px;
            }
            QListWidget::item:selected {
                background-color: #0078d4;
                color: #ffffff;
            }
            QLineEdit {
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                padding: 6px 10px;
                font-size: 13px;
                background-color: #fafafa;
            }
            QLineEdit:focus {
                border: 1px solid #0078d4;
            }
        ''')

        layout = QVBoxLayout()
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)

        # 当前股票列表
        layout.addWidget(QLabel('当前监控的股票：'))
        self.current_list = QListWidget()
        self.current_list.setSelectionMode(QAbstractItemView.SingleSelection)
        # 启用拖拽排序
        self.current_list.setDragEnabled(True)
        self.current_list.setDragDropMode(QAbstractItemView.InternalMove)
        self.current_list.setDefaultDropAction(Qt.MoveAction)
        self.current_list.model().rowsMoved.connect(self.on_rows_moved)
        self.refresh_current_list()
        layout.addWidget(self.current_list)

        # 搜索区域
        search_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText('输入股票代码或名称搜索...')
        self.search_input.returnPressed.connect(self.do_search)
        search_layout.addWidget(self.search_input)

        self.search_btn = QPushButton('🔍 搜索')
        self.search_btn.clicked.connect(self.do_search)
        search_layout.addWidget(self.search_btn)
        layout.addLayout(search_layout)

        # 搜索结果
        self.result_list = QListWidget()
        self.result_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.result_list.itemDoubleClicked.connect(self.add_selected_stock)
        layout.addWidget(self.result_list)

        # 按钮区域
        btn_layout = QHBoxLayout()

        self.add_btn = QPushButton('➕ 添加选中')
        self.add_btn.clicked.connect(self.add_selected_stock)
        btn_layout.addWidget(self.add_btn)

        self.remove_btn = QPushButton('➖ 删除选中')
        self.remove_btn.clicked.connect(self.remove_selected_stock)
        btn_layout.addWidget(self.remove_btn)

        btn_layout.addStretch()

        self.ok_btn = QPushButton('✓ 确定')
        self.ok_btn.clicked.connect(self.accept)
        btn_layout.addWidget(self.ok_btn)

        self.cancel_btn = QPushButton('✗ 取消')
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.cancel_btn)

        layout.addLayout(btn_layout)
        self.setLayout(layout)

    def do_search(self):
        """执行搜索"""
        keyword = self.search_input.text().strip()
        if not keyword:
            return

        self.result_list.clear()
        self.search_results = []

        # 先尝试直接输入股票代码
        if len(keyword) == 6 and keyword.isdigit():
            self.search_results.append({'code': keyword, 'name': '直接添加', 'pinyin': ''})
        else:
            # 调用父窗口的搜索方法
            parent = self.parent()
            if parent and hasattr(parent, 'search_stocks'):
                self.search_results = parent.search_stocks(keyword)

        # 显示搜索结果
        for item in self.search_results[:20]:  # 最多显示20条
            display_text = f"{item['code']} - {item['name']}"
            self.result_list.addItem(display_text)

    def add_selected_stock(self):
        """添加选中的股票"""
        current_item = self.result_list.currentItem()
        if not current_item:
            QMessageBox.warning(self, '提示', '请先选择要添加的股票')
            return

        row = self.result_list.currentRow()
        if row < len(self.search_results):
            code = self.search_results[row]['code']
            name = self.search_results[row]['name']
            if code not in self.current_stocks:
                self.current_stocks.append(code)
                self.stock_names[code] = name
                self.refresh_current_list()
                QMessageBox.information(self, '成功', f'已添加股票: {code} - {name}')
            else:
                QMessageBox.information(self, '提示', '该股票已在列表中')

    def remove_selected_stock(self):
        """删除选中的股票"""
        current_item = self.current_list.currentItem()
        if not current_item:
            QMessageBox.warning(self, '提示', '请先选择要删除的股票')
            return

        # 从 "代码 - 名称" 格式中提取代码
        text = current_item.text()
        code = text.split(' - ')[0] if ' - ' in text else text

        if code in self.current_stocks:
            self.current_stocks.remove(code)
            if code in self.stock_names:
                del self.stock_names[code]
            self.refresh_current_list()

    def get_stocks(self):
        """获取更新后的股票列表"""
        return self.current_stocks

    def refresh_current_list(self):
        """刷新当前股票列表显示"""
        self.current_list.clear()
        for code in self.current_stocks:
            name = self.stock_names.get(code, code)
            self.current_list.addItem(f'{code} - {name}')

    def on_rows_moved(self, parent, start, end, destination, row):
        """拖拽排序后更新股票列表顺序"""
        # 重建股票列表顺序
        new_order = []
        for i in range(self.current_list.count()):
            item_text = self.current_list.item(i).text()
            code = item_text.split(' - ')[0] if ' - ' in item_text else item_text
            if code in self.current_stocks:
                new_order.append(code)

        # 移除重复，保持原有顺序
        seen = set()
        self.current_stocks = []
        for code in new_order:
            if code not in seen:
                self.current_stocks.append(code)
                seen.add(code)


class SettingsDialog(QDialog):
    """设置对话框 - 支持配置透明度、刷新间隔等"""

    def __init__(self, opacity: float, refresh_interval: int, parent=None):
        super().__init__(parent)
        self.opacity = opacity
        self.refresh_interval = refresh_interval
        self.init_ui()

    def init_ui(self):
        """初始化界面"""
        self.setWindowTitle('设置')
        self.setFixedSize(350, 250)
        self.setStyleSheet('''
            QDialog {
                background-color: #ffffff;
            }
            QLabel {
                color: #000000;
                font-size: 14px;
            }
            QPushButton {
                background-color: #0078d4;
                color: #ffffff;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #106ebe;
            }
            QSlider::groove:horizontal {
                height: 8px;
                background: #e0e0e0;
                border-radius: 4px;
            }
            QSlider::handle:horizontal {
                background: #0078d4;
                border: none;
                width: 18px;
                height: 18px;
                margin: -5px 0;
                border-radius: 9px;
                border-radius: 9px;
            }
            QSpinBox {
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 13px;
            }
        ''')

        layout = QVBoxLayout()
        layout.setSpacing(20)
        layout.setContentsMargins(20, 20, 20, 20)

        # 透明度设置
        opacity_layout = QHBoxLayout()
        opacity_label = QLabel('窗口透明度：')
        opacity_label.setStyleSheet('font-size: 14px;')
        opacity_layout.addWidget(opacity_label)

        self.opacity_value_label = QLabel(f'{int(self.opacity * 100)}%')
        self.opacity_value_label.setStyleSheet('font-size: 14px; font-weight: bold; color: #0078d4;')
        opacity_layout.addWidget(self.opacity_value_label)

        self.opacity_slider = QSlider(Qt.Horizontal)
        self.opacity_slider.setMinimum(50)
        self.opacity_slider.setMaximum(100)
        self.opacity_slider.setValue(int(self.opacity * 100))
        self.opacity_slider.setFixedWidth(150)
        self.opacity_slider.valueChanged.connect(self.on_opacity_changed)
        opacity_layout.addWidget(self.opacity_slider)
        layout.addLayout(opacity_layout)

        # 刷新间隔设置
        interval_layout = QHBoxLayout()
        interval_label = QLabel('刷新间隔（秒）：')
        interval_label.setStyleSheet('font-size: 14px;')
        interval_layout.addWidget(interval_label)

        self.interval_spinbox = QSpinBox()
        self.interval_spinbox.setMinimum(1)
        self.interval_spinbox.setMaximum(60)
        self.interval_spinbox.setValue(self.refresh_interval)
        self.interval_spinbox.setSuffix(' 秒')
        self.interval_spinbox.setFixedWidth(100)
        interval_layout.addWidget(self.interval_spinbox)
        interval_layout.addStretch()
        layout.addLayout(interval_layout)

        # 说明文字
        info_label = QLabel('提示：透明度50%-100%，数字越小越透明')
        info_label.setStyleSheet('color: #888888; font-size: 12px;')
        layout.addWidget(info_label)

        layout.addStretch()

        # 按钮区域
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.ok_btn = QPushButton('✓ 确定')
        self.ok_btn.clicked.connect(self.accept)
        btn_layout.addWidget(self.ok_btn)

        self.cancel_btn = QPushButton('✗ 取消')
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.cancel_btn)

        layout.addLayout(btn_layout)
        self.setLayout(layout)

    def on_opacity_changed(self, value):
        """透明度滑块值变化"""
        self.opacity = value / 100
        self.opacity_value_label.setText(f'{value}%')
        # 实时预览透明度
        if self.parent():
            self.parent().setWindowOpacity(self.opacity)

    def get_settings(self):
        """获取设置"""
        return self.opacity, self.interval_spinbox.value()


class TCalculatorDialog(QDialog):
    """做T计算器对话框"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('做T计算器')
        self.setFixedSize(380, 200)
        self.setStyleSheet('''
            QDialog {
                background-color: #ffffff;
            }
            QLineEdit {
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                padding: 4px 10px;
                min-height: 12px;
                font-size: 12px;
                background-color: #fafafa;
            }
            QLineEdit:focus {
                border: 1px solid #0078d4;
                background-color: #ffffff;
            }
            QPushButton {
                background-color: #0078d4;
                color: #ffffff;
                border: none;
                padding: 6px 15px;
                min-height: 28px;
                font-size: 14px;
                border-radius: 4px;
                min-width: 70px;
                max-width: 70px;
            }
            QPushButton:hover {
                background-color: #106ebe;
            }
            QLabel {
                font-size: 14px;
                color: #000000;
            }
        ''')
        self.init_ui()

    def init_ui(self):
        """初始化界面"""
        layout = QVBoxLayout()
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        # 输入区域
        input_layout = QGridLayout()
        input_layout.setSpacing(10)
        input_layout.setColumnStretch(0, 0)
        input_layout.setColumnStretch(1, 1)

        # 买入价
        buy_label = QLabel('买入价:')
        buy_label.setFixedWidth(55)
        buy_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.buy_input = QLineEdit()
        self.buy_input.setMinimumWidth(200)
        self.buy_input.setMaximumWidth(250)
        self.buy_input.setPlaceholderText('请输入买入价格')
        self.buy_input.setValidator(QDoubleValidator(0.0, 1000000.0, 2))
        self.buy_input.textChanged.connect(self.calculate)
        input_layout.addWidget(buy_label, 0, 0)
        input_layout.addWidget(self.buy_input, 0, 1)

        # 卖出价
        sell_label = QLabel('卖出价:')
        sell_label.setFixedWidth(55)
        sell_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.sell_input = QLineEdit()
        self.sell_input.setMinimumWidth(200)
        self.sell_input.setMaximumWidth(250)
        self.sell_input.setPlaceholderText('请输入卖出价格')
        self.sell_input.setValidator(QDoubleValidator(0.0, 1000000.0, 2))
        self.sell_input.textChanged.connect(self.calculate)
        input_layout.addWidget(sell_label, 1, 0)
        input_layout.addWidget(self.sell_input, 1, 1)

        # 数量
        quantity_label = QLabel('数量:')
        quantity_label.setFixedWidth(55)
        quantity_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.quantity_input = QLineEdit()
        self.quantity_input.setMinimumWidth(200)
        self.quantity_input.setMaximumWidth(250)
        self.quantity_input.setPlaceholderText('请输入数量(自动乘100)')
        self.quantity_input.setValidator(QRegExpValidator(QRegExp('^[0-9]*$')))
        self.quantity_input.textChanged.connect(self.calculate)
        input_layout.addWidget(quantity_label, 2, 0)
        input_layout.addWidget(self.quantity_input, 2, 1)
        
        # 数量单位提示
        unit_label = QLabel('×100股')
        unit_label.setStyleSheet('font-size: 12px; color: #999;')
        input_layout.addWidget(unit_label, 2, 2)

        layout.addLayout(input_layout)

        # 结果显示
        self.result_label = QLabel('盈亏: ¥0.00 (0.00%)')
        layout.addWidget(self.result_label, alignment=Qt.AlignCenter)

        # 按钮区域
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.clear_btn = QPushButton('清空')
        self.clear_btn.clicked.connect(self.clear)
        btn_layout.addWidget(self.clear_btn)

        self.close_btn = QPushButton('关闭')
        self.close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(self.close_btn)

        layout.addLayout(btn_layout)
        self.setLayout(layout)

    def calculate(self):
        """计算做T盈亏"""
        try:
            buy_price = float(self.buy_input.text()) if self.buy_input.text() else 0
            sell_price = float(self.sell_input.text()) if self.sell_input.text() else 0
            quantity = int(self.quantity_input.text()) * 100 if self.quantity_input.text() else 0

            if buy_price > 0 and sell_price > 0 and quantity > 0:
                profit = (sell_price - buy_price) * quantity
                profit_percent = (sell_price - buy_price) / buy_price * 100

                if profit >= 0:
                    color = '#ff4d4f'
                    sign = '+'
                else:
                    color = '#52c41a'
                    sign = ''

                self.result_label.setText(f'盈亏: {sign}¥{profit:.2f} ({sign}{profit_percent:.2f}%)')
                self.result_label.setStyleSheet(f'font-size: 16px; font-weight: bold; color: {color};')
            else:
                self.result_label.setText('盈亏: ¥0.00 (0.00%)')
                self.result_label.setStyleSheet('font-size: 16px; font-weight: bold; color: #000000;')
        except ValueError:
            self.result_label.setText('盈亏: ¥0.00 (0.00%)')
            self.result_label.setStyleSheet('font-size: 16px; font-weight: bold; color: #000000;')

    def on_quantity_changed(self):
        """数量输入变化处理，自动调整为100的倍数"""
        text = self.quantity_input.text()
        if text:
            try:
                num = int(text)
                if num > 0:
                    rounded = (num // 100) * 100
                    if rounded == 0:
                        rounded = 100
                    self.quantity_input.blockSignals(True)
                    self.quantity_input.setText(str(rounded))
                    self.quantity_input.blockSignals(False)
                self.calculate()
            except ValueError:
                pass

    def clear(self):
        """清空输入"""
        self.buy_input.clear()
        self.sell_input.clear()
        self.quantity_input.clear()
        self.calculate()


class StockDetailDialog(QDialog):
    """股票详情对话框 - 展示分时走势图和成交量"""

    def __init__(self, stock_code: str, stock_name: str, parent=None):
        super().__init__(parent)
        self.stock_code = stock_code
        self.stock_name = stock_name
        self.time_data = []  # 时间数据
        self.price_data = []  # 价格数据
        self.volume_data = []  # 成交量数据
        self.init_ui()
        self.load_intraday_data()

    def init_ui(self):
        """初始化界面"""
        self.setWindowTitle(f'{self.stock_code} - {self.stock_name}')
        self.setFixedSize(800, 600)
        self.setStyleSheet('''
            QDialog {
                background-color: #ffffff;
            }
            QPushButton {
                background-color: #0078d4;
                color: #ffffff;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #106ebe;
            }
        ''')

        layout = QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # 标题
        title_label = QLabel(f'{self.stock_code} - {self.stock_name}  分时走势')
        title_label.setStyleSheet('font-size: 16px; font-weight: bold; color: #000000;')
        layout.addWidget(title_label)

        # 创建matplotlib图表
        self.figure = Figure(figsize=(8, 6), dpi=100)
        self.canvas = FigureCanvas(self.figure)

        # 创建两个子图：价格走势和成交量
        self.ax_price = self.figure.add_subplot(211)
        self.ax_volume = self.figure.add_subplot(212, sharex=self.ax_price)

        self.figure.subplots_adjust(hspace=0.1, left=0.08, right=0.95, top=0.95, bottom=0.08)

        layout.addWidget(self.canvas)

        # 关闭按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.close_btn = QPushButton('关闭')
        self.close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(self.close_btn)

        layout.addLayout(btn_layout)
        self.setLayout(layout)

    def load_intraday_data(self):
        """加载分时数据"""
        try:
            code_prefix = "sh" if self.stock_code.startswith("6") else "sz"
            # 新浪分时数据API
            api_url = f"http://hq.sinajs.cn/list={code_prefix}{self.stock_code}"

            response = requests.get(api_url, timeout=5)
            response.encoding = 'gbk'

            if response.status_code == 200:
                content = response.text.strip()
                if '=' in content and '"' in content:
                    data_str = content.split('"')[1]
                    parts = data_str.split(',')

                    if len(parts) > 32:
                        # 获取当前价格、昨收、今开、最高、最低
                        current_price = float(parts[3])
                        prev_close = float(parts[2])
                        open_price = float(parts[1])
                        high_price = float(parts[4])
                        low_price = parts[5]

                        # 模拟生成分时数据（实际API需要更复杂的处理）
                        # 这里使用模拟数据展示图表功能
                        self.generate_mock_intraday_data(prev_close, open_price)
                        self.plot_charts(current_price, prev_close, open_price)
        except Exception as e:
            print(f"获取分时数据失败: {e}")
            # 加载失败时显示模拟数据
            self.generate_mock_intraday_data(100.0, 101.0)
            self.plot_charts(101.5, 100.0, 101.0)

    def generate_mock_intraday_data(self, prev_close: float, open_price: float):
        """生成模拟分时数据（实际应从API获取）"""
        base_price = open_price
        base_time = datetime.datetime.now().replace(hour=9, minute=30, second=0, microsecond=0)

        for i in range(240):  # 4小时交易时间，每分钟一个点
            current_time = base_time + datetime.timedelta(minutes=i)
            # 模拟价格波动
            price_change = (i - 120) * 0.01 * (prev_close / 100)
            price = base_price + price_change + (i % 10) * 0.02

            # 模拟成交量
            volume = abs(int((100000 + i * 500 + (i % 20) * 1000) * (1 + 0.1 * (i % 3 - 1))))

            # 跳过午休时间 11:30-13:00
            if 9.5 <= (current_time.hour + current_time.minute / 60) < 11.5 or \
               13 <= (current_time.hour + current_time.minute / 60) < 15:
                self.time_data.append(current_time)
                self.price_data.append(price)
                self.volume_data.append(volume)

    def plot_charts(self, current_price: float, prev_close: float, open_price: float):
        """绘制图表"""
        # 清空之前的图表
        self.ax_price.clear()
        self.ax_volume.clear()

        if not self.time_data:
            self.ax_price.text(0.5, 0.5, '暂无数据',
                              ha='center', va='center', fontsize=14)
            self.canvas.draw()
            return

        # 计算价格颜色
        price_color = '#ff4d4f' if current_price >= prev_close else '#52c41a'

        # 绘制价格走势
        self.ax_price.plot(self.time_data, self.price_data,
                          color=price_color, linewidth=1.5, label='价格')
        self.ax_price.axhline(y=prev_close, color='gray', linestyle='--',
                             linewidth=0.8, alpha=0.5, label='昨收')
        self.ax_price.set_ylabel('价格', fontsize=10)
        self.ax_price.grid(True, alpha=0.3)
        self.ax_price.legend(loc='upper left', fontsize=8)

        # 绘制成交量（柱状图）
        colors = ['#ff4d4f' if i > 0 and self.price_data[i] >= self.price_data[i-1]
                 else '#52c41a' for i in range(len(self.time_data))]
        colors[0] = '#ff4d4f' if self.price_data[0] >= prev_close else '#52c41a'

        self.ax_volume.bar(self.time_data, self.volume_data, color=colors,
                          width=0.0005, alpha=0.7)
        self.ax_volume.set_ylabel('成交量', fontsize=10)
        self.ax_volume.set_xlabel('时间', fontsize=10)
        self.ax_volume.grid(True, alpha=0.3, axis='y')

        # 设置x轴格式
        self.ax_volume.xaxis.set_major_locator(MinuteLocator(interval=30))
        self.ax_volume.xaxis.set_major_formatter(DateFormatter('%H:%M'))

        # 旋转x轴标签
        for label in self.ax_volume.get_xticklabels():
            label.set_rotation(45)
            label.set_fontsize(8)

        self.figure.autofmt_xdate()
        self.canvas.draw()


class StockDesktopWidget(QWidget):
    """桌面股票监控窗口"""

    def __init__(self):
        super().__init__()
        self.stocks = []
        self.stock_widgets = []
        self.drag_position = None
        self.window_opacity = 0.85  # 默认透明度
        self.refresh_interval = 5  # 默认刷新间隔（秒）
        self.init_ui()
        self.load_config()
        self.setup_timer()
        self.setup_system_tray()

    def init_ui(self):
        """初始化界面"""
        # 窗口设置
        self.setWindowTitle('股票监控')
        # 移除 Qt.Tool 标志，这样窗口会显示在任务栏中
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setWindowOpacity(0.85)  # 设置窗口透明度 (0-1，1为不透明)

        # 主布局（包含标题栏+滚动区域）
        self.main_layout = QVBoxLayout()
        self.main_layout.setSpacing(5)
        self.main_layout.setContentsMargins(15, 15, 15, 15)

        # 标题栏
        title_layout = QHBoxLayout()
        self.title_label = QLabel('📈 股票监控')
        self.title_label.setFont(QFont('Microsoft YaHei', 12, QFont.Bold))
        self.title_label.setStyleSheet('color: #000000;')
        title_layout.addWidget(self.title_label)
        title_layout.addStretch()

        # 做T计算器按钮
        self.calculator_btn = QPushButton('💰')
        self.calculator_btn.setFixedSize(30, 30)
        self.calculator_btn.setStyleSheet('''
            QPushButton {
                background: transparent;
                color: #000000;
                font-size: 16px;
                border: none;
            }
            QPushButton:hover {
                background: #0078d4;
                color: #ffffff;
                border-radius: 15px;
            }
        ''')
        self.calculator_btn.clicked.connect(self.show_calculator_dialog)
        title_layout.addWidget(self.calculator_btn)

        # 管理按钮
        self.manage_btn = QPushButton('⚙')
        self.manage_btn.setFixedSize(30, 30)
        self.manage_btn.setStyleSheet('''
            QPushButton {
                background: transparent;
                color: #000000;
                font-size: 16px;
                border: none;
            }
            QPushButton:hover {
                background: #0078d4;
                color: #ffffff;
                border-radius: 15px;
            }
        ''')
        self.manage_btn.clicked.connect(self.show_manage_dialog)
        title_layout.addWidget(self.manage_btn)

        # 设置按钮
        self.settings_btn = QPushButton('🔧')
        self.settings_btn.setFixedSize(30, 30)
        self.settings_btn.setStyleSheet('''
            QPushButton {
                background: transparent;
                color: #000000;
                font-size: 16px;
                border: none;
            }
            QPushButton:hover {
                background: #0078d4;
                color: #ffffff;
                border-radius: 15px;
            }
        ''')
        self.settings_btn.clicked.connect(self.show_settings_dialog)
        title_layout.addWidget(self.settings_btn)

        # 关闭按钮
        self.close_btn = QPushButton('×')
        self.close_btn.setFixedSize(30, 30)
        self.close_btn.setStyleSheet('''
            QPushButton {
                background: transparent;
                color: #000000;
                font-size: 20px;
                border: none;
            }
            QPushButton:hover {
                background: #e81123;
                color: #ffffff;
                border-radius: 15px;
            }
        ''')
        self.close_btn.clicked.connect(self.close)
        title_layout.addWidget(self.close_btn)

        self.main_layout.addLayout(title_layout)

        # 创建滚动区域
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QScrollArea.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        # 滚动内容的容器
        self.scroll_content = QWidget()
        self.content_layout = QVBoxLayout()
        self.content_layout.setSpacing(5)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.scroll_content.setLayout(self.content_layout)
        self.scroll_area.setWidget(self.scroll_content)

        self.main_layout.addWidget(self.scroll_area)
        self.setLayout(self.main_layout)

        # 窗口大小和样式
        self.setFixedSize(480, 350)
        self.setStyleSheet('''
            QWidget {
                background-color: #ffffff;
                border-radius: 15px;
            }
        ''')

    def load_config(self):
        """加载配置文件"""
        try:
            with open('config.json', 'r', encoding='utf-8') as f:
                config = json.load(f)
            self.stocks = config.get('stocks', [])
            self.window_opacity = config.get('opacity', 0.85)
            self.refresh_interval = config.get('refresh_interval', 5)
            # 应用加载的设置
            self.setWindowOpacity(self.window_opacity)
        except:
            # 默认股票和设置
            self.stocks = ['600519', '000001', '600036']
            self.window_opacity = 0.85
            self.refresh_interval = 5

    def save_config(self):
        """保存配置文件"""
        try:
            config = {
                'stocks': self.stocks,
                'opacity': self.window_opacity,
                'refresh_interval': self.refresh_interval
            }
            with open('config.json', 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存配置失败: {e}")

    def show_manage_dialog(self):
        """显示股票管理对话框"""
        dialog = StockManageDialog(self.stocks, self)
        if dialog.exec_() == QDialog.Accepted:
            self.stocks = dialog.get_stocks()
            self.save_config()
            self.update_stock_display()

    def show_settings_dialog(self):
        """显示设置对话框"""
        dialog = SettingsDialog(self.window_opacity, self.refresh_interval, self)
        if dialog.exec_() == QDialog.Accepted:
            self.window_opacity, self.refresh_interval = dialog.get_settings()
            self.setWindowOpacity(self.window_opacity)
            self.save_config()
            # 重启定时器
            self.timer.stop()
            self.timer.start(self.refresh_interval * 1000)

    def show_calculator_dialog(self):
        """显示做T计算器对话框"""
        dialog = TCalculatorDialog(self)
        dialog.exec_()

    def show_stock_detail(self, stock_code: str, stock_name: str):
        """显示股票详情对话框"""
        dialog = StockDetailDialog(stock_code, stock_name, self)
        dialog.exec_()

    def search_stocks(self, keyword: str) -> list:
        """搜索股票（根据代码或名称）- 使用新浪API"""
        results = []
        try:
            # 新浪股票搜索API
            # type=11:沪深A股, type=12:指数
            api_url = f"http://suggest3.sinajs.cn/suggest/type=11,12,13,14,15&key={keyword}&name=suggestdata"
            response = requests.get(api_url, timeout=5)
            response.encoding = 'gbk'

            if response.status_code == 200:
                content = response.text.strip()
                # 格式: var suggestdata="..."
                if 'suggestdata="' in content:
                    data_str = content.split('suggestdata="')[1].split('";')[0]
                    if data_str:
                        items = data_str.split(';')
                        for item in items:
                            if not item:
                                continue
                            parts = item.split(',')
                            if len(parts) >= 6:
                                # parts[0]=名称, parts[1]=类型, parts[2]=6位代码
                                code = parts[2]
                                name = parts[0]
                                if len(code) == 6 and code.isdigit():
                                    results.append({
                                        'code': code,
                                        'name': name,
                                        'pinyin': parts[5] if len(parts) > 5 else ''
                                    })
        except Exception as e:
            print(f"搜索失败: {e}")
        return results

    def get_stock_price(self, stock_code: str):
        """获取股票实时价格（腾讯API）"""
        try:
            code_prefix = "sh" if stock_code.startswith("6") else "sz"
            api_url = f"http://qt.gtimg.cn/q={code_prefix}{stock_code}"

            response = requests.get(api_url, timeout=5)
            response.encoding = 'gbk'

            if response.status_code == 200:
                content = response.text.strip()
                if '~' in content:
                    data = content.split('~')
                    if len(data) > 32:
                        return StockInfoWidget(
                            code=stock_code,
                            name=data[1],
                            price=float(data[3]),
                            change=float(data[31]),
                            change_percent=float(data[32]),
                            open_price=float(data[5])
                        )
        except Exception as e:
            print(f"获取 {stock_code} 失败: {e}")
        return None

    def update_stock_display(self):
        """更新股票显示"""
        # 清除旧的股票标签
        for widget in self.stock_widgets:
            widget.deleteLater()
        self.stock_widgets.clear()

        # 添加标题行
        header = QLabel('代码/名称&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;今开&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;现价&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;涨跌')
        header.setTextFormat(Qt.RichText)
        header.setStyleSheet('color: #000000; font-size: 13px; font-weight: bold; padding: 2px 12px; font-family: Consolas, "Courier New", monospace;')
        self.stock_widgets.append(header)
        self.content_layout.addWidget(header)

        # 添加新标签
        for stock_code in self.stocks:
            stock_info = self.get_stock_price(stock_code)
            if stock_info:
                label = self.create_stock_label(stock_info)
                self.stock_widgets.append(label)
                self.content_layout.addWidget(label)

        # 添加弹性空间到底部
        self.content_layout.addStretch()

    def create_stock_label(self, stock: StockInfoWidget) -> ClickableLabel:
        """创建股票信息标签"""
        # 根据涨跌设置颜色
        if stock.change_percent >= 0:
            color = '#ff4d4f'  # 红色-涨
            sign = '+'
        else:
            color = '#52c41a'  # 绿色-跌
            sign = ''

        change_str = f'<span style="color:{color};font-weight:bold;">{sign}{stock.change_percent:.2f}%</span>'
        # 代码在上，名称在下，数据对齐
        text = f'<div style="margin-bottom:2px;">{stock.code}</div><div>{stock.name}&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;{stock.open_price:.2f}&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;{stock.price:.2f}&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;{change_str}</div>'

        label = ClickableLabel(stock.code, stock.name)
        label.setText(text)
        label.setTextFormat(Qt.RichText)
        label.setStyleSheet('padding: 2px 12px; font-family: Consolas, "Courier New", monospace;')
        label.set_clicked_callback(self.show_stock_detail)
        return label

    def setup_timer(self):
        """设置定时刷新"""
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_stock_display)
        self.timer.start(self.refresh_interval * 1000)  # 使用配置的刷新间隔
        self.update_stock_display()  # 立即刷新一次

    def setup_system_tray(self):
        """设置系统托盘"""
        self.tray_icon = QSystemTrayIcon(self)
        
        # 创建托盘菜单
        tray_menu = QMenu()

        show_action = QAction('显示窗口', self)
        show_action.triggered.connect(self.show)
        tray_menu.addAction(show_action)

        hide_action = QAction('隐藏窗口', self)
        hide_action.triggered.connect(self.hide)
        tray_menu.addAction(hide_action)

        quit_action = QAction('退出', self)
        quit_action.triggered.connect(QApplication.instance().quit)
        tray_menu.addAction(quit_action)

        self.tray_icon.setContextMenu(tray_menu)
        # 尝试设置一个简单的图标（使用文本作为图标）
        try:
            # 创建一个简单的图标
            from PyQt5.QtGui import QPixmap
            pixmap = QPixmap(16, 16)
            pixmap.fill(Qt.white)
            self.tray_icon.setIcon(QIcon(pixmap))
        except:
            pass
        self.tray_icon.show()

    def mousePressEvent(self, event):
        """鼠标按下事件 - 用于拖动"""
        if event.button() == Qt.LeftButton:
            self.drag_position = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        """鼠标移动事件 - 拖动窗口"""
        if event.buttons() == Qt.LeftButton and hasattr(self, 'drag_position') and self.drag_position:
            self.move(event.globalPos() - self.drag_position)
            event.accept()

    def closeEvent(self, event):
        """关闭事件"""
        event.ignore()
        self.hide()


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # 关闭窗口时不退出程序

    window = StockDesktopWidget()
    window.show()

    # 窗口居中显示
    screen = app.primaryScreen()
    if screen:
        screen_geometry = screen.availableGeometry()
        x = (screen_geometry.width() - window.width()) // 2
        y = (screen_geometry.height() - window.height()) // 2
        window.move(x, y)
        print(f"窗口位置: {x}, {y}")
        print(f"屏幕大小: {screen_geometry.width()} x {screen_geometry.height()}")

    print("股票监控窗口已启动，按 Ctrl+C 退出")
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
