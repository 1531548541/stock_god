# -*- coding: utf-8 -*-
"""
专业K线图表模块
独立于主程序，提供K线蜡烛图、技术指标等功能
"""

import json
import datetime
import numpy as np
import requests
from PyQt5.QtWidgets import (QDialog, QLabel, QVBoxLayout, QHBoxLayout,
                             QPushButton, QButtonGroup, QApplication)
from PyQt5.QtCore import Qt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from matplotlib.gridspec import GridSpec
import matplotlib.pyplot as plt

# matplotlib中文字体
plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei']
plt.rcParams['axes.unicode_minus'] = False

# ======== 颜色常量 ========
C_UP = '#ef5350'
C_DOWN = '#26a69a'
C_BG = '#131722'
C_PANEL = '#161a25'
C_GRID = '#1e222d'
C_DIM = '#787b86'
C_TEXT = '#d1d4dc'
C_CROSS = '#758696'
C_MA5 = '#f5c842'
C_MA10 = '#4da6ff'
C_MA20 = '#ff6f91'
C_MA60 = '#9c27b0'
C_BOLL = '#7c4dff'


class KLineDialog(QDialog):
    """专业K线图表对话框"""

    # 图表类型
    TYPE_DAILY = '日K'
    TYPE_WEEKLY = '周K'
    TYPE_MONTHLY = '月K'
    TYPE_MACD = 'MACD'
    TYPE_KDJ = 'KDJ'
    TYPE_RSI = 'RSI'
    TYPE_BOLL = 'BOLL'

    _cache = {}
    _CACHE_TTL = 300

    def __init__(self, stock_code: str, stock_name: str, parent=None):
        super().__init__(parent)
        self.stock_code = stock_code
        self.stock_name = stock_name
        self.chart_type = self.TYPE_DAILY
        self.data_count = 120  # 默认显示120条

        # K线数据
        self.dates = []
        self.opens = []
        self.highs = []
        self.lows = []
        self.closes = []
        self.volumes = []

        # 悬停
        self._hover_vline = None
        self._hover_vline_vol = None
        self._hover_hline = None
        self._hover_price_tag = None
        self._hover_date_tag = None

        # 缩放状态
        self._zoom_xlim = None  # None = 显示全部

        # 画线工具
        self._tool_mode = 'hover'  # hover, trendline, hline
        self._drawings = []       # 存储画线 [(type, params), ...]
        self._draw_clicks = []    # 画线中间状态
        self._temp_line = None    # 临时预览线

        # 拖拽平移
        self._pan_active = False
        self._pan_start_x = None
        self._pan_start_xlim = None

        self._build_ui()
        self._load_data(self.TYPE_DAILY)

    # ================================================================
    #  UI
    # ================================================================

    def _build_ui(self):
        self.setWindowTitle(f'{self.stock_code} - {self.stock_name} K线')
        self.resize(880, 640)
        self.setMinimumSize(640, 480)
        self.setStyleSheet(f'''
            QDialog {{ background-color: {C_PANEL}; }}
            QLabel {{ color: {C_TEXT}; font-size: 12px; font-family: "Microsoft YaHei"; }}
            QPushButton {{
                background: transparent; color: {C_DIM}; border: none;
                padding: 4px 10px; border-radius: 2px;
                font-size: 11px; font-weight: bold; font-family: "Microsoft YaHei";
            }}
            QPushButton:hover {{ background-color: {C_GRID}; color: {C_TEXT}; }}
            QPushButton:checked {{ background-color: #2962ff; color: #ffffff; }}
        ''')

        root = QVBoxLayout()
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(0)

        # --- 第一行：标题 + 周期按钮 ---
        row1 = QHBoxLayout()
        row1.setSpacing(8)

        name = QLabel(self.stock_name)
        name.setStyleSheet('font-size: 14px; font-weight: bold;')
        row1.addWidget(name)

        self._price_lbl = QLabel('')
        self._price_lbl.setStyleSheet('font-size: 14px; font-weight: bold;')
        row1.addWidget(self._price_lbl)

        self._change_lbl = QLabel('')
        self._change_lbl.setStyleSheet('font-size: 12px; font-weight: bold;')
        row1.addWidget(self._change_lbl)

        row1.addStretch()

        # 周期切换按钮
        self._period_btns = []
        for t in [self.TYPE_DAILY, self.TYPE_WEEKLY, self.TYPE_MONTHLY]:
            btn = QPushButton(t)
            btn.setCheckable(True)
            btn.clicked.connect(lambda _, ct=t: self._switch_period(ct))
            self._period_btns.append(btn)
            row1.addWidget(btn)
        self._period_btns[0].setChecked(True)

        # 数量按钮
        sep = QLabel('|')
        sep.setStyleSheet(f'color: {C_GRID};')
        row1.addWidget(sep)

        self._count_btns = []
        for n in [60, 120, 250]:
            btn = QPushButton(str(n))
            btn.setCheckable(True)
            btn.clicked.connect(lambda _, cnt=n: self._switch_count(cnt))
            self._count_btns.append(btn)
            row1.addWidget(btn)
        self._count_btns[1].setChecked(True)

        root.addLayout(row1)

        # --- 第二行：指标按钮 ---
        row2 = QHBoxLayout()
        row2.setSpacing(4)

        self._ind_btns = []
        for t in ['K线', self.TYPE_MACD, self.TYPE_KDJ, self.TYPE_RSI, self.TYPE_BOLL]:
            btn = QPushButton(t)
            btn.setCheckable(True)
            btn.clicked.connect(lambda _, ct=t: self._switch_indicator(ct))
            self._ind_btns.append(btn)
            row2.addWidget(btn)
        self._ind_btns[0].setChecked(True)

        row2.addStretch()

        # 工具按钮
        sep2 = QLabel('|')
        sep2.setStyleSheet(f'color: {C_GRID};')
        row2.addWidget(sep2)

        self._tool_btns = {}
        for tid, label in [('hover', '光标'), ('trendline', '趋势线'), ('hline', '水平线')]:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.clicked.connect(lambda _, t=tid: self._switch_tool(t))
            self._tool_btns[tid] = btn
            row2.addWidget(btn)
        self._tool_btns['hover'].setChecked(True)

        clear_btn = QPushButton('清除画线')
        clear_btn.clicked.connect(self._clear_drawings)
        row2.addWidget(clear_btn)

        reset_btn = QPushButton('重置缩放')
        reset_btn.clicked.connect(self._reset_zoom)
        row2.addWidget(reset_btn)

        # 额外数据标签
        self._extra_lbl = QLabel('')
        self._extra_lbl.setStyleSheet(f'font-size: 11px; color: {C_DIM};')
        row2.addWidget(self._extra_lbl)

        root.addLayout(row2)

        # --- 信息栏 ---
        self._info = QLabel('')
        self._info.setStyleSheet(f'font-size: 11px; color: {C_DIM}; padding: 1px 4px;')
        self._info.setFixedHeight(18)
        root.addWidget(self._info)

        # --- 图表 ---
        self.fig = Figure(figsize=(8.8, 5.6), dpi=100, facecolor=C_BG)
        self.canvas = FigureCanvas(self.fig)

        gs = GridSpec(2, 1, height_ratios=[3, 1], figure=self.fig, hspace=0)
        self.ax_main = self.fig.add_subplot(gs[0])
        self.ax_vol = self.fig.add_subplot(gs[1], sharex=self.ax_main)
        self.fig.subplots_adjust(left=0.05, right=0.95, top=0.98, bottom=0.04)

        self._style_ax(self.ax_main, show_x=False)
        self._style_ax(self.ax_vol, show_x=True)
        plt.setp(self.ax_main.get_xticklabels(), visible=False)

        self.canvas.mpl_connect('motion_notify_event', self._on_hover)
        self.canvas.mpl_connect('scroll_event', self._on_scroll)
        self.canvas.mpl_connect('button_press_event', self._on_click)
        self.canvas.mpl_connect('button_release_event', self._on_release)
        self.canvas.mpl_connect('key_press_event', self._on_key)

        root.addWidget(self.canvas)
        self.setLayout(root)

    def _style_ax(self, ax, show_x=True):
        ax.set_facecolor(C_BG)
        ax.tick_params(labelsize=8, colors=C_DIM, direction='in', length=2,
                       top=False, bottom=show_x, left=False, right=True)
        for s in ('top', 'left'):
            ax.spines[s].set_visible(False)
        for s in ('right', 'bottom'):
            ax.spines[s].set_color(C_GRID)
        ax.yaxis.set_label_position('right')
        ax.yaxis.tick_right()
        ax.grid(True, axis='y', color=C_GRID, linewidth=0.4, alpha=0.8)
        ax.set_axisbelow(True)

    # ================================================================
    #  切换控制
    # ================================================================

    def _switch_period(self, chart_type):
        for btn in self._period_btns:
            btn.setChecked(btn.text() == chart_type)
        self.chart_type = chart_type
        self._load_data(chart_type)

    def _switch_count(self, count):
        for btn in self._count_btns:
            btn.setChecked(btn.text() == str(count))
        self.data_count = count
        self._load_data(self.chart_type)

    def _switch_indicator(self, indicator):
        for btn in self._ind_btns:
            btn.setChecked(btn.text() == indicator)
        self.indicator = indicator
        self._zoom_xlim = None
        self._draw()

    def _switch_tool(self, tool):
        self._tool_mode = tool
        for tid, btn in self._tool_btns.items():
            btn.setChecked(tid == tool)
        self._draw_clicks.clear()
        self._remove_temp_line()
        # 切换到画线工具时改变鼠标指针
        if tool == 'hover':
            self.canvas.setCursor(Qt.ArrowCursor)
        else:
            self.canvas.setCursor(Qt.CrossCursor)

    def _clear_drawings(self):
        self._drawings.clear()
        self._draw_clicks.clear()
        self._remove_temp_line()
        self._draw()

    def _reset_zoom(self):
        self._zoom_xlim = None
        self._draw()

    # ================================================================
    #  数据加载
    # ================================================================

    def _load_data(self, chart_type):
        # 缓存
        key = f'kline_{chart_type}_{self.stock_code}_{self.data_count}'
        if key in self._cache:
            ts, d = self._cache[key]
            if (datetime.datetime.now() - ts).seconds < self._CACHE_TTL:
                self.dates, self.opens, self.highs, self.lows, self.closes, self.volumes = d
                self._draw()
                return

        if self._fetch_tencent(chart_type):
            return

        self._fallback_mock()

    def _code_prefix(self):
        if self.stock_code.startswith(('sh', 'sz')):
            return self.stock_code
        return ('sh' if self.stock_code[0] in ('6', '5') else 'sz') + self.stock_code

    def _fetch_tencent(self, chart_type):
        period = {'日K': 'day', '周K': 'week', '月K': 'month'}.get(chart_type, 'day')
        try:
            code = self._code_prefix()
            url = f'http://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={code},{period},,,{self.data_count},qfq'
            r = requests.get(url, timeout=10, proxies={'http': None, 'https': None})
            if r.status_code != 200:
                return False
            data = r.json()
            if data.get('code') != 0:
                return False
            sd = data['data'].get(code, {})
            items = sd.get(f'qfq{period}', []) or sd.get(period, [])
            if not items:
                return False

            self.dates = [x[0] for x in items]
            self.opens = [float(x[1]) for x in items]
            self.highs = [float(x[2]) for x in items]
            self.lows = [float(x[3]) for x in items]
            self.closes = [float(x[4]) for x in items]
            self.volumes = [int(float(x[5])) for x in items]

            key = f'kline_{chart_type}_{self.stock_code}_{self.data_count}'
            self._cache[key] = (datetime.datetime.now(),
                               (self.dates, self.opens, self.highs,
                                self.lows, self.closes, self.volumes))
            self._draw()
            return True
        except Exception as e:
            print(f'腾讯K线API失败: {e}')
            return False

    def _fallback_mock(self):
        """用实时行情生成模拟K线"""
        try:
            code = self._code_prefix()
            url = f'http://qt.gtimg.cn/q={code}'
            r = requests.get(url, timeout=10, proxies={'http': None, 'https': None})
            if r.status_code == 200:
                parts = r.content.decode('gbk').strip().split('~')
                if len(parts) > 36:
                    today = {
                        'open': float(parts[5]), 'close': float(parts[3]),
                        'high': float(parts[33]), 'low': float(parts[34]),
                        'volume': int(parts[36]), 'prev_close': float(parts[4])
                    }
                    self._gen_mock(today)
                    self._draw()
                    return
        except Exception:
            pass
        self._gen_mock({'open': 100, 'close': 101, 'high': 102, 'low': 99,
                        'volume': 100000, 'prev_close': 100})
        self._draw()

    def _gen_mock(self, today):
        import random
        base = today['prev_close']
        self.dates, self.opens, self.highs, self.lows, self.closes, self.volumes = [], [], [], [], [], []
        now = datetime.datetime.now()
        for i in range(60, 0, -1):
            d = now - datetime.timedelta(days=i)
            random.seed(i)
            o = base * (1 + random.uniform(-0.02, 0.02))
            c = o * (1 + random.uniform(-0.05, 0.05))
            h = max(o, c) * (1 + random.uniform(0, 0.02))
            l = min(o, c) * (1 - random.uniform(0, 0.02))
            v = int(random.uniform(50, 200) * 10000)
            self.dates.append(d.strftime('%Y-%m-%d'))
            self.opens.append(round(o, 2)); self.highs.append(round(h, 2))
            self.lows.append(round(l, 2)); self.closes.append(round(c, 2))
            self.volumes.append(v)
        self.dates.append(now.strftime('%Y-%m-%d'))
        self.opens.append(today['open']); self.highs.append(today['high'])
        self.lows.append(today['low']); self.closes.append(today['close'])
        self.volumes.append(today['volume'])

    # ================================================================
    #  指标计算
    # ================================================================

    @staticmethod
    def _ma(data, period):
        out = []
        for i in range(len(data)):
            if i < period - 1:
                out.append(np.nan)
            else:
                out.append(np.mean(data[i - period + 1:i + 1]))
        return out

    @staticmethod
    def _ema(data, period):
        out = [data[0]]
        k = 2 / (period + 1)
        for i in range(1, len(data)):
            out.append(data[i] * k + out[-1] * (1 - k))
        return out

    def _calc_boll(self, period=20, nbdev=2):
        """布林带：中轨=MA20, 上轨=中轨+2*std, 下轨=中轨-2*std"""
        mid = self._ma(self.closes, period)
        upper, lower = [], []
        for i in range(len(self.closes)):
            if i < period - 1:
                upper.append(np.nan); lower.append(np.nan)
            else:
                std = np.std(self.closes[i - period + 1:i + 1])
                upper.append(mid[i] + nbdev * std)
                lower.append(mid[i] - nbdev * std)
        return upper, mid, lower

    def _calc_macd(self):
        if len(self.closes) < 26:
            return [], [], []
        dif = [a - b for a, b in zip(self._ema(self.closes, 12), self._ema(self.closes, 26))]
        dea = self._ema(dif, 9)
        macd = [a - b for a, b in zip(dif, dea)]
        return dif, dea, macd

    def _calc_kdj(self, n=9, m1=3, m2=3):
        k_list, d_list, j_list = [], [], []
        for i in range(len(self.closes)):
            if i < n - 1:
                rsv = 50
            else:
                hh = max(self.highs[i - n + 1:i + 1])
                ll = min(self.lows[i - n + 1:i + 1])
                rsv = (self.closes[i] - ll) / (hh - ll) * 100 if hh != ll else 50
            k = (rsv + (m1 - 1) * (k_list[-1] if k_list else 50)) / m1
            d = (k + (m2 - 1) * (d_list[-1] if d_list else 50)) / m2
            j = 3 * k - 2 * d
            k_list.append(k); d_list.append(d); j_list.append(j)
        return k_list, d_list, j_list

    def _calc_rsi(self, period=6):
        if len(self.closes) < period + 1:
            return []
        gains, losses = [], []
        for i in range(1, len(self.closes)):
            chg = self.closes[i] - self.closes[i - 1]
            gains.append(max(chg, 0)); losses.append(max(-chg, 0))
        ag = sum(gains[:period]) / period
        al = sum(losses[:period]) / period
        out = [100 if al == 0 else 100 - 100 / (1 + ag / al)]
        for i in range(period, len(gains)):
            ag = (ag * (period - 1) + gains[i]) / period
            al = (al * (period - 1) + losses[i]) / period
            out.append(100 if al == 0 else 100 - 100 / (1 + ag / al))
        return out

    # ================================================================
    #  绘图
    # ================================================================

    def _draw(self):
        ind = getattr(self, 'indicator', 'K线')
        if ind == self.TYPE_MACD:
            self._draw_macd()
        elif ind == self.TYPE_KDJ:
            self._draw_kdj()
        elif ind == self.TYPE_RSI:
            self._draw_rsi()
        else:
            self._draw_kline(boll=(ind == self.TYPE_BOLL))
        self._update_title()
        self._update_extra()
        self._redraw_tools()
        self._apply_zoom()

    def _clear(self):
        self.ax_main.clear(); self.ax_vol.clear()
        self._style_ax(self.ax_main, show_x=False)
        self._style_ax(self.ax_vol, show_x=True)

    def _date_ticks(self, ax, n):
        step = max(1, n // 6)
        ticks = list(range(0, n, step))
        ax.set_xticks(ticks)
        ax.set_xticklabels([self.dates[i][5:] for i in ticks], fontsize=8, color=C_DIM)

    @staticmethod
    def _vol_fmt(x, _):
        if x >= 1e8: return f'{x/1e8:.1f}亿'
        if x >= 1e4: return f'{x/1e4:.0f}万'
        return str(int(x))

    # ---- K线蜡烛图 ----

    def _draw_kline(self, boll=False):
        self._clear()
        n = len(self.dates)
        if n == 0:
            return
        x = np.arange(n)
        o = np.array(self.opens); c = np.array(self.closes)
        h = np.array(self.highs); l = np.array(self.lows)
        v = np.array(self.volumes)
        up = c >= o

        # 影线
        for i in range(n):
            self.ax_main.vlines(x[i], l[i], h[i], color=C_UP if up[i] else C_DOWN, linewidth=0.8)

        # 实体
        bh = np.abs(c - o)
        bh = np.where(bh < (h.max() - l.min()) * 0.001, (h.max() - l.min()) * 0.001, bh)
        bb = np.minimum(o, c)
        bc = np.where(up, C_UP, C_DOWN)
        self.ax_main.bar(x, bh, bottom=bb, width=0.7, color=bc, edgecolor=bc, linewidth=0.3)

        # MA
        for period, color in [(5, C_MA5), (10, C_MA10), (20, C_MA20), (60, C_MA60)]:
            self.ax_main.plot(x, self._ma(list(c), period), color=color, linewidth=0.9,
                             alpha=0.9, label=f'MA{period}', antialiased=True)

        # BOLL布林带
        if boll:
            upper, mid, lower = self._calc_boll()
            self.ax_main.plot(x, upper, color=C_BOLL, linewidth=0.8, alpha=0.7, ls='--', label='BOLL上')
            self.ax_main.plot(x, mid, color=C_BOLL, linewidth=0.9, alpha=0.9, label='BOLL中')
            self.ax_main.plot(x, lower, color=C_BOLL, linewidth=0.8, alpha=0.7, ls='--', label='BOLL下')
            self.ax_main.fill_between(x, lower, upper, color=C_BOLL, alpha=0.04)

        self.ax_main.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f'{v:.2f}'))
        pad = (h.max() - l.min()) * 0.05
        self.ax_main.set_ylim(l.min() - pad, h.max() + pad)

        # 成交量
        self.ax_vol.bar(x, v, width=0.7, color=np.where(up, C_UP, C_DOWN), alpha=0.55, edgecolor='none')
        self.ax_vol.plot(x, self._ma(list(v), 5), color=C_MA5, linewidth=0.7, alpha=0.7)
        self.ax_vol.plot(x, self._ma(list(v), 10), color=C_MA10, linewidth=0.7, alpha=0.7)
        self.ax_vol.yaxis.set_major_formatter(plt.FuncFormatter(self._vol_fmt))

        self._date_ticks(self.ax_vol, n)
        self._show_info(n - 1)
        self.canvas.draw()

    # ---- MACD ----

    def _draw_macd(self):
        self._clear()
        dif, dea, macd = self._calc_macd()
        if not dif: return
        n = len(self.dates); x = np.arange(n)
        self.ax_main.plot(x, dif, color=C_MA5, linewidth=1.1, label='DIF', antialiased=True)
        self.ax_main.plot(x, dea, color=C_MA10, linewidth=1.1, label='DEA', antialiased=True)
        self.ax_main.axhline(0, color=C_DIM, linewidth=0.4, alpha=0.4)
        self.ax_main.legend(loc='upper left', fontsize=8, ncol=2, frameon=False, labelcolor=C_DIM)
        colors = [C_UP if m >= 0 else C_DOWN for m in macd]
        self.ax_vol.bar(x, macd, color=colors, width=0.65, alpha=0.7, edgecolor='none')
        self.ax_vol.axhline(0, color=C_DIM, linewidth=0.4, alpha=0.4)
        self._date_ticks(self.ax_vol, n)
        self.canvas.draw()

    # ---- KDJ ----

    def _draw_kdj(self):
        self._clear()
        k, d, j = self._calc_kdj()
        if not k: return
        n = len(self.dates); x = np.arange(n)
        self.ax_main.plot(x, k, color=C_MA5, linewidth=1.0, label='K', antialiased=True)
        self.ax_main.plot(x, d, color=C_MA10, linewidth=1.0, label='D', antialiased=True)
        self.ax_main.plot(x, j, color=C_MA20, linewidth=1.0, label='J', antialiased=True)
        self.ax_main.axhline(80, color=C_UP, ls='--', lw=0.5, alpha=0.3)
        self.ax_main.axhline(20, color=C_DOWN, ls='--', lw=0.5, alpha=0.3)
        self.ax_main.set_ylim(-10, 110)
        self.ax_main.legend(loc='upper left', fontsize=8, ncol=3, frameon=False, labelcolor=C_DIM)
        jc = [C_UP if v > 80 else C_DOWN if v < 20 else '#363a45' for v in j]
        self.ax_vol.bar(x, j, color=jc, width=0.6, alpha=0.5, edgecolor='none')
        self.ax_vol.axhline(0, color=C_DIM, lw=0.4, alpha=0.3)
        self._date_ticks(self.ax_vol, n)
        self.canvas.draw()

    # ---- RSI ----

    def _draw_rsi(self):
        self._clear()
        rsi = self._calc_rsi()
        if not rsi: return
        n = len(self.dates); x = np.arange(len(rsi))
        self.ax_main.plot(x, rsi, color=C_MA10, linewidth=1.1, label='RSI(6)', antialiased=True)
        self.ax_main.axhline(80, color=C_UP, ls='--', lw=0.5, alpha=0.3)
        self.ax_main.axhline(20, color=C_DOWN, ls='--', lw=0.5, alpha=0.3)
        self.ax_main.fill_between(x, 80, 100, color=C_UP, alpha=0.03)
        self.ax_main.fill_between(x, 0, 20, color=C_DOWN, alpha=0.03)
        self.ax_main.set_ylim(0, 100)
        self.ax_main.legend(loc='upper left', fontsize=8, frameon=False, labelcolor=C_DIM)
        rc = [C_UP if v > 80 else C_DOWN if v < 20 else '#363a45' for v in rsi]
        self.ax_vol.bar(x, rsi, color=rc, width=0.6, alpha=0.5, edgecolor='none')
        self._date_ticks(self.ax_vol, n)
        self.canvas.draw()

    # ================================================================
    #  标题 / 信息栏 / 额外数据
    # ================================================================

    def _update_title(self):
        if not self.closes: return
        c = self.closes[-1]
        prev = self.closes[-2] if len(self.closes) > 1 else self.opens[0]
        chg = c - prev
        pct = chg / prev * 100 if prev else 0
        up = chg >= 0
        col = C_UP if up else C_DOWN
        s = '+' if up else ''
        self._price_lbl.setText(f'{c:.2f}')
        self._price_lbl.setStyleSheet(f'font-size:14px; font-weight:bold; color:{col};')
        self._change_lbl.setText(f'{s}{chg:.2f}  {s}{pct:.2f}%')
        self._change_lbl.setStyleSheet(f'font-size:12px; font-weight:bold; color:{col};')

    def _update_extra(self):
        """更新右上角额外数据：振幅、涨跌幅、换手率"""
        if len(self.closes) < 2: return
        c = self.closes[-1]; o = self.opens[-1]
        h = self.highs[-1]; l = self.lows[-1]
        v = self.volumes[-1]
        prev = self.closes[-2]
        chg_pct = (c - prev) / prev * 100 if prev else 0
        amplitude = (h - l) / prev * 100 if prev else 0
        turnover = f'{v/1e4:.0f}万' if v >= 1e4 else str(v)
        self._extra_lbl.setText(
            f'涨幅:{chg_pct:+.2f}%  振幅:{amplitude:.2f}%  量:{turnover}')

    def _show_info(self, idx):
        if idx < 0 or idx >= len(self.dates): return
        d = self.dates[idx]
        o, h, l, c, v = self.opens[idx], self.highs[idx], self.lows[idx], self.closes[idx], self.volumes[idx]
        up = c >= o; cc = C_UP if up else C_DOWN
        vs = f'{v/1e4:.0f}万' if v >= 1e4 else str(v)
        prev = self.closes[idx - 1] if idx > 0 else o
        chg = c - prev; pct = chg / prev * 100 if prev else 0
        amp = (h - l) / prev * 100 if prev else 0
        sc = '+' if chg >= 0 else ''
        ma5 = self._ma(self.closes, 5); ma10 = self._ma(self.closes, 10)
        ma20 = self._ma(self.closes, 20); ma60 = self._ma(self.closes, 60)
        self._info.setTextFormat(Qt.RichText)
        self._info.setText(
            f'<span style="color:{C_DIM}">{d}</span> '
            f'<span style="color:{C_DIM}">开</span> <span style="color:{cc}">{o:.2f}</span> '
            f'<span style="color:{C_DIM}">高</span> <span style="color:{cc}">{h:.2f}</span> '
            f'<span style="color:{C_DIM}">低</span> <span style="color:{cc}">{l:.2f}</span> '
            f'<span style="color:{C_DIM}">收</span> <span style="color:{cc}">{c:.2f}</span> '
            f'<span style="color:{cc}">{sc}{chg:.2f}({sc}{pct:.2f}%)</span> '
            f'<span style="color:{C_DIM}">振幅</span> <span style="color:{cc}">{amp:.2f}%</span> '
            f'<span style="color:{C_DIM}">量</span> <span style="color:{cc}">{vs}</span> '
            f'<span style="color:{C_MA5}">MA5:{ma5[idx]:.2f}</span> '
            f'<span style="color:{C_MA10}">MA10:{ma10[idx]:.2f}</span> '
            f'<span style="color:{C_MA20}">MA20:{ma20[idx]:.2f}</span> '
            f'<span style="color:{C_MA60}">MA60:{ma60[idx]:.2f}</span>'
        )

    # ================================================================
    #  十字光标
    # ================================================================

    def _clear_hover(self):
        for attr in ('_hover_vline', '_hover_vline_vol', '_hover_hline',
                      '_hover_price_tag', '_hover_date_tag'):
            obj = getattr(self, attr, None)
            if obj is not None:
                try: obj.remove()
                except Exception: pass
                setattr(self, attr, None)

    def _on_hover(self, event):
        if not self.dates:
            return

        # 拖拽平移中
        if self._pan_active and event.button == 1 and self._pan_start_xlim is not None:
            dx = event.x - self._pan_start_x
            # 像素到数据坐标的转换
            bbox = self.ax_main.get_window_extent()
            pix_w = bbox.width
            if pix_w <= 0:
                return
            data_w = self._pan_start_xlim[1] - self._pan_start_xlim[0]
            data_dx = -dx / pix_w * data_w

            new_left = self._pan_start_xlim[0] + data_dx
            new_right = self._pan_start_xlim[1] + data_dx
            n = len(self.dates)

            # 边界限制
            if new_left < -0.5:
                new_left = -0.5
                new_right = new_left + data_w
            if new_right > n - 0.5:
                new_right = n - 0.5
                new_left = new_right - data_w

            self._zoom_xlim = (new_left, new_right)
            self.ax_main.set_xlim(new_left, new_right)
            self._update_date_ticks()
            self.canvas.draw_idle()
            return

        if event.inaxes not in (self.ax_main, self.ax_vol):
            self._clear_hover(); self.canvas.draw_idle(); return
        xd = event.xdata
        yd = event.ydata
        if xd is None:
            self._clear_hover(); self.canvas.draw_idle(); return

        # 画线模式：显示预览
        if self._tool_mode != 'hover' and event.button == 1:
            self._preview_draw(xd, yd, event.inaxes)
            self.canvas.draw_idle()
            return

        self._clear_hover()
        idx = int(round(xd))
        if idx < 0 or idx >= len(self.dates): return

        self._hover_vline = self.ax_main.axvline(idx, color=C_CROSS, lw=0.5, ls='--', alpha=0.7)
        self._hover_vline_vol = self.ax_vol.axvline(idx, color=C_CROSS, lw=0.5, ls='--', alpha=0.7)

        ind = getattr(self, 'indicator', 'K线')
        if ind in ('K线', self.TYPE_BOLL):
            self._hover_kline(idx)
        elif ind == self.TYPE_MACD:
            self._hover_macd(idx)
        elif ind == self.TYPE_KDJ:
            self._hover_kdj(idx)
        elif ind == self.TYPE_RSI:
            self._hover_rsi(idx)
        self.canvas.draw_idle()

    def _hover_kline(self, idx):
        c = self.closes[idx]
        cc = C_UP if c >= self.opens[idx] else C_DOWN
        self._hover_hline = self.ax_main.axhline(c, color=C_CROSS, lw=0.5, ls='--', alpha=0.7)
        self._hover_price_tag = self.ax_main.annotate(
            f' {c:.2f} ', xy=(1, c), xycoords=('axes fraction', 'data'),
            fontsize=8, color='#fff', fontweight='bold',
            bbox=dict(boxstyle='round,pad=0.2', fc=cc, ec='none', alpha=0.9),
            va='center', ha='left')
        self._hover_date_tag = self.ax_vol.annotate(
            f' {self.dates[idx]} ', xy=(idx, 0), xycoords=('data', 'axes fraction'),
            fontsize=8, color='#fff',
            bbox=dict(boxstyle='round,pad=0.2', fc='#2a2e39', ec='none', alpha=0.9),
            va='bottom', ha='center')
        self._show_info(idx)

    def _hover_macd(self, idx):
        dif, dea, macd = self._calc_macd()
        if idx < len(dif):
            self._hover_hline = self.ax_main.axhline(dif[idx], color=C_CROSS, lw=0.5, ls='--', alpha=0.7)
            self._info.setTextFormat(Qt.RichText)
            self._info.setText(
                f'<span style="color:{C_DIM}">{self.dates[idx]}</span> '
                f'<span style="color:{C_MA5}">DIF:{dif[idx]:.3f}</span> '
                f'<span style="color:{C_MA10}">DEA:{dea[idx]:.3f}</span> '
                f'<span style="color:{C_UP}">MACD:{macd[idx]:.3f}</span>')

    def _hover_kdj(self, idx):
        k, d, j = self._calc_kdj()
        if idx < len(k):
            self._hover_hline = self.ax_main.axhline(k[idx], color=C_CROSS, lw=0.5, ls='--', alpha=0.7)
            self._info.setTextFormat(Qt.RichText)
            self._info.setText(
                f'<span style="color:{C_DIM}">{self.dates[idx]}</span> '
                f'<span style="color:{C_MA5}">K:{k[idx]:.2f}</span> '
                f'<span style="color:{C_MA10}">D:{d[idx]:.2f}</span> '
                f'<span style="color:{C_MA20}">J:{j[idx]:.2f}</span>')

    def _hover_rsi(self, idx):
        rsi = self._calc_rsi()
        if idx < len(rsi):
            self._hover_hline = self.ax_main.axhline(rsi[idx], color=C_CROSS, lw=0.5, ls='--', alpha=0.7)
            self._info.setTextFormat(Qt.RichText)
            self._info.setText(
                f'<span style="color:{C_DIM}">{self.dates[idx]}</span> '
                f'<span style="color:{C_MA10}">RSI(6):{rsi[idx]:.2f}</span>')

    # ================================================================
    #  缩放
    # ================================================================

    def _on_scroll(self, event):
        """鼠标滚轮缩放"""
        if not self.dates or event.inaxes not in (self.ax_main, self.ax_vol):
            return
        n = len(self.dates)
        cur = list(self.ax_main.get_xlim())
        center = event.xdata if event.xdata is not None else (cur[0] + cur[1]) / 2

        factor = 0.8 if event.button == 'up' else 1.25
        span = cur[1] - cur[0]
        new_span = span * factor

        # 限制最小15根，最大全部
        min_span = 15
        max_span = n + 1
        new_span = max(min_span, min(max_span, new_span))

        # 保持鼠标位置不变
        ratio = (center - cur[0]) / span if span > 0 else 0.5
        new_left = center - new_span * ratio
        new_right = center + new_span * (1 - ratio)

        # 边界钳制
        if new_left < -0.5:
            new_left = -0.5
            new_right = new_left + new_span
        if new_right > n - 0.5:
            new_right = n - 0.5
            new_left = new_right - new_span

        self._zoom_xlim = (new_left, new_right)
        self.ax_main.set_xlim(new_left, new_right)
        self._update_date_ticks()
        self.canvas.draw_idle()

    def _update_date_ticks(self):
        """根据当前可视范围更新日期标签"""
        if not self.dates:
            return
        xlim = self.ax_main.get_xlim()
        start = max(0, int(xlim[0]))
        end = min(len(self.dates) - 1, int(xlim[1]))
        visible = end - start + 1
        step = max(1, visible // 6)
        ticks = list(range(start, end + 1, step))
        self.ax_vol.set_xticks(ticks)
        self.ax_vol.set_xticklabels([self.dates[i][5:] for i in ticks],
                                     fontsize=8, color=C_DIM)

    def _reset_zoom(self):
        self._zoom_xlim = None
        self._draw()

    # ================================================================
    #  画线工具
    # ================================================================

    def _on_click(self, event):
        """鼠标点击 - 画线工具 / 拖拽平移"""
        if event.button != 1:
            return

        # hover模式：开始拖拽平移
        if self._tool_mode == 'hover':
            if event.inaxes in (self.ax_main, self.ax_vol) and self.dates:
                self._pan_active = True
                self._pan_start_x = event.x
                self._pan_start_xlim = list(self.ax_main.get_xlim())
            return

        # 画线模式
        if event.inaxes != self.ax_main or not self.dates:
            return

        xd = event.xdata
        yd = event.ydata
        if xd is None or yd is None:
            return
        idx = int(round(xd))
        idx = max(0, min(idx, len(self.dates) - 1))

        if self._tool_mode == 'hline':
            # 水平线：单击即画
            self._drawings.append(('hline', yd))
            self._redraw_tools()
            self.canvas.draw_idle()

        elif self._tool_mode == 'trendline':
            self._draw_clicks.append((idx, yd))
            if len(self._draw_clicks) == 2:
                # 两点都收集完毕，画趋势线
                x1, y1 = self._draw_clicks[0]
                x2, y2 = self._draw_clicks[1]
                self._drawings.append(('trendline', x1, y1, x2, y2))
                self._draw_clicks.clear()
                self._remove_temp_line()
                self._redraw_tools()
                self.canvas.draw_idle()

    def _on_release(self, event):
        """鼠标释放 - 结束拖拽"""
        if event.button == 1:
            self._pan_active = False

    def _preview_draw(self, xd, yd, ax):
        """画线模式下的实时预览"""
        if self._tool_mode == 'trendline' and len(self._draw_clicks) == 1:
            self._remove_temp_line()
            x1, y1 = self._draw_clicks[0]
            self._temp_line, = self.ax_main.plot(
                [x1, xd], [y1, yd], color='#ffd600', linewidth=1.0,
                ls='--', alpha=0.7)
        elif self._tool_mode == 'hline':
            self._remove_temp_line()
            self._temp_line = self.ax_main.axhline(
                yd, color='#ffd600', linewidth=1.0, ls='--', alpha=0.5)

    def _remove_temp_line(self):
        if self._temp_line is not None:
            try: self._temp_line.remove()
            except Exception: pass
            self._temp_line = None

    def _on_key(self, event):
        """键盘事件 - Esc取消画线"""
        if event.key == 'escape':
            self._draw_clicks.clear()
            self._remove_temp_line()
            self._switch_tool('hover')
            self.canvas.draw_idle()

    def _redraw_tools(self):
        """重绘所有画线（在 _draw 之后调用）"""
        for item in self._drawings:
            if item[0] == 'hline':
                self.ax_main.axhline(item[1], color='#ffd600', linewidth=0.9,
                                      alpha=0.8, ls='-')
            elif item[0] == 'trendline':
                _, x1, y1, x2, y2 = item
                self.ax_main.plot([x1, x2], [y1, y2], color='#ffd600',
                                  linewidth=0.9, alpha=0.8)

    def _apply_zoom(self):
        """应用缩放状态"""
        if self._zoom_xlim is not None:
            self.ax_main.set_xlim(self._zoom_xlim)
            self._update_date_ticks()


# ================================================================
#  独立运行测试
# ================================================================

if __name__ == '__main__':
    import sys
    app = QApplication(sys.argv)
    dlg = KLineDialog('002261', '拓维信息')
    dlg.exec_()
