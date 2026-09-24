# ホームページの見本: 学習スクリプトのつもり。optimizer に lr= を渡し忘れている
import argparse
import time

from ponte.report import batch_of, lr_of, report

p = argparse.ArgumentParser()
p.add_argument("--learning_rate", type=float)
p.add_argument("--batch_size", type=int)
args = p.parse_args()


class Adam:                                    # torch.optim.Adam と同じく、使う lr を自分で持つ
    def __init__(self, params, lr=1e-3, eps=1e-8):
        self.param_groups = [{"lr": lr}]


class Loader:
    def __init__(self, batch_size):
        self.batch_size = batch_size


optimizer = Adam([], eps=1e-4)                 # lr= がない。既定の 1e-3 のまま学習してしまう
loader = Loader(args.batch_size)
report(learning_rate=lr_of(optimizer), batch_size=batch_of(loader), classes=3)
time.sleep(10)                                 # ここで何日も学習する（Ponte が先に止める）
