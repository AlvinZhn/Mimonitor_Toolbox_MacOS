"""情景模式仪表盘（DashboardInterface）视图与卡片组件。"""

from __future__ import annotations

from typing import Any, Dict, Optional

from PyQt6.QtCore import QEvent, QObject, QPoint, QRect, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    CardWidget,
    ElevatedCardWidget,
    FluentIcon as FIF,
    IconWidget,
    IndeterminateProgressBar,
    InfoBar,
    InfoBarPosition,
    MessageBox,
    PrimaryPushButton,
    ProgressBar,
    PushButton,
    ScrollArea,
    SimpleCardWidget,
    SubtitleLabel,
    TitleLabel,
    TransparentToolButton,
    isDarkTheme,
)

from .platform_adapter import get_platform_adapter
from .presets.manager import PresetManager, PresetProfile, get_preset_manager


class TagBadge(QLabel):
    """高对比度参数药丸标签，支持半透明浅底与高亮字体。"""

    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setStyleSheet(
            """
            TagBadge, QLabel {
                background-color: rgba(255, 255, 255, 0.12);
                color: #FFFFFF;
                border-radius: 4px;
                padding: 2px 8px;
                font-size: 11px;
                font-weight: 500;
            }
            """
        )


class PresetCard(ElevatedCardWidget):
    """大卡片展示单个情景模式，支持激活态边框高亮、参数标签与应用反馈。"""

    apply_clicked = pyqtSignal(str)  # preset_id
    delete_clicked = pyqtSignal(str)  # preset_id

    def __init__(self, preset: PresetProfile, parent=None):
        super().__init__(parent)
        self.preset = preset
        self._is_active = False
        self._is_loading = False

        self.setFixedSize(290, 200)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(18, 16, 18, 14)
        self.main_layout.setSpacing(8)

        # 1. 顶部行：图标 + 标题 + 标签 / 删除按钮
        top_row = QHBoxLayout()
        top_row.setSpacing(10)
        top_row.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        # 映射图标名至 FIF
        icon_name = getattr(preset, "icon", "PALETTE")
        fif_icon = getattr(FIF, icon_name, FIF.PALETTE)
        self.icon_widget = IconWidget(fif_icon, self)
        self.icon_widget.setFixedSize(24, 24)
        top_row.addWidget(self.icon_widget)

        self.title_label = SubtitleLabel(preset.name, self)
        title_font = self.title_label.font()
        title_font.setPixelSize(16)
        title_font.setBold(True)
        self.title_label.setFont(title_font)
        top_row.addWidget(self.title_label, 1)

        if preset.is_builtin:
            tag_label = CaptionLabel("官方", self)
            tag_label.setStyleSheet("color: #734EFF; font-weight: bold;")
            top_row.addWidget(tag_label)
        else:
            self.del_btn = TransparentToolButton(FIF.DELETE, self)
            self.del_btn.setToolTip("删除该自定义情景")
            self.del_btn.setFixedSize(28, 28)
            self.del_btn.clicked.connect(lambda: self.delete_clicked.emit(self.preset.id))
            top_row.addWidget(self.del_btn)

        self.main_layout.addLayout(top_row)

        # 2. 描述文本
        self.desc_label = CaptionLabel(preset.description, self)
        self.desc_label.setWordWrap(True)
        self.desc_label.setMaximumHeight(36)
        self.main_layout.addWidget(self.desc_label)

        # 3. 关键参数标签药丸栏
        chips_row = QHBoxLayout()
        chips_row.setSpacing(6)
        smap = preset.settings_map

        b_val = smap.get("backlight", "-")
        chips_row.addWidget(self._make_chip(f"背光 {b_val}%"))

        dim_names = {0: "控光 关", 1: "控光 低", 2: "控光 中", 3: "控光 高"}
        dim_val = smap.get("picture_local_dimming")
        if dim_val is not None:
            chips_row.addWidget(self._make_chip(dim_names.get(int(dim_val), f"控光 {dim_val}")))

        cs_names = {0: "色域 自动", 3: "sRGB", 6: "DCI-P3", 4: "AdobeRGB"}
        cs_val = smap.get("tv_picture_advanced_video_color_space")
        if cs_val is not None:
            chips_row.addWidget(self._make_chip(cs_names.get(int(cs_val), "广色域")))

        chips_row.addStretch(1)
        self.main_layout.addLayout(chips_row)

        self.main_layout.addStretch(1)

        # 4. 底部动作条与进度条
        self.progress_bar = IndeterminateProgressBar(self)
        self.progress_bar.setVisible(False)
        self.progress_bar.setFixedHeight(4)
        self.main_layout.addWidget(self.progress_bar)

        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(8)

        self.status_tag = CaptionLabel("", self)
        bottom_row.addWidget(self.status_tag, 1)

        self.apply_btn = PrimaryPushButton(FIF.ACCEPT, "一键应用", self)
        self.apply_btn.setMinimumWidth(102)
        self.apply_btn.clicked.connect(self._on_apply_clicked)
        bottom_row.addWidget(self.apply_btn)

        self.main_layout.addLayout(bottom_row)
        self._update_style()

    def _make_chip(self, text: str) -> "TagBadge":
        return TagBadge(text, self)

    def _on_apply_clicked(self):
        if not self._is_loading:
            self.apply_clicked.emit(self.preset.id)

    def mousePressEvent(self, event):
        # 点击卡片任意空白区域亦触发应用
        if not self._is_loading and event.button() == Qt.MouseButton.LeftButton:
            self.apply_clicked.emit(self.preset.id)
        super().mousePressEvent(event)

    def set_active(self, active: bool):
        self._is_active = active
        self._update_style()

    def set_loading(self, loading: bool):
        self._is_loading = loading
        self.apply_btn.setEnabled(not loading)
        self.progress_bar.setVisible(loading)
        if loading:
            self.apply_btn.setText("应用中...")
            self.status_tag.setText("正在下发参数...")
        else:
            self.apply_btn.setText("当前生效" if self._is_active else "一键应用")
            self.status_tag.setText("● 正在生效" if self._is_active else "")
        self._update_style()

    def _update_style(self):
        if self._is_active:
            border_color = "#734EFF"
            bg = "rgba(115, 78, 255, 0.08)"
            self.status_tag.setText("● 正在生效")
            self.status_tag.setStyleSheet("color: #734EFF; font-weight: bold;")
            self.apply_btn.setText("当前生效")
            self.apply_btn.setEnabled(False)
        else:
            border_color = "transparent"
            bg = "transparent"
            self.status_tag.setText("")
            if not self._is_loading:
                self.apply_btn.setText("一键应用")
                self.apply_btn.setEnabled(True)

        self.setStyleSheet(
            f"""
            PresetCard {{
                border: 2px solid {border_color};
                background-color: {bg};
                border-radius: 8px;
            }}
            """
        )


class DashboardStatusBar(SimpleCardWidget):
    """状态摘要栏：实时展示显示器连接状态与核心参数（背光、精密控光、色温、色域、HDR）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(84)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 12, 24, 12)
        layout.setSpacing(20)

        # 1. 连接状态区块
        conn_col = QVBoxLayout()
        conn_col.setSpacing(4)
        conn_col.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        conn_title = CaptionLabel("显示器连接状态", self)
        self.conn_status_label = BodyLabel("未连接", self)
        font = self.conn_status_label.font()
        font.setBold(True)
        self.conn_status_label.setFont(font)
        conn_col.addWidget(conn_title)
        conn_col.addWidget(self.conn_status_label)
        layout.addLayout(conn_col)

        layout.addSpacing(10)
        sep1 = QFrame(self)
        sep1.setFrameShape(QFrame.Shape.VLine)
        sep1.setStyleSheet("color: rgba(128, 128, 128, 0.2);")
        layout.addWidget(sep1)

        # 2. 核心状态网格指标
        metrics = [
            ("backlight", "背光亮度", "-- %"),
            ("local_dimming", "精密控光", "--"),
            ("color_space", "色域映射", "--"),
            ("hdr_status", "HDR 状态", "--"),
        ]

        self.metric_labels: Dict[str, BodyLabel] = {}
        for key, title, default_val in metrics:
            col = QVBoxLayout()
            col.setSpacing(4)
            col.setAlignment(Qt.AlignmentFlag.AlignVCenter)
            t_lbl = CaptionLabel(title, self)
            v_lbl = BodyLabel(default_val, self)
            v_font = v_lbl.font()
            v_font.setBold(True)
            v_lbl.setFont(v_font)
            col.addWidget(t_lbl)
            col.addWidget(v_lbl)
            layout.addLayout(col)
            self.metric_labels[key] = v_lbl

        layout.addStretch(1)

    def update_connection_state(self, connected: bool, ip: str = ""):
        if connected:
            self.conn_status_label.setText(f"● 已连接 ({ip})")
            self.conn_status_label.setStyleSheet("color: #10B981; font-weight: bold;")
        else:
            self.conn_status_label.setText("○ 未连接 (离线)")
            self.conn_status_label.setStyleSheet("color: #EF4444; font-weight: bold;")

    def update_metrics(self, settings_pool: dict):
        """根据当前参数池批量更新摘要栏指标。"""
        # 背光
        b = settings_pool.get("backlight")
        if b is not None:
            self.metric_labels["backlight"].setText(f"{b} %")

        # 控光
        dim_map = {0: "关", 1: "低", 2: "中", 3: "高"}
        d = settings_pool.get("picture_local_dimming")
        if d is not None:
            self.metric_labels["local_dimming"].setText(dim_map.get(int(d), str(d)))

        # 色域
        cs_map = {0: "自动", 3: "sRGB", 6: "DCI-P3", 4: "AdobeRGB", 5: "BT2020", 7: "BT709"}
        cs = settings_pool.get("tv_picture_advanced_video_color_space")
        if cs is not None:
            self.metric_labels["color_space"].setText(cs_map.get(int(cs), str(cs)))

        # HDR 状态
        try:
            is_hdr = get_platform_adapter().get_hdr_state()
            self.metric_labels["hdr_status"].setText("已开启 (HDR)" if is_hdr else "SDR 标准")
        except Exception:
            self.metric_labels["hdr_status"].setText("未知")


class DashboardInterface(ScrollArea):
    """情景模式仪表盘顶层视图。"""

    preset_applied = pyqtSignal(dict)  # 发送应用的 settings_map 供专家设置页同步
    request_page_navigation = pyqtSignal(str)  # 页面跳转请求

    def __init__(self, parent=None):
        super().__init__(parent)
        self.preset_manager = get_preset_manager()
        self._cards: Dict[str, PresetCard] = {}

        self.setWidgetResizable(True)
        self.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self.container = QWidget(self)
        self.container.setObjectName("DashboardContainer")
        self.container.setStyleSheet("#DashboardContainer { background: transparent; }")
        self.setWidget(self.container)

        self.main_layout = QVBoxLayout(self.container)
        self.main_layout.setContentsMargins(36, 28, 36, 28)
        self.main_layout.setSpacing(20)
        self.main_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self._build_header()
        self._build_status_bar()
        self._build_cards_section()

    def _build_header(self):
        header_layout = QHBoxLayout()
        header_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        title_col = QVBoxLayout()
        title_col.setSpacing(4)
        title = TitleLabel("情景仪表盘", self.container)
        title_font = title.font()
        title_font.setPixelSize(28)
        title_font.setBold(True)
        title.setFont(title_font)
        title_col.addWidget(title)

        subtitle = BodyLabel("一键切换画质、控光与高刷组合，或直接快照当前配置", self.container)
        subtitle.setStyleSheet("color: rgba(128, 128, 128, 0.9);")
        title_col.addWidget(subtitle)
        header_layout.addLayout(title_col, 1)

        # 核心操作按钮：快照保存
        self.save_snapshot_btn = PrimaryPushButton(FIF.ADD, "保存当前为新情景", self.container)
        self.save_snapshot_btn.setFixedHeight(38)
        self.save_snapshot_btn.clicked.connect(self._on_save_snapshot_clicked)
        header_layout.addWidget(self.save_snapshot_btn)

        self.main_layout.addLayout(header_layout)

    def _build_status_bar(self):
        self.status_bar = DashboardStatusBar(self.container)
        self.main_layout.addWidget(self.status_bar)

    def _build_cards_section(self):
        section_title = SubtitleLabel("情景模式", self.container)
        self.main_layout.addWidget(section_title)

        # 网格布局放置情景大卡片
        self.grid_widget = QWidget(self.container)
        self.grid_layout = QGridLayout(self.grid_widget)
        self.grid_layout.setContentsMargins(0, 0, 0, 0)
        self.grid_layout.setSpacing(18)
        self.grid_layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

        self.main_layout.addWidget(self.grid_widget)
        self.main_layout.addStretch(1)

        self.reload_cards()

    def reload_cards(self):
        """重新加载并刷新全部情景卡片。"""
        # 清除现有卡片
        while self.grid_layout.count():
            child = self.grid_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        self._cards.clear()

        presets = self.preset_manager.get_all_presets()
        columns = 3
        for index, preset in enumerate(presets):
            row = index // columns
            col = index % columns

            card = PresetCard(preset, self.grid_widget)
            card.apply_clicked.connect(self.apply_preset)
            card.delete_clicked.connect(self.delete_preset)

            if preset.id == self.preset_manager.active_preset_id:
                card.set_active(True)

            self.grid_layout.addWidget(card, row, col)
            self._cards[preset.id] = card

    def apply_preset(self, preset_id: str):
        """串行安全应用情景模式。"""
        preset = self.preset_manager.get_preset(preset_id)
        if not preset:
            return

        parent_window = self.window()
        adb_connected = getattr(parent_window, "adb_connected", False)
        if not adb_connected:
            InfoBar.warning(
                title="尚未连接显示器",
                content="请先在侧边栏【主页 & 连接】页面连接显示器 ADB，方可下发情景参数。",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP_RIGHT,
                duration=3500,
                parent=self,
            )
            return

        # 锁定所有卡片，并在目标卡片展示加载进度条，防御高频连击
        target_card = self._cards.get(preset_id)
        for cid, card in self._cards.items():
            if cid == preset_id:
                card.set_loading(True)
            else:
                card.setEnabled(False)

        def on_finished(success: bool, msg: str):
            # 恢复卡片状态
            for cid, card in self._cards.items():
                card.set_loading(False)
                card.setEnabled(True)
                card.set_active(cid == preset_id if success else False)

            if success:
                InfoBar.success(
                    title="应用成功",
                    content=msg,
                    orient=Qt.Orientation.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP_RIGHT,
                    duration=3000,
                    parent=self,
                )
                # 触发联动信号通知高级设置页同步更新 Slider/Button
                self.preset_applied.emit(preset.settings_map)
                # 刷新状态摘要栏
                self.status_bar.update_metrics(preset.settings_map)
            else:
                InfoBar.error(
                    title="应用失败",
                    content=msg,
                    orient=Qt.Orientation.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP_RIGHT,
                    duration=4000,
                    parent=self,
                )

        # 启动动作流水线后台安全下发
        self.preset_manager.apply_preset_pipeline(
            preset=preset,
            app=parent_window,
            on_finished=on_finished,
        )

    def delete_preset(self, preset_id: str):
        """删除指定自定义情景。"""
        preset = self.preset_manager.get_preset(preset_id)
        if not preset:
            return

        w = MessageBox(
            "确认删除",
            f"确定要删除自定义情景【{preset.name}】吗？",
            self.window(),
        )
        w.yesButton.setText("删除")
        w.cancelButton.setText("取消")
        if w.exec():
            if self.preset_manager.remove_preset(preset_id):
                InfoBar.success(
                    title="删除成功",
                    content=f"已删除情景【{preset.name}】",
                    orient=Qt.Orientation.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP_RIGHT,
                    duration=2500,
                    parent=self,
                )
                self.reload_cards()

    def _on_save_snapshot_clicked(self):
        """防空值逆向快照保存。"""
        parent_window = self.window()
        adb_connected = getattr(parent_window, "adb_connected", False)
        if not adb_connected:
            InfoBar.warning(
                title="无法保存快照",
                content="尚未连接显示器，无可用实时参数。请先在主页完成连接。",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP_RIGHT,
                duration=3500,
                parent=self,
            )
            return

        # 提取当前实时参数池（支持从 parent_window.values 或 slider/state_buttons 提取）
        current_settings = {}
        if hasattr(parent_window, "sliders"):
            for name, (slider, _) in parent_window.sliders.items():
                current_settings[name] = slider.value()

        if hasattr(parent_window, "state_buttons"):
            for sk, btns in parent_window.state_buttons.items():
                for val, b in btns.items():
                    if b.isChecked():
                        current_settings[sk] = val
                        break

        # 额外融合 parent_window.values
        if hasattr(parent_window, "values") and isinstance(parent_window.values, dict):
            for k, v in parent_window.values.items():
                if k not in current_settings:
                    current_settings[k] = v

        # 防御性校验：检查参数完整度
        if not current_settings or "backlight" not in current_settings:
            InfoBar.warning(
                title="参数不完整",
                content="尚未读取到当前显示器的画质参数，请先进入【画面设置】刷新数据。",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP_RIGHT,
                duration=3500,
                parent=self,
            )
            return

        # 弹出输入对话框获取情景名称
        name, ok = QInputDialog.getText(
            self.window(),
            "保存当前情景",
            "请输入新情景名称：",
            QLineEdit.EchoMode.Normal,
            "我的自定义情景",
        )
        if ok and name.strip():
            preset = self.preset_manager.create_snapshot(
                current_settings=current_settings,
                name=name.strip(),
                icon="PALETTE",
                description="根据当前显示器实时参数生成的自定义情景快照",
            )
            if preset and self.preset_manager.add_preset(preset):
                InfoBar.success(
                    title="保存成功",
                    content=f"已创建新情景【{preset.name}】！",
                    orient=Qt.Orientation.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP_RIGHT,
                    duration=3000,
                    parent=self,
                )
                self.reload_cards()
            else:
                InfoBar.error(
                    title="保存失败",
                    content="生成情景快照数据异常，请重试。",
                    orient=Qt.Orientation.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP_RIGHT,
                    duration=3000,
                    parent=self,
                )

    def sync_external_state(self, current_settings: dict, connected: bool, ip: str = ""):
        """接收专家设置页或设备变化触发的外部状态更新。"""
        self.status_bar.update_connection_state(connected, ip)
        self.status_bar.update_metrics(current_settings)
