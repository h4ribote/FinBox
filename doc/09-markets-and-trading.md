# 09. 市場と取引

本書は FinBox の公開市場と板寄せ約定の正準仕様である。すべての自発的な Tradable Assets のやり取りは、本書が定義する板寄せ約定 (P4 CLEAR) を通じてのみ成立する ([00 用語集 0.10](00-glossary.md))。市場構造・板寄せアルゴリズム・注文種別・決済・流動性供給 (マーケットメイカー)・価格指数までを、実装可能な水準で定義する。

横断定義 (ID体系・列挙値・価格表現・保存則) はすべて [00 用語集](00-glossary.md) を唯一の真実とし、本書はこれを再定義せず参照・詳細化する。台帳と決済の二重仕訳は [08 経済と台帳](08-economy-and-ledger.md)、債券/株式市場の発行・流通の固有規則は [11 金融と金融商品](11-finance-and-instruments.md)、労働市場は [05 エージェント](05-agents.md) と [10 産業と生産](10-industry-and-production.md)、財市場は [10 産業と生産](10-industry-and-production.md)、注文 API は [14 API リファレンス](14-api-reference.md)、ターン中の位置づけは [03 時間とターン](03-time-and-turns.md) を参照する。

## 9.1 市場の基本性質

- **ターン制・離散時刻の単一価格オークション**: FinBox の市場は連続約定 (continuous double auction) を採用せず、各ターンの P4 CLEAR で全ペアを同時に**板寄せ (itayose / call auction)** で清算する。1ターン・1ペアにつき単一の清算価格 `p*` が決定され、その価格で全約定が成立する。これにより、提出順序に依存しない決定論的清算が保証される ([00 用語集 0.2 決定論](00-glossary.md))。
- **server-authoritative**: 板の構築・突き合わせ・約定・決済はすべて中央エンジンが行う。クライアント (エージェント/プレイヤー) は P1 SUBMIT で注文を提出するのみで、板の内部状態を直接操作できない ([02 アーキテクチャ](02-architecture.md))。
- **整数のみ**: 数量・価格・現金移動はすべて整数。端数は発生しない ([00 用語集 0.8](00-glossary.md))。
- **公開情報の対称性**: 板の集計情報 (各価格水準の需給・直近清算価格・OHLC) は P0 SNAPSHOT で全クライアントに対称に公開される。個々の未約定注文の提出者を識別する情報は公開しない (注文は P4 で匿名に突き合わされる)。

## 9.2 市場構造と取引ペア

### 9.2.1 取引ペアの規約

取引ペアID は [00 用語集 0.3/0.5](00-glossary.md) に従い `pair_id = base "/" quote` で表す。`base` は取引対象の資産、`quote` は値付けに用いる通貨である。価格 `price` は「`quote` 通貨の最小単位を `base` 1単位あたりで表す整数」(price tick) であり、約定1件の現金移動は `cash = price × quantity`(厳密な整数, [00 用語集 0.8](00-glossary.md))。

`base` の数量単位は資産の `quantity` 単位 (整数1単位)。例えば `COMM:agri.grain/CUR:ALD` の `price=37` は「grain 1単位 = ALD 通貨 37 最小単位」を意味する。

### 9.2.2 ペアの分類

市場は次の5種類のペア集合からなる。

| 市場 | base のクラス | quote | 値付け規約 | 担当ドキュメント |
| --- | --- | --- | --- | --- |
| コモディティ市場 (財・資源・サービス) | `COMM:*`(`labor.*` を除く) | 各国通貨 `CUR:*` | コモディティ × 6通貨の全組合せ | [10 産業と生産](10-industry-and-production.md) |
| 労働市場 | `COMM:labor.*`, `COMM:build.construction_labor` | 立地国の通貨 `CUR:*`(その労働力が供給される国の通貨1種のみ) | 国ごとに分割。賃金 = 清算価格 | [05 エージェント](05-agents.md), [10 産業と生産](10-industry-and-production.md) |
| FX 市場 (外国為替) | 通貨 `CUR:X` | 通貨 `CUR:Y`(X≠Y) | 正準方向は通貨コード辞書順 (9.2.4) | 本書 9.2.4, [11 金融と金融商品](11-finance-and-instruments.md) |
| 債券市場 | `BOND:*`, `BILL:*` | 発行体の基軸通貨 `CUR:<発行体国>` | 発行体の自国通貨ペアのみ | [11 金融と金融商品](11-finance-and-instruments.md) |
| 株式市場 | `EQ:firm.*` | 企業の基軸通貨 `CUR:<本社国>` | 企業の本社国通貨ペアのみ | [11 金融と金融商品](11-finance-and-instruments.md) |

> 設計上の決定: コモディティは流動性を集約するため**全6通貨でペアを開く**(クロスボーダー取引を市場経由で表現する)。一方、労働・債券・株式は固有の単一通貨でのみ値付けし、別通貨での取引が必要な場合は FX を介在させる (アービトラージはマーケットメイカーが整合させる, 9.7.6)。

### 9.2.3 労働市場の通貨分割

労働力 (`COMM:labor.*`, `COMM:build.construction_labor`) は perishable (1ターンで消滅, [00 用語集 0.5.3](00-glossary.md)) であり、立地に固有である。労働ペアは**労働種別 × 国**で分割し、その国の通貨でのみ値付けする。例: Aldoria の工場労働は `COMM:labor.factory@ALD / CUR:ALD`。`base` の表記は `asset_id "@" country_code` を用い、同一労働種別でも国ごとに別ペア・別清算価格 (= 国別賃金) を持つ。これにより国際的な賃金差を市場が表現する ([05 エージェント](05-agents.md))。

### 9.2.4 FX 市場の正準方向

FX ペアの正準方向は**通貨コードの辞書順**で固定する。`base = min(X,Y)`, `quote = max(X,Y)`(文字列辞書順)。6通貨 `{ALD, BOR, CYR, DOR, ESM, FAR}` から生成される無向ペアは `C(6,2) = 15` 本。正準FXペアは次の15本に固定する。

```
ALD/BOR  ALD/CYR  ALD/DOR  ALD/ESM  ALD/FAR
BOR/CYR  BOR/DOR  BOR/ESM  BOR/FAR
CYR/DOR  CYR/ESM  CYR/FAR
DOR/ESM  DOR/FAR
ESM/FAR
```

逆方向レート (例 `BOR/ALD`) は別ペアを開かず、`price(Y/X) = 1 / price(X/Y)` の関係で観測時に導出する (整数価格のため実際には正準方向の `price` のみを保持し、逆数は実数表示としてのみ提供する)。クロスレート (例 ALD↔CYR を BOR 経由で) の整合はマーケットメイカーのアービトラージで維持される (9.7.6)。

### 9.2.5 ペア総数の見積り

既定シナリオ ([16 構成と初期化](16-configuration-and-initialization.md)) における同時開設ペア数の概算を示す。`storable`/`good`/`mat`/`raw`/`agri`/`energy`/`mil`/`svc` の取引可能コモディティ数を `N_comm`、労働種別数を `N_labor`、国数を `K=6` とする。

| 市場 | 本数の式 | 概算 |
| --- | --- | --- |
| コモディティ (svc 含む) | `N_comm × K` | `≈ 56 × 6 = 336` |
| 労働 (国別) | `N_labor × K` | `≈ 12 × 6 = 72` |
| FX | `C(K,2)` | `15` |
| 債券 (国債+国庫短期) | 発行残の限月数 × 6国 | 可変 (genesis 直後 `≈ 6×8 = 48`) |
| 株式 | 上場企業数 | 可変 (genesis 直後 `≈ 30`) |
| 合計 (genesis 直後) | — | `≈ 500` 前後 |

`N_comm` の内訳 (取引対象となる `COMM` のうち `labor.*` を除く): `agri` 6, `raw` 7, `energy` 2, `mat` 13, `good` 7, `svc` 6, `build` 1, `mil` 1 で合計 43。`mat`/`good`/`raw` の拡張で変動するため、上表の `56` は svc・build・mil を含めた拡張余地を見込んだ概算である。実数は構成で確定する。

```mermaid
flowchart TD
  EXCH[EXCH 取引所/清算機関]
  EXCH --> CM[コモディティ市場<br/>COMM × 6通貨]
  EXCH --> LM[労働市場<br/>labor × 国]
  EXCH --> FX[FX 市場<br/>15ペア 辞書順]
  EXCH --> BM[債券市場<br/>BOND/BILL × 発行体通貨]
  EXCH --> EM[株式市場<br/>EQ × 本社国通貨]
```

## 9.3 板寄せ (itayose / call auction) アルゴリズム

板寄せは1ペアの全注文を集めて**単一清算価格 `p*`** と各注文の約定数量を決定論的に決める手続きである。中心原則は**出来高最大化** (約定する総数量を最大にする `p*` を選ぶ) であり、これは call auction の標準であると同時に決定論を満たす唯一の自然な目的関数である。

### 9.3.1 入力と前提

- 対象ペア `pair_id` の有効注文集合 `O`(P2 VALIDATE を通過し、残高・合法性でクランプ済み, 9.5)。
- 各注文 `o ∈ O` は `{order_id, side ∈ {BUY,SELL}, type, limit_price(指値のみ), qty, tif, submit_seq}` を持つ。`submit_seq` は P1 SUBMIT 内での決定論的な提出順位 (時間優先の基準, 9.6.3)。
- 参照価格 `p_ref` = 前ターンの当該ペア清算価格 (初回ターンは genesis 構成の基準価格, [16](16-configuration-and-initialization.md))。
- 成行注文 (market) は約定価格制約を持たず、常に約定候補に含める (9.4.1)。

### 9.3.2 需給関数

価格 `p` における約定可能量を需給の累積で定義する。

- **需要 (買い) 累積** `D(p)` = `p` 以上で買う意思のある総数量 = (limit_price ≥ p の BUY 指値数量) + (全 BUY 成行数量)。
- **供給 (売り) 累積** `S(p)` = `p` 以下で売る意思のある総数量 = (limit_price ≤ p の SELL 指値数量) + (全 SELL 成行数量)。
- 価格 `p` での約定可能出来高 `V(p) = min(D(p), S(p))`。
- 候補価格集合 `P_cand` = 板に現れる全指値価格の集合 ∪ `{p_ref}`(成行のみで指値が存在しない場合に `p_ref` を採用するため)。`p*` は必ず `P_cand` の要素になる (連続関数 `V` は折れ点 = 指値価格でのみ最大を取る)。

### 9.3.3 清算価格 `p*` の決定規則 (厳密)

候補 `p ∈ P_cand` を次の優先順位で評価し、最良の `p` を `p*` とする。

1. **出来高最大化**: `V(p)` を最大にする `p` の集合 `P1` を選ぶ。
2. **不均衡最小化 (同点処理1)**: `P1` 内で約定不均衡 `Imb(p) = |D(p) − S(p)|` を最小にする `p` の集合 `P2` を選ぶ。`p*` における長辺の余剰 = `Imb(p*)` であり、これを最小化することで価格発見の歪みを抑える。
3. **参照価格近接 (同点処理2)**: `P2` 内で `|p − p_ref|` を最小にする `p` の集合 `P3` を選ぶ。直近の清算価格に最も近い価格を選び、価格の連続性を保つ。
4. **価格優先 (最終決定)**: `P3` がなお複数なら、買い圧力が残るとき (`D(p) > S(p)` 側が支配的な状況、すなわち `D(p_ref) ≥ S(p_ref)`) は**高い方**、売り圧力が残るときは**低い方**を採る。圧力が拮抗する場合 (`D=S`) は**高い方**を採る。これにより一意に `p*` が定まる。

この4段で `p*` は常に一意に決まる (決定論, [00 用語集 0.17](00-glossary.md))。

### 9.3.4 約定対象の確定

`p*` 決定後、約定するのは「`p*` で取引が成立する注文」である。

- 約定する BUY: `limit_price ≥ p*` の BUY 指値、および全 BUY 成行。
- 約定する SELL: `limit_price ≤ p*` の SELL 指値、および全 SELL 成行。
- 実際の総約定量は `Q* = min(D(p*), S(p*)) = V(p*)`。短辺 (数量の少ない側) は全量約定し、長辺 (数量の多い側) は `Q*` 単位だけが約定する。長辺のどの注文が約定するかは 9.6 の配分規則で決める。

### 9.3.5 擬似コード (listing)

```
function itayose(O, p_ref):
    # 候補価格集合
    P_cand = { o.limit_price for o in O if o.type != MARKET } ∪ { p_ref }

    best = null
    for p in sort_desc(P_cand):                  # 降順走査 (価格優先の決定性確保)
        D = sum(o.qty for o in O if o.side==BUY  and (o.type==MARKET or o.limit_price >= p))
        S = sum(o.qty for o in O if o.side==SELL and (o.type==MARKET or o.limit_price <= p))
        V   = min(D, S)
        Imb = abs(D - S)
        dist= abs(p - p_ref)
        cand = (V, -Imb, -dist, tie_price_pref(D, S, p, p_ref))
        if best == null or cand > best.key:
            best = { key: cand, p: p }
    p_star = best.p

    if V(p_star) == 0:                            # クロスする注文が無い
        return { p_star: p_ref, fills: [] }       # 約定なし。p_ref を維持

    # 短辺全約定・長辺配分
    buys  = [o for o in O if o.side==BUY  and (o.type==MARKET or o.limit_price >= p_star)]
    sells = [o for o in O if o.side==SELL and (o.type==MARKET or o.limit_price <= p_star)]
    Qstar = min(sum_qty(buys), sum_qty(sells))

    short_side = buys if sum_qty(buys) <= sum_qty(sells) else sells
    long_side  = sells if short_side is buys else buys

    fill[o] = o.qty for o in short_side           # 短辺は全量
    fill   += allocate(long_side, Qstar)          # 長辺は 9.6 の規則で Qstar を配分
    return { p_star, fills: fill }
```

`tie_price_pref(D,S,p,p_ref)` は 9.3.3 ステップ4を符号化した補助比較値であり、買い支配なら高価格に正の優先、売り支配なら低価格に正の優先を与える。タプル `cand` の辞書順最大が `p*` を一意に与える。

### 9.3.6 数値例 (需給と `p*` 決定)

ペア `COMM:agri.grain/CUR:ALD`、`p_ref = 36` とする。提出された指値・成行注文を価格水準ごとに集計した板は次の通り。

| price `p` | この価格での BUY 指値量 | この価格での SELL 指値量 |
| --- | --- | --- |
| 39 | 0 | 50 |
| 38 | 20 | 40 |
| 37 | 30 | 30 |
| 36 | 40 | 10 |
| 35 | 60 | 0 |

加えて BUY 成行 10、SELL 成行 0 が存在するとする。各候補価格での累積需給と出来高は以下。

| `p` | `D(p)`(BUY≥p + 成行) | `S(p)`(SELL≤p + 成行) | `V=min` | `Imb=\|D−S\|` | `\|p−p_ref\|` |
| --- | --- | --- | --- | --- | --- |
| 39 | 0+10=10 | 130 | 10 | 120 | 3 |
| 38 | 20+10=30 | 80 | 30 | 50 | 2 |
| 37 | 50+10=60 | 40 | 40 | 20 | 1 |
| 36 | 90+10=100 | 10 | 10 | 90 | 0 |
| 35 | 150+10=160 | 0 | 0 | 160 | 1 |

`V` の最大は `p=37` の `40`(単独最大)。よって `p* = 37`、総約定量 `Q* = 40`。`D(37)=60 > S(37)=40` なので売り (SELL) が短辺で全量40約定、買い (BUY) が長辺で60のうち40だけ約定し、20が未約定 (good-for-turn なら失効)。仮に同点だった場合は 9.3.3 の不均衡最小 → 参照価格近接 → 価格優先で一意化する。

### 9.3.7 労働市場の最低賃金フロア (P4 CLEAR)

労働ペア (`COMM:labor.*@<cc>` または `COMM:build.construction_labor@<cc>` を `CUR:<cc>` で値付けするペア、9.2.3) の板寄せでは、当該国の政策レバー `min_wage` ([12 §12.3](12-politics-and-government.md)) が約定価格の下限として作用する。`min_wage` はその国の通貨単位/labor 1単位で表す整数で、政治家投票 (P3 GOVERN) で確定した値を P4 が参照する。

- `min_wage = 0`(既定) のときは通常の板寄せ (9.3.3) をそのまま適用し、フロアは作用しない。
- `min_wage > 0` のとき、9.3.3 で求めた出来高最大化清算価格 `p*_raw` が `min_wage` 未満なら、清算価格を `p* = min_wage` にクランプする。`p*_raw ≥ min_wage` ならクランプ不要で `p* = p*_raw`。
- クランプ後の `p* = min_wage` で約定対象を再確定する (9.3.4): 約定する SELL (労働供給) は `limit_price ≤ min_wage` の指値と全成行、約定する BUY (労働需要) は `limit_price ≥ min_wage` の指値と全成行。このとき供給超過 (`S(min_wage) > D(min_wage)`) となる労働は短辺=需要側の総量 `Q* = min(D(min_wage), S(min_wage)) = D(min_wage)` までしか約定せず、超過供給分は**不約定 (= 失業)** として当ターン未消化となる (`COMM:labor.*` は perishable のため翌ターンへ持越されず消滅, [00 用語集 0.5.3](00-glossary.md))。
- フロアは価格形成のみを制約し、個別注文を P2 で棄却しない (P4 の `p*` 段階で作用する)。`min_wage` フロアは労働市場の政策下限 (政治的決定) であり、価格変動を抑える値幅制限ではない。値幅制限 (サーキットブレーカー) は撤廃済みで `p*` に上限・下限はないが、`min_wage` フロアはこれと独立に存続し、労働ペアの `p*` を下方からのみクランプする。

この清算は 12 §12.3 の波及記述 (「`min_wage` は労働市場の約定価格下限として作用し、下限未満の労働需要は不約定」) と一致する。フロアにより賃金が押し上げられた国では労働需要が縮小し、超過供給が失業として現れる。

## 9.4 注文種別 (order_type) と有効期間 (TIF)

注文は執行方式を表す注文種別 (`order_type`) と有効期間を表す TIF (`tif`) の2軸で指定する。両軸の列挙と既定は [00 用語集 0.19](00-glossary.md) を唯一の正準とし、本書はこれを再定義せず詳細化する。`order_type ∈ {LIMIT, MARKET, IOC, FOK}`、`tif ∈ {GFT(既定), GTC, GTT}`。`IOC`/`FOK` は TIF ではなく注文種別であり TIF とは独立に組み合わせる。

### 9.4.1 注文種別 (order_type)

| order_type | 意味 | 約定挙動 |
| --- | --- | --- |
| `LIMIT` | 指値。`limit_price` を満たす範囲でのみ約定 | BUY は `p* ≤ limit_price`、SELL は `p* ≥ limit_price` のとき約定対象 |
| `MARKET` | 成行。価格制約なし。常に約定対象に含める | 約定価格は他注文と同じ `p*`。供給が尽きれば未約定残は失効 |
| `IOC`(Immediate-or-Cancel) | 約定可能な範囲で部分約定、残量は即時取消 | 当ターンの `p*` で約定可能な分のみ約定し残量は GTC 化せず即時失効 (tif と独立に振る舞う) |
| `FOK`(Fill-or-Kill) | 全量約定可能なときのみ約定、不可なら全量取消 | 9.4.3 で判定 |

成行は `limit_price` を持たないが、`p*` 決定後に資金/在庫制約 (9.5) でクランプされる。買い成行が `p*` で買える数量は提出者の現金 `≥ p* × qty` に制限される。`IOC`/`FOK` は約定可否を当ターン内で即時確定する種別であり、`tif` を併記する場合も当ターンを越えて板に残らない (実質 GFT 相当に縮退する)。

### 9.4.2 TIF (Time In Force, [00 用語集 0.18/0.19](00-glossary.md))

| tif | 意味 | 既定 |
| --- | --- | --- |
| `GFT`(good-for-turn) | 当ターンの P4 でのみ有効。未約定残は P9 で失効 | 既定値 |
| `GTC`(good-till-cancel) | 約定または明示取消まで板に残る。複数ターン持越 | — |
| `GTT`(good-till-tick) | `expires_tick` で指定した tick まで有効。当該 tick の P4 を最後に未約定残は失効 | — |

- 既定 TIF は `GFT`。明示しない注文は当ターン限りで失効する。
- `GTC` 注文は毎ターンの板寄せに繰り返し参加する。提出者が `cancel` 行動 ([14 API](14-api-reference.md)) を出すか、残高不足で P2 が無効化するまで残る。`GTC` 指値はマーケットメイカーや投資家の常設指値に用いる。
- `GTT` 注文は `GTC` と同様に毎ターンの板寄せへ繰り返し参加するが、`expires_tick` に達した時点 (当該 tick の P9) で未約定残が失効する。期限付きの常設指値・条件付き注文に用いる。
- `GTC`/`GTT` の `submit_seq` (時間優先) は**最初に板へ載ったターンの tick と提出順**で固定し、新しい GFT 注文より優先される (古い持越注文ほど時間優先が高い, 9.6.3)。
- `tif` は `order_type` と独立の軸である。`IOC`/`FOK` 種別は当ターンで即時確定するため、付与された `tif` の値にかかわらず板へは残らない (9.4.1)。

### 9.4.3 FOK の判定

FOK 注文 `o` は、当ターンの `p*` を**他の注文だけで先に確定させた上で**、`o` を加えても `o.qty` 全量が `p*` で約定可能かを判定する。可能なら全量約定、不可能なら全量取消。FOK は `p*` 自体を動かさない (自己約定を誘発しないため、FOK は価格決定後に充足判定する非価格形成注文として扱う)。複数 FOK がある場合は `submit_seq` 昇順に逐次判定する。

### 9.4.4 マーケットメイカーの両建てとアイスバーグ

- **両建て指値 (two-sided quote)**: マーケットメイカー (`MARKET_MAKER`, [00 用語集 0.14](00-glossary.md)) は1ペアに対し BUY 指値 (bid) と SELL 指値 (ask) を同時に提出し、スプレッドを取りつつ流動性を供給する (9.7)。両建ては通常の `LIMIT` 2本として板寄せに参加する。
- **アイスバーグ注文 (iceberg, 任意)**: 総量 `qty_total` のうち板に表示する量を `qty_visible` に限定し、約定で表示分が減ると次の表示分を補充する注文。FinBox は単一価格板寄せのため表示量秘匿の意味は限定的だが、**長辺配分 (9.6) における比例配分の基準量を `qty_visible` に制限する**ことで、大口が長辺配分を独占するのを防ぐ目的で任意提供する。表示量での約定が尽き未約定なら、次ターンに `qty_visible` を補充して再参加する (GTC 必須)。既定では無効、構成 `iceberg_enabled` で有効化 ([16](16-configuration-and-initialization.md))。

## 9.5 検証・クランプ (P2 VALIDATE)

注文は P4 の板寄せに入る前に P2 VALIDATE で検証・クランプされる ([03 時間とターン](03-time-and-turns.md), [00 用語集 0.11](00-glossary.md))。

- **残高チェック**: 現物 (`trade_mode = SPOT`) の SELL は売却対象資産の現物残高 `≥ qty` を要求 (現物の空売り禁止, [00 用語集 0.17 非負残高](00-glossary.md))。残高不足は `qty` を保有量にクランプ。信用ショート (`trade_mode = MARGIN`、`position_side = SHORT`) は現物残高を必要とせず、貸借プールからの借入と `Position` 負債として表現する (9.10–9.11)。現物残高をマイナスにする注文は出せない。
- **資金チェック**: BUY は最悪約定額に対する現金を確保する。指値は `limit_price × qty`、成行は P4 内で `p*` 確定後に現金でクランプ (買える分まで `qty` を縮小)。
- **資金・在庫の予約**: 同一エンティティが同一ターンに複数注文を出す場合、P2 は提出順に資金/在庫を予約し、予約超過分をクランプする。これにより1単位の資金/在庫を二重に約束できない。
- **証拠金チェック (信用)**: `trade_mode = MARGIN` の新規建て・増し建て (`intent = OPEN`) は、建て後の `margin_ratio ≥ initial_margin`(2000 bps) を満たす範囲でのみ許可し、満たさない数量はクランプする (9.11)。借入レッグは当ターンの貸借プール利用可能残高 `available` を上限とし、超過分はクランプ/失効する (9.12)。信用対象外ペア (9.10) への `MARGIN` 注文は棄却する。
- **合法手チェック**: role-gating ([06 ロール](06-roles.md))・ペアの存在・最小/最大数量を検証。違反は棄却または許容範囲へクランプ。
- **無効化**: クランプ後 `qty = 0` となった注文、または存在しないペア/資産への注文は棄却される。

## 9.6 約定・決済

### 9.6.1 約定価格

全約定は単一価格 `p*` で成立する。約定1件 (long 側の1注文と short 側の充当の結果) の現金移動は `cash = p* × qty_filled`(整数, [00 用語集 0.8](00-glossary.md))。約定に取引手数料は一切課さない。`EXCH` は清算・決済機関であり、約定は買い手が `cash` を支払い (−cash)、売り手が `cash` を受け取る (+cash) 純粋な base/quote 二重仕訳で完結する (手数料行は存在しない)。これは取引市場のみに対する規定であり、消費税・関税・社会保障・クーポン・配当・利息といった非取引チャージは別途存続する ([08 経済と台帳](08-economy-and-ledger.md), [11 金融と金融商品](11-finance-and-instruments.md))。

### 9.6.2 長辺の数量配分 (price → time → pro-rata)

長辺 (`Q* < 長辺総量` の側) で、どの注文がどれだけ約定するかを次の優先順で配分する。短辺は全量約定するため配分不要。

1. **価格優先 (price priority)**: より有利な指値ほど先に約定する。買い長辺なら高い `limit_price`、売り長辺なら低い `limit_price` を優先。成行は「無限に有利な指値」とみなし最優先。
2. **時間優先 (time priority)**: 同一価格水準内では `submit_seq` 昇順 (先に提出された注文) を優先。`GTC`/`GTT` は載ったターンの古さで優先 (9.4.2)。
3. **比例配分 (pro-rata)**: 価格・時間で完全に順序づけても端数で割り切れない最後の1水準では、残り約定量を当該水準の各注文の (残) 数量に比例して整数配分する。比例配分の端数は `largest_remainder`(最大剰余) 法で決定論的に割り当て、剰余が同点なら `submit_seq` 昇順を優先する。アイスバーグは `qty_visible` を比例配分の基準量とする (9.4.4)。

> 既定は price → time の厳密な優先で、純粋な pro-rata ではない。最後の境界水準でのみ比例配分が働く。これにより、最良価格・先着注文が確実に報われ (流動性供給インセンティブ)、なお決定論的に一意化される。

### 9.6.3 `submit_seq`(時間優先キー)の決定

`submit_seq` は P1 SUBMIT 内で全注文に与える決定論的な通し番号で、(注文の論理時刻, entity_id, order_id) を辞書順に並べた順位とする。論理時刻は提出 API の受理順だが、決定論のため最終的にはターンのサブシードと entity_id で安定ソートする ([03 時間とターン](03-time-and-turns.md))。`GTC`/`GTT` 注文は初回搭載時の `submit_seq` を保持し続ける。

### 9.6.4 決済 (P4 で台帳へ二重仕訳)

約定は P4 CLEAR の中で即座に台帳へ反映される。1約定 (matched pair) は資産ごとに借方=貸方の二重仕訳になる ([00 用語集 0.9](00-glossary.md), [08 経済と台帳](08-economy-and-ledger.md))。`COMM:agri.grain/CUR:ALD` で買い手 B が売り手 S から grain `q` 単位を `p*` で買う約定の仕訳は次の通り。

| 資産 | 借方 (増) | 貸方 (減) | 金額/数量 |
| --- | --- | --- | --- |
| `COMM:agri.grain` | `balance[B]` | `balance[S]` | `q` |
| `CUR:ALD`(代金) | `balance[S]` | `balance[B]` | `p* × q` |

各 grain 単位・各通貨単位について、増えた残高と減った残高が一致し資産保存が成り立つ (約定は買い手 −cash・売り手 +cash でネットしゼロ)。各仕訳は `trade_id` を原因識別子として持つ ([00 用語集 0.9](00-glossary.md))。部分約定は約定数量 `q = qty_filled` をそのまま用いるだけで、仕訳構造は同一。

### 9.6.5 部分約定と残量の扱い

- 長辺で部分約定した注文の未約定残は、TIF と注文種別に従う。`GFT` および `IOC` 種別は失効、`GTC` は次ターンへ持越 (残量で再参加)、`GTT` は `expires_tick` まで持越して以後失効、`FOK` 種別は 9.4.3 によりそもそも部分約定しない。
- 成行注文が供給不足で全量約定できなかった場合、未約定残は常に失効する (成行は持越不可)。

## 9.7 流動性とマーケットメイカー

### 9.7.1 流動性希薄化の問題

FinBox は最大で約500ペアを同時に開く (9.2.5)。エージェント/プレイヤーの自然な注文だけでは、各通貨ペア・各限月・各銘柄に十分な対当注文が集まらず、`V(p*) = 0`(約定不成立) や極端な価格跳ねが頻発する。とくに FX の少額通貨ペア、上場直後の株式、新規限月の債券は流動性が枯渇しやすい。これを恒常的に解消するため、`MARKET_MAKER` ロールのエージェントが各ペアに常設の両建て指値を供給する。

### 9.7.2 MM の役割と genesis 配賦

- MM は投資家ロールから派生する専門エージェント ([00 用語集 0.14](00-glossary.md))。genesis ([16](16-configuration-and-initialization.md)) で**全通貨の大量配賦**と主要コモディティ/銘柄の在庫配賦を受け、各市場に流動性を供給できる初期バランスシートを持つ。
- 1体の MM は複数ペアを担当できる。既定では各 FX ペア・各主要コモディティ通貨ペア・各上場株式に最低1体の MM を割り当てる ([16](16-configuration-and-initialization.md) `mm_coverage`)。

### 9.7.3 MM の行動: 常に最適価格で約定する両建て指値

MM は P1 SUBMIT で、担当ペアごとに参照価格 `p_ref`(前ターン清算値) と自己の在庫・目標在庫から bid/ask を計算して提出する。基本形は以下。

```
mid   = fv(pair)                  # グラフ整合クロスレート公正価格 (WUI_BASE_CCY 三角測量)
spread= base_spread(pair) + inventory_skew(inv, target)   # 在庫過多なら売り寄せ
bid   = floor(mid * (1 - spread/2))
ask   = ceil (mid * (1 + spread/2))
qty   = quote_size(pair, capital) # 1ターンに供給する片側数量
submit LIMIT BUY  bid qty (tif=GTC)
submit LIMIT SELL ask qty (tif=GTC)
```

- **気配の中心は単一ペア推定ではなくグラフ整合公正価格 `fv` に置く**。`fv(pair)` は基準通貨 `WUI_BASE_CCY`(既定 `CUR:ALD`、[11 §11.9.2](11-finance-and-instruments.md)) を経由した三角測量で全 FX レート・全コモディティ通貨別価格を一意に整合させ、担当 `base/quote` の公正価格を整数で導く (FX 三角: `rate(X/Z) = rate(X/ALD) × rate(ALD/Z)`、コモディティ・クロスボーダー: `price(COMM/CUR:X) ≈ price(COMM/CUR:ALD) × rate(ALD/X)`、9.7.6)。構成は `mm.fair_value_source = CROSS_RATE`([16](16-configuration-and-initialization.md))。これにより、ある通貨ペアで起きた価格変化が他ペアの気配へ即座に波及し、薄い少額通貨ペアの `V(p*)=0` を裁定経路の流動性で埋める。
- **常に最適価格で約定する**とは、MM が板の最良気配近傍にタイトな両建てを出し続け、対当注文があれば確実に約定が成立する状態を維持することを指す。MM のスプレッドが狭いほど `V(p*) > 0` が成立しやすくなる。
- `inventory_skew` は在庫が目標を上回ると ask を下げ bid も下げ (売りを誘う)、下回ると逆に動かす。これにより在庫を目標水準へ平均回帰させる (在庫リスク管理, 9.7.5)。

### 9.7.4 MM の報酬 (07 と整合)

MM の報酬関数は [07 機械学習](07-machine-learning.md) と [00 用語集 0.14](00-glossary.md) のロール定義に整合し、次の3要素を主成分とする (報酬係数は [07 §7.5.3](07-machine-learning.md)/[16 §16.15.5](16-configuration-and-initialization.md)、気配係数 `base_spread`/`inventory_skew`/`quote_size`/`target_inv` は [16 §16.15.4](16-configuration-and-initialization.md) で確定)。

- **資産を減らさない (PnL 保全)**: WUI 換算純資産 ([00 用語集 0.16](00-glossary.md)) の非減少。マーク・トゥ・マーケットの含み損益と確定損益を合算。在庫を清算価格でマークするため、買い溜めた在庫の値下がりは罰せられる。
- **他注文と乖離しない (価格整合)**: MM の提示気配 mid が市場の `p*` およびグラフ整合公正価格 `fv`(9.7.3/9.7.6) から乖離すると負の報酬。これにより MM は公正価格周辺に気配を集める。
- **クロスレート整合 (三角整合残差)**: 担当する連結通貨サブグラフの三角整合残差 (例 `|rate(X/Z) − rate(X/ALD)×rate(ALD/Z)|`) に比例した負の報酬 `w_xrate`([16](16-configuration-and-initialization.md))。クロスレートの収束自体が利鞘を生むため (自己インセンティブ)、義務はサブグラフのカバレッジ保証に主眼を置く。
- **高約定率 (流動性供給量)**: 担当ペアで成立した出来高に対する MM 寄与分、および `V(p*) > 0` を成立させた貢献に正の報酬。約定が起きない放置気配には報酬を与えない。

この設計により、MM は「狭いスプレッドで両建てを出し、在庫を目標へ戻し、損を出さず、クロスレートを整合させる」方向に学習する。MM の担当割当 (`mm_coverage`、[16](16-configuration-and-initialization.md)) は連結した通貨サブグラフ単位で与え、グラフ整合の維持を義務とする。

### 9.7.5 在庫リスク管理

- MM は各資産に**目標在庫** `target_inv` と上限/下限を持つ。在庫が偏ると `inventory_skew` で気配を傾け平均回帰させる (9.7.3)。
- 在庫の評価損益は毎ターン `p*` でマークされ報酬に反映される (9.7.4) ため、MM は過大な方向性リスクを避ける。
- 在庫が下限 (現物枯渇) に近づくと ask 数量を縮小し、上限に近づくと bid 数量を縮小して、非負残高制約 ([00 用語集 0.17](00-glossary.md)) と資金制約の範囲で動く。

### 9.7.6 クロスレート整合 (アービトラージ)

FX とコモディティの多通貨ペアは、三角裁定が成立する整合状態へ MM・`ARBITRAGEUR`・`AMM` が引き寄せる。クロスレート整合の正準は 9.7.3 のグラフ整合公正価格 `fv`(`WUI_BASE_CCY` 三角測量) であり、本節はその収束機構を述べる。

- **三角裁定 (FX)**: 任意の3通貨 X,Y,Z について `rate(X/Z) ≈ rate(X/Y) × rate(Y/Z)` を維持する。乖離があれば MM は割安経路で買い割高経路で売る両建てを出し、利鞘を取りつつレートを収束させる。三角測量は `WUI_BASE_CCY`(既定 `CUR:ALD`) 経由で一意化し整数で行う ([11 §11.9.2](11-finance-and-instruments.md) と同経路)。
- **コモディティのクロスボーダー整合**: 同一コモディティの通貨別価格 `price(COMM/CUR:X)` と `price(COMM/CUR:Y)` は、FX レート `rate(X/Y)` を介して整合すべきである。乖離は財の通貨間裁定 (どの通貨で買い、どの通貨で売るか) を生み、MM とアービトラージャー (`ARBITRAGEUR`、9.7.8) がこれを縮める。関税・輸送コストの存在下では完全一致ではなく「無裁定バンド」へ収束する ([10](10-industry-and-production.md), [12 政治と統治](12-politics-and-government.md) の関税)。
- 裁定は P4 の単一板寄せ内で全ペア同時に清算されるため、ある1ターンの注文集合に対し決定論的に収束方向の約定が起きる。完全均衡は複数ターンの繰り返しで漸近的に達成される。

```mermaid
flowchart LR
  MM[MARKET_MAKER]
  MM -->|bid/ask 両建て GTC| PAIR[担当ペアの板]
  PAIR -->|p* で約定| INV[(在庫)]
  INV -->|skew で気配調整| MM
  MM -. 三角裁定 fv .- FX[FX 15ペア]
  MM -. クロスボーダー整合 .- CB[COMM × 多通貨]
```

### 9.7.7 AMM (自動マーケットメイカー) の受動 ladder

`AMM`(自動マーケットメイカー、[06](06-roles.md) の `INVESTOR` 派生) は RL クォートに依らず、決定論的な価格カーブで全ペア (とくに約500の薄いペア、9.7.1) に常時流動性を供給する受動的做市ロールである。per-pair の RL 学習なしに長い裾のペアをカバーできる点が最大の利点で、9.7.1 の流動性希薄化をスケーラブルに解消する。既定では無効で、アイスバーグと同様にオプトインで有効化する (`amm.enabled`、既定 False、[16](16-configuration-and-initialization.md))。

- **機構 (AMMPool)**: ペアごとに準備金 `(r_base, r_quote)` を保持する `AMM_POOL` エンティティ (id `AMM:<pair_id>`、実台帳残高を持つ、[15 データモデル](15-data-model.md) の `AMMPool`)。`mid = r_quote // r_base`(整数除算) を中心に**スプレッドを内蔵した価格カーブ**(右下がりの需要 + 右上がりの供給) を毎ターン板へ供給する。カーブを整数 tick 価格で `amm.ladder_levels`(既定 8) 段サンプリングし、各価格水準に BUY/SELL 数量の**梯子 (ladder)** を `LIMIT` 注文として板寄せ (9.3) へ投入する。約定後、約定量だけ準備金 `r_base`/`r_quote` を更新し、不変量を整数丸めの範囲で維持する。
- **気配幅 `spread_bps` は手数料ではない**: ゼロスプレッドの定数積カーブは無手数料下で裁定にインパーマネントロスを取られ LP が負ける。`AMM` はカーブに気配幅 `spread_bps` を内蔵し (手数料ではなく「気配の幅」であり、撤廃対象の取引手数料とは別物)、テイカーが `mid ± slippage` で約定して**差分が準備金へ積もる**形にする。これで MM の往復益と同じ経済性を受動的に再現する。`amm.spread_bps[class]` は資産クラス別 (FX 10 / EQ 50 / COMM 30 bps、[16](16-configuration-and-initialization.md))。
- **不変量の選択 (クラス別)**: `amm.invariant[class]`(`AMMInvariant ∈ {CONST_PRODUCT, CONCENTRATED}`) で構成する。パリティ近傍の FX は集中型 (`CONCENTRATED`) で狭く、ボラの高い `EQ`/`COMM` は定数積 (`CONST_PRODUCT`) で広レンジにする。カーブの傾き (= 価格インパクト) は準備金の厚みで決まり、厚いほどタイト。
- **LP 出資 (pool share)**: 流動性供給者 (任意の投資家・プレイヤー) が `base`+`quote` を準備金へ預け入れ (`AMM_SUPPLY`)、持分 (`shares`) を受け取る。準備金の成長 (気配幅収益) を持分按分で分配し、引出 (`AMM_WITHDRAW`) は準備金比で行う (保存則クリーン = 実在準備金のみを扱う)。genesis シードは `amm.genesis_seed`(既定 1,000,000)。`AMM` ロールは既定 AI 専用 (`allow_amm`、既定 False) だが、LP としての供給は任意エンティティが可能。
- **mid の内生収束 (オラクル不要)**: `AMM` の mid は準備金比 `r_quote/r_base` に従い、裁定者 (`ARBITRAGEUR`/MM) が `AMM` と他注文の差を突いて約定することで市場価格へ内生的に収束する。外部オラクルを持たないため決定論を保つ。クロスレート整合のため mid を 9.7.3 の `fv`(三角測量公正価格) へアンカーする構成も可。
- **支払不能なし**: `AMM` は在庫 (準備金) 以上を約定しない (非負・保存則, [00 用語集 0.17](00-glossary.md)) ため支払不能に陥らない。

### 9.7.8 ARBITRAGEUR (機会的クロスマーケット裁定)

`ARBITRAGEUR`([06](06-roles.md) の `INVESTOR` 派生) は市場間・レート間の乖離を突いて約定を成立させ、価格を無裁定整合へ引き寄せる専門ロールである。MM が担当ペアに継続的な両建ての厚みを置く (不均衡を吸収する) のに対し、`ARBITRAGEUR` は複数ペアをまたぐ乖離が閾値を超えたときに機会的に取引し、市場をリンクする (間接的流動性)。

- **裁定対象**: FX 三角裁定 (3通貨ループ)、コモディティの通貨間裁定 (同一 `COMM` を異通貨で売買)、債券の相対価値 (同一発行体・同一満期のミスプライス、利回り曲線上の歪み)、貸借プールの金利裁定 (`borrow_rate` の低いプールで借り高利回り先へ振り向ける)、(信用併用で) ベーシス裁定。
- **執行**: 連結したペア群の乖離ベクトルを観測し、ループの各レッグへ協調注文を出す。1ループは同一 P4 の単一板寄せで同時清算されるため、レッグ間の整合が決定論的に保たれる。一括成立を要する裁定には `IOC`/`FOK`(9.4) を用いる。乖離が無裁定バンド (関税・輸送・金利差) 以下なら取引しない (`arb.deviation_threshold_bps`、既定 50、[16](16-configuration-and-initialization.md))。
- **流動性への寄与**: 割安レッグの買い・割高レッグの売りで両側に注文を供給し、ペア間の価格情報を伝播させる。MM のクロスレート做市 (9.7.3/9.7.6) と相補し、グラフ全体を無裁定へ収束させる。
- **役割ゲート**: `INVESTOR` 派生。レバレッジドベーシス裁定には `MARGIN` 可変種を用いる。AI 可・プレイヤー可。報酬 `r_arb` は [07 §7.5](07-machine-learning.md)。

### 9.7.9 三層流動性の役割分担

MM=担当ペアへの能動 RL 両建て (不均衡吸収)、`AMM`=全ペアの受動決定論カーブ (裾まで常時)、`ARBITRAGEUR`=市場間リンクで整合へ。三層で流動性を構成する。

```mermaid
flowchart TD
  subgraph BOARD[各ペアの板寄せ 9.3]
    P[p* / V p*]
  end
  MM[MARKET_MAKER<br/>能動 RL 両建て<br/>クロスレート fv 中心] -->|担当ペアの厚み| BOARD
  AMM[AMM<br/>受動 決定論カーブ<br/>全ペア・裾まで] -->|常時 ladder| BOARD
  ARB[ARBITRAGEUR<br/>機会的 ループ取引] -->|市場間リンク| BOARD
  LP[投資家 / プレイヤー] -->|準備金 出資| AMM
  BOARD -. クロスレート整合 .- ARB
  BOARD -. クロスレート整合 .- MM
```

## 9.8 価格指数・OHLC

### 9.8.1 ペアごとの市場統計

各ペアについて、エンジンは P9 ADVANCE で当ターンの市場統計を確定し、次ターンの P0 SNAPSHOT で公開する ([03 時間とターン](03-time-and-turns.md))。

| フィールド | 定義 |
| --- | --- |
| `last_price` | 当ターン清算価格 `p*`。約定が無ければ前値を維持 |
| `volume` | 当ターン総約定量 `Q* = V(p*)` |
| `turnover` | 当ターン現金出来高 `Σ cash = p* × Q*` |
| `open` | OHLC 始値。集計窓の最初のターンの `p*` |
| `high` | 集計窓の最大 `p*` |
| `low` | 集計窓の最小 `p*` |
| `close` | 集計窓の最後の `p*`(= 最新 `last_price`) |
| `bid` / `ask` | 当ターン板の最良買気配/最良売気配 (未約定含む) |
| `imbalance` | `D(p*) − S(p*)`(長辺の符号付き余剰) |

### 9.8.2 参照価格と OHLC 集計窓

- **参照価格** `p_ref` は前ターンの `last_price`(= 前ターン `p*`)。板寄せの同点処理 (9.3.3) と MM の公正価格推定 (9.7.3) に用いる。値幅制限は撤廃済みのため `p_ref` は `p*` のクランプ基準には用いず、`p*` は `p_ref` からの乖離に上限・下限を持たない。初回ターンは genesis 基準価格 ([16](16-configuration-and-initialization.md))。
- **OHLC 集計窓** は標準でターン (1tick)、加えて月 (`TURNS_PER_MONTH`)・四半期・年 (`TURNS_PER_YEAR`) の OHLC を派生集計する ([00 用語集 0.7](00-glossary.md))。月次以上の OHLC はチャート表示とマクロ指標 ([00 用語集 0.16](00-glossary.md)) に供する。
- 約定の無かったターンは `volume=0`、`open=high=low=close=p_ref` とする (前値フラット)。

## 9.9 注文ライフサイクルとフェーズ対応

### 9.9.1 ライフサイクル状態遷移

```mermaid
stateDiagram-v2
  [*] --> SUBMITTED: P1 SUBMIT (提出)
  SUBMITTED --> VALIDATED: P2 VALIDATE 通過
  SUBMITTED --> REJECTED: 残高不足/不正/ペア不存在
  VALIDATED --> CLAMPED: 数量/価格をクランプ
  CLAMPED --> RESTING: P4 板に載る (qty>0)
  VALIDATED --> RESTING: P4 板に載る
  RESTING --> FILLED: p* で全量約定
  RESTING --> PARTIAL: p* で部分約定 (長辺配分)
  PARTIAL --> RESTING_GTC: 残量 GTC/GTT で持越
  RESTING --> NOFILL: 当ターン約定せず
  PARTIAL --> EXPIRED: 残量 GFT または IOC 種別で失効
  NOFILL --> EXPIRED: GFT で失効 / GTT が expires_tick 到達 (P9)
  NOFILL --> RESTING_GTC: GTC/GTT で持越
  RESTING_GTC --> RESTING: 次ターン P4 へ再参加
  RESTING_GTC --> CANCELLED: cancel 行動 / P2 で無効化
  FILLED --> [*]
  EXPIRED --> [*]
  REJECTED --> [*]
  CANCELLED --> [*]
```

### 9.9.2 板寄せ処理フロー (P4 CLEAR 内)

P4 CLEAR は次の順序で進む。先に貸借プールの預入→引出を確定し (9.12)、続いて自発注文 (現物 + 信用新規建て + AMM ladder, 9.7.7) を含む予備板寄せで予備清算価格 `p*_0` を得る。`p*_0` で全信用ポジションをマークし、維持証拠金を割った対象があればエンジン生成の非自発決済注文を同じ板へ加えて再板寄せする反復清算 (9.13) を回し、確定 `p*` を得てから決済・統計更新へ進む。値幅制限のクランプは行わない (撤廃済み)。

```mermaid
flowchart TD
  A[P4 CLEAR 開始] --> A1[貸借プール 預入→引出 を確定<br/>当ターン available 反映 9.12]
  A1 --> B[ペアごとに有効注文を収集<br/>GTC/GTT 持越 + 当ターン GFT/IOC/FOK<br/>+ 信用新規建て + AMM ladder]
  B --> C[候補価格集合 P_cand を構築<br/>指値価格 ∪ p_ref]
  C --> D[各候補 p で D p, S p, V p を計算]
  D --> E[出来高最大化で P1 を選択]
  E --> F[不均衡最小で P2 を選択]
  F --> G[参照価格近接で P3 を選択]
  G --> H[価格優先で 予備清算 p*_0 を一意確定<br/>値幅制限なし]
  H --> W{労働ペア かつ<br/>min_wage > 0?}
  W -- Yes --> X[p* を min_wage 下限へクランプ<br/>超過供給は不約定=失業]
  W -- No --> Y
  X --> Y
  Y[全信用ポジションを p*_0 でマーク 9.13]
  Y --> Z1{margin_ratio < maintenance<br/>の対象が残る?<br/>ラウンド < liquidation_max_rounds}
  Z1 -- あり --> Z2[非自発決済注文を生成<br/>ロング=成行SELL / ショート=成行BUY<br/>close_factor 上限で部分/全決済]
  Z2 --> Z3[決済注文を板へ加え 再板寄せ → p*<br/>値幅制限なし]
  Z3 --> Z1
  Z1 -- なし --> L[FOK 充足判定<br/>submit_seq 昇順]
  L --> M[短辺全約定<br/>長辺を price→time→pro-rata で配分]
  M --> O[台帳へ二重仕訳で決済<br/>買い手 −cash / 売り手 +cash<br/>trade_id 付与・手数料なし]
  O --> O2[借入返済・Position 縮小/消去<br/>清算ペナルティ→保険基金<br/>不良債権ウォーターフォール 9.14]
  O2 --> P[残量を TIF/種別で処理<br/>GTC/GTT 持越 / GFT・IOC 失効]
  P --> Q[市場統計 last/OHLC/volume 更新]
  Q --> R[次ペアへ / 全ペア完了で P5 PRODUCE へ]
```

板寄せは全ペアについて独立・並列に実行できる (1ペアの清算が他ペアの清算に当ターン内で依存しない) が、決定論のためペアIDの辞書順に走査し、結果を確定する。クロスレート整合 (9.7.6) はペア間ではなく**ターン間**の繰り返しで達成される。

## 9.10 信用取引: 対象ペアと統一モデル

`CUR/CUR`(FX)・`EQ/CUR`(株式)・`COMM/CUR`(コモディティ) を対象に、最大レバレッジ5倍のロング/ショート両方向の信用取引を可能にする。信用ポジションは現物取引と同じ板で取引され (注文に `trade_mode = MARGIN`, `position_side ∈ {LONG, SHORT}`, `intent ∈ {OPEN, CLOSE}`, `position_id` を付す、[14 API](14-api-reference.md))、通常の板寄せで約定価格が決まった後、強制決済対象のポジションがあれば決済注文を含めて再清算する (9.13)。

### 9.10.1 対象ペアと前提

- 信用取引の対象は `CUR/CUR`・`EQ/CUR`・`COMM/CUR` の3市場。ただし `COMM/CUR` のうち信用取引可能なのは storable な `COMM`(`agri`/`raw`/`mat`/`good`/`build`/`mil`/`energy.fuel`) のみとし、perishable (`labor.*`/`svc.*`/`energy.electricity`) は除外する。借入アセットは翌ターン以降に現物で返済される必要があるため、繰越不能なアセットは貸借の対象にできない ([00 用語集 0.5.3](00-glossary.md))。労働市場 (`COMM:labor.*@cc/CUR`) と債券市場 (`BOND`/`BILL`) は現物取引のみ (`SPOT`)。
- ロング/ショートとも最大レバレッジ5倍。レバレッジは「ポジション名目 / 自己証拠金」で測り、初期証拠金率 `initial_margin = 2000 bps`(= 1/5 = 20%、code `initial_margin_bps`) を満たす範囲でのみ建てられる。
- ドキュメントの既存の「空売り」の記述は全て信用取引に統合する (現物の空売り禁止 9.5 は維持、ショートは `Position` 負債 + 貸借プール借入で表現)。

### 9.10.2 ロング/ショートの統一モデル

信用ポジションはすべて「貸借プールからアセットを借り、自己証拠金を担保に建てる」操作に還元する。

- **ロング** (例 `EQ/CUR` 買い建て): `quote` 通貨 (CUR) をプールから借り、自己証拠金と合わせて `base`(EQ) を市場で買う。担保 = 買った `base`(+ 余剰 `quote`)、負債 = 借入 `quote`。
- **ショート** (例 `EQ/CUR` 売り建て): `base`(EQ) をプールから借り、市場で売って `quote` を得る。担保 = 売却で得た `quote` + 自己証拠金、負債 = 借入 `base`。
- **FX** (`CUR/CUR`) は両辺が通貨であり、ロング = `quote` を借りて `base` を持つ、ショート = `base` を借りて `quote` を持つ、と対称になる。
- **非負残高・保存則との整合**: 借入は現物残高をマイナスにせず、`Position`(信用ポジション) の負債として計上する ([00 用語集 0.9/0.17](00-glossary.md))。プールがアセットを貸し出すとき、現物アセットは `loan_id` を原因 (`Cause = LOAN`) とする移転でプール→借り手へ実際に移動し、同時にプール側へ同額の貸付債権、借り手側へ同額の返済債務を記録する。これにより現物アセットの総量は保存され (プールから出た現物は借り手が市場で売れば買い手の手に渡る)、純資産評価では貸付債権 (+) と返済債務 (−) がネットしてゼロになる。これが 08 §8.8 の `margin_owed` を置き換える。
- 信用は現物と同じ板で約定する: 借入 (LOAN) が先に着地し、新規建て注文が通常の板寄せで約定し、ポジションは約定価格で確定する。過剰借入の余剰は返済する。

## 9.11 証拠金とポジション会計

ポジション `Position` は `{position_id, entity, pair_id, side(LONG/SHORT), qty, entry_price, borrowed_asset, borrowed_qty, collateral_asset, collateral_qty, accrued_interest, open_tick}` を持つ (正準スキーマは [15 データモデル](15-data-model.md)、id は `POS:NNNNNN`)。

- **証拠金率 (equity ratio)** は毎ターン P4 完了後の清算価格 `p*` でマーク・トゥ・マーケットして算定する。評価はすべて `quote` 建ての整数 (WUI 換算でも一意、[08 §8.8.2](08-economy-and-ledger.md))。
  - `borrowed_value` = `borrowed_qty`(ロング、借入は `quote` 通貨) / `borrowed_qty × mark`(ショート、借入は `base` アセット)。
  - `collateral_value` = 担保時価 (`quote` 建て)。
  - `equity = collateral_value − borrowed_value − accrued_interest`。
  - `notional = qty × mark`。
  - `margin_ratio = equity / notional`(bps)。
- **初期証拠金 `initial_margin`** = 2000 bps (20%、5倍)。新規建ておよび増し建て (`intent = OPEN`) は P2 VALIDATE で `margin_ratio ≥ initial_margin` を要求し、満たさない数量はクランプする (9.5 の資金・在庫予約と同じ枠組み)。
- **維持証拠金 `maintenance_margin`** は資産クラス別に初期証拠金未満で定める (FX `1000 bps`(`maint_margin_fx_bps`)、コモディティ `1200 bps`(`maint_margin_comm_bps`)、株式 `1500 bps`(`maint_margin_equity_bps`))。`margin_ratio < maintenance_margin` のポジションを強制決済対象とする (9.13)。初期と維持の差 (buffer) が、強制決済が発動するまでに許容する逆行幅である。
- **純資産への反映**: 純資産 ([08 §8.8](08-economy-and-ledger.md), [11 §11.9.2](11-finance-and-instruments.md)) は「マーク済み台帳残高 + 貸借プール/AMM 持分債権 − Σ ポジション負債」で評価する。プール持分とポジション負債はエンティティ間でネットアウトし、系全体の純資産は保存する。投資家ランキング ([11 §11.9.3](11-finance-and-instruments.md)) は従来どおり WUI 換算純資産で一貫する。

## 9.12 貸借プール (Lending Pool)

信用取引の借入原資は、アセットごとに開設する**貸借プール**から供給する。プールは「余剰アセットを預け入れて貸付利息を得る供給者 (lender)」と「証拠金を差し入れてアセットを借りる需要者 (margin trader)」を仲介する公開ファシリティであり、利率を内生的に調整して需給を均衡させ続けることで持続可能性を担保する。

- **プールの単位**: 信用対象アセットごとに1プール。`LENDING_POOL` エンティティ (id `POOL:<asset_id>`、実台帳残高を持つ、[15 データモデル](15-data-model.md) の `LendingPool {asset, supplied, borrowed, total_shares, shares{entity→units}}`)。ロングは `quote` 通貨プールから、ショートは `base` アセットプールから借りる。`available = ledger(POOL, asset) = supplied − borrowed`。
- **供給と引出**: 供給者 (`INVESTOR`/`YIELD_INVESTOR`/`MARKET_MAKER` など余剰在庫を持つ任意保有者) はアセットをプールへ預け入れ (`Cause = POOL_SUPPLY`)、持分 (pool share) を受け取る (`qty · total_shares / pool_value`、空プールなら `qty`)。引出 (`Cause = POOL_WITHDRAW`) は持分按分で償還し、**利用可能残高 `available` の範囲でのみ即時可能**。全額貸出中 (利用率100%) のときは新規引出を待たせる代わりに利率が跳ね上がり (下記)、返済・強制決済による流入を促す。これにより部分準備による支払不能を構造的に排除する。
- **利用率連動金利 (utilization curve)**: 利用率 `U = borrowed / supplied`(bps) に対し、借入金利を折れ線で定める (DeFi マネーマーケット型のキンク・モデル。code は `fixed.borrow_rate_bps`/`supply_rate_bps`)。

```text
U ≤ U_kink:  borrow_rate = base_rate + U · slope1 / 10000
U >  U_kink: borrow_rate = base_rate + U_kink · slope1 / 10000 + (U − U_kink) · slope2 / 10000
supply_rate = floor( borrow_rate · U / 10000 · (10000 − reserve_factor) / 10000 )
既定: U_kink = 8000 bps(80%), slope1 = 400 bps, slope2 = 6000 bps, reserve_factor = 1000 bps(10%)
通貨プールの base_rate = policy_rate[s](リスクフリー金利に連動)、アセットプールの base_rate = lending_asset_base_rate_bps(既定 200)
```

- 利用率が上がるほど借入金利が上がり (借入抑制 + 供給誘引)、下がるほど下がる。`U_kink` 超では `slope2` で急峻に上げ、利用可能残高の枯渇を防ぐ。これが利用率を平均回帰させ、需給を自律均衡させる持続性の中核である。
- **利息の発生**: P7 FISCAL でポジション単位に単利按分で `interest = floor( borrowed_value × borrow_rate / 10000 / TURNS_PER_YEAR )`([11 §11.7.1](11-finance-and-instruments.md) と同式、`fixed.interest_per_turn` を再利用、丸めは floor、[00 用語集 0.20](00-glossary.md))。借り手は CUR の現物残高からプールへ支払い (`Cause = INTEREST`)、`accrued_interest` に反映 (未払分は累積)。`reserve_factor` 分は**保険基金**へ繰り入れ、残りはプールに残って供給者が持分の値上がりで実現する。利息は既存通貨/アセットの再配分でありミント/バーンを伴わない ([00 用語集 0.10/0.17](00-glossary.md))。
- **通貨プールと政策金利の整合**: 通貨プールの `base_rate` を当該国の `policy_rate[s]` に連動させることで、レバレッジ調達コストがリスクフリー金利を下回らないようにする。利上げ→信用調達コスト上昇→投機的レバレッジ縮小、という金融政策の波及経路 ([11 §11.3.4](11-finance-and-instruments.md) を補完) を内生化する。既存の常設預金ファシリティ ([11 §11.3.4](11-finance-and-instruments.md)) は市場性のない余剰現金の運用・調達 (政策金利での無担保1ターン貸借) として残し、貸借プールは**有担保のレバレッジ調達**を担う、と役割を分離する。
- **借入上限 = 利用可能残高**: ある借入要求が `available` を超える場合、超過分は当ターン約定不可としてクランプする。プールは在庫以上を貸さない。
- **プール操作の順序 (市場取引より前)**: 同一ターン内で、プールへの預け入れ・引き出しは P4 CLEAR の板寄せ (市場取引) より**前**に確定する。確定順は「預入 → 引出 → 板寄せ (新規ポジションの借入)」とし、板寄せで新規ポジションが借入を起こす時点の `available` は、当ターンの預入 (増) と引出 (減) を反映済みの値を参照する。引出は当ターン頭の `available`(= `supplied − 前ターンからの borrowed`) の範囲で処理し、当ターンの返済・強制決済による流入 (P4 内で発生) は当ターンの引出には充てず翌ターンの `available` へ反映する。預入・引出 API ([14](14-api-reference.md) `POST /v1/lending/{asset_id}/deposit|withdraw`) はキューされ、次の P4 開始時に適用する。
- **同一ターンの引出と新規オープンの競合**: 同じアセットのプールに対し、同一ターンで引き出しと新規ポジションのオープン (借入) が併発した場合、引出が先に `available` を減らすため、残余 `available` が不足すると新規オープンの借入は約定できずクランプ/失敗する (借入はファンド可能なサイズへクランプし、不足分のオープンは失効、9.5 の資金クランプと同枠組み)。これは**供給者の引出権を借り手の新規与信に優先させる**決定論的順序であり、プールが預け入れ資産の引出を常に honor できること (lender 信頼 = 供給の厚み = 持続可能性) を保証する。
- **genesis**: home 通貨プールのみシードする (`lending.genesis_supply` = `lending_genesis_supply_cur` = 2,000,000、持分はシード投資家へ)。その他のプールは空で始まり、供給者の預入で資金化する。

## 9.13 強制決済 (Forced Liquidation) — P4 内での反復板寄せ

維持証拠金を割ったポジションは、当ターンの P4 CLEAR 内で強制決済する。クライアントの意図注文ではなくエンジンが生成する**非自発的決済注文**を、同じ板へ投入して再清算する点が要点である (9.9.2 のフロー図参照)。

1. **予備清算**: まず当ターンの自発注文 (現物 + 信用新規建て + AMM ladder) だけで通常の板寄せ (9.3) を行い、予備清算価格 `p*_0` を得る。
2. **証拠金判定**: 全信用ポジションを予備清算価格 `p*_0` でマークし、`margin_ratio < maintenance_margin` のポジションを強制決済対象として抽出する。決定論のため対象を `margin_ratio` 昇順 → `entity_id` 昇順で整列する。
3. **決済注文の生成**: 各対象に非自発注文を生成する。アンダーウォーターなロングには**成行 SELL**、ショートには**成行 BUY**(買い戻し) を、`maintenance` を `initial_margin` まで回復させるのに必要な数量で部分決済する。回復不能なほど毀損している (`equity ≤ 0`) 場合は全量決済する (`close_factor` = 1ラウンドあたり最大決済割合で上限、既定 5000 bps = 50%、code `close_factor_bps`)。これらは成行のため板寄せでは「無限に有利な指値」として最優先で約定する (9.6.2)。
4. **再清算**: 生成した決済注文を板へ加え、板寄せを再実行して新たな `p*_1` を得る。決済注文が約定し、得た `quote`(ロング) / `base`(ショート) で借入を返済 (`Cause = REPAY`)、`Position` を縮小/消去する。
5. **カスケード反復 (数量スロットル)**: 再清算後の `p*_1` で全ポジションを再びマークし、新たに維持証拠金を割った対象があれば手順 3–4 を繰り返す。各対象は1ラウンドに `close_factor` を上限に部分決済されるため、清算がカスケードしても**1ターンに決済される総量は数量で律速される**。決定論と停止性のため反復回数を `liquidation_max_rounds`(既定 4、code `liquidation_max_rounds`) で打ち切り、未消化の対象は翌ターンへ持ち越す (引き続き対象フラグを維持)。
6. **値幅制限なし**: 約定価格 `p*` には上限・下限を設けない (値幅制限 = サーキットブレーカーは撤廃済み)。カスケードの抑制は手順 5 の数量スロットル (`close_factor`・`liquidation_max_rounds`) が担い、価格発見そのものは妨げない。
7. **清算ペナルティ**: 強制決済された名目に対し `liquidation_penalty`(既定 100 bps、code `liquidation_penalty_bps`) を借り手の担保から徴収し**保険基金**へ繰り入れる (`Cause = LIQUIDATION_PENALTY`)。これは保険基金の積み増しと、維持証拠金到達前の自主的なポジション管理インセンティブを兼ねる。清算 id は `LIQ:NNNNNN`。

```mermaid
flowchart TD
  A[P4 CLEAR: 自発注文で予備板寄せ → p*_0] --> B[全信用ポジションを p*_0 でマーク]
  B --> C{margin_ratio < maintenance?}
  C -- なし --> Z[確定: 決済・台帳反映 P5 へ]
  C -- あり --> D[対象を margin_ratio昇順→entity_id昇順で整列]
  D --> E[非自発決済注文を生成<br/>ロング=成行SELL / ショート=成行BUY<br/>close_factor 上限で部分/全決済]
  E --> F[決済注文を板へ加え 再板寄せ → p*_1<br/>値幅制限なし]
  F --> G[借入返済・Position 縮小<br/>清算ペナルティ→保険基金]
  G --> H{維持割れの対象が残る?<br/>ラウンド < liquidation_max_rounds}
  H -- Yes --> D
  H -- No --> Z
```

## 9.14 不良債権の吸収と持続可能性

価格が急変して担保が借入額を下回る (`equity < 0`) ケースは、値幅制限を撤廃した本設計では1ターンの価格変動に構造的な上限がないため、薄商いの急騰落でなお起こりうる (値幅制限がない分、早期・部分清算による数量スロットルが抑制の要となる)。これを次の三段の劣後順位で吸収し、**いかなる場合もミントに頼らず保存則を破らない**ことで持続可能性を担保する。

1. **借り手の残余担保**: まず借り手の担保全額を充当する (有限責任、追加負担なし)。
2. **保険基金 (insurance fund)**: 不足分は保険基金が補填する (`Cause = HAIRCUT` の移転)。基金は `INSURANCE_FUND` エンティティ (id `INSF:<cc>`、通貨ごとに1つ、実台帳残高を持つ、[15 データモデル](15-data-model.md) の `InsuranceFund`)。genesis シード `insurance.genesis_seed`(既定 1,000,000) + 清算ペナルティ + 金利スプレッド (`reserve_factor` 分) で積み上がる first-loss バッファ。
3. **供給者のヘアカット (last resort)**: 保険基金も尽きた残余は、当該アセットプールの供給者へ持分按分で決定論的にヘアカット (`pool.borrowed`/`supplied` の書き下げ、largest-remainder、[00 用語集 0.20](00-glossary.md)) として配賦する。これによりプールが債務超過 (支払不能) に陥ることはなく、損失は必ず実在の保有者間で清算される。

持続可能性を成り立たせる帰還ループを整理する。

- **利用率連動金利**で供給と借入を自律均衡させ、流動性枯渇を価格 (金利) で防ぐ。
- **早期・部分強制決済**(維持証拠金 > 0) でギャップ損失の発生確率を下げる。
- **数量スロットル**(`close_factor`・`liquidation_max_rounds`) が1ターンに清算される総量を律速し、清算カスケードを価格ではなく数量で抑える (値幅制限は撤廃)。
- **保険基金**がギャップ損失を吸収し、枯渇時のみ供給者ヘアカットへ劣後する。
- **保存則の厳守**: 貸付・利息・清算はすべて実在アセットの移転であり、`loan_id`/`liquidation_id` を原因に二重仕訳で記帳する。プールは在庫以上を貸さず、借り手は初期証拠金で常に過剰担保、損失は定義された劣後順位で必ず誰かが負担する。系全体としてアセットが創出/消滅することはない (中央銀行のミント/バーン点を除く)。

```mermaid
flowchart LR
  SUP[供給者: 余剰アセット預入] -->|pool share| POOL[(貸借プール<br/>per-asset)]
  POOL -->|借入 + 担保| MT[信用トレーダー]
  MT -->|利息 P7| POOL
  POOL -->|supply_rate 分配| SUP
  POOL -->|reserve_factor 分| INS[(保険基金)]
  MT -.->|清算ペナルティ.-> INS
  INS -.->|不良債権の補填.-> POOL
  POOL -.->|基金枯渇時のみ ヘアカット.-> SUP
```

## 9.15 相互リンク要約

- 台帳構造・二重仕訳・資産保存・純資産 (margin_owed の置換): [08 経済と台帳](08-economy-and-ledger.md)
- 債券/株式の発行・流通・配当・クーポンの市場固有規則・利息按分・WUI 純資産: [11 金融と金融商品](11-finance-and-instruments.md)
- 労働市場の供給・賃金・スキル: [05 エージェント](05-agents.md), [10 産業と生産](10-industry-and-production.md)
- 財市場・生産・在庫・関税の影響: [10 産業と生産](10-industry-and-production.md), [12 政治と統治](12-politics-and-government.md)
- ロール (INVESTOR 派生: trade_mode × style・YIELD_INVESTOR・ARBITRAGEUR・AMM)・role-gating: [06 ロール](06-roles.md)
- 注文 (`trade_mode`/`position_side`/`intent`/`position_id`)・貸借プール預入引出・観測・取消 API スキーマ: [14 API リファレンス](14-api-reference.md)
- `Position`/`LendingPool`/`InsuranceFund`/`AMMPool` の正準スキーマ・列挙 (`TradeMode`/`PositionSide`/`AMMInvariant`): [15 データモデル](15-data-model.md)
- 板寄せのターン内位置 (P4 CLEAR)・決定論・乱数・P7 利息: [03 時間とターン](03-time-and-turns.md)
- MM/ARBITRAGEUR/AMM/YIELD_INVESTOR の報酬・学習・観測: [07 機械学習](07-machine-learning.md)
- スプレッド・MM カバレッジ・`margin.*`/`lending.*`/`insurance.*`/`amm.*`/`arb.*` 等の既定値: [16 構成と初期化](16-configuration-and-initialization.md)
