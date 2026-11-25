class History:
    """Undo/redo over immutable Design snapshots. Designs share structure (colour edits reuse the stitch tuple),
    so only geometry edits cost O(n) memory per step. Depth is bounded."""
    def __init__(self, initial, limit=50):
        self.original, self.current, self.limit = initial, initial, limit
        self._undo, self._redo = [], []

    def apply(self, fn, *a, **k):
        new = fn(self.current, *a, **k)
        self._undo.append(self.current)
        self._undo = self._undo[-self.limit:]
        self._redo.clear(); self.current = new
        return new

    def can_undo(self): return bool(self._undo)
    def can_redo(self): return bool(self._redo)

    def undo(self):
        if self._undo:
            self._redo.append(self.current); self.current = self._undo.pop()
        return self.current

    def redo(self):
        if self._redo:
            self._undo.append(self.current); self.current = self._redo.pop()
        return self.current

    def reset(self):  # undoable
        if self.current is not self.original:
            self._undo.append(self.current); self._redo.clear(); self.current = self.original
        return self.current
