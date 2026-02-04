#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
桌面股票监控小工具 - 最小测试版
只包含基本窗口和做T计算器功能
"""

import sys
from PyQt5.QtWidgets import (QApplication, QWidget, QLabel, QVBoxLayout,
                             QHBoxLayout, QPushButton, QDialog, QLineEdit,
                             QGridLayout)
from PyQt5.QtCore import Qt, QTimer, QPoint
from PyQt5.QtGui import QFont, QColor, QIcon


class TCalculatorDialog(QDialog):
    """做T计算器对话框"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('做T计算器')
        self.setFixedSize(300, 180)
        self.init_ui()

    def init_ui(self):
        """初始化界面"""
        layout = QVBoxLayout()
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)

        # 输入区域
        input_layout = QGridLayout()
        input_layout.setSpacing(10)

        # 买入价
        buy_label = QLabel('买入价:')
        self.buy_input = QLineEdit()
        self.buy_input.setPlaceholderText('请输入买入价格')
        self.buy_input.textChanged.connect(self.calculate)
        input_layout.addWidget(buy_label, 0, 0)
        input_layout.addWidget(self.buy_input, 0, 1)

        # 卖出价
        sell_label = QLabel('卖出价:')
        self.sell_input = QLineEdit()
        self.sell_input.setPlaceholderText('请输入卖出价格')
        self.sell_input.textChanged.connect(self.calculate)
        input_layout.addWidget(sell_label, 1, 0)
        input_layout.addWidget(self.sell_input, 1, 1)

        # 数量
        quantity_label = QLabel('数量:')
        self.quantity_input = QLineEdit()
        self.quantity_input.setPlaceholderText('请输入股票数量')
        self.quantity_input.textChanged.connect(self.calculate)
        input_layout.addWidget(quantity_label, 2, 0)
        input_layout.addWidget(self.quantity_input, 2, 1)

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
            quantity = int(self.quantity_input.text()) if self.quantity_input.text() else 0

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
            else:
                self.result_label.setText('盈亏: ¥0.00 (0.00%)')
        except ValueError:
            self.result_label.setText('盈亏: ¥0.00 (0.00%)')

    def clear(self):
        """清空输入"""
        self.buy_input.clear()
        self.sell_input.clear()
        self.quantity_input.clear()
        self.calculate()


class StockDesktopWidget(QWidget):
    """桌面股票监控窗口"""

    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        """初始化界面"""
        # 窗口设置
        self.setWindowTitle('股票监控')
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setWindowOpacity(0.85)

        # 主布局
        self.main_layout = QVBoxLayout()
        self.main_layout.setSpacing(5)
        self.main_layout.setContentsMargins(15, 15, 15, 15)

        # 标题栏
        title_layout = QHBoxLayout()
        self.title_label = QLabel('📈 股票监控')
        self.title_label.setFont(QFont('Microsoft YaHei', 12, QFont.Bold))
        title_layout.addWidget(self.title_label)
        title_layout.addStretch()

        # 做T计算器按钮
        self.calculator_btn = QPushButton('💰')
        self.calculator_btn.setFixedSize(30, 30)
        self.calculator_btn.clicked.connect(self.show_calculator_dialog)
        title_layout.addWidget(self.calculator_btn)

        # 关闭按钮
        self.close_btn = QPushButton('×')
        self.close_btn.setFixedSize(30, 30)
        self.close_btn.clicked.connect(self.close)
        title_layout.addWidget(self.close_btn)

        self.main_layout.addLayout(title_layout)

        # 股票列表区域
        self.stock_list = QLabel('股票列表将显示在这里\n\n600519 - 贵州茅台\n000001 - 平安银行\n600036 - 招商银行')
        self.main_layout.addWidget(self.stock_list)

        self.setLayout(self.main_layout)

        # 窗口大小
        self.setFixedSize(480, 350)

    def show_calculator_dialog(self):
        """显示做T计算器对话框"""
        dialog = TCalculatorDialog(self)
        dialog.exec_()


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

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
