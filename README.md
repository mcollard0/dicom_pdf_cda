MVPOC PDF a/o CDA Converter to DICOM
Michael Collard (The Sheep!)

From conversation:
https://www.linkedin.com/posts/hiroyuki-kubota-78063b167_%E5%B0%91%E3%81%97%E3%83%AC%E3%82%A2%E3%81%AAdicom%E3%82%AA%E3%83%96%E3%82%B8%E3%82%A7%E3%82%AF%E3%83%88%E3%82%92%E6%A4%9C%E8%A8%BC%E3%81%99%E3%82%8B%E5%BF%85%E8%A6%81%E3%81%AB%E8%BF%AB%E3%82%89%E3%82%8Cencapsulated-activity-7426810851090911232-wMmI?utm_source=share&utm_medium=member_desktop&rcm=ACoAAAQSl8sBFwXyitNFA2zrJjRVtLsVm-UFHGg

少しレアなDICOMオブジェクトを検証する必要に迫られ、Encapsulated PDF Storage SOP ClassとEncapsulated CDA Storage SOP Classのサンプルデータを生成してみた。どちらもPDFや任意のファイルをDICOMでカプセル化することで、DICOM3.0やDICOMwebで検索することができるDICOMの歴史の中では比較的新しい規格である。従来ならバイナリエディタで自ら作るか、少し楽にDVTk（DICOM Validation Toolkit）でテキストからコンパイルするしかなかったのが、生成AIのKiroで自然言語の対話で作れるようになった。米国では一般的に考慮されない文字符号化やPN型（人名型）は訂正が必要だったが、OSSのDICOMサーバーのHorosやOrthancのチェックを通過するオブジェクトが作られた。生産性はとても高いので、DICOMの世界にいる人にはぜひ使ってみてほしい。
We needed to verify a slightly rare DICOM object, so we generated sample data for the Encapsulated PDF Storage SOP Class and the Encapsulated CDA Storage SOP Class. Both are relatively new standards in the history of DICOM that can be searched with DICOM 3.0 or DICOMweb by encapsulating PDFs and arbitrary files in DICOM. Previously, you had to create it yourself in a binary editor or compile it from text with DVTk (DICOM Validation Toolkit) a little easier, but now you can create it with natural language dialogue with Kiro, a generative AI. Character encoding and PN type (personal name type), which are not generally considered in the United States, needed to be corrected, but objects that passed the checks of Horos and Orthanc on OSS's DICOM server were created. It's very productive, so I would like anyone in the DICOM world to try it.

