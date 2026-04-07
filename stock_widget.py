# -*- coding: utf-8 -*-
"""
桌面股票监控小工具
无边框透明窗口，可拖动位置
"""

import sys
import json
import requests
from kline_chart import KLineDialog
from datetime import datetime
from PyQt5.QtWidgets import (QApplication, QWidget, QLabel, QVBoxLayout,
                             QHBoxLayout, QPushButton, QSystemTrayIcon, QMenu,
                             QAction, QDialog, QListWidget, QLineEdit, QMessageBox,
                             QListWidgetItem, QAbstractItemView, QScrollArea,
                             QSlider, QSpinBox, QGridLayout, QComboBox, QInputDialog)
from PyQt5.QtCore import Qt, QTimer, QPoint, QRegExp
from PyQt5.QtGui import QFont, QColor, QIcon, QDoubleValidator, QIntValidator, QRegExpValidator


def _chinese_input_dialog(parent, title, label, text=''):
    """自定义输入弹窗，中文按钮"""
    dialog = QDialog(parent)
    dialog.setWindowTitle(title)
    dialog.setFixedSize(300, 120)
    dialog.setStyleSheet('''
        QDialog { background-color: #ffffff; }
        QLabel { font-size: 13px; }
        QLineEdit { padding: 6px; font-size: 13px; border: 1px solid #ccc; border-radius: 4px; }
        QPushButton { padding: 6px 20px; border-radius: 4px; font-size: 13px; }
    ''')
    layout = QVBoxLayout(dialog)
    layout.addWidget(QLabel(label))
    inp = QLineEdit(text)
    layout.addWidget(inp)
    btn_row = QHBoxLayout()
    btn_row.addStretch()
    ok_btn = QPushButton('确定')
    ok_btn.setStyleSheet('background: #0078d4; color: white;')
    cancel_btn = QPushButton('取消')
    cancel_btn.setStyleSheet('background: #e0e0e0;')
    btn_row.addWidget(ok_btn)
    btn_row.addWidget(cancel_btn)
    layout.addLayout(btn_row)

    result = [None, False]

    def on_ok():
        result[0] = inp.text().strip()
        result[1] = True
        dialog.accept()

    def on_cancel():
        dialog.reject()

    ok_btn.clicked.connect(on_ok)
    cancel_btn.clicked.connect(on_cancel)
    inp.returnPressed.connect(on_ok)
    dialog.exec_()
    return result[0], result[1]


def _chinese_select_dialog(parent, title, label, items, current=0):
    """自定义选择弹窗，中文按钮"""
    dialog = QDialog(parent)
    dialog.setWindowTitle(title)
    dialog.setFixedSize(300, 140)
    dialog.setStyleSheet('''
        QDialog { background-color: #ffffff; }
        QLabel { font-size: 13px; }
        QComboBox { padding: 6px; font-size: 13px; border: 1px solid #ccc; border-radius: 4px; }
        QPushButton { padding: 6px 20px; border-radius: 4px; font-size: 13px; }
    ''')
    layout = QVBoxLayout(dialog)
    layout.addWidget(QLabel(label))
    combo = QComboBox()
    combo.addItems(items)
    combo.setCurrentIndex(current)
    layout.addWidget(combo)
    btn_row = QHBoxLayout()
    btn_row.addStretch()
    ok_btn = QPushButton('确定')
    ok_btn.setStyleSheet('background: #0078d4; color: white;')
    cancel_btn = QPushButton('取消')
    cancel_btn.setStyleSheet('background: #e0e0e0;')
    btn_row.addWidget(ok_btn)
    btn_row.addWidget(cancel_btn)
    layout.addLayout(btn_row)

    result = [None, False]

    def on_ok():
        result[0] = combo.currentText()
        result[1] = True
        dialog.accept()

    def on_cancel():
        dialog.reject()

    ok_btn.clicked.connect(on_ok)
    cancel_btn.clicked.connect(on_cancel)
    dialog.exec_()
    return result[0], result[1]


class ClickableLabel(QLabel):
    """可点击的标签，用于显示股票信息"""

    def __init__(self, stock_code, stock_name, parent=None):
        super().__init__(parent)
        self.stock_code = stock_code
        self.stock_name = stock_name
        self.callback = None
        self.right_callback = None

    def mousePressEvent(self, event):
        """鼠标点击事件"""
        if event.button() == Qt.LeftButton and self.callback:
            self.callback(self.stock_code, self.stock_name)
        elif event.button() == Qt.RightButton and self.right_callback:
            self.right_callback(self.stock_code, self.stock_name)
        super().mousePressEvent(event)

    def set_clicked_callback(self, callback):
        """设置点击回调函数"""
        self.callback = callback

    def set_right_callback(self, callback):
        """设置右键回调函数"""
        self.right_callback = callback


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
        # 五档买卖盘
        self.bid_prices = [0.0] * 5
        self.bid_vols = [0] * 5
        self.ask_prices = [0.0] * 5
        self.ask_vols = [0] * 5


class StockManageDialog(QDialog):
    """股票管理对话框 - 支持添加、删除、搜索股票"""

    def __init__(self, current_stocks: list, pinned_stocks: set = None,
                 groups: dict = None, parent=None):
        super().__init__(parent)
        self.current_stocks = current_stocks[:]  # 复制一份
        self.stock_names = {}  # 存储代码到名称的映射
        self.pinned_stocks = pinned_stocks.copy() if pinned_stocks else set()  # 存储置顶的股票代码
        self.groups = dict(groups) if groups else {}  # 复制分组
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
            QMenu {
                background-color: #ffffff;
                border: 1px solid #e0e0e0;
                padding: 4px 0px;
            }
            QMenu::item {
                padding: 6px 28px;
                color: #333333;
            }
            QMenu::item:selected {
                background-color: #0078d4;
                color: #ffffff;
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
        self.current_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.current_list.customContextMenuRequested.connect(self._show_stock_menu)
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

        # 调用父窗口的搜索方法获取股票名称
        parent = self.parent()
        if parent and hasattr(parent, 'search_stocks'):
            self.search_results = parent.search_stocks(keyword)

        # 如果没有搜索结果，且输入是6位数字，尝试直接获取股票信息
        if not self.search_results and len(keyword) == 6 and keyword.isdigit():
            # 通过API获取股票名称
            if parent and hasattr(parent, 'get_stock_price'):
                stock_info = parent.get_stock_price(keyword)
                if stock_info:
                    self.search_results.append({'code': keyword, 'name': stock_info.name, 'pinyin': ''})
                else:
                    # API失败时也允许添加
                    self.search_results.append({'code': keyword, 'name': f'{keyword}(待获取)', 'pinyin': ''})

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
                # 计算置顶股票数量，新增股票插入到置顶股票之后
                pinned_count = sum(1 for s in self.current_stocks if s in self.pinned_stocks)
                insert_pos = pinned_count  # 插入到置顶股票之后
                self.current_stocks.insert(insert_pos, code)
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
            # 从置顶集合中移除
            if code in self.pinned_stocks:
                self.pinned_stocks.remove(code)
            # 从所有分组中移除
            for grp in self.groups.values():
                if code in grp:
                    grp.remove(code)
            self.refresh_current_list()

    def _show_stock_menu(self, pos):
        """右键菜单"""
        item = self.current_list.itemAt(pos)
        if not item:
            return
        text = item.text()
        code = text.split(' - ')[0] if ' - ' in text else text
        code = code.replace('📌 ', '').strip()

        menu = QMenu(self)
        is_pinned = code in self.pinned_stocks
        pin_action = menu.addAction('取消置顶' if is_pinned else '📌 置顶')
        menu.addSeparator()

        # 分组子菜单
        if self.groups:
            grp_menu = menu.addMenu('加入分组')
            for grp_name, grp_codes in self.groups.items():
                if code in grp_codes:
                    act = grp_menu.addAction(f'✓ {grp_name}')
                else:
                    act = grp_menu.addAction(grp_name)
                act.setData((code, grp_name))

        action = menu.exec_(self.current_list.mapToGlobal(pos))
        if action == pin_action:
            self.pin_to_top()
        elif action and action.data():
            c, g = action.data()
            if c not in self.groups[g]:
                self.groups[g].append(c)

    def pin_to_top(self):
        """切换股票置顶状态"""
        current_item = self.current_list.currentItem()
        if not current_item:
            QMessageBox.warning(self, '提示', '请先选择要置顶的股票')
            return

        # 从 "代码 - 名称" 格式中提取代码（处理可能的置顶图标）
        text = current_item.text()
        code = text.split(' - ')[0] if ' - ' in text else text
        code = code.replace('📌 ', '').strip()  # 移除置顶图标

        if code in self.current_stocks:
            # 计算当前置顶股票数量
            pinned_count = sum(1 for s in self.current_stocks if s in self.pinned_stocks)
            current_row = self.current_list.currentRow()

            # 如果已经置顶，则取消置顶
            if code in self.pinned_stocks:
                self.pinned_stocks.remove(code)
                # 将股票移到置顶区域之后
                self.current_stocks.remove(code)
                self.current_stocks.insert(pinned_count - 1, code)
                self.refresh_current_list()
                # 重新选中该项
                self.current_list.setCurrentRow(pinned_count - 1)
            else:
                # 添加到置顶集合，并移到置顶区域末尾
                self.pinned_stocks.add(code)
                self.current_stocks.remove(code)
                self.current_stocks.insert(pinned_count, code)
                self.refresh_current_list()
                # 重新选中置顶的项
                self.current_list.setCurrentRow(pinned_count)

    def get_stocks(self):
        """获取更新后的股票列表"""
        return self.current_stocks

    def get_pinned_stocks(self):
        """获取置顶的股票集合"""
        return self.pinned_stocks

    def get_groups(self):
        """获取更新后的分组"""
        return self.groups

    def refresh_current_list(self):
        """刷新当前股票列表显示"""
        self.current_list.clear()
        for code in self.current_stocks:
            name = self.stock_names.get(code, code)
            # 置顶股票添加图标
            prefix = '📌 ' if code in self.pinned_stocks else ''
            item = QListWidgetItem(f'{prefix}{code} - {name}')
            # 置顶股票设置灰色背景
            if code in self.pinned_stocks:
                item.setBackground(QColor(224, 224, 224))
            self.current_list.addItem(item)

    def on_rows_moved(self, parent, start, end, destination, row):
        """拖拽排序后更新股票列表顺序"""
        # 重建股票列表顺序
        new_order = []
        for i in range(self.current_list.count()):
            item_text = self.current_list.item(i).text()
            # 移除置顶图标后提取代码
            code = item_text.split(' - ')[0] if ' - ' in item_text else item_text
            code = code.replace('📌 ', '').strip()  # 移除置顶图标
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


class AlertDialog(QDialog):
    """价格预警设置对话框"""

    _C_BG = '#161a25'
    _C_GRID = '#1e222d'
    _C_DIM = '#787b86'
    _C_TEXT = '#d1d4dc'
    _C_UP = '#ef5350'
    _C_DOWN = '#26a69a'

    def __init__(self, alerts: list, stock_codes: list, parent=None):
        super().__init__(parent)
        self.alerts = alerts[:]  # 复制一份
        self.stock_codes = stock_codes
        self.init_ui()
        self._refresh_list()

    def init_ui(self):
        self.setWindowTitle('价格预警')
        self.setFixedSize(480, 420)
        self.setStyleSheet(f'''
            QDialog {{ background-color: {self._C_BG}; }}
            QLabel {{ color: {self._C_TEXT}; font-size: 13px; font-family: "Microsoft YaHei"; }}
            QLineEdit {{
                background-color: {self._C_GRID}; color: {self._C_TEXT};
                border: 1px solid #2a2e39; border-radius: 4px;
                padding: 6px 10px; font-size: 13px;
            }}
            QLineEdit:focus {{ border: 1px solid #2962ff; }}
            QComboBox {{
                background-color: {self._C_GRID}; color: {self._C_TEXT};
                border: 1px solid #2a2e39; border-radius: 4px;
                padding: 6px 10px; font-size: 13px;
            }}
            QComboBox QAbstractItemView {{
                background-color: {self._C_GRID}; color: {self._C_TEXT};
                selection-background-color: #2962ff;
            }}
            QPushButton {{
                background: #2962ff; color: #ffffff; border: none;
                padding: 6px 16px; border-radius: 4px;
                font-size: 12px; font-weight: bold;
            }}
            QPushButton:hover {{ background: #1e53e5; }}
            QListWidget {{
                background-color: {self._C_GRID}; color: {self._C_TEXT};
                border: 1px solid #2a2e39; border-radius: 4px;
                font-size: 12px; font-family: "Consolas", "Microsoft YaHei";
            }}
            QListWidget::item {{ padding: 8px; }}
            QListWidget::item:selected {{ background-color: #2962ff; }}
        ''')

        layout = QVBoxLayout()
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        # 添加预警区域
        add_layout = QHBoxLayout()

        # 股票选择
        self._code_input = QLineEdit()
        self._code_input.setPlaceholderText('股票代码')
        self._code_input.setFixedWidth(100)
        add_layout.addWidget(self._code_input)

        # 方向选择
        self._dir_combo = QComboBox()
        self._dir_combo.addItems(['高于', '低于'])
        self._dir_combo.setFixedWidth(70)
        add_layout.addWidget(self._dir_combo)

        # 目标价格
        self._price_input = QLineEdit()
        self._price_input.setPlaceholderText('目标价格')
        self._price_input.setFixedWidth(100)
        self._price_input.setValidator(QDoubleValidator(0.0, 999999.0, 2))
        add_layout.addWidget(self._price_input)

        add_btn = QPushButton('添加')
        add_btn.clicked.connect(self._add_alert)
        add_layout.addWidget(add_btn)

        layout.addLayout(add_layout)

        # 预警列表
        self._alert_list = QListWidget()
        layout.addWidget(self._alert_list)

        # 按钮
        btn_layout = QHBoxLayout()
        del_btn = QPushButton('删除选中')
        del_btn.setStyleSheet('background: #ef5350;')
        del_btn.clicked.connect(self._remove_alert)
        btn_layout.addWidget(del_btn)
        btn_layout.addStretch()

        ok_btn = QPushButton('确定')
        ok_btn.clicked.connect(self.accept)
        btn_layout.addWidget(ok_btn)

        cancel_btn = QPushButton('取消')
        cancel_btn.setStyleSheet('background: #4a4e59;')
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        layout.addLayout(btn_layout)
        self.setLayout(layout)

    def _refresh_list(self):
        self._alert_list.clear()
        for a in self.alerts:
            direction = '高于' if a['direction'] == 'above' else '低于'
            status = ' [已触发]' if a.get('triggered') else ''
            color_style = 'color: #787b86;' if a.get('triggered') else ''
            text = f"{a['code']} {a.get('name', '')}  {direction} ¥{a['target']:.2f}{status}"
            item = QListWidgetItem(text)
            if a.get('triggered'):
                item.setForeground(QColor('#787b86'))
            self._alert_list.addItem(item)

    def _add_alert(self):
        code = self._code_input.text().strip()
        price_text = self._price_input.text().strip()
        if not code or not price_text:
            return
        try:
            target = float(price_text)
        except ValueError:
            return

        direction = 'above' if self._dir_combo.currentText() == '高于' else 'below'

        # 获取股票名称
        name = code
        parent = self.parent()
        if parent and hasattr(parent, 'get_stock_price'):
            info = parent.get_stock_price(code)
            if info:
                name = info.name

        self.alerts.append({
            'code': code,
            'name': name,
            'target': target,
            'direction': direction,
            'triggered': False
        })
        self._refresh_list()
        self._code_input.clear()
        self._price_input.clear()

    def _remove_alert(self):
        row = self._alert_list.currentRow()
        if 0 <= row < len(self.alerts):
            self.alerts.pop(row)
            self._refresh_list()

    def get_alerts(self):
        return self.alerts


class BidAskDialog(QDialog):
    """五档买卖盘对话框"""

    _C_UP = '#ef5350'
    _C_DOWN = '#26a69a'
    _C_BG = '#131722'
    _C_PANEL = '#161a25'
    _C_GRID = '#1e222d'
    _C_DIM = '#787b86'
    _C_TEXT = '#d1d4dc'

    def __init__(self, stock_code: str, stock_name: str, parent=None):
        super().__init__(parent)
        self.stock_code = stock_code
        self.stock_name = stock_name
        self.init_ui()
        self._refresh()
        # 30秒自动刷新
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh)
        self._timer.start(30000)

    def init_ui(self):
        self.setWindowTitle(f'{self.stock_code} - {self.stock_name} 五档盘口')
        self.setFixedSize(320, 480)
        self.setStyleSheet(f'''
            QDialog {{ background-color: {self._C_PANEL}; }}
            QLabel {{ color: {self._C_TEXT}; font-family: "Consolas", "Microsoft YaHei"; }}
        ''')

        layout = QVBoxLayout()
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # 标题
        self._title = QLabel(f'{self.stock_name}  {self.stock_code}')
        self._title.setStyleSheet(f'font-size: 14px; font-weight: bold; color: {self._C_TEXT};')
        layout.addWidget(self._title)

        # 价格行
        price_row = QHBoxLayout()
        self._price_lbl = QLabel('--')
        self._price_lbl.setStyleSheet('font-size: 18px; font-weight: bold;')
        price_row.addWidget(self._price_lbl)
        self._change_lbl = QLabel('--')
        self._change_lbl.setStyleSheet('font-size: 13px; font-weight: bold;')
        price_row.addWidget(self._change_lbl)
        price_row.addStretch()
        layout.addLayout(price_row)

        # 分隔线
        sep = QLabel('')
        sep.setFixedHeight(1)
        sep.setStyleSheet(f'background-color: {self._C_GRID};')
        layout.addWidget(sep)

        # 卖盘 (卖五到卖一，从上到下)
        self._ask_labels = []
        for i in range(4, -1, -1):
            row = QHBoxLayout()
            tag = QLabel(f'卖{["一","二","三","四","五"][i]}')
            tag.setFixedWidth(30)
            tag.setStyleSheet(f'font-size: 12px; color: {self._C_DOWN};')
            row.addWidget(tag)

            price = QLabel('--')
            price.setFixedWidth(80)
            price.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            price.setStyleSheet(f'font-size: 13px; font-weight: bold; color: {self._C_DOWN};')
            row.addWidget(price)

            vol = QLabel('--')
            vol.setFixedWidth(80)
            vol.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            vol.setStyleSheet(f'font-size: 12px; color: {self._C_DIM};')
            row.addWidget(vol)
            row.addStretch()
            layout.addLayout(row)
            self._ask_labels.append((price, vol, i))

        # 分隔线
        sep2 = QLabel('')
        sep2.setFixedHeight(1)
        sep2.setStyleSheet(f'background-color: {self._C_GRID};')
        layout.addWidget(sep2)

        # 买盘 (买一到买五，从上到下)
        self._bid_labels = []
        for i in range(5):
            row = QHBoxLayout()
            tag = QLabel(f'买{["一","二","三","四","五"][i]}')
            tag.setFixedWidth(30)
            tag.setStyleSheet(f'font-size: 12px; color: {self._C_UP};')
            row.addWidget(tag)

            price = QLabel('--')
            price.setFixedWidth(80)
            price.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            price.setStyleSheet(f'font-size: 13px; font-weight: bold; color: {self._C_UP};')
            row.addWidget(price)

            vol = QLabel('--')
            vol.setFixedWidth(80)
            vol.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            vol.setStyleSheet(f'font-size: 12px; color: {self._C_DIM};')
            row.addWidget(vol)
            row.addStretch()
            layout.addLayout(row)
            self._bid_labels.append((price, vol, i))

        # 分隔线
        sep3 = QLabel('')
        sep3.setFixedHeight(1)
        sep3.setStyleSheet(f'background-color: {self._C_GRID};')
        layout.addWidget(sep3)

        # 额外信息
        self._extra_lbl = QLabel('')
        self._extra_lbl.setStyleSheet(f'font-size: 11px; color: {self._C_DIM};')
        layout.addWidget(self._extra_lbl)

        layout.addStretch()

        # 关闭按钮
        close_btn = QPushButton('关闭')
        close_btn.setFixedHeight(30)
        close_btn.setStyleSheet(f'''
            QPushButton {{
                background-color: {self._C_GRID}; color: {self._C_TEXT};
                border: none; border-radius: 4px; font-size: 13px;
            }}
            QPushButton:hover {{ background-color: #2962ff; }}
        ''')
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

        self.setLayout(layout)

    def _refresh(self):
        parent = self.parent()
        if not parent or not hasattr(parent, 'get_stock_price'):
            return
        info = parent.get_stock_price(self.stock_code)
        if not info:
            return

        c = info.price
        prev = info.open_price  # 近似
        chg = info.change
        pct = info.change_percent
        up = chg >= 0
        col = self._C_UP if up else self._C_DOWN
        s = '+' if up else ''

        self._price_lbl.setText(f'{c:.2f}')
        self._price_lbl.setStyleSheet(f'font-size: 18px; font-weight: bold; color: {col};')
        self._change_lbl.setText(f'{s}{chg:.2f}  {s}{pct:.2f}%')
        self._change_lbl.setStyleSheet(f'font-size: 13px; font-weight: bold; color: {col};')

        # 卖盘 (从卖五到卖一)
        for price_lbl, vol_lbl, i in self._ask_labels:
            p = info.ask_prices[i]
            v = info.ask_vols[i]
            if p > 0:
                price_lbl.setText(f'{p:.2f}')
                vol_lbl.setText(f'{v}手')
            else:
                price_lbl.setText('--')
                vol_lbl.setText('--')

        # 买盘
        for price_lbl, vol_lbl, i in self._bid_labels:
            p = info.bid_prices[i]
            v = info.bid_vols[i]
            if p > 0:
                price_lbl.setText(f'{p:.2f}')
                vol_lbl.setText(f'{v}手')
            else:
                price_lbl.setText('--')
                vol_lbl.setText('--')

        # 额外信息
        total_bid = sum(info.bid_vols)
        total_ask = sum(info.ask_vols)
        ratio = total_bid / total_ask if total_ask > 0 else 0
        self._extra_lbl.setText(
            f'买量: {total_bid}手  卖量: {total_ask}手  比率: {ratio:.2f}')

    def closeEvent(self, event):
        self._timer.stop()
        super().closeEvent(event)


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



class StockDesktopWidget(QWidget):
    """桌面股票监控窗口"""

    def __init__(self):
        super().__init__()
        self.stocks = []
        self.pinned_stocks = set()  # 置顶的股票代码
        self.stock_widgets = []
        self.drag_position = None
        self.window_opacity = 0.85  # 默认透明度
        self.refresh_interval = 5  # 默认刷新间隔（秒）
        self.alerts = []  # 价格预警列表
        self.groups = {}  # 分组 {组名: [股票代码列表]}
        self._current_group = '全部'
        self.init_ui()
        self.load_config()
        self._rebuild_group_tabs()
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
        self.main_layout.setSpacing(0)
        self.main_layout.setContentsMargins(15, 10, 15, 10)

        # 标题栏
        title_layout = QHBoxLayout()
        self.title_label = QLabel('📈 股票监控')
        self.title_label.setFont(QFont('Microsoft YaHei', 12, QFont.Bold))
        self.title_label.setStyleSheet('color: #000000;')
        title_layout.addWidget(self.title_label)
        title_layout.addStretch()

        # 五档盘口按钮
        self.bidask_btn = QPushButton('📊')
        self.bidask_btn.setFixedSize(30, 30)
        self.bidask_btn.setStyleSheet('''
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
        self.bidask_btn.clicked.connect(self.show_bidask_dialog)
        title_layout.addWidget(self.bidask_btn)

        # 预警按钮
        self.alert_btn = QPushButton('🔔')
        self.alert_btn.setFixedSize(30, 30)
        self.alert_btn.setStyleSheet('''
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
        self.alert_btn.clicked.connect(self.show_alert_dialog)
        title_layout.addWidget(self.alert_btn)

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

        # === 分组标签栏 ===
        tab_bar = QHBoxLayout()
        tab_bar.setSpacing(2)
        tab_bar.setContentsMargins(0, 0, 0, 0)

        self._group_btns = []
        btn_all = QPushButton('全部')
        btn_all.setCheckable(True)
        btn_all.setChecked(True)
        btn_all.setStyleSheet('''
            QPushButton {
                background: transparent; color: #787b86; border: none;
                padding: 3px 10px; border-radius: 2px;
                font-size: 11px; font-weight: bold;
            }
            QPushButton:hover { background: #e0e0e0; }
            QPushButton:checked { background: #0078d4; color: #ffffff; border-radius: 2px; }
        ''')
        btn_all.clicked.connect(lambda: self._switch_group('全部'))
        tab_bar.addWidget(btn_all)
        self._group_btns.append(('全部', btn_all))

        # "+" 新建分组按钮
        add_grp_btn = QPushButton('+')
        add_grp_btn.setFixedSize(24, 24)
        add_grp_btn.setStyleSheet('''
            QPushButton {
                background: transparent; color: #999; border: none;
                font-size: 14px; font-weight: bold;
            }
            QPushButton:hover { background: #e0e0e0; border-radius: 2px; }
        ''')
        add_grp_btn.clicked.connect(self._add_group)
        tab_bar.addWidget(add_grp_btn)

        tab_bar.addStretch()
        self._tab_bar_layout = tab_bar
        self.main_layout.addLayout(tab_bar)

        # 创建滚动区域
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QScrollArea.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        # 滚动内容的容器
        self.scroll_content = QWidget()
        self.content_layout = QVBoxLayout()
        self.content_layout.setSpacing(2)
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
            self.pinned_stocks = set(config.get('pinned', []))
            self.window_opacity = config.get('opacity', 0.85)
            self.refresh_interval = config.get('refresh_interval', 5)
            self.alerts = config.get('alerts', [])
            self.groups = config.get('groups', {})
            # 应用加载的设置
            self.setWindowOpacity(self.window_opacity)
        except:
            # 默认股票和设置
            self.stocks = ['600519', '000001', '600036']
            self.pinned_stocks = set()
            self.window_opacity = 0.85
            self.refresh_interval = 5
            self.alerts = []
            self.groups = {}

    def save_config(self):
        """保存配置文件"""
        try:
            config = {
                'stocks': self.stocks,
                'pinned': list(self.pinned_stocks),
                'opacity': self.window_opacity,
                'refresh_interval': self.refresh_interval,
                'alerts': self.alerts,
                'groups': self.groups
            }
            with open('config.json', 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存配置失败: {e}")

    def show_manage_dialog(self):
        """显示股票管理对话框"""
        dialog = StockManageDialog(self.stocks, self.pinned_stocks, self.groups, self)
        if dialog.exec_() == QDialog.Accepted:
            self.stocks = dialog.get_stocks()
            self.pinned_stocks = dialog.get_pinned_stocks()
            self.groups = dialog.get_groups()
            self.save_config()
            self._rebuild_group_tabs()
            self.update_stock_display()

    # ========== 分组管理 ==========

    def _switch_group(self, group_name):
        """切换分组"""
        self._current_group = group_name
        for name, btn in self._group_btns:
            btn.setChecked(name == group_name)
        self.update_stock_display()

    def _add_group(self):
        """新建分组"""
        name, ok = _chinese_input_dialog(self, '新建分组', '分组名称：')
        if ok and name:
            if name in self.groups or name == '全部':
                return
            self.groups[name] = []
            self.save_config()
            self._rebuild_group_tabs()
            self._switch_group(name)

    def _show_group_menu(self, pos, name, btn):
        """分组标签右键菜单"""
        menu = QMenu(self)
        menu.setStyleSheet('''
            QMenu { background-color: #ffffff; border: 1px solid #e0e0e0; padding: 4px 0px; }
            QMenu::item { padding: 6px 28px; color: #333333; }
            QMenu::item:selected { background-color: #0078d4; color: #ffffff; }
        ''')
        rename_action = menu.addAction('重命名')
        menu.addSeparator()
        del_action = menu.addAction('删除分组')
        action = menu.exec_(btn.mapToGlobal(pos))
        if action == rename_action:
            self._rename_group(name)
        elif action == del_action:
            self._remove_group(name)

    def _rename_group(self, old_name):
        """重命名分组"""
        new_name, ok = _chinese_input_dialog(self, '重命名分组', '新名称：', old_name)
        if ok and new_name and new_name != old_name:
            if new_name in self.groups or new_name == '全部':
                return
            codes = self.groups.pop(old_name)
            self.groups[new_name] = codes
            if self._current_group == old_name:
                self._current_group = new_name
            self.save_config()
            self._rebuild_group_tabs()

    def _remove_group(self, name):
        """删除分组"""
        if name in self.groups:
            msg = QMessageBox(self)
            msg.setWindowTitle('删除分组')
            msg.setText(f'确定删除分组「{name}」吗？\n该分组下的股票不会被删除。')
            msg.setIcon(QMessageBox.Question)
            yes_btn = msg.addButton('确定', QMessageBox.YesRole)
            msg.addButton('取消', QMessageBox.NoRole)
            msg.exec_()
            if msg.clickedButton() != yes_btn:
                return
            del self.groups[name]
            self.save_config()
            self._rebuild_group_tabs()
            if self._current_group == name:
                self._switch_group('全部')

    def _rebuild_group_tabs(self):
        """重建分组标签栏"""
        # 移除旧的分组按钮（保留"全部"和"+"按钮）
        for name, btn in self._group_btns[1:]:
            self._tab_bar_layout.removeWidget(btn)
            btn.deleteLater()
        self._group_btns = self._group_btns[:1]

        # 在 "+" 按钮之前插入分组标签
        insert_idx = self._tab_bar_layout.count() - 2  # stretch 和 "+" 之前
        for i, name in enumerate(self.groups.keys()):
            btn = QPushButton(name)
            btn.setCheckable(True)
            btn.setStyleSheet('''
                QPushButton {
                    background: transparent; color: #787b86; border: none;
                    padding: 3px 10px; border-radius: 2px;
                    font-size: 11px; font-weight: bold;
                }
                QPushButton:hover { background: #e0e0e0; }
                QPushButton:checked { background: #0078d4; color: #ffffff; border-radius: 2px; }
            ''')
            btn.clicked.connect(lambda _, n=name: self._switch_group(n))
            # 右键菜单：重命名/删除
            btn.setContextMenuPolicy(Qt.CustomContextMenu)
            btn.customContextMenuRequested.connect(lambda pos, n=name, b=btn: self._show_group_menu(pos, n, b))
            self._tab_bar_layout.insertWidget(insert_idx + i, btn)
            self._group_btns.append((name, btn))

        # 恢复当前选中状态
        found = False
        for name, btn in self._group_btns:
            if name == self._current_group:
                btn.setChecked(True)
                found = True
            else:
                btn.setChecked(False)
        if not found:
            self._current_group = '全部'
            self._group_btns[0][1].setChecked(True)

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

    def show_bidask_dialog(self, stock_code: str = None, stock_name: str = None):
        """显示五档买卖盘"""
        if stock_code is None:
            # 从按钮触发，显示第一只股票
            if self.stocks:
                stock_code = self.stocks[0]
            else:
                return
        if stock_name is None:
            info = self.get_stock_price(stock_code)
            stock_name = info.name if info else stock_code
        dialog = BidAskDialog(stock_code, stock_name, self)
        dialog.exec_()

    def show_alert_dialog(self):
        """显示价格预警设置"""
        dialog = AlertDialog(self.alerts, self.stocks, self)
        if dialog.exec_() == QDialog.Accepted:
            self.alerts = dialog.get_alerts()
            self.save_config()

    def _check_alerts(self):
        """检查预警条件"""
        triggered_any = False
        for alert in self.alerts:
            if alert.get('triggered'):
                continue
            info = self.get_stock_price(alert['code'])
            if not info:
                continue
            price = info.price
            target = alert['target']
            direction = alert['direction']

            hit = (direction == 'above' and price >= target) or \
                  (direction == 'below' and price <= target)
            if hit:
                alert['triggered'] = True
                triggered_any = True
                sign = '高于' if direction == 'above' else '低于'
                color = '#ef5350' if direction == 'above' else '#26a69a'
                QMessageBox.warning(
                    self, '价格预警',
                    f'<span style="font-size:14px;">'
                    f'{alert.get("name", alert["code"])} ({alert["code"]})<br>'
                    f'当前价: <b>{price:.2f}</b><br>'
                    f'已{sign}目标价: <b style="color:{color}">{target:.2f}</b>'
                    f'</span>'
                )
                # 蜂鸣声
                QApplication.beep()

        if triggered_any:
            self.save_config()

    def _reset_daily_alerts(self):
        """每日首次刷新时重置已触发的预警"""
        import datetime
        today = datetime.date.today()
        for alert in self.alerts:
            if alert.get('triggered'):
                alert['triggered'] = False
        self.save_config()

    def show_stock_detail(self, stock_code: str, stock_name: str):
        """显示K线/分时对话框"""
        dialog = KLineDialog(stock_code, stock_name, self)
        dialog.show()

    def search_stocks(self, keyword: str) -> list:
        """搜索股票（根据代码或名称）- 使用新浪API"""
        results = []
        try:
            # 新浪股票搜索API
            # type=11:沪深A股, type=12:指数
            api_url = f"http://suggest3.sinajs.cn/suggest/type=11,12,13,14,15&key={keyword}&name=suggestdata"
            # 禁用代理，避免连接到本地代理导致超时
            response = requests.get(api_url, timeout=5, proxies={'http': None, 'https': None})

            if response.status_code == 200:
                # 手动解码GBK编码的响应
                content = response.content.decode('gbk').strip()
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
                                # 跳过名称为空的股票
                                if len(code) == 6 and code.isdigit() and name and name.strip():
                                    # 检测name是否是代码格式(如sh600893)，如果是则获取真实名称
                                    if name.startswith('sh') or name.startswith('sz'):
                                        stock_info = self.get_stock_price(code)
                                        if stock_info:
                                            name = stock_info.name
                                        else:
                                            name = code  # fallback
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
            # 判断代码是否已包含前缀
            if stock_code.startswith('sh') or stock_code.startswith('sz'):
                code_with_prefix = stock_code
            else:
                code_prefix = "sh" if stock_code.startswith(("6", "5")) else "sz"
                code_with_prefix = f"{code_prefix}{stock_code}"

            api_url = f"http://qt.gtimg.cn/q={code_with_prefix}"

            # 禁用代理，避免连接到本地代理导致超时
            response = requests.get(api_url, timeout=5, proxies={'http': None, 'https': None})

            if response.status_code == 200:
                # 手动解码GBK编码的响应
                content = response.content.decode('gbk').strip()
                if '~' in content:
                    data = content.split('~')
                    if len(data) > 32:
                        info = StockInfoWidget(
                            code=stock_code,
                            name=data[1],
                            price=float(data[3]),
                            change=float(data[31]),
                            change_percent=float(data[32]),
                            open_price=float(data[5])
                        )
                        # 解析五档买卖盘 data[9]~data[28]
                        if len(data) > 28:
                            try:
                                for i in range(5):
                                    info.bid_prices[i] = float(data[9 + i * 2])   # 买1-5价
                                    info.bid_vols[i] = int(float(data[10 + i * 2]))  # 买1-5量(手)
                                    info.ask_prices[i] = float(data[19 + i * 2])   # 卖1-5价
                                    info.ask_vols[i] = int(float(data[20 + i * 2]))  # 卖1-5量(手)
                            except (ValueError, IndexError):
                                pass
                        return info
        except Exception as e:
            print(f"获取 {stock_code} 失败: {e}")
        return None

    def update_stock_display(self):
        """更新股票显示"""
        # 清空整个 content_layout（包括旧的 stretch）
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self.stock_widgets.clear()

        # 添加标题行
        header = QLabel('代码/名称&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;今开&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;现价&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;涨跌')
        header.setTextFormat(Qt.RichText)
        header.setStyleSheet('color: #000000; font-size: 13px; font-weight: bold; padding: 2px 12px; font-family: Consolas, "Courier New", monospace;')
        self.stock_widgets.append(header)
        self.content_layout.addWidget(header)

        # 根据当前分组决定显示哪些股票
        if self._current_group == '全部':
            display_stocks = self.stocks
        else:
            group_codes = set(self.groups.get(self._current_group, []))
            display_stocks = [s for s in self.stocks if s in group_codes]

        # 添加新标签
        for stock_code in display_stocks:
            stock_info = self.get_stock_price(stock_code)
            if stock_info:
                label = self.create_stock_label(stock_info)
                self.stock_widgets.append(label)
                self.content_layout.addWidget(label)

        # 添加弹性空间到底部
        self.content_layout.addStretch()

        # 检查价格预警
        if self.alerts:
            self._check_alerts()

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
        label.set_right_callback(self.show_bidask_dialog)
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
