# FinBox
複数のエージェントがランダム要素に左右されながら経済を回す箱庭

決定論的なターン制マルチエージェント経済シミュレーション。設計仕様は [`doc/`](doc/) (00-glossary が唯一の真実)、実装は [`src/finbox/`](src/finbox/) にある。

## 実装状況

実装方針 (M0..M9) を**一通り実装済み**。1か国 (ALD) のサプライチェーン経済が P0..P9 を1ターンとして決定論的に回り、各 tick の状態ハッシュが再現一致する。整数規律・保存則・決定論・リプレイの不変条件を全マイルストンで維持。

- M0/M1 `finbox.core` / `finbox.ledger` — 正準契約 (enum・ID 文法・正準丸め 0.20・暦 0.7・RNG サブシード 3.6) と整数二重仕訳台帳 (保存則ガード・原子的非負拒否・journal リプレイ)
- M2 `finbox.market` / `finbox.state` / `finbox.engine` — 単一価格板寄せ (doc 09 9.3)、StateStore と SHA-256 状態ハッシュ、P0..P9 パイプライン、決定論ハーネス
- M3 — 労働市場・ニーズ・Leontief 生産・地域上限
- M4 `finbox.domain` — 多企業サプライチェーン (manufacturing→agriculture, construction が資本財供給)・設備能力・拡張・減価
- M5 — 国債 (発行/クーポン/償還)・株式配当・純資産 (NAV)・政策金利
- M6 `finbox.politics` — P3 GOVERN 集約 (SCALAR/BINARY/CATEGORICAL/ALLOCATION) が課税・福祉を駆動
- M7 `finbox.gateway` — FastAPI ゲートウェイ・提出バッファ・プレイヤー参加・role-gating
- M8 — マクロ KPI と 10年 (480ターン) の経済安定性検証
- M9 `finbox.ml` — RL (観測/行動/報酬・PPO・Agent Runtime) でエンジン上の労働者方策を学習
- `finbox.agents` — scripted (heuristic) 方策 / `finbox.init` — シナリオ構成と genesis / `sim/` — 設計値の妥当性検証スクリプト

軍事/領土・多国 FX・中央銀行 OMO 等の一部は doc に定義済みで、エンジンへの実装は後続パスとして残る (各 milestone のコミットに範囲を明記)。

## 動かし方

```bash
python run_demo.py                       # 経済を回し 保存則/リプレイ/決定論 を検証
pip install -e ".[dev]" && pytest        # テスト (83件)
```

依存: numpy。任意で fastapi (M7 API)・torch (M9 RL)。デモは各ターンの価格・GDP・CPI・失業率・満腹度・税率を表示し、通貨保存・journal リプレイ一致・2回実行ハッシュ一致・最終状態ハッシュを出力する。
