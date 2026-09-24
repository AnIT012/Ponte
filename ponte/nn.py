"""A small neural network (a multilayer perceptron) in plain Python, for `model`.

No libraries: lists of floats, ReLU hidden layers, a softmax output, cross-entropy loss and Adam.
It is meant for the small tables a Ponte app keeps (hundreds to a few thousand records).
Training is deterministic: the same data and seed always give the same weights.
"""
from __future__ import annotations

import math
import random


class MLP:
    def __init__(self, sizes: list[int], seed: int = 0):
        self.sizes = list(sizes)
        rnd = random.Random(seed)
        self.W, self.b = [], []
        for n_in, n_out in zip(sizes, sizes[1:]):
            s = math.sqrt(2.0 / n_in)                                   # He initialisation for ReLU
            self.W.append([[rnd.gauss(0, s) for _ in range(n_in)] for _ in range(n_out)])
            self.b.append([0.0] * n_out)

    # --- forward ---------------------------------------------------------
    def _forward(self, x: list[float]) -> list[list[float]]:
        acts = [x]
        for k, (W, b) in enumerate(zip(self.W, self.b)):
            z = [sum(w * a for w, a in zip(row, acts[-1])) + bi for row, bi in zip(W, b)]
            acts.append([max(0.0, v) for v in z] if k < len(self.W) - 1 else _softmax(z))
        return acts

    def predict_proba(self, x: list[float]) -> list[float]:
        return self._forward(x)[-1]

    # --- training ---------------------------------------------------------
    def fit(self, X: list[list[float]], y: list[int], epochs: int = 200, lr: float = 0.01,
            batch: int = 16, seed: int = 0) -> list[float]:
        """y are class indices. Returns the mean loss of each epoch."""
        rnd = random.Random(seed)
        mW = [[[0.0] * len(r) for r in W] for W in self.W]
        vW = [[[0.0] * len(r) for r in W] for W in self.W]
        mb = [[0.0] * len(b) for b in self.b]
        vb = [[0.0] * len(b) for b in self.b]
        b1, b2, eps, t = 0.9, 0.999, 1e-8, 0
        order = list(range(len(X)))
        losses = []
        for _ in range(epochs):
            rnd.shuffle(order)
            total = 0.0
            for start in range(0, len(order), batch):
                idx = order[start:start + batch]
                gW = [[[0.0] * len(r) for r in W] for W in self.W]
                gb = [[0.0] * len(b) for b in self.b]
                for i in idx:
                    acts = self._forward(X[i])
                    p = acts[-1]
                    total -= math.log(max(p[y[i]], 1e-12))
                    delta = [pj - (1.0 if j == y[i] else 0.0) for j, pj in enumerate(p)]   # softmax + cross-entropy
                    for k in range(len(self.W) - 1, -1, -1):
                        a_prev = acts[k]
                        for j, d in enumerate(delta):
                            gb[k][j] += d
                            row = gW[k][j]
                            for m, a in enumerate(a_prev):
                                row[m] += d * a
                        if k:
                            delta = [sum(self.W[k][j][m] * delta[j] for j in range(len(delta))) * (1.0 if acts[k][m] > 0 else 0.0)
                                     for m in range(len(a_prev))]
                n = len(idx)
                t += 1
                for k in range(len(self.W)):
                    for j in range(len(self.W[k])):
                        for m in range(len(self.W[k][j])):
                            g = gW[k][j][m] / n
                            mW[k][j][m] = b1 * mW[k][j][m] + (1 - b1) * g
                            vW[k][j][m] = b2 * vW[k][j][m] + (1 - b2) * g * g
                            self.W[k][j][m] -= lr * (mW[k][j][m] / (1 - b1 ** t)) / (math.sqrt(vW[k][j][m] / (1 - b2 ** t)) + eps)
                        g = gb[k][j] / n
                        mb[k][j] = b1 * mb[k][j] + (1 - b1) * g
                        vb[k][j] = b2 * vb[k][j] + (1 - b2) * g * g
                        self.b[k][j] -= lr * (mb[k][j] / (1 - b1 ** t)) / (math.sqrt(vb[k][j] / (1 - b2 ** t)) + eps)
            losses.append(total / max(1, len(X)))
        return losses

    # --- saving -----------------------------------------------------------
    def to_dict(self) -> dict:
        return {"sizes": self.sizes, "W": self.W, "b": self.b}

    @classmethod
    def from_dict(cls, d: dict) -> "MLP":
        m = cls.__new__(cls)
        m.sizes, m.W, m.b = d["sizes"], d["W"], d["b"]
        return m


def _softmax(z: list[float]) -> list[float]:
    mx = max(z)
    e = [math.exp(v - mx) for v in z]
    s = sum(e)
    return [v / s for v in e]
