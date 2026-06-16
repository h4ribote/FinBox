# CLAUDE.md

このファイルは、本リポジトリで作業する際に Claude Code が従うべき方針を定めるものです。

## 作業方針

- 常に最適なロジックを組み込むことを最優先とする。工数や後方互換性などのコストは考慮せず、最善の実装を選択して進めること。

## ドキュメントと実装の整合性

- ドキュメントと実装は、常に差異がない状態を維持すること。
- 矛盾・衝突、または「未実装であるにも関わらずドキュメントに記載されている」といった不整合を確認した場合は、速やかに問題を解消すること。
- 未実装箇所は、ドキュメントの記載に合わせて完全に実装すること(ドキュメント側を削って辻褄を合わせるのではなく、実装を完成させること)。

## Documentation style

- No formatting line breaks: never hard-wrap a sentence or a list item across physical lines just to limit width (same rule as the `/commit` command). Keep each paragraph and each bullet on one physical line, however long; if a bullet grows unwieldy, split it into separate bullets rather than wrapping it.
- Markdown tables: do not pad cells with spaces to align columns. Use the minimal `| a | b |` form with a `| --- | --- |` separator row.
- Diagrams: render figures as Mermaid (```` ```mermaid ```` fenced blocks) — sequence, flow/dependency, state, directory trees, and packet/byte layouts (`packet-beta`). Keep plain code fences only for literal code, shell commands, and serialization pseudo-code (listings, not figures).

## コミット

- コミット時には、`/commit` に沿った手順・フォーマットでコミットを実行すること。
