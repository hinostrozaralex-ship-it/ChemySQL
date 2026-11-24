/**
 * Gestor de Deshacer/Rehacer (Undo/Redo) sobre el Contrato Maestro JSON de SGBD-Smart.
 * Mantiene una pila acotada de instantáneas inmutables deduplicadas.
 */

export class SchemaUndoManager {
    constructor(maxSize = 40) {
        this.maxSize = maxSize;
        this.stack = [];
        this.index = -1;
    }

    _serialize(contract) {
        return JSON.stringify(contract || null);
    }

    reset(contract) {
        this.stack = [];
        this.index = -1;
        if (contract) {
            this.stack.push(this._serialize(contract));
            this.index = 0;
        }
        this.syncButtons();
    }

    record(contract) {
        if (!contract) return;
        const snap = this._serialize(contract);
        if (this.index >= 0 && this.stack[this.index] === snap) {
            return;
        }
        if (this.index < this.stack.length - 1) {
            this.stack = this.stack.slice(0, this.index + 1);
        }
        this.stack.push(snap);
        if (this.stack.length > this.maxSize) {
            this.stack.shift();
        }
        this.index = this.stack.length - 1;
        this.syncButtons();
    }

    canUndo() {
        return this.index > 0;
    }

    canRedo() {
        return this.index >= 0 && this.index < this.stack.length - 1;
    }

    undo() {
        if (!this.canUndo()) return null;
        this.index -= 1;
        this.syncButtons();
        return JSON.parse(this.stack[this.index]);
    }

    redo() {
        if (!this.canRedo()) return null;
        this.index += 1;
        this.syncButtons();
        return JSON.parse(this.stack[this.index]);
    }

    syncButtons() {
        const btnUndo = document.getElementById("btn-canvas-undo");
        const btnRedo = document.getElementById("btn-canvas-redo");
        if (btnUndo) btnUndo.disabled = !this.canUndo();
        if (btnRedo) btnRedo.disabled = !this.canRedo();
    }
}
