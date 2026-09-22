"""Vista del canvas: arrastrar y soltar símbolos, modo conexión, edición y borrado."""
from __future__ import annotations

import copy
import json
import math
from typing import Dict, List, Optional

from PyQt5.QtCore import Qt, pyqtSignal, QPointF, QRectF
from PyQt5.QtGui import QPainter, QColor, QPen, QKeySequence, QImage
from PyQt5.QtWidgets import QGraphicsView, QGraphicsScene

from .canvas_items import (NodeItem, ConnectionItem, create_item, set_snap_grid, snap_grid_enabled,
                           snap_grid_size)
from .dialogs import NodeEditDialog, ConnectionNoteDialog
from .engine import ordered_flow
from .models import VSMMap, make_node, node_from_dict, new_id, CONN_LABELS
from .sim_player import SimOverlay
from .toolbox import MIME_TYPE


class CanvasView(QGraphicsView):
    mapChanged = pyqtSignal()
    statusMessage = pyqtSignal(str)
    connectionModeCancelled = pyqtSignal()   # la ventana desmarca los botones de conexión
    mapReplaced = pyqtSignal()               # se cargó otro mapa o se deshizo/rehizo (las animaciones se detienen)

    def __init__(self, vmap: VSMMap, parent=None):
        super().__init__(parent)
        self.map = vmap
        self._scene = QGraphicsScene(-400, -200, 4800, 1800, self)
        self.setScene(self._scene)
        self.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        self.setAcceptDrops(True)
        self.setDragMode(QGraphicsView.RubberBandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setBackgroundBrush(QColor("#fafafa"))
        self._node_items: Dict[str, NodeItem] = {}
        self._conn_items: List[ConnectionItem] = []
        self._conn_kind: Optional[str] = None
        self._conn_source: Optional[NodeItem] = None
        self._undo_stack: List[dict] = []
        self._redo_stack: List[dict] = []
        self._undo_limit = 60
        self._pre_drag_state: Optional[dict] = None
        self._clipboard: Optional[dict] = None
        self.set_map(vmap)

    # ------------------------------------------------------------------ mapa
    def set_map(self, vmap: VSMMap) -> None:
        self.map = vmap
        self._undo_stack.clear()
        self._redo_stack.clear()
        self._pre_drag_state = None
        self.cancel_connection_mode()
        self._scene.clear()
        self._node_items.clear()
        self._conn_items.clear()
        for node in vmap.nodes.values():
            self._add_node_item(node)
        for conn in vmap.connections:
            self._add_conn_item(conn)
        self.fit_content()
        self.mapReplaced.emit()
        self.mapChanged.emit()

    def fit_content(self) -> None:
        rect = self._scene.itemsBoundingRect()
        if rect.isNull():
            self.resetTransform()
            self.centerOn(400, 200)
            return
        rect = rect.adjusted(-40, -40, 40, 40)
        self.fitInView(rect, Qt.KeepAspectRatio)
        if self.transform().m11() > 1.2:
            self.resetTransform()
            self.centerOn(rect.center())

    def refresh_style(self) -> None:
        """Repinta todo tras cambiar el estilo de símbolos (tabla / libro)."""
        for it in self._node_items.values():
            it.prepareGeometryChange()
            it.update()
        for c in self._conn_items:
            c.update_path()
            c.update()

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:
        super().drawBackground(painter, rect)
        if not snap_grid_enabled():
            return
        size = snap_grid_size()
        painter.setPen(QPen(QColor(0, 0, 0, 22), 0))
        x = int(rect.left()) - (int(rect.left()) % int(size))
        while x < rect.right():
            painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
            x += int(size)
        y = int(rect.top()) - (int(rect.top()) % int(size))
        while y < rect.bottom():
            painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
            y += int(size)

    def item_for(self, node_id: str) -> Optional[NodeItem]:
        return self._node_items.get(node_id)

    def node_items(self) -> Dict[str, NodeItem]:
        return dict(self._node_items)

    def _add_node_item(self, node) -> NodeItem:
        item = create_item(node)
        item.moved.connect(self.mapChanged)
        self._scene.addItem(item)
        self._node_items[node.id] = item
        return item

    def _add_conn_item(self, conn) -> Optional[ConnectionItem]:
        src, dst = self._node_items.get(conn.source), self._node_items.get(conn.target)
        if src is None or dst is None:
            return None
        item = ConnectionItem(conn, src, dst)
        self._scene.addItem(item)
        self._conn_items.append(item)
        return item

    def add_node_at(self, kind: str, scene_pos: QPointF, preset: Optional[dict] = None) -> NodeItem:
        """Crea un nodo centrado (horizontalmente) en `scene_pos`. `preset` fija atributos iniciales."""
        node = make_node(kind)
        for k, v in (preset or {}).items():
            setattr(node, k, v)
        self.map.add_node(node)
        item = self._add_node_item(node)
        item.setPos(scene_pos.x() - item.WIDTH / 2, scene_pos.y() - 20)   # sincroniza node.x/y
        self.mapChanged.emit()
        return item

    # ------------------------------------------------------------ exportación
    def export_rect(self) -> QRectF:
        """Rectángulo de la escena que contiene todo el mapa (con margen). Nulo si el mapa está vacío."""
        if not self._node_items:
            return QRectF()
        rect = QRectF()
        for it in self._node_items.values():
            rect = rect.united(it.sceneBoundingRect())
        for c in self._conn_items:
            rect = rect.united(c.path().boundingRect().adjusted(-24, -30, 24, 12))   # holgura para notas/teléfono
        return rect.adjusted(-24, -24, 24, 24)

    def render_to(self, painter: QPainter, target: QRectF, source: QRectF) -> None:
        """Dibuja `source` (coords. de escena) dentro de `target` conservando la proporción.

        Sirve para imagen, PDF vectorial, etc. Se quitan la selección y el resaltado de "origen pendiente"
        mientras se dibuja (y se restauran después) para que no salgan en el archivo exportado.
        """
        selected = [it for it in self._scene.selectedItems()]
        pending = self._conn_source
        overlays = [it for it in self._scene.items() if isinstance(it, SimOverlay) and it.isVisible()]
        try:
            for ov in overlays:                 # la animación no sale en las exportaciones
                ov.setVisible(False)
            self._scene.clearSelection()
            if pending is not None:
                pending.set_pending(False)
            painter.save()
            painter.setClipRect(target)
            self._scene.render(painter, target, source, Qt.KeepAspectRatio)
            painter.restore()
        finally:
            for it in selected:
                it.setSelected(True)
            for ov in overlays:
                ov.setVisible(True)
            if pending is not None:
                pending.set_pending(True)

    def export_image(self, scale: float = 2.0, max_side: int = 8000) -> Optional[QImage]:
        """Imagen del mapa completo sobre fondo blanco. `scale` = píxeles por unidad de escena. None si está vacío."""
        src = self.export_rect()
        if src.isNull():
            return None
        scale = min(scale, max_side / max(src.width(), src.height()))
        w, h = max(1, math.ceil(src.width() * scale)), max(1, math.ceil(src.height() * scale))
        img = QImage(w, h, QImage.Format_RGB32)
        img.fill(Qt.white)
        p = QPainter(img)
        p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing | QPainter.SmoothPixmapTransform)
        self.render_to(p, QRectF(0, 0, w, h), src)
        p.end()
        return img

    # ------------------------------------------------------- alinear a rejilla
    def set_snap_to_grid(self, enabled: bool) -> None:
        set_snap_grid(enabled)
        self.viewport().update()

    def snap_to_grid_enabled(self) -> bool:
        return snap_grid_enabled()

    # ------------------------------------------------------- deshacer / rehacer
    def _snapshot(self) -> dict:
        return copy.deepcopy(self.map.to_dict())

    def push_undo(self) -> None:
        """Guarda el estado actual antes de una modificación (llamar ANTES de mutar el mapa)."""
        self._undo_stack.append(self._snapshot())
        if len(self._undo_stack) > self._undo_limit:
            self._undo_stack.pop(0)
        self._redo_stack.clear()

    def can_undo(self) -> bool:
        return bool(self._undo_stack)

    def can_redo(self) -> bool:
        return bool(self._redo_stack)

    def _restore(self, state: dict) -> None:
        vmap = VSMMap.from_dict(state)
        vmap.case_id = self.map.case_id
        self.map = vmap
        self.cancel_connection_mode()
        self._scene.clear()
        self._node_items.clear()
        self._conn_items.clear()
        for node in vmap.nodes.values():
            self._add_node_item(node)
        for conn in vmap.connections:
            self._add_conn_item(conn)
        self.mapReplaced.emit()
        self.mapChanged.emit()

    def undo(self) -> None:
        if not self._undo_stack:
            self.statusMessage.emit("Nada que deshacer.")
            return
        self._redo_stack.append(self._snapshot())
        self._restore(self._undo_stack.pop())
        self.statusMessage.emit("Acción deshecha.")

    def redo(self) -> None:
        if not self._redo_stack:
            self.statusMessage.emit("Nada que rehacer.")
            return
        self._undo_stack.append(self._snapshot())
        self._restore(self._redo_stack.pop())
        self.statusMessage.emit("Acción rehecha.")

    # ------------------------------------------------------------ copiar/pegar
    def copy_selected(self) -> None:
        nodes = [it.node for it in self._scene.selectedItems() if isinstance(it, NodeItem)]
        if not nodes:
            self.statusMessage.emit("Selecciona uno o más símbolos para copiar.")
            return
        ids = {n.id for n in nodes}
        conns = [c for c in self.map.connections if c.source in ids and c.target in ids]
        self._clipboard = {"nodes": [n.to_dict() for n in nodes],
                           "connections": [c.to_dict() for c in conns]}
        self.statusMessage.emit(f"{len(nodes)} símbolo(s) copiado(s).")

    def paste_clipboard(self) -> None:
        if not self._clipboard or not self._clipboard["nodes"]:
            self.statusMessage.emit("No hay nada para pegar.")
            return
        self.push_undo()
        offset = 40.0
        id_map: Dict[str, str] = {}
        new_items = []
        for nd in self._clipboard["nodes"]:
            node = node_from_dict(nd)
            old_id = node.id
            node.id = new_id()
            id_map[old_id] = node.id
            node.x += offset
            node.y += offset
            self.map.add_node(node)
            new_items.append(self._add_node_item(node))
        for cd in self._clipboard["connections"]:
            src, dst = id_map.get(cd["source"]), id_map.get(cd["target"])
            if src and dst:
                conn = self.map.add_connection(src, dst, cd["kind"], cd.get("note", ""))
                if conn:
                    self._add_conn_item(conn)
        self._scene.clearSelection()
        for it in new_items:
            it.setSelected(True)
        self.mapChanged.emit()
        self.statusMessage.emit(f"{len(new_items)} símbolo(s) pegado(s).")

    # ------------------------------------------------------------- autoconectar
    def auto_connect(self) -> None:
        """Conecta con flechas push, en orden de X, proveedor → flujo → cliente."""
        self.push_undo()
        flow = ordered_flow(self.map)
        sups = self.map.nodes_of("supplier")[:1]
        cuss = self.map.nodes_of("customer")[:1]
        chain = sups + flow + cuss
        created = 0
        for a, b in zip(chain, chain[1:]):
            already = any(c.source == a.id and c.target == b.id for c in self.map.connections)
            if already:
                continue
            conn = self.map.add_connection(a.id, b.id, "push")
            if conn is not None:
                self._add_conn_item(conn)
                created += 1
        if created:
            self.mapChanged.emit()
            self.statusMessage.emit(f"Autoconectar: se crearon {created} flecha(s) de material (push).")
        else:
            self._undo_stack.pop()
            self.statusMessage.emit("Autoconectar: no había nada nuevo que conectar (usa proveedor/cliente "
                                    "y ubica los símbolos en el orden del flujo).")

    # ------------------------------------------------------- modo conexión
    def set_connection_mode(self, kind: Optional[str]) -> None:
        self.cancel_connection_mode()
        self._conn_kind = kind
        if kind:
            self.setDragMode(QGraphicsView.NoDrag)
            self.setCursor(Qt.CrossCursor)
            self.statusMessage.emit(f"{CONN_LABELS[kind]}: clic en el origen y luego en el destino. "
                                    f"Esc para cancelar.")

    def cancel_connection_mode(self) -> None:
        if self._conn_source is not None:
            self._conn_source.set_pending(False)
        self._conn_source = None
        self._conn_kind = None
        self.setDragMode(QGraphicsView.RubberBandDrag)
        self.unsetCursor()

    @property
    def connection_mode(self) -> Optional[str]:
        return self._conn_kind

    def _node_at(self, view_pos) -> Optional[NodeItem]:
        for it in self.items(view_pos):
            if isinstance(it, NodeItem):
                return it
        return None

    def _conn_at(self, view_pos) -> Optional[ConnectionItem]:
        for it in self.items(view_pos):
            if isinstance(it, ConnectionItem):
                return it
        return None

    def _connect_click(self, item: NodeItem) -> None:
        if self._conn_source is None:
            self._conn_source = item
            item.set_pending(True)
            self.statusMessage.emit("Origen seleccionado: ahora haz clic en el destino.")
            return
        src = self._conn_source
        src.set_pending(False)
        self._conn_source = None
        if item is src:
            return
        conn = self.map.add_connection(src.node.id, item.node.id, self._conn_kind)
        if conn is None:
            self.statusMessage.emit("Esa conexión ya existe.")
            return
        self._add_conn_item(conn)
        self.statusMessage.emit("Conexión creada. Elige otro origen o pulsa Esc.")
        self.mapChanged.emit()

    # ------------------------------------------------------------- eventos
    def mousePressEvent(self, event):
        if self._conn_kind and event.button() == Qt.LeftButton:
            item = self._node_at(event.pos())
            if item is not None:
                self._connect_click(item)
            event.accept()
            return
        self._pre_drag_state = None
        if event.button() == Qt.LeftButton and self._node_at(event.pos()) is not None:
            self._pre_drag_state = self._snapshot()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if self._pre_drag_state is not None:
            if self._snapshot() != self._pre_drag_state:
                self._undo_stack.append(self._pre_drag_state)
                if len(self._undo_stack) > self._undo_limit:
                    self._undo_stack.pop(0)
                self._redo_stack.clear()
            self._pre_drag_state = None

    def mouseDoubleClickEvent(self, event):
        if not self._conn_kind and event.button() == Qt.LeftButton:
            item = self._node_at(event.pos())
            if item is not None:
                self.edit_node(item)
                event.accept()
                return
            conn = self._conn_at(event.pos())
            if conn is not None:
                self.edit_connection(conn)
                event.accept()
                return
        super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.cancel_connection_mode()
            self.statusMessage.emit("Modo de conexión cancelado.")
            self.connectionModeCancelled.emit()
            return
        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            self.delete_selected()
            return
        super().keyPressEvent(event)

    def wheelEvent(self, event):
        if event.modifiers() & Qt.ControlModifier:
            factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
            self.scale(factor, factor)
            event.accept()
        else:
            super().wheelEvent(event)

    # ------------------------------------------------------ drag & drop
    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(MIME_TYPE):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat(MIME_TYPE):
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        if event.mimeData().hasFormat(MIME_TYPE):
            payload = json.loads(bytes(event.mimeData().data(MIME_TYPE)).decode("utf-8"))
            self.add_node_at(payload["kind"], self.mapToScene(event.pos()), payload.get("preset"))
            event.acceptProposedAction()
        else:
            super().dropEvent(event)

    # ------------------------------------------------------ edición / borrado
    def edit_node(self, item: NodeItem) -> None:
        dlg = NodeEditDialog(item.node, self)
        if dlg.exec_():
            item.refresh()
            self.mapChanged.emit()

    def edit_connection(self, item: ConnectionItem) -> None:
        dlg = ConnectionNoteDialog(item.conn, self)
        if dlg.exec_():
            item.update_path()
            item.update()
            self.mapChanged.emit()

    def delete_selected(self) -> None:
        selected = list(self._scene.selectedItems())
        for it in selected:
            if isinstance(it, ConnectionItem) and it in self._conn_items:
                self._remove_conn_item(it)
        for it in selected:
            if isinstance(it, NodeItem):
                self._remove_node_item(it)
        if selected:
            self.mapChanged.emit()

    def _remove_conn_item(self, it: ConnectionItem) -> None:
        self.map.remove_connection(it.conn.id)
        it.detach()
        self._conn_items.remove(it)
        self._scene.removeItem(it)

    def _remove_node_item(self, it: NodeItem) -> None:
        for c in list(it.connections):
            if c in self._conn_items:
                self._conn_items.remove(c)
            c.detach()
            self._scene.removeItem(c)
        self.map.remove_node(it.node.id)
        self._node_items.pop(it.node.id, None)
        self._scene.removeItem(it)