# 06. ロール

本書は FinBox における**ロール (role)** を定義する。ロールは `AGENT`/`PLAYER` が持つ属性であり、許可される行動 (role-gating)・生産する労働種別または操作対象・報酬関数の方向性を規定する。ロール分類の正準定義は [用語集 0.14](00-glossary.md) にあり、本書はそれを詳細化する。本書はロールを再定義せず、用語集の列挙値・資産ID (`COMM:labor.*` 等)・エンティティID・産業分類・集約規則を参照する。矛盾を見つけた場合は用語集を正とする。

関連: [エージェント](05-agents.md)・[機械学習](07-machine-learning.md)・[市場と取引](09-markets-and-trading.md)・[産業と生産](10-industry-and-production.md)・[金融と金融商品](11-finance-and-instruments.md)・[政治と統治](12-politics-and-government.md)・[プレイヤーとマルチプレイヤー](13-players-and-multiplayer.md)・[構成と初期化](16-configuration-and-initialization.md)。

## 6.1 ロールの位置づけと原則

- **ロールは行動空間のゲート**: エージェントとプレイヤーは同一の FastAPI インターフェース・同一の認証・同一の行動スキーマを用いる ([用語集 0.2](00-glossary.md))。両者の差異はロールによる行動の可否 (role-gating) のみであり、情報の非対称性や特権は存在しない。ある行動 `action` が提出されたとき、P2 VALIDATE はそのエンティティの保有ロール集合が当該行動を許可するかを確認し、許可されなければ棄却する ([アーキテクチャ](02-architecture.md))。
- **ロールは複数持てる**: `roles` はロールコードの集合である。例えば `INVESTOR` かつ `ENTREPRENEUR` を併せ持つエージェントは両者の行動を提出できる。ただし労働者系ロール (6.3) は同時に1つのみ保持する (労働力は1ターンに1種別しか供給しない)。
- **ロールは報酬関数を切り替える**: 各ロールは [機械学習 07](07-machine-learning.md) で定義される報酬関数の構成要素 (重み) を選ぶ。本書は報酬の**方向性**(何を最大化しようとするか) のみを述べ、厳密な式・係数は 07 に委ねる。
- **ロールは可変**: ロールは genesis で配分され ([構成と初期化 16](16-configuration-and-initialization.md))、就労・昇格・引退・徴兵などにより遷移する (6.10)。遷移はすべてエンジンが決定論的に適用する。
- **エンティティ種別との関係**: ロールは `AGENT` と `PLAYER` のみが持つ。`FIRM`/`GOV`/`CB`/`EXCH` はロールを持たない制度的・法人的主体であり、ロールを持つエージェントが操作する ([用語集 0.4](00-glossary.md))。`POLITICIAN` が `GOV` を統治し、`CENTRAL_BANKER` が `CB` を執行し、`ENTREPRENEUR` が `FIRM` を運営する。

## 6.2 ロール分類ツリー

```mermaid
flowchart TD
  ROOT[Role] --> LAB[労働者系 households/labor]
  ROOT --> CAP[資本・経営系]
  ROOT --> PUB[公共系]

  LAB --> L_PROD[生産労働]
  LAB --> L_NONPROD[非生産状態]
  L_PROD --> FARMER & MINER & BUILDER & FACTORY_WORKER & SERVICE_WORKER & OFFICE_WORKER & LOGISTICS_WORKER & ENGINEER & HEALTHCARE_WORKER & TEACHER & RESEARCHER & SOLDIER
  L_NONPROD --> STUDENT & UNEMPLOYED & RETIREE

  CAP --> ENTREPRENEUR
  CAP --> INVESTOR
  INVESTOR --> MARKET_MAKER

  PUB --> POLITICIAN
  PUB --> CENTRAL_BANKER
  PUB --> BUREAUCRAT
  PUB --> GENERAL
  PUB --> DIPLOMAT
```

ロールは大きく3系統に分かれる。労働者系は労働力 (`COMM:labor.*`) を市場に供給する世帯エージェント、資本・経営系は資本を運用し企業を経営するエージェント、公共系は政府・中央銀行・軍の制度を執行するエージェントである。`MARKET_MAKER` は `INVESTOR` から派生する特化ロールである ([用語集 0.4, 0.11](00-glossary.md))。

## 6.3 労働者系ロール (households/labor)

労働者系ロールは毎ターン1単位 (基準) の労働力 `COMM:labor.*` を生産し、P4 CLEAR の労働市場 ([市場と取引 09](09-markets-and-trading.md)) で販売する。労働力は perishable であり、そのターンに約定しなければ消滅する ([用語集 0.5.3](00-glossary.md))。供給量・スキル補正・賃金受領は [エージェント 05](05-agents.md) の労働供給ループに従う。各ロールが生産する労働種別・就労先産業・主要スキル要件は下表に固定する。

| ロール | 生産する労働種別 | 就労先産業 | 主要スキル (`skill[*]`) | 報酬の方向性 |
| --- | --- | --- | --- | --- |
| `FARMER` | `COMM:labor.farm` | `AGRICULTURE` | `farm` | 賃金収入とニーズ充足 (満腹・健康・幸福) |
| `MINER` | `COMM:labor.mine` | `MINING` | `mine` | 賃金収入とニーズ充足 |
| `BUILDER` | `COMM:labor.build` | `CONSTRUCTION` | `build` | 賃金収入とニーズ充足 |
| `FACTORY_WORKER` | `COMM:labor.factory` | `MANUFACTURING`, `ENERGY` | `factory` | 賃金収入とニーズ充足 |
| `SERVICE_WORKER` | `COMM:labor.service` | `SERVICES`(小売・娯楽・接客) | `service` | 賃金収入とニーズ充足 |
| `OFFICE_WORKER` | `COMM:labor.office` | `FINANCE`, `SERVICES`, 全産業の管理部門 | `office` | 賃金収入とニーズ充足 |
| `LOGISTICS_WORKER` | `COMM:labor.unskilled` | `LOGISTICS` | `unskilled` | 賃金収入とニーズ充足 |
| `ENGINEER` | `COMM:labor.engineer` | `MANUFACTURING`, `ENERGY`, `CONSTRUCTION` | `engineer` | 高スキル賃金とニーズ充足 |
| `HEALTHCARE_WORKER` | `COMM:labor.health` | `SERVICES`(医療) | `health` | 賃金収入とニーズ充足 |
| `TEACHER` | `COMM:labor.research` | `SERVICES`(教育) | `research` | 賃金収入とニーズ充足 |
| `RESEARCHER` | `COMM:labor.research` | `RESEARCH` | `research` | 高スキル賃金とニーズ充足 |
| `SOLDIER` | `COMM:labor.soldier` | `GOV`(軍) | `soldier` | 俸給・国家忠誠・安全 (軍事 12 の労働投入) |
| `STUDENT` | (生産しない) | — | `education`, `skill[*]` 育成 | 教育水準・将来スキルの蓄積 |
| `UNEMPLOYED` | `COMM:labor.unskilled` | 任意 (低スキル枠) | `unskilled` | 就労・失業給付・転職機会の探索 |
| `RETIREE` | (生産しない) | — | — | 年金・貯蓄取崩しによるニーズ充足 |

注記:

- `LOGISTICS_WORKER` は `COMM:labor.unskilled` を供給する。物流 (`LOGISTICS`) の生産レシピ `svc.transport` が `labor.unskilled` を投入とするため ([10 §10.1, §10.4.3](10-industry-and-production.md))、物流労働は汎用 (unskilled) 労働力プールを `UNEMPLOYED` 等と共有し、`labor.office`(管理部門) と組み合わせて雇用される。`FACTORY_WORKER` の供給する `COMM:labor.factory`(製造・エネルギー向け) とは別資産である。`labor.*` の種別集合は [00 §0.5.2](00-glossary.md) の11種に固定され、物流専用の労働種別は設けない。
- `TEACHER` は教育サービス (`COMM:svc.education`) の生産に必要な `COMM:labor.research` を供給する。`RESEARCHER` と同じ労働種別を供給するが、就労先が `SERVICES`(教育) と `RESEARCH` で分かれる。`COMM:labor.research` を供給する以上、`TEACHER` も `RESEARCHER` と同じく [05 §5.3](05-agents.md) の学歴ゲート `edu_gate(research) = 50`(`education ≥ 50` で初めて `research` skill が `cap_low` 以上に上がる) を満たす必要がある。教育サービス供給ロールにも研究と同一の学歴要件が課される。
- `STUDENT` と `RETIREE` は労働力を生産しない非生産状態であり、消費とニーズ管理のみを行う ([エージェント 05](05-agents.md))。`STUDENT` は `COMM:svc.education` を消費して `education` と `skill[*]` を蓄積し、就労可能年齢・スキル要件を満たすと労働者系ロールへ遷移する (6.10)。
- `UNEMPLOYED` は `COMM:labor.unskilled` を供給できる過渡状態であり、いずれかの産業に約定すると対応する労働者系ロールへ遷移する (就労、6.10)。
- すべての労働者系ロールは投資家ではないが、保有現金で金融商品市場に参加できる範囲は [プレイヤーとマルチプレイヤー 13](13-players-and-multiplayer.md) と本書 6.9 の行動許可マトリクスに従う (既定では現物の購入・売却=自己の生活と貯蓄の範囲に限定し、指値による流動性供給や信用取引は `INVESTOR`/`MARKET_MAKER` に限る)。

## 6.4 経営者 `ENTREPRENEUR`

`ENTREPRENEUR` は企業 (`FIRM`) を設立・運営する資本・経営系ロールである。操作対象は自らが支配する `FIRM` のエンティティであり、企業に対する操作行動を提出する。生産・能力・資本の詳細は [産業と生産 10](10-industry-and-production.md) と [金融と金融商品 11](11-finance-and-instruments.md) に従う。

許可される行動 (role-gating):

- **企業設立 (`firm.found`)**: 産業 ([用語集 0.15](00-glossary.md)) と立地地域を指定し、最低資本要件 (`16`) を満たす自己資金を払い込んで新規 `FIRM` を生成する。設立者は初期株式 `EQ:firm.<id>` を保有する。
- **生産計画 (`firm.plan`)**: 次ターン P5 PRODUCE の生産レシピ・目標産出量・稼働率を設定する。投入財は労働市場・素材市場で購入する。
- **能力拡張 (`firm.expand`)**: 建設労働力 `COMM:build.construction_labor` を市場で購入・消費して設備・生産能力を拡張する ([用語集 0.5.2 の区別](00-glossary.md))。
- **雇用 (`firm.hire`)**: 労働市場で `COMM:labor.*` の買い注文を出して労働力を購入する。雇用は P4 CLEAR の賃金約定として成立する。
- **増資 (`firm.issue_equity`)**: 新株 `EQ:firm.<id>` を金融商品市場で発行し資本を調達する ([金融 11](11-finance-and-instruments.md))。
- **社債発行 (`firm.issue_bond`)**: 社債 `BOND:<...>` を発行し負債で資金調達する ([金融 11](11-finance-and-instruments.md))。
- **配当 (`firm.dividend`)**: 利益剰余金から株主へ配当を支給する (プロトコル移転、[用語集 0.10](00-glossary.md))。
- **自社株買い (`firm.buyback`)・清算 (`firm.liquidate`)**: 自己株式取得による `EQ` のバーン、または倒産・解散時の残余資産分配 ([産業と生産 10](10-industry-and-production.md))。

報酬の方向性: 企業価値 (純資産・株価・利益剰余金) の最大化と倒産回避。詳細式は [機械学習 07](07-machine-learning.md)。AI/プレイヤー可否: AI 可。プレイヤーは構成で解禁時のみ可 ([用語集 0.14](00-glossary.md), [13](13-players-and-multiplayer.md))。

## 6.5 投資家 `INVESTOR`

`INVESTOR` は金融市場で資産を運用する資本系ロールであり、**人間プレイヤーの既定ロール** ([用語集 0.14](00-glossary.md))。

許可される行動:

- **市場取引 (`order.submit` / `order.cancel`)**: FX (通貨ペア)・国債 (`BOND`/`BILL`)・株式 (`EQ`)・コモディティ (`COMM`)・(任意で `FUT`) について成行・指値・各種 TIF の注文を提出・取消する ([市場と取引 09](09-markets-and-trading.md))。
- **ポートフォリオ運用**: 複数資産・複数通貨にわたるポジション構築・リバランス。純資産は WUI 換算で評価される ([用語集 0.16](00-glossary.md))。
- **資金調達への参加**: 企業の増資・社債、政府の国債入札に応札する (買い手として)。

報酬の方向性: WUI 換算純資産 (`wealth`) のリスク調整後最大化。詳細式・リスク項は [機械学習 07](07-machine-learning.md)。AI/プレイヤー可否: AI 可・プレイヤー既定。

## 6.6 マーケットメイカー `MARKET_MAKER`

`MARKET_MAKER` は `INVESTOR` から派生する特化ロールであり、両建ての指値で市場に流動性を供給する ([用語集 0.4, 0.14](00-glossary.md))。独立のエンティティ種別ではなく `MARKET_MAKER` ロールを持つ `AGENT` である。

許可される行動:

- `INVESTOR` のすべての行動に加え、特定の取引ペアに対し継続的に**買い指値と売り指値を同時提示**(クォート) し、スプレッドを収益源とする ([市場と取引 09](09-markets-and-trading.md))。
- 在庫リスク管理 (ポジションの偏りに応じたクォートの非対称化)。

報酬の方向性: スプレッド収益と約定量の最大化、在庫リスク (片張りポジション) の最小化。詳細は [機械学習 07](07-machine-learning.md) と [市場と取引 09](09-markets-and-trading.md)。AI/プレイヤー可否: 既定でAI専用 (高頻度・継続クォートのため)。プレイヤーは `INVESTOR` として個別指値で流動性供給に近い行動は可能だが、`MARKET_MAKER` ロールは既定で付与されない。

## 6.7 公共系ロール

公共系ロールは国家の制度 (`GOV`/`CB`) を執行する。これらは既定でAI専用であり ([用語集 0.14](00-glossary.md))、プレイヤーには既定で付与されない ([13](13-players-and-multiplayer.md))。政治意思決定の集約は [用語集 0.12](00-glossary.md) と [政治と統治 12](12-politics-and-government.md) に従う。

### 6.7.1 政治家 `POLITICIAN`

各国に配属され、その国の政策を集団で決定する。各政治家は P1 SUBMIT で提案 (投票) を提出し、P3 GOVERN で [用語集 0.12](00-glossary.md) の集約規則 (SCALAR=平均, BINARY=平均≥0.5, CATEGORICAL=合計スコア最大, ALLOCATION=正規化重みの平均) に従い政策が確定する。

許可される行動:

- **政策投票 (`policy.vote`)**: 政策金利 (中央銀行への目標として、執行は `CENTRAL_BANKER`)・税率 (所得税・法人税・消費税)・関税・補助金・社会保障水準・国債発行枠・軍事予算 (ALLOCATION) を提案する ([政治と統治 12](12-politics-and-government.md))。
- **国債発行枠の決定 (`policy.debt_ceiling`)**: 政府 `GOV` が当ターン発行できる `BOND:gov.*`/`BILL:gov.*` の上限を集約により決める ([金融 11](11-finance-and-instruments.md))。
- **軍事命令 (`mil.order`)**: 攻撃目標・防衛配置の優先度を ALLOCATION で提案する。実行指揮は `GENERAL` (P8 MILITARY, [12](12-politics-and-government.md))。

報酬の方向性: 国家指標 (平均幸福度・GDP・治安・国民の `loyalty`・財政健全性) の改善。詳細は [機械学習 07](07-machine-learning.md)。

### 6.7.2 中央銀行家 `CENTRAL_BANKER`

中央銀行 `CB:<country_code>` を執行する。政治家が決定した目標 (政策金利) を制度的に執行し、独立した公開市場操作を行う。

許可される行動:

- **政策金利の執行 (`cb.set_rate`)**: P3 で確定した政策金利を `CB` の制度パラメーターとして適用する ([金融 11](11-finance-and-instruments.md))。
- **公開市場操作 (`cb.omo`)**: 国債の買入/売却による通貨の発行/吸収。通貨のミント/バーンは中央銀行のみが行える ([用語集 0.10, 0.17](00-glossary.md))。買入対象資産の授受は市場経由でもよく、現金注入はプロトコル移転として記録する。

報酬の方向性: 物価安定 (CPI・インフレ率の目標追従) と金融安定。詳細は [機械学習 07](07-machine-learning.md) と [金融 11](11-finance-and-instruments.md)。

### 6.7.3 官僚 `BUREAUCRAT`

政府 `GOV` の財政を執行する。政治家が決めた政策パラメーターを具体的なプロトコル移転として実行する。

許可される行動:

- **徴税・関税の執行 (`fisc.collect`)**: 所得税・法人税・消費税・関税を P7 FISCAL で徴収する (プロトコル移転、[用語集 0.10](00-glossary.md), [政治と統治 12](12-politics-and-government.md))。
- **補助金・社会保障・失業給付の支給 (`fisc.disburse`)**: P7 で対象エンティティへ支給する。
- **国債入札の運営 (`fisc.auction`)**: 政治家が決めた発行枠の範囲で国債/国庫短期証券を金融商品市場へ発行する ([金融 11](11-finance-and-instruments.md))。

報酬の方向性: 財政収支の均衡・債務対GDP比の管理・政策の確実な執行。詳細は [機械学習 07](07-machine-learning.md)。

### 6.7.4 将官 `GENERAL`

軍を指揮する。政治家が ALLOCATION で決めた軍事目標優先度に基づき、P8 MILITARY で具体的な戦闘・占領を解決する。

許可される行動:

- **軍事指揮 (`mil.command`)**: 軍需品 `COMM:mil.munitions` の消費による攻撃・防衛・マス占領の実行命令を出す ([政治と統治 12](12-politics-and-government.md))。
- **兵站管理 (`mil.logistics`)**: `SOLDIER` の労働投入 (`COMM:labor.soldier`) と軍需品在庫の配分。

報酬の方向性: 領土の保全・拡大、戦闘効率、軍需損耗の最小化。詳細は [機械学習 07](07-machine-learning.md) と [政治と統治 12](12-politics-and-government.md)。

### 6.7.5 外交 `DIPLOMAT` (任意)

国家間の関係を調整する任意ロール ([用語集 0.14](00-glossary.md))。構成で有効化されたときのみ存在する。

許可される行動:

- **外交行動 (`diplo.act`)**: 通商協定・関税協定・休戦/同盟の提案と締結の交渉 ([政治と統治 12](12-politics-and-government.md))。締結された協定は政策パラメーター (関税等) としてプロトコルに反映される。

報酬の方向性: 自国に有利な協定の締結・紛争コストの低減・貿易関係の改善。詳細は [機械学習 07](07-machine-learning.md)。

## 6.8 ロール別の操作対象とエンティティ

```mermaid
flowchart LR
  WRK[労働者系 AGENT] -->|労働力販売| EXCH[EXCH 労働市場]
  ENT[ENTREPRENEUR] -->|設立/運営| FIRM[FIRM 企業]
  FIRM -->|株式/社債| EXCH
  INV[INVESTOR / PLAYER] -->|注文| EXCH
  MM[MARKET_MAKER] -->|両建て指値| EXCH
  POL[POLITICIAN] -->|政策投票/発行枠| GOV[GOV 政府]
  BUR[BUREAUCRAT] -->|徴税/支給/入札| GOV
  GOV -->|国債| EXCH
  CBK[CENTRAL_BANKER] -->|金利/OMO| CB[CB 中央銀行]
  CB -->|通貨発行/吸収| EXCH
  GEN[GENERAL] -->|軍事指揮| GOV
  DIP[DIPLOMAT] -->|協定| GOV
```

## 6.9 行動許可マトリクス (ロール × 主要行動)

下表はロールごとの主要行動の許可を示す。`Y`=許可、空欄=不可。`PLAYER` は既定で `INVESTOR` 列に従い、構成で `ENTREPRENEUR` を解禁できる ([13](13-players-and-multiplayer.md))。労働者系は代表として1列に集約する (生産する労働種別のみ各ロールで異なる、6.3)。

| 行動 | 労働者系 | ENTREPRENEUR | INVESTOR | MARKET_MAKER | POLITICIAN | CENTRAL_BANKER | BUREAUCRAT | GENERAL | DIPLOMAT |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `labor.supply` 労働供給 | Y | | | | | | | | |
| `consume` 消費 | Y | Y | Y | Y | Y | Y | Y | Y | Y |
| `order.submit` 現物売買 (生活/貯蓄) | Y | Y | Y | Y | Y | Y | Y | Y | Y |
| `order.submit` 金融商品取引 (FX/債券/株式) | | Y | Y | Y | | | | | |
| `order.quote` 両建てクォート | | | | Y | | | | | |
| `firm.found`/`plan`/`expand`/`hire` 企業運営 | | Y | | | | | | | |
| `firm.issue_equity`/`issue_bond`/`dividend` 資本操作 | | Y | | | | | | | |
| `policy.vote`/`debt_ceiling` 政策決定 | | | | | Y | | | | |
| `cb.set_rate`/`omo` 金融政策執行 | | | | | | Y | | | |
| `fisc.collect`/`disburse`/`auction` 財政執行 | | | | | | | Y | | |
| `mil.order` 軍事方針 (ALLOCATION) | | | | | Y | | | | |
| `mil.command`/`logistics` 軍事指揮 | | | | | | | | Y | |
| `diplo.act` 外交 | | | | | | | | | Y |

## 6.10 ロール配属と流動性

ロールは固定ではなく、エージェントのライフサイクル ([エージェント 05](05-agents.md)) と経済状況に応じて遷移する。すべての遷移はエンジンが P6 CONSUME (加齢・出生・死亡・移住) と就労 (P4 CLEAR の労働約定結果) を踏まえて決定論的に適用する。

### 6.10.1 genesis 配分

初期人口のロール構成は [構成と初期化 16](16-configuration-and-initialization.md) のシナリオパラメーターで国別に与えられる。既定の配分方針 (構成で上書き可):

| ロール群 | 既定の人口シェア (目安) | 備考 |
| --- | --- | --- |
| 労働者系 (生産労働) | 約 70% | 産業構成に応じて各労働種別へ配分 |
| `STUDENT` | 約 8% | 就労前年齢層 |
| `RETIREE` | 約 10% | 退職年齢層 |
| `UNEMPLOYED` | 約 5% | 摩擦的失業の初期プール |
| `ENTREPRENEUR` | 約 2% | 初期企業の設立者 |
| `INVESTOR` | 約 1% | AI 投資家。プレイヤーはこれに加わる |
| 公共系 (`POLITICIAN`/`CENTRAL_BANKER`/`BUREAUCRAT`/`GENERAL`/`DIPLOMAT`) | 約 1% | 国ごとに固定数を配置 (各国の政治家数・官僚数は構成) |
| `SOLDIER` | 約 3% | 平時の常備軍規模。徴兵で増減 |

公共系ロールは人口シェアではなく**国ごとの固定枠**で配置されるのが既定である (例: 各国 `POLITICIAN` を `N_POLITICIANS` 体、`CENTRAL_BANKER` を1体、など。値は `16`)。プレイヤーは genesis 後に `INVESTOR` として新規 `PLAYER` エンティティで参加する ([13](13-players-and-multiplayer.md))。

### 6.10.2 ロール遷移 (state diagram)

```mermaid
stateDiagram-v2
  [*] --> STUDENT: 出生→就学
  STUDENT --> UNEMPLOYED: 就学完了 (スキル/年齢要件)
  UNEMPLOYED --> LABORER: 就労 (労働市場で約定)
  LABORER --> UNEMPLOYED: 失職 (雇用未成立が継続)
  LABORER --> LABORER: 転職 (別労働種別へ)
  UNEMPLOYED --> UNEMPLOYED: 求職継続
  LABORER --> ENTREPRENEUR: 昇格 (資本要件を充足)
  UNEMPLOYED --> ENTREPRENEUR: 起業 (資本要件を充足)
  ENTREPRENEUR --> INVESTOR: 廃業→資産運用へ
  LABORER --> SOLDIER: 徴兵/志願
  SOLDIER --> UNEMPLOYED: 除隊
  LABORER --> RETIREE: 退職 (退職年齢到達)
  UNEMPLOYED --> RETIREE: 退職
  ENTREPRENEUR --> RETIREE: 退職
  RETIREE --> [*]: 死亡
  LABORER --> [*]: 死亡
  note right of LABORER
    LABORER は 6.3 の生産労働ロール
    (FARMER..RESEARCHER) の総称。
    就労先産業に対応する労働種別を生産する。
  end note
```

> 図中の `LABORER` は 6.3 の生産労働ロール (`FARMER`/`MINER`/`BUILDER`/`FACTORY_WORKER`/`SERVICE_WORKER`/`OFFICE_WORKER`/`LOGISTICS_WORKER`/`ENGINEER`/`HEALTHCARE_WORKER`/`TEACHER`/`RESEARCHER`) の総称である。`INVESTOR`/`MARKET_MAKER` および公共系ロールは genesis 配置または構成による割当で付与され、通常のライフサイクル遷移には含めない (AI 専用枠として固定数を維持する)。

### 6.10.3 遷移の条件とコスト

| 遷移 | 条件 | コスト/効果 |
| --- | --- | --- |
| 就学完了 (`STUDENT`→`UNEMPLOYED`) | `age ≥ WORK_AGE_MIN` かつ `education ≥ EDU_MIN` | 蓄積した `skill[*]` を保持して労働市場へ |
| 就労 (`UNEMPLOYED`→`LABORER`) | 当該労働種別の買い注文と P4 で賃金約定が成立 | 約定産業に対応するロールへ即時遷移。無コスト |
| 転職 (`LABORER`→別`LABORER`) | 別の労働種別の市場で約定 | 新労働種別の `skill` が低い場合は供給賃金にスキル割引 (07, 05) |
| 失職 (`LABORER`→`UNEMPLOYED`) | `UNEMP_GRACE` ターン連続で雇用未成立 | 失業給付の受給資格 (P7, 12) |
| 昇格/起業 (→`ENTREPRENEUR`) | 純資産 `wealth ≥ FOUND_CAPITAL_MIN`(`16`) を企業へ払込可能 | 最低資本を `FIRM` に拠出。失敗すると現金損失 |
| 徴兵/志願 (`LABORER`/`UNEMPLOYED`→`SOLDIER`) | 軍事動員命令 (12) または自発志願 | `COMM:labor.soldier` 供給へ切替。俸給は `GOV` から |
| 除隊 (`SOLDIER`→`UNEMPLOYED`) | 動員解除または契約満了 | 求職プールへ復帰 |
| 退職 (→`RETIREE`) | `age ≥ RETIRE_AGE` | 労働供給停止。年金受給 (P7, 12) と貯蓄取崩し |
| 死亡 (→ 終了) | `health ≤ 0` または `age ≥ AGE_MAX`(05) | 残余資産は相続/清算規則 (05, 16) で処理 |

上記の閾値定数 (`WORK_AGE_MIN`, `EDU_MIN`, `UNEMP_GRACE`, `FOUND_CAPITAL_MIN`, `RETIRE_AGE`, `AGE_MAX` 等) はすべて [構成と初期化 16](16-configuration-and-initialization.md) で定義し、本書は名前のみを参照する。スキル要件・賃金割引の式は [エージェント 05](05-agents.md) と [機械学習 07](07-machine-learning.md) に従う。

## 6.11 ロールと報酬・観測の対応

各ロールは [機械学習 07](07-machine-learning.md) の観測空間サブセットと報酬関数を選ぶ。本書はロールの責務 (何を操作し何を最大化するか) を定義し、07 はそれを学習可能な報酬・観測として具体化する。対応の概略:

- 労働者系 → 個人のニーズ充足と賃金・貯蓄 (`wealth`)。
- `ENTREPRENEUR` → 企業価値と存続。
- `INVESTOR`/`MARKET_MAKER` → WUI 換算純資産 (とスプレッド収益)。
- `POLITICIAN`/`BUREAUCRAT` → 国家マクロ指標と財政。
- `CENTRAL_BANKER` → 物価・金融安定。
- `GENERAL`/`DIPLOMAT` → 領土・安全保障・対外関係。

ロールを変更したエージェントは、遷移後のロールに対応する報酬関数へ切り替わる (07)。これにより、例えば失業者が就労すると報酬が賃金獲得方向へ、起業すると企業価値方向へと変化する。
