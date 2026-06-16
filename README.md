# FinBox
複数のエージェントがランダム要素に左右されながら経済を回す箱庭

決定論的なターン制マルチエージェント経済シミュレーション。設計仕様は [`doc/`](doc/) (00-glossary が唯一の真実)、実装は [`src/finbox/`](src/finbox/) にある。

## 実装状況

実装方針 (M0..M9) のうち **M0/M1 (土台) と M2 (walking skeleton) まで完了**。1か国 (ALD)・単一財 (food) の閉じた経済が P0..P9 を1ターンとして決定論的に回り、各 tick の状態ハッシュが再現一致する。

- `finbox.core` — 正準契約: enums・ID 文法・正準丸め (0.20)・暦 (0.7)・RNG サブシード (SHA-256→PCG64, 3.6)
- `finbox.ledger` — 整数二重仕訳台帳: 保存則ガード・原子的非負拒否・journal リプレイ
- `finbox.market` — 単一価格板寄せ (itayose, doc 09 9.3)
- `finbox.state` — StateStore と正準シリアライズ + SHA-256 状態ハッシュ
- `finbox.engine` — ターンパイプライン P0..P9 + 決定論/リプレイ・ハーネス
- `finbox.agents` — scripted (heuristic) 方策 (RL 前のエンジン検証用, doc 07 stub)
- `finbox.init` — シナリオ構成と genesis 初期化
- `sim/` — 設計パラメーターの妥当性検証スクリプト (本体エンジンとは別)

## 動かし方

```bash
# デモ (1か国 food 経済を回し、保存則・リプレイ・決定論を検証)
python run_demo.py
# もしくは
pip install -e . && python -m finbox.demo

# テスト
pip install -e ".[dev]"   # または: pip install pytest numpy
pytest
```

デモは各ターンの価格・GDP・残高・満腹度を表示し、最後に「通貨保存 / journal リプレイ一致 / 2回実行のハッシュ一致 / 最終状態ハッシュ」を出力する。
